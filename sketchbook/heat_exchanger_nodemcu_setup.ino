#include <Wire.h>
#include <ESP8266WiFi.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <SPI.h>

// WiFi credentials
//const char* ssid = "Airtel_9309924679_5G";
//const char* password = "archsam801";

const char* ssid = "zerolosssystems";
const char* password = "123456789";

// Django API details
const char* host = "103.150.136.203";  // Your server IP
const int port = 8000;                 // Django server port
String writeApiKey = "dce5fdfb-308e-473c-85d5-012526b03784";  // Platex device write key
String deviceId = "2";                 // Platex device ID

// DS18B20 Sensor Setup
#define ONE_WIRE_BUS D4
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ADS1220 SPI Pins
#define ADS1220_CS_PIN   D8  // GPIO15
#define ADS1220_DRDY_PIN D2  // GPIO4 (Optional)
#define ADS1220_CLK_PIN  D5  // GPIO14
#define ADS1220_MISO_PIN D6  // GPIO12
#define ADS1220_MOSI_PIN D7  // GPIO13

// ADS1220 Register Definitions
#define ADS1220_CMD_RESET   0x06
#define ADS1220_CMD_START   0x08
#define ADS1220_CMD_RDATA   0x10
#define ADS1220_CMD_RREG    0x20
#define ADS1220_CMD_WREG    0x40

// ADS1220 Configuration Register Addresses
#define CONFIG_REG0  0x00
#define CONFIG_REG1  0x01
#define CONFIG_REG2  0x02
#define CONFIG_REG3  0x03

// DPT Configuration
float shuntResistance = 250.0; // 250Ω as per your wiring diagram
float pressureMin = 0.0; // Bar
float pressureMax = 10.0; // Bar

// New voltage ranges with 250Ω:
// 4mA = 0.004A × 250Ω = 1.00V
// 20mA = 0.020A × 250Ω = 5.00V
float voltageAt4mA = 1.00;  // 4mA × 250Ω
float voltageAt20mA = 5.00; // 20mA × 250Ω

// ========== UPDATED TDS CONFIGURATION ==========
float tdsVoltageAt0ppm = 0.0;       // Voltage at 0 ppm (pure water)
float tdsVoltageAt1000ppm = 2.048;  // Voltage at 1000 ppm (MAXIMUM based on 2.048V reference)
float tdsMin = 0.0;                 // Minimum TDS value in ppm
float tdsMax = 1000.0;              // Maximum TDS value in ppm
float tdsTemperatureCoefficient = 0.02; // 2% per °C for temperature compensation

// ADS1220 Channels
enum ADS1220_CHANNELS {
  CH_DPT = 0,    // AIN0-AIN1 differential (DPT sensor)
  CH_TDS = 1     // AIN2-AIN3 differential (TDS sensor)
};

// Sensor variables
bool dptConnected = false;
bool tdsConnected = false;
String dptLabel = "DPT1";
String tdsLabel = "TDS1";

// Temperature sensor variables
int numberOfTempSensors;
DeviceAddress tempSensorAddress[4];
String tempSensorLabels[4] = {"T1In", "T1Out", "T2In", "T2Out"};
bool tempSensorConnected[4] = {false, false, false, false};

// WiFi Management Variables
unsigned long lastDataSend = 0;
const unsigned long SEND_INTERVAL = 60000; // 60 seconds
bool wifiConnected = false;
int connectionAttempts = 0;
unsigned long lastWiFiCheck = 0;
const unsigned long WIFI_CHECK_INTERVAL = 10000; // Check WiFi every 10 seconds

// Function prototypes
void testDjangoConnection();
void sendToDjangoAPI(float t1, float t2, float t3, float t4, float pressure, float tdsValue);
void initializeADS1220();
void selectADS1220Channel(uint8_t channel);
void detectDPTSensor();
void detectTDSSensor();
float readDPTSensor();
float readTDSSensor(float temperature = 25.0);
String getTDSQuality(float tdsValue);
int32_t readADS1220();
void writeRegister(uint8_t reg, uint8_t value);
uint8_t readRegister(uint8_t reg);
void printAllReadings(float t1, float t2, float t3, float t4, float pressure, float tdsValue);
bool connectToWiFi();
void checkWiFiConnection();
void monitorConnection();
void calibrateTDSSensor();
void testTDSSensorWithSolutions();

