import requests
import time
# ─────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────
BACKEND_URL  = "http://127.0.0.1:5001/data"
NTFY_CHANNEL = "revision-alerts"
SUSTAIN_SECS = 0

# ─────────────────────────────────────
# STATE
# ─────────────────────────────────────
last_alerted  = None
level_start   = None
current_level = None


# ─────────────────────────────────────
# PHONE NOTIFICATION — ntfy.sh
# No account needed. Free forever.
# Police setup:
#   1. Install "ntfy" app on phone
#   2. Subscribe to: revision-alerts
#   3. Done — alerts arrive instantly
# ─────────────────────────────────────
def send_phone_notification(alert_level, risk_score):
    risk_percent = round(risk_score * 100)

    if alert_level == "HIGH":
        title    = "EMERGENCY — Re-Vision"
        message  = (f"CRITICAL risk: {risk_percent}%. "
                    f"Deploy crowd control NOW.")
        priority = "urgent"
        tags     = "rotating_light"

    elif alert_level == "MEDIUM":
        title    = "CAUTION — Re-Vision"
        message  = (f"Risk rising: {risk_percent}%. "
                    f"Begin crowd dispersal.")
        priority = "high"
        tags     = "warning"

    else:  # LOW
        title    = "All Clear — Re-Vision"
        message  = (f"Crowd is safe. Risk: {risk_percent}%.")
        priority = "default"
        tags     = "white_check_mark"

    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_CHANNEL}",
            data    = message.encode('utf-8'),
            headers = {
                "Title":    title,
                "Priority": priority,
                "Tags":     tags
            },
            timeout = 5
        )
        print(f"   📱 Phone notified: {title}")
    except Exception as e:
        print(f"   ⚠️  Phone notification skipped: {e}")


# ─────────────────────────────────────
# FIRE ALARM
# ─────────────────────────────────────
def fire_alarm(alert_level, risk_score):
    risk_percent = round(risk_score * 100)

    if alert_level == "LOW":
        # Do nothing when threat level is low (no sound or notifications)
        print("=" * 50)
        print("✅  ALL CLEAR")
        print(f"    Risk   : {risk_percent}%")
        print(f"    Status : Threat level is low, no action taken")
        print("=" * 50)

    elif alert_level == "MEDIUM":
        # Dispersal CAUTION. (No buzzer, audio reserved for alert.mp3 in HIGH)
        send_phone_notification("MEDIUM", risk_score)
        print("=" * 50)
        print("🟡  CAUTION ALERT")
        print(f"    Risk   : {risk_percent}%")
        print(f"    Notify : Volunteers + Coordinators")
        print(f"    Action : Begin gentle dispersal")
        print("=" * 50)

    elif alert_level == "HIGH":
        # Play mp3 siren — emergency
        try:
            import pygame
            import os
            
            # Suppress the pygame welcome text
            os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
            
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load("alert.mp3")
            pygame.mixer.music.play()
            # Wait until the MP3 finishes playing so it matches the previous blocking behavior
            while pygame.mixer.music.get_busy():
                import time
                time.sleep(0.1)
        except ImportError:
            # Fallback if pygame is not installed
            print("🔊 Pygame is missing! No audio will play because winsound beeps have been removed.")
        send_phone_notification("HIGH", risk_score)
        print("*" * 50)
        print("🔴  EMERGENCY ALERT")
        print(f"    Risk   : {risk_percent}%")
        print(f"    Notify : Police + Medical + All Staff")
        print(f"    Action : Deploy immediately")
        print("*" * 50)


# ─────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────
def run():
    global last_alerted, level_start, current_level

    print("=" * 50)
    print("  Re-Vision — Alarm Manager")
    print(f"  Backend : {BACKEND_URL}")
    print(f"  Phone   : ntfy.sh/{NTFY_CHANNEL}")
    print(f"  Sustain : {SUSTAIN_SECS} seconds")
    print("=" * 50)

    while True:
        try:
            response    = requests.get(BACKEND_URL, timeout=3)
            data        = response.json()
            alert_level = data.get("alert", "LOW")
            risk_score  = data.get("risk",  0)

            print(f"📊  {alert_level:6} | "
                  f"Risk: {round(risk_score * 100):3}% | "
                  f"Crowd: {data.get('crowd_count', 0):3} | "
                  f"Devices: {data.get('device_count', 0):3}")

            # Level changed — reset timer
            if alert_level != current_level:
                current_level = alert_level
                level_start   = time.time()
                print(f"⏱   → {alert_level} — "
                      f"waiting {SUSTAIN_SECS}s...")

            # Sustained long enough — fire alarm
            if level_start is not None:
                held = time.time() - level_start
                if (held >= SUSTAIN_SECS and
                        alert_level != last_alerted):
                    fire_alarm(alert_level, risk_score)
                    last_alerted = alert_level

        except requests.exceptions.ConnectionError:
            print("❌  Backend not running — "
                  "start flask_backend.py first")
        except Exception as e:
            print(f"❌  Error: {e}")

        time.sleep(0.01)


if __name__ == "__main__":
    run()