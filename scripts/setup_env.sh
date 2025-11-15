#!/bin/bash
# ==============================================
# SmartFactory_API Environment Setup Script
# ==============================================
# This script ensures your .env has the right host/IP for Django to work on LAN.

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
BACKUP_FILE="$ENV_FILE.bak"
HOST_IP="192.168.1.2"
PORT="8010"

echo "🔧 Setting up environment in: $ENV_FILE"

# Create .env if missing
if [ ! -f "$ENV_FILE" ]; then
  echo "⚙️  No .env file found. Creating one from template..."
  if [ -f "$PROJECT_ROOT/.env.template" ]; then
    cp "$PROJECT_ROOT/.env.template" "$ENV_FILE"
  elif [ -f "$PROJECT_ROOT/.env.example" ]; then
    cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
  else
    echo "❌ No .env template found! Please create .env manually."
    exit 1
  fi
fi

# Backup before modifying
cp "$ENV_FILE" "$BACKUP_FILE"

# Update or append HTTP_PORT
if grep -q '^HTTP_PORT=' "$ENV_FILE"; then
  sed -i.bak "s/^HTTP_PORT=.*/HTTP_PORT=${PORT}/" "$ENV_FILE"
else
  echo "HTTP_PORT=${PORT}" >> "$ENV_FILE"
fi

# Update or append ALLOWED_HOSTS
if grep -q '^ALLOWED_HOSTS=' "$ENV_FILE"; then
  sed -i.bak "s@^ALLOWED_HOSTS=.*@ALLOWED_HOSTS=localhost,127.0.0.1,${HOST_IP}@" "$ENV_FILE"
else
  echo "ALLOWED_HOSTS=localhost,127.0.0.1,${HOST_IP}" >> "$ENV_FILE"
fi

echo "✅ Updated .env file:"
grep -E 'ALLOWED_HOSTS|HTTP_PORT' "$ENV_FILE"
echo "------------------------------------"

# Restart Docker containers
cd "$PROJECT_ROOT"
echo "♻️  Restarting Docker Compose stack..."
docker compose down
docker compose up -d --build

echo "✅ Docker containers restarted successfully."
echo "Now test from browser:  http://${HOST_IP}:${PORT}/admin"
echo "and update your Arduino sketch with:"
echo "  const char* host = \"${HOST_IP}\";"
echo "  const int port = ${PORT};"

