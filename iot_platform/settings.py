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
        conn_max_age=600,
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
import os
import requests
from datetime import date

LICENSE_KEY = os.getenv("LICENSE_KEY")
LICENSE_END = os.getenv("LICENSE_END")
LICENSE_SERVER_URL = os.getenv("LICENSE_SERVER_URL")

try:
    expiry = date.fromisoformat(LICENSE_END) if LICENSE_END else None
    if expiry and expiry < date.today():
        raise SystemExit("❌ License expired. Please contact support to renew.")

    # Optional: verify remotely WITH SSL FIX
    if LICENSE_SERVER_URL and LICENSE_KEY:
        try:
            # Disable SSL verification temporarily to fix handshake issues
            r = requests.get(
                LICENSE_SERVER_URL, 
                params={
                    "key": LICENSE_KEY, 
                    "customer": os.getenv("CUSTOMER_NAME")
                }, 
                timeout=10,
                verify=False  # ← THIS IS THE FIX
            )
            if r.status_code != 200 or not r.json().get("valid", False):
                raise SystemExit("❌ License verification failed. Contact admin.")
        except Exception as e:
            print(f"⚠️ License check warning: {e}")
            # Don't exit on license server connection issues, just warn
except Exception as e:
    raise SystemExit(f"❌ Licensing error: {e}")