void setup() {
  Serial.begin(115200);
  Serial.println("\n🚀 Starting Platex IoT Sensor System...");
  Serial.println("==========================================");
  
  // Enhanced WiFi configuration
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  
  // Set maximum WiFi power and N-only mode for better stability
  WiFi.setOutputPower(20.5);
  WiFi.setPhyMode(WIFI_PHY_MODE_11N);

  // Initialize SPI for ADS1220
  SPI.begin();
  SPI.setDataMode(SPI_MODE1);
  SPI.setBitOrder(MSBFIRST);
  SPI.setFrequency(1000000); // 1MHz SPI clock
  
  pinMode(ADS1220_CS_PIN, OUTPUT);
  digitalWrite(ADS1220_CS_PIN, HIGH);
  
  if (ADS1220_DRDY_PIN != -1) {
    pinMode(ADS1220_DRDY_PIN, INPUT);
  }

  // Initialize temperature sensors
  sensors.begin();
  numberOfTempSensors = sensors.getDeviceCount();
  Serial.print("🔍 Temperature sensors found: ");
  Serial.println(numberOfTempSensors);

  // Detect temperature sensors
  for (int i = 0; i < 4; i++) {
    if (sensors.getAddress(tempSensorAddress[i], i)) {
      tempSensorConnected[i] = true;
      Serial.print("✅ Temp Sensor ");
      Serial.print(i);
      Serial.print(" (");
      Serial.print(tempSensorLabels[i]);
      Serial.println("): Connected");
    } else {
      tempSensorConnected[i] = false;
      Serial.print("❌ Temp Sensor ");
      Serial.print(i);
      Serial.print(" (");
      Serial.print(tempSensorLabels[i]);
      Serial.println("): NOT CONNECTED");
    }
  }

  // Initialize ADS1220
  initializeADS1220();
  
  // Detect sensors
  detectDPTSensor();
  detectTDSSensor();

  // OPTIONAL: Run TDS calibration if needed
  // Uncomment this line to calibrate TDS sensor
  // calibrateTDSSensor();

  // Connect to WiFi with enhanced handling
  connectToWiFi();
  
  // Test Django connection
  testDjangoConnection();
  
  Serial.println("✅ System initialization complete!");
  Serial.println("==========================================\n");
}

bool connectToWiFi() {
  Serial.println("📡 Connecting to WiFi...");
  WiFi.disconnect();
  delay(1000);
  
  WiFi.begin(ssid, password);
  
  unsigned long startTime = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startTime < 30000) {
    delay(500);
    Serial.print(".");
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    connectionAttempts = 0;
    Serial.println("\n✅ WiFi Connected!");
    Serial.print("📶 IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("📶 RSSI: ");
    Serial.println(WiFi.RSSI());
    return true;
  } else {
    wifiConnected = false;
    connectionAttempts++;
    Serial.println("\n❌ WiFi Connection Failed!");
    Serial.println("💡 Check: Router distance, power supply, credentials");
    return false;
  }
}

void checkWiFiConnection() {
  if (WiFi.status() != WL_CONNECTED) {
    wifiConnected = false;
    Serial.println("⚠️ WiFi Disconnected! Attempting reconnect...");
    
    if (connectionAttempts < 3) {
      connectToWiFi();
    } else {
      // After 3 failures, wait longer before retry
      Serial.println("💤 Waiting 2 minutes before retry...");
      delay(120000);
      connectionAttempts = 0;
      connectToWiFi();
    }
  }
}

void monitorConnection() {
  static unsigned long lastMonitor = 0;
  if (millis() - lastMonitor > 30000) { // Every 30 seconds
    lastMonitor = millis();
    
    Serial.println("📊 Connection Monitor:");
    Serial.print("  WiFi Status: ");
    Serial.println(WiFi.status() == WL_CONNECTED ? "Connected" : "Disconnected");
    Serial.print("  RSSI: ");
    Serial.println(WiFi.RSSI());
    Serial.print("  Free Heap: ");
    Serial.println(ESP.getFreeHeap());
    Serial.print("  Connection Attempts: ");
    Serial.println(connectionAttempts);
    Serial.println("-------------------");
  }
}

