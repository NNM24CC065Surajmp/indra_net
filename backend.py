from flask import Flask, jsonify, request
import random
import math
from phyphox import get_data as get_phyphox_data

app = Flask(__name__)

latest_device_count = 0  # Global variable to store device count from C# program
current_crowd_count = 0  # Track actual camera detections (no fake data)

# 🔁 Global variables for Phyphox data
prev_mag = 0
history = []

# 🔹 Step 1: Magnitude
def magnitude(x, y, z):
    return math.sqrt(x*x + y*y + z*z)

# 🔹 Step 2: Variation (change over time)
def get_variation(x, y, z):
    global prev_mag
    curr_mag = magnitude(x, y, z)
    variation = abs(curr_mag - prev_mag)
    prev_mag = curr_mag
    return variation

# 🔹 Step 3: Smoothing (moving average)
def get_instability(variation):
    global history
    history.append(variation)

    if len(history) > 10:
        history.pop(0)

    return sum(history) / len(history) if len(history) > 0 else 0

# 🔹 Step 4: Normalize (0 to 1)
def normalize_instability(instability):
    return min(instability / 5, 1)   # adjust 5 based on testing

# 🔹 Final function to call in your backend
def compute_motion_risk(x, y, z):
    variation = get_variation(x, y, z)
    instability_val = get_instability(variation)
    norm_instability = normalize_instability(instability_val)
    return norm_instability

# 🔹 Final risk formula (use inside your /data API)
def calculate_risk(crowd_count, device_count, norm_instability):
    risk = (
        0.5 * (crowd_count / 100) +
        0.3 * (device_count / 50) +
        0.2 * norm_instability
    )

    # Optional spike boost (for demo impact with 1 phone)
    if norm_instability > 0.4:
        risk += 0.3  # Helps push into MEDIUM
    if norm_instability > 0.7:
        risk += 0.6  # Forces directly into HIGH

    # Alert levels
    if risk > 0.7:
        alert = "HIGH"
    elif risk > 0.4:
        alert = "MEDIUM"
    else:
        alert = "LOW"

    return round(min(risk, 1), 2), alert

@app.route('/')
def home():
    return "Backend running!"

@app.route('/update_devices', methods=['POST'])
def update_devices():
    """
    Endpoint for C# program to send Bluetooth device count
    Expected JSON: {"device_count": <number>}
    """
    global latest_device_count
    try:
        data = request.json
        latest_device_count = data.get("device_count", 0)
        print(f"Updated device count: {latest_device_count}")
        return jsonify({"status": "ok", "received_device_count": latest_device_count})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/data')
def get_data():
    """
    Returns data for Streamlit frontend
    Accepts area parameter from frontend location selector
    Uses device_count from C# Bluetooth monitor
    """
    global latest_device_count, current_crowd_count
    
    # Get area from query parameter (default to 200 m² if not provided)
    area = float(request.args.get('area', 200))
    
    # Use device count from C# program (updated via /update_devices endpoint)
    device_count = latest_device_count
    
    # Fetch real crowd count from camera.py edge vision pipeline
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        cam_res = requests.get("https://127.0.0.1:5000/api/counts", verify=False, timeout=0.05)
        crowd_count = cam_res.json().get("total", 0)
        current_crowd_count = crowd_count # Synchronize state
    except Exception as e:
        # No random simulation. Just return the last known true count or 0.
        crowd_count = current_crowd_count
    
    # Calculate crowd density per m²
    if area > 0:
        crowd_density = crowd_count / area
    else:
        crowd_density = 0

    # --- PHYPHOX INTEGRATION ---
    x, y, z = get_phyphox_data()
    norm_instability = compute_motion_risk(x, y, z)
    
    risk, alert = calculate_risk(crowd_count, device_count, norm_instability)
    
    # Scale instability back up to 10 for the UI display
    instability = norm_instability * 10
    # ----------------------------------------------------------

    return jsonify({
        "crowd_count": crowd_count,
        "device_count": device_count,
        "crowd_density": round(crowd_density, 2),
        "area": area,
        "instability": round(instability, 2),
        "risk": round(risk, 2),
        "alert": alert
    })

# 🚨 VERY IMPORTANT
if __name__ == '__main__':
    print("Starting Flask server on http://127.0.0.1:5001")
    print("C# program should POST to: http://127.0.0.1:5001/update_devices")
    app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False)