"""
UrbanPulse NEXUS — Design System & UI/UX Components.
Centralized styling, CSS animated ambient glows, high-contrast tabs,
glassmorphic card system, and standardized Plotly visualizations.

Theme Palette:
  Main Background:      #080F1E
  Secondary Background: #101C30
  Card Surface:         #15243B
  Primary Cyan:         #29D8F4
  Electric Blue:        #4F8CFF
  Accent Violet:        #9685FF
  Positive (Emerald):   #35D6A1
  Warning (Amber):      #FFBF69
  Critical (Coral):     #FF647C
  Main Text:            #F4F8FF
  Secondary Text:       #9FB1C9
"""

import base64
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any, List
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

# Complete NEXUS Global CSS with High-Contrast Tabs & Subtle Ambient Background
NEXUS_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Manrope:wght@400;600;700;800&display=swap');

/* Global Font & Canvas Reset */
html, body, [class*="css"], div[data-testid="stAppViewContainer"] {
    font-family: 'Inter', 'Manrope', -apple-system, BlinkMacSystemFont, sans-serif;
    color: #F4F8FF;
}

div[data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at 15% 15%, #101C30 0%, #080F1E 55%, #050914 100%);
    background-attachment: fixed;
    position: relative;
    overflow-x: hidden;
}

header[data-testid="stHeader"] {
    background: transparent !important;
}

/* Subtle Animated Ambient Mesh Background (Lightweight CSS) */
div[data-testid="stAppViewContainer"]::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: 
        radial-gradient(circle at 12% 18%, rgba(41, 216, 244, 0.08) 0%, transparent 40%),
        radial-gradient(circle at 88% 78%, rgba(150, 133, 255, 0.09) 0%, transparent 45%),
        radial-gradient(circle at 50% 50%, rgba(79, 140, 255, 0.04) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
    animation: ambient-breathe 16s ease-in-out infinite alternate;
}

/* Subtle Moving Cyber Grid Pattern (GPU-accelerated, zero JS) */
div[data-testid="stAppViewContainer"]::after {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image: 
        linear-gradient(to right, rgba(41, 216, 244, 0.028) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(41, 216, 244, 0.028) 1px, transparent 1px);
    background-size: 52px 52px;
    pointer-events: none;
    z-index: 0;
    opacity: 0.85;
    animation: grid-drift 70s linear infinite;
}

@keyframes ambient-breathe {
    0% { opacity: 0.55; transform: scale(1); }
    50% { opacity: 0.85; transform: scale(1.04); }
    100% { opacity: 0.6; transform: scale(1); }
}

@keyframes grid-drift {
    0% { background-position: 0 0; }
    100% { background-position: 52px 52px; }
}

/* Reduced motion preference support for accessibility */
@media (prefers-reduced-motion: reduce) {
    *, div[data-testid="stAppViewContainer"]::before, div[data-testid="stAppViewContainer"]::after {
        animation: none !important;
        transition: none !important;
    }
}

/* Sidebar Overrides & Navigation Polish — Scrollable & Sleek */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0A1325 0%, #060B17 100%) !important;
    border-right: 1px solid rgba(41, 216, 244, 0.15) !important;
    padding-top: 1rem !important;
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.35);
    overflow-y: auto !important;
    max-height: 100vh !important;
}

section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
section[data-testid="stSidebar"] > div:first-child {
    overflow-y: auto !important;
    max-height: 100vh !important;
    padding-bottom: 2rem !important;
}

section[data-testid="stSidebar"]::-webkit-scrollbar,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"]::-webkit-scrollbar {
    width: 6px !important;
}
section[data-testid="stSidebar"]::-webkit-scrollbar-track,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"]::-webkit-scrollbar-track {
    background: rgba(10, 19, 37, 0.5) !important;
}
section[data-testid="stSidebar"]::-webkit-scrollbar-thumb,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"]::-webkit-scrollbar-thumb {
    background: rgba(41, 216, 244, 0.35) !important;
    border-radius: 3px !important;
}
section[data-testid="stSidebar"]::-webkit-scrollbar-thumb:hover,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"]::-webkit-scrollbar-thumb:hover {
    background: rgba(41, 216, 244, 0.65) !important;
}

section[data-testid="stSidebar"] h1, 
section[data-testid="stSidebar"] h2, 
section[data-testid="stSidebar"] h3 {
    color: #F4F8FF !important;
    font-family: 'Manrope', sans-serif !important;
    font-weight: 700;
}

section[data-testid="stSidebar"] p, 
section[data-testid="stSidebar"] span, 
section[data-testid="stSidebar"] label {
    color: #9FB1C9 !important;
}

/* Radio Navigation in Sidebar */
section[data-testid="stSidebar"] div[role="radiogroup"] > label {
    background: rgba(21, 36, 59, 0.45);
    border: 1px solid rgba(79, 140, 255, 0.14);
    border-radius: 10px;
    padding: 10px 14px;
    margin-bottom: 7px;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    cursor: pointer;
}

section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
    background: rgba(41, 216, 244, 0.12);
    border-color: rgba(41, 216, 244, 0.4);
    transform: translateX(4px);
    box-shadow: 0 2px 12px rgba(41, 216, 244, 0.15);
}

section[data-testid="stSidebar"] div[role="radiogroup"] > label[data-checked="true"],
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
    background: linear-gradient(90deg, #1852E8 0%, #0A84FF 100%) !important;
    border-left: 3px solid #29D8F4 !important;
    border-color: rgba(41, 216, 244, 0.8) !important;
    box-shadow: 0 4px 16px rgba(24, 82, 232, 0.45), inset 0 0 12px rgba(41, 216, 244, 0.25) !important;
}

