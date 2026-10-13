/*
 * UrbanPulse — Smart City Edge IoT Microcontroller Firmware
 * Target Hardware: Arduino Uno R3 (ATmega328P)
 * Baud Rate: 9600 bps
 *
 * Description:
 * Reads physical analog/digital environmental sensors, performs local thresholding,
 * controls status indication LED (Pin 13), and emits structured serial packets over USB.
 *
 * Configurable Sensor Modes:
 *   SOUND_SENSOR_TEST_MODE = 1 -> Temporary Sound Sensor Hardware Experiment (Pin A0)
 *   SOUND_SENSOR_TEST_MODE = 0 -> Standard Municipal Environmental Sensing (SENSOR_MODE 1-4)
 *     1 = SIMULATED_SINE (Hardware verification without attached sensor module)
 *     2 = DHT11 (Temperature & Relative Humidity)
 *     3 = MQ135 (Raw Analog Gas / Air Quality ADC reading)
 *     4 = LDR (Light-Dependent Resistor ambient lux ADC reading)
 */

// ==========================================
// CONFIGURATION FLAGS
// ==========================================
// Set SOUND_SENSOR_TEST_MODE to 1 for sound sensor hardware testing.
// Set to 0 to return to standard multi-sensor behavior.
#define SOUND_SENSOR_TEST_MODE 1

#define SENSOR_MODE 1           // 1: Built-in Simulation, 2: DHT11, 3: MQ135, 4: LDR
#define DEVICE_ID "ARDUINO_SOUND_01"
#define SAMPLING_INTERVAL_MS 1000   // 1 second (1000ms) interval for sound responsiveness
#define STATUS_LED_PIN 13          // On-board LED for transmit heartbeat

// Pin assignments for physical sensors
#define DHT_PIN 2               // Digital Pin for DHT11 data line
#define MQ135_PIN A0            // Analog Pin for MQ-135 Gas Sensor
#define LDR_PIN A1              // Analog Pin for LDR Light Sensor

// Sound Sensor pin assignment (Configurable)
// Connect the Analog Output (AO / OUT) of your sound sensor module to Analog Pin A0.
#define SOUND_ANALOG_PIN A0     // Analog Pin for Sound Sensor

// Error handling thresholds
#define SOUND_MAX_ADC 1023
#define MQ135_MAX_ADC 1023
#define LDR_MAX_ADC 1023

unsigned long lastSampleTime = 0;
float simCounter = 0.0;

void setup() {
  pinMode(STATUS_LED_PIN, OUTPUT);
  Serial.begin(9600);
  while (!Serial) {
    ; // Wait for serial port connection (native USB compatibility)
  }

  // Signal device initialization
  digitalWrite(STATUS_LED_PIN, HIGH);
  delay(500);
  digitalWrite(STATUS_LED_PIN, LOW);

  // Send system boot banner
  #if SOUND_SENSOR_TEST_MODE == 1
    Serial.println(F("# UrbanPulse Edge Firmware v1.3.0 Initialized [SOUND_SENSOR_TEST_MODE Active - P2P Sampling]"));
    Serial.print(F("# Device: ")); Serial.println(DEVICE_ID);
    Serial.print(F("# Sound Input Pin: A")); Serial.println(SOUND_ANALOG_PIN - A0);
    Serial.println(F("# Sampling Window: 50ms | Transmit Interval: 1000ms"));
  #else
    Serial.println(F("# UrbanPulse Edge Firmware v1.3.0 Initialized [Standard Mode]"));
    Serial.print(F("# Device: ")); Serial.println(DEVICE_ID);
    Serial.print(F("# Sensor Mode: ")); Serial.println(SENSOR_MODE);
  #endif
}

