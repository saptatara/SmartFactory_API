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
const char* host = "150.241.244.250";  // Your server IP
const int port = 8001;                 // Django server port
String writeApiKey = "f9cec3cb-f793-4345-aa9e-1f8284ce38f9";  // Platex device write key
String deviceId = "1";                 // Platex device ID

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

// Function prototypes
void testDjangoConnection();
void sendToDjangoAPI(float t1, float t2, float t3, float t4, float pressure);
void initializeADS1220();
void detectDPTSensor();
float readDPTSensor();
int32_t readADS1220();
void writeRegister(uint8_t reg, uint8_t value);
void printAllReadings(float t1, float t2, float t3, float t4, float pressure);

void setup() {
  Serial.begin(115200);
  
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
  Serial.print("Temperature sensors found: ");
  Serial.println(numberOfTempSensors);

  // Detect temperature sensors
  for (int i = 0; i < 4; i++) {
    if (sensors.getAddress(tempSensorAddress[i], i)) {
      tempSensorConnected[i] = true;
      Serial.print("Temp Sensor ");
      Serial.print(i);
      Serial.print(" (");
      Serial.print(tempSensorLabels[i]);
      Serial.println("): Connected");
    } else {
      tempSensorConnected[i] = false;
      Serial.print("Temp Sensor ");
      Serial.print(i);
      Serial.print(" (");
      Serial.print(tempSensorLabels[i]);
      Serial.println("): NOT CONNECTED");
    }
  }

  // Initialize ADS1220 and detect DPT sensor
  initializeADS1220();
  detectDPTSensor();

  // Connect to WiFi
  Serial.println("Connecting to WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
  
  // Test Django connection
  testDjangoConnection();
}

void testDjangoConnection() {
  Serial.println("🧪 Testing Django connection...");
  
  WiFiClient client;
  if (client.connect(host, port)) {
    Serial.println("✅ Django server is reachable");
    
    // Send a simple test request - FIXED STRING CONCATENATION
    String testRequest = String("GET /health/ HTTP/1.1\r\n") +
                        "Host: " + String(host) + "\r\n" +
                        "Connection: close\r\n\r\n";
    
    client.print(testRequest);
    
    // Read response
    unsigned long timeout = millis();
    while (client.connected() && millis() - timeout < 5000) {
      if (client.available()) {
        String line = client.readStringUntil('\n');
        Serial.println("Test response: " + line);
      }
    }
    client.stop();
  } else {
    Serial.println("❌ Django server is NOT reachable");
    Serial.println("Please check:");
    Serial.println("1. Server IP: " + String(host));
    Serial.println("2. Port: " + String(port));
    Serial.println("3. Django is running: docker ps");
    Serial.println("4. Firewall allows port " + String(port));
  }
}

void loop() {
  // Read temperature sensors
  sensors.requestTemperatures();
  float t1 = tempSensorConnected[0] ? sensors.getTempCByIndex(0) : -999.0;
  float t2 = tempSensorConnected[1] ? sensors.getTempCByIndex(1) : -999.0;
  float t3 = tempSensorConnected[2] ? sensors.getTempCByIndex(2) : -999.0;
  float t4 = tempSensorConnected[3] ? sensors.getTempCByIndex(3) : -999.0;

  // Read DPT sensor
  float pressure = readDPTSensor();

  // Print all readings to Serial
  printAllReadings(t1, t2, t3, t4, pressure);
  
  // Send data to Django API
  sendToDjangoAPI(t1, t2, t3, t4, pressure);

  delay(30000); // Send data every 30 seconds
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
  Serial.println("Detecting DPT sensor...");
  Serial.println("Using 120Ω shunt resistor");
  Serial.println("Expected voltage range: 0.48V to 2.40V");
  
  float pressure = readDPTSensor();
  
  if (pressure >= -1.0 && pressure <= 12.0) { // Reasonable pressure range
    dptConnected = true;
    Serial.println(dptLabel + ": CONNECTED");
    Serial.println("Current reading: " + String(pressure, 2) + " bar");
  } else {
    dptConnected = false;
    Serial.println(dptLabel + ": NOT DETECTED");
    Serial.println("Please check wiring: DPT Pin2 -> 120Ω -> GND");
    Serial.println("Measurement points: AIN0 (after 1kΩ) and AIN1 (GND side)");
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
  Serial.print("ADC: " + String(adcValue) + " | ");
  Serial.print("Voltage: " + String(voltage, 4) + "V | ");
  Serial.print("Current: " + String(current * 1000, 1) + "mA | ");
  
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
    Serial.println("Pressure: " + String(pressure, 2) + " bar");
    return pressure;
  } else {
    Serial.println("INVALID CURRENT");
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
  Serial.println("=== SENSOR READINGS ===");
  
  // Temperature readings
  Serial.println("Temperature Sensors:");
  Serial.print(tempSensorLabels[0] + ": ");
  Serial.println(tempSensorConnected[0] ? String(t1, 1) + "°C" : "NOT CONNECTED");
  Serial.print(tempSensorLabels[1] + ": ");
  Serial.println(tempSensorConnected[1] ? String(t2, 1) + "°C" : "NOT CONNECTED");
  Serial.print(tempSensorLabels[2] + ": ");
  Serial.println(tempSensorConnected[2] ? String(t3, 1) + "°C" : "NOT CONNECTED");
  Serial.print(tempSensorLabels[3] + ": ");
  Serial.println(tempSensorConnected[3] ? String(t4, 1) + "°C" : "NOT CONNECTED");
  
  // DPT reading
  Serial.println("DPT Sensor (120Ω shunt):");
  Serial.print(dptLabel + ": ");
  if (dptConnected && pressure > -9990.0) {
    Serial.println(String(pressure, 2) + " bar");
  } else {
    Serial.println("NOT DETECTED");
  }
  Serial.println("======================");
}

void sendToDjangoAPI(float t1, float t2, float t3, float t4, float pressure) {
  WiFiClient client;
  
  Serial.println("🔌 Attempting to connect to Django server...");
  Serial.print("Host: "); Serial.print(host); Serial.print(":"); Serial.println(port);
  
  // Test connection with timeout
  unsigned long connectTimeout = 10000; // 10 seconds
  unsigned long connectStart = millis();
  
  if (!client.connect(host, port)) {
    Serial.println("❌ Connection to Django failed - server unreachable");
    Serial.println("Possible reasons:");
    Serial.println("1. Django server is down");
    Serial.println("2. Network connectivity issue");
    Serial.println("3. Wrong IP/port");
    Serial.println("4. Firewall blocking connection");
    
    // Check WiFi status
    Serial.print("WiFi status: ");
    Serial.println(WiFi.status());
    Serial.print("RSSI: ");
    Serial.println(WiFi.RSSI());
    return;
  }
  
  Serial.println("✅ Connected to Django server!");
  
  String jsonData = "{";
  
  // Temperature data
  jsonData += "\"t1_in\":" + (tempSensorConnected[0] ? String(t1,2) : "null") + ",";
  jsonData += "\"t1_out\":" + (tempSensorConnected[1] ? String(t2,2) : "null") + ",";
  jsonData += "\"t2_in\":" + (tempSensorConnected[2] ? String(t3,2) : "null") + ",";
  jsonData += "\"t2_out\":" + (tempSensorConnected[3] ? String(t4,2) : "null") + ",";
  
  // DPT data
  jsonData += "\"dpt1\":" + (dptConnected && pressure > -9990.0 ? String(pressure,2) : "null");
  jsonData += "}";

  String request = "POST /api/write_data/" + deviceId + "/ HTTP/1.1\r\n" +
                   "Host: " + String(host) + "\r\n" +
                   "Authorization: Bearer " + writeApiKey + "\r\n" +  // ← CHANGED "Token" to "Bearer"
                   "Content-Type: application/json\r\n" +
                   "Connection: close\r\n" +
                   "Content-Length: " + String(jsonData.length()) + "\r\n\r\n" +
                   jsonData;

  Serial.println("📤 Sending request to Django...");
  client.print(request);
  
  Serial.println("Sent to Django:");
  Serial.println(jsonData);
  Serial.println("API Key: " + writeApiKey);

  // Wait for response with timeout
  unsigned long responseTimeout = 10000; // 10 seconds
  unsigned long responseStart = millis();
  bool headersReceived = false;
  String response = "";

  while (client.connected() && millis() - responseStart < responseTimeout) {
    if (client.available()) {
      String line = client.readStringUntil('\n');
      
      if (!headersReceived) {
        Serial.println("Header: " + line);
        if (line == "\r") {
          headersReceived = true;
          Serial.println("=== Response Body ===");
        }
      } else {
        response += line + "\n";
        Serial.println("Body: " + line);
      }
    }
    
    // Small delay to allow data to arrive
    delay(10);
  }

  if (response.length() > 0) {
    Serial.println("✅ Full Response: " + response);
  } else {
    Serial.println("❌ No response received (timeout)");
  }
  
  client.stop();
  Serial.println("Connection closed.");
}
