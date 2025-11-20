# api/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
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
from collections import defaultdict

# ------------------------
# Helper utilities
# ------------------------
def latest_chronological(queryset, n):
    """
    Return the latest `n` records from `queryset` ordered oldest -> newest.

    This selects the newest N records (by ordering -created_at) then reverses
    the slice so the returned list goes from oldest to newest, which is
    ideal for plotting on a time-series x-axis.
    """
    #return list(queryset.order_by("-created_at")[:n])[::-1]
    return list(queryset.order_by("-created_at")[:n])


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
#@api_view(["GET"])
#@authentication_classes([])
#@permission_classes([])
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
        sensor_data[r.sensor_config.sensor_label].append({
            "timestamp": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
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

    return Response([
        {"id": d.id, "device": d.device.id, "sensor_label": d.sensor_config.sensor_label,
         "value": d.value, "created_at": d.created_at.isoformat()}
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
            sensor_data[r.sensor_config.sensor_label].append({
                "timestamp": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "value": r.value,
            })
        # readings already chronological; keep sort to be defensive
        #for label in sensor_data:
        #    sensor_data[label].sort(key=lambda x: x["timestamp"])
        #dashboard_data.append({
        #    "device_id": device.id,
        #    "device_name": device.name,
        #    "sensor_data": sensor_data,
        #})

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
        sensor_data[r.sensor_config.sensor_label].append({
            "id": r.id, "value": r.value, "created_at": r.created_at.isoformat()
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
            sensor_data[r.sensor_config.sensor_label].append({
                "timestamp": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "value": r.value,
            })
        for label in sensor_data:
            sensor_data[label].sort(key=lambda x: x["timestamp"])
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
        devices = Device.objects.filter(customer__dashboard_uuid=dashboard_uuid)
        data = []
        for device in devices:
            latest_data = SensorData.objects.filter(device=device).order_by('-created_at').first()
            data.append({
                'device_name': device.name,
                'latest_value': latest_data.value if latest_data else None,
                'timestamp': latest_data.created_at if latest_data else None,
            })
        return JsonResponse({'devices': data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

