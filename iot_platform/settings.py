import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url
# Add this at the top of settings.py if you're getting SSL warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------
# Base and environment setup
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ---------------------------------------------------------
# Security and environment settings
# ---------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret")
DEBUG = os.getenv("DEBUG", "True") == "True"
#ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,192.168.1.2").split(",")
# Read allowed hosts from env, try both names for backwards compatibility
_allowed = os.getenv("ALLOWED_HOSTS")
if not _allowed:
    _allowed = os.getenv("DJANGO_ALLOWED_HOSTS")

# fallback default
if not _allowed:
    _allowed = "localhost,127.0.0.1"

ALLOWED_HOSTS = [h.strip() for h in _allowed.split(",") if h.strip()]

# ---------------------------------------------------------
# Installed apps
# ---------------------------------------------------------
INSTALLED_APPS = [
    # Default Django apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',
    'django_prometheus',

    # Your local apps
    'api',
    'devices',
]

# ---------------------------------------------------------
# Middleware
# ---------------------------------------------------------
MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',  # must come first for metrics
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

# ---------------------------------------------------------
# URL and WSGI
# ---------------------------------------------------------
ROOT_URLCONF = 'iot_platform.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'iot_platform.wsgi.application'

# ---------------------------------------------------------
# Database (SQLite by default, auto-switchable via DATABASE_URL)
# ---------------------------------------------------------
DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=300,
    )
}

# ---------------------------------------------------------
# Authentication & REST Framework (JWT)
# ---------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

LOGIN_REDIRECT_URL = '/api/ui/dashboard/'

# ---------------------------------------------------------
# Static files
# ---------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# ---------------------------------------------------------
# Timezone & Localization
# ---------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# ================================================================
# Licensing enforcement - WITH SSL FIX
# ================================================================
# ================================================================
# Non-blocking license check
# ================================================================
import os
import requests
from datetime import date
import threading

def check_license_async():
    """Check license in background without blocking startup"""
    LICENSE_KEY = os.getenv("LICENSE_KEY")
    LICENSE_END = os.getenv("LICENSE_END")
    LICENSE_SERVER_URL = os.getenv("LICENSE_SERVER_URL")
    
    try:
        # Check expiry date first
        expiry = date.fromisoformat(LICENSE_END) if LICENSE_END else None
        if expiry and expiry < date.today():
            print("❌ License expired. Please contact support to renew.")
            return False

        # Remote check with SSL workaround
        if LICENSE_SERVER_URL and LICENSE_KEY:
            try:
                r = requests.get(
                    LICENSE_SERVER_URL,
                    params={"key": LICENSE_KEY, "customer": os.getenv("CUSTOMER_NAME")},
                    timeout=15,
                    verify=False
                )
                if r.status_code == 200 and r.json().get("valid", False):
                    print("✅ License verified successfully")
                    return True
                else:
                    print("⚠️ License verification failed")
                    return False
            except Exception as e:
                print(f"⚠️ License server unreachable: {e}")
                return True  # Don't block if server is down
    except Exception as e:
        print(f"⚠️ License check error: {e}")
        return True  # Don't block on license errors

# Run license check in background thread
license_thread = threading.Thread(target=check_license_async, daemon=True)
license_thread.start()
