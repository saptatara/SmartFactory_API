#!/bin/bash

# Complete Application Startup Script
echo "🎯 Starting IoT Platform Application..."
echo "======================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Creating one..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🐍 Activating virtual environment..."
source venv/bin/activate

# Create python symlink in venv if it doesn't exist
if [ ! -f "venv/bin/python" ]; then
    echo "🔗 Creating python symlink in virtual environment..."
    cd venv/bin
    ln -s python3 python
    ln -s pip3 pip
    cd /home/ubuntu/HeatExchanger_Only_IOT
fi

# Install requirements if not installed
if ! pip list | grep -q "Django"; then
    echo "📦 Installing requirements..."
    pip install -r requirements.txt
fi

# Run migrations
echo "📦 Running migrations..."
cd /home/ubuntu/HeatExchanger_Only_IOT

if python manage.py makemigrations 2>/dev/null; then
    echo "✅ Migrations created"
else
    echo "ℹ️  No new migrations needed"
fi

if python manage.py migrate; then
    echo "✅ Database migrated"
else
    echo "❌ Migration failed"
    exit 1
fi

# Collect static files
echo "📁 Collecting static files..."
# Fix permissions first
sudo chown -R ubuntu:ubuntu /home/ubuntu/HeatExchanger_Only_IOT/staticfiles/ 2>/dev/null || true
sudo chmod -R 755 /home/ubuntu/HeatExchanger_Only_IOT/staticfiles/ 2>/dev/null || true

if python manage.py collectstatic --noinput; then
    echo "✅ Static files collected"
    # Fix permissions after collection
    sudo chown -R www-data:www-data /home/ubuntu/HeatExchanger_Only_IOT/staticfiles/ 2>/dev/null || true
    sudo chmod -R 755 /home/ubuntu/HeatExchanger_Only_IOT/staticfiles/ 2>/dev/null || true
else
    echo "❌ Static collection failed - trying with clear option"
    python manage.py collectstatic --noinput --clear
    sudo chown -R www-data:www-data /home/ubuntu/HeatExchanger_Only_IOT/staticfiles/ 2>/dev/null || true
    sudo chmod -R 755 /home/ubuntu/HeatExchanger_Only_IOT/staticfiles/ 2>/dev/null || true
fi
# Start services
echo "🚀 Starting services..."
/home/ubuntu/HeatExchanger_Only_IOT/start_services.sh

echo ""
echo "🎉 IoT Platform Application started successfully!"
echo "================================================="
echo "📊 Application Status:"
echo "Gunicorn: $(pgrep -f "gunicorn" > /dev/null && echo '✅ RUNNING' || echo '❌ STOPPED')"
echo "Nginx: $(if command -v nginx >/dev/null 2>&1; then sudo systemctl is-active nginx && echo '✅ RUNNING' || echo '❌ STOPPED'; else echo '❌ NOT INSTALLED'; fi)"
echo ""
echo "🌐 Access URLs:"
PUBLIC_IP=$(curl -4 -s icanhazip.com || hostname -I | awk '{print $1}')
echo "Admin Panel: http://$PUBLIC_IP/admin"
echo "API Base: http://$PUBLIC_IP/api/"
echo ""
echo "🔧 API Endpoints:"
echo "Create API Key: POST /api/create_apikey/"
echo "Get API Key: GET /api/get_apikey/"
echo "Delete API Key: DELETE /api/delete_apikey/"
echo "Write Data: POST /api/write_data/<device_id>/"
echo "Get Sensor Data: GET /api/sensor_data/<device_id>/"
echo ""
echo "💡 Management commands:"
echo "Use './manage.sh' instead of 'python manage.py'"
echo "Use './stop_services.sh' to stop services"
echo "Use './restart_services.sh' to restart services"
