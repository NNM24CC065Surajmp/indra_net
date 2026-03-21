import cv2
import numpy as np
import time
import socket
from flask import Flask, request, jsonify, Response, render_template
from ultralytics import YOLO

app = Flask(__name__)

# Load YOLOv8 nano model for fast detection
model = YOLO("yolov8n.pt")

# Store camera data: {"Cam1": {"frame": bytes, "count": int, "last_seen": timestamp}}
cameras = {}

TIMEOUT = 30 # seconds before considering a camera disconnected

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/phone')
def phone():
    return render_template('phone.html')

@app.route('/upload', methods=['POST'])
def upload():
    # Receive frame from phone camera
    file = request.files.get("frame")
    cam_id = request.headers.get("Camera-ID", "Unknown")
    
    if not file or not cam_id:
        return jsonify({"error": "Missing frame or Camera-ID"}), 400

    # Read image
    npimg = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    if frame is None:
        return jsonify({"error": "Invalid frame"}), 400

    # Run YOLO detection for people (class 0 parameter)
    results = model(frame, conf=0.3, classes=[0], verbose=False)
    
    person_count = 0
    # Process detections
    if len(results) > 0 and results[0].boxes is not None:
        person_count = len(results[0].boxes) # Total detected people
        for box in results[0].boxes:
            # Get bounding box coordinates
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            
            # Draw green bounding box and label
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"Person {conf:.2f}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Draw the count on the frame itself
    cv2.putText(frame, f"Count: {person_count}", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 4)

    # Encode processed frame as JPEG
    ret, buffer = cv2.imencode('.jpg', frame)
    if ret:
        cameras[cam_id] = {
            "frame": buffer.tobytes(),
            "count": person_count,
            "last_seen": time.time()
        }

    return jsonify({"status": "success", "count": person_count})

@app.route('/video/<cam_id>')
def video(cam_id):
    def generate():
        while True:
            if cam_id in cameras:
                cam_data = cameras[cam_id]
                # Check for timeout
                if time.time() - cam_data["last_seen"] < TIMEOUT:
                    frame = cam_data["frame"]
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                else:
                    # Disconnect feed
                    break
            time.sleep(0.1)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/counts')
def api_counts():
    active_cams = {}
    total_count = 0
    now = time.time()
    
    # Cleanup disconnected cameras
    cams_to_remove = []
    
    for cam_id, data in cameras.items():
        if now - data["last_seen"] < TIMEOUT:
            active_cams[cam_id] = data["count"]
            total_count += data["count"]
        else:
            cams_to_remove.append(cam_id)
            
    for cam_id in cams_to_remove:
        del cameras[cam_id]
        
    return jsonify({
        "cameras": active_cams,
        "total": total_count
    })

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

if __name__ == '__main__':
    ip = get_ip()
    print("="*60)
    print("🚨 CROWD SAFETY CCTV SYSTEM STARTED 🚨")
    print(f"-> 💻 Laptop CCTV Dashboard: http://localhost:5000  (or https://10.111.160.50:5000)")
    print(f"-> 📱 Connect Phones via:    https://10.111.160.50:5000/phone")
    print("="*60)
    
    # Run the Flask app on all interfaces inside home network with adhoc SSL
    app.run(host="0.0.0.0", port=5000, ssl_context='adhoc')
#=======
#python app.py
#>>>>>>> 1f2743c6f8e37a359d54238a96d7bcf0bb1cb3d5