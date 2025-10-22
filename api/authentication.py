# api/authentication.py
from rest_framework import authentication
from rest_framework import exceptions
from .models import Device

class DeviceAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        # Get the authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header:
            return None  # Let other authentication classes handle it
        
        # Extract the key (remove any prefix like "Bearer" or "Token")
        if ' ' in auth_header:
            auth_type, auth_key = auth_header.split(' ', 1)
        else:
            auth_key = auth_header
        
        # Try to find a device with this API key
        try:
            device = Device.objects.get(
                write_api_key=auth_key,
                is_active=True
            )
            return (device.customer.user, device)  # Return (user, device) tuple
        except Device.DoesNotExist:
            try:
                # Also check read API key for read operations
                device = Device.objects.get(
                    read_api_key=auth_key,
                    is_active=True
                )
                return (device.customer.user, device)
            except Device.DoesNotExist:
                raise exceptions.AuthenticationFailed('Invalid device API key')