void loop() {
  // 1. Host Handshake & Hardware Identification Protocol (Immediate response)
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "PING" || cmd == "IDENT" || cmd == "UP_HANDSHAKE") {
      #if SOUND_SENSOR_TEST_MODE == 1
        Serial.print(F("UP_IDENT,"));
        Serial.print(DEVICE_ID);
        Serial.println(F(",ARDUINO_UNO_R3,v1.3.0,SOUND_P2P_A0"));
      #else
        Serial.print(F("UP_IDENT,"));
        Serial.print(DEVICE_ID);
        Serial.print(F(",ARDUINO_UNO_R3,v1.3.0,MODE_"));
        Serial.println(SENSOR_MODE);
      #endif
    }
  }

  unsigned long currentMillis = millis();
  unsigned long interval = (SOUND_SENSOR_TEST_MODE == 1) ? 1000 : SAMPLING_INTERVAL_MS;

  if (currentMillis - lastSampleTime >= interval) {
    lastSampleTime = currentMillis;

    // Flash status LED during transmission
    digitalWrite(STATUS_LED_PIN, HIGH);

    #if SOUND_SENSOR_TEST_MODE == 1
      // Windowed Peak-to-Peak Sampling (50ms window)
      // Audio is an alternating AC voltage waveform oscillating around a DC baseline.
      // Sampling repeatedly across a 50ms window captures min and max ADC peaks,
      // computing peak-to-peak amplitude (max - min) that reliably detects speech,
      // claps, and acoustic vibration spikes without missing transient waveforms.
      const unsigned int sampleWindow = 50; // 50ms measurement window
      unsigned long windowStart = millis();
      int minADC = 1023;
      int maxADC = 0;

      while (millis() - windowStart < sampleWindow) {
        int sample = analogRead(SOUND_ANALOG_PIN);
        if (sample >= 0 && sample <= SOUND_MAX_ADC) {
          if (sample > maxADC) maxADC = sample;
          if (sample < minADC) minADC = sample;
        }
      }

      if (maxADC < minADC) {
        sendPacket("SOUND_P2P", 0.0, "ADC", "ERR_READ_FAILED");
      } else {
        int peakToPeak = maxADC - minADC;
        if (peakToPeak < 0) peakToPeak = 0;
        if (peakToPeak > 1023) peakToPeak = 1023;
        sendPacket("SOUND_P2P", (float)peakToPeak, "ADC", "OK");
      }

    #else
      #if SENSOR_MODE == 1
        // Mode 1: Built-in synthetic sine wave (for testing without external components)
        simCounter += 0.15;
        float testTemp = 25.0 + 5.0 * sin(simCounter);
        float testHum = 50.0 + 10.0 * cos(simCounter);
        
        sendPacket("DHT11_TEMP", testTemp, "C", "OK");
        sendPacket("DHT11_HUMIDITY", testHum, "PCT", "OK");

      #elif SENSOR_MODE == 2
        // Mode 2: DHT11 Sensor
        float t = 28.0; // Placeholder until DHT library is loaded in Arduino IDE
        float h = 60.0;
        if (isnan(t) || isnan(h)) {
          sendPacket("DHT11", 0.0, "ERR", "ERR_SENSOR_FAILED");
        } else {
          sendPacket("DHT11_TEMP", t, "C", "OK");
          sendPacket("DHT11_HUMIDITY", h, "PCT", "OK");
        }

      #elif SENSOR_MODE == 3
        // Mode 3: MQ-135 Gas Sensor (Raw ADC Reading)
        int rawGas = analogRead(MQ135_PIN);
        if (rawGas < 0 || rawGas > MQ135_MAX_ADC) {
          sendPacket("MQ135_RAW", 0.0, "ADC", "ERR_OUT_OF_BOUNDS");
        } else {
          sendPacket("MQ135_RAW", (float)rawGas, "ADC", "OK");
        }

      #elif SENSOR_MODE == 4
        // Mode 4: LDR Light Sensor
        int rawLight = analogRead(LDR_PIN);
        if (rawLight < 0 || rawLight > LDR_MAX_ADC) {
          sendPacket("LDR_LIGHT", 0.0, "ADC", "ERR_OUT_OF_BOUNDS");
        } else {
          sendPacket("LDR_LIGHT", (float)rawLight, "ADC", "OK");
        }
      #endif
    #endif

    digitalWrite(STATUS_LED_PIN, LOW);
  }
}

/**
 * Transmits a structured CSV packet across USB Serial:
 * Format: UP_IOT,DEVICE_ID,SENSOR_TYPE,VALUE,UNIT,STATUS
 */
void sendPacket(const char* sensorType, float val, const char* unit, const char* status) {
  Serial.print(F("UP_IOT,"));
  Serial.print(DEVICE_ID);
  Serial.print(F(","));
  Serial.print(sensorType);
  Serial.print(F(","));
  Serial.print(val, 2);
  Serial.print(F(","));
  Serial.print(unit);
  Serial.print(F(","));
  Serial.println(status);
}
