# =========================
# Dockerfile for Django app
# =========================

# Use official Python slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install OS-level dependencies
RUN apt-get update && apt-get install -y gcc libpq-dev curl && apt-get clean

# Copy requirements first (for better Docker caching)
COPY requirements.txt /app/

# Install dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy the rest of the project
COPY . /app/

# Collect static files (optional, safe to keep)
RUN python manage.py collectstatic --noinput || true

# Expose port
EXPOSE 8000

# Start server using Gunicorn
RUN python manage.py collectstatic --noinput
CMD ["gunicorn", "iot_platform.wsgi:application", "--bind", "0.0.0.0:8000"]
# In your Dockerfile, ensure you have:
RUN apt-get update && apt-get install -y ca-certificates && update-ca-certificates


