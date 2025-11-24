# api/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from rest_framework.decorators import (
    api_view, permission_classes, authentication_classes
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import TokenAuthentication, BasicAuthentication
from rest_framework.response import Response
from rest_framework import status
from .models import (
    Customer, Device, SensorConfiguration, SensorData, SensorType, IoTData
)
from .serializers import DeviceSerializer, SensorDataSerializer, IoTDataSerializer
from .forms import SensorDataForm
from rest_framework.authtoken.models import Token
import json


import os
import logging
from django.conf import settings
try:
    from twilio.rest import Client
except Exception:
    Client = None  # Twilio not installed; send_sms will raise if used

logger = logging.getLogger(__name__)

# Simple in-memory cooldown for alerts: {(device_id, sensor_label): timestamp}
_last_alert_sent = {}

def get_twilio_client():
    account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None) or os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None) or os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        raise RuntimeError("Twilio credentials are not configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN).")
    if Client is None:
        raise RuntimeError("twilio package not installed. Add 'twilio' to requirements.txt.")
    return Client(account_sid, auth_token)

def send_sms(body: str, to: str = None, from_number: str = None):
    """
    Send SMS to one or more recipients.
    ALERT_SMS_TO may contain comma or space separated numbers.
    """
    raw_to = to or getattr(settings, "ALERT_SMS_TO", None) or os.getenv("ALERT_SMS_TO")
    if not raw_to:
        raise RuntimeError("No recipient phone number(s) configured (ALERT_SMS_TO).")

    # Split by comma or space
    numbers = [n.strip() for n in raw_to.replace(" ", ",").split(",") if n.strip()]

    from_number = from_number or getattr(settings, "TWILIO_FROM_NUMBER", None) or os.getenv("TWILIO_FROM_NUMBER")
    client = get_twilio_client()

    sids = []
    for num in numbers:
        msg = client.messages.create(body=body, from_=from_number, to=num)
        logger.info("Sent SMS alert sid=%s to=%s", getattr(msg, "sid", ""), num)
        sids.append(getattr(msg, "sid", None))

    return sids

def _should_send_alert(device_id, sensor_label, cooldown_seconds=None):
    import time
    cooldown_seconds = cooldown_seconds or getattr(settings, "SMS_ALERT_COOLDOWN_SECONDS", 1800)
    key = (device_id, sensor_label)
    last = _last_alert_sent.get(key)
    now = time.time()
    if last and (now - last) < cooldown_seconds:
        return False
    _last_alert_sent[key] = now
    return True

def _normalize_label(label: str) -> str:
    """
    Normalize various sensor labels to canonical keys used for thresholds.
    This lets us handle labels like 't1_in', 'T1-IN', 'T1 INLET', etc.
    """
    if not label:
        return ""
    l = label.strip().lower()

    # Temperature probes
    # Your actual labels: t1_in, t1_out, t2_in, t2_out
    if l in ("t1_in", "t1in", "t1-in", "t1 inlet", "t1 in"):
        return "t1in"
    if l in ("t2_in", "t2in", "t2-in", "t2 inlet", "t2 in"):
        return "t2in"
    if l in ("t1_out", "t1out", "t1-out", "t1 outlet", "t1 out"):
        return "t1out"
    if l in ("t2_out", "t2out", "t2-out", "t2 outlet", "t2 out"):
        return "t2out"

    # Pressure – your label: dpt1
    if l in ("pressure", "press", "dpt", "dpt1", "dp", "dp1"):
        return "pressure"

    # Fouling
    if "foul" in l:
        return "fouling"

    # Fallback: use original lowercased label
    return l


def _get_threshold_for_label(label):
    """
    Return (threshold_value, direction) for a canonical label.
    Label must already be normalized via _normalize_label().
    """
    label = label.lower()
    thresholds = {
        "t1in": getattr(settings, "THRESHOLD_T1IN", None),
        "t2in": getattr(settings, "THRESHOLD_T2IN", None),
        "t1out": getattr(settings, "THRESHOLD_T1OUT", None),
        "t2out": getattr(settings, "THRESHOLD_T2OUT", None),
        "pressure": getattr(settings, "THRESHOLD_PRESSURE", None),
        "fouling": getattr(settings, "THRESHOLD_FOULING", None),
    }
    defaults = {
        "t1in": 80.0,
        "t2in": 80.0,
        "t1out": 80.0,
        "t2out": 80.0,
        "pressure": 10.0,
        "fouling": 0.001,
    }
    thr = thresholds.get(label)
    if thr is None:
        thr = defaults.get(label)
    if thr is None:
        return None, None  # no threshold configured for this label
    direction = "gt"  # for now: alert when value > threshold
    return float(thr), direction


