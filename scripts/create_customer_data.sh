#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/create_customer_data.sh <customer_name> [device_name] [admin_password] [http_port]
# Example:
#   ./scripts/create_customer_data.sh acme NodeMCU13E-1 SmartFactory@123 8011

if [ $# -lt 1 ]; then
  echo "Usage: $0 <customer_name> [device_name] [admin_password] [http_port]"
  exit 1
fi

# --- inputs / defaults ---
RAW_CUSTOMER="$1"
DEVICE_NAME="${2:-NodeMCU13E-1}"
ADMIN_PASSWORD="${3:-SmartFactory@123}"
HTTP_PORT="${4:-8000}"

# sanitize customer -> lowercase alnum + underscore
CUSTOMER="$(echo "$RAW_CUSTOMER" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9_]+/_/g')"
PROJECT="${CUSTOMER}__iot"   # docker compose project name convention you use

echo "Creating / verifying customer data for: '$CUSTOMER'"
echo "Project: $PROJECT"
echo "Device: $DEVICE_NAME"
echo "HTTP Port (for info): $HTTP_PORT"

# ensure running from repo root where .env exists (or provide full path)
if [ ! -f .env ]; then
  echo "Warning: .env not found in current directory ($(pwd)). Make sure you're in the repo root or pass --env-file with docker compose calls."
fi

# run Django shell inside the web container for the given project
docker compose --env-file .env -p "${PROJECT}" exec -T web python manage.py shell <<PY
from django.contrib.auth import get_user_model
from django.db import transaction
from api.models import Customer, Device, SensorConfiguration, SensorType
import sys

USERNAME = "$CUSTOMER"
PASSWORD = "$ADMIN_PASSWORD"
EMAIL = f"admin@{USERNAME}.local"
COMPANY_NAME = "$CUSTOMER"
DEVICE_NAME = "$DEVICE_NAME"

SENSOR_CONFIGS = [
    ("t1In", "Temperature", "°C"),
    ("t2In", "Temperature", "°C"),
    ("t1Out", "Temperature", "°C"),
    ("t2Out", "Temperature", "°C"),
    ("Deltap", "Pressure", "bar"),
]

User = get_user_model()

def safe_print(title, obj):
    print(f'--- {title} ---')
    print(obj)
    print()

with transaction.atomic():
    # create or get user
    user, created = User.objects.get_or_create(username=USERNAME, defaults={"email": EMAIL})
    if created:
        user.set_password(PASSWORD)
        user.is_staff = True
        user.is_superuser = False
        user.save()
        print(f"Created user '{USERNAME}' with password '{PASSWORD}'")
    else:
        # Do not change password silently if user exists. Print message to change if required.
        print(f"User '{USERNAME}' already exists. To reset password run: manage.py changepassword {USERNAME}")
    safe_print("User", f"{user.username} (id={user.pk})")

    # create or get Customer
    customer, c_created = Customer.objects.get_or_create(user=user, defaults={"company_name": COMPANY_NAME})
    if not c_created and customer.company_name != COMPANY_NAME:
        customer.company_name = COMPANY_NAME
        customer.save()
    safe_print("Customer", f"{customer.company_name} (id={customer.pk}) linked to user {user.username}")

    # create or get Device
    device_defaults = {"is_active": True}
    device, d_created = Device.objects.get_or_create(name=DEVICE_NAME, customer=customer, defaults=device_defaults)
    if d_created:
        print(f"Created Device '{DEVICE_NAME}' for customer '{customer.company_name}'")
    else:
        print(f"Device '{DEVICE_NAME}' already exists for customer '{customer.company_name}'")

    # print device API keys if present
    wa = getattr(device, "write_api_key", None)
    ra = getattr(device, "read_api_key", None)
    safe_print("Device API keys", {"write_api_key": wa, "read_api_key": ra})

    # create sensor types + configurations
    sensor_type_map = {}
    for label, type_name, unit in SENSOR_CONFIGS:
        st, st_created = SensorType.objects.get_or_create(name=type_name, defaults={"unit": unit})
        if st_created:
            print(f"Created SensorType '{type_name}' (unit={unit})")
        sensor_type_map[type_name] = st

    created_cfgs = []
    for sensor_label, type_name, unit in SENSOR_CONFIGS:
        st = sensor_type_map[type_name]
        defaults = {"sensor_type": st}
        cfg, cfg_created = SensorConfiguration.objects.get_or_create(
            device=device,
            sensor_label=sensor_label,
            defaults=defaults
        )
        if cfg_created:
            created_cfgs.append(sensor_label)
            print(f"Created SensorConfiguration: {sensor_label} (type={type_name})")
        else:
            print(f"SensorConfiguration exists: {sensor_label} (type={getattr(cfg.sensor_type,'name',None)})")

    print("\\n===== SUMMARY =====")
    print("User:", user.username)
    print("Customer:", customer.company_name, "id=", customer.pk)
    print("Device:", device.name, "id=", device.pk)
    print("API keys: write=", wa, " read=", ra)
    print("Sensor configurations created/checked:", ", ".join(created_cfgs) if created_cfgs else "none newly created")
    print("===================")
PY

echo "Done. If you need to reset the admin password for user '$CUSTOMER' run:"
echo "  docker compose --env-file .env -p ${PROJECT} exec -T web python manage.py changepassword ${CUSTOMER}"

