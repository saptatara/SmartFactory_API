#!/bin/bash
# ============================================
# 🔁 Restart Heat Exchanger IoT Platform
# ============================================

echo "🔁 Restarting Heat Exchanger IoT Platform..."

# Stop all running containers (if any)
docker compose down --remove-orphans

# Rebuild and start containers in detached mode
docker compose up -d --build

# Show container status
echo ""
echo "✅ Containers running:"
docker compose exec web python manage.py collectstatic --noinput
docker compose ps

