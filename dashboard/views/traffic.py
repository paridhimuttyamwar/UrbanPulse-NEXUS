"""
UrbanPulse NEXUS — Traffic Intelligence View.
Nagpur mobility operations, genuine TomTom Traffic Flow API telemetry,
speed benchmarking, and corridor congestion dynamics across 15 municipal arterials.
"""

from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analytics.traffic_analytics import traffic_analytics
from dashboard.data_loader import (
    load_latest_traffic_per_corridor,
    load_road_segments,
    load_traffic_readings,
)
from dashboard.theme import (
    apply_nexus_theme,
    render_kpi_card,
    render_nexus_header,
    render_section_header,
)
from config.corridors import get_approved_corridors, NAGPUR_CORRIDORS_GEO, get_corridor_geo


def render_traffic():
    approved_corrs = get_approved_corridors()
    total_cnt = len(NAGPUR_CORRIDORS_GEO)
    approved_cnt = len(approved_corrs)
    excluded_cnt = max(0, total_cnt - approved_cnt)

    # 1. Header with REAL_API Provenance Badge
    render_nexus_header(
        title="🚦 Traffic Intelligence — Nagpur",
        subtitle="Monitor traffic speeds, travel delays, and congestion patterns across Nagpur's monitored road corridors.",
        provenance_badge="REAL_API",
    )

    selected_loc = "LOC_NAGPUR"
    df_segments = load_road_segments(location_id=selected_loc)

    # 2. Corridor Filter, Date Range & Provenance Controls
    col_sel, col_date, col_info = st.columns([1.8, 1.4, 1.2])

    seg_names = ["ALL"] + (df_segments["segment_id"].tolist() if not df_segments.empty else [])
    if excluded_cnt == 0:
        all_label = f"All Nagpur Corridors ({approved_cnt} Active)"
    else:
        all_label = f"All Nagpur Corridors ({approved_cnt}/{total_cnt} Active)"
    seg_labels = {"ALL": all_label}
    if not df_segments.empty:
        for _, r in df_segments.iterrows():
            cid = r["segment_id"]
            seg_labels[cid] = r["road_name"]

    with col_sel:
        selected_seg = st.selectbox(
            "Select Nagpur Road Corridor",
            seg_names,
            format_func=lambda x: seg_labels.get(x, x),
            index=0,
            label_visibility="collapsed",
        )

    with col_date:
        today = datetime.now().date()
        date_sel = st.date_input(
            "Traffic Date Range",
            value=(today - timedelta(days=2), today),
            key="traffic_date_filter",
            label_visibility="collapsed",
        )

    start_date = None
    end_date = None
    if isinstance(date_sel, (list, tuple)):
        if len(date_sel) >= 1:
            start_date = date_sel[0]
        if len(date_sel) >= 2:
            end_date = date_sel[1]
        else:
            end_date = start_date
    elif date_sel:
        start_date = date_sel
        end_date = date_sel

    with col_info:
        st.markdown(
            """
            <div style="font-size: 11.5px; font-weight: 700; color: #29D8F4; padding: 7px 12px; background: rgba(21, 36, 59, 0.5); border: 1px solid rgba(41, 216, 244, 0.25); border-radius: 6px; text-align: center; letter-spacing: 0.05em;">
                API
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Load latest snapshot for all corridors and time series telemetry
    df_latest = load_latest_traffic_per_corridor(
        location_id=selected_loc,
        source_type="REAL_API",
        stale_threshold_minutes=90,
    )

    df_traffic_all = load_traffic_readings(
        segment_id="ALL",
        location_id=selected_loc,
        start_date=start_date,
        end_date=end_date,
        source_type="REAL_API",
        limit=5000,
    )
    df_traffic = (
        df_traffic_all[df_traffic_all["segment_id"] == selected_seg]
        if (selected_seg != "ALL" and not df_traffic_all.empty)
        else df_traffic_all
    )

    if df_latest.empty:
        st.info(
            "ℹ️ No genuine TomTom API traffic observations found in MySQL. "
            "All historical simulated data is quarantined in accordance with the Real-Data-Only policy. "
            "When the scheduled Airflow ingestion runs, live flow telemetry will populate automatically."
        )
        return

    df_latest["is_approved"] = df_latest["segment_id"].isin(approved_corrs)
    df_latest["status_label"] = df_latest["is_approved"].map(
        {True: "ACTIVE (VERIFIED)", False: "EXCLUDED (PENDING GPS)"}
    )
    df_active = df_latest[df_latest["is_approved"]]

    # 3. Top Metrics Summary Cards
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        approved_cnt = len(approved_corrs)
        total_cnt = len(NAGPUR_CORRIDORS_GEO)
        delta_str = f"{approved_cnt} Active Verified (All {total_cnt})" if excluded_cnt == 0 else f"{approved_cnt} Active Verified • {excluded_cnt} Excluded"
        render_kpi_card(
            label="Monitored Corridors",
            value=f"{approved_cnt} / {total_cnt}",
            unit=" corridors",
            delta=delta_str,
            provenance=None,
            icon="🛣️",
            sparkline_type="bars_blue",
            accent_color="blue",
        )

    with col2:
        net_avg_spd = df_active["avg_speed_kmh"].mean() if not df_active.empty else df_latest["avg_speed_kmh"].mean()
        net_ff_spd = df_active["free_flow_speed_kmh"].mean() if not df_active.empty else df_latest["free_flow_speed_kmh"].mean()
        render_kpi_card(
            label="Network Mean Speed",
            value=f"{net_avg_spd:.1f}" if pd.notna(net_avg_spd) else "--",
            unit=" km/h",
            delta=f"Free-Flow: {net_ff_spd:.1f} km/h" if pd.notna(net_ff_spd) else "Nominal",
            provenance=None,
            icon="🏎️",
            sparkline_type="wave_cyan",
            accent_color="cyan",
        )

    with col3:
        target_df = df_active if not df_active.empty else df_latest
        max_delay = target_df["delay_seconds"].max()
        if pd.notna(max_delay) and max_delay > 0:
            delay_row = target_df.loc[target_df["delay_seconds"].idxmax()]
            delay_road = delay_row["road_name"][:18]
            delta_str = f"Max on {delay_road}"
        else:
            delta_str = "Zero Network Delay"

        render_kpi_card(
            label="Peak Travel Delay",
            value=f"{int(max_delay)}" if pd.notna(max_delay) else "0",
            unit=" sec",
            delta=delta_str,
            provenance=None,
            icon="⏱️",
            sparkline_type="wave_amber",
            accent_color="amber",
        )

    with col4:
        stale_count = int(df_latest["is_stale"].sum())
        fresh_count = len(df_latest) - stale_count
        freshness_label = df_latest["time_ago"].iloc[0] if not df_latest.empty else "N/A"
        delta_freshness = "All Corridors Fresh (<90m)" if stale_count == 0 else f"{stale_count} Stale (Batch paused)"

        render_kpi_card(
            label="Data Freshness",
            value=freshness_label,
            unit="",
            delta=delta_freshness,
            provenance=None,
            icon="📡",
            sparkline_type="wave_green",
            accent_color="green",
        )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # 4. Innovative Traffic Corridor Explorer
    if selected_seg != "ALL":
        corridor_matches = df_latest[df_latest["segment_id"] == selected_seg]
        if not corridor_matches.empty:
            c_row = corridor_matches.iloc[0]
            road_name = c_row.get("road_name", selected_seg)
            seg_type = c_row.get("segment_type", "ARTERIAL")
            cur_spd = c_row.get("avg_speed_kmh", 0.0)
            ff_spd = c_row.get("free_flow_speed_kmh", 0.0)
            cur_time = c_row.get("current_travel_time_sec", 0)
            ff_time = c_row.get("free_flow_travel_time_sec", 0)
            delay_sec = c_row.get("delay_seconds", 0)
            speed_red = c_row.get("speed_reduction_pct", 0.0)
            los = c_row.get("congestion_level", "LOW")
            conf = c_row.get("confidence_score", 1.0)
            is_closed = c_row.get("road_closure", False)
            last_seen = c_row.get("timestamp_display", "Recent")
            fresh_badge = c_row.get("freshness_badge", "FRESH")
            is_stale = c_row.get("is_stale", False)
            is_corridor_active = selected_seg in approved_corrs

            los_badge_color = {
                "LOW": "#35D6A1",
                "MEDIUM": "#4F8CFF",
                "HIGH": "#FFBF69",
                "SEVERE": "#FF647C",
            }.get(los, "#35D6A1")

            closure_str = "<strong style='color: #FF647C;'>CLOSED</strong>" if is_closed else "<strong style='color: #35D6A1;'>OPEN</strong>"
            fresh_color = "#FFBF69" if is_stale else "#35D6A1"

            exclusion_notice = ""
            if not is_corridor_active:
                exclusion_notice = (
                    '<div style="background: rgba(255, 191, 105, 0.1); border: 1px solid rgba(255, 191, 105, 0.35); border-radius: 6px; padding: 8px 12px; margin-bottom: 12px; font-size: 12px; color: #FFD180;">'
                    f'⚠️ <strong>Pending Verification Notice:</strong> This corridor ({road_name}) is pending precision GPS ground verification to prevent FRC1 highway snapping.'
                    '</div>'
                )

            status_badge_text = "VERIFIED ACTIVE" if is_corridor_active else "PENDING GPS"
            status_badge_style = "background: rgba(53, 214, 161, 0.15); color: #35D6A1; border: 1px solid rgba(53, 214, 161, 0.3);" if is_corridor_active else "background: rgba(255, 191, 105, 0.15); color: #FFBF69; border: 1px solid rgba(255, 191, 105, 0.3);"

            explorer_html = (
                '<div class="nexus-card" style="border-left: 3px solid #29D8F4; background: linear-gradient(135deg, rgba(21, 36, 59, 0.9) 0%, rgba(16, 28, 48, 0.95) 100%);">'
                f'{exclusion_notice}'
                '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">'
                '<div>'
                f'<span style="font-size: 17px; font-weight: 800; color: #F4F8FF;">🛣️ Corridor Explorer: {road_name}</span>'
                '</div>'
                '<div style="display: flex; gap: 8px;">'
                f'<span class="badge-nexus" style="{status_badge_style}">{status_badge_text}</span>'
                f'<span class="badge-nexus" style="background: rgba(41, 216, 244, 0.15); color: #29D8F4; border: 1px solid rgba(41, 216, 244, 0.3);">{seg_type}</span>'
                f'<span class="badge-nexus" style="background: rgba(255, 255, 255, 0.05); color: {los_badge_color}; border: 1px solid {los_badge_color};">LOS: {los}</span>'
                f'<span class="badge-nexus" style="color: {fresh_color}; border: 1px solid {fresh_color};">{fresh_badge}</span>'
                '</div>'
                '</div>'
                '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; font-size: 13px;">'
                f'<div>Observed Speed: <strong style="color: #29D8F4;">{cur_spd:.1f} km/h</strong></div>'
                f'<div>Free-Flow Speed: <strong style="color: #F4F8FF;">{ff_spd:.1f} km/h</strong></div>'
                f'<div>Speed Reduction: <strong style="color: {"#FF647C" if speed_red >= 40 else "#35D6A1"};">{speed_red:.1f}%</strong></div>'
                f'<div>Travel Time: <strong style="color: #F4F8FF;">{cur_time}s</strong> (FF: {ff_time}s)</div>'
                f'<div>Calculated Delay: <strong style="color: {"#FF647C" if delay_sec > 180 else "#35D6A1"};">{delay_sec}s</strong></div>'
                f'<div>TomTom Confidence: <strong style="color: #F4F8FF;">{float(conf)*100:.1f}%</strong></div>'
                f'<div>Road Status: {closure_str}</div>'
                f'<div>Last Observation: <strong style="color: #F4F8FF;">{last_seen}</strong></div>'
                '</div>'
                '</div>'
            )
            st.markdown(explorer_html, unsafe_allow_html=True)

    # 5. Charts Row 1: Speed Benchmark & Congestion Breakdown
    render_section_header(
        title="Flow Dynamics & Congestion Classification",
        subtitle="Current velocity vs free-flow speed benchmarks and Level of Service (LOS) breakdown",
        badge="TOMTOM FLOW",
    )
    c1, c2 = st.columns([1.6, 1])

    with c1:
        st.markdown("#### 🏎️ Corridor Speed Benchmark: Observed vs Free-Flow")
        # Prepare comparison dataframe
        bench_df = df_latest.sort_values("avg_speed_kmh", ascending=True)
        fig_speed = go.Figure()
        fig_speed.add_trace(
            go.Bar(
                y=bench_df["road_name"],
                x=bench_df["avg_speed_kmh"],
                name="Current Observed Speed",
                orientation="h",
                marker=dict(color="#29D8F4"),
            )
        )
        fig_speed.add_trace(
            go.Bar(
                y=bench_df["road_name"],
                x=bench_df["free_flow_speed_kmh"],
                name="Free-Flow Speed Baseline",
                orientation="h",
                marker=dict(color="#4F8CFF", opacity=0.45),
            )
        )
        fig_speed.update_layout(
            barmode="group",
            xaxis=dict(title="Speed (km/h)", tickfont=dict(color="#9FB1C9", size=10)),
            yaxis=dict(tickfont=dict(color="#DCE9FA", size=10)),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                bgcolor="rgba(21, 36, 59, 0.7)",
                font=dict(color="#DCE9FA", size=10.5),
            ),
            margin=dict(l=20, r=20, t=40, b=20),
        )
        apply_nexus_theme(fig_speed, height=440)
        st.plotly_chart(fig_speed, use_container_width=True)

    with c2:
        st.markdown("#### 📊 Congestion Level (LOS) Breakdown")
        cong_counts = df_latest["congestion_level"].value_counts().reset_index()
        cong_counts.columns = ["Level", "Count"]
        color_discrete_map = {
            "LOW": "#35D6A1",
            "MEDIUM": "#4F8CFF",
            "HIGH": "#FFBF69",
            "SEVERE": "#FF647C",
        }
        fig_pie = px.pie(
            cong_counts,
            names="Level",
            values="Count",
            hole=0.55,
            color="Level",
            color_discrete_map=color_discrete_map,
        )
        apply_nexus_theme(fig_pie, height=440)
        st.plotly_chart(fig_pie, use_container_width=True)

    # 6. Charts Row 2: Travel-Time Delay Comparison & Speed Reduction %
    render_section_header(
        title="Delay Analytics & Velocity Reduction Profiles",
        subtitle="Calculated travel-time delay in seconds and percentage speed reduction below free-flow baseline",
        badge="DERIVED METRICS",
    )

    # Check if all observed values in the selected observations are zero
    delay_df = df_latest.sort_values("delay_seconds", ascending=True)
    red_df = df_latest.sort_values("speed_reduction_pct", ascending=True)

    max_d_series = delay_df["delay_seconds"].dropna()
    max_d = float(max_d_series.max()) if not max_d_series.empty else 0.0

    max_red_series = red_df["speed_reduction_pct"].dropna()
    max_red = float(max_red_series.max()) if not max_red_series.empty else 0.0

    corridor_count = len(df_latest)
    if max_d == 0.0 and max_red == 0.0:
        st.info(
            f"ℹ️ All {corridor_count} monitored corridors show zero recorded travel delay "
            "and speed reduction in the selected observations."
        )

    c3, c4 = st.columns([1, 1])

    with c3:
        st.markdown("#### ⏱️ Corridor Travel-Time Delay (Seconds above Free-Flow)")

        # Prepare delay labels: preserve missing as 'N/A' rather than converting to zero
        def _delay_text(val):
            if pd.isna(val):
                return "N/A"
            ival = int(round(val))
            return f"{ival}s (Optimal)" if ival == 0 else f"{ival}s delay"

        delay_texts = [_delay_text(d) for d in delay_df["delay_seconds"]]
        delay_vals = delay_df["delay_seconds"].fillna(0)

        fig_delay = go.Figure()
        fig_delay.add_trace(
            go.Bar(
                y=delay_df["road_name"],
                x=delay_vals,
                orientation="h",
                text=delay_texts,
                textposition="outside",
                textfont=dict(color="#9FB1C9", size=10),
                marker=dict(
                    color=delay_vals,
                    colorscale=[[0, "#35D6A1"], [0.4, "#FFBF69"], [1, "#FF647C"]],
                    cmin=0,
                    cmax=max(10.0, max_d if max_d > 0 else 10.0),
                ),
            )
        )
        # Dynamically expanding x-axis: if max_d > 0, expand to 1.25x max_d; if 0, provide clean breathing room
        x_range_delay = [0, max(15.0, max_d * 1.25)] if max_d > 0 else [0, 15.0]
        fig_delay.update_layout(
            xaxis=dict(title="Delay above Free-Flow (seconds)", range=x_range_delay, tickfont=dict(color="#9FB1C9", size=10)),
            yaxis=dict(tickfont=dict(color="#DCE9FA", size=10)),
            margin=dict(l=20, r=45, t=20, b=20),
        )
        apply_nexus_theme(fig_delay, height=440)
        st.plotly_chart(fig_delay, use_container_width=True)

    with c4:
        st.markdown("#### 📉 Velocity Reduction Percentage (%)")

        # Prepare speed reduction labels: preserve missing as 'N/A' rather than converting to zero
        def _red_text(val):
            if pd.isna(val):
                return "N/A"
            fval = float(val)
            return f"{fval:.1f}% (Free-Flow)" if fval == 0.0 else f"{fval:.1f}%"

        red_texts = [_red_text(r) for r in red_df["speed_reduction_pct"]]
        red_vals = red_df["speed_reduction_pct"].fillna(0)

        fig_red = go.Figure()
        fig_red.add_trace(
            go.Bar(
                y=red_df["road_name"],
                x=red_vals,
                orientation="h",
                text=red_texts,
                textposition="outside",
                textfont=dict(color="#9FB1C9", size=10),
                marker=dict(
                    color=red_vals,
                    colorscale=[[0, "#35D6A1"], [0.35, "#FFBF69"], [1, "#FF647C"]],
                    cmin=0,
                    cmax=max(10.0, max_red if max_red > 0 else 10.0),
                ),
            )
        )
        # Dynamically expanding x-axis: if max_red > 0, expand to 1.25x max_red; if 0, provide clean breathing room
        x_range_red = [0, max(15.0, max_red * 1.25)] if max_red > 0 else [0, 15.0]
        fig_red.update_layout(
            xaxis=dict(title="Velocity Reduction (%)", range=x_range_red, tickfont=dict(color="#9FB1C9", size=10)),
            yaxis=dict(tickfont=dict(color="#DCE9FA", size=10)),
            margin=dict(l=20, r=50, t=20, b=20),
        )
        apply_nexus_theme(fig_red, height=440)
        st.plotly_chart(fig_red, use_container_width=True)

    # 7. Historical Speed Trajectory with Corridor Selection Filter
    render_section_header(
        title="Historical Speed Trajectory",
        subtitle="Temporal velocity variations across observed TomTom ingestion cycles",
        badge="TIME SERIES",
    )

    all_corr_keys = list(NAGPUR_CORRIDORS_GEO.keys())
    if selected_seg != "ALL" and selected_seg in all_corr_keys:
        default_traj_corrs = [selected_seg]
    else:
        default_traj_corrs = [c for c in ["SEG_NAG_01", "SEG_NAG_02", "SEG_NAG_03"] if c in all_corr_keys]

    sel_traj_corrs = st.multiselect(
        "Select Corridors to Compare (Up to 5):",
        options=all_corr_keys,
        default=default_traj_corrs,
        format_func=lambda x: NAGPUR_CORRIDORS_GEO.get(x, {}).get("road_name", x),
        key="traffic_speed_trajectory_corridors_multiselect",
        help="Select up to 5 Nagpur corridors to evaluate speed progression over time.",
    )

    if len(sel_traj_corrs) > 5:
        st.warning("⚠️ Maximum 5 corridors allowed for clear comparison. Displaying the first 5 selected.")
        sel_traj_corrs = sel_traj_corrs[:5]

    df_traj_source = df_traffic_all if not df_traffic_all.empty else df_traffic
    df_traj_plot = (
        df_traj_source[df_traj_source["segment_id"].isin(sel_traj_corrs)]
        if (not df_traj_source.empty and sel_traj_corrs)
        else pd.DataFrame()
    )

    if not df_traj_plot.empty and "timestamp" in df_traj_plot.columns:
        distinct_timestamps = df_traj_plot["timestamp"].nunique()
        if distinct_timestamps > 1:
            fig_hist = px.line(
                df_traj_plot.sort_values("timestamp"),
                x="timestamp_ist_naive",
                y="avg_speed_kmh",
                color="road_name",
                labels={"avg_speed_kmh": "Speed (km/h)", "timestamp_ist_naive": "Observation Time (IST)", "road_name": "Corridor"},
                color_discrete_sequence=["#29D8F4", "#4F8CFF", "#9685FF", "#35D6A1", "#FFBF69", "#FF647C"],
            )
            fig_hist.update_traces(connectgaps=False, mode="lines+markers")
            fig_hist.update_layout(
                xaxis=dict(title="Observation Time (IST)"),
                yaxis=dict(title="Speed (km/h)"),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                    bgcolor="rgba(21, 36, 59, 0.7)",
                ),
                margin=dict(l=20, r=20, t=30, b=20),
            )
            apply_nexus_theme(fig_hist, height=380)
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.info("Baseline snapshot recorded. Multi-interval historical trends will populate automatically as hourly Airflow ingestion cycles execute.")
    elif not sel_traj_corrs:
        st.info("Please select at least one corridor above to view historical speed variations.")
    else:
        st.info("No historical observations recorded for the selected corridor(s) in this date range.")

    # 8. Recent Traffic Observations Table
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    with st.expander("Recent Traffic Observations", expanded=False):
        display_cols = [
            "segment_id",
            "road_name",
            "status_label",
            "avg_speed_kmh",
            "free_flow_speed_kmh",
            "speed_reduction_pct",
            "current_travel_time_sec",
            "free_flow_travel_time_sec",
            "delay_seconds",
            "congestion_level",
            "confidence_score",
            "road_closure",
            "timestamp_display",
            "freshness_badge",
        ]
        valid_cols = [c for c in display_cols if c in df_latest.columns]
        st.dataframe(df_latest[valid_cols], use_container_width=True)
