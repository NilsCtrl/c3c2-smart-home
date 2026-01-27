import smbus2
import time
import sqlite3
import logging
from bme280 import BME280

# Configuration
DB_PATH = "/home/it/Dokumente/c3c2-smart-home/c3c2-smart-home/c2c1.db"
DEVICE_ID = 1
INTERVAL = 5  # Seconds between readings

# Initialize Sensor
bus = smbus2.SMBus(1)
bme280 = BME280(i2c_dev=bus)

def write_sensor(db_path, device_id, temperature, humidity, pressure):
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO history (timestamp, deviceID, temperature, humidity, pressure)
                VALUES (datetime('now', 'localtime'), ?, ?, ?, ?)
            """, (device_id, round(temperature, 2), round(humidity, 2), round(pressure, 2)))
            conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")

print(f"Starting logging to {DB_PATH}...")

try:
    while True:
        t = bme280.get_temperature()
        h = bme280.get_humidity()
        p = bme280.get_pressure()

        print(f"[{time.strftime('%H:%M:%S')}] T:{t:.1f}°C H:{h:.1f}% P:{p:.1f}hPa")
        
        write_sensor(DB_PATH, DEVICE_ID, t, h, p)
        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nLogging stopped by user.")
finally:
    bus.close()