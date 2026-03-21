from flask import Flask, jsonify
import random

app = Flask(__name__)

@app.route('/')
def home():
    return "Backend running!"

@app.route('/data')
def get_data():
    crowd_count = random.randint(20, 100)
    device_count = int(crowd_count * random.uniform(0.6, 0.9))
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
        "instability": instability,
        "risk": round(risk, 2),
        "alert": alert
    })

# 🚨 VERY IMPORTANT
if __name__ == '__main__':
    print("Starting Flask server on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)