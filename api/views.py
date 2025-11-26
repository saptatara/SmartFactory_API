# api/views.py
from django.shortcuts import render, redirect, get_object_or_404
import csv
from datetime import datetime, timedelta
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.db import models
from rest_framework.decorators import (
    api_view, permission_classes, authentication_classes
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import TokenAuthentication, BasicAuthentication
from rest_framework.response import Response
from rest_framework import status
from .models import (
    Customer, Device, DeviceType, SensorData, SensorConfiguration, 
    SensorType, IoTData, FoulingData
)
from .serializers import DeviceSerializer, SensorDataSerializer, IoTDataSerializer
from .forms import SensorDataForm
from rest_framework.authtoken.models import Token
from django.db.models import Q
from datetime import datetime, timedelta
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
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
import math

def _latest_sensor_value(device, label):
    """
    Return latest SensorData.value for the given device + sensor_label,
    or None if not found.
    """
    try:
        sc = SensorConfiguration.objects.get(device=device, sensor_label=label)
    except SensorConfiguration.DoesNotExist:
        return None
    sd = SensorData.objects.filter(device=device, sensor_config=sc).order_by("-created_at").first()
    return sd.value if sd else None


from collections import defaultdict
import math
from django.conf import settings
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework.response import Response
from rest_framework import status

@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def device_fouling_snapshot(request, device_id):
    """
    Compute current fouling factor for a device using latest t1/t2 readings.
    Assumes:
      - t1_in, t1_out, t2_in, t2_out exist as sensor labels
      - Flow rates, area, U_clean are configured as constants
    """
    device = get_object_or_404(Device, id=device_id, customer__user=request.user)

    # helper to get latest value for a given sensor label
    def latest_value(label):
        try:
            sc = SensorConfiguration.objects.get(device=device, sensor_label=label)
        except SensorConfiguration.DoesNotExist:
            return None
        sd = SensorData.objects.filter(device=device, sensor_config=sc).order_by("-created_at").first()
        return sd.value if sd else None

    t1_in  = latest_value("t1_in")
    t1_out = latest_value("t1_out")
    t2_in  = latest_value("t2_in")
    t2_out = latest_value("t2_out")

    if None in (t1_in, t1_out, t2_in, t2_out):
        return Response(
            {"error": "Missing temperature readings (t1_in, t1_out, t2_in, t2_out)"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Use configured or default design values (mass flow in kg/s etc.)
    hot_flow_rate = getattr(settings, "DEFAULT_HOT_FLOW_KG_S", 1.0)
    cold_flow_rate = getattr(settings, "DEFAULT_COLD_FLOW_KG_S", 1.0)
    heat_transfer_area = getattr(settings, "DEFAULT_HEAT_TRANSFER_AREA", 15.5)
    U_clean = getattr(settings, "DEFAULT_U_CLEAN", 800.0)

    result = calculate_fouling_factor(
        hot_flow_rate=hot_flow_rate,
        cold_flow_rate=cold_flow_rate,
        hot_inlet_temp=t1_in,
        hot_outlet_temp=t1_out,
        cold_inlet_temp=t2_in,
        cold_outlet_temp=t2_out,
        heat_transfer_area=heat_transfer_area,
        U_clean=U_clean,
    )

    severity_info = assess_fouling_severity(result["fouling_factor"])
    result.update(severity_info)
    result["device_id"] = device.id
    result["device_name"] = device.name
    result["calculated_at"] = format_ist_timestamp(timezone.now())

    return Response(result)

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
    for PARALLEL-FLOW heat exchanger.

    Parameters:
    - hot_flow_rate: Hot fluid flow rate (kg/s)
    - cold_flow_rate: Cold fluid flow rate (kg/s)
    - hot_inlet_temp: Hot fluid inlet temperature (°C)  -> e.g. t1_in
    - hot_outlet_temp: Hot fluid outlet temperature (°C) -> e.g. t1_out
    - cold_inlet_temp: Cold fluid inlet temperature (°C) -> e.g. t2_in
    - cold_outlet_temp: Cold fluid outlet temperature (°C)-> e.g. t2_out
    - heat_transfer_area: Heat transfer area (m²)

    Returns dict:
      {
        'U_clean': U_clean,
        'heat_duty': heat_duty,
        'lmtd': lmtd,
        'heat_duty_hot': heat_duty_hot,
        'heat_duty_cold': heat_duty_cold,
      }
    """
    # Specific heat capacity of water (J/kg·K)
    cp = 4186.0

    # 1) Heat duty from both sides
    heat_duty_hot = hot_flow_rate * cp * (hot_inlet_temp - hot_outlet_temp)
    heat_duty_cold = cold_flow_rate * cp * (cold_outlet_temp - cold_inlet_temp)

    # Use average of both sides (you could also choose min(), but average is fine)
    heat_duty = (heat_duty_hot + heat_duty_cold) / 2.0

    # 2) LMTD for PARALLEL FLOW:
    #    ΔT1 = Th,in - Tc,in
    #    ΔT2 = Th,out - Tc,out
    delta_t1 = hot_inlet_temp - cold_inlet_temp
    delta_t2 = hot_outlet_temp - cold_outlet_temp

    # Basic safety: ensure positive ΔT for LMTD calculation.
    # If they are non-positive (sensor issues / transients), we log and coerce.
    if delta_t1 <= 0 or delta_t2 <= 0:
        logger.warning(
            "Non-positive ΔT detected in LMTD calculation. "
            "Using absolute values. Th_in=%s, Th_out=%s, Tc_in=%s, Tc_out=%s, ΔT1=%s, ΔT2=%s",
            hot_inlet_temp, hot_outlet_temp, cold_inlet_temp, cold_outlet_temp,
            delta_t1, delta_t2,
        )
        delta_t1 = abs(delta_t1)
        delta_t2 = abs(delta_t2)
        if delta_t1 == 0:
            delta_t1 = 0.1
        if delta_t2 == 0:
            delta_t2 = 0.1

    # 3) Compute LMTD
    if abs(delta_t1 - delta_t2) < 1e-9:
        lmtd = delta_t1
    else:
        # Guard against weird log arguments
        ratio = delta_t1 / delta_t2
        if ratio <= 0:
            logger.warning(
                "Invalid LMTD log argument ratio=%s (ΔT1=%s, ΔT2=%s). "
                "Falling back to arithmetic mean.",
                ratio, delta_t1, delta_t2,
            )
            lmtd = 0.5 * (delta_t1 + delta_t2)
        else:
            lmtd = (delta_t1 - delta_t2) / math.log(ratio)

    # 4) Overall heat transfer coefficient
    if heat_transfer_area <= 0 or lmtd <= 0:
        logger.warning(
            "Non-positive area or LMTD in U_clean calculation. "
            "A=%s, LMTD=%s, heat_duty=%s",
            heat_transfer_area, lmtd, heat_duty,
        )
        U_clean = 0.0
    else:
        U_clean = heat_duty / (heat_transfer_area * lmtd)

    return {
        'U_clean': U_clean,
        'heat_duty': heat_duty,
        'lmtd': lmtd,
        'heat_duty_hot': heat_duty_hot,
        'heat_duty_cold': heat_duty_cold,
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
from collections import defaultdict

@api_view(["GET"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def device_fouling_history(request, device_id):
    """
    Return a time series of fouling factor values computed from historical SensorData.
    Uses t1_in, t1_out, t2_in, t2_out for each timestamp where all four are present.
    Query param: ?points=50 (max number of points, default 50)
    """
    device = get_object_or_404(Device, id=device_id, customer__user=request.user)
    try:
        max_points = int(request.GET.get("points", 50))
    except ValueError:
        max_points = 50

    # Fetch recent data for the four key sensors
    label_list = ["t1_in", "t1_out", "t2_in", "t2_out"]
    qs = (
        SensorData.objects
        .filter(device=device, sensor_config__sensor_label__in=label_list)
        .select_related("sensor_config")
        .order_by("-created_at")[: max_points * 4]
    )

    # Group by timestamp (to the second) -> {timestamp: {label: value}}
    grouped = defaultdict(dict)
    for sd in qs:
        ts = sd.created_at.replace(microsecond=0)
        grouped[ts][sd.sensor_config.sensor_label] = sd.value

    hot_flow_rate = getattr(settings, "DEFAULT_HOT_FLOW_KG_S", 1.0)
    cold_flow_rate = getattr(settings, "DEFAULT_COLD_FLOW_KG_S", 1.0)
    heat_transfer_area = getattr(settings, "DEFAULT_HEAT_TRANSFER_AREA", 10.0)
    U_clean_design = getattr(settings, "DEFAULT_U_CLEAN", 800.0)

    data_points = []

    # Sort timestamps oldest -> newest for plotting
    for ts in sorted(grouped.keys()):
        sample = grouped[ts]
        if not all(lbl in sample for lbl in label_list):
            continue

        t1_in  = sample["t1_in"]
        t1_out = sample["t1_out"]
        t2_in  = sample["t2_in"]
        t2_out = sample["t2_out"]

        result = calculate_fouling_factor(
            hot_flow_rate=hot_flow_rate,
            cold_flow_rate=cold_flow_rate,
            hot_inlet_temp=t1_in,
            hot_outlet_temp=t1_out,
            cold_inlet_temp=t2_in,
            cold_outlet_temp=t2_out,
            heat_transfer_area=heat_transfer_area,
            U_clean=U_clean_design,
        )
        severity_info = assess_fouling_severity(result["fouling_factor"])

        data_points.append({
            "timestamp": format_ist_timestamp(ts),
            "fouling_factor": result["fouling_factor"],
            "U_actual": result["U_actual"],
            "U_clean": result["U_clean"],
            "performance_ratio": result["performance_ratio"],
            "lmtd": result["lmtd"],
            "severity": severity_info["severity"],
            "recommendation": severity_info["recommendation"],
            "color_code": severity_info["color_code"],
            "risk_level": severity_info["risk_level"],
        })

        if len(data_points) >= max_points:
            break

    return Response({
        "device_id": device.id,
        "device_name": device.name,
        "data": data_points,
    })


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
    """Redirect to the UUID-based dashboard"""
    if not request.user.is_authenticated:
        return redirect('customer_login')
    
    try:
        customer = Customer.objects.get(user=request.user)
        return redirect("customer_dashboard_ui", dashboard_uuid=customer.dashboard_url)
    except Customer.DoesNotExist:
        messages.error(request, "Customer profile not found.")
        return redirect('customer_login')
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


from collections import defaultdict
import json

@login_required
def device_detail_ui(request, device_id):
    device = get_object_or_404(Device, id=device_id)
    
    # Get sensor data with proper structure
    sensor_readings = SensorData.objects.filter(device=device).order_by("-created_at")[:100]
    
    sensor_data = defaultdict(list)
    timestamps_seen = set()
    
    for r in sensor_readings:
        timestamp_key = r.created_at.replace(second=0, microsecond=0)
        sensor_key = (timestamp_key, r.sensor_config.sensor_label)
        if sensor_key not in timestamps_seen:
            ist_timestamp = format_ist_timestamp(r.created_at)
            sensor_data[r.sensor_config.sensor_label].append({
                "timestamp": ist_timestamp,
                "value": r.value,
            })
            timestamps_seen.add(sensor_key)
    
    # Reverse to show chronological order
    for sensor_label in sensor_data:
        sensor_data[sensor_label].reverse()
    
    return render(request, "api/device_detail.html", {
        "device": device,
        "sensor_readings": sensor_readings,
        "sensor_data": sensor_data,                 
        "sensor_data_json": json.dumps(sensor_data),
    })

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
#====================================Sensor Report Generation============================
@api_view(["GET"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def device_fouling_report_csv(request, device_id):
    """Generate comprehensive fouling data CSV report with enhanced formatting"""
    try:
        device = Device.objects.get(id=device_id, customer__user=request.user)
    except Device.DoesNotExist:
        return HttpResponse("Device not found", status=404)

    # Date range filtering
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')
    
    fouling_data = FoulingData.objects.filter(device=device)
    
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            fouling_data = fouling_data.filter(calculated_at__date__gte=start_date)
        except ValueError:
            pass
            
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            fouling_data = fouling_data.filter(calculated_at__date__lte=end_date)
        except ValueError:
            pass

    fouling_data = fouling_data.order_by('-calculated_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="fouling_report_{device.name}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

    writer = csv.writer(response)
    
    # Enhanced header with better organization
    writer.writerow([
        'TIMESTAMP', 'DEVICE_NAME', 'LOCATION', 
        'FOULING_FACTOR_M2K_W', 'U_ACTUAL_W_M2K', 'U_CLEAN_W_M2K', 
        'PERFORMANCE_RATIO_PERCENT', 'HEAT_DUTY_W', 'LMTD_K', 
        'SEVERITY_LEVEL', 'RISK_LEVEL', 'MAINTENANCE_RECOMMENDATION'
    ])

    for data in fouling_data:
        writer.writerow([
            data.calculated_at.strftime("%Y-%m-%d %H:%M:%S"),
            device.name,
            device.location or 'N/A',
            f"{data.fouling_factor:.8f}",  # Higher precision for fouling factor
            f"{data.u_actual:.2f}",
            f"{data.u_clean:.2f}",
            f"{(data.performance_ratio * 100):.2f}",
            f"{data.heat_duty:.2f}",
            f"{data.lmtd:.2f}",
            data.severity.upper(),
            data.risk_level.upper(),
            data.recommendation
        ])

    return response

@api_view(["GET"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def device_sensor_report_csv(request, device_id):
    """Generate comprehensive sensor data CSV report with enhanced formatting"""
    try:
        device = Device.objects.get(id=device_id, customer__user=request.user)
    except Device.DoesNotExist:
        return HttpResponse("Device not found", status=404)

    # Date range filtering
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')
    
    sensor_data = SensorData.objects.filter(device=device)
    
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            sensor_data = sensor_data.filter(created_at__date__gte=start_date)
        except ValueError:
            pass
            
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            sensor_data = sensor_data.filter(created_at__date__lte=end_date)
        except ValueError:
            pass

    sensor_data = sensor_data.select_related('sensor_config', 'sensor_config__sensor_type').order_by('-created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="sensor_report_{device.name}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

    writer = csv.writer(response)
    
    # Write header with enhanced information
    writer.writerow([
        'TIMESTAMP', 'DEVICE_NAME', 'SENSOR_LABEL', 'SENSOR_TYPE', 
        'VALUE', 'UNIT', 'EXPECTED_MIN', 'EXPECTED_MAX', 'STATUS', 'LOCATION'
    ])

    for data in sensor_data:
        # Determine status based on expected ranges
        status = 'NORMAL'
        config = data.sensor_config
        if config.expected_min is not None and data.value < config.expected_min:
            status = 'BELOW_MINIMUM'
        elif config.expected_max is not None and data.value > config.expected_max:
            status = 'ABOVE_MAXIMUM'

        writer.writerow([
            data.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            device.name,
            config.sensor_label,
            config.sensor_type.name,
            f"{data.value:.6f}",  # More precise formatting
            config.sensor_type.unit,
            config.expected_min or 'N/A',
            config.expected_max or 'N/A',
            status,
            device.location or 'N/A'
        ])

    return response
def get_dashboard_stats(customer):
    """Get enhanced statistics for dashboard display"""
    devices = Device.objects.filter(customer=customer, is_active=True)
    total_sensors = SensorConfiguration.objects.filter(device__in=devices).count()
    
    # Calculate critical alerts
    critical_alerts = IoTData.objects.filter(
        device__in=devices, 
        is_alert=True
    ).count()
    
    # Calculate average performance from fouling data
    fouling_data = FoulingData.objects.filter(device__in=devices)
    if fouling_data.exists():
        performance_avg = fouling_data.aggregate(models.Avg('performance_ratio'))['performance_ratio__avg'] * 100
    else:
        performance_avg = 0
    
    return {
        'total_devices': devices.count(),
        'total_sensors': total_sensors,
        'critical_alerts': critical_alerts,
        'performance_avg': round(performance_avg, 1)
    }
@login_required
def debug_device_data(request, device_id):
    """Debug view to check what data is available for frontend"""
    device = get_object_or_404(Device, id=device_id)
    
    # Get sensor data exactly like your dashboard does
    sensor_readings = latest_chronological(SensorData.objects.filter(device=device), 50)
    
    print(f"=== DEBUG: Device {device.name} ===")
    print(f"Total sensor readings: {len(sensor_readings)}")
    
    sensor_data = defaultdict(list)
    for r in sensor_readings:
        ist_timestamp = format_ist_timestamp(r.created_at)
        sensor_data[r.sensor_config.sensor_label].append({
            "timestamp": ist_timestamp,
            "value": r.value,
        })
        print(f"  - {r.sensor_config.sensor_label}: {r.value} at {ist_timestamp}")
    
    # Check what's being passed to template
    context = {
        "device": device,
        "sensor_readings": sensor_readings,
        "sensor_data_json": json.dumps(sensor_data),
    }
    
    print(f"Sensor data keys: {list(sensor_data.keys())}")
    print(f"Sensor data JSON length: {len(json.dumps(sensor_data))}")
    
    return render(request, "api/debug_device_data.html", context)
@login_required
def test_charts(request, device_id):
    """Test view to verify chart rendering with sample data"""
    device = get_object_or_404(Device, id=device_id)
    
    # Create sample data to test charts
    import random
    from datetime import datetime, timedelta
    
    # Generate sample data for testing
    sensor_data = {
        "t1_in": [],
        "t1_out": [], 
        "t2_in": [],
        "t2_out": []
    }
    
    base_time = timezone.now()
    for i in range(10):
        timestamp = base_time - timedelta(minutes=i*2)
        ist_timestamp = format_ist_timestamp(timestamp)
        
        sensor_data["t1_in"].append({
            "timestamp": ist_timestamp,
            "value": 25 + random.uniform(0, 5) + i*0.5
        })
        sensor_data["t1_out"].append({
            "timestamp": ist_timestamp, 
            "value": 20 + random.uniform(0, 5) + i*0.3
        })
        sensor_data["t2_in"].append({
            "timestamp": ist_timestamp,
            "value": 15 + random.uniform(0, 3) + i*0.2
        })
        sensor_data["t2_out"].append({
            "timestamp": ist_timestamp,
            "value": 18 + random.uniform(0, 4) + i*0.4
        })
    
    context = {
        "device": device,
        "sensor_data_json": json.dumps(sensor_data),
        "test_data": True
    }
    
    return render(request, "api/test_charts.html", context)
