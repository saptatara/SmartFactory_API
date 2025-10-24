#!/bin/bash
# ============================================
# 🛑 Stop Heat Exchanger IoT Platform
# ============================================

echo "🛑 Stopping Heat Exchanger IoT Platform..."

# Stop and remove containers (keep volumes)
docker compose down

echo ""
echo "✅ All services stopped."

