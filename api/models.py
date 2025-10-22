# api/models.py
from django.db import models
from django.contrib.auth.models import User
import uuid


class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    company_name = models.CharField(max_length=100)
    contact_email = models.EmailField()
    phone_number = models.CharField(max_length=15, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Customer-specific settings
    dashboard_url = models.UUIDField(default=uuid.uuid4, unique=True)
    alert_threshold = models.FloatField(default=0.8)
    receive_sms_alerts = models.BooleanField(default=True)
    receive_email_alerts = models.BooleanField(default=True)

    def __str__(self):
        return self.company_name


class DeviceType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Device(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="devices")
    device_type = models.ForeignKey(DeviceType, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=100, blank=True)
    write_api_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    read_api_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.customer.company_name})"


class SensorType(models.Model):
    name = models.CharField(max_length=100)  # e.g. Temperature, Pressure, Flow
    unit = models.CharField(max_length=20)   # e.g. °C, kPa, L/min
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.unit})"


class SensorConfiguration(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="sensor_configs")
    sensor_type = models.ForeignKey(SensorType, on_delete=models.CASCADE)
    sensor_label = models.CharField(max_length=50)
    expected_min = models.FloatField(null=True, blank=True)
    expected_max = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ["device", "sensor_label"]

    def __str__(self):
        return f"{self.device.name} - {self.sensor_label}"


class SensorData(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="sensor_data")
    sensor_config = models.ForeignKey(SensorConfiguration, on_delete=models.CASCADE)
    value = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["device", "created_at"])]

    def __str__(self):
        return f"{self.device.name} - {self.sensor_config.sensor_label}: {self.value}"


class IoTData(models.Model):
    """Generalized data model (replaces FoulingData)."""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="iot_data")
    key = models.CharField(max_length=100)  # e.g. metric name or computed field
    value = models.FloatField()
    unit = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_alert = models.BooleanField(default=False)
    alert_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.device.name} - {self.key}: {self.value} {self.unit or ''}"

