"""
UrbanPulse NEXUS — Anomaly Center View.
Centralized incident command for monitoring, triaging, and resolving
traffic congestion spikes, environmental hazards, and hardware faults across Nagpur.
"""

import streamlit as st
import plotly.express as px
import pandas as pd
from datetime import datetime

from dashboard.theme import (
    render_nexus_header,
    render_kpi_card,
    render_section_header,
    apply_nexus_theme,
)
from dashboard.data_loader import load_anomalies
from database.connection import get_db_cursor
from config.corridors import NAGPUR_CORRIDORS_GEO


def render_anomaly_center():
    # 1. Header with Operations Badge
    render_nexus_header(
        title="🚨 Anomaly Center — Urban Alert Operations",
        subtitle="Deterministic rule-based incident triage across Nagpur corridors and environment",
        provenance_badge="ALERT OPERATIONS",
    )

    # 2. Filters & Controls Bar
    col1, col2, col3 = st.columns([1.2, 1.2, 1.4])
    with col1:
        status_filter = st.selectbox("Incident Triage Status", ["ALL", "ACTIVE", "ACKNOWLEDGED", "RESOLVED"], index=1)
    with col2:
        severity_filter = st.selectbox("Severity Classification", ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"], index=0)
    with col3:
        source_opt = st.selectbox("Operational Provenance", ["REAL_API (Live Operational)", "ALL (Include Archived Simulation)"], index=0)
        source_filter = "REAL_API" if "REAL_API" in source_opt else "ALL"

    # Query strictly filtered for Nagpur
    df_anom = load_anomalies(status=status_filter, location_id="LOC_NAGPUR", source_type=source_filter, limit=500)
    if severity_filter != "ALL" and not df_anom.empty:
        df_anom = df_anom[df_anom["severity"] == severity_filter]

    # 3. Incident KPI Cards
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        render_kpi_card(
            label="Total Incidents",
            value=len(df_anom),
            unit=" records",
            provenance="TRIAGE",
            icon="🚨",
        )
    with col_m2:
        crit_count = int((df_anom["severity"] == "CRITICAL").sum()) if not df_anom.empty else 0
        render_kpi_card(
            label="Critical Hazards",
            value=crit_count,
            unit=" alerts",
            delta="Urgent Action" if crit_count > 0 else "None",
            provenance="CRITICAL",
            icon="🔥",
        )
    with col_m3:
        high_count = int((df_anom["severity"] == "HIGH").sum()) if not df_anom.empty else 0
        render_kpi_card(
            label="High Bottlenecks",
            value=high_count,
            unit=" alerts",
            delta="Active Review" if high_count > 0 else "None",
            provenance="WARNING",
            icon="⚠️",
        )
    with col_m4:
        active_count = int((df_anom["status"] == "ACTIVE").sum()) if not df_anom.empty else 0
        render_kpi_card(
            label="Pending Resolution",
            value=active_count,
            unit=" unaddressed",
            delta="In Queue" if active_count > 0 else "Clear",
            provenance="ACTIVE",
            icon="⏱️",
        )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # 4. Chart Row: Severity and Source Breakdown
    render_section_header(
        title="Incident Analytics & Provenance Distribution",
        subtitle="Classification by hazard severity and originating data ingestion stream",
        badge="HAZARD METRICS",
    )
    if df_anom.empty:
        st.info("ℹ️ No incident distribution data available for selected filters. Monitored corridors operating within nominal parameters.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 📊 Incidents by Severity Tier")
            sev_counts = df_anom["severity"].value_counts().reset_index()
            sev_counts.columns = ["Severity", "Count"]
            fig_sev = px.bar(
                sev_counts,
                x="Severity",
                y="Count",
                color="Severity",
                color_discrete_map={
                    "CRITICAL": "#FF647C",
                    "HIGH": "#FFBF69",
                    "MEDIUM": "#4F8CFF",
                    "LOW": "#35D6A1",
                },
            )
            apply_nexus_theme(fig_sev, height=310)
            st.plotly_chart(fig_sev, use_container_width=True)

        with c2:
            st.markdown("#### 📡 Incidents by Provenance Stream")
            src_counts = df_anom["source_type"].value_counts().reset_index()
            src_counts.columns = ["Source", "Count"]
            fig_src = px.pie(
                src_counts,
                names="Source",
                values="Count",
                hole=0.55,
                color_discrete_sequence=["#29D8F4", "#9685FF", "#4F8CFF", "#FFBF69"],
            )
            apply_nexus_theme(fig_src, height=310)
            st.plotly_chart(fig_src, use_container_width=True)

    # 5. Triage Incident Cards Feed
    render_section_header(
        title="Incident Triage Command Queue — Nagpur",
        subtitle="Active alert triage and operational response resolution for municipal events",
        badge="TRIAGE QUEUE",
    )

    st.markdown(
        """
        <div style="background: rgba(41, 216, 244, 0.05); border: 1px solid rgba(41, 216, 244, 0.2); border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; font-size: 12.5px; color: #DCE9FA;">
            <strong style="color: #29D8F4;">ℹ️ Administrative Triage Protocol:</strong>
            Incidents are deterministically triggered by rule-based engines evaluating genuine TomTom Flow API telemetry and official atmospheric models.
            Resolving an incident records operator administrative disposition in MySQL (<code>ACTIVE → ACKNOWLEDGED → RESOLVED</code>); it serves as operational triage acknowledgement and does <em>not</em> imply or guarantee that real-world road or weather conditions have physically cleared.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if df_anom.empty:
        st.success("✓ Zero operational incidents matching filters across Nagpur municipal sensors. All networks operating within nominal parameters.")

    for _, row in df_anom.iterrows():
        sev = row["severity"]
        border_col = {
            "CRITICAL": "#FF647C",
            "HIGH": "#FFBF69",
            "MEDIUM": "#4F8CFF",
            "LOW": "#35D6A1",
        }.get(sev, "#9FB1C9")

        src_type = row.get("source_type", "REAL_API")
        badge_class = "badge-real-api" if src_type == "REAL_API" else ("badge-critical" if sev == "CRITICAL" else "badge-simulated")

        status_color = {
            "ACTIVE": "#FF647C",
            "ACKNOWLEDGED": "#FFBF69",
            "RESOLVED": "#35D6A1",
        }.get(row["status"], "#9FB1C9")

        seg_id = row.get("segment_id")
        road_name_val = row.get("road_name")
        if pd.isna(road_name_val) or not road_name_val:
            if seg_id and seg_id in NAGPUR_CORRIDORS_GEO:
                road_name_val = NAGPUR_CORRIDORS_GEO[seg_id].get("road_name", seg_id)
            else:
                road_name_val = "Nagpur Municipal Sector"
        road_display = f"{road_name_val} ({seg_id})" if seg_id else road_name_val
        ts_detected = row.get("timestamp_display", str(row["timestamp"]))

        ack_info_html = ""
        if row["status"] == "ACKNOWLEDGED" and row.get("resolution_notes"):
            ack_info_html = f"""
            <div style="margin-top: 8px; padding: 8px 12px; background: rgba(255, 191, 105, 0.08); border-left: 2px solid #FFBF69; border-radius: 4px; font-size: 12px;">
                <span style="color: #FFBF69; font-weight: 600;">👁️ Acknowledgement Note:</span> <em style="color: #DCE9FA;">"{row['resolution_notes']}"</em>
            </div>
            """

        resolved_info_html = ""
        if row["status"] == "RESOLVED":
            res_at = row.get("resolved_at")
            if pd.notna(res_at):
                try:
                    res_dt = pd.to_datetime(res_at)
                    if res_dt.tzinfo is None:
                        res_at_ist = res_dt.tz_localize("UTC").tz_convert("Asia/Kolkata")
                    else:
                        res_at_ist = res_dt.tz_convert("Asia/Kolkata")
                    res_at_str = res_at_ist.strftime("%d %b %Y, %I:%M:%S %p IST")
                except Exception:
                    res_at_str = str(res_at)
            else:
                res_at_str = "Recorded"
            res_note = row.get("resolution_notes") or "Operator marked resolved"
            resolved_info_html = f"""
            <div style="margin-top: 8px; padding: 8px 12px; background: rgba(53, 214, 161, 0.08); border-left: 2px solid #35D6A1; border-radius: 4px; font-size: 12px;">
                <span style="color: #35D6A1; font-weight: 600;">✓ Resolved at:</span> <span style="color: #F4F8FF;">{res_at_str}</span><br/>
                <span style="color: #9FB1C9;">Disposition Note:</span> <em style="color: #DCE9FA;">"{res_note}"</em>
            </div>
            """

        st.markdown(
            f"""
            <div class="nexus-card" style="border-left: 3px solid {border_col}; padding: 16px 20px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div>
                        <span class="badge-nexus {badge_class}">[{sev}] {row['anomaly_type']}</span>
                        <span style="font-size: 12px; color: #9FB1C9; margin-left: 10px;">ID: <code>{row['anomaly_id']}</code></span>
                    </div>
                    <span class="badge-nexus badge-prototype">SRC: {row['source_type']}</span>
                </div>
                <div style="font-size: 13.5px; color: #F4F8FF; margin-bottom: 6px; line-height: 1.4;">
                    {row['description']}
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 16px; font-size: 11.5px; color: #9FB1C9;">
                    <span>🕒 Detected: <strong style="color: #F4F8FF;">{ts_detected}</strong></span>
                    <span>📍 Corridor: <strong style="color: #29D8F4;">{road_display}</strong></span>
                    <span>⚡ Status: <strong style="color: {status_color};">{row['status']}</strong></span>
                </div>
                {ack_info_html}
                {resolved_info_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Incident action workflow (ACTIVE -> ACKNOWLEDGED / RESOLVED, ACKNOWLEDGED -> RESOLVED)
        if row["status"] in ("ACTIVE", "ACKNOWLEDGED"):
            with st.expander(f"⚙️ Triage Actions — Incident {row['anomaly_id']}", expanded=False):
                if row["status"] == "ACTIVE":
                    triage_tab_ack, triage_tab_res = st.tabs(["👁️ Acknowledge Alert", "✓ Resolve Incident"])
                    with triage_tab_ack:
                        with st.form(key=f"ack_form_{row['anomaly_id']}"):
                            ack_note = st.text_input(
                                "Operator Acknowledgement Note (Optional):",
                                placeholder="e.g., Traffic operations monitoring corridor; field unit alerted",
                                key=f"ack_note_input_{row['anomaly_id']}",
                            )
                            ack_submitted = st.form_submit_button("👁️ Confirm Acknowledgement")
                            if ack_submitted:
                                clean_ack = ack_note.strip() if ack_note else None
                                with get_db_cursor(commit=True) as cursor:
                                    cursor.execute(
                                        """
                                        UPDATE anomalies
                                        SET status = 'ACKNOWLEDGED',
                                            resolution_notes = COALESCE(%(note)s, resolution_notes)
                                        WHERE anomaly_id = %(id)s AND status = 'ACTIVE'
                                        """,
                                        {"id": row["anomaly_id"], "note": clean_ack if clean_ack else None}
                                    )
                                st.success(f"Incident {row['anomaly_id']} marked as ACKNOWLEDGED.")
                                st.cache_data.clear()
                                st.rerun()

                    with triage_tab_res:
                        with st.form(key=f"res_form_active_{row['anomaly_id']}"):
                            st.markdown(
                                "<div style='font-size: 12px; color: #9FB1C9; margin-bottom: 6px;'>"
                                "⚠️ <strong>Mandatory Note:</strong> Enter resolution rationale or operational disposition. "
                                "Blank or whitespace-only notes will be rejected.<br/>"
                                "<em>Note: Administrative triage action only; does not physically clear real-world road conditions.</em>"
                                "</div>",
                                unsafe_allow_html=True,
                            )
                            res_note = st.text_area(
                                "Resolution Notes (Mandatory):",
                                placeholder="Detail actions taken, verified observations, or closure rationale...",
                                key=f"res_note_active_{row['anomaly_id']}",
                                height=80,
                            )
                            res_submitted = st.form_submit_button("✓ Confirm Direct Resolution", type="primary")
                            if res_submitted:
                                if not res_note or not res_note.strip():
                                    st.error("❌ Resolution notes are mandatory. Please provide a substantive explanation before resolving.")
                                else:
                                    with get_db_cursor(commit=True) as cursor:
                                        cursor.execute(
                                            """
                                            UPDATE anomalies
                                            SET status = 'RESOLVED',
                                                resolution_notes = %(notes)s,
                                                resolved_at = UTC_TIMESTAMP()
                                            WHERE anomaly_id = %(id)s AND status IN ('ACTIVE', 'ACKNOWLEDGED')
                                            """,
                                            {"id": row["anomaly_id"], "notes": res_note.strip()}
                                        )
                                    st.success(f"✓ Incident {row['anomaly_id']} successfully RESOLVED.")
                                    st.cache_data.clear()
                                    st.rerun()

                elif row["status"] == "ACKNOWLEDGED":
                    with st.form(key=f"res_form_ack_{row['anomaly_id']}"):
                        st.markdown(
                            "<div style='font-size: 12px; color: #9FB1C9; margin-bottom: 6px;'>"
                            "⚠️ <strong>Mandatory Note:</strong> Enter final disposition notes before closing this incident. "
                            "Blank or whitespace-only notes will be rejected.<br/>"
                            "<em>Note: Administrative triage action only; does not physically clear real-world road conditions.</em>"
                            "</div>",
                            unsafe_allow_html=True,
                        )
                        res_note_ack = st.text_area(
                            "Resolution Notes (Mandatory):",
                            value="Traffic conditions reviewed; nominal corridor flow verified.",
                            placeholder="Detail actions taken, verified observations, or closure rationale...",
                            key=f"res_note_ack_{row['anomaly_id']}",
                            height=80,
                        )
                        res_ack_submitted = st.form_submit_button("✓ Confirm Resolution", type="primary")
                        if res_ack_submitted:
                            if not res_note_ack or not res_note_ack.strip():
                                st.error("❌ Resolution notes are mandatory. Please provide a substantive explanation before resolving.")
                            else:
                                with get_db_cursor(commit=True) as cursor:
                                    cursor.execute(
                                        """
                                        UPDATE anomalies
                                        SET status = 'RESOLVED',
                                            resolution_notes = %(notes)s,
                                            resolved_at = UTC_TIMESTAMP()
                                        WHERE anomaly_id = %(id)s AND status IN ('ACTIVE', 'ACKNOWLEDGED')
                                        """,
                                        {"id": row["anomaly_id"], "notes": res_note_ack.strip()}
                                    )
                                st.success(f"✓ Incident {row['anomaly_id']} successfully RESOLVED.")
                                st.cache_data.clear()
                                st.rerun()

    # 6. Incident Archive Explorer
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    with st.expander("🔎 View Incident History"):
        st.dataframe(df_anom, use_container_width=True)