void testDjangoConnection() {
  if (!wifiConnected) return;
  
  Serial.println("🧪 Testing Django connection...");
  
  WiFiClient client;
  if (client.connect(host, port)) {
    Serial.println("✅ Django server is reachable");
    
    // Send test request with CORRECT authentication
    String testRequest = "GET /api/ui/dashboard/ HTTP/1.1\r\n";
    testRequest += "Host: " + String(host) + "\r\n";
    testRequest += "Authorization: " + writeApiKey + "\r\n";  // ← NO "Token" prefix!
    testRequest += "Connection: close\r\n\r\n";
    
    client.print(testRequest);
    
    // Read response
    unsigned long timeout = millis();
    while (client.connected() && millis() - timeout < 5000) {
      if (client.available()) {
        String line = client.readStringUntil('\n');
        if (line.startsWith("HTTP")) {
          Serial.println("📡 Server response: " + line);
          break;
        }
      }
    }
    client.stop();
  } else {
    Serial.println("❌ Django server is NOT reachable");
  }
}

void loop() {
  unsigned long currentTime = millis();
  
  // Check WiFi connection regularly
  if (currentTime - lastWiFiCheck >= WIFI_CHECK_INTERVAL) {
    checkWiFiConnection();
    lastWiFiCheck = currentTime;
  }
  
  // Monitor connection status
  monitorConnection();
  
  // Send data only at the specified interval AND when WiFi is connected
  if (wifiConnected && (currentTime - lastDataSend >= SEND_INTERVAL)) {
    
    // Read sensors
    sensors.requestTemperatures();
    float t1 = tempSensorConnected[0] ? sensors.getTempCByIndex(0) : -999.0;
    float t2 = tempSensorConnected[1] ? sensors.getTempCByIndex(1) : -999.0;
    float t3 = tempSensorConnected[2] ? sensors.getTempCByIndex(2) : -999.0;
    float t4 = tempSensorConnected[3] ? sensors.getTempCByIndex(3) : -999.0;
    
    // Read DPT sensor
    float pressure = readDPTSensor();
    
    // Read TDS sensor with temperature compensation
    // Using T1Out (t2) as water temperature for compensation
    float waterTemperature = 25.0; // Default value
    if (tempSensorConnected[1] && t2 > -900.0 && t2 <= 100.0) { // Check if T1Out is connected and valid
      waterTemperature = t2;
      Serial.println("🌡️ Using T1Out temperature for TDS compensation: " + String(waterTemperature, 1) + "°C");
    } else {
      Serial.println("🌡️ Using default temperature (25°C) for TDS compensation");
    }
    
    float tdsValue = readTDSSensor(waterTemperature);
    
    // Print readings
    printAllReadings(t1, t2, t3, t4, pressure, tdsValue);
    
    // Send to API
    sendToDjangoAPI(t1, t2, t3, t4, pressure, tdsValue);
    
    lastDataSend = currentTime;
    Serial.println("⏰ Next send in 60 seconds...");
  }
  
  // Small delay to prevent watchdog reset
  delay(100);
}

void initializeADS1220() {
  digitalWrite(ADS1220_CS_PIN, LOW);
  SPI.transfer(ADS1220_CMD_RESET); // Reset ADS1220
  delay(10);
  
  // Configure default channel (DPT sensor: AIN0-AIN1 differential)
  // Register 0: AIN0-AIN1, PGA bypass, Gain=1
  writeRegister(CONFIG_REG0, 0x00); 
  // Register 1: DR=20 SPS, Normal mode, Continuous conversion
  writeRegister(CONFIG_REG1, 0x04);
  // Register 2: Internal 2.048V reference, 50/60Hz rejection, Pulse conversion
  writeRegister(CONFIG_REG2, 0x10);
  // Register 3: Disable IDAC currents
  writeRegister(CONFIG_REG3, 0x00);
  
  digitalWrite(ADS1220_CS_PIN, HIGH);
  delay(100);
}

