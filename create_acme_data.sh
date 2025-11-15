#!/usr/bin/env bash
set -e
docker compose --env-file .env -p acer__iot exec -T web python manage.py shell <<'PY'
from django.contrib.auth import get_user_model
from django.utils import timezone
from api.models import Customer, Device, SensorConfiguration, SensorType
from django.db import transaction
import uuid

User = get_user_model()

# Configuration (edit these values if you want different names/password)
USERNAME = "acer"
PASSWORD = "acer"
EMAIL = "admin@acer.local"
COMPANY_NAME = "acer"
DEVICE_NAME = "NodeMCU13E-1"
DEVICE_TYPE_NAME = "NodeMCU13E"  # optional: only set if DeviceType model exists
SENSOR_CONFIGS = [
    ("t1In", "Temperature", "°C"),
    ("t2In", "Temperature", "°C"),
    ("t1Out", "Temperature", "°C"),
    ("t2Out", "Temperature", "°C"),
    ("Deltap", "Pressure", "bar"),
]

def safe_print(title, obj):
    print(f"--- {title} ---")
    print(obj)
    print()

with transaction.atomic():
    # 1) Create or get user
    user, created = User.objects.get_or_create(username=USERNAME, defaults={"email": EMAIL})
    if created:
        user.set_password(PASSWORD)
        # make admin/staff if you prefer:
        user.is_staff = True
        user.is_superuser = False
        user.save()
        print(f"Created user '{USERNAME}' with password '{PASSWORD}'")
    else:
        print(f"User '{USERNAME}' exists (no password change). To reset password run manage.py changepassword {USERNAME}")
    safe_print("User", f"{user.username} (id={user.pk})")

    # 2) Create or get Customer linked to user
    customer, c_created = Customer.objects.get_or_create(user=user, defaults={"company_name": COMPANY_NAME})
    if not c_created and customer.company_name != COMPANY_NAME:
        customer.company_name = COMPANY_NAME
        customer.save()
    safe_print("Customer", f"{customer.company_name} (id={customer.pk}) linked to user {user.username}")

    # 3) Create or get Device
    device_defaults = {"is_active": True}
    device, d_created = Device.objects.get_or_create(name=DEVICE_NAME, customer=customer, defaults=device_defaults)
    if d_created:
        print(f"Created Device '{DEVICE_NAME}' for customer '{customer.company_name}'")
    else:
        print(f"Device '{DEVICE_NAME}' already exists for customer '{customer.company_name}'")
    # Print potential API keys if fields exist
    # Many Device models auto-generate write_api_key/read_api_key on save; show them if available
    wa = getattr(device, "write_api_key", None)
    ra = getattr(device, "read_api_key", None)
    safe_print("Device API keys", {"write_api_key": wa, "read_api_key": ra})

    # 4) (Optional) Create a DeviceType and attach to device if model supports it
    try:
        # try to import the model if it exists in api.models
        from api.models import DeviceType
        dtype, dt_created = DeviceType.objects.get_or_create(name=DEVICE_TYPE_NAME)
        if dt_created:
            print(f"Created DeviceType '{DEVICE_TYPE_NAME}'")
        device.device_type = dtype
        device.save()
        safe_print("DeviceType attached", getattr(device, "device_type", None))
    except Exception:
        # DeviceType not present in your models — ignore silently
        pass

    # 5) Create SensorType entries (Temperature, Pressure, etc.)
    sensor_type_map = {}
    for label, type_name, unit in SENSOR_CONFIGS:
        st, st_created = SensorType.objects.get_or_create(name=type_name, defaults={"unit": unit})
        if st_created:
            print(f"Created SensorType '{type_name}' (unit={unit})")
        sensor_type_map[type_name] = st

    # 6) Create SensorConfiguration records for this device
    created_configs = []
    for sensor_label, type_name, unit in SENSOR_CONFIGS:
        st = sensor_type_map[type_name]
        cfg, cfg_created = SensorConfiguration.objects.get_or_create(
            device=device,
            sensor_label=sensor_label,
            defaults={
                "sensor_type": st,
                # add sensible defaults for other fields if exist; adjust keys as needed
            }
        )
        if cfg_created:
            created_configs.append(sensor_label)
            print(f"Created SensorConfiguration: {sensor_label} (type={type_name})")
        else:
            print(f"SensorConfiguration exists: {sensor_label} (type={getattr(cfg.sensor_type, 'name', None)})")

    # 7) Summary
    print("\n===== SUMMARY =====")
    print("User:", user.username)
    print("Customer:", customer.company_name, "id=", customer.pk)
    print("Device:", device.name, "id=", device.pk)
    print("API keys: write=", wa, " read=", ra)
    print("Sensor configurations created/checked:", ", ".join([cfg if isinstance(cfg,str) else str(cfg) for cfg in created_configs]) or "none newly created")
    print("===================\n")

PY
