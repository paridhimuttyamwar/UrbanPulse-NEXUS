"""
UrbanPulse NEXUS — Urban Analytics & Research Workspace.
Empirical historical analytics, diurnal congestion heatmaps, corridor rankings,
multi-arterial congestion trends, statistical correlation matrix, and cross-domain
traffic-environmental exploration across genuine Nagpur urban telemetry.

Strictly adheres to the UrbanPulse Real-Data-Only policy and UI simplification guidelines.
"""

from datetime import datetime, timedelta, date, time
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.theme import (
    render_nexus_header,
    render_section_header,
    render_kpi_card,
    apply_nexus_theme,
)
from analytics.traffic_analytics import traffic_analytics
from analytics.environment_analytics import environment_analytics
from config.corridors import NAGPUR_CORRIDORS_GEO, get_approved_corridors


def _calc_speed_reduction_pct(observed_speed: Any, free_flow_speed: Any) -> float:
    """Calculates percentage speed reduction relative to free-flow velocity."""
    if pd.isna(observed_speed) or pd.isna(free_flow_speed):
        return np.nan
    try:
        obs = float(observed_speed)
        ff = float(free_flow_speed)
        if ff <= 0:
            return np.nan
        return max(0.0, (1.0 - (obs / ff)) * 100.0)
    except (ZeroDivisionError, ValueError, TypeError):
        return np.nan


def _calc_travel_delay_pct(current_travel_time: Any, free_flow_travel_time: Any) -> float:
    """Calculates travel-time delay percentage relative to baseline free-flow travel time."""
    if pd.isna(current_travel_time) or pd.isna(free_flow_travel_time):
        return np.nan
    try:
        cur = float(current_travel_time)
        ff = float(free_flow_travel_time)
        if ff <= 0:
            return np.nan
        return max(0.0, ((cur - ff) / ff) * 100.0)
    except (ZeroDivisionError, ValueError, TypeError):
        return np.nan