void selectADS1220Channel(uint8_t channel) {
  digitalWrite(ADS1220_CS_PIN, LOW);
  
  uint8_t muxConfig;
  
  if (channel == CH_DPT) {
    // AIN0-AIN1 differential for DPT
    muxConfig = 0x00; // AINP=AIN0, AINN=AIN1
  } else if (channel == CH_TDS) {
    // AIN2-AIN3 differential for TDS
    muxConfig = 0x30; // AINP=AIN2, AINN=AIN3
  } else {
    muxConfig = 0x00; // Default to DPT
  }
  
  // Read current config and update only MUX bits
  uint8_t currentConfig = readRegister(CONFIG_REG0);
  currentConfig = (currentConfig & 0x0F) | muxConfig; // Keep lower 4 bits, update upper 4 bits
  
  writeRegister(CONFIG_REG0, currentConfig);
  
  digitalWrite(ADS1220_CS_PIN, HIGH);
  delay(10); // Small delay for configuration to take effect
}

void detectDPTSensor() {
  Serial.println("🔧 Detecting DPT sensor...");
  Serial.println("📊 Using 250Ω shunt resistor");
  Serial.println("⚡ Expected: 1.00V (4mA) to 5.00V (20mA)");
  
  // Select DPT channel
  selectADS1220Channel(CH_DPT);
  delay(100);
  
  float pressure = readDPTSensor();
  
  if (pressure >= -1.0 && pressure <= 12.0) { // Reasonable pressure range
    dptConnected = true;
    Serial.println("✅ " + dptLabel + ": CONNECTED");
    Serial.println("📊 Current reading: " + String(pressure, 2) + " bar");
  } else {
    dptConnected = false;
    Serial.println("❌ " + dptLabel + ": NOT DETECTED");
    Serial.println("🔧 Wiring Guide:");
    Serial.println("   DPT Pin2 → 250Ω → GND");
    Serial.println("   DPT Pin2 → AIN0");
    Serial.println("   GND side of 250Ω → AIN1");
  }
}

void detectTDSSensor() {
  Serial.println("🔧 Detecting TDS sensor...");
  Serial.println("📊 Specifications: 0-2.048V output (0-1000 ppm)");
  Serial.println("⚡ Reference Voltage: 2.048V (ADS1220 internal)");
  Serial.println("💡 Note: Using accurate linear conversion");
  
  // Select TDS channel
  selectADS1220Channel(CH_TDS);
  delay(100);
  
  float tdsValue = readTDSSensor(25.0);
  
  if (tdsValue >= 0.0 && tdsValue <= 1100.0) { // Reasonable TDS range (with margin)
    tdsConnected = true;
    Serial.println("✅ " + tdsLabel + ": CONNECTED");
    Serial.println("📊 Current reading: " + String(tdsValue, 1) + " ppm");
    Serial.println("📊 Water Quality: " + getTDSQuality(tdsValue));
    Serial.println("⚠️  Note: Accuracy ±10% at 25°C");
  } else if (tdsValue > -9900.0 && tdsValue < 0) {
    tdsConnected = true; // Possibly negative voltage (ground offset)
    Serial.println("⚠️ " + tdsLabel + ": DETECTED (possible ground offset)");
    Serial.println("📊 Current reading: " + String(tdsValue, 1) + " ppm");
  } else {
    tdsConnected = false;
    Serial.println("❌ " + tdsLabel + ": NOT DETECTED");
    Serial.println("🔧 Wiring Guide:");
    Serial.println("   TDS VOUT → AIN2 (ADS1220)");
    Serial.println("   TDS GND → AIN3 (ADS1220)");
    Serial.println("   TDS VCC → 3.3V (ESP32)");
  }
}

