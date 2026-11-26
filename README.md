# INDRA-NET (Re-Vision) — Crowd Safety & Risk Monitoring System

INDRA-NET is a multi-sensor crowd monitoring prototype built for Windows. It fuses **edge computer vision** (phone cameras running through YOLOv8), **Bluetooth device density** (a Windows C# `DeviceWatcher`), and **phone accelerometer motion data** (via the Phyphox app) into a central Flask backend, then surfaces risk scores on a **Streamlit command dashboard** and triggers **audio/push (`ntfy.sh`) and SMS (`Twilio`) alerts**.

---

## How the Parts Connect

```text
+--------------------------+       HTTPS POST /upload (JPEG @ 2 FPS)       +-----------------------------------+
| Phone Browser(s)         | --------------------------------------------> | camera.py (Flask HTTPS :5000)     |
| templates/phone.html     |                                               | - Runs YOLOv8n person detection   |
+--------------------------+                                               | - Serves CCTV UI (/) & MJPEG feed |
                                                                           +-----------------+-----------------+
                                                                                             |
                                                                      GET https://127.0.0.1:5000/api/counts
                                                                                             |
+--------------------------+       HTTP POST /update_devices               +-----------------v-----------------+
| BluetoothWatcher         | --------------------------------------------> | backend.py (Flask HTTP :5001)     |
| C# (.NET 8 WinRT AQS)    |       {"device_count": N}                     | - Aggregates crowd, devices,      |
+--------------------------+                                               |   and motion instability          |
                                                                           | - Computes risk (0..1) & alert    |
+--------------------------+       HTTP GET /get?accX&accY&accZ            |   (LOW / MEDIUM / HIGH)           |
| Phyphox App on Phone     | <-------------------------------------------- +-----------------+-----------------+
| (Port 8080 Remote Access)|       (called via phyphox.py on /data)                          |
+--------------------------+                                                                 |
                                                    +--------------------+-------------------+--------------------+
                                                    |                    |                                        |
                                        GET /data?area=...       GET /data                                GET /data
                                                    |                    |                                        |
                                                    v                    v                                        v
                                     +--------------------+   +--------------------+                   +--------------------+
                                     | main.py            |   | alarm.py           |                   | notification.py    |
                                     | Streamlit UI :8501 |   | Plays alert.mp3 &  |                   | Sends SMS via      |
                                     |                    |   | posts to ntfy.sh   |                   | Twilio REST API    |
                                     +--------------------+   +--------------------+                   +--------------------+
```

### Data & Risk Pipeline
1. **Camera Edge Vision (`camera.py` + `templates/phone.html` + `templates/dashboard.html`)**:
   - Phones open `https://<laptop-ip>:5000/phone`, capture camera frames on an HTML `<canvas>` every `500 ms` (2 FPS), and `POST` them to `/upload` with a `Camera-ID` header.
   - `camera.py` runs `yolov8n.pt` (`classes=[0]`, `conf=0.3`) to count people, draws bounding boxes and counts onto each frame, exposes an MJPEG stream at `/video/<cam_id>`, and reports active camera counts at `/api/counts` (30-second inactivity timeout).
2. **Bluetooth Watcher (`pune_hackathon/BluetoothWatcher/Program.cs`)**:
   - Uses the Windows `DeviceInformation` / `DeviceWatcher` API (`Windows.Devices.Enumeration`) to count Bluetooth Association Endpoints and sends `{"device_count": count}` via `POST` to `http://127.0.0.1:5001/update_devices` on startup and whenever devices are added or removed.
3. **Phyphox Motion Data (`phyphox.py`)**:
   - Queries the Phyphox mobile app's HTTP Remote Access endpoint (`http://10.111.160.115:8080/get?accX&accY&accZ`) to read the latest `accX`, `accY`, `accZ` accelerometer values whenever `backend.py` handles `GET /data`.
4. **Central Backend (`backend.py`)**:
   - Combines `crowd_count` (from `camera.py`), `device_count` (from `BluetoothWatcher`), and `norm_instability` (10-sample moving average of acceleration magnitude delta, normalized by `/ 5` and capped at `1`):
     - Base risk: `0.5 * (crowd_count / 100) + 0.3 * (device_count / 50) + 0.2 * norm_instability`
     - Spike boosts: `+0.3` if `norm_instability > 0.4`, `+0.6` if `norm_instability > 0.7`, clamped to `[0, 1]`.
     - Alert thresholds: `HIGH` (`risk > 0.7`), `MEDIUM` (`risk > 0.4`), otherwise `LOW`.
5. **Dashboard & Alert Consumers (`main.py`, `alarm.py`, `notification.py`)**:
   - `main.py`: Streamlit UI polling `http://127.0.0.1:5001/data?area=<50|200|500>` every `0.1s`.
   - `alarm.py`: Polls `/data` every `0.01s`; sends push notifications to `https://ntfy.sh/revision-alerts` on `MEDIUM` and `HIGH`, and plays `alert.mp3` via `pygame.mixer` on `HIGH`.
   - `notification.py`: Polls `/data` every `0.1s`; sends an SMS via Twilio when `alert` transitions from `LOW` to `MEDIUM` or `HIGH`.

---

## What Each File Does

| File | Purpose |
| :--- | :--- |
| `camera.py` | Flask HTTPS server on port `5000` (`ssl_context='adhoc'`). Loads `yolov8n.pt`, processes uploaded phone frames for person detection, serves MJPEG feeds (`/video/<cam_id>`), exposes `/api/counts`, and renders `dashboard.html` and `phone.html`. |
| `templates/phone.html` | Mobile web client served at `/phone`. Uses `getUserMedia` (rear camera) and an HTML canvas to stream JPEG frames to `/upload` at 2 FPS. |
| `templates/dashboard.html` | CCTV web view served at `/`. Polls `/api/counts` every second and displays live MJPEG feeds and per-camera/total person counts. |
| `yolov8n.pt` | Pre-trained YOLOv8 nano PyTorch weights (~6.5 MB) used by `camera.py`. |
| `backend.py` | Core Flask HTTP API on `127.0.0.1:5001`. Accepts Bluetooth counts on `POST /update_devices`, pulls camera counts and Phyphox motion data on `GET /data`, and returns JSON risk/alert metrics. |
| `phyphox.py` | Fetches latest `accX`, `accY`, `accZ` readings from the Phyphox phone app (`get_data()`). Can also be run directly to print sensor readings every second. |
| `main.py` | Streamlit command dashboard (`INDRA-NET`). Displays location selector, sensor layer cards, risk score, threat level, and live metrics. |
| `alarm.py` | Background alert daemon. Polls `backend.py`, plays `alert.mp3` via `pygame` on `HIGH` alert, and sends push notifications via `ntfy.sh`. |
| `alert.mp3` | Siren audio file played by `alarm.py` during `HIGH` alerts. |
| `notification.py` | Background SMS daemon using the Twilio REST client. Sends a warning SMS when threat level rises out of `LOW`. |
| `requirements.txt` | Core Python dependencies (`flask`, `requests`, `streamlit`, `opencv-python`, `numpy`, `ultralytics`). *Missing several packages—see below.* |
| `.gitignore` | Git ignore rules for build outputs, Visual Studio files, and Python cache (contains stray shell `cat` lines—see below). |
| `pune_hackathon/BluetoothWatcher/Program.cs` | C# Windows console app that watches Bluetooth Association Endpoints using `Windows.Devices.Enumeration` and posts device counts to `backend.py`. |
| `pune_hackathon/BluetoothWatcher/BluetoothWatcher.csproj` | .NET project targeting `net8.0-windows10.0.19041.0` (`Exe`). |
| `pune_hackathon/BluetoothWatcher/BluetoothWatcher.sln` | Visual Studio 2022 solution file for `BluetoothWatcher.csproj`. |
| `pune_hackathon/pune_hackathon.sln` | Top-level Visual Studio 2022 solution file pointing to `BluetoothWatcher/BluetoothWatcher.csproj`. |

---

## What to Install

### 1. System / Runtime Prerequisites (Windows)
- **Windows 10 (build 19041+) or Windows 11** (required by `net8.0-windows10.0.19041.0` and `Windows.Devices.Enumeration`).
- **Python 3.10+** (recommended for `ultralytics`, `streamlit`, and `pygame` compatibility).
- **.NET 8.0 SDK** (with Windows Desktop/WinRT targeting support for `net8.0-windows10.0.19041.0`).
- **Mobile Apps (on phone(s) on the same Wi-Fi network as the Windows PC)**:
  - A mobile browser (Chrome/Safari) for `templates/phone.html`.
  - **Phyphox** app (Android/iOS) with *Acceleration without g* / *Accelerometer* + **Allow remote access** enabled.
  - **ntfy** app (optional, Android/iOS) subscribed to `revision-alerts` to receive push notifications from `alarm.py`.
- **Twilio Account** (optional, only needed if running `notification.py` for SMS).

### 2. Python Packages
`requirements.txt` omits packages required by `camera.py` (`cryptography` for Flask's `ssl_context='adhoc'`), `alarm.py` (`pygame`), and `notification.py` (`twilio`). Install all of them in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install cryptography pygame twilio
```

---

## Exact Steps to Run on Windows

> **Important:** Run all Python commands from the repository root (`indra_net\`) because `camera.py` loads `yolov8n.pt` and `alarm.py` loads `alert.mp3` using relative paths.

### Step 1: Update Hard-Coded Phone IP & Credentials (Before Running)
1. **Phyphox IP (`phyphox.py`)**: Open Phyphox on your phone, start an Accelerometer experiment, enable **Allow remote access**, and replace `10.111.160.115:8080` in `phyphox.py` (lines 4 and 8) with the URL shown in the Phyphox app.
2. **Twilio Credentials (`notification.py`, optional)**: Set environment variables in the terminal where you will run `notification.py`, and update `TWILIO_FROM_NUMBER` / `TO_NUMBER` in `notification.py`:
   ```powershell
   $env:TWILIO_ACCOUNT_SID="your_account_sid"
   $env:TWILIO_AUTH_TOKEN="your_auth_token"
   ```
3. **Firewall**: Ensure Windows Defender Firewall allows inbound TCP on port `5000` on your local/private Wi-Fi network so phones can reach `camera.py`.

### Step 2: Start Each Component (Separate PowerShell Terminals)

**Terminal 1 — Edge Vision Server (`camera.py`)**
```powershell
cd C:\Users\Hp\Desktop\Projects\indra_net
.\.venv\Scripts\Activate.ps1
python camera.py
```
- Starts HTTPS server on `0.0.0.0:5000`.
- Find your Windows PC's actual LAN IPv4 address using `ipconfig` (do **not** rely on the hard-coded IP printed by `camera.py`).

**Terminal 2 — Central Backend (`backend.py`)**
```powershell
cd C:\Users\Hp\Desktop\Projects\indra_net
.\.venv\Scripts\Activate.ps1
python backend.py
```
- Starts HTTP API at `http://127.0.0.1:5001`.

**Terminal 3 — Windows Bluetooth Watcher (`BluetoothWatcher`)**
```powershell
cd C:\Users\Hp\Desktop\Projects\indra_net\pune_hackathon\BluetoothWatcher
dotnet run
```
- Enumerates paired/present Bluetooth endpoints and posts updates to `http://127.0.0.1:5001/update_devices`. Press `Enter` in this terminal to stop scanning.

**Terminal 4 — Streamlit Command Dashboard (`main.py`)**
```powershell
cd C:\Users\Hp\Desktop\Projects\indra_net
.\.venv\Scripts\Activate.ps1
streamlit run main.py
```
- Opens in your browser (typically `http://localhost:8501`).

**Terminal 5 — Alarm Manager (`alarm.py`, optional)**
```powershell
cd C:\Users\Hp\Desktop\Projects\indra_net
.\.venv\Scripts\Activate.ps1
python alarm.py
```

**Terminal 6 — SMS Service (`notification.py`, optional)**
```powershell
cd C:\Users\Hp\Desktop\Projects\indra_net
.\.venv\Scripts\Activate.ps1
python notification.py
```

### Step 3: Connect Phone Camera(s) & CCTV View
1. On your phone (same Wi-Fi as the PC), open `https://<YOUR-PC-LAN-IP>:5000/phone`.
2. Accept the browser warning for the self-signed (`adhoc`) HTTPS certificate (HTTPS is required by mobile browsers for `getUserMedia` camera access).
3. Enter a camera name and tap **Start Streaming CCTV**.
4. Open `https://localhost:5000/` (accepting the certificate warning) to view the live annotated CCTV feeds.

---

## Broken, Missing, or Hard-Coded Items

### Hard-Coded IP Addresses, Ports, Paths, and Secrets
- **Phone / LAN IPs**:
  - `phyphox.py` (lines 4, 8): Hard-coded `http://10.111.160.115:8080/get?accX&accY&accZ`. Also defines `URL` on line 4 but hard-codes the URL string again inside `get_data()` on line 8 instead of referencing `URL`.
  - `camera.py` (lines 129–130): Hard-codes `https://10.111.160.50:5000` and `https://10.111.160.50:5000/phone` in startup console logs, even though `ip = get_ip()` is computed on line 126 and never used.
- **Backend / Service URLs & Ports**:
  - `camera.py` (line 134): Port `5000` (`0.0.0.0:5000`, HTTPS adhoc).
  - `backend.py` (lines 112, 147–149): Hard-coded `https://127.0.0.1:5000/api/counts` and binds to `http://127.0.0.1:5001`.
  - `main.py` (lines 205, 319): Hard-coded `http://127.0.0.1:5001/data?area={selected_area}`.
  - `alarm.py` (lines 6, 7, 51): Hard-coded `BACKEND_URL = "http://127.0.0.1:5001/data"` and `NTFY_CHANNEL = "revision-alerts"`.
  - `notification.py` (line 16): Hard-coded `BACKEND_URL = "http://127.0.0.1:5001/data"`.
  - `pune_hackathon/BluetoothWatcher/Program.cs` (line 13): Hard-coded `flaskUrl = "http://127.0.0.1:5001/update_devices"`.
- **Phone Numbers & Credentials**:
  - `notification.py` (lines 11–14): Hard-coded `TWILIO_FROM_NUMBER = "+918217620677"` and `TO_NUMBER = "+919963811127"`, plus placeholder defaults `"YOUR_TWILIO_ACCOUNT_SID_HERE"` and `"YOUR_TWILIO_AUTH_TOKEN_HERE"`.
- **Relative File Paths**:
  - `camera.py` (line 11): `"yolov8n.pt"`.
  - `alarm.py` (line 100): `"alert.mp3"`.

### Missing Dependencies & Assets
- `requirements.txt` is missing:
  - `cryptography` (required by Flask/Werkzeug for `ssl_context='adhoc'` in `camera.py`).
  - `pygame` (required by `alarm.py` to play `alert.mp3`; without it, `alarm.py` catches `ImportError` and plays no sound).
  - `twilio` (required by `notification.py`; running `notification.py` without it fails immediately on import).
- No root `README.md` or `.env.example` existed prior to this file.

### Broken / Buggy Behavior
1. **Malformed `.gitignore`**: Line 1 contains `cat > .gitignore <<EOF` and line 40 contains `EOF`, meaning shell heredoc commands were pasted literally into `.gitignore`.
2. **`backend.py` 50 ms timeout calling `camera.py` (`timeout=0.05`, line 112)**: Performing a fresh HTTPS TLS handshake on `https://127.0.0.1:5000/api/counts` within 50 ms frequently times out and silently falls back to the stale `current_crowd_count` (`0` at startup).
3. **Global Phyphox motion state corrupted by concurrent polling (`backend.py`)**:
   - `compute_motion_risk` updates global `prev_mag` and `history` (without thread locks) on *every* `GET /data` request.
   - `main.py` (`~0.1s` sleep), `alarm.py` (`0.01s` sleep — up to 100 requests/sec), and `notification.py` (`0.1s` sleep) all poll `/data` simultaneously, causing the 10-sample moving average to be flushed ~120 times per second against a much slower sensor buffer and skewing `variation` toward `0`.
   - When Phyphox is offline, every `/data` call blocks for `phyphox.py`'s `2s` timeout, stalling the dashboard and alert pollers.
4. **Inverted / Mismatched Motion Metric (`backend.py` vs `main.py`)**:
   - `backend.py` returns `"instability": round(norm_instability * 10, 2)` (`0`–`10` scale, where higher = more unstable).
   - `main.py` (line 234) multiplies that by `10` (`0`–`100`) and displays it as **`Stability Score`** (higher instability is shown as higher stability), while line 282 displays the `0`–`10` value as **`MOTION INDEX`**.
5. **`area` / `crowd_density` unused in risk calculation (`backend.py`)**: `GET /data` accepts `?area=...` and computes `crowd_density`, but `calculate_risk()` ignores `crowd_density` and uses raw `crowd_count / 100`. `main.py` also never renders `crowd_density`.
6. **Stream generator infinite loop on timed-out cameras (`camera.py`, lines 74–88)**: `/video/<cam_id>` loops forever with `time.sleep(0.1)` once `api_counts()` deletes a timed-out `cam_id` from `cameras`, because the `break` is only inside `if cam_id in cameras:`. Also sends duplicate frames every `0.1s` even when the phone only uploads at `0.5s` intervals.
7. **Dead code & merge-conflict leftovers (`camera.py`)**:
   - Line 30 defaults `cam_id` to `"Unknown"`, making `if not cam_id:` on line 32 unreachable.
   - Lines 135–137 contain commented git merge markers (`#=======`, `#python app.py`, `#>>>>>>> ...`).
8. **Alarm blocking & stale error message (`alarm.py`)**:
   - Line 160 prints `"start flask_backend.py first"` instead of `backend.py`.
   - Lines 103–105 block in a `while pygame.mixer.music.get_busy()` loop *before* calling `send_phone_notification("HIGH", risk_score)` on line 109, delaying push notifications until the audio finishes.
   - `SUSTAIN_SECS = 0` disables sustained-alert debouncing; `"LOW"` branch in `send_phone_notification` is dead code.
9. **SMS trigger gaps & silent error swallowing (`notification.py`)**:
   - Only fires on `LOW -> MEDIUM` or `LOW -> HIGH` (line 59); starting while already `MEDIUM`/`HIGH` or escalating `MEDIUM -> HIGH` sends no SMS.
   - Line 70–72 catches all non-`ConnectionError` exceptions with `pass`.
10. **BluetoothWatcher thread-safety & null-cast risk (`Program.cs`)**:
    - Line 130 casts `d.Properties["System.Devices.Aep.IsConnected"]` directly to `(bool)` without checking for `null`, which can throw `NullReferenceException` in `watcher.Updated`.
    - `seenDevices` and `deviceCount` are mutated in `Added` and `Removed` event handlers without synchronization (`lock`).
    - `aqsFilter` enumerates all Windows Bluetooth Association Endpoints (including paired/cached devices), not strictly active nearby phones.
11. **Duplicate Visual Studio solutions**: Both `pune_hackathon/pune_hackathon.sln` and `pune_hackathon/BluetoothWatcher/BluetoothWatcher.sln` exist for the single `BluetoothWatcher.csproj` project.
12. **Unused imports**: `random` in `backend.py` (line 2) and `math` in `main.py` (line 5).
