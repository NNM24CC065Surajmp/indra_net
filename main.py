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

st.markdown("""
    <h1 style='text-align: center'>INDRA-NET</h1>
    <h4 style='text-align: center; color: #888;'>Command Dashboard</h4>
""", unsafe_allow_html=True)

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

try:
    # Pass the area to the backend
    data = requests.get(f"http://127.0.0.1:5001/data?area={selected_area}", timeout=5).json()

    # Top Section - 3 Columns with Metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("EDGE VISION LAYER")
        st.metric("Crowd Count", 0, "Real-time")
    
    with col2:
        st.subheader("WIRELESS DENSITY LAYER")
        st.metric("Connected Devices", data.get("device_count", "N/A"), "Calculated by density")
    
    with col3:
        st.subheader("MOTION INTELLIGENCE LAYER")
        st.metric("Stability Score", f"{int(data.get('instability', 0) * 10)}/100", "Stable Movement")

    st.markdown("---")

    # Middle Section - Risk Score Display
    col_left, col_center, col_right = st.columns([1, 2, 1])
    
    with col_center:
        st.markdown(f"""
            <div style="text-align: center; padding: 20px;">
                <h3 style="margin-bottom: 10px; font-weight: 600;">OVERALL RISK SCORE</h3>
                <div style="font-size: 72px; color: #ffd700; font-weight: bold; line-height: 1;">
                    {round(data.get("risk", 0) * 100)}
                </div>
                <div style="font-size: 22px; color: #ffd700; font-weight: 500; margin-top: 0px;">
                    {data.get("alert", "UNKNOWN")}
                </div>
            </div>
        """, unsafe_allow_html=True)

    # Auto-refresh
    time.sleep(2)
    st.rerun()

except requests.exceptions.ConnectionError:
    st.error("Cannot connect to backend at http://127.0.0.1:5001")
    st.info("Make sure your Flask/backend server is running on port 5001")
except Exception as e:
    st.error(f"Error: {str(e)}")