from datetime import datetime
import time

try:
    import requests
except ImportError:
    requests = None

try:
    import streamlit as st
except ImportError:
    st = None


def compute_stability_score(instability):
    """Convert 0-10 instability into a clamped 0-100 stability score (higher = calmer)."""
    clamped = max(0.0, min(10.0, float(instability or 0)))
    return round(100 - (clamped * 10))


def compute_motion_index(instability):
    """Return clamped 0-10 motion instability index rounded to 2 decimals."""
    clamped = max(0.0, min(10.0, float(instability or 0)))
    return round(clamped, 2)


def render_dashboard():
    st.set_page_config(page_title="INDRA-NET", layout="wide", initial_sidebar_state="collapsed")

    # Advanced Custom CSS - Dark theme with neon effects
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&family=Roboto:wght@300;400;700&display=swap');
        
        * {
            font-family: 'Roboto', sans-serif;
        }
        
        /* Main background */
        body, .main {
            background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 50%, #0f1929 100%) !important;
            color: #e4e6eb;
        }
        
        /* Cards styling */
        .metric-card {
            background: linear-gradient(145deg, #1a2140 0%, #2a3f5f 100%);
            border: 1px solid rgba(100, 200, 255, 0.2);
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 150, 255, 0.1);
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
        }
        
        .metric-card:hover {
            border-color: rgba(100, 200, 255, 0.5);
            box-shadow: 0 12px 48px rgba(0, 150, 255, 0.2);
            transform: translateY(-2px);
        }
        
        /* Title styling */
        h1, h2, h3 {
            font-family: 'Courier Prime', monospace;
            font-weight: 700;
            letter-spacing: 2px;
            background: linear-gradient(90deg, #00d4ff, #00ffaa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        h1 {
            font-size: 3.5rem !important;
            text-shadow: 0 0 20px rgba(0, 212, 255, 0.3);
        }
        
        h4 {
            color: #00d4ff;
            font-size: 1.1rem;
            letter-spacing: 3px;
        }
        
        /* Risk score display */
        .risk-score {
            font-family: 'Courier Prime', monospace;
            font-size: 6rem;
            font-weight: 700;
            letter-spacing: 4px;
            transition: color 0.3s, text-shadow 0.3s;
        }
        
        /* Alert status */
        .alert-high {
            color: #ff006e;
            font-weight: 700;
            font-size: 2rem;
            letter-spacing: 2px;
            text-shadow: 0 0 15px rgba(255, 0, 110, 0.5);
        }
        
        .alert-medium {
            color: #ffd60a;
            font-weight: 700;
            font-size: 2rem;
            letter-spacing: 2px;
            text-shadow: 0 0 15px rgba(255, 214, 10, 0.5);
        }
        
        .alert-low {
            color: #00d4ff;
            font-weight: 700;
            font-size: 2rem;
            letter-spacing: 2px;
            text-shadow: 0 0 15px rgba(0, 212, 255, 0.5);
        }
        
        /* Progress bar */
        .progress-bar {
            background: linear-gradient(90deg, #00d4ff, #00ffaa);
            border-radius: 10px;
            height: 8px;
            box-shadow: 0 0 15px rgba(0, 212, 255, 0.5);
        }
        
        /* Zone container */
        .zone-container {
            background: linear-gradient(145deg, #1a2140 0%, #2a3f5f 100%);
            border: 2px solid rgba(0, 212, 255, 0.3);
            border-radius: 12px;
            padding: 20px;
            margin: 10px 0;
            backdrop-filter: blur(10px);
            transition: all 0.3s ease;
        }
        
        .zone-container:hover {
            border-color: rgba(0, 212, 255, 0.7);
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.2);
        }
        
        /* Data display */
        .data-label {
            color: #00d4ff;
            font-family: 'Courier Prime', monospace;
            font-size: 1.3rem;
            letter-spacing: 1px;
            opacity: 0.8;
        }
        
        .data-value {
            color: #00ffaa;
            font-family: 'Courier Prime', monospace;
            font-size: 3rem;
            font-weight: 700;
            margin-top: 5px;
        }
        
        /* Divider */
        hr {
            border: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent, rgba(0, 212, 255, 0.3), transparent);
            margin: 30px 0;
        }
        
        /* Selectbox styling */
        .stSelectbox label {
            color: #00d4ff !important;
            font-weight: 600;
            letter-spacing: 1px;
        }
        
        /* Button styling */
        .stButton button {
            background: linear-gradient(90deg, #00d4ff, #00ffaa) !important;
            color: #0a0e27 !important;
            border: none !important;
            font-weight: 700 !important;
            letter-spacing: 1px !important;
        }
        
        .stButton button:hover {
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.5) !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Main Title
    st.markdown("""
        <div style='text-align: center; margin-bottom: 20px;'>
            <h1>INDRA-NET</h1>
            <h4>[ COMMAND DASHBOARD v1.0 ]</h4>
            <p style='color: #00d4ff; font-family: Courier Prime; letter-spacing: 2px; margin-top: -10px;'>Real-time Crowd Monitoring System</p>
        </div>
    """, unsafe_allow_html=True)

    # Location Selector with styling
    col_loc1, col_loc2, col_loc3 = st.columns([1, 2, 1])
    with col_loc2:
        st.markdown("<p style='color: #00d4ff; font-weight: 600; letter-spacing: 1px;'>SELECT LOCATION</p>", unsafe_allow_html=True)
        location_options = {
            "Small Hall (50 m²)": 50,
            "Auditorium (200 m²)": 200,
            "Open Ground (500 m²)": 500
        }
        selected_location = st.selectbox(
            "Select Location",
            list(location_options.keys()),
            key="location_selector",
            label_visibility="collapsed"
        )

    selected_area = location_options[selected_location]

    # Header info
    col_info1, col_info2, col_info3 = st.columns([1, 2, 1])
    with col_info1:
        st.markdown(f"<p style='color: #00ffaa; font-family: Courier Prime; font-weight: 600;'>LOCATION: {selected_location}</p>", unsafe_allow_html=True)
    with col_info3:
        st.markdown(f"<p style='color: #00d4ff; font-family: Courier Prime; font-weight: 600; text-align: right;'>TIME: {datetime.now().strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)

    st.markdown("")

    should_rerun = False
    try:
        data = requests.get(f"http://127.0.0.1:5001/data?area={selected_area}", timeout=5).json()

        # Top Layer Metrics
        st.markdown("<p style='color: #00d4ff; font-family: Courier Prime; font-weight: 600; letter-spacing: 2px; margin-bottom: 15px;'>>> SENSOR LAYERS</p>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3, gap="medium")
        
        crowd = data.get("crowd_count", 0)
        
        with col1:
            st.markdown(f"""
                <div class='metric-card'>
                    <p class='data-label'>EDGE VISION LAYER</p>
                    <p class='data-value'>{crowd}</p>
                    <p style='color: #888; font-size: 0.9rem;'>Total People Detected</p>
                </div>
            """, unsafe_allow_html=True)
        
        with col2:
            device_count = data.get("device_count", 0)
            st.markdown(f"""
                <div class='metric-card'>
                    <p class='data-label'>WIRELESS DENSITY</p>
                    <p class='data-value'>{device_count}</p>
                    <p style='color: #888; font-size: 0.9rem;'>Devices Connected</p>
                </div>
            """, unsafe_allow_html=True)
        
        with col3:
            instability_val = data.get("instability", 0)
            stability = compute_stability_score(instability_val)
            motion_stale = data.get("motion_stale", False)
            stability_subtitle = "Stability Score (Stale)" if motion_stale else "Stability Score"
            st.markdown(f"""
                <div class='metric-card'>
                    <p class='data-label'>MOTION INTELLIGENCE</p>
                    <p class='data-value'>{stability}/100</p>
                    <p style='color: #888; font-size: 0.9rem;'>{stability_subtitle}</p>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("")
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("")

        # Risk Score - Main Display
        risk_value = round(data.get("risk", 0) * 100)
        alert_status = data.get("alert", "UNKNOWN")
        
        # Determine color based on alert
        if alert_status == "HIGH":
            alert_class = "alert-high"
            risk_color = "#ff0000"
        elif alert_status == "MEDIUM":
            alert_class = "alert-medium"
            risk_color = "#ffd60a"
        else:
            alert_class = "alert-low"
            risk_color = "#00ff00"
        
        st.markdown(f"""
            <div style='text-align: center; padding: 40px 20px;'>
                <p style='color: #00d4ff; font-family: Courier Prime; font-weight: 600; letter-spacing: 2px; font-size: 1.1rem;'>>>> OVERALL RISK ASSESSMENT <<<<</p>
                <div class='risk-score' style='color: {risk_color}; text-shadow: 0 0 30px {risk_color}80;'>{risk_value}</div>
                <div class='{alert_class}' style='margin-top: 15px;'>{alert_status} THREAT LEVEL</div>
                <p style='color: #888; margin-top: 15px; font-size: 0.9rem;'>[ Risk Analysis Complete ]</p>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("")
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("")

        # Live Metrics
        st.markdown("<p style='color: #00d4ff; font-family: Courier Prime; font-weight: 600; letter-spacing: 2px; margin-bottom: 15px;'>>> LIVE METRICS</p>", unsafe_allow_html=True)
        
        metric_col1, metric_col2, metric_col3 = st.columns(3, gap="medium")
        
        crowd = data.get("crowd_count", 0)
        devices = data.get("device_count", 0)
        motion = compute_motion_index(data.get("instability", 0))
        
        with metric_col1:
            st.markdown(f"""
                <div class='metric-card'>
                    <p class='data-label'>CROWD COUNT</p>
                    <p class='data-value'>{crowd}</p>
                </div>
            """, unsafe_allow_html=True)
        
        with metric_col2:
            st.markdown(f"""
                <div class='metric-card'>
                    <p class='data-label'>DEVICE DENSITY</p>
                    <p class='data-value'>{devices}</p>
                </div>
            """, unsafe_allow_html=True)
        
        with metric_col3:
            st.markdown(f"""
                <div class='metric-card'>
                    <p class='data-label'>INSTABILITY INDEX</p>
                    <p class='data-value'>{motion}</p>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("")
        st.markdown("<p style='color: #666; text-align: center; font-family: Courier Prime; font-size: 0.8rem; margin-top: 20px;'>[ System Status: ONLINE ] [ Data: LIVE ] [ Connection: STABLE ]</p>", unsafe_allow_html=True)

        should_rerun = True

    except Exception as e:
        if requests is not None and isinstance(e, requests.exceptions.ConnectionError):
            st.markdown("""
                <div style='text-align: center; padding: 40px; background: linear-gradient(145deg, #2a1f1f, #3a2f2f); border: 2px solid #ff006e; border-radius: 12px;'>
                    <p style='color: #ff006e; font-family: Courier Prime; font-weight: 600; font-size: 1.2rem;'>CONNECTION ERROR</p>
                    <p style='color: #ff6b9d;'>Cannot reach backend at http://127.0.0.1:5001</p>
                    <p style='color: #888; font-size: 0.9rem; margin-top: 15px;'>Ensure Flask server is running: <code style='background: #1a1a1a; padding: 5px 10px; border-radius: 5px;'>python backend.py</code></p>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
                <div style='text-align: center; padding: 40px; background: linear-gradient(145deg, #2a1f1f, #3a2f2f); border: 2px solid #ff006e; border-radius: 12px;'>
                    <p style='color: #ff006e; font-family: Courier Prime; font-weight: 600; font-size: 1.2rem;'>SYSTEM ERROR</p>
                    <p style='color: #ff6b9d;'>{str(e)}</p>
                </div>
            """, unsafe_allow_html=True)

    if should_rerun:
        # Auto-refresh outside try/except so rerun control-flow exceptions propagate cleanly
        time.sleep(0.1)
        st.rerun()


if __name__ == "__main__":
    render_dashboard()