float readDPTSensor() {
  // Select DPT channel
  selectADS1220Channel(CH_DPT);
  delay(50); // Allow channel switching
  
  int32_t adcValue = readADS1220();
  
  if (adcValue == 0x7FFFFF || adcValue == 0x800000) {
    return -9999.0; // Invalid reading
  }
  
  // Convert ADC value to voltage (24-bit, 2.048V reference)
  float voltage = (adcValue / 8388607.0) * 2.048;
  
  // Debug information
  Serial.print("📊 DPT ADC: " + String(adcValue) + " | ");
  Serial.print("⚡ Voltage: " + String(voltage, 4) + "V | ");
  
  // Calculate current through 250Ω shunt
  float current = voltage / shuntResistance;
  Serial.print("🔌 Current: " + String(current * 1000, 1) + "mA | ");
  
  // Convert current to pressure (4-20mA = 0-10 bar)
  if (current >= 0.003 && current <= 0.021) { // 3-21mA range with margin
    // More accurate calculation using voltage ranges
    float pressure = ((voltage - voltageAt4mA) / (voltageAt20mA - voltageAt4mA)) * (pressureMax - pressureMin);
    
    // Constrain to valid range
    pressure = constrain(pressure, pressureMin, pressureMax);
    
    // Check if pressure is reasonable
    if (pressure >= -1.0 && pressure <= 12.0) {
      Serial.println("📏 Pressure: " + String(pressure, 2) + " bar");
      return pressure;
    }
  }
  
  Serial.println("❌ INVALID READING");
  return -9999.0; // Invalid reading
}

// ========== CORRECTED TDS READING FUNCTION ==========
float readTDSSensor(float temperature) {
  // Select TDS channel
  selectADS1220Channel(CH_TDS);
  delay(50);
  
  // Take multiple readings
  int32_t adcValue = 0;
  int validReadings = 0;
  
  for (int i = 0; i < 5; i++) {
    int32_t reading = readADS1220();
    
    if (reading != 0x7FFFFF && reading != 0x800000 && reading != 0) {
      adcValue += abs(reading);
      validReadings++;
    }
    delay(10);
  }
  
  if (validReadings == 0) {
    Serial.println("❌ TDS: No valid ADC readings");
    return -9999.0;
  }
  
  // Calculate average ADC value
  adcValue = adcValue / validReadings;
  
  // Convert ADC value to voltage (24-bit, 2.048V reference)
  float voltage = (adcValue / 8388607.0) * 2.048;
  
  // Debug information
  Serial.print("📊 TDS ADC: " + String(adcValue) + " | ");
  Serial.print("⚡ Voltage: " + String(voltage, 4) + "V | ");
  
  // CORRECTED CALCULATION BASED ON YOUR ACTUAL DATA
  // Using linear interpolation:
  // Point 1: 0.0243V = 0 ppm (AIR)
  // Point 2: 2.3859V = 873 ppm (SALT WATER)
  
  // Calculate slope (ppm per volt)
  float voltageRange = 2.3859 - 0.0243;
  float ppmRange = 873.0 - 0.0;
  float ppmPerVolt = ppmRange / voltageRange;
  
  // Calculate ppm
  float tdsValue = (voltage - 0.0243) * ppmPerVolt;
  
  // Ensure non-negative
  if (tdsValue < 0) tdsValue = 0;
  
  // Debug
  Serial.print("📈 Raw TDS: " + String(tdsValue, 1) + " ppm | ");
  
  // Apply temperature compensation if valid
  if (temperature >= 0.0 && temperature <= 100.0) {
    // Standard compensation: 2% per °C from reference temperature (25°C)
    float compensationFactor = 1.0 + tdsTemperatureCoefficient * (25.0 - temperature);
    tdsValue = tdsValue * compensationFactor;
    
    Serial.print("🌡️ Compensated @ " + String(temperature, 1) + "°C: ");
  }
  
  // Constrain to reasonable range
  tdsValue = constrain(tdsValue, 0.0, 1200.0);
  
  Serial.println("💧 Final TDS: " + String(tdsValue, 1) + " ppm");
  
  return tdsValue;
}
  else if (voltage < 0.0 && voltage > -0.1) {
    // Slight negative offset (common in differential measurements)
    Serial.print("⚠️  Small negative offset detected (");
    Serial.print(voltage, 4);
    Serial.println("V), setting to 0V");
    
    // Treat as 0V = 0 ppm
    Serial.println("💧 TDS: 0.0 ppm (treated as pure water)");
    return 0.0;
  }
  else if (voltage > 2.048 && voltage < 2.5) {
    // Voltage slightly above reference
    Serial.print("⚠️  Voltage exceeds 2.048V reference (");
    Serial.print(voltage, 3);
    Serial.println("V)");
    
    // Conservative extrapolation using sensor max of 2.3V
    float tdsValue = (voltage / 2.3) * 1000.0;
    tdsValue = constrain(tdsValue, 0.0, 1200.0);
    
    Serial.println("💧 Extrapolated TDS: " + String(tdsValue, 1) + " ppm (reduced accuracy)");
    return tdsValue;
  }
  else {
    Serial.println("❌ INVALID: Voltage out of range (0-2.048V expected, got " + String(voltage, 3) + "V)");
    return -9999.0;
  }
}

