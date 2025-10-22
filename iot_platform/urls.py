from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse


def home(request):
    return HttpResponse("""
        <html>
        <head>
            <title>Heat Exchanger IoT Platform</title>
            <style>
                body { font-family: Arial, sans-serif; background: #f8f9fa; color: #333; text-align: center; padding: 50px; }
                h1 { color: #007bff; }
                a { color: #007bff; text-decoration: none; margin: 10px; }
                a:hover { text-decoration: underline; }
                .links { margin-top: 30px; }
                .card {
                    background: #fff; padding: 20px; border-radius: 10px;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.1); display: inline-block;
                }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>✅ Heat Exchanger IoT Platform</h1>
                <p>Welcome! Your Django + Docker setup is running successfully.</p>
                <div class="links">
                    <a href="/admin/">🛠 Admin Panel</a><br>
                    <a href="/api/">📡 API Endpoints</a><br>
                    <a href="/accounts/login/">🔐 Login</a>
                </div>
            </div>
        </body>
        </html>
    """)


urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('accounts/', include('django.contrib.auth.urls')),  # login/logout routes
]

