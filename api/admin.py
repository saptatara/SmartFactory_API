from django.contrib import admin
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
    list_display = ["company_name", "user", "contact_email", "phone_number", "created_at"]
    list_filter = ["created_at", "receive_sms_alerts", "receive_email_alerts"]
    search_fields = ["company_name", "contact_email"]
    readonly_fields = ["dashboard_url"]

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
    ]
    list_filter = ["is_active", "device_type", "created_at", "customer"]
    search_fields = ["name", "location"]
    readonly_fields = ["write_api_key", "read_api_key"]

    def api_keys(self, obj):
        return f"Write: {obj.write_api_key}\nRead: {obj.read_api_key}"

    api_keys.short_description = "API Keys"

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
    list_display = ["device", "sensor_config", "value", "created_at"]
    list_filter = ["device", "sensor_config__sensor_type", "created_at"]
    search_fields = ["device__name", "sensor_config__sensor_label"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"

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

    class Meta:
        verbose_name = "IoT Data"
        verbose_name_plural = "IoT Data"

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
    
    class Meta:
        verbose_name = "Fouling Data"
        verbose_name_plural = "Fouling Data"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(device__customer__user=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "device" and not request.user.is_superuser:
            kwargs["queryset"] = Device.objects.filter(customer__user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
