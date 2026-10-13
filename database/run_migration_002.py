"""
Runs Migration 002: IoT Telemetry Mode Separation & Provenance Isolation.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.connection import get_db_cursor

def run_migration():
    print("Applying Migration 002: IoT Telemetry Mode Separation...")
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("DESCRIBE iot_devices")
        cols = [r['Field'] for r in cursor.fetchall()]
        
        if 'device_type' not in cols:
            cursor.execute("ALTER TABLE iot_devices ADD COLUMN device_type VARCHAR(20) NOT NULL DEFAULT 'PHYSICAL'")
            print("  + Added column 'device_type' to iot_devices")
        else:
            print("  * Column 'device_type' already exists")

        if 'connected_sensors' not in cols:
            cursor.execute("ALTER TABLE iot_devices ADD COLUMN connected_sensors VARCHAR(255) DEFAULT 'DHT11,MQ-135,LDR'")
            print("  + Added column 'connected_sensors' to iot_devices")
        else:
            print("  * Column 'connected_sensors' already exists")

        if 'port_assignment' not in cols:
            cursor.execute("ALTER TABLE iot_devices ADD COLUMN port_assignment VARCHAR(32) DEFAULT NULL")
            print("  + Added column 'port_assignment' to iot_devices")
        else:
            print("  * Column 'port_assignment' already exists")

        # Update existing devices to VIRTUAL
        cursor.execute("""
            UPDATE iot_devices 
            SET device_type = 'VIRTUAL', 
                device_name = 'Nagpur Zero Mile Edge Unit (Simulated)',
                connected_sensors = 'DHT11,MQ-135,LDR'
            WHERE device_id = 'ARDUINO_UNO_NAG_01'
        """)
        cursor.execute("""
            UPDATE iot_devices 
            SET device_type = 'VIRTUAL', 
                device_name = 'UrbanPulse Edge Unit 1 (Virtual Prototype)',
                connected_sensors = 'DHT11,MQ-135,LDR'
            WHERE device_id = 'ARDUINO_UNO_01'
        """)
        print("  + Set existing prototype nodes to device_type='VIRTUAL'")

        # Quarantine unverified legacy test records
        cursor.execute("""
            UPDATE iot_sensor_readings 
            SET source_type = 'UNVERIFIED_LEGACY' 
            WHERE id IN (1, 2, 3, 4, 5) AND source_type = 'REAL_HARDWARE'
        """)
        print(f"  + Quarantined legacy records: {cursor.rowcount} updated to 'UNVERIFIED_LEGACY'")

    print("Migration 002 applied successfully!")

if __name__ == "__main__":
    run_migration()
