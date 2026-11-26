from flask import Flask, jsonify, request
import json
import math
import ssl
import threading
import time
import urllib.request

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    requests = None

import phyphox
from phyphox import get_data as get_phyphox_data
import risk_engine

app = Flask(__name__)

CAMERA_COUNTS_URL = "https://127.0.0.1:5000/api/counts"
CAMERA_POLL_INTERVAL = 1.0
CAMERA_TIMEOUT = 1.0
MOTION_POLL_INTERVAL = 0.2

LEVEL_TO_ALERT = {
    "Green": "LOW",
    "Yellow": "MEDIUM",
    "Red": "HIGH"
}

_devices_lock = threading.Lock()
_camera_lock = threading.Lock()
_motion_lock = threading.Lock()
_worker_lock = threading.Lock()
_profile_lock = threading.Lock()

EVENT_PROFILES = risk_engine.load_profiles()
active_profile_name = "default"

latest_device_count = 0  # Global variable to store device count from C# program

# Cached camera count state updated by background thread
current_crowd_count = 0
camera_last_updated = None
camera_stale = True

# Cached Phyphox motion state updated by background thread
prev_mag = 0
history = []
latest_norm_instability = 0.0
motion_last_updated = None
motion_stale = True

_stop_event = threading.Event()
_camera_thread = None
_motion_thread = None
_camera_session = requests.Session() if requests is not None else None


# 🔹 Step 1: Magnitude
def magnitude(x, y, z):
    return math.sqrt(x * x + y * y + z * z)


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


def get_active_profile():
    """Return (profile_name, profile_dict) in a thread-safe manner."""
    with _profile_lock:
        name = active_profile_name
        profile = EVENT_PROFILES.get(name) or EVENT_PROFILES.get("default", {})
        return name, profile


def set_active_profile(name):
    """Set active profile by name; raises ValueError if not recognized."""
    global active_profile_name
    with _profile_lock:
        if name not in EVENT_PROFILES:
            raise ValueError(f"Unknown profile: {name}")
        active_profile_name = name
        return name, EVENT_PROFILES[name]


def calculate_risk_and_advice(crowd_count, device_count, norm_instability, profile=None):
    """Calculate risk (0..1), alert level (LOW/MEDIUM/HIGH), and advice text via risk_engine."""
    if profile is None:
        _, profile = get_active_profile()

    V = max(0.0, min(1.0, crowd_count / 100.0))
    W = max(0.0, min(1.0, device_count / 50.0))
    M = max(0.0, min(1.0, norm_instability))

    R, level = risk_engine.risk(V, W, M, profile)
    risk_val = round(R / 100.0, 2)
    alert = LEVEL_TO_ALERT.get(level, "LOW")
    advice_text = risk_engine.advice(profile, level)
    return risk_val, alert, advice_text


# 🔹 Risk formula delegated to risk_engine for compatibility
def calculate_risk(crowd_count, device_count, norm_instability, profile=None):
    risk_val, alert, _ = calculate_risk_and_advice(
        crowd_count, device_count, norm_instability, profile=profile
    )
    return risk_val, alert


def _fetch_camera_counts():
    """Fetch camera JSON payload from the local edge vision service."""
    if requests is not None:
        session = _camera_session or requests
        cam_res = session.get(CAMERA_COUNTS_URL, verify=False, timeout=CAMERA_TIMEOUT)
        cam_res.raise_for_status()
        return cam_res.json()

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(CAMERA_COUNTS_URL, timeout=CAMERA_TIMEOUT, context=ctx) as res:
        return json.loads(res.read().decode("utf-8"))


def _read_phyphox_sample():
    """Read (x, y, z) from Phyphox, raising if Phyphox is offline."""
    # Respect tests or callers that monkeypatch backend.get_phyphox_data directly.
    if get_phyphox_data is not phyphox.get_data:
        return get_phyphox_data()
    return phyphox.fetch_data()


def refresh_camera_count():
    """Poll the camera service once and update the cached count and timestamp."""
    global current_crowd_count, camera_last_updated, camera_stale
    try:
        payload = _fetch_camera_counts()
        crowd_count = payload.get("total", 0)
        now = time.time()
        with _camera_lock:
            current_crowd_count = crowd_count
            camera_last_updated = now
            camera_stale = False
        return crowd_count
    except Exception:
        with _camera_lock:
            camera_stale = True
            return current_crowd_count


