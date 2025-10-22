#!/bin/bash

# Virtual Environment Check Script
echo "🔍 Checking Virtual Environment..."
echo "================================="

if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ Virtual environment not active"
    
    if [ -f "venv/bin/activate" ]; then
        echo "🐍 Activating virtual environment..."
        source venv/bin/activate
        echo "✅ Virtual environment activated"
    else
        echo "❌ Virtual environment not found at venv/bin/activate"
        echo "📦 Creating new virtual environment..."
        python3 -m venv venv
        source venv/bin/activate
        echo "✅ Virtual environment created and activated"
        
        # Install requirements
        if [ -f "requirements.txt" ]; then
            echo "📦 Installing requirements..."
            pip install -r requirements.txt
        fi
    fi
else
    echo "✅ Virtual environment is active: $VIRTUAL_ENV"
fi

echo ""
echo "🐍 Python: $(which python)"
echo "📦 Python version: $(python --version)"
echo "📋 Installed packages:"
pip list --format=columns | grep -E "(Django|gunicorn|djangorestframework)"
