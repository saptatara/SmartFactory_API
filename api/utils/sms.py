# api/utils/sms.py
import os
from twilio.rest import Client
from django.conf import settings

def get_twilio_client():
    account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None) or os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None) or os.getenv("TWILIO_AUTH_TOKEN")
    return Client(account_sid, auth_token)

def send_sms(body: str, to: str, from_number: str = None):
    client = get_twilio_client()
    from_number = from_number or getattr(settings, "TWILIO_FROM_NUMBER", None) or os.getenv("TWILIO_FROM_NUMBER")
    if not (from_number and to and body):
        raise ValueError("TWILIO_FROM_NUMBER, to and body are required")
    message = client.messages.create(
        body=body,
        from_=from_number,
        to=to
    )
    return message.sid

