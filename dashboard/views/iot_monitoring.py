"""
UrbanPulse NEXUS — Edge IoT Lab View.
Prototype Edge-Sensing & Microcontroller Ingestion Laboratory.
Provides strict separation between Real Hardware Mode and Virtual Demo Mode:
- Real Hardware Mode: Only verified physical Arduino nodes, PySerial hardware handshake,
  USB port scanning, device registration, and genuine REAL_HARDWARE telemetry.
- Virtual Demo Mode: Clearly labeled synthetic demonstration environment, isolated simulated
  nodes, and the interactive Virtual Sensor Simulator.
"""

import streamlit as st
import plotly.express as px
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict, Any

from dashboard.theme import (
    render_nexus_header,
    render_kpi_card,
    render_section_header,
    apply_nexus_theme,
)
from dashboard.data_loader import load_iot_readings, load_iot_devices, get_gateway_runtime_status
from config.settings import settings
from database.connection import get_db_cursor
from database.repository import repository
from validation.models import IoTSensorRecord
from iot.serial_gateway.gateway import serial_gateway


def render_iot_monitoring():
    # 1. Header with Edge Hardware Provenance Badge
    render_nexus_header(
        title="🔌 Edge IoT Lab — Hardware Telemetry",
        subtitle="Physical Arduino Uno R3 & HW-484 Sound Sensor Telemetry Interface",
        provenance_badge="PHYSICAL HARDWARE",
    )

    # Fetch physical devices strictly
    mode_devices = load_iot_devices(device_type="PHYSICAL")

    # Load real hardware telemetry strictly
    df_iot = load_iot_readings(
        device_id=None,
        source_type="REAL_HARDWARE",
        limit=500,
    )

    # Gateway runtime process telemetry & host serial port discovery
    gw_info = get_gateway_runtime_status()
    is_gw_running = gw_info.get("is_alive", False)
    gw_conn_state = gw_info.get("connection_state", "DISCONNECTED")
    active_gw_port = gw_info.get("active_port")

    try:
        from serial.tools import list_ports
        detected_ports_raw = list_ports.comports()
        detected_ports = [p.device for p in detected_ports_raw]
    except Exception:
        detected_ports = []

    # Dynamic connection status evaluation
    active_device_count = 0
    for dev in mode_devices:
        if is_gw_running and gw_conn_state == "STREAMING" and (dev["device_id"] == gw_info.get("device_id") or not gw_info.get("device_id")):
            dev["live_status"] = "STREAMING"
            dev["status_desc"] = f"Streaming on {active_gw_port or 'USB'}"
            active_device_count += 1
        elif is_gw_running and gw_conn_state in ("IDLE", "STREAMING", "CONNECTED"):
            dev["live_status"] = "CONNECTED"
            dev["status_desc"] = f"Idle on {active_gw_port or 'USB'}"
            active_device_count += 1
        elif is_gw_running and gw_conn_state == "CONNECTING":
            dev["live_status"] = "CONNECTING"
            dev["status_desc"] = f"Connecting to {active_gw_port or 'USB'}"
        elif is_gw_running and gw_conn_state == "PORT_BUSY":
            dev["live_status"] = "CONNECTED"
            dev["status_desc"] = f"Port {active_gw_port} open in other app"
        elif not is_gw_running:
            dev["live_status"] = "OFFLINE"
            dev["status_desc"] = "Gateway stopped"
        else:
            dev["live_status"] = "OFFLINE"
            dev["status_desc"] = "Hardware Unplugged"

    # 3. Top Metrics KPI Cards (4 Simplified Cards with Restored Decorative Sparklines)
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        dev_count = len(mode_devices)
        if is_gw_running and gw_conn_state in ("STREAMING", "CONNECTED"):
            kpi_delta = "Gateway Connected"
        elif not is_gw_running:
            kpi_delta = "Gateway Stopped"
        else:
            kpi_delta = "Hardware Standby"

        render_kpi_card(
            label="Registered Devices",
            value=dev_count,
            unit=" units",
            delta=kpi_delta,
            provenance=None,
            icon="📟",
            sparkline_type="wave_cyan",
            accent_color="cyan",
        )

    with col2:
        tot_records = len(df_iot)
        render_kpi_card(
            label="Stored Sensor Readings",
            value=f"{tot_records:,}",
            unit=" records",
            delta="Hardware Serial Records (MySQL Archive)",
            provenance=None,
            icon="📡",
            sparkline_type="bars_blue",
            accent_color="blue",
        )

    with col3:
        latest_amp = "—"
        amp_unit = ""
        amp_delta = "No sound readings"
        if not df_iot.empty:
            p2p_df = df_iot[df_iot["sensor_type"] == "SOUND_P2P"]
            raw_snd_df = df_iot[df_iot["sensor_type"] == "SOUND_RAW"]
            if not p2p_df.empty:
                latest_amp = f"{int(p2p_df['reading_value'].iloc[0])}"
                amp_unit = " ADC"
                amp_delta = "Peak-to-Peak (50ms Window)"
            elif not raw_snd_df.empty:
                latest_amp = f"{int(raw_snd_df['reading_value'].iloc[0])}"
                amp_unit = " ADC"
                amp_delta = "Historical Raw Sample"

        render_kpi_card(
            label="Latest Sound Amplitude",
            value=latest_amp,
            unit=amp_unit,
            delta=amp_delta,
            provenance=None,
            icon="🎙️",
            sparkline_type="wave_purple",
            accent_color="purple",
        )

    with col4:
        if is_gw_running and gw_conn_state == "STREAMING":
            gw_status_val = "STREAMING"
            gw_status_delta = f"Streaming on {active_gw_port or 'USB'}"
        elif is_gw_running and gw_conn_state in ("IDLE", "CONNECTED"):
            gw_status_val = "CONNECTED"
            gw_status_delta = f"Idle on {active_gw_port or 'USB'}"
        elif is_gw_running and gw_conn_state == "CONNECTING":
            gw_status_val = "CONNECTING"
            gw_status_delta = f"Connecting on {active_gw_port or 'USB'}"
        elif is_gw_running and gw_conn_state == "PORT_BUSY":
            gw_status_val = "CONNECTED"
            gw_status_delta = f"Port {active_gw_port} in use"
        else:
            gw_status_val = "OFFLINE"
            gw_status_delta = "Gateway process stopped"

        render_kpi_card(
            label="Gateway Status",
            value=gw_status_val,
            unit="",
            delta=gw_status_delta,
            provenance=None,
            icon="🔌",
            sparkline_type="wave_amber" if gw_status_val == "OFFLINE" else "wave_green",
            accent_color="amber" if gw_status_val == "OFFLINE" else "cyan",
        )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # 4. Device Setup & Configuration Expander
    with st.expander("Device Setup & Configuration", expanded=False):
        st.markdown("#### 📝 Physical Microcontroller Node Registration & Discovery")
        st.caption(
            "Detect physical Arduino hardware over USB, verify identity with the urbanpulse_firmware.ino "
            "handshake protocol, and register or update the unit in MySQL."
        )

        discovered_info = None

        if is_gw_running and active_gw_port:
            st.success(
                f"✓ **Arduino verified — connected through active gateway on {active_gw_port}.**"
            )
            discovered_info = {
                "port": active_gw_port,
                "device_id": gw_info.get("device_id") or "ARDUINO_SOUND_01",
                "device_model": "Arduino Uno R3",
                "firmware_version": gw_info.get("firmware_version") or "v1.3.0",
                "mode": "SOUND_P2P_A0",
            }
        else:
            cand_ports = serial_gateway.find_candidate_ports()
            likely_ports = [c["device"] for c in cand_ports if c.get("is_likely_arduino")]

            c_disc1, c_disc2 = st.columns([2, 1])
            with c_disc1:
                port_summary = (
                    f"Host COM Ports Detected: <strong>{len(cand_ports)}</strong>"
                    + (f" (Candidate Arduino on: <code>{', '.join(likely_ports)}</code>)" if likely_ports else " (No obvious Arduino USB bridges)")
                )
                st.markdown(f"<div style='font-size: 13px; color: #9FB1C9; padding-top: 6px;'>{port_summary}</div>", unsafe_allow_html=True)
            with c_disc2:
                do_probe = st.button("🔍 Scan & Handshake Probing", help="Probes free USB serial ports for authentic UrbanPulse firmware.")

            if do_probe:
                with st.spinner("Scanning candidate serial ports for UrbanPulse firmware handshake..."):
                    is_found, f_port, f_meta, f_msg = serial_gateway.discover_arduino()
                    if is_found and f_meta:
                        st.session_state["discovered_arduino"] = f_meta
                        st.success(f"✓ {f_msg}")
                    else:
                        st.session_state.pop("discovered_arduino", None)
                        st.warning(f"⚠️ {f_msg}")

            discovered_info = st.session_state.get("discovered_arduino")

        existing_dev_match = None
        target_match_id = discovered_info["device_id"] if (discovered_info and discovered_info.get("device_id")) else "ARDUINO_SOUND_01"
        existing_dev_match = next((d for d in mode_devices if d["device_id"] == target_match_id), None)

        if existing_dev_match:
            st.markdown(
                f"""
                <div class="nexus-card" style="border-left: 3px solid #35D6A1; background: rgba(53, 214, 161, 0.08); padding: 12px 16px; margin-bottom: 14px;">
                    <span style="font-weight: 700; color: #35D6A1;">✓ Registered Hardware Unit Recognized:</span> <strong>{existing_dev_match['device_name']}</strong> (<code>{existing_dev_match['device_id']}</code>)<br/>
                    <span style="font-size: 12px; color: #9FB1C9;">Currently assigned to port <strong>{existing_dev_match.get('port_assignment') or 'AUTO'}</strong>. Submitting will update its port configuration and preserve all historical telemetry records.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif not discovered_info:
            st.markdown(
                """
                <div class="nexus-card" style="border-left: 3px solid #FFBF69; background: rgba(255, 191, 105, 0.08); padding: 12px 16px; margin-bottom: 14px;">
                    <span style="font-weight: 700; color: #FFBF69;">⚪ No Physical Arduino Currently Detected</span><br/>
                    <span style="font-size: 12px; color: #9FB1C9;">Previously registered devices remain fully accessible. Connect your Arduino Uno via USB and click <strong>Scan & Handshake Probing</strong>, or register with <strong>Auto Detect (Recommended)</strong> below.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with st.form("register_arduino_form"):
            rf_col1, rf_col2 = st.columns(2)

            default_dev_name = existing_dev_match["device_name"] if existing_dev_match else (
                f"Nagpur Lab Arduino ({discovered_info['device_id']})" if discovered_info else "Nagpur Sound Sensor Unit"
            )
            default_dev_id = discovered_info["device_id"] if discovered_info else (
                existing_dev_match["device_id"] if existing_dev_match else "ARDUINO_SOUND_01"
            )

            with rf_col1:
                reg_dev_name = st.text_input(
                    "Descriptive Device Name *",
                    value=default_dev_name,
                    help="Human-readable name identifying this physical installation.",
                )
                reg_dev_id = st.text_input(
                    "Hardware Device Identifier *",
                    value=default_dev_id,
                    help="Stable device ID obtained from firmware handshake. Stable across COM port changes.",
                )
                reg_board_model = st.selectbox(
                    "Arduino Board Model",
                    ["Arduino Uno R3 (ATmega328P)", "Arduino Nano", "Arduino Mega 2560"],
                    index=0,
                    help="Microcontroller hardware architecture.",
                )

            with rf_col2:
                reg_location = st.selectbox(
                    "Assigned Laboratory Location",
                    ["LOC_NAGPUR", "LOC_PUNE"],
                    index=0,
                    help="Municipal testbed location associated with this edge node.",
                )
                reg_sensors = st.multiselect(
                    "Connected Physical Sensors",
                    [
                        "Sound Sensor (Peak-to-Peak ADC)",
                        "Sound Sensor (Raw ADC)",
                        "DHT11 (Temp & Humidity)",
                        "MQ-135 (Gas ADC)",
                        "LDR (Light ADC)",
                    ],
                    default=["Sound Sensor (Peak-to-Peak ADC)", "Sound Sensor (Raw ADC)"],
                    help="Physical sensors wired to the board.",
                )

                port_options = ["Auto Detect (Recommended)"]
                if detected_ports:
                    port_options += [f"{p} (Detected Port)" for p in detected_ports]

                reg_port_selection = st.selectbox(
                    "COM Port Assignment Mode",
                    port_options,
                    index=0,
                    help="Auto Detect dynamically tracks whichever COM port Windows assigns to this Arduino.",
                )

            with st.expander("⚙️ Advanced Connection Settings", expanded=False):
                reg_baud = st.selectbox("UART Baud Rate", [9600, 19200, 38400, 57600, 115200], index=0)
                manual_port_override = st.text_input("Manual Port Override (Optional)", placeholder="e.g. COM7", help="Leave blank for Auto Detect.")

            submit_reg = st.form_submit_button("💾 Save / Update Device in MySQL", type="primary")

        if submit_reg:
            if manual_port_override.strip():
                final_port = manual_port_override.strip().upper()
            elif reg_port_selection.startswith("Auto"):
                final_port = "AUTO"
            else:
                final_port = reg_port_selection.split(" ")[0]

            sensor_keys = []
            for s in reg_sensors:
                if "Peak-to-Peak" in s:
                    sensor_keys.append("SOUND_P2P")
                elif "Raw ADC" in s and "Sound" in s:
                    sensor_keys.append("SOUND_RAW")
                elif "DHT" in s:
                    sensor_keys.append("DHT11")
                elif "MQ" in s:
                    sensor_keys.append("MQ-135")
                elif "LDR" in s:
                    sensor_keys.append("LDR")
                else:
                    sensor_keys.append(s.split(" ")[0])
            sensor_str = ",".join(sensor_keys)

            reg_ok, reg_msg = serial_gateway.register_hardware_device(
                device_id=reg_dev_id.strip(),
                device_name=reg_dev_name.strip(),
                device_model=reg_board_model.split(" (")[0],
                location_id=reg_location,
                connected_sensors=sensor_str,
                port_assignment=final_port,
            )
            if reg_ok:
                st.success(f"✓ {reg_msg}")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(reg_msg)

    # 5. Gateway Monitoring
    render_section_header(
        title="Gateway Monitoring",
        subtitle="Serial port connection status and runtime microcontroller link health",
    )

    # Probe button
    col_b1, _ = st.columns([1, 1])
    with col_b1:
        if st.button("🔄 Refresh Host USB / Serial State"):
            st.cache_data.clear()
            st.rerun()

    # Granular Connection Classification
    has_db_readings = not df_iot.empty
    
    if is_gw_running:
        if gw_conn_state == "STREAMING":
            live_status_tag = "🟢 CONNECTED & STREAMING"
            live_status_color = "#35D6A1"
            status_explanation = "Gateway process is running and actively processing genuine microcontroller packets."
        elif gw_conn_state == "IDLE":
            live_status_tag = "🟡 CONNECTED (IDLE)"
            live_status_color = "#FFBF69"
            status_explanation = "Arduino connection established, but recent sensor packets are not arriving."
        elif gw_conn_state == "PORT_BUSY":
            live_status_tag = "🟠 PORT BUSY"
            live_status_color = "#FF9F43"
            status_explanation = "COM port is open in another application (e.g. Arduino IDE Serial Monitor)."
        else:
            live_status_tag = "🔴 DEVICE DISCONNECTED"
            live_status_color = "#FF647C"
            status_explanation = "Gateway is active and scanning for Arduino, but no matching device is currently plugged into USB."
    else:
        if has_db_readings:
            live_status_tag = "⚪ GATEWAY STOPPED (HISTORICAL DATA AVAILABLE)"
            live_status_color = "#9FB1C9"
            status_explanation = "Gateway process is not running. Historical sensor records in MySQL remain fully accessible below."
        else:
            live_status_tag = "⚪ GATEWAY STOPPED"
            live_status_color = "#9FB1C9"
            status_explanation = "Gateway process is stopped. Run the serial gateway to start streaming."

    st.markdown(
        f"""
        <div class="nexus-card" style="border-left: 3px solid {live_status_color}; background: rgba(15, 23, 42, 0.7); padding: 14px 20px; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-weight: 700; color: {live_status_color}; font-size: 14px; white-space: nowrap;">{live_status_tag}</span>
                <span style="font-size: 11px; color: #9FB1C9; font-family: monospace;">PID: {gw_info.get('pid') or 'None'}</span>
            </div>
            <div style="font-size: 12px; color: #F4F8FF; line-height: 1.5;">
                {status_explanation}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    hw_s1, hw_s2 = st.columns(2)
    with hw_s1:
        target_reg_dev = mode_devices[0] if mode_devices else {}
        reg_port_mode = "AUTO" if str(target_reg_dev.get("port_assignment") or "").upper() in ["AUTO", ""] else "MANUAL"
        last_known_port = target_reg_dev.get("port_assignment") or "Unassigned"

        detected_ports_str = (
            ", ".join([f"<code>{p}</code>" for p in detected_ports])
            if detected_ports
            else "<em>None detected (Hardware unplugged)</em>"
        )

        st.markdown(
            f"""
            <div class="nexus-card">
                <div style="font-size: 14px; font-weight: 700; color: #F4F8FF; margin-bottom: 8px;">Hardware Bus & Port Telemetry</div>
                <div style="font-size: 13px; line-height: 2; color: #9FB1C9;">
                    <div>Port Selection Mode: <strong style="color: #29D8F4;">{reg_port_mode}</strong> (Config: <code>{settings.ARDUINO_PORT}</code>)</div>
                    <div>Currently Detected COM Port: <strong style="color: #F4F8FF;">{active_gw_port or ('None detected' if not detected_ports else detected_ports[0])}</strong></div>
                    <div>Last Known Assigned Port: <strong style="color: #F4F8FF;">{last_known_port}</strong></div>
                    <div>Host Detected Ports: {detected_ports_str}</div>
                    <div>UART Baud Rate: <strong style="color: #F4F8FF;">{settings.ARDUINO_BAUD_RATE} bps</strong></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with hw_s2:
        last_pkt_ts = gw_info.get("last_packet_time") or (
            df_iot["timestamp"].iloc[0].strftime("%Y-%m-%d %H:%M:%S") if not df_iot.empty else "No packets received yet"
        )
        gw_proc_badge = '<span style="color: #35D6A1; font-weight: 700; white-space: nowrap;">🟢 RUNNING</span>' if is_gw_running else '<span style="color: #FF647C; font-weight: 700; white-space: nowrap;">🔴 STOPPED</span>'

        st.markdown(
            f"""
            <div class="nexus-card">
                <div style="font-size: 14px; font-weight: 700; color: #F4F8FF; margin-bottom: 8px;">Gateway Process & Runtime Health</div>
                <div style="font-size: 13px; line-height: 2; color: #9FB1C9;">
                    <div>Gateway Process Status: {gw_proc_badge} (PID: <code>{gw_info.get('pid') or '—'}</code>)</div>
                    <div>Registered Device ID: <code style="color: #29D8F4;">{target_reg_dev.get('device_id') or 'ARDUINO_SOUND_01'}</code></div>
                    <div>Last Received Packet: <strong style="color: #F4F8FF;">{last_pkt_ts}</strong></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Telemetry Feed (Poll MySQL)"):
        st.cache_data.clear()
        st.rerun()

    # 6. Physical Sound Sensor Hardware Section
    df_sound = (
        df_iot[df_iot["sensor_type"].isin(["SOUND_P2P", "SOUND_RAW"])]
        if not df_iot.empty
        else pd.DataFrame()
    )

    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
    render_section_header(
        title="🎙️ Sound Sensor Hardware Interface",
        subtitle="Live acoustic amplitude & microphone sampling verification on physical Arduino Uno R3",
        badge="SOUND EXPERIMENT",
    )

    # Technical Disclosure Card (Part 6)
    st.markdown(
        """
        <div class="nexus-card" style="border-left: 3px solid #29D8F4; background: rgba(41, 216, 244, 0.05); padding: 14px 18px; margin-bottom: 14px;">
            <div style="font-size: 13px; font-weight: 700; color: #29D8F4; margin-bottom: 4px;">
                🎙️ Physical Hardware Verification: HW-484 Sound Sensor (Pin A0 — 50ms Windowed Sampling)
            </div>
            <div style="font-size: 12.5px; color: #F4F8FF; line-height: 1.55;">
                The sensor produces uncalibrated ADC peak-to-peak amplitude measurements. Actual values depend on the hardware module, circuit, environmental conditions, and acoustic signal.
            </div>
            <div style="font-size: 11.5px; color: #9FB1C9; margin-top: 6px; line-height: 1.5;">
                • ADC amplitude represents electrical peak-to-peak difference (max &minus; min ADC in 50ms), not calibrated sound pressure levels in decibels (dB SPL).<br/>
                • A transient amplitude spike indicates a change in measured electrical amplitude, not automatically a specific verified sound event.<br/>
                • The dashboard visualizes actual recorded sensor telemetry from MySQL without inventing, amplifying, or fabricating measurements.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Interactive View Controls (Time Filter, Stream Selector, Y-Axis Scaling)
    c_ctrl1, c_ctrl2, c_ctrl3 = st.columns([2, 2, 2])
    with c_ctrl1:
        time_filter = st.selectbox(
            "Observation Time Window",
            ["All Available History", "Last 1 Hour", "Last 15 Minutes", "Last 5 Minutes", "Last 1 Minute"],
            index=0,
            help="Filters observation period using database observation timestamps.",
        )
    with c_ctrl2:
        stream_mode = st.selectbox(
            "Measurement Metric Stream",
            ["SOUND_P2P (Peak-to-Peak Amplitude)", "SOUND_RAW (Historical Raw Samples)", "All Measurements (Distinct Series)"],
            index=0,
            help="Select whether to view dynamic peak-to-peak amplitude or historical raw ADC samples.",
        )
    with c_ctrl3:
        yaxis_mode = st.radio(
            "Y-Axis Scaling",
            ["Auto Scale (Recommended)", "Full ADC Range (0–1023)"],
            index=0,
            horizontal=True,
            help="Auto Scale adjusts the vertical axis to highlight low-amplitude variations without modifying stored data.",
        )

    # Apply Time-Based Filtering (Part 5.D)
    df_sound_filtered = df_sound.copy()
    if not df_sound_filtered.empty and time_filter != "All Available History":
        latest_ts = df_sound_filtered["timestamp"].max()
        if time_filter == "Last 1 Minute":
            df_sound_filtered = df_sound_filtered[df_sound_filtered["timestamp"] >= latest_ts - pd.Timedelta(minutes=1)]
        elif time_filter == "Last 5 Minutes":
            df_sound_filtered = df_sound_filtered[df_sound_filtered["timestamp"] >= latest_ts - pd.Timedelta(minutes=5)]
        elif time_filter == "Last 15 Minutes":
            df_sound_filtered = df_sound_filtered[df_sound_filtered["timestamp"] >= latest_ts - pd.Timedelta(minutes=15)]
        elif time_filter == "Last 1 Hour":
            df_sound_filtered = df_sound_filtered[df_sound_filtered["timestamp"] >= latest_ts - pd.Timedelta(hours=1)]

    # Strict P2P separation for KPIs (Part 4.B)
    df_p2p_all = df_sound[df_sound["sensor_type"] == "SOUND_P2P"]
    df_p2p_win = df_sound_filtered[df_sound_filtered["sensor_type"] == "SOUND_P2P"]
    df_raw_win = df_sound_filtered[df_sound_filtered["sensor_type"] == "SOUND_RAW"]

    # Acoustic Threshold Slider & Indicator (Part 5.E & Part 6)
    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    t_col1, t_col2 = st.columns([2, 1])

    with t_col1:
        sound_threshold = st.slider(
            "Acoustic Activity Threshold (ADC Peak-to-Peak)",
            min_value=1,
            max_value=500,
            value=5,
            step=1,
            help="Uncalibrated electrical amplitude threshold. A crossing indicates transient electrical waveform change.",
        )
        st.caption(
            "User-defined electrical amplitude classification boundary. "
            "Indicates transient analog waveform deviation; does not alter hardware ADC sampling or claim calibrated acoustic sound-level/speech recognition."
        )

    with t_col2:
        # Compare threshold strictly against SOUND_P2P values
        if not df_p2p_win.empty:
            cur_adc = float(df_p2p_win["reading_value"].iloc[0])
            if cur_adc >= sound_threshold:
                st.markdown(
                    f"""
                    <div style="padding: 10px 14px; background: rgba(255, 100, 124, 0.15); border: 1px solid #FF647C; border-radius: 8px; margin-top: 14px;">
                        <span style="font-weight: 700; color: #FF647C;">⚡ Above Threshold</span><br/>
                        <span style="font-size: 12px; color: #F4F8FF;">Current: <strong>{int(cur_adc)} ADC P2P</strong> (&ge; {sound_threshold})</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div style="padding: 10px 14px; background: rgba(53, 214, 161, 0.15); border: 1px solid #35D6A1; border-radius: 8px; margin-top: 14px;">
                        <span style="font-weight: 700; color: #35D6A1;">🔈 Below Baseline Threshold</span><br/>
                        <span style="font-size: 12px; color: #F4F8FF;">Current: <strong>{int(cur_adc)} ADC P2P</strong> (&lt; {sound_threshold})</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                """
                <div style="padding: 10px 14px; background: rgba(159, 177, 201, 0.1); border: 1px solid rgba(159, 177, 201, 0.3); border-radius: 8px; margin-top: 14px;">
                    <span style="font-weight: 600; color: #9FB1C9;">⚪ Awaiting P2P Packets</span><br/>
                    <span style="font-size: 12px; color: #9FB1C9;">Threshold applies to SOUND_P2P stream</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Chart Dataset Preparation with Stream Separation (Part 5.B & 5.C)
    if stream_mode.startswith("SOUND_P2P"):
        df_plot = df_sound_filtered[df_sound_filtered["sensor_type"] == "SOUND_P2P"]
    elif stream_mode.startswith("SOUND_RAW"):
        df_plot = df_sound_filtered[df_sound_filtered["sensor_type"] == "SOUND_RAW"]
    else:
        df_plot = df_sound_filtered

    if not df_plot.empty:
        st.markdown("##### 📈 Sound Amplitude Over Time (ADC Peak-to-Peak)")
        x_axis_col = "timestamp_ist_naive" if "timestamp_ist_naive" in df_plot.columns else "timestamp"
        fig_sound = px.line(
            df_plot.sort_values(x_axis_col),
            x=x_axis_col,
            y="reading_value",
            color="sensor_type",
            labels={
                "reading_value": "Peak-to-Peak ADC Amplitude",
                x_axis_col: "Observation Timestamp (IST)",
                "sensor_type": "Measurement Series",
            },
            color_discrete_map={"SOUND_P2P": "#29D8F4", "SOUND_RAW": "#9FB1C9"},
        )

        # Show threshold horizontal line only when SOUND_P2P series is rendered
        if (df_plot["sensor_type"] == "SOUND_P2P").any():
            fig_sound.add_hline(
                y=sound_threshold,
                line_dash="dash",
                line_color="#FF647C",
                annotation_text=f"Threshold ({sound_threshold} ADC P2P)",
                annotation_position="top right",
            )

        # Dynamic Y-Axis Scaling (Part 5.A)
        if yaxis_mode.startswith("Auto"):
            max_observed = df_plot["reading_value"].max()
            y_upper = max(10, int(max_observed * 1.35 + 4)) if pd.notnull(max_observed) else 20
            fig_sound.update_yaxes(range=[0, y_upper])
        else:
            fig_sound.update_yaxes(range=[0, 1050])

        apply_nexus_theme(fig_sound, height=330)
        st.plotly_chart(fig_sound, use_container_width=True)
    else:
        st.markdown(
            f"""
            <div class="nexus-card" style="text-align: center; padding: 28px 20px; border: 1px dashed rgba(41, 216, 244, 0.3);">
                <div style="font-size: 28px; margin-bottom: 8px;">🎙️</div>
                <div style="font-size: 14px; font-weight: 700; color: #F4F8FF; margin-bottom: 4px;">
                    No Sound Records Found for Selected Filter
                </div>
                <div style="font-size: 12px; color: #9FB1C9; max-width: 500px; margin: 0 auto; line-height: 1.5;">
                    No readings matching <code>{stream_mode}</code> in window <code>{time_filter}</code>.
                    Select <em>All Available History</em> or start the gateway (<code>python -m iot.serial_gateway.gateway</code>).
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 7. Mode-Specific Sensor Telemetry Charts
    with st.expander("Advanced: Multi-Sensor Telemetry", expanded=False):
        st.markdown("##### 🔬 Multi-Sensor Telemetry Stream")
        st.caption("Chronological recording of authentic microcontroller packets in MySQL across all sensor channels.")
        if not df_iot.empty:
            # Check if multiple sensor types exist with differing units
            sensor_types_present = df_iot["sensor_type"].unique()

            # Split temperature/humidity (°C / %) from raw analog ADC (0-1023)
            ambient_mask = df_iot["sensor_type"].isin(["DHT11_TEMP", "DHT11_HUMIDITY"])
            analog_mask = df_iot["sensor_type"].isin(["MQ135_RAW", "LDR_LIGHT", "SOUND_RAW", "SOUND_P2P"])

            df_ambient = df_iot[ambient_mask]
            df_analog = df_iot[analog_mask]

            x_col = "timestamp_ist_naive" if "timestamp_ist_naive" in df_iot.columns else "timestamp"

            if not df_ambient.empty and not df_analog.empty:
                ch_col1, ch_col2 = st.columns(2)
                with ch_col1:
                    st.markdown("##### 🌡️ Ambient Atmosphere (Temperature & Humidity)")
                    fig_amb = px.line(
                        df_ambient.sort_values(x_col),
                        x=x_col,
                        y="reading_value",
                        color="sensor_type",
                        labels={"reading_value": "Value (°C / %)", x_col: "Timestamp (IST)"},
                        color_discrete_sequence=["#29D8F4", "#4F8CFF"],
                    )
                    apply_nexus_theme(fig_amb, height=340)
                    st.plotly_chart(fig_amb, use_container_width=True)

                with ch_col2:
                    st.markdown("##### 🧪 Analog Gas & Light Sensors (Raw ADC: 0–1023)")
                    fig_ana = px.line(
                        df_analog.sort_values(x_col),
                        x=x_col,
                        y="reading_value",
                        color="sensor_type",
                        labels={"reading_value": "Raw ADC Level", x_col: "Timestamp (IST)"},
                        color_discrete_sequence=["#FFBF69", "#35D6A1"],
                    )
                    apply_nexus_theme(fig_ana, height=340)
                    st.plotly_chart(fig_ana, use_container_width=True)

            else:
                # Single combined plot when only one category is present
                fig_iot = px.line(
                    df_iot.sort_values(x_col),
                    x=x_col,
                    y="reading_value",
                    color="sensor_type",
                    labels={"reading_value": "Telemetry Value", x_col: "Timestamp (IST)"},
                    color_discrete_sequence=["#29D8F4", "#4F8CFF", "#9685FF", "#35D6A1"],
                )
                apply_nexus_theme(fig_iot, height=350)
                st.plotly_chart(fig_iot, use_container_width=True)

        else:
            st.markdown(
                f"""
                <div class="nexus-card" style="text-align: center; padding: 36px 20px; border: 1px dashed rgba(41, 216, 244, 0.3);">
                    <div style="font-size: 32px; margin-bottom: 10px;">🔌</div>
                    <div style="font-size: 15px; font-weight: 700; color: #F4F8FF; margin-bottom: 6px;">
                        No Real Hardware Data Available
                    </div>
                    <div style="font-size: 13px; color: #9FB1C9; max-width: 540px; margin: 0 auto; line-height: 1.6;">
                        No genuine microcontroller readings have been recorded for the selected filter (<code>{selected_node_label}</code>).
                        To stream real measurements, plug in an Arduino Uno running <code>urbanpulse_firmware.ino</code> and
                        launch the PySerial gateway (<code>python iot/serial_gateway/gateway.py</code>).
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # 7. Recent Ingestion Packets Explorer
    with st.expander("Recent Sensor Readings", expanded=False):
        if not df_iot.empty:
            avail_sensors = list(df_iot["sensor_type"].dropna().unique())
            sensor_options = ["All Sensors"]
            for pref in ["SOUND_P2P", "SOUND_RAW"]:
                if pref in avail_sensors and pref not in sensor_options:
                    sensor_options.append(pref)
            for s in sorted(avail_sensors):
                if s not in sensor_options:
                    sensor_options.append(s)

            filter_col1, _ = st.columns([2, 2])
            with filter_col1:
                sel_modality = st.selectbox(
                    "Sensor Modality Filter",
                    options=sensor_options,
                    index=0,
                    key="real_telemetry_modality_select",
                )

            df_table = df_iot.copy()
            if sel_modality != "All Sensors":
                df_table = df_table[df_table["sensor_type"] == sel_modality]

            # Ensure Timestamp (IST) column is formatted properly
            if "timestamp_display" in df_table.columns:
                df_table["Timestamp (IST)"] = df_table["timestamp_display"]
            elif "timestamp_ist" in df_table.columns:
                df_table["Timestamp (IST)"] = df_table["timestamp_ist"].dt.strftime("%d %b %Y, %I:%M:%S %p IST")
            else:
                df_table["Timestamp (IST)"] = df_table["timestamp"].astype(str)

            display_cols = []
            rename_map = {
                "event_id": "Event ID",
                "device_id": "Device ID",
                "sensor_type": "Sensor Type",
                "reading_value": "Reading Value",
                "unit": "Unit",
                "Timestamp (IST)": "Timestamp (IST)",
                "source_type": "Source Type",
            }
            for c in ["event_id", "device_id", "sensor_type", "reading_value", "unit", "Timestamp (IST)", "source_type"]:
                if c in df_table.columns:
                    display_cols.append(c)

            df_render = df_table[display_cols].rename(columns=rename_map)
            st.dataframe(df_render.head(50), use_container_width=True)
        else:
            st.info("No real hardware sensor records in MySQL for selected filter.")
