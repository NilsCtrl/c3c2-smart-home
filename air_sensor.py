import smbus2
import time
import sqlite3
from bme280 import BME280

# Configuration
DB_PATH = "/home/it/Dokumente/c3c2-smart-home/c3c2-smart-home/c2c1.db"
DEVICE_ID = 1
INTERVAL = 5 

# Initialize Sensor mit expliziter Adresse (meist 0x76 oder 0x77)
bus = smbus2.SMBus(1)
# Falls Fehler auftreten, versuche i2c_addr=0x76
bme280 = BME280(i2c_dev=bus)

# "Warm-up" Reading: Ersten Wert verwerfen
try:
    bme280.get_temperature()
    time.sleep(1)
except:
    pass

def save_in_db(db_path, device_id, temperature, humidity, pressure):
    try:
        # timeout hilft gegen "database is locked" Fehler
        with sqlite3.connect(db_path, timeout=10) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO air_measurement (timestamp, deviceID, temperature, humidity, pressure)
                VALUES (datetime('now'), ?, ?, ?, ?)
            """, (device_id, round(temperature, 2), round(humidity, 2), round(pressure, 2)))
            conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")

print(f"Starting logging to {DB_PATH}...")

try:
    while True:
        # Sensordaten auslesen
        t = bme280.get_temperature()
        h = bme280.get_humidity()
        p = bme280.get_pressure()

        print(f"[{time.strftime('%H:%M:%S')}] T:{t:.2f}°C H:{h:.2f}% P:{p:.2f}hPa")
        
        save_in_db(DB_PATH, DEVICE_ID, t, h, p)
        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nLogging gestoppt.")
finally:
    bus.close()