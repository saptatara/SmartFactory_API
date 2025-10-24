# api/forms.py
from django import forms
from .models import SensorData, SensorConfiguration, Device

class SensorDataForm(forms.ModelForm):
    class Meta:
        model = SensorData
        fields = ['device', 'sensor_config', 'value']
    
    def __init__(self, customer, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['device'].queryset = Device.objects.filter(customer=customer, is_active=True)
        self.fields['sensor_config'].queryset = SensorConfiguration.objects.none()
        
        if 'device' in self.data:
            try:
                device_id = int(self.data.get('device'))
                self.fields['sensor_config'].queryset = SensorConfiguration.objects.filter(
                    device_id=device_id, device__customer=customer
                )
            except (ValueError, TypeError):
                pass
