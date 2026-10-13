"""
UrbanPulse NEXUS — Overview Command Center.
Signature smart city operations, KPI intelligence cards, atmospheric vitals,
provenance stream health, and collapsible system diagnostics.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from config.settings import settings
from dashboard.theme import (
    render_nexus_hero,
    render_kpi_card,
    render_section_header,
    apply_nexus_theme,
    get_badge_class,
)
from dashboard.data_loader import (
    load_latest_weather,
    load_latest_air_quality,
    load_traffic_readings,
    load_latest_traffic_per_corridor,
    load_anomalies,
    load_data_source_status,
    format_time_ago,
    trigger_manual_environmental_ingestion,
    get_gateway_runtime_status,
)
from config.corridors import get_approved_corridors, NAGPUR_CORRIDORS_GEO
from database.connection import get_db_cursor


def render_overview():
    # Data Fetching for Nagpur
    df_weather = load_latest_weather(location_id="LOC_NAGPUR")
    df_aq = load_latest_air_quality(location_id="LOC_NAGPUR")
    df_traffic_latest = load_latest_traffic_per_corridor(location_id="LOC_NAGPUR", source_type="REAL_API", stale_threshold_minutes=90)
    df_traffic = load_traffic_readings(location_id="LOC_NAGPUR", source_type="REAL_API", limit=100)
    df_anom = load_anomalies(status="ACTIVE", location_id="LOC_NAGPUR", source_type="REAL_API")

    # Evaluate dynamic data freshness for Hero section & Atmospheric panels
    weather_fresh = False
    weather_ago = "No Data"
    if not df_weather.empty and pd.notna(df_weather["timestamp"].iloc[0]):
        ts_w = pd.to_datetime(df_weather["timestamp"].iloc[0])
        weather_ago, elapsed_w = format_time_ago(ts_w, is_utc=False)
        weather_fresh = (elapsed_w <= 75 * 60)

    aq_fresh = False
    aq_ago = "No Data"
    if not df_aq.empty and pd.notna(df_aq["timestamp"].iloc[0]):
        ts_aq = pd.to_datetime(df_aq["timestamp"].iloc[0])
        aq_ago, elapsed_aq = format_time_ago(ts_aq, is_utc=False)
        aq_fresh = (elapsed_aq <= 90 * 60)

    traffic_fresh = False
    traffic_ago = "No Data"
    if not df_traffic_latest.empty:
        traffic_ago = df_traffic_latest["time_ago"].iloc[0]
        traffic_fresh = not df_traffic_latest["is_stale"].iloc[0]

    if weather_fresh and aq_fresh and traffic_fresh:
        hero_status_label = "ALL APIS SYNCHRONIZED"
        hero_status_cls = "badge-positive"
    elif weather_fresh or aq_fresh or traffic_fresh:
        hero_status_label = "PARTIAL FRESH SYNC"
        hero_status_cls = "badge-positive"
    elif not df_weather.empty or not df_aq.empty or not df_traffic_latest.empty:
        hero_status_label = f"STALE API ({traffic_ago})"
        hero_status_cls = "badge-amber"
    else:
        hero_status_label = "NO DATA"
        hero_status_cls = "badge-negative"

    # 1. Signature NEXUS Hero Section (with Authentic Nagpur Cityscape & Dynamic Freshness Badge)
    render_nexus_hero(status_label=hero_status_label, status_cls=hero_status_cls)

    # 2. Responsive KPI Metric Cards Grid
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        if not df_weather.empty:
            temp_val = f"{df_weather['temperature_c'].iloc[0]:.1f}"
            cond = df_weather['weather_condition'].iloc[0]
            render_kpi_card(
                label="Nagpur Temperature",
                value=temp_val,
                unit="°C",
                delta=f"{cond} • {weather_ago}",
                provenance=None,
                icon="🌡️",
                sparkline_type="wave_cyan",
                accent_color="cyan",
            )
        else:
            render_kpi_card(
                label="Nagpur Temperature",
                value="--",
                unit="°C",
                delta="No Data",
                provenance=None,
                icon="🌡️",
                sparkline_type="wave_cyan",
                accent_color="cyan",
            )

    with col2:
        if not df_aq.empty and "us_aqi" in df_aq.columns:
            aqi_val = int(df_aq["us_aqi"].iloc[0])
            cat = df_aq["aqi_category"].iloc[0] if "aqi_category" in df_aq.columns else "Moderate"
            render_kpi_card(
                label="Air Quality Index",
                value=aqi_val,
                unit=" AQI",
                delta=f"{cat} • {aq_ago}",
                provenance=None,
                icon="🍃",
                sparkline_type="wave_purple",
                accent_color="purple",
            )
        else:
            render_kpi_card(
                label="Air Quality Index",
                value="--",
                unit=" AQI",
                delta="No Data",
                provenance=None,
                icon="🍃",
                sparkline_type="wave_purple",
                accent_color="purple",
            )

    with col3:
        if not df_traffic_latest.empty:
            avg_spd = f"{df_traffic_latest['avg_speed_kmh'].mean():.1f}"
            high_cong = int((df_traffic_latest["congestion_level"].isin(["HIGH", "SEVERE"])).sum())
            max_delay = int(df_traffic_latest["delay_seconds"].max())
            render_kpi_card(
                label="Mean Network Speed",
                value=avg_spd,
                unit=" km/h",
                delta=f"{high_cong} Congested • Max Delay {max_delay}s",
                provenance=None,
                icon="🚗",
                sparkline_type="wave_cyan",
                accent_color="cyan",
            )
        else:
            render_kpi_card(
                label="Mean Network Speed",
                value="--",
                unit=" km/h",
                delta="No Live Telemetry",
                provenance=None,
                icon="🚗",
                sparkline_type="wave_cyan",
                accent_color="cyan",
            )

    with col4:
        active_anom_count = len(df_anom)
        render_kpi_card(
            label="Active Incidents",
            value=active_anom_count,
            unit=" alerts",
            delta="Requires Triage" if active_anom_count > 0 else "All Normal",
            provenance="ALERTS" if active_anom_count > 0 else None,
            icon="🚨",
            sparkline_type="wave_red" if active_anom_count > 0 else "wave_green",
            accent_color="red" if active_anom_count > 0 else "green",
        )

    with col5:
        approved_corrs = get_approved_corridors()
        approved_cnt = len(approved_corrs)
        total_cnt = len(NAGPUR_CORRIDORS_GEO)
        excluded_cnt = total_cnt - approved_cnt
        delta_label = f"{approved_cnt} Active • All Corridors Verified" if excluded_cnt == 0 else f"{approved_cnt} Active • {excluded_cnt} Excluded"
        render_kpi_card(
            label="Monitored Corridors",
            value=f"{approved_cnt} / {total_cnt}",
            unit=" arterials",
            delta=delta_label,
            provenance=None,
            icon="🛣️",
            sparkline_type="bars_blue",
            accent_color="blue",
        )

    # 3. Atmospheric Intelligence & Municipal Profile Grid with Varied Visual Layout
    col_hdr, col_sync = st.columns([3.4, 1.2])
    with col_hdr:
        render_section_header(
            title="Atmospheric Intelligence & Municipal Node",
            subtitle="Synchronized Open-Meteo meteorological observations & Zero Mile municipal coordinates",
            badge="OPEN-METEO",
        )
    with col_sync:
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Sync Live Weather & AQI", key="sync_env_overview", help="Fetch real-time Open-Meteo weather and air quality for Nagpur"):
            with st.spinner("Fetching latest Open-Meteo records..."):
                sync_res = trigger_manual_environmental_ingestion("LOC_NAGPUR")
                if sync_res["success"]:
                    st.success(f"✓ Synchronized: Weather={sync_res['weather_inserted']}, AQI={sync_res['aq_inserted']}")
                    st.rerun()
                else:
                    st.error(f"Sync error: {sync_res.get('error')}")

    if not df_weather.empty and not df_aq.empty:
        merged = pd.merge(df_weather, df_aq[["location_id", "pm2_5", "pm10", "us_aqi", "aqi_category"]], on="location_id", how="left")
        w_row = merged.iloc[0]
        col_w, col_aq, col_env = st.columns([1, 1, 1.2])

        w_status_badge = "FRESH" if weather_fresh else "STALE"
        w_status_color = "#35D6A1" if weather_fresh else "#FFBF69"

        with col_w:
            st.markdown(
                f"""
                <div class="nexus-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                        <span style="font-size: 15px; font-weight: 700; color: #F4F8FF;">🌤️ Weather Microclimate</span>
                        <span class="badge-nexus" style="background: rgba(41, 216, 244, 0.15); color: #29D8F4; border: 1px solid rgba(41, 216, 244, 0.3);">OPEN-METEO</span>
                    </div>
                    <div style="font-size: 13.5px; line-height: 2.1; color: #9FB1C9;">
                        <div>Condition: <strong style="color: #F4F8FF;">{w_row['weather_condition']}</strong></div>
                        <div>Temperature: <strong style="color: #29D8F4; font-size: 15px;">{w_row['temperature_c']} °C</strong></div>
                        <div>Relative Humidity: <strong style="color: #F4F8FF;">{w_row['relative_humidity_pct']}%</strong></div>
                        <div>Wind Speed: <strong style="color: #F4F8FF;">{w_row['wind_speed_kmh']} km/h</strong></div>
                    </div>
                    <div style="margin-top: 12px; font-size: 11px; color: #4F8CFF; border-top: 1px solid rgba(79, 140, 255, 0.15); padding-top: 8px; display: flex; justify-content: space-between; align-items: center;">
                        <span>🕒 Observed: {w_row['timestamp']} ({weather_ago})</span>
                        <span style="color: {w_status_color}; font-weight: 700; font-size: 10px; background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px;">{w_status_badge}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        aq_status_badge = "FRESH" if aq_fresh else "STALE"
        aq_status_color = "#35D6A1" if aq_fresh else "#FFBF69"

        with col_aq:
            euro_aqi = df_aq['european_aqi'].iloc[0] if 'european_aqi' in df_aq.columns and pd.notna(df_aq['european_aqi'].iloc[0]) else 'N/A'
            aqi_val = w_row['us_aqi']
            cat_name = w_row.get('aqi_category', 'Moderate')
            cat_color = "#35D6A1" if "Good" in str(cat_name) else ("#FFBF69" if "Moderate" in str(cat_name) else "#FF647C")
            st.markdown(
                f"""
                <div class="nexus-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                        <span style="font-size: 15px; font-weight: 700; color: #F4F8FF;">🍃 Atmospheric Purity (AQI)</span>
                        <span class="badge-nexus" style="background: rgba(150, 133, 255, 0.15); color: #9685FF; border: 1px solid rgba(150, 133, 255, 0.3);">AIR MODEL</span>
                    </div>
                    <div style="font-size: 13.5px; line-height: 2.1; color: #9FB1C9;">
                        <div>EPA US AQI: <strong style="color: {cat_color}; font-size: 15px;">{aqi_val} ({cat_name})</strong></div>
                        <div>Fine Particulates (PM2.5): <strong style="color: #F4F8FF;">{w_row['pm2_5']} µg/m³</strong></div>
                        <div>Coarse Particulates (PM10): <strong style="color: #F4F8FF;">{w_row['pm10']} µg/m³</strong></div>
                        <div>European Index: <strong style="color: #F4F8FF;">{euro_aqi}</strong></div>
                    </div>
                    <div style="margin-top: 12px; font-size: 11px; color: #9FB1C9; border-top: 1px solid rgba(79, 140, 255, 0.15); padding-top: 8px; display: flex; justify-content: space-between; align-items: center;">
                        <span>✓ Validated Open-Meteo ({aq_ago})</span>
                        <span style="color: {aq_status_color}; font-weight: 700; font-size: 10px; background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px;">{aq_status_badge}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_env:
            telemetry_status = "Live Sync (Fresh)" if (weather_fresh and aq_fresh) else f"Archived ({weather_ago})"
            telemetry_color = "#35D6A1" if (weather_fresh and aq_fresh) else "#FFBF69"
            pulse_html = '<span class="live-pulse"></span>' if (weather_fresh and aq_fresh) else ""

            gw_status = get_gateway_runtime_status()
            is_gw_alive = gw_status.get("is_alive", False)
            gw_conn_state = gw_status.get("connection_state", "DISCONNECTED")
            active_gw_port = gw_status.get("active_port")

            if is_gw_alive and gw_conn_state in ("STREAMING", "CONNECTED"):
                arduino_status_str = f"🟢 Connected ({active_gw_port or 'USB'})"
                arduino_color = "#35D6A1"
            elif is_gw_alive:
                arduino_status_str = f"🟡 Standby ({gw_conn_state})"
                arduino_color = "#FFBF69"
            else:
                arduino_status_str = "⚪ Offline (Gateway Standby)"
                arduino_color = "#9FB1C9"

            st.markdown(
                f"""
                <div class="nexus-card nexus-card-featured">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 18px;">🏛️</span>
                            <div>
                                <span style="font-size: 15px; font-weight: 800; color: #F4F8FF;">Zero Mile Municipal Node</span>
                                <div style="font-size: 11px; color: #29D8F4; margin-top: 1px;">Nagpur Operations Command</div>
                            </div>
                        </div>
                        <span class="badge-nexus badge-positive">ACTIVE NODE</span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12.5px; line-height: 1.7; color: #9FB1C9;">
                        <div>Node ID: <strong style="color: #29D8F4;">LOC_NAGPUR</strong></div>
                        <div>Latitude: <strong style="color: #F4F8FF;">21.1458° N</strong></div>
                        <div>Altitude: <strong style="color: #F4F8FF;">310 m MSL</strong></div>
                        <div>Longitude: <strong style="color: #F4F8FF;">79.0882° E</strong></div>
                        <div>Telemetry: <strong style="color: {telemetry_color};">{telemetry_status}</strong> {pulse_html}</div>
                        <div>Arduino Node: <strong style="color: {arduino_color};">{arduino_status_str}</strong></div>
                    </div>
                    <a href="?nav=iot" target="_self" class="nexus-card-nav-link" style="margin-top: 14px; font-size: 11.5px; color: #29D8F4; background: rgba(8, 15, 30, 0.65); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(41, 216, 244, 0.25);">
                        <span>📡 Edge Lab: Zero Mile Station (Arduino Uno R3 Prototype)</span>
                        <span style="font-weight: 700; font-size: 13px;">&gt;</span>
                    </a>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("Awaiting initial atmospheric records for Nagpur. Click 'Sync Live Weather & AQI' above to fetch.")

    # 4. Two-Column Layout: Pipeline Streams & Live Incident Feed
    render_section_header(
        title="Data Pipelines & Live Municipal Incident Queue",
        subtitle="Kafka streaming ingestion health and deterministic incident triage for Nagpur",
        badge="ACTIVE STREAMS",
    )
    col_left, col_right = st.columns([1, 1])

    with col_left:
        sources = load_data_source_status()
        df_sources = pd.DataFrame(sources)
        st.dataframe(
            df_sources,
            column_config={
                "Source": st.column_config.TextColumn("Data Stream", width="medium"),
                "Type": st.column_config.TextColumn("Provenance", width="small"),
                "Records": st.column_config.NumberColumn("Total Records"),
                "Last Update": st.column_config.TextColumn("Last Update", width="medium"),
                "Status": st.column_config.TextColumn("Pipeline Health"),
            },
            hide_index=True,
            use_container_width=True,
        )

    with col_right:
        if not df_anom.empty:
            for _, anom in df_anom.head(3).iterrows():
                sev = anom["severity"]
                sev_color = "#FF647C" if sev in ["CRITICAL", "HIGH"] else "#FFBF69"
                src = anom.get("source_type", "REAL_API")
                src_badge_cls = "badge-real-api" if src == "REAL_API" else "badge-simulated"
                r_name = anom.get("road_name") or "Nagpur Municipal Area"
                st.markdown(
                    f"""
                    <div class="nexus-card" style="padding: 14px 18px; margin-bottom: 10px; border-left: 3px solid {sev_color};">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="font-size: 13px; font-weight: 700; color: {sev_color};">[{sev}] {anom['anomaly_type']}</span>
                            <span class="badge-nexus {src_badge_cls}">{src}</span>
                        </div>
                        <div style="font-size: 12.5px; color: #F4F8FF; margin-bottom: 4px;">{anom['description']}</div>
                        <div style="display: flex; justify-content: space-between; font-size: 11px; color: #9FB1C9;">
                            <span>📍 {r_name}</span>
                            <span>🕒 {anom['timestamp']} | ID: {anom['anomaly_id']}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            anom_ok_html = (
                '<div class="nexus-card" style="border: 1px solid rgba(53, 214, 161, 0.4); background: linear-gradient(135deg, rgba(16, 42, 32, 0.78) 0%, rgba(10, 26, 20, 0.88) 100%); padding: 22px;">'
                '<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">'
                '<div style="display: flex; align-items: center; gap: 8px;">'
                '<span style="width: 10px; height: 10px; border-radius: 50%; background: #35D6A1; display: inline-block; box-shadow: 0 0 10px #35D6A1;"></span>'
                '<span style="font-weight: 700; color: #35D6A1; font-size: 14.5px;">Live Municipal Incident Queue</span>'
                '</div>'
                '<span class="badge-nexus badge-positive">NORMAL STATUS</span>'
                '</div>'
                '<div style="font-size: 14px; color: #F4F8FF; font-weight: 600; margin-bottom: 6px;">'
                '🟢 No active anomalies detected across Nagpur municipal corridors.'
                '</div>'
                '<div style="font-size: 12px; color: #9FB1C9; margin-bottom: 14px;">'
                'Continuous deterministic anomaly triage active across all 15 verified arterial corridors and weather models.'
                '</div>'
                '<svg viewBox="0 0 400 45" preserveAspectRatio="none" style="width: 100%; height: 45px; overflow: visible;">'
                '<defs>'
                '<linearGradient id="anom_green_grad" x1="0%" y1="0%" x2="0%" y2="100%">'
                '<stop offset="0%" stop-color="#35D6A1" stop-opacity="0.32" />'
                '<stop offset="100%" stop-color="#35D6A1" stop-opacity="0.0" />'
                '</linearGradient>'
                '</defs>'
                '<path d="M 0,32 Q 50,28 100,24 T 200,20 T 300,16 T 400,14 L 400,45 L 0,45 Z" fill="url(#anom_green_grad)" />'
                '<path d="M 0,32 Q 50,28 100,24 T 200,20 T 300,16 T 400,14" fill="none" stroke="#35D6A1" stroke-width="2" stroke-linecap="round" />'
                '<circle cx="400" cy="14" r="3.5" fill="#35D6A1" filter="drop-shadow(0 0 6px #35D6A1)" />'
                '</svg>'
                '</div>'
            )
            st.markdown(anom_ok_html, unsafe_allow_html=True)

    # 5. Collapsible System Diagnostics Panel
    with st.expander("🛠️ System Diagnostics & Operational Telemetry", expanded=False):
        diag_col1, diag_col2, diag_col3 = st.columns(3)
        try:
            with get_db_cursor() as cursor:
                cursor.execute("SELECT 1")
                db_ok = True
        except Exception:
            db_ok = False

        with diag_col1:
            st.markdown("#### 🗄️ Database Tier")
            st.markdown(f"**Engine:** MySQL 8.0")
            st.markdown(f"**Target Host:** `{settings.MYSQL_HOST}:{settings.MYSQL_PORT}`")
            st.markdown(f"**Database:** `{settings.MYSQL_DATABASE}`")
            status_text = "🟢 Operational (Connected)" if db_ok else "🔴 Offline"
            st.markdown(f"**Connection Pool:** {status_text}")

        with diag_col2:
            st.markdown("#### ⚡ Streaming & Broker")
            st.markdown(f"**Broker Architecture:** Apache Kafka 3.7 (KRaft)")
            st.markdown(f"**Bootstrap Server:** `{getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')}`")
            st.markdown(f"**Traffic Topic:** `{getattr(settings, 'KAFKA_TRAFFIC_TOPIC', 'urbanpulse.traffic.raw')}`")
            # Safe non-blocking broker reachability check
            import socket
            broker_str = getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
            try:
                b_host, b_port = broker_str.split(":")
                with socket.create_connection((b_host, int(b_port)), timeout=0.5):
                    kafka_status = "🟢 Operational (Broker Active)"
            except Exception:
                kafka_status = "⚪ Standby (Offline simulation mode)"
            st.markdown(f"**Broker Status:** {kafka_status}")

        with diag_col3:
            st.markdown("#### 🔌 Edge Sensing Lab")
            st.markdown(f"**Microcontroller:** Arduino Uno R3 (Prototype)")
            st.markdown(f"**Hardware Port:** `{settings.ARDUINO_PORT}` @ `{settings.ARDUINO_BAUD_RATE}`")
            diag_gw = get_gateway_runtime_status()
            if diag_gw.get("is_alive", False) and diag_gw.get("connection_state") in ("STREAMING", "CONNECTED"):
                hw_link = f"🟢 Connected ({diag_gw.get('active_port') or settings.ARDUINO_PORT})"
            elif diag_gw.get("is_alive", False):
                hw_link = f"🟡 Standby ({diag_gw.get('connection_state')} on {diag_gw.get('active_port') or settings.ARDUINO_PORT})"
            else:
                hw_link = f"⚪ Offline (Gateway Stopped — Port {settings.ARDUINO_PORT})"
            st.markdown(f"**Hardware Link:** {hw_link}")
            st.markdown(f"**Scope:** Local experimental lab (not public street sensor)")

