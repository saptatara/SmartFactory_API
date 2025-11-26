from django.urls import path
from . import views

urlpatterns = [
    # ==================== CUSTOMER UI VIEWS ====================
    path('ui/dashboard/', views.customer_dashboard, name='customer_dashboard'),
    path('ui/dashboard/<uuid:dashboard_uuid>/', views.customer_dashboard_uuid, name='customer_dashboard_ui'),
    path('ui/device/<int:device_id>/', views.device_detail, name='device_detail'),
    path('ui/device/<int:device_id>/ui/', views.device_detail_ui, name='device_detail_ui'),
    path('ui/add-sensor-data/', views.add_sensor_data, name='add_sensor_data'),
    path('ui/sensor-configs/', views.sensor_configurations, name='sensor_configurations'),

    # ==================== FOULING FACTOR UI VIEWS ====================
    path('ui/fouling-calculator/', views.fouling_calculator, name='fouling_calculator'),
    path('ui/device/<int:device_id>/fouling/', views.fouling_monitoring, name='fouling_monitoring'),

    path('ui/login/', views.customer_login, name='customer_login'),
    path('ui/logout/', views.customer_logout, name='customer_logout'),

    # ==================== API ENDPOINTS ====================
    path('write_data/<int:device_id>/', views.write_data, name='write_data'),
    path('sensor_data/<int:device_id>/', views.get_sensor_data, name='get_sensor_data'),

    path('dashboard_data/<uuid:dashboard_uuid>/', views.customer_dashboard_data, name='customer_dashboard_data'),

    path('api/dashboard/<uuid:dashboard_uuid>/data/', views.customer_devices_data, name='customer_devices_data'),

    # ==================== DEVICE MANAGEMENT API ====================
    path('devices/', views.device_list, name='device_list'),
    path('devices/<int:device_id>/', views.device_detail_api, name='device_detail_api'),

    # ==================== FOULING FACTOR API ====================
    path('fouling/calculate/', views.calculate_fouling_api, name='calculate_fouling'),
    path('fouling/calculate-clean-u/', views.calculate_clean_u_api, name='calculate_clean_u'),

    # ✅ FIXED — added missing comma, correct order
    path(
        "devices/<int:device_id>/fouling-history/",
        views.device_fouling_history,
        name="device_fouling_history",
    ),
    path(
        "devices/<int:device_id>/fouling-snapshot/",
        views.device_fouling_snapshot,
        name="device_fouling_snapshot",
    ),

    # ==================== AUTHENTICATION API ====================
    path('create_apikey/', views.create_apikey, name='create_apikey'),
    path('get_apikey/', views.get_apikey, name='get_apikey'),
    path('delete_apikey/', views.delete_apikey, name='delete_apikey'),

    # ==================== CUSTOMER DEVICES API ====================
    path('customer/<int:customer_id>/devices/', views.customer_devices, name='customer_devices'),

    # ==================== REPORTING API ====================
    path(
        "devices/<int:device_id>/fouling-report-csv/",
        views.device_fouling_report_csv,
        name="device_fouling_report_csv",
    ),
    path(
        "devices/<int:device_id>/sensor-report-csv/",
        views.device_sensor_report_csv,
        name="device_sensor_report_csv",
    ),
]