String getTDSQuality(float tdsValue) {
  if (tdsValue < 50) return "Excellent (Pure)";
  else if (tdsValue < 150) return "Good";
  else if (tdsValue < 250) return "Fair";
  else if (tdsValue < 350) return "Poor";
  else if (tdsValue < 500) return "Very Poor";
  else return "Unacceptable";
}

int32_t readADS1220() {
  digitalWrite(ADS1220_CS_PIN, LOW);
  
  // Start conversion
  SPI.transfer(ADS1220_CMD_START);
  
  // Wait for DRDY pin if connected, otherwise delay
  if (ADS1220_DRDY_PIN != -1) {
    while (digitalRead(ADS1220_DRDY_PIN) == HIGH) {
      delayMicroseconds(10);
    }
  } else {
    delay(100); // Wait for conversion (20 SPS = 50ms per conversion)
  }
  
  // Read conversion result
  SPI.transfer(ADS1220_CMD_RDATA);
  delayMicroseconds(10);
  
  uint8_t b1 = SPI.transfer(0xFF);
  uint8_t b2 = SPI.transfer(0xFF);
  uint8_t b3 = SPI.transfer(0xFF);
  
  digitalWrite(ADS1220_CS_PIN, HIGH);
  
  int32_t value = (b1 << 16) | (b2 << 8) | b3;
  
  // Convert from 24-bit 2's complement to 32-bit
  if (value & 0x800000) {
    value |= 0xFF000000;
  }
  
  return value;
}

void writeRegister(uint8_t reg, uint8_t value) {
  digitalWrite(ADS1220_CS_PIN, LOW);
  SPI.transfer(ADS1220_CMD_WREG | (reg << 2));
  SPI.transfer(value);
  digitalWrite(ADS1220_CS_PIN, HIGH);
}

uint8_t readRegister(uint8_t reg) {
  digitalWrite(ADS1220_CS_PIN, LOW);
  SPI.transfer(ADS1220_CMD_RREG | (reg << 2));
  uint8_t value = SPI.transfer(0xFF);
  digitalWrite(ADS1220_CS_PIN, HIGH);
  return value;
}

void printAllReadings(float t1, float t2, float t3, float t4, float pressure, float tdsValue) {
  Serial.println("📊 === SENSOR READINGS ===");
  Serial.println("⏰ Timestamp: " + String(millis() / 1000) + " seconds");
  
  // Temperature readings
  Serial.println("🌡️ Temperature Sensors:");
  Serial.print("  " + tempSensorLabels[0] + ": ");
  Serial.println(tempSensorConnected[0] ? String(t1, 1) + "°C" : "❌ NOT CONNECTED");
  Serial.print("  " + tempSensorLabels[1] + ": ");
  Serial.println(tempSensorConnected[1] ? String(t2, 1) + "°C" : "❌ NOT CONNECTED");
  Serial.print("  " + tempSensorLabels[2] + ": ");
  Serial.println(tempSensorConnected[2] ? String(t3, 1) + "°C" : "❌ NOT CONNECTED");
  Serial.print("  " + tempSensorLabels[3] + ": ");
  Serial.println(tempSensorConnected[3] ? String(t4, 1) + "°C" : "❌ NOT CONNECTED");
  
  // DPT reading
  Serial.println("📏 DPT Sensor:");
  Serial.print("  " + dptLabel + ": ");
  if (dptConnected && pressure > -9990.0) {
    Serial.println(String(pressure, 2) + " bar");
  } else {
    Serial.println("❌ NOT DETECTED");
  }
  
  // TDS reading
  Serial.println("💧 TDS Sensor:");
  Serial.print("  " + tdsLabel + ": ");
  if (tdsConnected && tdsValue > -9990.0) {
    Serial.print(String(tdsValue, 1) + " ppm");
    Serial.print(" (" + getTDSQuality(tdsValue) + ")");
    Serial.println();
  } else {
    Serial.println("❌ NOT DETECTED");
  }
  
  Serial.println("📊 ======================");
}

