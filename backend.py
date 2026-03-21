from flask import Flask, jsonify, request
import random

app = Flask(__name__)

latest_device_count = 0  # Global variable to store device count from C# program

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
    global latest_device_count
    
    # Get area from query parameter (default to 200 m² if not provided)
    area = float(request.args.get('area', 200))
    
    # Use device count from C# program (updated via /update_devices endpoint)
    device_count = latest_device_count
    
    # Generate crowd count based on location
    crowd_count = random.randint(20, 100)
    
    # Calculate crowd density per m²
    if area > 0:
        crowd_density = crowd_count / area
    else:
        crowd_density = 0
    
    # Generate random instability
    instability = random.uniform(1, 8)

    risk = 0.5*(crowd_count/100) + 0.3*(instability/10) + 0.2*(device_count/50)

    if risk > 0.7:
        alert = "HIGH"
    elif risk > 0.4:
        alert = "MEDIUM"
    else:
        alert = "LOW"

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