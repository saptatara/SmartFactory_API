#!/usr/bin/env bash
set -euo pipefail

# ================================================================
# Multi-Tenant Setup Script for SmartFactory_API with Licensing
# (Updated: preserves all original features + auto-detect public IP and
#  include it in DJANGO_ALLOWED_HOSTS so you can reach the admin from the VM's public IP)
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
# Step 4: Detect public IP and compose ALLOWED_HOSTS
# ---------------------------------------------------------------
# Try several methods to detect the VM's public IP. Prefer HTTP queries, fallback to local host detection.
PUBLIC_IP=""
# try common external services (if instance has outbound internet)
if command -v curl >/dev/null 2>&1; then
  PUBLIC_IP="$(curl -s ifconfig.me || true)"
  if [ -z "${PUBLIC_IP}" ]; then
    PUBLIC_IP="$(curl -s icanhazip.com || true)"
  fi
fi
# fallback using dig or host (rare)
if [ -z "${PUBLIC_IP}" ] && command -v dig >/dev/null 2>&1; then
  PUBLIC_IP="$(dig +short myip.opendns.com @resolver1.opendns.com || true)"
fi
# fallback to hostname -I (useful for private IPs)
if [ -z "${PUBLIC_IP}" ] && command -v hostname >/dev/null 2>&1; then
  # hostname -I works on many linux systems; take first entry
  PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
fi

# final fallback: empty (we will still include localhost/127.0.0.1)
if [ -n "${PUBLIC_IP}" ]; then
  # strip whitespace
  PUBLIC_IP="$(echo "${PUBLIC_IP}" | tr -d '[:space:]')"
  DJANGO_ALLOWED_HOSTS_VAL="localhost,127.0.0.1,${PUBLIC_IP}"
else
  DJANGO_ALLOWED_HOSTS_VAL="localhost,127.0.0.1"
fi

echo "Detected public IP (may be blank if detection failed): '${PUBLIC_IP}'"
echo "Will write DJANGO_ALLOWED_HOSTS='${DJANGO_ALLOWED_HOSTS_VAL}' into tenant .env"

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
POSTGRES_PORT=$((RANDOM % 1000 + 5500))

# Networking
HTTP_PORT=${HTTP_PORT}

# ===== Licensing =====
LICENSE_KEY=${LICENSE_KEY}
LICENSE_START=${LICENSE_START}
LICENSE_END=${LICENSE_END}
LICENSE_SERVER_URL=https://license.smartfactory.com/verify
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
# Step 6: Build and start Docker for tenant
# ---------------------------------------------------------------
PROJECT_NAME="${CUSTOMER}_iot"
echo "🐳 Starting Docker environment for ${CUSTOMER} (project: ${PROJECT_NAME})..."
docker compose --env-file "${ENV_PATH_TENANT}" -p "${PROJECT_NAME}" -f "${CUSTOMER_DIR}/docker-compose.yml" up -d --build

# ---------------------------------------------------------------
# Step 7: Apply migrations & collect static files
# ---------------------------------------------------------------
echo "🛠  Running migrations..."
docker compose --env-file "${ENV_PATH_TENANT}" -p "${PROJECT_NAME}" exec -T web python manage.py migrate --noinput
echo "📦 Collecting static files..."
docker compose --env-file "${ENV_PATH_TENANT}" -p "${PROJECT_NAME}" exec -T web python manage.py collectstatic --noinput

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
# Step 9: Summary & next steps
# ---------------------------------------------------------------
echo "✅ ${CUSTOMER} environment is ready!"
echo "🔑 License Key: ${LICENSE_KEY}"
echo "📅 Valid From: ${LICENSE_START}  →  ${LICENSE_END}"
echo "🌐 URL: http://localhost:${HTTP_PORT} (or http://<PUBLIC_IP>:${HTTP_PORT} if your cloud firewall/security-group permits traffic)"
echo ""
echo "DJANGO_ALLOWED_HOSTS written into ${ENV_PATH_TENANT}:"
sed -n '1,120p' "${ENV_PATH_TENANT}" | grep -i DJANGO_ALLOWED_HOSTS || true
echo ""
echo "If you need to reach via public IP, ensure the cloud VM security group / firewall allows inbound TCP on port ${HTTP_PORT}."
echo ""
echo "To inspect logs if anything failed:"
echo "  docker compose --env-file \"${ENV_PATH_TENANT}\" -p \"${PROJECT_NAME}\" logs --tail 200 web"
echo ""
echo "To stop this tenant:"
echo "  docker compose --env-file \"${ENV_PATH_TENANT}\" -p \"${PROJECT_NAME}\" down"