void sendToDjangoAPI(float t1, float t2, float t3, float t4, float pressure, float tdsValue) {
  if (!wifiConnected) return;
  
  Serial.println("🔌 === SENDING DATA TO DJANGO ===");
  
  WiFiClient client;
  client.setTimeout(15000);
  
  Serial.print("🌐 Connecting to ");
  Serial.print(host);
  Serial.print(":");
  Serial.print(port);
  Serial.println("...");
  
  if (!client.connect(host, port)) {
    Serial.println("❌ Connection failed to Django server");
    wifiConnected = false; // Mark as disconnected
    return;
  }
  
  Serial.println("✅ Connected to Django server!");
  
  // Prepare JSON data
  String jsonData = "{";
  jsonData += "\"t1_in\":" + String(t1,2) + ",";
  jsonData += "\"t1_out\":" + String(t2,2) + ",";
  jsonData += "\"t2_in\":" + String(t3,2) + ",";
  jsonData += "\"t2_out\":" + String(t4,2) + ",";
  jsonData += "\"dpt1\":" + (dptConnected && pressure > -9990.0 ? String(pressure,2) : "null") + ",";
  jsonData += "\"tds1\":" + (tdsConnected && tdsValue > -9990.0 ? String(tdsValue,1) : "null");
  jsonData += "}";
  
  // CORRECT: Use ONLY the API key without "Token" prefix
  String request = "POST /api/write_data/2/ HTTP/1.1\r\n";
  request += "Host: " + String(host) + ":" + String(port) + "\r\n";
  request += "Authorization: " + writeApiKey + "\r\n";  // ← NO "Token" prefix!
  request += "Content-Type: application/json\r\n";
  request += "Content-Length: " + String(jsonData.length()) + "\r\n";
  request += "Connection: close\r\n";
  request += "\r\n";
  request += jsonData;
  
  Serial.println("📤 Sending sensor data...");
  Serial.println("📦 JSON: " + jsonData);
  
  client.print(request);
  Serial.println("✅ Request sent to server!");
  
  // Wait for response
  unsigned long startTime = millis();
  bool gotResponse = false;
  String responseBody = "";
  
  Serial.println("⏳ Waiting for server response...");
  
  while (client.connected() && millis() - startTime < 15000) {
    while (client.available()) {
      String line = client.readStringUntil('\n');
      line.trim();
      
      if (line.length() > 0) {
        if (!gotResponse) {
          Serial.println("📡 === SERVER RESPONSE ===");
          gotResponse = true;
        }
        Serial.println("<< " + line);
        responseBody += line + "\n";
        
        // Check for success
        if (line.startsWith("HTTP/1.1 20")) {
          Serial.println("🎉 SUCCESS: Server accepted the data!");
        }
      }
    }
    delay(50);
  }
  
  if (gotResponse) {
    // Check if we got the expected response format
    if (responseBody.indexOf("\"sensor_label\"") > 0) {
      Serial.println("✅ DATA SAVED: Sensor records created successfully!");
    } else {
      Serial.println("⚠️  Response received but format unexpected");
    }
  } else {
    Serial.println("❌ No response received from server");
    Serial.println("💡 This might be a network issue - data may still be saved");
  }
  
  client.stop();
  Serial.println("🔌 Connection closed");
  Serial.println("=================================");
}