section[data-testid="stSidebar"] div[role="radiogroup"] > label[data-checked="true"] p,
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p {
    color: #FFFFFF !important;
    font-weight: 700 !important;
}

/* Streamlit Tabs Styling — HIGH CONTRAST & CLEAR VISIBILITY */
div[data-baseweb="tab-list"], [data-testid="stTabs"] > div:first-child {
    background: rgba(16, 28, 48, 0.85) !important;
    border: 1px solid rgba(79, 140, 255, 0.3) !important;
    border-radius: 10px !important;
    padding: 6px 8px !important;
    gap: 10px !important;
    margin-bottom: 18px !important;
}

div[data-baseweb="tab-highlight"] {
    background-color: #29D8F4 !important;
    height: 3px !important;
    border-radius: 2px !important;
}

div[data-baseweb="tab-border"] {
    background-color: rgba(79, 140, 255, 0.25) !important;
}

/* Base button styling for all tabs */
button[data-baseweb="tab"], [data-testid="stTabs"] button, button[role="tab"] {
    background: rgba(21, 36, 59, 0.75) !important;
    border: 1px solid rgba(79, 140, 255, 0.28) !important;
    border-radius: 8px !important;
    padding: 10px 20px !important;
    color: #DCE9FA !important;
    font-size: 13.5px !important;
    font-weight: 600 !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

/* Force high contrast text on all tab children */
button[data-baseweb="tab"] *, [data-testid="stTabs"] button *, button[role="tab"] * {
    color: #DCE9FA !important;
    font-weight: 600 !important;
}

/* Unselected tabs — High Contrast Light Text on Dark Glass */
button[data-baseweb="tab"][aria-selected="false"],
[data-testid="stTabs"] button[aria-selected="false"],
button[role="tab"][aria-selected="false"] {
    background: rgba(21, 36, 59, 0.85) !important;
    border: 1px solid rgba(79, 140, 255, 0.32) !important;
}

button[data-baseweb="tab"][aria-selected="false"] *,
[data-testid="stTabs"] button[aria-selected="false"] *,
button[role="tab"][aria-selected="false"] * {
    color: #DCE9FA !important;
    opacity: 0.95 !important;
}

/* Hover state — Cyan outline & glow */
button[data-baseweb="tab"]:hover, [data-testid="stTabs"] button:hover, button[role="tab"]:hover {
    background: rgba(41, 216, 244, 0.16) !important;
    border-color: rgba(41, 216, 244, 0.65) !important;
    box-shadow: 0 2px 14px rgba(41, 216, 244, 0.2) !important;
    transform: translateY(-1px) !important;
}

button[data-baseweb="tab"]:hover *, [data-testid="stTabs"] button:hover *, button[role="tab"]:hover * {
    color: #29D8F4 !important;
}

/* Active / Selected Tab */
button[data-baseweb="tab"][aria-selected="true"],
[data-testid="stTabs"] button[aria-selected="true"],
button[role="tab"][aria-selected="true"] {
    background: linear-gradient(135deg, rgba(41, 216, 244, 0.28) 0%, rgba(79, 140, 255, 0.22) 100%) !important;
    border: 1px solid rgba(41, 216, 244, 0.75) !important;
    border-bottom: 2px solid #29D8F4 !important;
    box-shadow: 0 4px 18px rgba(41, 216, 244, 0.28) !important;
}

button[data-baseweb="tab"][aria-selected="true"] *,
[data-testid="stTabs"] button[aria-selected="true"] *,
button[role="tab"][aria-selected="true"] * {
    color: #FFFFFF !important;
    font-weight: 700 !important;
}

/* Segmented Control Styling — High Contrast Dark Glass Pills */
div[data-testid="stSegmentedControl"] {
    background: rgba(16, 28, 48, 0.85) !important;
    border: 1px solid rgba(79, 140, 255, 0.3) !important;
    border-radius: 12px !important;
    padding: 6px !important;
    gap: 8px !important;
    margin-bottom: 20px !important;
}

div[data-testid="stSegmentedControl"] button {
    background: rgba(21, 36, 59, 0.80) !important;
    border: 1px solid rgba(79, 140, 255, 0.25) !important;
    border-radius: 8px !important;
    padding: 10px 22px !important;
    color: #E2ECFA !important;
    font-size: 13.5px !important;
    font-weight: 600 !important;
    transition: all 0.22s ease !important;
}

div[data-testid="stSegmentedControl"] button * {
    color: #E2ECFA !important;
    font-weight: 600 !important;
}

div[data-testid="stSegmentedControl"] button:hover {
    background: rgba(41, 216, 244, 0.16) !important;
    border-color: rgba(41, 216, 244, 0.6) !important;
    color: #29D8F4 !important;
}

div[data-testid="stSegmentedControl"] button:hover * {
    color: #29D8F4 !important;
}

div[data-testid="stSegmentedControl"] button[aria-selected="true"],
div[data-testid="stSegmentedControl"] button[data-checked="true"] {
    background: linear-gradient(135deg, rgba(41, 216, 244, 0.28) 0%, rgba(79, 140, 255, 0.22) 100%) !important;
    border: 1px solid rgba(41, 216, 244, 0.8) !important;
    box-shadow: 0 0 16px rgba(41, 216, 244, 0.25) !important;
}

div[data-testid="stSegmentedControl"] button[aria-selected="true"] *,
div[data-testid="stSegmentedControl"] button[data-checked="true"] * {
    color: #FFFFFF !important;
    font-weight: 700 !important;
}

/* Global Form Widget Label Styling — High Contrast & Legibility */
label[data-testid="stWidgetLabel"],
label[data-testid="stWidgetLabel"] p,
label[data-testid="stWidgetLabel"] span,
label[data-testid="stWidgetLabel"] div,
[data-testid="stWidgetLabel"] *,
div[data-baseweb="select"] ~ label,
label[data-baseweb="label"] {
    color: #DCE9F8 !important;
    font-size: 13.5px !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
}

/* Selectbox Dropdown Container & Menu Items */
div[data-baseweb="select"] > div {
    background-color: rgba(21, 36, 59, 0.85) !important;
    border: 1px solid rgba(79, 140, 255, 0.32) !important;
    color: #F4F8FF !important;
    border-radius: 8px !important;
}

div[data-baseweb="select"] * {
    color: #F4F8FF !important;
}

div[data-baseweb="popover"] ul, div[data-baseweb="menu"] {
    background-color: #101C30 !important;
    border: 1px solid rgba(79, 140, 255, 0.3) !important;
}

div[data-baseweb="popover"] li, div[data-baseweb="menu"] li {
    color: #F4F8FF !important;
}

/* Animations */
@keyframes pulse-dot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.35; transform: scale(0.85); }
}

