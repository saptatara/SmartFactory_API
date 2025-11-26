#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/create_customer_data.sh <customer_name> [device_name] [admin_password] [http_port]
# Example:
#   ./scripts/create_customer_data.sh platex NodeMCU13E-1 SmartFactory@123 8001

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

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
sleep 10

# Step 1: Create migrations and apply them
echo "🛠️ Creating and running database migrations..."
docker compose --env-file "$ENV_FILE" -p "${PROJECT}" exec -T web python manage.py makemigrations api --noinput
docker compose --env-file "$ENV_FILE" -p "${PROJECT}" exec -T web python manage.py migrate --noinput

# Step 2: Check if migrations were successful
echo "🔍 Checking database state..."
docker compose --env-file "$ENV_FILE" -p "${PROJECT}" exec -T web python manage.py check --database default

# Run the Django creation block inside the tenant web container WITHOUT transaction.atomic()
docker compose --env-file "$ENV_FILE" -p "${PROJECT}" exec -T web python manage.py shell <<PY
from django.contrib.auth import get_user_model
from api.models import Customer, Device, SensorConfiguration, SensorType, FoulingData
import uuid

USERNAME = "${CUSTOMER}"
PASSWORD = "${ADMIN_PASSWORD}"
EMAIL = f"admin@{USERNAME}.local"
COMPANY_NAME = "${RAW_CUSTOMER}"  # Use the original name with proper casing
DEVICE_NAME = "${DEVICE_NAME}"

SENSOR_CONFIGS = [
    ("t1_in", "Temperature", "°C"),
    ("t1_out", "Temperature", "°C"), 
    ("t2_in", "Temperature", "°C"),
    ("t2_out", "Temperature", "°C"),
    ("dpt1", "Pressure", "bar"),
]

User = get_user_model()

def safe_print(title, obj):
    print(f'--- {title} ---')
    print(obj)
    print()

# Remove sample device first (outside of any transaction)
try:
    sample_device = Device.objects.filter(name='Heat Exchanger Unit #1').first()
    if sample_device:
        print("Found sample device 'Heat Exchanger Unit #1' - removing it...")
        sample_device.delete()
        print("Sample device removed")
except Exception as e:
    print(f"⚠️  Could not remove sample device: {e}")

# Create user
try:
    user, created = User.objects.get_or_create(username=USERNAME, defaults={"email": EMAIL})
    if created:
        user.set_password(PASSWORD)
        user.is_staff = True
        user.is_superuser = True
        user.save()
        print(f"✅ Created user '{USERNAME}' with password '{PASSWORD}'")
    else:
        print(f"ℹ️  User '{USERNAME}' exists. Updating password...")
        user.set_password(PASSWORD)
        user.is_staff = True
        user.is_superuser = True
        user.save()
    safe_print("User", f"{user.username} (id={user.pk})")
except Exception as e:
    print(f"❌ Failed to create user: {e}")
    exit(1)

# Create customer
try:
    customer, c_created = Customer.objects.get_or_create(
        user=user, 
        defaults={
            "company_name": COMPANY_NAME,
            "contact_email": EMAIL,
            "dashboard_url": uuid.uuid4()
        }
    )
    if not c_created and customer.company_name != COMPANY_NAME:
        customer.company_name = COMPANY_NAME
        customer.save()
    safe_print("Customer", f"{customer.company_name} (id={customer.pk}) linked to user {user.username}")
except Exception as e:
    print(f"❌ Failed to create customer: {e}")
    exit(1)

# Delete any existing device with the same name
try:
    existing_devices = Device.objects.filter(name=DEVICE_NAME, customer=customer)
    if existing_devices.exists():
        print(f"Removing existing device '{DEVICE_NAME}'...")
        existing_devices.delete()
except Exception as e:
    print(f"⚠️  Could not remove existing devices: {e}")

# Create new device
try:
    device = Device.objects.create(
        name=DEVICE_NAME, 
        customer=customer, 
        is_active=True,
        location="Main Production Line"
    )
    print(f"✅ Created Device '{DEVICE_NAME}' for customer '{customer.company_name}'")
except Exception as e:
    print(f"❌ Failed to create device: {e}")
    exit(1)

wa = getattr(device, "write_api_key", None)
ra = getattr(device, "read_api_key", None)
safe_print("Device API keys", {"write_api_key": wa, "read_api_key": ra})

# Create sensor types and configurations
sensor_type_map = {}
for label, type_name, unit in SENSOR_CONFIGS:
    try:
        st, st_created = SensorType.objects.get_or_create(name=type_name, defaults={"unit": unit})
        sensor_type_map[type_name] = st
        if st_created:
            print(f"Created SensorType '{type_name}' (unit={unit})")
    except Exception as e:
        print(f"⚠️  Failed to create sensor type {type_name}: {e}")

created_cfgs = []
for sensor_label, type_name, unit in SENSOR_CONFIGS:
    try:
        st = sensor_type_map.get(type_name)
        if not st:
            print(f"⚠️  Sensor type {type_name} not found, skipping {sensor_label}")
            continue
            
        cfg, cfg_created = SensorConfiguration.objects.get_or_create(
            device=device,
            sensor_label=sensor_label,
            defaults={"sensor_type": st}
        )
        if cfg_created:
            created_cfgs.append(sensor_label)
            print(f"✅ Created SensorConfiguration: {sensor_label} (type={type_name})")
        else:
            print(f"ℹ️  SensorConfiguration exists: {sensor_label}")
    except Exception as e:
        print(f"⚠️  Failed to create sensor configuration {sensor_label}: {e}")

# Create sample fouling data for the device
try:
    fouling_data, fd_created = FoulingData.objects.get_or_create(
        device=device,
        defaults={
            'fouling_factor': 0.00015,
            'u_actual': 650.0,
            'u_clean': 800.0,
            'performance_ratio': 0.81,
            'heat_duty': 150000.0,
            'lmtd': 28.5,
            'severity': 'Minor Fouling',
            'recommendation': 'Monitor closely, consider routine cleaning during next maintenance',
            'risk_level': 'Low'
        }
    )
    
    if fd_created:
        print("✅ Created sample fouling data for device")
    else:
        print("ℹ️  Fouling data already exists")
except Exception as e:
    print(f"⚠️  Could not create fouling data: {e}")
    print("This might be because the FoulingData model isn't migrated yet")

print("\\n" + "="*50)
print("🎯 SETUP COMPLETE - READY FOR ARDUINO DATA")
print("="*50)
print("User:", user.username)
print("Password:", PASSWORD)
print("Customer:", customer.company_name, "(id:", customer.pk, ")")
print("Device:", device.name, "(id:", device.pk, ")")
print("Write API Key:", wa)
print("Read API Key:", ra)
print("Sensor Configurations:", ", ".join(created_cfgs))
print("")
print("📝 Arduino Configuration:")
print("   Device ID:", device.pk)
print("   Write API Key:", wa)
print("   Server:", "150.241.244.250:${HTTP_PORT}")
print("")
print("🔗 Dashboard URL: http://150.241.244.250:${HTTP_PORT}/api/ui/dashboard/")
print("="*50)
PY

echo "✅ Setup completed for customer: $RAW_CUSTOMER"
echo "📊 Dashboard: http://150.241.244.250:$HTTP_PORT/api/ui/dashboard/"
echo "🔑 Login with: $CUSTOMER / $ADMIN_PASSWORD"
echo ""
echo "To monitor logs:"
echo "  docker compose --env-file \"$ENV_FILE\" -p \"$PROJECT\" logs --tail 200 web"
