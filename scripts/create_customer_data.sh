#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/create_customer_data.sh <customer_name> [device_name] [admin_password] [http_port]
# Example:
#   ./scripts/create_customer_data.sh tesla NodeMCU13E-1 SmartFactory@123 8001

if [ $# -lt 1 ]; then
  echo "Usage: $0 <customer_name> [device_name] [admin_password] [http_port]"
  exit 1
fi

RAW_CUSTOMER="$1"
DEVICE_NAME="${2:-NodeMCU13E-1}"
ADMIN_PASSWORD="${3:-SmartFactory@123}"
HTTP_PORT="${4:-8000}"

CUSTOMER="$(echo "$RAW_CUSTOMER" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9_]+/_/g')"
PROJECT="${CUSTOMER}__iot"

# Try to locate a sensible env-file to use:
ENV_FILE=""
# priority: .env.<customer>  -> .env (repo root) -> <customer>_iot/.env
if [ -f ".env.${CUSTOMER}" ]; then
  ENV_FILE=".env.${CUSTOMER}"
elif [ -f ".env" ]; then
  ENV_FILE=".env"
elif [ -f "${CUSTOMER}_iot/.env" ]; then
  ENV_FILE="${CUSTOMER}_iot/.env"
fi

if [ -z "$ENV_FILE" ]; then
  echo "ERROR: Could not find a .env file. I looked for:"
  echo "  - .env.${CUSTOMER}"
  echo "  - .env"
  echo "  - ${CUSTOMER}_iot/.env"
  echo ""
  echo "Please either:"
  echo "  * run this script from the repo root where .env exists, or"
  echo "  * create .env.${CUSTOMER} (or ${CUSTOMER}_iot/.env), or"
  echo "  * pass an env file by editing the script."
  exit 2
fi

echo "Using env file: $ENV_FILE"
echo "Project: $PROJECT"
echo "Device: $DEVICE_NAME"

# Ensure the compose stack is running (start it if not)
echo "Checking docker-compose services for project: $PROJECT ..."
RUNNING_WEB="$(docker compose --env-file "$ENV_FILE" -p "${PROJECT}" ps --services --filter status=running | grep -x web || true)"
if [ -z "$RUNNING_WEB" ]; then
  echo "Web container not running for project ${PROJECT} — starting (this may take a moment)..."
  docker compose --env-file "$ENV_FILE" -p "${PROJECT}" up -d --build
  echo "Started compose stack for ${PROJECT}."
else
  echo "Web container is already running for project ${PROJECT}."
fi

# Run the Django creation block inside the tenant web container
docker compose --env-file "$ENV_FILE" -p "${PROJECT}" exec -T web python manage.py shell <<PY
from django.contrib.auth import get_user_model
from django.db import transaction
from api.models import Customer, Device, SensorConfiguration, SensorType

USERNAME = "${CUSTOMER}"
PASSWORD = "${ADMIN_PASSWORD}"
EMAIL = f"admin@{USERNAME}.local"
COMPANY_NAME = "${CUSTOMER}"
DEVICE_NAME = "${DEVICE_NAME}"

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
    user, created = User.objects.get_or_create(username=USERNAME, defaults={"email": EMAIL})
    if created:
        user.set_password(PASSWORD)
        user.is_staff = True
        user.save()
        print(f"Created user '{USERNAME}' with password '{PASSWORD}'")
    else:
        print(f"User '{USERNAME}' exists. Use manage.py changepassword {USERNAME} to update password if needed.")
    safe_print("User", f"{user.username} (id={user.pk})")

    customer, c_created = Customer.objects.get_or_create(user=user, defaults={"company_name": COMPANY_NAME})
    if not c_created and customer.company_name != COMPANY_NAME:
        customer.company_name = COMPANY_NAME
        customer.save()
    safe_print("Customer", f"{customer.company_name} (id={customer.pk}) linked to user {user.username}")

    device_defaults = {"is_active": True}
    device, d_created = Device.objects.get_or_create(name=DEVICE_NAME, customer=customer, defaults=device_defaults)
    if d_created:
        print(f"Created Device '{DEVICE_NAME}' for customer '{customer.company_name}'")
    else:
        print(f"Device '{DEVICE_NAME}' already exists for customer '{customer.company_name}'")

    wa = getattr(device, "write_api_key", None)
    ra = getattr(device, "read_api_key", None)
    safe_print("Device API keys", {"write_api_key": wa, "read_api_key": ra})

    sensor_type_map = {}
    for label, type_name, unit in SENSOR_CONFIGS:
        st, st_created = SensorType.objects.get_or_create(name=type_name, defaults={"unit": unit})
        sensor_type_map[type_name] = st
        if st_created:
            print(f"Created SensorType '{type_name}' (unit={unit})")

    created_cfgs = []
    for sensor_label, type_name, unit in SENSOR_CONFIGS:
        st = sensor_type_map[type_name]
        cfg, cfg_created = SensorConfiguration.objects.get_or_create(
            device=device,
            sensor_label=sensor_label,
            defaults={"sensor_type": st}
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

echo "Done for customer: $CUSTOMER (project: $PROJECT)."
echo "If you want to inspect logs run:"
echo "  docker compose --env-file \"$ENV_FILE\" -p \"$PROJECT\" logs --tail 200 web"