@keyframes float-element {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-4px); }
}

/* Section Header Bar */
.nexus-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 24px;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(79, 140, 255, 0.15);
}

.nexus-section-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: 'Manrope', sans-serif;
    font-size: 19px;
    font-weight: 700;
    color: #F4F8FF;
    letter-spacing: -0.01em;
}

.nexus-section-indicator {
    width: 4px;
    height: 18px;
    border-radius: 2px;
    background: linear-gradient(180deg, #29D8F4, #4F8CFF);
    display: inline-block;
}

/* Glassmorphism Card System */
.nexus-card {
    background: linear-gradient(135deg, rgba(21, 36, 59, 0.78) 0%, rgba(16, 28, 48, 0.88) 100%);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(79, 140, 255, 0.18);
    border-radius: 14px;
    padding: 22px;
    margin-bottom: 16px;
    transition: transform 0.28s ease, box-shadow 0.28s ease, border-color 0.28s ease;
    box-shadow: 0 4px 22px rgba(0, 0, 0, 0.3);
    position: relative;
    overflow: hidden;
}

.nexus-card:hover {
    border-color: rgba(41, 216, 244, 0.42);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), 0 0 20px rgba(41, 216, 244, 0.12);
    transform: translateY(-2px);
}

.nexus-card-featured {
    background: linear-gradient(135deg, rgba(21, 36, 59, 0.92) 0%, rgba(16, 28, 48, 0.96) 100%);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(41, 216, 244, 0.32);
    border-radius: 14px;
    padding: 24px;
    margin-bottom: 16px;
    transition: transform 0.28s ease, box-shadow 0.28s ease, border-color 0.28s ease;
    box-shadow: 0 4px 22px rgba(0, 0, 0, 0.35), 0 0 20px rgba(41, 216, 244, 0.08);
    position: relative;
    overflow: hidden;
}

.nexus-card-featured:hover {
    border-color: rgba(41, 216, 244, 0.55);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45), 0 0 25px rgba(41, 216, 244, 0.22);
    transform: translateY(-2px);
}

