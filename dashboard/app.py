"""
UrbanPulse — Smart City Real-Time Data Engineering Platform.
Main Streamlit Application Entrypoint.
"""

import sys
from pathlib import Path
import streamlit as st

# Ensure urbanpulse root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from config.settings import settings
from dashboard.theme import (
    NEXUS_CSS,
    inject_overview_page_background,
    inject_default_page_background,
    get_sidebar_monument_image_base64,
)
from dashboard.views.overview import render_overview
from dashboard.views.traffic import render_traffic
from dashboard.views.environment import render_environment
from dashboard.views.urban_analytics import render_urban_analytics
from dashboard.views.iot_monitoring import render_iot_monitoring
from dashboard.views.anomaly_center import render_anomaly_center

# Page Configuration
st.set_page_config(
    page_title="UrbanPulse NEXUS | Nagpur Command Center",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply Centralized NEXUS CSS
st.markdown(NEXUS_CSS, unsafe_allow_html=True)


def main():
    # Streamlined Sidebar
    with st.sidebar:
        st.markdown(
            """
            <div style="padding: 10px 0 16px 0;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 26px;">🏙️</span>
                    <div>
                        <div style="font-family: 'Manrope', sans-serif; font-size: 20px; font-weight: 800; color: #F4F8FF; letter-spacing: -0.01em;">
                            UrbanPulse <span style="color: #29D8F4; font-size: 16px; font-weight: 700;">NEXUS</span>
                        </div>
                        <div style="font-size: 11px; color: #9FB1C9; font-weight: 500;">
                            NAGPUR COMMAND CENTER
                        </div>
                    </div>
                </div>
                <div style="margin-top: 12px; display: inline-flex; align-items: center; gap: 6px; background: rgba(41, 216, 244, 0.1); border: 1px solid rgba(41, 216, 244, 0.25); border-radius: 20px; padding: 4px 12px; font-size: 11px; color: #29D8F4; font-weight: 600;">
                    <span style="width: 6px; height: 6px; border-radius: 50%; background-color: #35D6A1; display: inline-block;"></span>
                    Nagpur, MH, India (LOC_NAGPUR)
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")

        nav_options = [
            "🏙️ Overview",
            "🚦 Traffic Intelligence",
            "🌱 Environmental Monitoring",
            "🔬 Urban Analytics",
            "🔌 Edge IoT Lab",
            "🚨 Anomaly Center",
        ]

        # Handle URL query parameter navigation (?nav=iot, etc.)
        if "nav" in st.query_params:
            target = st.query_params.get("nav")
            if target in ["iot", "edge_iot", "iot_monitoring", "Edge IoT Lab"]:
                st.session_state["nav_selection"] = "🔌 Edge IoT Lab"
            elif target in ["overview", "Overview"]:
                st.session_state["nav_selection"] = "🏙️ Overview"
            elif target in ["traffic", "Traffic"]:
                st.session_state["nav_selection"] = "🚦 Traffic Intelligence"
            elif target in ["environment", "Environment"]:
                st.session_state["nav_selection"] = "🌱 Environmental Monitoring"
            elif target in ["analytics", "Urban Analytics"]:
                st.session_state["nav_selection"] = "🔬 Urban Analytics"
            elif target in ["anomaly", "Anomaly Center"]:
                st.session_state["nav_selection"] = "🚨 Anomaly Center"
            del st.query_params["nav"]

        if "nav_selection" not in st.session_state or st.session_state["nav_selection"] not in nav_options:
            st.session_state["nav_selection"] = "🏙️ Overview"

        page = st.radio(
            "Navigation",
            nav_options,
            key="nav_selection",
            label_visibility="collapsed",
        )



        monument_b64 = get_sidebar_monument_image_base64()
        if monument_b64:
            st.markdown(
                f"""
                <div style="margin-top: 8px; text-align: center; position: relative; overflow: hidden; border-radius: 12px; pointer-events: none;">
                    <img src="data:image/png;base64,{monument_b64}" 
                         alt="Nagpur Zero Mile Monument Artwork" 
                         style="width: 100%; height: auto; max-height: 245px; object-fit: cover; object-position: center top; display: block; border-radius: 12px; mask-image: linear-gradient(to bottom, transparent 0%, black 14%, black 86%, transparent 100%); -webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 14%, black 86%, transparent 100%); opacity: 0.92; filter: drop-shadow(0 0 16px rgba(41, 216, 244, 0.25));" />
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Routing & Per-Page Dynamic Background Isolation
    if page == "🏙️ Overview":
        inject_overview_page_background()
        render_overview()
    else:
        inject_default_page_background()
        if page == "🚦 Traffic Intelligence":
            render_traffic()
        elif page == "🌱 Environmental Monitoring":
            render_environment()
        elif page == "🔬 Urban Analytics":
            render_urban_analytics()
        elif page == "🔌 Edge IoT Lab":
            render_iot_monitoring()
        elif page == "🚨 Anomaly Center":
            render_anomaly_center()


if __name__ == "__main__":
    main()
