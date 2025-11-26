from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Customer,
    Device,
    DeviceType,
    SensorType,
    SensorConfiguration,
    SensorData,
    IoTData,
    FoulingData,
)


class CustomerSpecificAdmin(admin.ModelAdmin):
    """Base class for customer-specific admin views"""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Filter by customer for non-superusers
        return qs.filter(customer__user=request.user)

    def save_model(self, request, obj, form, change):
        # Automatically set customer for new objects if user is not superuser
        if not request.user.is_superuser and not change:
            if hasattr(obj, "customer") and not obj.customer:
                try:
                    customer = Customer.objects.get(user=request.user)
                    obj.customer = customer
                except Customer.DoesNotExist:
                    pass
        super().save_model(request, obj, form, change)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["company_name", "user", "contact_email", "phone_number", "created_at", "dashboard_link"]
    list_filter = ["created_at", "receive_sms_alerts", "receive_email_alerts"]
    search_fields = ["company_name", "contact_email"]
    readonly_fields = ["dashboard_url"]
    
    def dashboard_link(self, obj):
        return format_html('<a href="/api/ui/dashboard/{}/" target="_blank" class="button">View Dashboard</a>', obj.dashboard_url)
    dashboard_link.short_description = "Dashboard"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)


@admin.register(DeviceType)
class DeviceTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]


@admin.register(Device)
class DeviceAdmin(CustomerSpecificAdmin):
    list_display = [
        "name",
        "customer",
        "device_type",
        "location",
        "is_active",
        "created_at",
        "api_keys",
        "quick_actions",
    ]
    list_filter = ["is_active", "device_type", "created_at", "customer"]
    search_fields = ["name", "location"]
    readonly_fields = ["write_api_key", "read_api_key"]

    def api_keys(self, obj):
        return format_html(
            '<div style="font-family: monospace; font-size: 11px;">'
            '<strong>Write:</strong> {}<br>'
            '<strong>Read:</strong> {}</div>',
            obj.write_api_key,
            obj.read_api_key
        )
    api_keys.short_description = "API Keys"

    def quick_actions(self, obj):
        return format_html(
            '<div class="action-buttons">'
            '<a href="/api/ui/device/{}/" class="button" target="_blank" style="display: inline-block; padding: 4px 8px; background: #007bff; color: white; text-decoration: none; border-radius: 3px; margin-right: 5px; font-size: 12px;">📊 View</a>'
            '<a href="/api/ui/device/{}/fouling/" class="button" target="_blank" style="display: inline-block; padding: 4px 8px; background: #fd7e14; color: white; text-decoration: none; border-radius: 3px; font-size: 12px;">🔥 Fouling</a>'
            '</div>',
            obj.id, obj.id
        )
    quick_actions.short_description = "Quick Actions"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "customer" and not request.user.is_superuser:
            kwargs["queryset"] = Customer.objects.filter(user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(SensorType)
class SensorTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "unit", "description"]
    list_filter = ["name"]
    search_fields = ["name", "unit"]


@admin.register(SensorConfiguration)
class SensorConfigurationAdmin(CustomerSpecificAdmin):
    list_display = ["sensor_label", "device", "sensor_type", "expected_min", "expected_max"]
    list_filter = ["sensor_type", "device"]
    search_fields = ["sensor_label", "device__name"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(device__customer__user=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "device" and not request.user.is_superuser:
            kwargs["queryset"] = Device.objects.filter(customer__user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(SensorData)
class SensorDataAdmin(CustomerSpecificAdmin):
    list_display = ["device", "sensor_config", "value", "unit_display", "created_at"]
    list_filter = ["device", "sensor_config__sensor_type", "created_at"]
    search_fields = ["device__name", "sensor_config__sensor_label"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"
    
    def unit_display(self, obj):
        return obj.sensor_config.sensor_type.unit
    unit_display.short_description = "Unit"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(device__customer__user=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            if db_field.name == "device":
                kwargs["queryset"] = Device.objects.filter(customer__user=request.user)
            elif db_field.name == "sensor_config":
                kwargs["queryset"] = SensorConfiguration.objects.filter(
                    device__customer__user=request.user
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(IoTData)
class IoTDataAdmin(CustomerSpecificAdmin):
    """New generalized IoT data admin replacing old FoulingData."""

    list_display = ["device", "key", "value", "unit", "is_alert", "created_at"]
    list_filter = ["is_alert", "device", "created_at"]
    search_fields = ["device__name", "key", "alert_message"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(device__customer__user=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "device" and not request.user.is_superuser:
            kwargs["queryset"] = Device.objects.filter(customer__user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(FoulingData)
class FoulingDataAdmin(CustomerSpecificAdmin):
    """Admin for fouling factor calculations"""
    
    list_display = ["device", "fouling_factor", "u_actual", "u_clean", "performance_ratio", "severity", "calculated_at"]
    list_filter = ["severity", "risk_level", "device", "calculated_at"]
    search_fields = ["device__name", "severity", "recommendation"]
    readonly_fields = ["calculated_at"]
    date_hierarchy = "calculated_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(device__customer__user=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "device" and not request.user.is_superuser:
            kwargs["queryset"] = Device.objects.filter(customer__user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
