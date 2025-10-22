# iot_client.py
import requests
import json
import time
import random
from datetime import datetime

class HeatExchangerMonitor:
    def __init__(self, device_id, write_api_key, server_url="http://65.0.30.109"):
        self.device_id = device_id
        self.write_api_key = write_api_key
        self.server_url = server_url
        self.session = requests.Session()
        
    def read_sensors(self):
        """Simulate reading sensors - Replace with actual sensor reading code"""
        # This is where you'd interface with actual sensors
        return {
            "T1_In": round(random.uniform(20.0, 35.0), 2),
            "T1_Out": round(random.uniform(40.0, 60.0), 2),
            "T2_In": round(random.uniform(15.0, 25.0), 2),
            "T2_Out": round(random.uniform(30.0, 45.0), 2),
            "DP_In": round(random.uniform(100.0, 150.0), 2),
            "DP_Out": round(random.uniform(80.0, 120.0), 2),
            "Flow_In": round(random.uniform(50.0, 100.0), 2),
            "Flow_Out": round(random.uniform(45.0, 95.0), 2)
        }
    
    def send_data(self, sensor_data):
        """Send sensor data to server"""
        url = f"{self.server_url}/api/write_data/{self.device_id}/"
        headers = {
            "Authorization": f"Token {self.write_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "sensor_data": sensor_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            print(f"Data sent successfully: {response.json()}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error sending data: {e}")
            return False
    
    def run_monitoring(self, interval=30):
        """Main monitoring loop"""
        print(f"Starting Heat Exchanger Monitoring for device {self.device_id}")
        
        while True:
            try:
                # Read sensors
                sensor_data = self.read_sensors()
                print(f"Sensor readings: {sensor_data}")
                
                # Send to server
                success = self.send_data(sensor_data)
                
                if success:
                    # Calculate fouling (simplified)
                    fouling_factor = self.calculate_fouling(sensor_data)
                    print(f"Calculated fouling factor: {fouling_factor}")
                
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
            
            time.sleep(interval)
    
    def calculate_fouling(self, sensor_data):
        """Calculate fouling factor based on sensor data"""
        # Simplified fouling calculation - replace with your actual algorithm
        temp_diff = sensor_data["T1_Out"] - sensor_data["T1_In"]
        flow_ratio = sensor_data["Flow_In"] / max(sensor_data["Flow_Out"], 1.0)
        
        fouling_factor = (temp_diff * flow_ratio) / 100.0
        return round(fouling_factor, 4)

# Usage example
if __name__ == "__main__":
    # These values should come from device configuration
    DEVICE_ID = 2
    WRITE_API_KEY = "platex_machine_001"  # This will be auto-generated
    
    monitor = HeatExchangerMonitor(DEVICE_ID, WRITE_API_KEY)
    monitor.run_monitoring(interval=30)  # Send data every 30 seconds
