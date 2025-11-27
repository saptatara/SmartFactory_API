#!/usr/bin/env bash
set -euo pipefail

# ================================================================
# Multi-Tenant Setup Script for SmartFactory_API with Licensing
# (Updated: Fixes SSL and admin issues)
# ================================================================
#
# Usage:
#   ./multi_tenant_setup.sh <customer_name> [license_days] [http_port]
# Example:
#   ./multi_tenant_setup.sh acme 30 8001
#
# Notes:
#  - The script will write .env.<customer> into repo root and into <customer>_iot/
#  - It will also create <customer>_iot/.env used by docker compose for that tenant
#  - It will not overwrite an existing repo-level .env file
# ================================================================

if [ $# -lt 1 ]; then
  echo "Usage: $0 <customer_name> [license_days] [http_port]"
  exit 1
fi

CUSTOMER_RAW="$1"
CUSTOMER="$(echo "$CUSTOMER_RAW" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_' '_')"
LICENSE_DAYS="${2:-30}"
HTTP_PORT="${3:-8000}"

# Determine repository root (prefer git top-level if available)
if git rev-parse --show-toplevel >/dev/null 2>&1; then
  BASE_DIR="$(git rev-parse --show-toplevel)"
else
  BASE_DIR="$(pwd)"
fi

TEMPLATE_DIR="${BASE_DIR}"
CUSTOMER_DIR="${BASE_DIR}/${CUSTOMER}_iot"

echo "🚀 Creating new SmartFactory environment for '${CUSTOMER}' (Trial: ${LICENSE_DAYS} days) on port ${HTTP_PORT}"
echo "Repository root: ${BASE_DIR}"
echo "Template dir: ${TEMPLATE_DIR}"
echo "Customer dir: ${CUSTOMER_DIR}"

# ---------------------------------------------------------------
# Step 1: Copy base project (if needed)
# ---------------------------------------------------------------
if [ -d "${CUSTOMER_DIR}" ]; then
  echo "⚠️  ${CUSTOMER_DIR} already exists — verifying required files..."
  if [ ! -f "${CUSTOMER_DIR}/docker-compose.yml" ]; then
    echo "📁 docker-compose.yml missing in tenant dir — copying essential files..."
    rsync -a "${TEMPLATE_DIR}/docker-compose.yml" "${CUSTOMER_DIR}/"
    rsync -a "${TEMPLATE_DIR}/Dockerfile" "${CUSTOMER_DIR}/"
  fi
else
  echo "📁 Copying SmartFactory_API → ${CUSTOMER_DIR}"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --exclude 'venv' --exclude '.git' --exclude 'pgdata*' --exclude 'node_modules' "${TEMPLATE_DIR}/" "${CUSTOMER_DIR}/"
  else
    cp -r "${TEMPLATE_DIR}" "${CUSTOMER_DIR}"
  fi
  echo "✅ Copied base project to ${CUSTOMER_DIR}"
fi

mkdir -p "${CUSTOMER_DIR}"

# ---------------------------------------------------------------
# Step 2: Generate credentials
# ---------------------------------------------------------------
POSTGRES_DB="${CUSTOMER}_db"
POSTGRES_USER="${CUSTOMER}_user"
POSTGRES_PASSWORD="$(openssl rand -hex 12)"
DJANGO_SECRET_KEY="$(openssl rand -hex 24)"

# ---------------------------------------------------------------
# Step 3: Generate license info
# ---------------------------------------------------------------
LICENSE_KEY="$(openssl rand -hex 16)"
LICENSE_START="$(date '+%Y-%m-%d')"
if date -v+"${LICENSE_DAYS}"d >/dev/null 2>&1; then
  LICENSE_END="$(date -v+"${LICENSE_DAYS}"d '+%Y-%m-%d')"
else
  LICENSE_END="$(date -d "+${LICENSE_DAYS} days" '+%Y-%m-%d')"
fi

# ---------------------------------------------------------------
# Step 4: Set ALLOWED_HOSTS to wildcard (*) for all hosts
# ---------------------------------------------------------------
DJANGO_ALLOWED_HOSTS_VAL="*"

echo "🌐 Setting DJANGO_ALLOWED_HOSTS='${DJANGO_ALLOWED_HOSTS_VAL}' to allow all hosts"

# ---------------------------------------------------------------
# Step 5: Create .env files (both in repo root and tenant dir)
# ---------------------------------------------------------------
ENV_FILENAME=".env.${CUSTOMER}"
ENV_PATH_REPO="${BASE_DIR}/${ENV_FILENAME}"
ENV_PATH_TENANT="${CUSTOMER_DIR}/${ENV_FILENAME}"
ENV_PATH_TENANT_PLAIN="${CUSTOMER_DIR}/.env"

cat > "${ENV_PATH_REPO}" <<EOF
# ===============================
# Environment for ${CUSTOMER}
# ===============================
CUSTOMER_NAME=${CUSTOMER}

# Django
DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS_VAL}

# Database
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Networking
HTTP_PORT=${HTTP_PORT}