def check_and_alert(device, sensor_label, value):
    """
    Check threshold for the given sensor_label and send SMS alert if threshold crossed.
    This function is defensive — any exception is logged and swallowed so it doesn't break ingest.
    """
    try:
        # Normalize to canonical label used by thresholds
        canonical = _normalize_label(sensor_label)
        thr, direction = _get_threshold_for_label(canonical)
        if thr is None:
            return False

        # Convert value to float
        val = float(value)
        exceeded = False
        if direction == "gt" and val > thr:
            exceeded = True
        elif direction == "lt" and val < thr:
            exceeded = True

        if exceeded and _should_send_alert(device.id, canonical):
            to = getattr(settings, "ALERT_SMS_TO", None) or os.getenv("ALERT_SMS_TO")
            body = (
                f"ALERT: Device '{device.name}' sensor '{sensor_label}' "
                f"value={val} exceeded threshold={thr}."
            )
            try:
                send_sms(body=body, to=to)
            except Exception as e:
                logger.exception("Failed to send SMS alert: %s", e)
            return True
    except Exception:
        logger.exception("Error during check_and_alert for %s", sensor_label)
    return False

from collections import defaultdict
import math

# ------------------------
# Helper utilities
# ------------------------
def latest_chronological(queryset, n):
    """
    Return the latest `n` records from `queryset` ordered oldest -> newest.
    """
    return list(queryset.order_by("-created_at")[:n])[::-1]

def format_ist_timestamp(dt):
    """
    Convert datetime to IST timezone and format as string
    """
    # Activate IST timezone
    ist = timezone.get_fixed_timezone(330)  # IST is UTC+5:30 (330 minutes)
    if timezone.is_aware(dt):
        ist_time = dt.astimezone(ist)
    else:
        ist_time = timezone.make_aware(dt, timezone=ist)
    
    return ist_time.strftime("%Y-%m-%d %H:%M:%S")

# ==================== FOULING FACTOR CALCULATIONS ====================

def calculate_clean_overall_heat_transfer_coefficient(
    hot_flow_rate, cold_flow_rate, 
    hot_inlet_temp, hot_outlet_temp,
    cold_inlet_temp, cold_outlet_temp,
    heat_transfer_area
):
    """
    Calculate clean overall heat transfer coefficient (U_clean)
    
    Parameters:
    - hot_flow_rate: Hot fluid flow rate (kg/s)
    - cold_flow_rate: Cold fluid flow rate (kg/s)  
    - hot_inlet_temp: Hot fluid inlet temperature (°C)
    - hot_outlet_temp: Hot fluid outlet temperature (°C)
    - cold_inlet_temp: Cold fluid inlet temperature (°C)
    - cold_outlet_temp: Cold fluid outlet temperature (°C)
    - heat_transfer_area: Heat transfer area (m²)
    
    Returns:
    - U_clean: Clean overall heat transfer coefficient (W/m²·K)
    - heat_duty: Heat transfer rate (W)
    - lmtd: Log Mean Temperature Difference (K)
    """
    # Specific heat capacity of water (J/kg·K) - can be parameterized later
    cp = 4186  # J/kg·K
    
    # Calculate heat duty from both streams
    heat_duty_hot = hot_flow_rate * cp * (hot_inlet_temp - hot_outlet_temp)
    heat_duty_cold = cold_flow_rate * cp * (cold_outlet_temp - cold_inlet_temp)
    
    # Use average heat duty
    heat_duty = (heat_duty_hot + heat_duty_cold) / 2
    
    # Calculate Log Mean Temperature Difference (LMTD)
    delta_t1 = hot_inlet_temp - cold_inlet_temp  # Temperature difference at one end
    delta_t2 = hot_outlet_temp - cold_outlet_temp  # Temperature difference at other end
    
    if delta_t1 <= 0 or delta_t2 <= 0:
        raise ValueError("Temperature cross detected - check input temperatures")
    
    if delta_t1 == delta_t2:
        lmtd = delta_t1
    else:
        lmtd = (delta_t1 - delta_t2) / math.log(delta_t1 / delta_t2)
    
    # Calculate clean overall heat transfer coefficient
    U_clean = heat_duty / (heat_transfer_area * lmtd)
    
    return {
        'U_clean': U_clean,
        'heat_duty': heat_duty,
        'lmtd': lmtd,
        'heat_duty_hot': heat_duty_hot,
        'heat_duty_cold': heat_duty_cold
    }

