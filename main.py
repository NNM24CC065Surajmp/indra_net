import streamlit as st
import requests
import time
from datetime import datetime

st.set_page_config(page_title="INDRA-NET", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS for better styling
st.markdown("""
    <style>
    .metric-card {
        background-color: #1e1e2e;
        padding: 20px;
        border-radius: 10px;
        border-left: 4px solid #ffd700;
    }
    .safe-status {color: #00ff00;}
    .caution-status {color: #ffd700;}
    .critical-status {color: #ff4444;}
    </style>
""", unsafe_allow_html=True)

st.title("INDRA-NET Command Dashboard")

# Location Selector
st.subheader("Select Location")
location_options = {
    "Small Hall (50 m²)": 50,
    "Auditorium (200 m²)": 200,
    "Open Ground (500 m²)": 500
}

selected_location = st.selectbox(
    "Choose location to monitor:",
    list(location_options.keys()),
    key="location_selector"
)

selected_area = location_options[selected_location]

# Header with location and time
col_header1, col_header2, col_header3 = st.columns([2, 3, 1])
with col_header1:
    st.write(f"{selected_location}")
with col_header3:
    st.write(f"{datetime.now().strftime('%I:%M:%S %p')}")

st.markdown("---")

placeholder = st.empty()

try:
    # Pass the area to the backend
    data = requests.get(f"http://127.0.0.1:5001/data?area={selected_area}", timeout=5).json()

    with placeholder.container():
        # Top Section - 3 Columns with Metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("EDGE VISION LAYER")
            st.metric("Density Level", "Medium", "58% capacity")
        
        with col2:
            st.subheader("WIRELESS DENSITY LAYER")
            st.metric("Device Count", data.get("device_count", "N/A"), "Calculated by density")
        
        with col3:
            st.subheader("MOTION INTELLIGENCE LAYER")
            st.metric("Stability Score", int(data.get("instability", 0) * 10), "Stable Movement")

        st.markdown("---")

        # Middle Section - Risk Score Display
        col_left, col_center, col_right = st.columns([1, 2, 1])
        
        with col_center:
            st.subheader("OVERALL RISK SCORE")
            st.markdown(f"""
                <div style="text-align: center; padding: 30px;">
                    <div style="font-size: 72px; color: #ffd700; font-weight: bold;">
                        {round(data.get("risk", 0) * 100)}
                    </div>
                    <div style="font-size: 18px; color: #ffd700; margin-top: 10px;">
                        {data.get("alert", "UNKNOWN")}
                    </div>
                </div>
            """, unsafe_allow_html=True)
        
        with col_left:
            st.subheader("ALERTS")
            alerts = [
                "Zone D density exceeding threshold",
                "Unusual motion pattern in Zone B",
                "Device count spike detected (+34)"
            ]
            for i, alert in enumerate(alerts, 1):
                st.warning(f"{i}. {alert}")

        st.markdown("---")

        # Zone Overview Section
        st.subheader("ZONE OVERVIEW")
        zone_col1, zone_col2, zone_col3, zone_col4 = st.columns(4)
        
        zones = [
            ("Zone A – Entry", " SAFE", "safe-status"),
            ("Zone B – Platform", " CAUTION", "caution-status"),
            ("Zone C – Exit", " SAFE", "safe-status"),
            ("Zone D – Lobby", " CRITICAL", "critical-status")
        ]
        
        with zone_col1:
            st.markdown(f'<p style="color: #888;">{zones[0][0]}</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="{zones[0][2]}">{zones[0][1]}</p>', unsafe_allow_html=True)
            st.progress(0.3)
        
        with zone_col2:
            st.markdown(f'<p style="color: #888;">{zones[1][0]}</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="{zones[1][2]}">{zones[1][1]}</p>', unsafe_allow_html=True)
            st.progress(0.6)
        
        with zone_col3:
            st.markdown(f'<p style="color: #888;">{zones[2][0]}</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="{zones[2][2]}">{zones[2][1]}</p>', unsafe_allow_html=True)
            st.progress(0.2)
        
        with zone_col4:
            st.markdown(f'<p style="color: #888;">{zones[3][0]}</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="{zones[3][2]}">{zones[3][1]}</p>', unsafe_allow_html=True)
            st.progress(0.9)

        st.markdown("---")

        # Live Metrics section
        st.subheader("LIVE METRICS")
        metric_col1, metric_col2, metric_col3 = st.columns(3)
        
        with metric_col1:
            st.metric("Crowd Count", data.get("crowd_count", "N/A"), "Real-time")
        
        with metric_col2:
            st.metric("Connected Devices", data.get("device_count", "N/A"))
        
        with metric_col3:
            st.metric("Motion Instability", f"{data.get('instability', 0)}/10")

        # Auto-refresh
        time.sleep(2)
        st.rerun()

except requests.exceptions.ConnectionError:
    st.error("Cannot connect to backend at http://127.0.0.1:5001")
    st.info("Make sure your Flask/backend server is running on port 5001")
except Exception as e:
    st.error(f"Error: {str(e)}")