// ========== TDS CALIBRATION FUNCTION ==========
void calibrateTDSSensor() {
  Serial.println("🔧 === TDS SENSOR CALIBRATION ===");
  Serial.println("NOTE: This will calibrate for 0-1000 ppm range");
  Serial.println("1. Clean sensor with distilled water");
  Serial.println("2. Place sensor in DISTILLED WATER (0 ppm)");
  Serial.println("3. Wait 30 seconds for stabilization");
  Serial.println("4. Press any key to continue...");
  
  while (!Serial.available()) {
    delay(100);
  }
  Serial.read(); // Clear buffer
  
  // Read zero point
  selectADS1220Channel(CH_TDS);
  delay(2000); // Wait for stabilization
  
  long totalAdc = 0;
  int samples = 10;
  
  Serial.print("🔬 Measuring zero point");
  for (int i = 0; i < samples; i++) {
    int32_t adcValue = readADS1220();
    if (adcValue != 0x7FFFFF && adcValue != 0x800000) {
      totalAdc += abs(adcValue);
      Serial.print(".");
    }
    delay(500);
  }
  
  float avgAdc = totalAdc / (float)samples;
  tdsVoltageAt0ppm = (avgAdc / 8388607.0) * 2.048;
  
  Serial.println("\n✅ Zero point calibrated:");
  Serial.println("   ADC: " + String(avgAdc));
  Serial.println("   Voltage: " + String(tdsVoltageAt0ppm, 4) + "V");
  
  // Calibrate at known TDS value
  Serial.println("\n5. Place sensor in 1000 ppm calibration solution");
  Serial.println("6. Wait 60 seconds for stabilization");
  Serial.println("7. Press any key to continue...");
  
  while (!Serial.available()) {
    delay(100);
  }
  Serial.read(); // Clear buffer
  
  delay(3000); // Wait for stabilization
  
  totalAdc = 0;
  Serial.print("🔬 Measuring 1000 ppm point");
  for (int i = 0; i < samples; i++) {
    int32_t adcValue = readADS1220();
    if (adcValue != 0x7FFFFF && adcValue != 0x800000) {
      totalAdc += abs(adcValue);
      Serial.print(".");
    }
    delay(500);
  }
  
  avgAdc = totalAdc / (float)samples;
  tdsVoltageAt1000ppm = (avgAdc / 8388607.0) * 2.048;
  
  Serial.println("\n✅ 1000 ppm point calibrated:");
  Serial.println("   ADC: " + String(avgAdc));
  Serial.println("   Voltage: " + String(tdsVoltageAt1000ppm, 4) + "V");
  
  // Calculate actual range
  float actualRange = tdsVoltageAt1000ppm - tdsVoltageAt0ppm;
  Serial.println("📐 Actual sensor range: " + String(actualRange, 4) + "V");
  
  // Adjust max TDS if range is different
  if (actualRange < 1.0) {
    Serial.println("⚠️  Warning: Small voltage range detected");
    Serial.println("   Consider using a different TDS range");
  }
  
  Serial.println("✅ Calibration complete!");
  Serial.println("   Use these values in your code:");
  Serial.println("   tdsVoltageAt0ppm = " + String(tdsVoltageAt0ppm, 4) + ";");
  Serial.println("   tdsVoltageAt1000ppm = " + String(tdsVoltageAt1000ppm, 4) + ";");
  Serial.println("=================================");
}

// ========== TDS SENSOR TEST ==========
void testTDSSensorWithSolutions() {
  Serial.println("🧪 === TDS SENSOR TEST ===");
  Serial.println("Testing with different water samples:");
  
  // Test with different solutions (simulated or real)
  float testTemperatures[] = {20.0, 25.0, 30.0, 35.0};
  int numTests = sizeof(testTemperatures) / sizeof(testTemperatures[0]);
  
  for (int i = 0; i < numTests; i++) {
    Serial.println("\n🌡️ Test at " + String(testTemperatures[i], 1) + "°C:");
    
    // Simulate different water qualities
    // These are example voltages - actual values depend on your sensor
    float testVoltages[] = {0.1, 0.5, 1.0, 1.5, 2.0};
    
    for (int j = 0; j < 5; j++) {
      float voltage = testVoltages[j];
      float tdsValue = (voltage / 2.048) * 1000.0;
      
      // Apply temperature compensation
      float compensationFactor = 1.0 + tdsTemperatureCoefficient * (25.0 - testTemperatures[i]);
      tdsValue = tdsValue * compensationFactor;
      
      Serial.print("  " + String(voltage, 2) + "V → ");
      Serial.print(String(tdsValue, 0) + " ppm (");
      Serial.print(getTDSQuality(tdsValue));
      Serial.println(")");
    }
  }
  
  Serial.println("✅ Test complete!");
  Serial.println("=================================");
}
