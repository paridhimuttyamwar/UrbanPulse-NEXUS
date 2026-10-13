"""
UrbanPulse NEXUS — Environmental Monitoring View.
Tracks real atmospheric observations from Open-Meteo Weather and Air Quality APIs.
Features the Environmental Health Ring, EPA AQI categories, pollutant concentrations,
and ambient microclimate vitals for Nagpur.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from dashboard.theme import (
    render_nexus_header,
    render_kpi_card,
    render_section_header,
    apply_nexus_theme,
)
from dashboard.data_loader import format_time_ago, trigger_manual_environmental_ingestion
from analytics.environment_analytics import environment_analytics


def render_environment():
    # 1. Header with Single Clear Source Indicator & Manual Ingestion Trigger
    col_hdr, col_sync = st.columns([4.2, 1.1])
    with col_hdr:
        render_nexus_header(
            title="🌱 Environmental Monitoring — Nagpur",
            subtitle="Atmospheric observations from Open-Meteo meteorological and air pollution models",
            provenance_badge="OPEN-METEO",
        )
    with col_sync:
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Sync Live Weather & AQI", key="sync_env_page", help="Fetch real-time Open-Meteo observations for Nagpur"):
            with st.spinner("Fetching latest Open-Meteo records..."):
                sync_res = trigger_manual_environmental_ingestion("LOC_NAGPUR")
                if sync_res["success"]:
                    st.success(f"✓ Synchronized! Weather={sync_res['weather_inserted']}, AQI={sync_res['aq_inserted']}")
                    st.rerun()
                else:
                    st.error(f"Sync error: {sync_res.get('error')}")

    df_weather = environment_analytics.load_weather_dataframe(limit=1000)
    df_aq = environment_analytics.load_air_quality_dataframe(limit=1000)

    if df_weather.empty or df_aq.empty:
        st.warning("No environmental data available yet. Click 'Sync Live Weather & AQI' above to fetch.")
        return

    # Filtered exclusively for Nagpur
    selected_loc = "LOC_NAGPUR"
    filtered_weather = df_weather[df_weather["location_id"] == selected_loc]
    filtered_aq = df_aq[df_aq["location_id"] == selected_loc]

    if filtered_weather.empty or filtered_aq.empty:
        st.info("No meteorological records available specifically for Nagpur yet. Click 'Sync Live Weather & AQI' above.")
        return

    latest_weather = filtered_weather.sort_values("timestamp", ascending=False).iloc[0]
    latest_aq = filtered_aq.sort_values("timestamp", ascending=False).iloc[0]

    # Calculate dynamic data freshness
    ts_w = pd.to_datetime(latest_weather["timestamp"])
    w_ago, w_elapsed = format_time_ago(ts_w, is_utc=False)
    w_fresh = (w_elapsed <= 75 * 60)
    w_status_str = "FRESH" if w_fresh else "STALE"

    ts_aq = pd.to_datetime(latest_aq["timestamp"])
    aq_ago, aq_elapsed = format_time_ago(ts_aq, is_utc=False)
    aq_fresh = (aq_elapsed <= 90 * 60)
    aq_status_str = "FRESH" if aq_fresh else "STALE"

    # 2. Top KPI Metric Cards (Equalized Dimensions with Subtle Decorative Sparklines)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_kpi_card(
            label="Ambient Temperature",
            value=f"{latest_weather['temperature_c']:.1f}",
            unit="°C",
            delta=f"{latest_weather['weather_condition']} • {w_ago} ({w_status_str})",
            provenance=None,
            icon="🌡️",
            sparkline_type="wave_cyan",
            accent_color="cyan",
        )
    with col2:
        render_kpi_card(
            label="Relative Humidity",
            value=f"{latest_weather['relative_humidity_pct']:.0f}",
            unit="%",
            delta=f"Wind: {latest_weather['wind_speed_kmh']} km/h • {w_ago}",
            provenance=None,
            icon="💧",
            sparkline_type="bars_blue",
            accent_color="blue",
        )
    with col3:
        render_kpi_card(
            label="Fine Particulates (PM2.5)",
            value=f"{latest_aq['pm2_5']:.1f}",
            unit=" µg/m³",
            delta=f"WHO Guideline: 15 µg/m³ • {aq_ago} ({aq_status_str})",
            provenance=None,
            icon="🔬",
            sparkline_type="wave_amber",
            accent_color="amber",
        )
    with col4:
        aqi_val = int(latest_aq['us_aqi'])
        cat_name = latest_aq['aqi_category'] if 'aqi_category' in latest_aq else ("Good" if aqi_val <= 50 else "Moderate")
        render_kpi_card(
            label="US Air Quality Index",
            value=f"{aqi_val}",
            unit=" AQI",
            delta=f"{cat_name} • {aq_ago} ({aq_status_str})",
            provenance=None,
            icon="🍃",
            sparkline_type="wave_purple",
            accent_color="purple",
        )

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

    # 3. Charts Row 1: Innovative Environmental Health Ring & Ambient Vitals
    render_section_header(
        title="Atmospheric Quality & Chemical Speciation",
        subtitle="Real-time US EPA AQI health classification and measured particulate concentrations",
        badge="AIR MODEL",
    )
    c1, c2 = st.columns([1, 1])

    with c1:
        st.markdown("#### 🎯 Environmental Health Ring (US EPA AQI)")
        current_aqi = int(latest_aq["us_aqi"])
        
        # Color coding according to EPA standard
        if current_aqi <= 50:
            needle_color = "#35D6A1"
            health_status = "Good (Air quality is satisfactory)"
        elif current_aqi <= 100:
            needle_color = "#FFBF69"
            health_status = "Moderate (Acceptable; sensitive individuals take caution)"
        elif current_aqi <= 150:
            needle_color = "#FF9F43"
            health_status = "Unhealthy for Sensitive Groups"
        elif current_aqi <= 200:
            needle_color = "#FF647C"
            health_status = "Unhealthy (General public may experience irritation)"
        elif current_aqi <= 300:
            needle_color = "#9685FF"
            health_status = "Very Unhealthy (Health alert: increased risk for everyone)"
        else:
            needle_color = "#7F1D1D"
            health_status = "Hazardous (Emergency health warning)"

        cat_name = latest_aq['aqi_category'] if 'aqi_category' in latest_aq and pd.notna(latest_aq['aqi_category']) else ("Good" if current_aqi <= 50 else ("Moderate" if current_aqi <= 100 else "Unhealthy"))

        fig_gauge = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=current_aqi,
                domain={"x": [0.06, 0.94], "y": [0.02, 0.96]},
                title={
                    "text": f"<b>Nagpur AQI Index</b><br><span style='font-size:13px; color:{needle_color}; font-weight:700;'>Category: {cat_name}</span><br><span style='font-size:11px; color:#9FB1C9;'>Observed at {latest_aq['timestamp']} ({aq_ago} • {aq_status_str})</span>",
                    "font": {"size": 16, "color": "#F4F8FF"},
                },
                number={
                    "font": {"size": 48, "color": needle_color, "family": "Manrope, Inter, sans-serif"},
                    "suffix": " AQI",
                },
                gauge={
                    "axis": {
                        "range": [0, 500],
                        "tickwidth": 1,
                        "tickcolor": "#9FB1C9",
                        "tickfont": {"size": 11, "color": "#9FB1C9"},
                        "nticks": 6,
                    },
                    "bar": {"color": needle_color, "thickness": 0.28},
                    "bgcolor": "rgba(21, 36, 59, 0.6)",
                    "borderwidth": 1,
                    "bordercolor": "rgba(79, 140, 255, 0.25)",
                    "steps": [
                        {"range": [0, 50], "color": "rgba(53, 214, 161, 0.3)"},
                        {"range": [50, 100], "color": "rgba(255, 191, 105, 0.3)"},
                        {"range": [100, 150], "color": "rgba(255, 159, 67, 0.3)"},
                        {"range": [150, 200], "color": "rgba(255, 100, 124, 0.3)"},
                        {"range": [200, 300], "color": "rgba(150, 133, 255, 0.3)"},
                        {"range": [300, 500], "color": "rgba(127, 29, 29, 0.4)"},
                    ],
                },
            )
        )
        apply_nexus_theme(fig_gauge, height=350)
        fig_gauge.update_layout(
            margin=dict(l=30, r=30, t=65, b=25),
        )
        st.plotly_chart(fig_gauge, use_container_width=True)
        st.caption(f"🩺 **Health Assessment:** {health_status}")

    with c2:
        st.markdown("#### 🧪 Atmospheric Particulate & Chemical Levels")
        pollutant_means = {
            "PM2.5": filtered_aq["pm2_5"].iloc[0],
            "PM10": filtered_aq["pm10"].iloc[0],
            "NO2": filtered_aq["nitrogen_dioxide"].iloc[0] if "nitrogen_dioxide" in filtered_aq else 0,
            "O3": filtered_aq["ozone"].iloc[0] if "ozone" in filtered_aq else 0,
            "SO2": filtered_aq["sulphur_dioxide"].iloc[0] if "sulphur_dioxide" in filtered_aq else 0,
        }
        df_poll = pd.DataFrame(list(pollutant_means.items()), columns=["Pollutant", "Concentration (µg/m³)"])
        fig_poll = px.bar(
            df_poll,
            x="Pollutant",
            y="Concentration (µg/m³)",
            color="Pollutant",
            color_discrete_sequence=["#29D8F4", "#4F8CFF", "#9685FF", "#35D6A1", "#FFBF69"],
            labels={"Concentration (µg/m³)": "Concentration (µg/m³)"},
        )
        apply_nexus_theme(fig_poll, height=350)
        st.plotly_chart(fig_poll, use_container_width=True)
        st.caption("Fresh Open-Meteo atmospheric dispersion readings for Nagpur.")

    filtered_weather = filtered_weather.copy()
    filtered_aq = filtered_aq.copy()
    filtered_weather["timestamp_display"] = pd.to_datetime(filtered_weather["timestamp"]).dt.strftime("%d %b %Y, %I:%M %p IST")
    filtered_aq["timestamp_display"] = pd.to_datetime(filtered_aq["timestamp"]).dt.strftime("%d %b %Y, %I:%M %p IST")

    # 4. Charts Row 2: Ambient Meteorological Profiles
    render_section_header(
        title="Meteorological Trends & Ambient Profiles",
        subtitle="Ambient temperature progression and relative humidity tracking over time",
        badge="WEATHER MODEL",
    )
    c3, c4 = st.columns([1, 1])

    with c3:
        st.markdown("#### 🌡️ Nagpur Temperature Progression (°C)")
        if len(filtered_weather) > 1:
            fig_temp = px.line(
                filtered_weather.sort_values("timestamp"),
                x="timestamp",
                y="temperature_c",
                labels={"temperature_c": "Temperature (°C)", "timestamp": "Observation Time (IST)"},
                color_discrete_sequence=["#FFBF69"],
            )
            fig_temp.update_traces(connectgaps=False, mode="lines+markers")
            apply_nexus_theme(fig_temp, height=340)
            st.plotly_chart(fig_temp, use_container_width=True)
        else:
            st.info("Single baseline weather observation recorded. Trends will populate automatically as observations accumulate.")

    with c4:
        st.markdown("#### 💧 Nagpur Relative Humidity Progression (%)")
        if len(filtered_weather) > 1:
            fig_hum = px.line(
                filtered_weather.sort_values("timestamp"),
                x="timestamp",
                y="relative_humidity_pct",
                labels={"relative_humidity_pct": "Relative Humidity (%)", "timestamp": "Observation Time (IST)"},
                color_discrete_sequence=["#29D8F4"],
            )
            fig_hum.update_traces(connectgaps=False, mode="lines+markers")
            apply_nexus_theme(fig_hum, height=340)
            st.plotly_chart(fig_hum, use_container_width=True)
        else:
            st.info("Single baseline humidity observation recorded. Trends will populate automatically as observations accumulate.")

    # 5. Raw Data Explorer
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    with st.expander("Recent Environmental Observations", expanded=False):
        aq_cols = ["timestamp_display", "us_aqi", "aqi_category", "pm2_5", "pm10", "nitrogen_dioxide", "ozone", "source_type"]
        valid_aq_cols = [c for c in aq_cols if c in filtered_aq.columns]
        st.dataframe(filtered_aq[valid_aq_cols].head(100), use_container_width=True)