def calculate_fouling_factor(
    hot_flow_rate, cold_flow_rate,
    hot_inlet_temp, hot_outlet_temp, 
    cold_inlet_temp, cold_outlet_temp,
    heat_transfer_area, U_clean
):
    """
    Calculate fouling factor based on current operating conditions
    
    Parameters:
    - All previous parameters plus:
    - U_clean: Clean overall heat transfer coefficient (W/m²·K)
    
    Returns:
    - fouling_factor: Fouling factor (m²·K/W)
    - U_actual: Actual overall heat transfer coefficient (W/m²·K)
    - performance_ratio: Ratio of actual to clean heat transfer performance
    """
    
    # Calculate actual overall heat transfer coefficient
    clean_data = calculate_clean_overall_heat_transfer_coefficient(
        hot_flow_rate, cold_flow_rate,
        hot_inlet_temp, hot_outlet_temp,
        cold_inlet_temp, cold_outlet_temp,
        heat_transfer_area
    )
    
    U_actual = clean_data['U_clean']
    heat_duty = clean_data['heat_duty']
    lmtd = clean_data['lmtd']
    
    # Calculate fouling factor
    if U_actual > 0 and U_clean > 0:
        fouling_factor = (1/U_actual) - (1/U_clean)
        performance_ratio = U_actual / U_clean
    else:
        fouling_factor = 0
        performance_ratio = 0
    
    return {
        'fouling_factor': max(fouling_factor, 0),  # Fouling factor cannot be negative
        'U_actual': U_actual,
        'U_clean': U_clean,
        'performance_ratio': performance_ratio,
        'heat_duty': heat_duty,
        'lmtd': lmtd,
        'fouling_resistance': fouling_factor * 10000  # Convert to cm²·K/W
    }

def assess_fouling_severity(fouling_factor):
    """
    Assess the severity of fouling based on fouling factor value
    
    Parameters:
    - fouling_factor: Fouling factor (m²·K/W)
    
    Returns:
    - severity: Text description of fouling severity
    - recommendation: Maintenance recommendation
    - color_code: Color code for UI display
    """
    fouling_resistance_cm2 = fouling_factor * 10000  # Convert to cm²·K/W
    
    if fouling_resistance_cm2 < 0.0001:
        return {
            'severity': 'No Fouling',
            'recommendation': 'Normal operation',
            'color_code': 'green',
            'risk_level': 'Low'
        }
    elif fouling_resistance_cm2 < 0.0005:
        return {
            'severity': 'Minor Fouling', 
            'recommendation': 'Monitor closely, consider routine cleaning',
            'color_code': 'blue',
            'risk_level': 'Low'
        }
    elif fouling_resistance_cm2 < 0.001:
        return {
            'severity': 'Moderate Fouling',
            'recommendation': 'Schedule cleaning in near future',
            'color_code': 'yellow', 
            'risk_level': 'Medium'
        }
    elif fouling_resistance_cm2 < 0.002:
        return {
            'severity': 'Severe Fouling',
            'recommendation': 'Schedule immediate cleaning',
            'color_code': 'orange',
            'risk_level': 'High'
        }
    else:
        return {
            'severity': 'Critical Fouling',
            'recommendation': 'Emergency shutdown required for cleaning',
            'color_code': 'red',
            'risk_level': 'Critical'
        }

# ==================== FOULING FACTOR API ENDPOINTS ====================