def refresh_motion_state():
    """Poll Phyphox once and update smoothed motion instability, or mark stale if offline."""
    global latest_norm_instability, motion_last_updated, motion_stale
    try:
        sample = _read_phyphox_sample()
        if sample is None:
            raise ValueError("Phyphox returned no sample")
        x, y, z = sample
        with _motion_lock:
            norm_instability = compute_motion_risk(x, y, z)
            latest_norm_instability = norm_instability
            motion_last_updated = time.time()
            motion_stale = False
        return norm_instability
    except Exception:
        with _motion_lock:
            motion_stale = True
            return latest_norm_instability


def _poll_loop(fn, interval, stop_event):
    """Run a polling callback at a fixed interval until stop_event is set."""
    while not stop_event.is_set():
        fn()
        if stop_event.wait(interval):
            break


def start_background_workers():
    """Start daemon threads for camera count and Phyphox motion polling if not running."""
    global _camera_thread, _motion_thread
    with _worker_lock:
        if _stop_event.is_set():
            _stop_event.clear()

        if _camera_thread is None or not _camera_thread.is_alive():
            _camera_thread = threading.Thread(
                target=_poll_loop,
                args=(refresh_camera_count, CAMERA_POLL_INTERVAL, _stop_event),
                name="camera-poller",
                daemon=True,
            )
            _camera_thread.start()

        if _motion_thread is None or not _motion_thread.is_alive():
            _motion_thread = threading.Thread(
                target=_poll_loop,
                args=(refresh_motion_state, MOTION_POLL_INTERVAL, _stop_event),
                name="motion-poller",
                daemon=True,
            )
            _motion_thread.start()


def stop_background_workers(timeout=2.0):
    """Signal background polling threads to stop and wait briefly for exit."""
    global _camera_thread, _motion_thread
    with _worker_lock:
        _stop_event.set()
        cam_t = _camera_thread
        mot_t = _motion_thread
        _camera_thread = None
        _motion_thread = None

    if cam_t is not None and cam_t.is_alive():
        cam_t.join(timeout=timeout)
    if mot_t is not None and mot_t.is_alive():
        mot_t.join(timeout=timeout)


@app.before_request
def _ensure_workers():
    if not app.config.get("TESTING", False):
        start_background_workers()


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
        received = data.get("device_count", 0)
        with _devices_lock:
            latest_device_count = received
        print(f"Updated device count: {received}")
        return jsonify({"status": "ok", "received_device_count": received})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/set_event', methods=['POST'])
def set_event():
    """
    Endpoint to switch active event profile.
    Expected JSON: {"profile": "<profile_name>"} or {"event": "<profile_name>"}
    """
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("profile") or data.get("event")
        if not name:
            name = request.form.get("profile") or request.form.get("event")
        if not name and request.data:
            name = request.get_data(as_text=True).strip()

        if not name:
            return jsonify({"status": "error", "message": "Missing profile name"}), 400

        if name not in EVENT_PROFILES:
            return jsonify({
                "status": "error",
                "message": f"Unknown profile: {name}",
                "valid_profiles": list(EVENT_PROFILES.keys())
            }), 400

        set_active_profile(name)
        profile = EVENT_PROFILES[name]
        return jsonify({
            "status": "ok",
            "active_profile": name,
            "label": profile.get("label", name)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/data')
def get_data():
    """
    Returns data for Streamlit frontend
    Accepts area parameter from frontend location selector
    Uses device_count from C# Bluetooth monitor and cached camera/motion state
    """
    area = float(request.args.get('area', 200))

    with _devices_lock:
        device_count = latest_device_count

    with _camera_lock:
        crowd_count = current_crowd_count
        cam_updated_at = camera_last_updated
        cam_is_stale = camera_stale

    with _motion_lock:
        norm_instability = latest_norm_instability
        mot_updated_at = motion_last_updated
        mot_is_stale = motion_stale

    prof_name, prof_data = get_active_profile()

    crowd_density = crowd_count / area if area > 0 else 0

    risk, alert, advice_text = calculate_risk_and_advice(
        crowd_count, device_count, norm_instability, profile=prof_data
    )

    # Scale instability back up to 10 for the UI display
    instability = norm_instability * 10

    return jsonify({
        "crowd_count": crowd_count,
        "device_count": device_count,
        "crowd_density": round(crowd_density, 2),
        "area": area,
        "instability": round(instability, 2),
        "risk": round(risk, 2),
        "alert": alert,
        "profile": prof_name,
        "profile_label": prof_data.get("label", prof_name),
        "advice": advice_text,
        "camera_updated_at": cam_updated_at,
        "camera_stale": cam_is_stale,
        "motion_updated_at": mot_updated_at,
        "motion_stale": mot_is_stale,
    })


# 🚨 VERY IMPORTANT
if __name__ == '__main__':
    print("Starting Flask server on http://127.0.0.1:5001")
    print("C# program should POST to: http://127.0.0.1:5001/update_devices")
    start_background_workers()
    app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False)