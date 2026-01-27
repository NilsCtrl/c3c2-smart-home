import sqlite3
from collections import defaultdict
import time as t

from exceptions import DBExistsException, DeviceTypeNotFoundException, DeviceNotFoundException

# Datenbank-Wrapper für Gerätesteuerung (leichtgewichtig)
# Fokus: Geräte, Typen, Logs, Zustands-Historie

class DBWrapper:
    def __init__(self, db_name):
        self.db_name = db_name
        self.connection = None
        self.cur = None
        # DB initial noch nicht verbunden

    def dict_factory(self, cursor, row):
        """Zeilen -> Dict (spaltenname: wert)"""
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def group_by_minute(self, data):
        """Gruppiert History-Einträge nach Minute"""
        history_by_minute = defaultdict(list)
        for row in data:
            minute = row["minute_group"]
            history_by_minute[minute].append(row)
        return dict(history_by_minute)

    def create_db(self):
        """Stellt Verbindung her (einmalig)"""
        self.connection = sqlite3.connect(self.db_name,check_same_thread=False)
        self.connection.row_factory = self.dict_factory
        self.cur = self.connection.cursor()
        return self.cur

    def init_tables(self):
        """Erzeugt Tabellen falls nicht vorhanden & schreibt Startup-Log"""
        start = t.time()
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
                type TEXT NOT NULL,
                code TEXT NOT NULL,
                message TEXT NOT NULL,
                deviceID INTEGER,
                FOREIGN KEY(deviceID) REFERENCES device(id)
            );
        """)

        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                deviceID INTEGER,
                temperature REAL,
                humidity REAL,
                pressure REAL,
                FOREIGN KEY(deviceID) REFERENCES device(id)
            );
        """)

        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS device_type (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_type TEXT NOT NULL
            );
        """)
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS device (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                devicename TEXT NOT NULL,
                pin INTEGER NOT NULL UNIQUE,
                second_pin INTEGER UNIQUE,
                device_type_id INTEGER NOT NULL,
                roomID INTEGER,
                state INTEGER,
                FOREIGN KEY(device_type_id) REFERENCES device_type(id)
            );
        """)

        # Standard-Gerätetypen (id fix): 1=output, 2=input, 3=virt
        self.cur.executemany("""
            INSERT OR IGNORE INTO device_type (id, device_type) VALUES (?, ?);
        """, [(1, 'output'), (2, 'input'), (3, 'virtual_input')])
        time_to_build = t.time() - start
        self.cur.execute("""
            INSERT INTO logs (type, code, message, deviceID)
            VALUES (?, ?, ?, NULL);
        """, ('info', 'startup', f'System initialized in {time_to_build:.2f} secs'))
        self.connection.commit()

    def init_db(self):
        """Convenience: erstellt Verbindung"""
        self.create_db()
        return self.cur

    def write_log(self, msg_type: str, code: str, message: str, device_id=None):
        """Schreibt Logeintrag"""
        self.cur.execute("""
            INSERT INTO logs (type, code, message, deviceID)
            VALUES (?, ?, ?, ?);
        """, (msg_type, code, message, device_id))
        self.connection.commit()

    def add_device(self, device_name: str, pin: int, device_type: int, secondary_pin=None, room_id = 0):
        """Neues Gerät hinzufügen (Pin eindeutig). Rückgabe True/False"""
        device_type_obj = self.cur.execute("""
            SELECT id FROM device_type WHERE id = ?;
        """, (device_type,)).fetchone()
        if not device_type_obj:
            raise DeviceTypeNotFoundException(f"Device type not found",device_type)
            
        try:
            if device_type == 1:
                self.cur.execute("""
                    INSERT INTO device (devicename, pin, device_type_id, roomID)
                    VALUES (?, ?, ?, ?);
                """, (device_name, pin, device_type, room_id))
            elif device_type == 2:
                self.cur.execute("""
                    INSERT INTO device (devicename, pin, secondary_pin, device_type_id, roomID)
                    VALUES (?, ?, ?, ?, ?);
                """, (device_name, pin, secondary_pin, device_type, room_id))
        except sqlite3.IntegrityError:
            return False
        self.write_log("info", "device_added", f"Successfully added device {device_name} of type {device_type} on pin {pin}")
        self.connection.commit()
        return True

    def remove_device(self, pin):
        """Entfernt Gerät anhand Pin oder wirft Ausnahme"""
        pin_is_in_use = self.cur.execute("""
            SELECT pin FROM device WHERE pin = ?;
        """, (pin,)).fetchone()
        if pin_is_in_use:
            self.cur.execute("""
                DELETE FROM device WHERE pin = ?;
            """, (pin,))
            self.write_log("info", "device_removed", f"Successfully removed device on pin {pin}")
            self.connection.commit()
        else:
            raise DeviceNotFoundException(f"Device with pin {pin} not found")

    def get_device(self, pin):
        """Gerät via Pin holen (oder None)"""
        device = self.cur.execute("""
        SELECT * FROM device WHERE pin = ?;
        """, (pin,)).fetchone()
        
        return device
    
    def get_all_devices(self):
        """Alle Geräte (Liste)"""
        all_devices = self.cur.execute("""
        SELECT * FROM device ORDER BY roomID DESC;
        """).fetchall()
        return all_devices
    
    def get_all_devices_for_room(self,room_id: int):
        """Geräte in Raum"""
        all_devices_for_room = self.cur.execute("""
        SELECT * FROM device WHERE roomID = ?;
        """, (room_id,)).fetchall()

        return all_devices_for_room
    
    def get_all_devices_grouped_by_room(self):
        """Geräte gruppiert nach Raum -> Dict"""
        all_devices = self.cur.execute("""
        SELECT * FROM device ORDER BY roomID DESC;
        """).fetchall()

        grouped_devices = {}

        for device in all_devices:
            roomID = device["roomID"]
            if roomID not in grouped_devices:
                grouped_devices[roomID] = []
            grouped_devices[roomID].append(device)
        
        return grouped_devices


    def update_device_state_by_pin(self, pin: int, state: int):
        """Speichert aktuellen Zustand (state)"""
        update = self.cur.execute("""
        UPDATE device SET state = ? WHERE pin = ?;
        """, (state,pin, ))
        self.write_log("INFO", 200 , f"Updated state on pin {pin} to {state}" )
        self.connection.commit()

    def get_number_of_rooms(self):
        """Liste distinct roomIDs"""
        result = self.cur.execute("""
        SELECT DISTINCT roomID FROM device;
        """).fetchall()
        return result
    
    def create_record(self, deviceID, temp, hum, pres):
        """Historieneintrag anlegen"""
        self.cur.execute("""
                INSERT INTO history (deviceID, temperature, humidity, pressure)
                VALUES (?, ?, ?, ?)
            """, (deviceID, temp, hum, pres))

        self.connection.commit()
        return True
    
    def get_num_state_updates(self):
        """Anzahl Zustandsänderungen (COUNT)"""
        num_updates = self.cur.execute("""
            SELECT COUNT(deviceID) FROM history;
        """)
        return num_updates
    def get_history(self):
        """History gruppiert nach Minute"""
        history_entries = self.cur.execute("""
            SELECT 
                strftime('%Y-%m-%d %H:%M', history.timestamp) AS minute_group,
                device.devicename,
                device.id AS device_id,
                device.roomID,
                history.state
            FROM 
                history
            JOIN 
                device ON history.deviceID = device.id
            GROUP BY 
                minute_group, device.id
            ORDER BY 
                minute_group DESC;
        """)
        grouped_data = self.group_by_minute(history_entries)
        return grouped_data

    def get_all_buttons(self):
        """Alle Button-Geräte (device_type_id=2)"""
        return  self.cur.execute("""
            SELECT * FROM device WHERE device_type_id=2;
        """).fetchall()
    
    def log_sensor_data(self, device_id, temperature, humidity, pressure):
        """Logs sensor data into the history table."""
        self.cur.execute("""
            INSERT INTO history (deviceID, temperature, humidity, pressure) VALUES (?, ?, ?, ?)
        """, (device_id, temperature, humidity, pressure))
        self.connection.commit()
        
    def get_all_history(self):
        """Ruft alle Historieneinträge ab."""
        history_entries = self.cur.execute("""
            SELECT 
                id, 
                datetime(timestamp, 'localtime'), 
                deviceID, 
                temperature, 
                humidity, 
                pressure 
            FROM history 
            ORDER BY timestamp DESC;
        """).fetchall()
        return history_entries


    def close(self):
        """DB-Verbindung schließen"""
        if self.connection:
            self.connection.close()


if __name__ == "__main__":
    # 1. Objekt erstellen
    db = DBWrapper("c2c1.db")
    
    # 2. Verbindung herstellen und Tabellen anlegen
    db.init_db()
    db.init_tables()
    
    # 3. Testweise ein Gerät hinzufügen
    db.add_device("Luftsensor", 17, 1)
    
    print("Datenbank wurde initialisiert und Test-Gerät angelegt.")
    db.close()