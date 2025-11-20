# api/serializers.py
from rest_framework import serializers
from .models import (
    Customer, Device, DeviceType,
    SensorData, SensorConfiguration, SensorType, IoTData
)


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "company_name", "contact_email", "phone_number", "created_at"]


class DeviceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceType
        fields = "__all__"


class SensorTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorType
        fields = ["id", "name", "unit", "description"]


class SensorConfigurationSerializer(serializers.ModelSerializer):
    sensor_type = SensorTypeSerializer()

    class Meta:
        model = SensorConfiguration
        fields = ["id", "sensor_label", "sensor_type", "expected_min", "expected_max"]


class SensorDataSerializer(serializers.ModelSerializer):
    sensor_label = serializers.CharField(source="sensor_config.sensor_label", read_only=True)
    unit = serializers.CharField(source="sensor_config.sensor_type.unit", read_only=True)
    timestamp = serializers.DateTimeField(source="created_at", format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = SensorData
        fields = ["id", "value", "timestamp", "sensor_label", "unit"]


class DeviceSerializer(serializers.ModelSerializer):
    sensor_data = serializers.SerializerMethodField()
    device_type = DeviceTypeSerializer()

    class Meta:
        model = Device
        fields = ["id", "name", "location", "device_type", "created_at", "sensor_data"]

    def get_sensor_data(self, obj):
        readings = obj.sensor_data.all().select_related(
            "sensor_config", "sensor_config__sensor_type"
        ).order_by("-created_at")[:50]

        grouped = {}
        for r in readings:
            label = r.sensor_config.sensor_label
            grouped.setdefault(label, []).append({
                "timestamp": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "value": r.value,
                "unit": r.sensor_config.sensor_type.unit,
            })

        for label in grouped:
            #grouped[label].sort(key=lambda x: x["timestamp"])
            grouped[label] = grouped[label][::-1]
        return grouped


class IoTDataSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source="device.name", read_only=True)

    class Meta:
        model = IoTData
        fields = ["id", "device_name", "key", "value", "unit", "notes", "is_alert", "alert_message", "created_at"]

