#!/bin/bash
# ================================================================
# Multi-Tenant Setup Script for IoT Platform with Licensing
# Author: Sameer Wadekar
# ================================================================

if [ -z "$1" ]; then
    echo "Usage: ./multi_tenant_setup.sh <customer_name> [license_days]"
    exit 1
fi

CUSTOMER=$(echo "$1" | tr '[:upper:]' '[:lower:]')
LICENSE_DAYS=${2:-30}  # Default trial = 30 days
BASE_DIR=$(pwd)
TEMPLATE_DIR="${BASE_DIR}/HeatExchanger_Only_IOT"
CUSTOMER_DIR="${BASE_DIR}/${CUSTOMER}_iot"

echo "🚀 Creating new IoT environment for ${CUSTOMER} (License: ${LICENSE_DAYS} days)"

# ---------------------------------------------------------------
# Step 1: Copy project template
# ---------------------------------------------------------------
if [ -d "$CUSTOMER_DIR" ]; then
    echo "⚠️  ${CUSTOMER_DIR} already exists. Skipping copy..."
else
    cp -r "$TEMPLATE_DIR" "$CUSTOMER_DIR"
    echo "✅ Copied base project to ${CUSTOMER_DIR}"
fi
cd "$CUSTOMER_DIR" || exit 1

# ---------------------------------------------------------------
# Step 2: Generate credentials
# ---------------------------------------------------------------
POSTGRES_DB="${CUSTOMER}_db"
POSTGRES_USER="${CUSTOMER}_user"
POSTGRES_PASSWORD=$(openssl rand -hex 8)
DJANGO_SECRET_KEY=$(openssl rand -hex 16)

# ---------------------------------------------------------------
# Step 3: Generate license
# ---------------------------------------------------------------
LICENSE_KEY=$(openssl rand -hex 12)
LICENSE_START=$(date +"%Y-%m-%d")
LICENSE_END=$(date -v+${LICENSE_DAYS}d +"%Y-%m-%d" 2>/dev/null || date -d "+${LICENSE_DAYS} days" +"%Y-%m-%d")

cat > .env <<EOF
# ===============================
# Environment for ${CUSTOMER}
# ===============================
CUSTOMER_NAME=${CUSTOMER}
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_PORT=5432
DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=*

# ====== Licensing ======
LICENSE_KEY=${LICENSE_KEY}
LICENSE_START=${LICENSE_START}
LICENSE_END=${LICENSE_END}
LICENSE_SERVER_URL=https://license.yourdomain.com/verify
EOF

echo "✅ .env created with license valid until ${LICENSE_END}"

# ---------------------------------------------------------------
# Step 4: Build and start Docker
# ---------------------------------------------------------------
docker compose -p "${CUSTOMER}_iot" up -d --build
if [ $? -eq 0 ]; then
    echo "✅ ${CUSTOMER} IoT Platform started successfully!"
    echo "🔑 License Key: ${LICENSE_KEY}"
    echo "📅 Valid From: ${LICENSE_START} To: ${LICENSE_END}"
else
    echo "❌ Docker startup failed. Check logs with:"
    echo "   docker compose -p ${CUSTOMER}_iot logs -f"
    exit 1
fi

# ---------------------------------------------------------------
# Step 5: Run migrations & collectstatic inside container
# ---------------------------------------------------------------
docker compose -p "${CUSTOMER}_iot" exec web python manage.py migrate
docker compose -p "${CUSTOMER}_iot" exec web python manage.py collectstatic --noinput

echo "✅ Migrations and static files ready."
echo "🌐 Access dashboard: http://localhost:8000"

