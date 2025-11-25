#include <Wire.h>
#include <ESP8266WiFi.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <SPI.h>

// WiFi credentials
const char* ssid = "Airtel_9309924679_5G";
const char* password = "archsam801";

//const char* ssid = "zerolosssystems";
//const char* password = "123456789";

// Django API details
const char* host = "150.241.245.67";  // Your server IP
const int port = 8000;                 // Django server port
String writeApiKey = "b97fa24b-5ee1-4761-a24f-9b6d78346e60";  // Platex device write key
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

// DPT Configuration for ONE sensor with 120Ω resistor
float shuntResistance = 120.0; // Changed from 125Ω to 120Ω
float pressureMin = 0.0; // Bar
float pressureMax = 10.0; // Bar

// New voltage ranges with 120Ω:
// 4mA = 0.004A × 120Ω = 0.48V
// 20mA = 0.020A × 120Ω = 2.40V
float voltageAt4mA = 0.48;  // 4mA × 120Ω
float voltageAt20mA = 2.40; // 20mA × 120Ω

// DPT calibration values
int32_t dptAdcMin = 0;  // ADC value at 4mA
int32_t dptAdcMax = 0;  // ADC value at 20mA
bool dptConnected = false;
String dptLabel = "DPT1";

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
void sendToDjangoAPI(float t1, float t2, float t3, float t4, float pressure);
void initializeADS1220();
void detectDPTSensor();
float readDPTSensor();
int32_t readADS1220();
void writeRegister(uint8_t reg, uint8_t value);
void printAllReadings(float t1, float t2, float t3, float t4, float pressure);
bool connectToWiFi();
void checkWiFiConnection();
void monitorConnection();

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

  // Initialize ADS1220 and detect DPT sensor
  initializeADS1220();
  detectDPTSensor();

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
    float pressure = readDPTSensor();
    
    // Print readings
    printAllReadings(t1, t2, t3, t4, pressure);
    
    // Send to API
    sendToDjangoAPI(t1, t2, t3, t4, pressure);
    
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
  
  // Configure ADS1220 for AIN0-AIN1 differential input
  // Register 0: AIN0-AIN1, PGA bypass, Gain=1
  writeRegister(0, 0x00); 
  // Register 1: DR=20 SPS, Normal mode, Continuous conversion
  writeRegister(1, 0x04);
  // Register 2: Internal reference, 50/60Hz rejection, Pulse conversion
  writeRegister(2, 0x10);
  
  digitalWrite(ADS1220_CS_PIN, HIGH);
  delay(100);
}

void detectDPTSensor() {
  Serial.println("🔧 Detecting DPT sensor...");
  Serial.println("📊 Using 120Ω shunt resistor");
  Serial.println("⚡ Expected: 0.48V (4mA) to 2.40V (20mA)");
  
  float pressure = readDPTSensor();
  
  if (pressure >= -1.0 && pressure <= 12.0) { // Reasonable pressure range
    dptConnected = true;
    Serial.println("✅ " + dptLabel + ": CONNECTED");
    Serial.println("📊 Current reading: " + String(pressure, 2) + " bar");
  } else {
    dptConnected = false;
    Serial.println("❌ " + dptLabel + ": NOT DETECTED");
    Serial.println("🔧 Wiring Guide:");
    Serial.println("   DPT Pin2 → 120Ω → GND");
    Serial.println("   DPT Pin2 → 1kΩ → AIN0");
    Serial.println("   GND side of 120Ω → AIN1");
  }
}

float readDPTSensor() {
  int32_t adcValue = readADS1220();
  
  if (adcValue == 0x7FFFFF || adcValue == 0x800000) {
    return -9999.0; // Invalid reading
  }
  
  // Convert ADC value to voltage (24-bit, 2.048V reference)
  float voltage = (adcValue / 8388607.0) * 2.048;
  
  // Convert voltage to current using 120Ω
  float current = voltage / shuntResistance;
  
  // Debug information
  Serial.print("📊 ADC: " + String(adcValue) + " | ");
  Serial.print("⚡ Voltage: " + String(voltage, 4) + "V | ");
  Serial.print("🔌 Current: " + String(current * 1000, 1) + "mA | ");
  
  // Convert current to pressure (4-20mA = 0-10 bar)
  if (current >= 0.003 && current <= 0.021) { // 3-21mA range with margin
    // More accurate calculation using voltage ranges
    float pressure = ((voltage - voltageAt4mA) / (voltageAt20mA - voltageAt4mA)) * (pressureMax - pressureMin);
    
    // Apply calibration if available
    if (dptAdcMin != 0 && dptAdcMax != 0) {
      float calibratedCurrent = ((adcValue - dptAdcMin) / (float)(dptAdcMax - dptAdcMin)) * (20.0 - 4.0) + 4.0;
      pressure = ((calibratedCurrent - 4.0) / 16.0) * (pressureMax - pressureMin);
    }
    
    pressure = constrain(pressure, pressureMin, pressureMax);
    Serial.println("📏 Pressure: " + String(pressure, 2) + " bar");
    return pressure;
  } else {
    Serial.println("❌ INVALID CURRENT");
    return -9999.0; // Invalid current reading
  }
}

int32_t readADS1220() {
  digitalWrite(ADS1220_CS_PIN, LOW);
  
  // Start conversion
  SPI.transfer(ADS1220_CMD_START);
  delay(100); // Wait for conversion (adjust based on data rate)
  
  // Read conversion result
  SPI.transfer(ADS1220_CMD_RDATA);
  delay(1);
  
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

void printAllReadings(float t1, float t2, float t3, float t4, float pressure) {
  Serial.println("📊 === SENSOR READINGS ===");
  
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
  Serial.println("📊 ======================");
}

void sendToDjangoAPI(float t1, float t2, float t3, float t4, float pressure) {
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
  jsonData += "\"dpt1\":" + (dptConnected && pressure > -9990.0 ? String(pressure,2) : "null");
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
