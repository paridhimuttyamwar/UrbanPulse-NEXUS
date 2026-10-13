"""
Targeted Verification Script for UrbanPulse NEXUS Overview Fixes (Tasks 1 to 5).
Checks:
1. Removal of top Zero Mile Station card from render_nexus_hero() while keeping hero panorama and metadata.
2. Bottom Atmospheric & Municipal Node section contains all 3 cards with all original fields.
3. Matching hover elevation effect on .nexus-card-featured identical to .nexus-card.
4. Navigation link to Edge IoT Lab via Streamlit navigation and state synchronization.
"""

import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from streamlit.testing.v1 import AppTest

def test_task1_top_hero_card_removed():
    print("[1/4] Verifying Task 1: Top Zero Mile Station hero card removal...")
    theme_file = root_dir / "dashboard" / "theme.py"
    content = theme_file.read_text(encoding="utf-8")
    
    # In render_nexus_hero
    hero_def = content[content.find("def render_nexus_hero") :]
    assert "class=\"zero-mile-card\"" not in hero_def, "Found zero-mile-card in render_nexus_hero!"
    assert "monument_thumb_html" not in hero_def, "Found monument_thumb_html in render_nexus_hero!"
    assert "Edge Ingestion Prototype (IoT) | Virtual Gateway Lab" not in hero_def, "Found old prototype link in top hero!"
    
    # Ensure hero essentials are preserved
    assert "urbanpulse_hero_city_background.png" in content
    assert "nexus-hero-bg-img" in hero_def
    assert "nexus-hero-gradient-overlay" in hero_def
    assert "NAGPUR OPERATIONS COMMAND" in hero_def
    assert "ZERO MILE HUB" in hero_def
    assert "Intelligence for a Smarter" in hero_def
    assert "21.1458° N, 79.0882° E" in hero_def
    assert "Zero Mile Landmark Hub" in hero_def
    assert "15 Arterial Corridors" in hero_def
    print(" -> Top Zero Mile Station card removed from hero.")
    print(" -> Hero panorama background and Nagpur metadata preserved.")
    print(" [PASSED] Task 1 Verified.")

def test_task2_bottom_three_cards_preserved():
    print("[2/4] Verifying Task 2: All 3 Atmospheric & Municipal Node cards preserved...")
    overview_file = root_dir / "dashboard" / "views" / "overview.py"
    content = overview_file.read_text(encoding="utf-8")
    
    # Card 1: Weather Microclimate
    assert "Weather Microclimate" in content, "Missing Weather Microclimate card"
    # Card 2: Atmospheric Purity (AQI)
    assert "Atmospheric Purity (AQI)" in content, "Missing Atmospheric Purity card"
    # Card 3: Zero Mile Municipal Node
    assert "Zero Mile Municipal Node" in content, "Missing Zero Mile Municipal Node card"
    assert "LOC_NAGPUR" in content, "Missing LOC_NAGPUR node ID"
    assert "21.1458° N" in content, "Missing latitude"
    assert "79.0882° E" in content, "Missing longitude"
    assert "310 m MSL" in content, "Missing altitude"
    assert "Hybrid (API + SIM)" in content, "Missing Hybrid mode"
    assert "Live Sync" in content, "Missing Live Sync telemetry"
    assert "Edge Lab: Zero Mile Station (Arduino Uno R3 Prototype)" in content, "Missing Edge Lab link label"
    print(" -> All 3 cards present with exact metrics and fields.")
    print(" [PASSED] Task 2 Verified.")

def test_task4_matching_hover_effect():
    print("[3/4] Verifying Task 4: Matching hover elevation effect...")
    theme_file = root_dir / "dashboard" / "theme.py"
    content = theme_file.read_text(encoding="utf-8")
    
    # Check .nexus-card transition and hover
    assert ".nexus-card:hover" in content
    assert "transform: translateY(-2px);" in content
    assert "transition: transform 0.28s ease, box-shadow 0.28s ease, border-color 0.28s ease;" in content
    
    # Check .nexus-card-featured transition and hover
    assert ".nexus-card-featured:hover" in content
    featured_idx = content.find(".nexus-card-featured {")
    featured_block = content[featured_idx : content.find("/* KPI Metric Cards", featured_idx)]
    assert "transform: translateY(-2px);" in featured_block, "nexus-card-featured missing translateY(-2px) on hover!"
    assert "transition: transform 0.28s ease" in featured_block, "nexus-card-featured missing 0.28s transition!"
    print(" -> .nexus-card-featured has matching translateY(-2px) hover elevation and 0.28s transition.")
    print(" [PASSED] Task 4 Verified.")

def test_task3_navigation_flow():
    print("[4/4] Verifying Task 3: Edge IoT Lab navigation & state synchronization...")
    app_file = root_dir / "dashboard" / "app.py"
    at = AppTest.from_file(str(app_file))
    at.run(timeout=15)
    
    # Initial state
    assert at.radio[0].value == "🏙️ Overview", f"Initial page not Overview: {at.radio[0].value}"
    print(" -> Initial page successfully loaded as: 🏙️ Overview")
    
    # Simulate clicking Edge IoT Lab link via ?nav=iot
    at.query_params["nav"] = "iot"
    at.run(timeout=15)
    assert at.radio[0].value == "🔌 Edge IoT Lab", f"Expected Edge IoT Lab, got: {at.radio[0].value}"
    print(" -> Query param ?nav=iot successfully navigated to: 🔌 Edge IoT Lab")
    print(" -> Sidebar active radio indicator automatically updated to: 🔌 Edge IoT Lab")
    
    # Simulate user clicking back to Overview in sidebar radio
    at.radio[0].set_value("🏙️ Overview").run()
    assert at.radio[0].value == "🏙️ Overview", f"Failed to return to Overview: {at.radio[0].value}"
    print(" -> Sidebar radio return to 🏙️ Overview successfully verified.")
    print(" [PASSED] Task 3 Verified.")

if __name__ == "__main__":
    print("=======================================================")
    print("URBANPULSE NEXUS — OVERVIEW FIXES VERIFICATION SUITE")
    print("=======================================================\n")
    test_task1_top_hero_card_removed()
    test_task2_bottom_three_cards_preserved()
    test_task4_matching_hover_effect()
    test_task3_navigation_flow()
    print("\n=======================================================")
    print("ALL 4 TASK VERIFICATIONS PASSED CLEANLY WITH 0 ERRORS!")
    print("=======================================================")
