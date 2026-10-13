"""
UrbanPulse Realistic Urban Traffic Simulator.
Simulates realistic vehicle flows, rush hour diurnal patterns, weekend vs weekday shifts,
road capacity constraints, and stochastic congestion incidents across 15 road segments.
All records are explicitly tagged as SIMULATED.
"""

import math
import random
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Generator, List, Optional

from config.settings import settings
from database.repository import repository
from validation.validator import ValidationEngine


class TrafficSimulator:
    """
    Realistic traffic simulation engine.
    
    Assumptions:
    1. Greenshields-inspired speed-density relationship: As density increases towards jam density,
       average speed declines non-linearly.
    2. Rush hour dynamics:
       - Morning peak (08:30 - 10:30): Up to 2.5x baseline traffic volume.
       - Evening peak (17:30 - 20:30): Up to 2.8x baseline traffic volume.
       - Night trough (23:00 - 05:00): ~15%-25% baseline traffic.
    3. Weekend adjustments: Morning rush is attenuated; afternoon & evening recreational traffic peaks.
    4. Random Incident Factor: 4% chance of a localized spike (breakdown, bottleneck) dropping speed by ~60%.
    5. All records carry source_type = 'SIMULATED'.
    """

    def __init__(self, random_seed: Optional[int] = 42, location_id: Optional[str] = None):
        if random_seed is not None:
            random.seed(random_seed)
        self.location_id = location_id or settings.DEFAULT_LOCATION_ID
        self.segments_cache = []
        self._load_segments()

    def _load_segments(self):
        """Loads road segment topologies from MySQL for the active city or falls back to Nagpur defaults."""
        try:
            db_segments = repository.get_all_road_segments(location_id=self.location_id)
            if db_segments:
                self.segments_cache = db_segments
                return
        except Exception:
            pass

        # Fallback in-memory segments for Nagpur if DB query is deferred or before migration
        self.segments_cache = [
            {"segment_id": "SEG_NAG_01", "sensor_id": "SNS_TRF_NAG_01", "road_name": "Wardha Road - Airport Corridor", "segment_type": "HIGHWAY", "speed_limit_kmh": 70, "length_km": 6.0, "capacity_vph": 4500},
            {"segment_id": "SEG_NAG_02", "sensor_id": "SNS_TRF_NAG_02", "road_name": "Sitabuldi Main Road", "segment_type": "DOWNTOWN", "speed_limit_kmh": 35, "length_km": 1.8, "capacity_vph": 2000},
            {"segment_id": "SEG_NAG_03", "sensor_id": "SNS_TRF_NAG_03", "road_name": "Dharampeth - Shankar Nagar Road", "segment_type": "ARTERIAL", "speed_limit_kmh": 45, "length_km": 2.5, "capacity_vph": 2600},
            {"segment_id": "SEG_NAG_04", "sensor_id": "SNS_TRF_NAG_04", "road_name": "Sadar Main Road", "segment_type": "DOWNTOWN", "speed_limit_kmh": 35, "length_km": 2.0, "capacity_vph": 2100},
            {"segment_id": "SEG_NAG_05", "sensor_id": "SNS_TRF_NAG_05", "road_name": "Manish Nagar Main Road", "segment_type": "ARTERIAL", "speed_limit_kmh": 40, "length_km": 3.0, "capacity_vph": 2400},
            {"segment_id": "SEG_NAG_06", "sensor_id": "SNS_TRF_NAG_06", "road_name": "Hingna Road", "segment_type": "ARTERIAL", "speed_limit_kmh": 50, "length_km": 4.5, "capacity_vph": 3000},
            {"segment_id": "SEG_NAG_07", "sensor_id": "SNS_TRF_NAG_07", "road_name": "Amravati Road", "segment_type": "HIGHWAY", "speed_limit_kmh": 65, "length_km": 5.5, "capacity_vph": 4000},
            {"segment_id": "SEG_NAG_08", "sensor_id": "SNS_TRF_NAG_08", "road_name": "Kamptee Road", "segment_type": "HIGHWAY", "speed_limit_kmh": 65, "length_km": 5.0, "capacity_vph": 4000},
            {"segment_id": "SEG_NAG_09", "sensor_id": "SNS_TRF_NAG_09", "road_name": "Central Avenue Road", "segment_type": "ARTERIAL", "speed_limit_kmh": 45, "length_km": 4.0, "capacity_vph": 2800},
            {"segment_id": "SEG_NAG_10", "sensor_id": "SNS_TRF_NAG_10", "road_name": "Medical Square - Ajni Road", "segment_type": "ARTERIAL", "speed_limit_kmh": 40, "length_km": 3.2, "capacity_vph": 2500},
            {"segment_id": "SEG_NAG_11", "sensor_id": "SNS_TRF_NAG_11", "road_name": "Trimurti Nagar Main Road", "segment_type": "SUBURBAN", "speed_limit_kmh": 40, "length_km": 2.8, "capacity_vph": 2000},
            {"segment_id": "SEG_NAG_12", "sensor_id": "SNS_TRF_NAG_12", "road_name": "Nandanvan Main Road", "segment_type": "SUBURBAN", "speed_limit_kmh": 40, "length_km": 2.6, "capacity_vph": 1900},
            {"segment_id": "SEG_NAG_13", "sensor_id": "SNS_TRF_NAG_13", "road_name": "MIHAN Access Road", "segment_type": "HIGHWAY", "speed_limit_kmh": 70, "length_km": 5.0, "capacity_vph": 3800},
            {"segment_id": "SEG_NAG_14", "sensor_id": "SNS_TRF_NAG_14", "road_name": "Civil Lines Road", "segment_type": "DOWNTOWN", "speed_limit_kmh": 40, "length_km": 2.2, "capacity_vph": 2200},
            {"segment_id": "SEG_NAG_15", "sensor_id": "SNS_TRF_NAG_15", "road_name": "Ring Road - Narendra Nagar Corridor", "segment_type": "HIGHWAY", "speed_limit_kmh": 65, "length_km": 6.5, "capacity_vph": 4200},
        ]

    def _get_time_multiplier(self, dt: datetime) -> float:
        """Computes diurnal traffic demand multiplier based on time of day and day of week."""
        hour = dt.hour + dt.minute / 60.0
        is_weekend = dt.weekday() >= 5

        if is_weekend:
            # Weekend diurnal curve
            if 0 <= hour < 7:
                return 0.20
            elif 7 <= hour < 12:
                return 0.70 + 0.30 * math.sin((hour - 7) / 5 * math.pi)
            elif 12 <= hour < 17:
                return 1.10
            elif 17 <= hour < 22:
                return 1.45 + 0.25 * math.sin((hour - 17) / 5 * math.pi)
            else:
                return 0.50
        else:
            # Weekday diurnal curve with dual sharp rush hours
            if 0 <= hour < 5.5:
                return 0.15
            elif 5.5 <= hour < 8.0:
                # Morning ramp-up
                return 0.30 + 1.2 * ((hour - 5.5) / 2.5)
            elif 8.0 <= hour <= 11.0:
                # Morning rush hour peak
                peak_center = 9.5
                dist = abs(hour - peak_center)
                return 2.4 - (dist * 0.5)
            elif 11.0 < hour < 16.5:
                # Midday plateau
                return 1.15 + random.uniform(-0.1, 0.1)
            elif 16.5 <= hour <= 20.5:
                # Evening rush hour peak
                peak_center = 18.5
                dist = abs(hour - peak_center)
                return 2.7 - (dist * 0.6)
            elif 20.5 < hour < 23.0:
                # Evening taper
                return 1.2 - ((hour - 20.5) / 2.5) * 0.7
            else:
                return 0.35

    def generate_single_reading(
        self, segment: Dict[str, Any], sim_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Generates a physically realistic traffic reading for a given road segment."""
        current_time = sim_time or datetime.utcnow()
        speed_limit = float(segment.get("speed_limit_kmh", 50))
        capacity = float(segment.get("capacity_vph", 2200))
        length_km = float(segment.get("length_km", 2.0))

        multiplier = self._get_time_multiplier(current_time)
        
        # Base flow demand (vehicles per hour)
        base_demand = (capacity * 0.40) * multiplier
        # Add natural stochastic variance
        stochastic_noise = random.gauss(0, capacity * 0.05)
        demand_flow = max(50.0, base_demand + stochastic_noise)

        # Incident / Congestion Spike check (4% probability)
        is_incident = random.random() < 0.04
        if is_incident:
            demand_flow *= 1.4

        # Volume-to-Capacity ratio (V/C)
        vc_ratio = demand_flow / capacity

        # Greenshields model speed curve
        if vc_ratio <= 0.4:
            # Free flow condition
            avg_speed = speed_limit * random.uniform(0.88, 1.05)
        elif vc_ratio <= 0.8:
            # Moderate traffic
            avg_speed = speed_limit * (1.0 - 0.45 * ((vc_ratio - 0.4) / 0.4))
        elif vc_ratio <= 1.2:
            # Heavy congestion
            avg_speed = speed_limit * (0.55 - 0.35 * ((vc_ratio - 0.8) / 0.4))
        else:
            # Jam condition
            avg_speed = speed_limit * random.uniform(0.08, 0.20)

        # Apply incident penalty if triggered
        if is_incident:
            avg_speed = max(5.0, avg_speed * 0.40)

        avg_speed = round(max(5.0, min(speed_limit * 1.15, avg_speed)), 2)

        # Estimate vehicle count passing sensor in current 5-min aggregation interval
        interval_hours = 5.0 / 60.0
        vehicle_count = int(round(demand_flow * interval_hours))

        # Density = vehicle count / road segment length
        density_vpk = round(vehicle_count / max(0.5, length_km), 2)

        # Congestion level classification
        speed_ratio = avg_speed / speed_limit
        if speed_ratio >= 0.70:
            congestion_level = "LOW"
        elif speed_ratio >= 0.45:
            congestion_level = "MEDIUM"
        elif speed_ratio >= 0.25:
            congestion_level = "HIGH"
        else:
            congestion_level = "SEVERE"

        event_id = f"EVT_TRF_{uuid.uuid4().hex[:16].upper()}"

        return {
            "event_id": event_id,
            "sensor_id": segment.get("sensor_id") or f"SNS_TRF_{segment['segment_id']}",
            "segment_id": segment["segment_id"],
            "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "vehicle_count": vehicle_count,
            "avg_speed_kmh": avg_speed,
            "congestion_level": congestion_level,
            "traffic_density_vpk": density_vpk,
            "source_type": "SIMULATED",
        }

    def generate_batch(
        self, sim_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Generates one reading for every configured road segment."""
        if not self.segments_cache:
            self._load_segments()
        t = sim_time or datetime.utcnow()
        return [self.generate_single_reading(seg, t) for seg in self.segments_cache]

    def simulate_historical_days(
        self, days: int = 2, interval_minutes: int = 60
    ) -> Generator[Dict[str, Any], None, None]:
        """Generates historical simulated readings across specified days."""
        if not self.segments_cache:
            self._load_segments()
        start_time = datetime.utcnow() - timedelta(days=days)
        end_time = datetime.utcnow()
        current_time = start_time

        while current_time <= end_time:
            for seg in self.segments_cache:
                yield self.generate_single_reading(seg, current_time)
            current_time += timedelta(minutes=interval_minutes)


traffic_simulator = TrafficSimulator()