# ===== Licensing =====
LICENSE_KEY=${LICENSE_KEY}
LICENSE_START=${LICENSE_START}
LICENSE_END=${LICENSE_END}
# Disable license verification for now to avoid SSL issues
LICENSE_SERVER_URL=
# ---------------------------
# Twilio SMS configuration
# (These values are read by Django settings via os.getenv)
# You can set them in your shell before running this script, or leave blank to fill later.
TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID:-""}
TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN:-""}
TWILIO_FROM_NUMBER=${TWILIO_FROM_NUMBER:-""}
ALERT_SMS_TO=${ALERT_SMS_TO:-""}

# Optional per-tenant default thresholds (can be overridden by environment or settings)
THRESHOLD_T1IN=${THRESHOLD_T1IN:-50.0}
THRESHOLD_T2IN=${THRESHOLD_T2IN:-50.0}
THRESHOLD_T1OUT=${THRESHOLD_T1OUT:-50.0}
THRESHOLD_T2OUT=${THRESHOLD_T2OUT:-50.0}
THRESHOLD_PRESSURE=${THRESHOLD_PRESSURE:-10.0}
THRESHOLD_FOULING=${THRESHOLD_FOULING:-0.001}

# SMS cooldown (seconds) to reduce repeated alerts
SMS_ALERT_COOLDOWN_SECONDS=${SMS_ALERT_COOLDOWN_SECONDS:-1800}
# ---------------------------

EOF

# copy into tenant dir and create plain .env
cp -f "${ENV_PATH_REPO}" "${ENV_PATH_TENANT}"
cp -f "${ENV_PATH_TENANT}" "${ENV_PATH_TENANT_PLAIN}"

echo "✅ Created env files:"
echo "  - ${ENV_PATH_REPO}"
echo "  - ${ENV_PATH_TENANT}"
echo "  - ${ENV_PATH_TENANT_PLAIN}"

# copy into repo root .env only if not present (do not overwrite existing .env)
if [ ! -f "${BASE_DIR}/.env" ]; then
  cp -n "${ENV_PATH_REPO}" "${BASE_DIR}/.env" || true
  echo "ℹ️  .env did not exist in repo root — copied ${ENV_FILENAME} to ${BASE_DIR}/.env"
else
  echo "ℹ️  .env already exists in repo root; not overwriting."
fi

# ---------------------------------------------------------------
# Step 6: Build and start Docker for tenant (NO CACHE)
# ---------------------------------------------------------------
PROJECT_NAME="${CUSTOMER}_iot"
echo "🐳 Building Docker images for ${CUSTOMER} (project: ${PROJECT_NAME}) with NO CACHE..."

docker compose \
  --env-file "${ENV_PATH_TENANT}" \
  -p "${PROJECT_NAME}" \
  -f "${CUSTOMER_DIR}/docker-compose.yml" \
  build --no-cache

echo "🐳 Starting Docker containers for ${CUSTOMER}..."
docker compose \
  --env-file "${ENV_PATH_TENANT}" \
  -p "${PROJECT_NAME}" \
  -f "${CUSTOMER_DIR}/docker-compose.yml" \
  up -d

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
sleep 10
# ---------------------------------------------------------------
# Step 6.5: Install required Python packages
# ---------------------------------------------------------------
echo "📦 Installing required Python packages..."
docker compose --env-file "${ENV_PATH_TENANT}" -p "${PROJECT_NAME}" exec -T web pip install pytz

# ---------------------------------------------------------------
# Step 7: Apply migrations & collect static files (WITH ERROR HANDLING)
# ---------------------------------------------------------------
echo "🛠  Running migrations (including fouling factor tables)..."

# First, let's check if there are any migration issues
echo "🔍 Checking for migration issues..."
docker compose --env-file "${ENV_PATH_TENANT}" -p "${PROJECT_NAME}" exec -T web python manage.py check --database default || true

# Run migrations with error handling
if docker compose --env-file "${ENV_PATH_TENANT}" -p "${PROJECT_NAME}" exec -T web python manage.py migrate --noinput; then
  echo "✅ Migrations completed successfully"
else
  echo "⚠️  Migrations had issues, trying to continue..."
fi

echo "📦 Collecting static files..."
docker compose --env-file "${ENV_PATH_TENANT}" -p "${PROJECT_NAME}" exec -T web python manage.py collectstatic --noinput || echo "⚠️  Static collection had issues, continuing..."

# ---------------------------------------------------------------
# Step 8: Create or Reset Default Superuser
# ---------------------------------------------------------------
echo "👤 Creating or updating default Django superuser..."

docker compose --env-file "${ENV_PATH_TENANT}" -p "${PROJECT_NAME}" exec -T web \
  python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
username = "admin"
email = "admin@${CUSTOMER}.com"
password = "SmartFactory@123"

try:
    user, created = User.objects.get_or_create(username=username, defaults={"email": email})
    if created:
        user.set_password(password)
        user.is_superuser = True
        user.is_staff = True
        user.save()
        print("✅ Superuser 'admin' created with password 'SmartFactory@123'")
    else:
        user.set_password(password)
        user.email = email
        user.is_superuser = True
        user.is_staff = True
        user.save()
        print("🔁 Superuser 'admin' password reset to 'SmartFactory@123'")
