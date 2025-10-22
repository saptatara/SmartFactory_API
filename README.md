IoT Platform POC (Django)
=========================

This is a minimal Django-based Proof-of-Concept for an IoT backend with simple API key authentication.

Endpoints
- POST /api/write/  : write sensor data (JSON)
- GET  /api/read/?device=<device_id>&limit=100 : read recent data
- GET  /api/create_apikey/?customer=<slug> : create API key for a customer (quick helper)

Quick start
1. Unzip the folder and `cd` into it
2. Create virtualenv and install:
   python -m venv venv
   source venv/bin/activate   # or venv\Scripts\activate on Windows
   pip install -r requirements.txt
3. Run migrations:
   python manage.py migrate
4. Create superuser (optional):
   python manage.py createsuperuser
5. Run server:
   python manage.py runserver

Example: create apikey for customer 'zeroloss':
GET /api/create_apikey/?customer=zeroloss

Example: send data (curl)
curl -X POST http://127.0.0.1:8000/api/write/ -H 'Content-Type: application/json' -d '{"device_id":"esp1","apikey":"<KEY>","data":{"temp1":45.2}}'

Example: read data
GET /api/read/?device=esp1&limit=10