.nexus-card-nav-link {
    display: flex;
    align-items: center;
    justify-content: space-between;
    text-decoration: none !important;
    cursor: pointer !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.nexus-card-nav-link:hover {
    background: rgba(41, 216, 244, 0.16) !important;
    border-color: rgba(41, 216, 244, 0.65) !important;
    box-shadow: 0 2px 14px rgba(41, 216, 244, 0.25) !important;
    color: #FFFFFF !important;
    transform: translateX(2px);
}

.nexus-card-nav-link:hover span {
    color: #FFFFFF !important;
}

/* KPI Metric Cards — Visually Striking & Polished */
.nexus-kpi-card {
    background: linear-gradient(145deg, rgba(21, 36, 59, 0.88) 0%, rgba(16, 28, 48, 0.96) 100%);
    backdrop-filter: blur(14px);
    border: 1px solid rgba(41, 216, 244, 0.22);
    border-radius: 14px;
    padding: 16px 18px;
    position: relative;
    overflow: hidden;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 4px 22px rgba(0, 0, 0, 0.35);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 185px;
    height: 100%;
    box-sizing: border-box;
}

/* Ensure equal height stretch across Streamlit columns */
div[data-testid="column"] {
    display: flex !important;
    flex-direction: column !important;
}
div[data-testid="column"] > div {
    flex: 1 1 auto !important;
    display: flex !important;
    flex-direction: column !important;
}
div[data-testid="column"] > div > div {
    flex: 1 1 auto !important;
    display: flex !important;
    flex-direction: column !important;
}

.nexus-kpi-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 3px;
    background: linear-gradient(90deg, #29D8F4 0%, #4F8CFF 50%, #9685FF 100%);
    opacity: 0.9;
}

.kpi-accent-cyan::before { background: linear-gradient(90deg, #29D8F4, #4F8CFF) !important; }
.kpi-accent-purple::before { background: linear-gradient(90deg, #9685FF, #29D8F4) !important; }
.kpi-accent-amber::before { background: linear-gradient(90deg, #FFBF69, #FF9F1C) !important; }
.kpi-accent-green::before { background: linear-gradient(90deg, #35D6A1, #29D8F4) !important; }
.kpi-accent-red::before { background: linear-gradient(90deg, #FF647C, #FF3366) !important; }
.kpi-accent-blue::before { background: linear-gradient(90deg, #4F8CFF, #29D8F4) !important; }

.nexus-kpi-card:hover {
    transform: translateY(-3px);
    border-color: rgba(41, 216, 244, 0.55);
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.5), 0 0 24px rgba(41, 216, 244, 0.2);
}

.kpi-header {
    display: flex;
    justify-content: flex-start;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 6px;
    min-height: 38px;
}

.kpi-title {
    font-size: 11.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #9FB1C9;
    line-height: 1.3;
    word-break: break-word;
    flex: 1;
    min-height: 32px;
    display: flex;
    align-items: center;
}

.kpi-icon-wrapper {
    width: 34px;
    height: 34px;
    flex-shrink: 0;
    border-radius: 50%;
    background: rgba(41, 216, 244, 0.12);
    border: 1px solid rgba(41, 216, 244, 0.35);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    box-shadow: 0 0 12px rgba(41, 216, 244, 0.18);
    transition: transform 0.25s ease;
}

.kpi-icon-wrapper.kpi-icon-cyan {
    background: rgba(41, 216, 244, 0.14);
    border-color: rgba(41, 216, 244, 0.45);
    box-shadow: 0 0 12px rgba(41, 216, 244, 0.24);
}
.kpi-icon-wrapper.kpi-icon-purple {
    background: rgba(150, 133, 255, 0.14);
    border-color: rgba(150, 133, 255, 0.45);
    box-shadow: 0 0 12px rgba(150, 133, 255, 0.24);
}
.kpi-icon-wrapper.kpi-icon-amber {
    background: rgba(255, 191, 105, 0.14);
    border-color: rgba(255, 191, 105, 0.45);
    box-shadow: 0 0 12px rgba(255, 191, 105, 0.24);
}
.kpi-icon-wrapper.kpi-icon-green {
    background: rgba(53, 214, 161, 0.14);
    border-color: rgba(53, 214, 161, 0.45);
    box-shadow: 0 0 12px rgba(53, 214, 161, 0.24);
}
.kpi-icon-wrapper.kpi-icon-red {
    background: rgba(255, 100, 124, 0.14);
    border-color: rgba(255, 100, 124, 0.45);
    box-shadow: 0 0 12px rgba(255, 100, 124, 0.24);
}
.kpi-icon-wrapper.kpi-icon-blue {
    background: rgba(79, 140, 255, 0.14);
    border-color: rgba(79, 140, 255, 0.45);
    box-shadow: 0 0 12px rgba(79, 140, 255, 0.24);
}

.kpi-sparkline {
    margin: 6px 0 6px 0;
    width: 100%;
    height: 30px;
    display: block;
}

.kpi-value {
    font-family: 'Manrope', sans-serif;
    font-size: 30px;
    font-weight: 800;
    color: #F4F8FF;
    line-height: 1.15;
    margin-bottom: 4px;
    letter-spacing: -0.02em;
    min-height: 36px;
    display: flex;
    align-items: baseline;
}

.kpi-unit {
    font-size: 15px;
    font-weight: 600;
    color: #29D8F4;
    margin-left: 4px;
}

.kpi-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 11.5px;
    color: #9FB1C9;
    margin-top: auto;
    padding-top: 8px;
    border-top: 1px solid rgba(159, 177, 201, 0.12);
    min-height: 32px;
}

/* Provenance & Status Badges */
.badge-nexus {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3.5px 9.5px;
    border-radius: 5px;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    line-height: 1.2;
}

.badge-real-api {
    background: rgba(41, 216, 244, 0.16);
    color: #29D8F4;
    border: 1px solid rgba(41, 216, 244, 0.45);
    box-shadow: 0 0 8px rgba(41, 216, 244, 0.15);
}

.badge-simulated {
    background: rgba(255, 191, 105, 0.16);
    color: #FFBF69;
    border: 1px solid rgba(255, 191, 105, 0.45);
    box-shadow: 0 0 8px rgba(255, 191, 105, 0.12);
}

.badge-prototype {
    background: rgba(150, 133, 255, 0.16);
    color: #9685FF;
    border: 1px solid rgba(150, 133, 255, 0.45);
    box-shadow: 0 0 8px rgba(150, 133, 255, 0.15);
}

.badge-positive {
    background: rgba(53, 214, 161, 0.16);
    color: #35D6A1;
    border: 1px solid rgba(53, 214, 161, 0.45);
}

.badge-critical {
    background: rgba(255, 100, 124, 0.18);
    color: #FF647C;
    border: 1px solid rgba(255, 100, 124, 0.45);
    box-shadow: 0 0 10px rgba(255, 100, 124, 0.2);
}

.live-pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: #35D6A1;
    display: inline-block;
    box-shadow: 0 0 8px #35D6A1;
    animation: pulse-dot 1.8s infinite;
}

/* Hero Section Banner — Clean Command Center Glassmorphism */
.nexus-hero {
    background-color: #080F1E;
    border: 1px solid rgba(41, 216, 244, 0.35);
    border-radius: 18px;
    padding: 30px 36px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 10px 36px rgba(0, 0, 0, 0.45), 0 0 25px rgba(41, 216, 244, 0.12);
}

.nexus-hero-bg-img {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center center;
    z-index: 1;
    pointer-events: none;
    opacity: 0.95;
}

.nexus-hero-gradient-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: 
        linear-gradient(to right, rgba(8, 15, 30, 0.95) 0%, rgba(8, 15, 30, 0.82) 48%, rgba(8, 15, 30, 0.35) 75%, rgba(8, 15, 30, 0.70) 100%),
        linear-gradient(to bottom, rgba(8, 15, 30, 0.05) 0%, rgba(8, 15, 30, 0.25) 65%, #080F1E 100%);
    z-index: 2;
    pointer-events: none;
}

.nexus-hero-content {
    position: relative;
    z-index: 3;
    max-width: 880px;
}

.nexus-hero-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 28px;
    align-items: start;
    position: relative;
    z-index: 3;
    width: 100%;
}

@media (max-width: 992px) {
    .nexus-hero-grid {
        grid-template-columns: 1fr;
    }
}

.zero-mile-card {
    background: rgba(16, 28, 48, 0.84);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(41, 216, 244, 0.36);
    border-radius: 14px;
    padding: 20px 22px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4), 0 0 16px rgba(41, 216, 244, 0.12);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

.nexus-hero-title {
    font-family: 'Manrope', sans-serif;
    font-size: 35px;
    font-weight: 800;
    color: #F4F8FF;
    letter-spacing: -0.025em;
    margin-bottom: 8px;
    background: linear-gradient(90deg, #F4F8FF 40%, #29D8F4 85%, #9685FF 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    line-height: 1.15;
}

.nexus-hero-subtitle {
    font-size: 15px;
    font-weight: 400;
    color: #C1D3EB;
    margin-bottom: 16px;
    max-width: 840px;
    line-height: 1.55;
}

.nexus-location-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(8, 15, 30, 0.78);
    border: 1px solid rgba(41, 216, 244, 0.35);
    padding: 6px 15px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    color: #29D8F4;
    letter-spacing: 0.03em;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
}

/* Page Header Component */
.nexus-page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 22px;
    padding-bottom: 16px;
    border-bottom: 1px solid rgba(79, 140, 255, 0.15);
}

.nexus-page-title {
    font-family: 'Manrope', sans-serif;
    font-size: 27px;
    font-weight: 800;
    color: #F4F8FF;
    letter-spacing: -0.015em;
    margin-bottom: 4px;
}

.nexus-page-desc {
    font-size: 14.5px;
    color: #9FB1C9;
}

/* Streamlit Widget Overrides */
div[data-testid="stMetric"] {
    background: rgba(21, 36, 59, 0.75) !important;
    border: 1px solid rgba(79, 140, 255, 0.22) !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
    box-shadow: 0 4px 18px rgba(0,0,0,0.25) !important;
}

div[data-testid="stMetricLabel"] p {
    color: #9FB1C9 !important;
    font-weight: 600 !important;
    font-size: 12.5px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}

div[data-testid="stMetricValue"] {
    color: #F4F8FF !important;
    font-family: 'Manrope', sans-serif !important;
    font-weight: 800 !important;
}

div[data-testid="stExpander"] {
    background: rgba(21, 36, 59, 0.55) !important;
    border: 1px solid rgba(79, 140, 255, 0.22) !important;
    border-radius: 12px !important;
    margin-top: 16px !important;
}

div[data-testid="stExpander"] summary {
    color: #29D8F4 !important;
    font-weight: 600 !important;
}

/* Custom Table / Dataframe Dark Aesthetics */
div[data-testid="stDataFrame"] {
    border-radius: 12px !important;
    overflow: hidden !important;
    border: 1px solid rgba(79, 140, 255, 0.22) !important;
}

/* Button Styling */
button[kind="primary"], button[kind="secondary"], .stButton > button {
    background: linear-gradient(135deg, rgba(41, 216, 244, 0.22) 0%, rgba(79, 140, 255, 0.28) 100%) !important;
    color: #F4F8FF !important;
    border: 1px solid rgba(41, 216, 244, 0.45) !important;
    border-radius: 8px !important;
    padding: 9px 20px !important;
    font-weight: 600 !important;
    transition: all 0.25s ease !important;
}

button[kind="primary"]:hover, button[kind="secondary"]:hover, .stButton > button:hover {
    background: linear-gradient(135deg, rgba(41, 216, 244, 0.38) 0%, rgba(79, 140, 255, 0.45) 100%) !important;
    border-color: #29D8F4 !important;
    box-shadow: 0 0 18px rgba(41, 216, 244, 0.3) !important;
    transform: translateY(-2px) !important;
}
</style>
"""


def apply_nexus_theme(fig: go.Figure, height: Optional[int] = None) -> go.Figure:
    """
    Standardizes a Plotly figure to the UrbanPulse NEXUS visual identity:
    Dark/transparent canvas, cyan/electric blue/violet accents, Inter typography,
    subtle gridlines, and clean responsive formatting.
    """
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(16, 28, 48, 0.45)",
        font=dict(
            family="Inter, Manrope, sans-serif",
            color="#F4F8FF",
            size=12,
        ),
        margin=dict(l=42, r=26, t=46, b=42),
        legend=dict(
            bgcolor="rgba(21, 36, 59, 0.65)",
            bordercolor="rgba(79, 140, 255, 0.25)",
            borderwidth=1,
            font=dict(color="#9FB1C9", size=11),
        ),
        hoverlabel=dict(
            bgcolor="#15243B",
            bordercolor="#29D8F4",
            font=dict(family="Inter, sans-serif", color="#F4F8FF", size=12),
        ),
    )

    if height:
        fig.update_layout(height=height)

    fig.update_xaxes(
        gridcolor="rgba(159, 177, 201, 0.12)",
        zerolinecolor="rgba(41, 216, 244, 0.28)",
        tickfont=dict(color="#9FB1C9", size=11),
        title_font=dict(color="#F4F8FF", size=12),
    )
    fig.update_yaxes(
        gridcolor="rgba(159, 177, 201, 0.12)",
        zerolinecolor="rgba(41, 216, 244, 0.28)",
        tickfont=dict(color="#9FB1C9", size=11),
        title_font=dict(color="#F4F8FF", size=12),
    )
    return fig


def render_nexus_header(title: str, subtitle: str, provenance_badge: Optional[str] = None):
    """Renders a standardized, clean page header with provenance indicator."""
    badge_html = f'<span class="{get_badge_class(provenance_badge)}">{provenance_badge}</span>' if provenance_badge else ""
    st.markdown(
        f"""
        <div class="nexus-page-header">
            <div>
                <div class="nexus-page-title">{title}</div>
                <div class="nexus-page-desc">{subtitle}</div>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
                <span class="nexus-location-pill">📍 Nagpur, MH</span>
                {badge_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title: str, subtitle: Optional[str] = None, badge: Optional[str] = None):
    """Renders an elegant section divider header with glowing indicator."""
    badge_html = f'<span class="{get_badge_class(badge)}">{badge}</span>' if badge else ""
    sub_html = f'<div style="font-size: 12.5px; color: #9FB1C9; margin-top: 2px;">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="nexus-section-header">
            <div>
                <div class="nexus-section-title">
                    <span class="nexus-section-indicator"></span>
                    {title}
                </div>
                {sub_html}
            </div>
            <div>{badge_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def get_badge_class(provenance: str) -> str:
    """Maps provenance names to CSS classes."""
    p = provenance.upper() if provenance else ""
    if "REAL" in p:
        return "badge-nexus badge-real-api"
    elif "SIM" in p:
        return "badge-nexus badge-simulated"
    elif "PROTOTYPE" in p or "LAB" in p or "HARDWARE" in p:
        return "badge-nexus badge-prototype"
    elif "CRITICAL" in p or "HIGH" in p:
        return "badge-nexus badge-critical"
    else:
        return "badge-nexus badge-positive"


def generate_svg_sparkline(sparkline_type: Optional[str] = "wave_cyan") -> str:
    """Generates glowing, lightweight responsive SVG sparklines for KPI metric cards."""
    if not sparkline_type or str(sparkline_type).lower() in ("none", "false", ""):
        return ""
    s_type = str(sparkline_type).lower()
    if s_type == "wave_cyan":
        return (
            '<svg viewBox="0 0 160 30" class="sparkline-svg" preserveAspectRatio="none" style="width: 100%; height: 30px; overflow: visible;">'
            '<defs>'
            '<linearGradient id="grad_cyan" x1="0%" y1="0%" x2="0%" y2="100%">'
            '<stop offset="0%" stop-color="#29D8F4" stop-opacity="0.38" />'
            '<stop offset="100%" stop-color="#29D8F4" stop-opacity="0.0" />'
            '</linearGradient>'
            '</defs>'
            '<path d="M 0,22 Q 25,6 50,18 T 100,10 T 135,20 T 160,8 L 160,30 L 0,30 Z" fill="url(#grad_cyan)" />'
            '<path d="M 0,22 Q 25,6 50,18 T 100,10 T 135,20 T 160,8" fill="none" stroke="#29D8F4" stroke-width="2.2" stroke-linecap="round" />'
            '<circle cx="160" cy="8" r="3" fill="#29D8F4" filter="drop-shadow(0 0 4px #29D8F4)" />'
            '</svg>'
        )
    elif s_type == "wave_purple":
        return (
            '<svg viewBox="0 0 160 30" class="sparkline-svg" preserveAspectRatio="none" style="width: 100%; height: 30px; overflow: visible;">'
            '<defs>'
            '<linearGradient id="grad_purple" x1="0%" y1="0%" x2="0%" y2="100%">'
            '<stop offset="0%" stop-color="#9685FF" stop-opacity="0.38" />'
            '<stop offset="100%" stop-color="#9685FF" stop-opacity="0.0" />'
            '</linearGradient>'
            '</defs>'
            '<path d="M 0,24 Q 28,26 55,14 T 110,18 T 140,8 T 160,12 L 160,30 L 0,30 Z" fill="url(#grad_purple)" />'
            '<path d="M 0,24 Q 28,26 55,14 T 110,18 T 140,8 T 160,12" fill="none" stroke="#9685FF" stroke-width="2.2" stroke-linecap="round" />'
            '<circle cx="160" cy="12" r="3" fill="#9685FF" filter="drop-shadow(0 0 4px #9685FF)" />'
            '</svg>'
        )
    elif s_type == "wave_amber":
        return (
            '<svg viewBox="0 0 160 30" class="sparkline-svg" preserveAspectRatio="none" style="width: 100%; height: 30px; overflow: visible;">'
            '<defs>'
            '<linearGradient id="grad_amber" x1="0%" y1="0%" x2="0%" y2="100%">'
            '<stop offset="0%" stop-color="#FFBF69" stop-opacity="0.38" />'
            '<stop offset="100%" stop-color="#FFBF69" stop-opacity="0.0" />'
            '</linearGradient>'
            '</defs>'
            '<path d="M 0,16 Q 30,26 60,12 T 110,24 T 140,10 T 160,16 L 160,30 L 0,30 Z" fill="url(#grad_amber)" />'
            '<path d="M 0,16 Q 30,26 60,12 T 110,24 T 140,10 T 160,16" fill="none" stroke="#FFBF69" stroke-width="2.2" stroke-linecap="round" />'
            '<circle cx="160" cy="16" r="3" fill="#FFBF69" filter="drop-shadow(0 0 4px #FFBF69)" />'
            '</svg>'
        )
    elif s_type == "wave_green":
        return (
            '<svg viewBox="0 0 160 30" class="sparkline-svg" preserveAspectRatio="none" style="width: 100%; height: 30px; overflow: visible;">'
            '<defs>'
            '<linearGradient id="grad_green" x1="0%" y1="0%" x2="0%" y2="100%">'
            '<stop offset="0%" stop-color="#35D6A1" stop-opacity="0.38" />'
            '<stop offset="100%" stop-color="#35D6A1" stop-opacity="0.0" />'
            '</linearGradient>'
            '</defs>'
            '<path d="M 0,26 Q 35,24 70,20 T 120,18 T 145,15 T 160,12 L 160,30 L 0,30 Z" fill="url(#grad_green)" />'
            '<path d="M 0,26 Q 35,24 70,20 T 120,18 T 145,15 T 160,12" fill="none" stroke="#35D6A1" stroke-width="2.2" stroke-linecap="round" />'
            '<circle cx="160" cy="12" r="3" fill="#35D6A1" filter="drop-shadow(0 0 4px #35D6A1)" />'
            '</svg>'
        )
    elif s_type == "wave_red":
        return (
            '<svg viewBox="0 0 160 30" class="sparkline-svg" preserveAspectRatio="none" style="width: 100%; height: 30px; overflow: visible;">'
            '<defs>'
            '<linearGradient id="grad_red" x1="0%" y1="0%" x2="0%" y2="100%">'
            '<stop offset="0%" stop-color="#FF647C" stop-opacity="0.38" />'
            '<stop offset="100%" stop-color="#FF647C" stop-opacity="0.0" />'
            '</linearGradient>'
            '</defs>'
            '<path d="M 0,26 Q 20,8 45,24 T 90,6 T 130,22 T 160,8 L 160,30 L 0,30 Z" fill="url(#grad_red)" />'
            '<path d="M 0,26 Q 20,8 45,24 T 90,6 T 130,22 T 160,8" fill="none" stroke="#FF647C" stroke-width="2.2" stroke-linecap="round" />'
            '<circle cx="160" cy="8" r="3" fill="#FF647C" filter="drop-shadow(0 0 4px #FF647C)" />'
            '</svg>'
        )
    elif s_type == "bars_blue":
        return (
            '<svg viewBox="0 0 160 30" class="sparkline-svg" preserveAspectRatio="none" style="width: 100%; height: 30px;">'
            '<defs>'
            '<linearGradient id="grad_bar" x1="0%" y1="0%" x2="0%" y2="100%">'
            '<stop offset="0%" stop-color="#29D8F4" stop-opacity="0.9" />'
            '<stop offset="100%" stop-color="#4F8CFF" stop-opacity="0.4" />'
            '</linearGradient>'
            '</defs>'
            '<rect x="5" y="16" width="6" height="14" rx="2" fill="url(#grad_bar)" />'
            '<rect x="18" y="10" width="6" height="20" rx="2" fill="url(#grad_bar)" />'
            '<rect x="31" y="14" width="6" height="16" rx="2" fill="url(#grad_bar)" />'
            '<rect x="44" y="6" width="6" height="24" rx="2" fill="url(#grad_bar)" />'
            '<rect x="57" y="12" width="6" height="18" rx="2" fill="url(#grad_bar)" />'
            '<rect x="70" y="8" width="6" height="22" rx="2" fill="url(#grad_bar)" />'
            '<rect x="83" y="18" width="6" height="12" rx="2" fill="url(#grad_bar)" />'
            '<rect x="96" y="11" width="6" height="19" rx="2" fill="url(#grad_bar)" />'
            '<rect x="109" y="5" width="6" height="25" rx="2" fill="url(#grad_bar)" />'
            '<rect x="122" y="13" width="6" height="17" rx="2" fill="url(#grad_bar)" />'
            '<rect x="135" y="7" width="6" height="23" rx="2" fill="url(#grad_bar)" />'
            '<rect x="148" y="12" width="6" height="18" rx="2" fill="url(#grad_bar)" />'
            '</svg>'
        )
    return ""


def render_kpi_card(
    label: str,
    value: Any,
    unit: str = "",
    delta: Optional[str] = None,
    provenance: Optional[str] = None,
    icon: str = "📊",
    help_text: Optional[str] = None,
    sparkline_type: Optional[str] = "auto",
    accent_color: str = "cyan",
):
    """Renders a responsive, interactive NEXUS KPI card with glowing top accent border and circular icon wrapper."""
    badge_cls = get_badge_class(provenance) if provenance else ""
    badge_html = f'<div style="flex-shrink: 0; margin-left: 6px;"><span class="{badge_cls}">{provenance}</span></div>' if provenance else ""

    delta_color = "#35D6A1"
    if delta:
        d_lower = delta.lower()
        if any(w in d_lower for w in ["critical", "requires triage", "alert", "stale"]):
            delta_color = "#FF647C"
        elif any(w in d_lower for w in ["warning", "congested", "delay", "standby", "provisional"]):
            delta_color = "#FFBF69"

    delta_html = f'<div style="color: {delta_color}; font-weight: 600; line-height: 1.35; font-size: 11.5px; word-break: break-word; flex: 1;">{delta}</div>' if delta else "<div></div>"

    # Decorative sparklines: default to matching accent wave unless explicitly suppressed ("none" or False)
    effective_spark = sparkline_type
    if effective_spark in (None, "auto"):
        color_spark_map = {
            "cyan": "wave_cyan",
            "purple": "wave_purple",
            "amber": "wave_amber",
            "green": "wave_green",
            "red": "wave_red",
            "blue": "bars_blue",
        }
        effective_spark = color_spark_map.get(accent_color, "wave_cyan")
    elif str(effective_spark).lower() in ("none", "false", ""):
        effective_spark = None

    sparkline_svg = generate_svg_sparkline(effective_spark) if effective_spark else ""
    sparkline_html = f'<div class="kpi-sparkline">{sparkline_svg}</div>' if sparkline_svg else '<div class="kpi-sparkline" style="visibility: hidden;"></div>'

    accent_class = f"kpi-accent-{accent_color}"
    icon_wrapper_class = f"kpi-icon-wrapper kpi-icon-{accent_color}"

    val_str = str(value) if value is not None else "—"
    is_numeric = False
    try:
        float(val_str.replace(",", "").replace("%", ""))
        is_numeric = True
    except ValueError:
        is_numeric = False

    if not is_numeric and len(val_str) > 12:
        val_style = "font-size: 19px; line-height: 1.25; word-break: break-word;"
    elif not is_numeric and len(val_str) > 5:
        val_style = "font-size: 22px; line-height: 1.2; word-break: break-word;"
    else:
        val_style = "font-size: 30px; font-weight: 800; white-space: nowrap;"

    card_html = (
        f'<div class="nexus-kpi-card {accent_class}">'
        f'<div class="kpi-header">'
        f'<div class="{icon_wrapper_class}">{icon}</div>'
        f'<span class="kpi-title">{label}</span>'
        f'</div>'
        f'<div class="kpi-value" style="{val_style}">{value}<span class="kpi-unit">{unit}</span></div>'
        f'{sparkline_html}'
        f'<div class="kpi-footer">'
        f'{delta_html}'
        f'{badge_html}'
        f'</div>'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)


@lru_cache(maxsize=1)
def get_hero_city_background_base64() -> str:
    """Loads and caches base64 representation of Image 2 (urbanpulse_hero_city_background.png)."""
    asset_path = Path(__file__).resolve().parent / "assets" / "urbanpulse_hero_city_background.png"
    if asset_path.exists():
        with open(asset_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""


@lru_cache(maxsize=1)
def get_sidebar_monument_image_base64() -> str:
    """Loads and caches base64 representation of Image 3 (urbanpulse_sidebar_monument.png)."""
    asset_path = Path(__file__).resolve().parent / "assets" / "urbanpulse_sidebar_monument.png"
    if asset_path.exists():
        with open(asset_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""


@lru_cache(maxsize=1)
def get_nagpur_hero_image_base64() -> str:
    """Fallback legacy loader kept for backwards compatibility."""
    asset_path = Path(__file__).resolve().parent / "assets" / "nagpur_cityscape.jpg"
    if asset_path.exists():
        with open(asset_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""


def inject_overview_page_background():
    """
    Ensures the Overview page uses a clean dark navy background without any full-page photo.
    The city panorama is scoped strictly to the upper hero container.
    """
    st.markdown(
        """
<style>
[data-testid="stMain"], section.main {
    background: transparent !important;
}
[data-testid="stMain"] > div:first-child,
.main .block-container {
    background: transparent !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def inject_default_page_background():
    """
    Restores the clean default transparent background for non-overview pages.
    Guarantees no hero imagery leaks into other views.
    """
    st.markdown(
        """
<style>
[data-testid="stMain"], section.main {
    background: transparent !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_nexus_hero(status_label: str = "SYNCED", status_cls: str = "badge-positive"):
    """
    Renders the signature command center hero section for Nagpur with the authentic
    urbanpulse_hero_city_background.png scoped strictly behind the hero region,
    using an absolute DOM image overlay and transparent gradient, presenting operations telemetry,
    heading, description, and location metadata in an open, balanced layout.
    """
    hero_b64 = get_hero_city_background_base64()

    hero_img_html = ""
    if hero_b64:
        hero_img_html = (
            f'<img src="data:image/png;base64,{hero_b64}" '
            f'class="nexus-hero-bg-img" '
            f'alt="Nagpur Smart City Panorama" />'
        )

    hero_html = (
'<div class="nexus-hero">'
f'{hero_img_html}'
'<div class="nexus-hero-gradient-overlay"></div>'
'<div class="nexus-hero-content">'
'<div>'
'<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap;">'
'<span class="nexus-location-pill">'
'<span class="live-pulse"></span>'
'NAGPUR OPERATIONS COMMAND'
'</span>'
'<span class="badge-nexus badge-real-api">ZERO MILE HUB</span>'
f'<span class="badge-nexus {status_cls}">{status_label}</span>'
'</div>'
'<div style="font-size: 11px; font-weight: 700; color: #29D8F4; text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 6px;">URBANPULSE NEXUS | URBAN INTELLIGENCE PLATFORM</div>'
'<div class="nexus-hero-title">Intelligence for a Smarter <span style="color: #29D8F4; -webkit-text-fill-color: #29D8F4;">Nagpur</span></div>'
'<div class="nexus-hero-subtitle">'
'An urban data intelligence platform integrating traffic, weather, air quality, and IoT observations to monitor and analyze conditions across Nagpur.'
'</div>'
'</div>'
'<div style="display: flex; flex-wrap: wrap; gap: 16px; margin-top: 18px; font-size: 13px; color: #9FB1C9;">'
'<span>📍 <strong>21.1458° N, 79.0882° E</strong></span>'
'<span>🏛️ <strong>Zero Mile Landmark Hub</strong></span>'
'<span>🛣️ <strong>15 Arterial Corridors</strong></span>'
'<span>🍃 <strong>Open-Meteo Vitals</strong></span>'
'<span>⏱️ <strong>Hourly Pipeline Ingestion</strong></span>'
'</div>'
'</div>'
'</div>'
    )
    st.markdown(hero_html, unsafe_allow_html=True)
