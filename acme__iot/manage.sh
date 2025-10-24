#!/bin/bash

# Django Management Script with Virtual Environment
echo "🐍 Running Django management command with virtual environment..."

# Check and activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✅ Virtual environment activated"
else
    echo "❌ Virtual environment not found. Using system Python."
fi

# Run the command with python3
python3 manage.py "$@"
