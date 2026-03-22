import requests
import time
import winsound  # Built into Windows — no install needed

# ─────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────
BACKEND_URL  = "http://127.0.0.1:5001/data"
NTFY_CHANNEL = "revision-alerts"
SUSTAIN_SECS = 3

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
        # Single soft beep — all clear
        winsound.Beep(1000, 600)
        send_phone_notification("LOW", risk_score)
        print("=" * 50)
        print("✅  ALL CLEAR")
        print(f"    Risk   : {risk_percent}%")
        print(f"    Notify : Coordinators only")
        print("=" * 50)

    elif alert_level == "MEDIUM":
        # 6 fast beeps — caution
        for _ in range(6):
            winsound.Beep(1500, 150)
        send_phone_notification("MEDIUM", risk_score)
        print("=" * 50)
        print("🟡  CAUTION ALERT")
        print(f"    Risk   : {risk_percent}%")
        print(f"    Notify : Volunteers + Coordinators")
        print(f"    Action : Begin gentle dispersal")
        print("=" * 50)

    elif alert_level == "HIGH":
        # Fast alternating siren — emergency
        for _ in range(10):
            winsound.Beep(2000, 150)
            winsound.Beep(800,  150)
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
            elif level_start is not None:
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

        time.sleep(2)


if __name__ == "__main__":
    run()