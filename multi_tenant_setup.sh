#!/usr/bin/env bash
set -euo pipefail

# ================================================================
# Multi-Tenant Setup Script for SmartFactory_API with Licensing
# Author: Sameer Wadekar
# ================================================================

# Usage:
#   ./multi_tenant_setup.sh <customer_name> [license_days] [http_port]
# Example:
#   ./multi_tenant_setup.sh acme 30 8001

if [ $# -lt 1 ]; then
  echo "Usage: $0 <customer_name> [license_days] [http_port]"
  exit 1
fi

CUSTOMER_RAW="$1"
CUSTOMER="$(echo "$CUSTOMER_RAW" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_' '_')"
LICENSE_DAYS="${2:-30}"
HTTP_PORT="${3:-8000}"

BASE_DIR="$(pwd)"
TEMPLATE_DIR="${BASE_DIR}"
CUSTOMER_DIR="${BASE_DIR}/${CUSTOMER}_iot"

echo "🚀 Creating new SmartFactory environment for '${CUSTOMER}' (Trial: ${LICENSE_DAYS} days) on port ${HTTP_PORT}"

# ---------------------------------------------------------------
# Step 1: Copy base project
# ---------------------------------------------------------------
if [ -d "${CUSTOMER_DIR}" ]; then
  echo "⚠️  ${CUSTOMER_DIR} already exists — verifying required files..."
  if [ ! -f "${CUSTOMER_DIR}/docker-compose.yml" ]; then
    echo "📁 docker-compose.yml missing — copying essential files..."
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

cd "${CUSTOMER_DIR}" || exit 1

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
# Step 4: Create .env file (auto-detect host IP and set ALLOWED_HOSTS)
# ---------------------------------------------------------------
ENV_FILE=".env.${CUSTOMER}"

# Attempt to detect the host LAN IP (non-loopback)
HOST_IP=""
# Preferred method: ip route
if command -v ip >/dev/null 2>&1; then
  HOST_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}' || true)
fi

# Fallback: parse ifconfig / ip addr
if [ -z "${HOST_IP}" ]; then
  if command -v ifconfig >/dev/null 2>&1; then
    # macOS / BSD style output
    HOST_IP=$(ifconfig 2>/dev/null | awk '/inet / && $2 != "127.0.0.1" {print $2; exit}' || true)
  else
    HOST_IP=$(ip addr 2>/dev/null | awk '/inet / && $2 !~ /127\\.0\\.0\\.1/ {split($2,a,"/"); print a[1]; exit}' || true)
  fi
fi

# final fallback
HOST_IP=${HOST_IP:-127.0.0.1}

cat > "${ENV_FILE}" <<EOF
# ===============================
# Environment for ${CUSTOMER}
# ===============================
CUSTOMER_NAME=${CUSTOMER}

# Django
DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
DJANGO_DEBUG=True

# IMPORTANT: provide ALLOWED_HOSTS (settings.py reads ALLOWED_HOSTS env var)
ALLOWED_HOSTS=localhost,127.0.0.1,${HOST_IP}

# Database
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_HOST=db
POSTGRES_PORT=$((RANDOM % 1000 + 5500))

# Networking
HTTP_PORT=${HTTP_PORT}

# ===== Licensing =====
LICENSE_KEY=${LICENSE_KEY}
LICENSE_START=${LICENSE_START}
LICENSE_END=${LICENSE_END}
LICENSE_SERVER_URL=https://license.smartfactory.com/verify
EOF

# Make a copy as .env for convenience (same behavior as before)
cp "${ENV_FILE}" .env

echo "✅ .env created for ${CUSTOMER} (valid until ${LICENSE_END}) with HOST_IP=${HOST_IP}"

# ---------------------------------------------------------------
# Step 5: Build and start Docker
# ---------------------------------------------------------------
PROJECT_NAME="${CUSTOMER}_iot"
echo "🐳 Starting Docker environment for ${CUSTOMER}..."
docker compose --env-file "${CUSTOMER_DIR}/${ENV_FILE}" -p "${PROJECT_NAME}" -f "${CUSTOMER_DIR}/docker-compose.yml" up -d --build

# ---------------------------------------------------------------
# Step 6: Apply migrations & collect static files
# ---------------------------------------------------------------
echo "🛠 Running migrations..."
docker compose --env-file "${ENV_FILE}" -p "${PROJECT_NAME}" exec -T web python manage.py migrate --noinput
echo "📦 Collecting static files..."
docker compose --env-file "${ENV_FILE}" -p "${PROJECT_NAME}" exec -T web python manage.py collectstatic --noinput
# ---------------------------------------------------------------
# Step 7: Create or Reset Default Superuser
# ---------------------------------------------------------------
echo "👤 Creating or updating default Django superuser..."

docker compose --env-file "${ENV_FILE}" -p "${PROJECT_NAME}" exec -T web \
  python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
username = "admin"
email = "admin@${CUSTOMER}.com"
password = "SmartFactory@123"

user, created = User.objects.get_or_create(username=username, defaults={"email": email})
if created:
    user.set_password(password)
    user.is_superuser = True
    user.is_staff = True
    user.save()
    print("✅ Superuser 'admin' created with password 'SmartFactory@123'")
else:
    user.set_password(password)
    user.save()
    print("🔁 Superuser 'admin' password reset to 'SmartFactory@123'")
EOF

# ---------------------------------------------------------------
# Step 8: Summary
# ---------------------------------------------------------------
echo "✅ ${CUSTOMER} environment is ready!"
echo "🔑 License Key: ${LICENSE_KEY}"
echo "📅 Valid From: ${LICENSE_START}  →  ${LICENSE_END}"
echo "🌐 URL: http://localhost:${HTTP_PORT}"
echo ""
echo "To create an admin user:"
echo "  docker compose --env-file ${ENV_FILE} -p ${PROJECT_NAME} exec web python manage.py createsuperuser"
echo ""
echo "To stop this tenant:"
echo "  docker compose -p ${PROJECT_NAME} down -v"
echo ""
echo "To view logs:"
echo "  docker compose --env-file ${ENV_FILE} -p ${PROJECT_NAME} logs -f"

