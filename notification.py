import os
import time
import requests
from twilio.rest import Client

# ─────────────────────────────────────
# TWILIO CONFIGURATION
# ─────────────────────────────────────
# ⚠️ Replace these placeholders with your actual Twilio credentials
# You can find them at https://console.twilio.com/
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', "YOUR_TWILIO_ACCOUNT_SID_HERE")
TWILIO_AUTH_TOKEN  = os.environ.get('TWILIO_AUTH_TOKEN', "YOUR_TWILIO_AUTH_TOKEN_HERE")
TWILIO_FROM_NUMBER = "+918217620677"
TO_NUMBER          = "+919963811127"

BACKEND_URL = "http://127.0.0.1:5001/data"

def send_stampede_warning_sms(risk_score):
    """Sends an SMS warning about potential stampede."""
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Format the risk score as a percentage
        risk_percent = round(risk_score * 100)
        message_body = f"URGENT: Possibility of a stampede! Current risk score is {risk_percent}%."
        
        print(f"📡 Sending SMS to {TO_NUMBER}...")
        message = client.messages.create(
            body=message_body,
            from_=TWILIO_FROM_NUMBER,
            to=TO_NUMBER
        )
        print(f"✅ SMS sent successfully! Message SID: {message.sid}")
        
    except Exception as e:
        print(f"❌ Failed to send SMS: {e}")
        print("💡 Hint: Did you replace YOUR_TWILIO_ACCOUNT_SID_HERE and YOUR_TWILIO_AUTH_TOKEN_HERE with your real credentials?")

def run():
    print("=" * 50)
    print("  Re-Vision — SMS Notification Service")
    print(f"  Backend URL : {BACKEND_URL}")
    print(f"  Twilio From : {TWILIO_FROM_NUMBER}")
    print(f"  Twilio To   : {TO_NUMBER}")
    print("=" * 50)

    # We start with assuming the level is LOW (green)
    current_level = "LOW"
    
    while True:
        try:
            response = requests.get(BACKEND_URL, timeout=3)
            data = response.json()
            
            alert_level = data.get("alert", "LOW")
            risk_score  = data.get("risk", 0)
            
            # Check if it crossed the green threshold (LOW -> MEDIUM or HIGH)
            if current_level == "LOW" and alert_level in ["MEDIUM", "HIGH"]:
                print(f"\n⚠️ THRESHOLD CROSSED! Alert Level is now {alert_level}.")
                send_stampede_warning_sms(risk_score)
                
            # Keep track of the current level to detect future changes
            # This ensures we don't spam SMS while the threat stays HIGH
            current_level = alert_level
            
        except requests.exceptions.ConnectionError:
            print("❌ Backend offline. Retrying...")
            time.sleep(2)
        except Exception as e:
            # Ignore timeouts or normal connection drops
            pass
            
        # Poll 10 times a second like alarm.py
        time.sleep(0.1)

if __name__ == "__main__":
    run()