@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def calculate_fouling_api(request):
    """
    API endpoint to calculate fouling factor
    """
    try:
        data = request.data
        
        required_params = [
            'hot_flow_rate', 'cold_flow_rate', 
            'hot_inlet_temp', 'hot_outlet_temp',
            'cold_inlet_temp', 'cold_outlet_temp', 
            'heat_transfer_area', 'U_clean'
        ]
        
        # Validate required parameters
        for param in required_params:
            if param not in data:
                return Response(
                    {"error": f"Missing required parameter: {param}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Extract parameters
        hot_flow_rate = float(data['hot_flow_rate'])
        cold_flow_rate = float(data['cold_flow_rate'])
        hot_inlet_temp = float(data['hot_inlet_temp'])
        hot_outlet_temp = float(data['hot_outlet_temp'])
        cold_inlet_temp = float(data['cold_inlet_temp'])
        cold_outlet_temp = float(data['cold_outlet_temp'])
        heat_transfer_area = float(data['heat_transfer_area'])
        U_clean = float(data['U_clean'])
        
        # Calculate fouling factor
        result = calculate_fouling_factor(
            hot_flow_rate, cold_flow_rate,
            hot_inlet_temp, hot_outlet_temp,
            cold_inlet_temp, cold_outlet_temp,
            heat_transfer_area, U_clean
        )
        
        # Add severity assessment
        severity_info = assess_fouling_severity(result['fouling_factor'])
        result.update(severity_info)
        
        # Add timestamp
        result['calculated_at'] = format_ist_timestamp(timezone.now())
        
        return Response(result)
        
    except ValueError as e:
        return Response(
            {"error": f"Invalid parameter value: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {"error": f"Calculation failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(["POST"])
@authentication_classes([TokenAuthentication]) 
@permission_classes([IsAuthenticated])
def calculate_clean_u_api(request):
    """
    API endpoint to calculate clean overall heat transfer coefficient
    """
    try:
        data = request.data
        
        required_params = [
            'hot_flow_rate', 'cold_flow_rate',
            'hot_inlet_temp', 'hot_outlet_temp', 
            'cold_inlet_temp', 'cold_outlet_temp',
            'heat_transfer_area'
        ]
        
        # Validate required parameters
        for param in required_params:
            if param not in data:
                return Response(
                    {"error": f"Missing required parameter: {param}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Extract parameters
        hot_flow_rate = float(data['hot_flow_rate'])
        cold_flow_rate = float(data['cold_flow_rate'])
        hot_inlet_temp = float(data['hot_inlet_temp'])
        hot_outlet_temp = float(data['hot_outlet_temp'])
        cold_inlet_temp = float(data['cold_inlet_temp'])
        cold_outlet_temp = float(data['cold_outlet_temp'])
        heat_transfer_area = float(data['heat_transfer_area'])
        
        # Calculate clean overall heat transfer coefficient
        result = calculate_clean_overall_heat_transfer_coefficient(
            hot_flow_rate, cold_flow_rate,
            hot_inlet_temp, hot_outlet_temp,
            cold_inlet_temp, cold_outlet_temp,
            heat_transfer_area
        )
        
        # Add timestamp
        result['calculated_at'] = format_ist_timestamp(timezone.now())
        
        return Response(result)
        
    except ValueError as e:
        return Response(
            {"error": f"Invalid parameter value: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {"error": f"Calculation failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# ==================== FOULING FACTOR UI VIEWS ====================

@login_required
def fouling_calculator(request):
    """
    UI view for fouling factor calculator
    """
    return render(request, "api/fouling_calculator.html")

@login_required
def fouling_monitoring(request, device_id):
    """
    UI view for fouling factor monitoring for a specific device
    """
    device = get_object_or_404(Device, id=device_id, customer__user=request.user)
    return render(request, "api/fouling_monitoring.html", {"device": device})

# ==================== AUTH ====================

def customer_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            try:
                customer = Customer.objects.get(user=user)
                return redirect("customer_dashboard_ui", dashboard_uuid=customer.dashboard_url)
            except Customer.DoesNotExist:
                return render(request, "login.html", {"error": "No customer linked"})
        return render(request, "login.html", {"error": "Invalid credentials"})
    return render(request, "login.html")


def customer_logout(request):
    logout(request)
    return redirect("customer_login")


# ==================== CUSTOMER UI ====================

@login_required
def customer_dashboard(request):
    customer = get_object_or_404(Customer, user=request.user)
    devices = Device.objects.filter(customer=customer, is_active=True)
    # Use helper to fetch latest 5 records but in chronological order (oldest->newest)
    recent_data = latest_chronological(SensorData.objects.filter(device__in=devices), 5)

    return render(request, "api/customer_dashboard.html", {
        "customer": customer, "devices": devices, "recent_data": recent_data
    })

@login_required
def customer_dashboard_uuid(request, dashboard_uuid):
    customer = get_object_or_404(Customer, dashboard_url=dashboard_uuid, user=request.user)
    devices = Device.objects.filter(customer=customer, is_active=True)
    return render(request, "api/customer_dashboard.html", {
        "customer": customer, "devices": devices, "dashboard_uuid": dashboard_uuid
    })


def device_detail(request, device_id):
    device = get_object_or_404(Device, id=device_id)
    # Fetch latest 50 readings in chronological order for display
    sensor_readings = latest_chronological(SensorData.objects.filter(device=device), 50)

    sensor_data = defaultdict(list)
    for r in sensor_readings:
        # Convert to IST timezone
        ist_timestamp = format_ist_timestamp(r.created_at)
        sensor_data[r.sensor_config.sensor_label].append({
            "timestamp": ist_timestamp,  # Use IST timestamp
            "value": r.value,
        })

    return render(request, "api/device_detail.html", {
        "device": device,
        "sensor_readings": sensor_readings,
        "sensor_data_json": json.dumps(sensor_data),
    })


@login_required
def device_detail_ui(request, device_id):
    return device_detail(request, device_id)


@login_required
def add_sensor_data(request):
    customer = get_object_or_404(Customer, user=request.user)
    if request.method == "POST":
        form = SensorDataForm(customer, request.POST)
        if form.is_valid():
            form.save()
            return redirect("customer_dashboard")
    else:
        form = SensorDataForm(customer)
    return render(request, "api/add_sensor_data.html", {"form": form})


@login_required
def sensor_configurations(request):
    customer = get_object_or_404(Customer, user=request.user)
    devices = Device.objects.filter(customer=customer, is_active=True)
    configs = SensorConfiguration.objects.filter(device__in=devices)
    return render(request, "api/sensor_configurations.html", {"configs": configs, "devices": devices})


# ==================== API: DEVICE WRITE ====================

@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def write_data(request, device_id):
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header:
        return Response({"error": "Authorization header required"}, status=401)
    auth_key = auth_header.split(" ")[-1]

    try:
        device = Device.objects.get(id=device_id, write_api_key=auth_key, is_active=True)
    except Device.DoesNotExist:
        return Response({"error": "Invalid device or API key"}, status=401)

    created_data = []
    for sensor_label, value in request.data.items():
        if value in [None, "", "null", "None"]:
            continue
        sensor_config, _ = SensorConfiguration.objects.get_or_create(
            device=device,
            sensor_label=sensor_label,
            defaults={
                "sensor_type": SensorType.objects.get_or_create(name="Generic", defaults={"unit": "unit"})[0]
            },
        )
        d = SensorData.objects.create(device=device, sensor_config=sensor_config, value=float(value))
        created_data.append(d)

        # --- SMS Alerting: check thresholds for important sensors (non-blocking) ---
        try:
            # call check_and_alert for some sensor labels (t1in,t2in,t1out,t2out,pressure,fouling)
            check_and_alert(device, sensor_config.sensor_label, d.value)
        except Exception as e:
            logger.exception("SMS alert check failed: %s", e)


    return Response([
        {"id": d.id, "device": d.device.id, "sensor_label": d.sensor_config.sensor_label,
         "value": d.value, "created_at": format_ist_timestamp(d.created_at)}  # Use IST timestamp
        for d in created_data
    ], status=201 if created_data else 400)


# ==================== DASHBOARD DATA ====================

@login_required
def customer_dashboard_data(request, dashboard_uuid):
    customer = get_object_or_404(Customer, user=request.user, dashboard_url=dashboard_uuid)
    devices = Device.objects.filter(customer=customer, is_active=True)
    dashboard_data = []

    for device in devices:
        # Get latest 200 records in chronological order
        readings = latest_chronological(SensorData.objects.filter(device=device), 200)
        sensor_data = defaultdict(list)
        for r in readings:
            # Convert to IST timezone
            ist_timestamp = format_ist_timestamp(r.created_at)
            sensor_data[r.sensor_config.sensor_label].append({
                "timestamp": ist_timestamp,  # Use IST timestamp
                "value": r.value,
            })
        
        dashboard_data.append({
            "device_id": device.id,
            "device_name": device.name,
            "sensor_data": sensor_data,
        })

    return Response({
        "customer": customer.company_name,
        "dashboard_uuid": str(customer.dashboard_url),
        "devices": dashboard_data,
    })


# ==================== READ SENSOR DATA ====================

@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def get_sensor_data(request, device_id):
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header:
        return Response({"error": "Authorization header required"}, status=401)
    auth_key = auth_header.split(" ")[-1]
    try:
        device = Device.objects.get(id=device_id, read_api_key=auth_key, is_active=True)
    except Device.DoesNotExist:
        return Response({"error": "Invalid device or API key"}, status=401)

    sensor_data = defaultdict(list)
    # Return in chronological order for clients
    for r in latest_chronological(SensorData.objects.filter(device=device), 1000):
        # Convert to IST timezone
        ist_timestamp = format_ist_timestamp(r.created_at)
        sensor_data[r.sensor_config.sensor_label].append({
            "id": r.id, 
            "value": r.value, 
            "created_at": ist_timestamp  # Use IST timestamp
        })
    return Response(sensor_data)


# ==================== DEVICE MGMT API ====================

@api_view(["GET", "POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def device_list(request):
    if request.method == "GET":
        devices = Device.objects.filter(customer__user=request.user)
        serializer = DeviceSerializer(devices, many=True)
        return Response(serializer.data)
    serializer = DeviceSerializer(data=request.data)
    if serializer.is_valid():
        customer = get_object_or_404(Customer, user=request.user)
        serializer.save(customer=customer)
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

@api_view(["GET", "PUT", "DELETE"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def device_detail_api(request, device_id):
    device = get_object_or_404(Device, id=device_id, customer__user=request.user)
    if request.method == "GET":
        serializer = DeviceSerializer(device)
        readings = latest_chronological(SensorData.objects.filter(device=device), 200)
        sensor_data = defaultdict(list)
        for r in readings:
            # Convert to IST timezone
            ist_timestamp = format_ist_timestamp(r.created_at)
            sensor_data[r.sensor_config.sensor_label].append({
                "timestamp": ist_timestamp,  # Use IST timestamp
                "value": r.value,
            })
        return Response({"device": serializer.data, "sensor_data": sensor_data})
    elif request.method == "PUT":
        serializer = DeviceSerializer(device, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)
    else:
        device.delete()
        return Response(status=204)


# ==================== API KEY MGMT ====================

@api_view(["POST"])
@authentication_classes([TokenAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def create_apikey(request):
    token, created = Token.objects.get_or_create(user=request.user)
    return Response({
        "token": token.key,
        "created": created,
        "message": "New token created" if created else "Existing token retrieved",
    }, status=201 if created else 200)


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_apikey(request):
    try:
        token = Token.objects.get(user=request.user)
        return Response({"token": token.key, "user": request.user.username})
    except Token.DoesNotExist:
        return Response({"error": "No token found"}, status=404)

@api_view(["DELETE"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def delete_apikey(request):
    try:
        Token.objects.get(user=request.user).delete()
        return Response({"message": "API token deleted"}, status=204)
    except Token.DoesNotExist:
        return Response({"error": "No token found"}, status=404)


# ==================== CUSTOMER DEVICES ====================

@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def customer_devices(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id, user=request.user)
    devices = Device.objects.filter(customer=customer)
    serializer = DeviceSerializer(devices, many=True)
    return Response(serializer.data)


# ==================== GENERIC IoT DATA API ====================

@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def iot_data_list(request):
    data_qs = IoTData.objects.filter(device__customer__user=request.user)
    data = latest_chronological(data_qs, 100)
    serializer = IoTDataSerializer(data, many=True)
    return Response(serializer.data)


from django.http import JsonResponse
from .models import Device, SensorData

def customer_devices_data(request, dashboard_uuid):
    """
    Returns summarized sensor/device data for a given customer dashboard.
    This ensures backward compatibility with URLs referencing /data/.
    """
    try:
        customer = get_object_or_404(Customer, dashboard_url=dashboard_uuid)
        devices = Device.objects.filter(customer=customer, is_active=True)
        data = []
        for device in devices:
            latest_data = SensorData.objects.filter(device=device).order_by('-created_at').first()
            if latest_data:
                # Convert to IST timezone
                ist_timestamp = format_ist_timestamp(latest_data.created_at)
                data.append({
                    'device_name': device.name,
                    'latest_value': latest_data.value,
                    'timestamp': ist_timestamp,  # Use IST timestamp
                })
            else:
                data.append({
                    'device_name': device.name,
                    'latest_value': None,
                    'timestamp': None,
                })
        return JsonResponse({'devices': data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