def render_urban_analytics():
    # 1. Header with Single Subtle Provenance Indicator
    render_nexus_header(
        title="🔬 Urban Analytics — Empirical Research Studio",
        subtitle="Explore historical congestion patterns and corridor performance across Nagpur",
        provenance_badge="REAL_API TELEMETRY",
    )

    # 2. Analytics Filter Controls
    selected_loc = "LOC_NAGPUR"
    col_f1, col_f2 = st.columns([2.5, 1.5])
    with col_f1:
        st.markdown(
            """
            <div style="font-size: 12.5px; color: #9FB1C9; padding: 6px 0;">
                📅 <strong>Observation Window:</strong> Historical traffic dynamics and atmospheric records across all 15 registered Nagpur corridors.
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_f2:
        today = datetime.now().date()
        date_selection = st.date_input(
            "Filter Observation Date Range",
            value=(today - timedelta(days=3), today),
            key="urban_analytics_date_filter",
            label_visibility="collapsed",
        )

    start_date = None
    end_date = None
    if isinstance(date_selection, (list, tuple)):
        if len(date_selection) >= 1:
            start_date = date_selection[0]
        if len(date_selection) >= 2:
            end_date = date_selection[1]
        else:
            end_date = start_date
    elif date_selection:
        start_date = date_selection
        end_date = date_selection

    # 3. Load genuine datasets
    approved_corrs = get_approved_corridors()
    df_trf = traffic_analytics.load_traffic_dataframe(
        limit=10000,
        location_id=selected_loc,
        start_date=start_date,
        end_date=end_date,
        source_type="REAL_API",
    )

    df_weather_all = environment_analytics.load_weather_dataframe(limit=2000)
    df_aq_all = environment_analytics.load_air_quality_dataframe(limit=2000)

    df_weather = df_weather_all[df_weather_all["location_id"] == selected_loc] if not df_weather_all.empty else pd.DataFrame()
    df_aq = df_aq_all[df_aq_all["location_id"] == selected_loc] if not df_aq_all.empty else pd.DataFrame()

    # Defensively convert numeric types
    if not df_weather.empty:
        for col in ["temperature_c", "relative_humidity_pct", "wind_speed_kmh", "precipitation_mm"]:
            if col in df_weather.columns:
                df_weather[col] = pd.to_numeric(df_weather[col], errors="coerce")

    if not df_aq.empty:
        for col in ["pm2_5", "pm10", "nitrogen_dioxide", "ozone", "carbon_monoxide", "us_aqi", "european_aqi"]:
            if col in df_aq.columns:
                df_aq[col] = pd.to_numeric(df_aq[col], errors="coerce")

    # Data transformation for traffic telemetry
    if not df_trf.empty:
        for col in [
            "avg_speed_kmh",
            "free_flow_speed_kmh",
            "current_travel_time_sec",
            "free_flow_travel_time_sec",
            "confidence_score",
        ]:
            if col in df_trf.columns:
                df_trf[col] = pd.to_numeric(df_trf[col], errors="coerce")

        df_trf["speed_reduction_pct"] = df_trf.apply(
            lambda r: _calc_speed_reduction_pct(r.get("avg_speed_kmh"), r.get("free_flow_speed_kmh")), axis=1
        )
        df_trf["delay_pct"] = df_trf.apply(
            lambda r: _calc_travel_delay_pct(r.get("current_travel_time_sec"), r.get("free_flow_travel_time_sec")), axis=1
        )

        road_map = {cid: c.get("road_name", cid) for cid, c in NAGPUR_CORRIDORS_GEO.items()}
        df_trf["road_name"] = df_trf["segment_id"].map(road_map).fillna(df_trf.get("road_name", df_trf["segment_id"]))

        df_trf["timestamp"] = pd.to_datetime(df_trf["timestamp"])
        df_trf["timestamp_ist"] = df_trf["timestamp"].dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")
        df_trf["hour_ist"] = df_trf["timestamp_ist"].dt.hour
        df_trf["timestamp_display"] = df_trf["timestamp_ist"].dt.strftime("%d %b %Y, %I:%M %p IST")

    # =========================================================================
    # SECTION 1 — Historical Analytics Overview (4 Analytical KPIs)
    # =========================================================================
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)

    if not df_trf.empty:
        total_obs = len(df_trf)
        distinct_corrs = df_trf["segment_id"].nunique()

        # KPI 1: Traffic Observations
        with col_k1:
            render_kpi_card(
                label="Analyzed Observations",
                value=f"{total_obs:,}",
                unit=" records",
                delta=f"{distinct_corrs} Corridors Represented",
                provenance=None,
                icon="📡",
                sparkline_type="wave_cyan",
                accent_color="cyan",
            )

        # KPI 2: Most Congested Corridor
        corridor_stats = (
            df_trf.groupby(["segment_id", "road_name"])
            .agg(
                mean_red=("speed_reduction_pct", "mean"),
                obs_count=("speed_reduction_pct", "count"),
            )
            .reset_index()
            .sort_values("mean_red", ascending=False)
        )

        top_corridor = corridor_stats.iloc[0] if not corridor_stats.empty else None
        top_name = top_corridor["road_name"] if top_corridor is not None else "None"
        top_red = top_corridor["mean_red"] if top_corridor is not None else 0.0
        top_count = int(top_corridor["obs_count"]) if top_corridor is not None else 0
        is_provisional = top_count < 10

        with col_k2:
            render_kpi_card(
                label="Most Congested Corridor",
                value=f"{top_name}",
                unit="",
                delta=f"{top_red:.1f}% Speed Drop • {top_count} Obs{' (Provisional)' if is_provisional else ''}",
                provenance=None,
                icon="🚨",
                sparkline_type="wave_amber",
                accent_color="amber",
            )

        # KPI 3: Mean Network Speed Reduction
        valid_reductions = df_trf["speed_reduction_pct"].dropna()
        mean_net_red = valid_reductions.mean() if not valid_reductions.empty else 0.0

        with col_k3:
            render_kpi_card(
                label="Network Speed Reduction",
                value=f"{mean_net_red:.1f}",
                unit="%",
                delta=f"Evaluated across {len(valid_reductions)} Valid Readings",
                provenance=None,
                icon="📉",
                sparkline_type="bars_blue",
                accent_color="blue",
            )

        # KPI 4: Historical Data Coverage
        distinct_hours = df_trf["timestamp_ist"].dt.floor("h").nunique()
        period_str = f"{start_date.strftime('%d %b')} – {end_date.strftime('%d %b')}" if start_date and end_date else "Selected Range"
        coverage_tag = "Provisional Pilot" if distinct_hours < 8 else "Active Hourly"

        with col_k4:
            render_kpi_card(
                label="Historical Coverage",
                value=f"{distinct_hours}",
                unit=" hours",
                delta=f"{period_str} • {coverage_tag}",
                provenance=None,
                icon="⏱️",
                sparkline_type="wave_purple",
                accent_color="purple",
            )
    else:
        with col_k1:
            render_kpi_card(label="Analyzed Observations", value="0", unit=" records", delta="0 Corridors Represented", provenance=None, icon="📡", sparkline_type="wave_cyan", accent_color="cyan")
        with col_k2:
            render_kpi_card(label="Most Congested Corridor", value="No Telemetry", unit="", delta="No Observations in Window", provenance=None, icon="🚨", sparkline_type="wave_amber", accent_color="amber")
        with col_k3:
            render_kpi_card(label="Network Speed Reduction", value="0.0", unit="%", delta="No Valid Observations", provenance=None, icon="📉", sparkline_type="bars_blue", accent_color="blue")
        with col_k4:
            render_kpi_card(label="Historical Coverage", value="0", unit=" hours", delta="No Ingestion in Period", provenance=None, icon="⏱️", sparkline_type="wave_purple", accent_color="purple")

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    if df_trf.empty:
        st.info("ℹ️ No traffic observations recorded for the selected date range. Please expand the date filter or verify the Airflow ingestion schedule.")
        return

    # =========================================================================
    # SECTION 2 — Road Congestion Heatmap (15 Corridors x 24 Hours IST)
    # =========================================================================
    render_section_header(
        title="Road Congestion Heatmap — Diurnal Velocity Profile",
        subtitle="Historical average speed reduction percentage by corridor and hour of day (00:00–23:00 IST)",
    )

    all_corridor_ids = list(NAGPUR_CORRIDORS_GEO.keys())
    y_corridor_names = [NAGPUR_CORRIDORS_GEO[cid].get("road_name", cid) for cid in all_corridor_ids]
    x_hours = [f"{h:02d}:00" for h in range(24)]

    # 15 corridors x 24 hours grid
    matrix_z = np.full((len(all_corridor_ids), 24), np.nan)
    matrix_counts = np.zeros((len(all_corridor_ids), 24), dtype=int)

    for i, cid in enumerate(all_corridor_ids):
        corr_subset = df_trf[df_trf["segment_id"] == cid]
        if not corr_subset.empty:
            for h in range(24):
                hr_match = corr_subset[corr_subset["hour_ist"] == h]
                valid_vals = hr_match["speed_reduction_pct"].dropna()
                if len(valid_vals) > 0:
                    matrix_z[i, h] = valid_vals.mean()
                    matrix_counts[i, h] = len(valid_vals)

    max_z_val = float(np.nanmax(matrix_z)) if np.any(np.isfinite(matrix_z)) else 25.0
    z_upper = max(25.0, max_z_val)

    fig_heat = go.Figure(
        data=go.Heatmap(
            z=matrix_z,
            x=x_hours,
            y=y_corridor_names,
            customdata=matrix_counts,
            colorscale=[
                [0.0, "#101C30"],
                [0.2, "#35D6A1"],
                [0.5, "#FFBF69"],
                [1.0, "#FF647C"],
            ],
            zmin=0.0,
            zmax=z_upper,
            colorbar=dict(
                title=dict(text="Speed Drop (%)", font=dict(color="#F4F8FF", size=11)),
                tickfont=dict(color="#9FB1C9", size=10),
            ),
            hoverongaps=False,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Time: %{x} IST<br>"
                "Avg Speed Reduction: %{z:.1f}%<br>"
                "Observations: %{customdata} records<extra></extra>"
            ),
        )
    )
    fig_heat.update_layout(
        xaxis=dict(title="Hour of Day (IST)", tickangle=-45, tickfont=dict(size=10)),
        yaxis=dict(title="", tickfont=dict(size=11, color="#DCE9FA")),
        margin=dict(l=10, r=20, t=25, b=50),
    )
    apply_nexus_theme(fig_heat, height=440)
    st.plotly_chart(fig_heat, use_container_width=True)

    st.markdown(
        """
        <div style="font-size: 11.5px; color: #9FB1C9; margin-top: -12px; margin-bottom: 22px; padding: 6px 12px; background: rgba(21, 36, 59, 0.45); border-left: 2px solid #29D8F4; border-radius: 4px;">
            ℹ️ <strong>Sparse Coverage Safeguard:</strong> Only hours containing recorded traffic observations are populated.
            Unobserved hours remain transparent to prevent artificial zero-congestion distortion. As automated hourly Airflow ingestion cycles accumulate, all 24 diurnal hours will populate automatically.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # =========================================================================
    # SECTION 3 — Historical Corridor Performance Ranking
    # =========================================================================
    render_section_header(
        title="Historical Corridor Performance Ranking",
        subtitle="Empirical ranking of monitored Nagpur arterials by cumulative congestion impact",
    )

    rank_metric_label = st.radio(
        "Corridor Ranking Metric",
        ["Average Speed Reduction (%)", "Average Travel-Time Delay (%)"],
        horizontal=True,
        key="corridor_ranking_metric_radio",
    )

    is_speed_metric = "Speed Reduction" in rank_metric_label
    agg_col = "speed_reduction_pct" if is_speed_metric else "delay_pct"
    unit_str = "%"

    corridor_perf = (
        df_trf.groupby(["segment_id", "road_name"])
        .agg(
            metric_val=(agg_col, "mean"),
            obs_count=(agg_col, "count"),
            mean_speed=("avg_speed_kmh", "mean"),
            mean_ff_speed=("free_flow_speed_kmh", "mean"),
        )
        .reset_index()
    )

    corridor_perf = corridor_perf.dropna(subset=["metric_val"])
    corridor_perf = corridor_perf.sort_values("metric_val", ascending=True)  # ascending so highest is at top of horizontal bar

    if not corridor_perf.empty:
        # Annotation for provisional status
        corridor_perf["display_name"] = corridor_perf.apply(
            lambda r: f"{r['road_name']} (N={r['obs_count']})" if r["obs_count"] < 10 else r["road_name"],
            axis=1,
        )

        fig_rank = px.bar(
            corridor_perf,
            x="metric_val",
            y="display_name",
            orientation="h",
            color="metric_val",
            color_continuous_scale=[[0.0, "#35D6A1"], [0.4, "#FFBF69"], [1.0, "#FF647C"]],
            labels={
                "metric_val": "Speed Reduction (%)" if is_speed_metric else "Travel-Time Delay (%)",
                "display_name": "Corridor",
            },
            custom_data=["obs_count", "mean_speed", "mean_ff_speed", "road_name"],
        )
        fig_rank.update_traces(
            hovertemplate=(
                "<b>%{customdata[3]}</b><br>"
                + ("Avg Speed Reduction: " if is_speed_metric else "Avg Travel Delay: ")
                + "%{x:.1f}%<br>"
                "Observations: %{customdata[0]} records<br>"
                "Observed Speed: %{customdata[1]:.1f} km/h (Free-Flow: %{customdata[2]:.1f} km/h)<extra></extra>"
            )
        )
        fig_rank.update_layout(
            xaxis=dict(title=f"{'Mean Speed Reduction' if is_speed_metric else 'Mean Travel-Time Delay'} ({unit_str})"),
            yaxis=dict(title=""),
            coloraxis_showscale=False,
            margin=dict(l=10, r=20, t=20, b=30),
        )
        apply_nexus_theme(fig_rank, height=420)
        st.plotly_chart(fig_rank, use_container_width=True)

        st.markdown(
            """
            <div style="font-size: 11.5px; color: #9FB1C9; margin-top: -12px; margin-bottom: 22px;">
                <em>Note: Corridors with fewer than 10 observations are flagged with <code>(N=...)</code> denoting provisional rankings. Performance reflects empirical measurements collected during active pipeline operations.</em>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("Insufficient valid observations to compute corridor rankings.")

    # =========================================================================
    # SECTION 4 — Historical Congestion Trends (Multi-Arterial Comparison Tool)
    # =========================================================================
    render_section_header(
        title="Historical Congestion Trends — Arterial Comparison",
        subtitle="Time-series progression of speed reduction percentage across selected Nagpur corridors",
    )

    corr_options = list(NAGPUR_CORRIDORS_GEO.keys())
    corr_labels = {cid: NAGPUR_CORRIDORS_GEO[cid].get("road_name", cid) for cid in corr_options}

    # Default to top 2 corridors with the most readings
    top_cids_by_obs = (
        df_trf["segment_id"].value_counts().index.tolist()
        if not df_trf.empty else corr_options[:2]
    )
    default_selection = [c for c in top_cids_by_obs if c in corr_options][:2]

    selected_corridors = st.multiselect(
        "Select Corridors to Compare (Up to 3):",
        options=corr_options,
        default=default_selection,
        format_func=lambda x: corr_labels.get(x, x),
        key="trends_corridors_multiselect",
    )

    if len(selected_corridors) > 3:
        st.warning("⚠️ Maximum 3 corridors allowed for comparative analysis. Displaying the first 3 selected.")
        selected_corridors = selected_corridors[:3]

    if selected_corridors:
        trend_colors = ["#29D8F4", "#FFBF69", "#9685FF"]
        fig_trend = go.Figure()

        for idx, cid in enumerate(selected_corridors):
            sub_trf = df_trf[df_trf["segment_id"] == cid].sort_values("timestamp")
            if not sub_trf.empty:
                r_name = NAGPUR_CORRIDORS_GEO[cid].get("road_name", cid)
                col_c = trend_colors[idx % len(trend_colors)]
                fig_trend.add_trace(
                    go.Scatter(
                        x=sub_trf["timestamp_ist"],
                        y=sub_trf["speed_reduction_pct"],
                        mode="lines+markers",
                        name=r_name,
                        line=dict(color=col_c, width=2.2),
                        marker=dict(size=7, color=col_c, line=dict(width=1, color="#080F1E")),
                        connectgaps=False,
                        customdata=np.stack((sub_trf["avg_speed_kmh"], sub_trf["free_flow_speed_kmh"]), axis=-1),
                        hovertemplate=(
                            f"<b>{r_name}</b><br>"
                            "Time: %{x|%d %b %Y, %I:%M %p IST}<br>"
                            "Speed Reduction: %{y:.1f}%<br>"
                            "Observed: %{customdata[0]:.1f} km/h (Free-Flow: %{customdata[1]:.1f} km/h)<extra></extra>"
                        ),
                    )
                )

        fig_trend.update_layout(
            xaxis=dict(title="Observation Timestamp (IST)", tickformat="%d %b, %H:%M"),
            yaxis=dict(title="Speed Reduction (%)", zerolinecolor="rgba(41, 216, 244, 0.28)"),
            legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
            margin=dict(l=10, r=20, t=30, b=30),
        )
        apply_nexus_theme(fig_trend, height=360)
        st.plotly_chart(fig_trend, use_container_width=True)

        st.markdown(
            """
            <div style="font-size: 11.5px; color: #9FB1C9; margin-top: -12px; margin-bottom: 22px;">
                <em>Note: Discrete data markers denote hourly traffic observations. Disconnected gaps reflect periods where hourly ingestion was paused, preserving empirical truth without interpolation.</em>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("Select at least one corridor above to view historical congestion trends.")

    # =========================================================================
    # SECTION 5 — Statistical Correlation Analysis
    # =========================================================================
    render_section_header(
        title="Traffic Dynamics — Statistical Correlation Matrix",
        subtitle="Pairwise Pearson correlation coefficients across mobility metrics",
    )

    corr_candidates = [
        ("avg_speed_kmh", "Observed Speed (km/h)"),
        ("speed_reduction_pct", "Speed Reduction (%)"),
        ("delay_pct", "Travel Delay (%)"),
        ("confidence_score", "Provider Confidence"),
    ]

    valid_keys = []
    valid_labels = []
    for k, lab in corr_candidates:
        if k in df_trf.columns:
            s = df_trf[k].dropna()
            if len(s) >= 5 and s.nunique() > 1 and s.var() > 0:
                valid_keys.append(k)
                valid_labels.append(lab)

    if len(valid_keys) >= 2:
        df_corr_subset = df_trf[valid_keys].dropna()
        n_paired = len(df_corr_subset)

        if n_paired >= 5:
            corr_mat = df_corr_subset.corr(method="pearson")
            corr_mat.columns = valid_labels
            corr_mat.index = valid_labels

            fig_corr = px.imshow(
                corr_mat,
                text_auto=".2f",
                aspect="auto",
                color_continuous_scale=[[0.0, "#FF647C"], [0.5, "#15243B"], [1.0, "#29D8F4"]],
                zmin=-1.0,
                zmax=1.0,
                labels=dict(color="Pearson (r)"),
            )
            apply_nexus_theme(fig_corr, height=340)
            st.plotly_chart(fig_corr, use_container_width=True)

            st.caption(
                f"N = {n_paired} paired observations across traffic telemetry. "
                "Pearson r measures statistical co-variation across corridors and does not establish causation."
            )
        else:
            st.info("Insufficient paired observations with complete metrics to compute a reliable correlation matrix.")
    else:
        st.info("Insufficient variable variance in the current window to generate a meaningful correlation matrix.")

    # =========================================================================
    # SECTION 6 — Traffic and Environmental Relationship Explorer
    # =========================================================================
    render_section_header(
        title="Cross-Domain Relationship Explorer — Traffic & Atmosphere",
        subtitle="Investigating empirical associations between arterial congestion and atmospheric dispersion",
    )

    # City-wide network-level hourly aggregation to avoid sample size inflation
    df_trf_hourly = (
        df_trf.groupby(df_trf["timestamp_ist"].dt.floor("h"))
        .agg(
            net_speed_red=("speed_reduction_pct", "mean"),
            net_delay_pct=("delay_pct", "mean"),
            active_corridors=("segment_id", "nunique"),
        )
        .reset_index()
    )
    df_trf_hourly.rename(columns={"timestamp_ist": "hour_ist"}, inplace=True)

    has_env = False
    merged_cross = pd.DataFrame()

    if not df_weather.empty or not df_aq.empty:
        df_w_sub = pd.DataFrame()
        if not df_weather.empty and "timestamp" in df_weather.columns:
            w_copy = df_weather.copy()
            w_copy["timestamp_ist"] = pd.to_datetime(w_copy["timestamp"]).dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")
            df_w_sub = (
                w_copy.groupby(w_copy["timestamp_ist"].dt.floor("h"))
                .agg(
                    temperature_c=("temperature_c", "mean"),
                    relative_humidity_pct=("relative_humidity_pct", "mean"),
                )
                .reset_index()
            )
            df_w_sub.rename(columns={"timestamp_ist": "hour_ist"}, inplace=True)

        df_aq_sub = pd.DataFrame()
        if not df_aq.empty and "timestamp" in df_aq.columns:
            aq_copy = df_aq.copy()
            aq_copy["timestamp_ist"] = pd.to_datetime(aq_copy["timestamp"]).dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")
            df_aq_sub = (
                aq_copy.groupby(aq_copy["timestamp_ist"].dt.floor("h"))
                .agg(
                    pm2_5=("pm2_5", "mean"),
                    pm10=("pm10", "mean"),
                )
                .reset_index()
            )
            df_aq_sub.rename(columns={"timestamp_ist": "hour_ist"}, inplace=True)

        if not df_w_sub.empty:
            merged_cross = pd.merge(df_trf_hourly, df_w_sub, on="hour_ist", how="inner")
        if not df_aq_sub.empty:
            if merged_cross.empty:
                merged_cross = pd.merge(df_trf_hourly, df_aq_sub, on="hour_ist", how="inner")
            else:
                merged_cross = pd.merge(merged_cross, df_aq_sub, on="hour_ist", how="inner")

    n_matched_hours = len(merged_cross)

    if n_matched_hours >= 3:
        sc_col1, sc_col2 = st.columns(2)
        with sc_col1:
            trf_var_opt = st.selectbox(
                "Mobility Metric (Independent)",
                ["Speed Reduction (%)", "Travel-Time Delay (%)"],
                key="cross_trf_var_select",
            )
            trf_var_key = "net_speed_red" if "Speed Reduction" in trf_var_opt else "net_delay_pct"

        with sc_col2:
            env_avail = []
            if "pm2_5" in merged_cross.columns and merged_cross["pm2_5"].dropna().nunique() > 1:
                env_avail.append(("pm2_5", "PM2.5 Particulate (µg/m³)"))
            if "pm10" in merged_cross.columns and merged_cross["pm10"].dropna().nunique() > 1:
                env_avail.append(("pm10", "PM10 Particulate (µg/m³)"))
            if "temperature_c" in merged_cross.columns and merged_cross["temperature_c"].dropna().nunique() > 1:
                env_avail.append(("temperature_c", "Ambient Temperature (°C)"))
            if "relative_humidity_pct" in merged_cross.columns and merged_cross["relative_humidity_pct"].dropna().nunique() > 1:
                env_avail.append(("relative_humidity_pct", "Relative Humidity (%)"))

            if env_avail:
                env_var_selected = st.selectbox(
                    "Atmospheric Metric (Dependent)",
                    options=[e[1] for e in env_avail],
                    key="cross_env_var_select",
                )
                env_var_key = next(e[0] for e in env_avail if e[1] == env_var_selected)
            else:
                env_var_key = None

        if env_var_key:
            sub_cross = merged_cross[[trf_var_key, env_var_key, "hour_ist"]].dropna()
            if len(sub_cross) >= 3 and sub_cross[trf_var_key].var() > 0 and sub_cross[env_var_key].var() > 0:
                r_val = float(sub_cross[trf_var_key].corr(sub_cross[env_var_key]))
                sub_cross["time_str"] = sub_cross["hour_ist"].dt.strftime("%d %b, %H:00 IST")

                fig_scatter = px.scatter(
                    sub_cross,
                    x=trf_var_key,
                    y=env_var_key,
                    hover_data=["time_str"],
                    labels={trf_var_key: trf_var_opt, env_var_key: env_var_selected},
                    color_discrete_sequence=["#29D8F4"],
                )
                fig_scatter.update_traces(marker=dict(size=9, opacity=0.85, line=dict(width=1, color="#F4F8FF")))
                apply_nexus_theme(fig_scatter, height=330)
                st.plotly_chart(fig_scatter, use_container_width=True)

                st.markdown(
                    f"""
                    <div style="font-size: 12px; color: #DCE9FA; padding: 10px 14px; background: rgba(21, 36, 59, 0.5); border-left: 2px solid #29D8F4; border-radius: 4px;">
                        <strong>Empirical Correlation Result:</strong> <code>r = {r_val:+.2f}</code> (N = {len(sub_cross)} matched hourly intervals).<br/>
                        <span style="color: #9FB1C9;">Unit of Analysis: City-wide hourly network congestion paired with hourly municipal atmospheric monitoring.
                        Methodological Note: Atmospheric quality is influenced by planetary boundary layer height, ambient wind speed, and regional industrial emissions, rather than road traffic alone.</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.info("Insufficient variance in matched intervals to compute cross-domain scatter plot.")
    else:
        st.info(
            f"ℹ️ Cross-domain correlation requires at least 3 overlapping hourly observation periods (currently N = {n_matched_hours} matched hours). "
            "As scheduled hourly Airflow cycles accumulate, paired observations will populate automatically."
        )

    # =========================================================================
    # SECTION 7 — Analytical Corridor Summary Table with CSV Export
    # =========================================================================
    render_section_header(
        title="Nagpur Corridors Performance Summary Table",
        subtitle="Aggregated performance benchmarks across all 15 registered arterials",
    )

    summary_rows = []
    for cid in all_corridor_ids:
        r_name = NAGPUR_CORRIDORS_GEO[cid].get("road_name", cid)
        sub = df_trf[df_trf["segment_id"] == cid]
        obs_n = len(sub)

        if obs_n > 0:
            m_speed = sub["avg_speed_kmh"].mean()
            ff_speed = sub["free_flow_speed_kmh"].mean()
            m_red = sub["speed_reduction_pct"].mean()
            m_delay = sub["delay_pct"].mean()
            latest_ts = sub["timestamp_ist"].max()
            latest_str = latest_ts.strftime("%d %b, %I:%M %p") if pd.notna(latest_ts) else "—"
            coverage_status = "Verified Baseline" if obs_n >= 10 else f"Provisional (N={obs_n})"
        else:
            m_speed = np.nan
            ff_speed = np.nan
            m_red = np.nan
            m_delay = np.nan
            latest_str = "—"
            coverage_status = "No Observations"

        summary_rows.append({
            "Corridor Name": r_name,
            "Corridor ID": cid,
            "Observations": obs_n,
            "Mean Speed (km/h)": round(m_speed, 1) if pd.notna(m_speed) else None,
            "Free-Flow Speed (km/h)": round(ff_speed, 1) if pd.notna(ff_speed) else None,
            "Mean Speed Reduction (%)": round(m_red, 1) if pd.notna(m_red) else None,
            "Mean Travel Delay (%)": round(m_delay, 1) if pd.notna(m_delay) else None,
            "Latest Reading (IST)": latest_str,
            "Coverage Status": coverage_status,
        })

    summary_df = pd.DataFrame(summary_rows).sort_values("Observations", ascending=False)

    col_tb1, col_tb2 = st.columns([3, 1])
    with col_tb2:
        csv_bytes = summary_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Export Corridor Summary (CSV)",
            data=csv_bytes,
            file_name=f"nagpur_corridors_analytics_{start_date}_{end_date}.csv",
            mime="text/csv",
            key="export_corridor_summary_csv_btn",
        )

    # Format display table with non-zero missing placeholders ('—')
    display_df = summary_df.copy()
    for num_col in ["Mean Speed (km/h)", "Free-Flow Speed (km/h)", "Mean Speed Reduction (%)", "Mean Travel Delay (%)"]:
        display_df[num_col] = display_df[num_col].apply(lambda v: f"{v:.1f}" if pd.notna(v) and v is not None else "—")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )
