#!/bin/bash
# ============================================
# 🚀 Start Heat Exchanger IoT Platform
# ============================================

echo "🟢 Starting Heat Exchanger IoT Platform..."

# Start containers in detached mode (no rebuild)
docker compose up -d

# Show container status
echo ""
echo "✅ Containers running:"
docker compose ps