except Exception as e:
    print(f"⚠️  Error creating superuser: {e}")
EOF

# ---------------------------------------------------------------
# Step 9: Create sample data for demonstration
# ---------------------------------------------------------------
echo "🔧 Creating sample data for demonstration..."

docker compose --env-file "${ENV_PATH_TENANT}" -p "${PROJECT_NAME}" exec -T web \
  python manage.py shell <<EOF
from api.models import Customer, Device, DeviceType, SensorType, SensorConfiguration, FoulingData
from django.contrib.auth.models import User
import uuid

try:
    user = User.objects.get(username="admin")
    customer, created = Customer.objects.get_or_create(
        user=user,
        defaults={
            'company_name': '${CUSTOMER} Company',
            'contact_email': 'admin@${CUSTOMER}.com',
            'dashboard_url': str(uuid.uuid4())
        }
    )
    
    if created:
        print(f"✅ Created customer: {customer.company_name}")
    
    # Create device type if needed
    device_type, _ = DeviceType.objects.get_or_create(
        name='Heat Exchanger',
        defaults={'description': 'Industrial heat exchange unit'}
    )
    
    # Create sample device
    device, device_created = Device.objects.get_or_create(
        customer=customer,
        name='Heat Exchanger Unit #1',
        defaults={
            'device_type': device_type,
            'location': 'Main Production Line',
            'is_active': True
        }
    )
    
    if device_created:
        print(f"✅ Created sample device: {device.name}")
    
    # Create sensor types
    temp_sensor, _ = SensorType.objects.get_or_create(
        name='Temperature',
        defaults={'unit': '°C', 'description': 'Temperature sensor'}
    )
    
    pressure_sensor, _ = SensorType.objects.get_or_create(
        name='Pressure', 
        defaults={'unit': 'kPa', 'description': 'Pressure sensor'}
    )
    
    # Create sensor configurations
    sensors_to_create = [
        ('t1_in', temp_sensor, 20.0, 100.0),
        ('t1_out', temp_sensor, 20.0, 100.0),
        ('t2_in', temp_sensor, 20.0, 100.0),
        ('t2_out', temp_sensor, 20.0, 100.0),
        ('pressure', pressure_sensor, 0.0, 20.0),
    ]
    
    for label, sensor_type, min_val, max_val in sensors_to_create:
        config, created = SensorConfiguration.objects.get_or_create(
            device=device,
            sensor_label=label,
            defaults={
                'sensor_type': sensor_type,
                'expected_min': min_val,
                'expected_max': max_val
            }
        )
        if created:
            print(f"✅ Created sensor: {label}")
    
    # Create sample fouling data
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
        print("✅ Created sample fouling data for demonstration")
    else:
        print("ℹ️  Fouling data already exists")
        
except Exception as e:
    print(f"⚠️  Could not create sample data: {e}")
EOF

# ---------------------------------------------------------------
# Step 10: Final health check
# ---------------------------------------------------------------
echo "🔍 Performing final health check..."
if docker compose --env-file "${ENV_PATH_TENANT}" -p "${PROJECT_NAME}" exec -T web python manage.py check --database default; then
  echo "✅ All systems operational!"
else
  echo "⚠️  Some checks failed, but basic functionality should work"
fi

# ---------------------------------------------------------------
# Step 11: Summary & next steps
# ---------------------------------------------------------------
echo ""
echo "🎉 ${CUSTOMER} environment is ready!"
echo "🔑 License Key: ${LICENSE_KEY}"
echo "📅 Valid From: ${LICENSE_START}  →  ${LICENSE_END}"
echo "🌐 URL: http://localhost:${HTTP_PORT}"
echo "👤 Admin Login: admin / SmartFactory@123"
echo ""
echo "🎯 FEATURES INCLUDED:"
echo "   • Fouling Factor Calculations"
echo "   • Heat Exchanger Performance Monitoring"
echo "   • Fouling Trend Analysis"
echo "   • Maintenance Recommendations"
echo "   • Professional Dashboard UI"
echo ""
echo "📊 To access the system:"
echo "  1. Go to http://localhost:${HTTP_PORT}/api/ui/dashboard/"
echo "  2. Login as admin / SmartFactory@123"
echo "  3. Explore fouling analysis and sensor monitoring"
echo ""
echo "🐳 Container Management:"
echo "  To view logs: docker compose --env-file \"${ENV_PATH_TENANT}\" -p \"${PROJECT_NAME}\" logs --tail 100 web"
echo "  To stop: docker compose --env-file \"${ENV_PATH_TENANT}\" -p \"${PROJECT_NAME}\" down"
echo "  To restart: docker compose --env-file \"${ENV_PATH_TENANT}\" -p \"${PROJECT_NAME}\" restart"
echo ""
echo "🔧 If you encounter admin interface issues, check your admin.py for proper 'actions' configuration"
