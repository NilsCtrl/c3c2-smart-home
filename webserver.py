from flask import Flask, render_template, redirect, request, url_for, render_template_string, flash, abort
import led as LEDC
import file_access as FA
import configparser
import run_on_start as setup2
from db import DBWrapper
from buttons.press_button import PressButton
from buttons.switch_button import SwitchButton
from exceptions import DeviceTypeNotFoundException
# import os
import sqlite3


# --- Erweiterung der DBWrapper Logik (lokal oder in db.py) ---
# Hinweis: Idealerweise fügst du diese Methode direkt in deine db.py Datei ein.
def get_all_history_extended(self):
    try:
        # Nutzt die bestehende Verbindungsmethode deiner DBWrapper Klasse
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row 
            cursor = connection.cursor()
            return cursor.execute("SELECT * FROM history ORDER BY timestamp DESC;").fetchall()
    except sqlite3.OperationalError as e:
        print(f"Datenbankfehler: {e}")
        return []
    
def create_record(deviceID, state):
    """Persistiert Zustandsänderung"""
    db.create_record(deviceID, state)

def switch(pin):
    """Toggle physisches Gerät + Zustand speichern"""
    device = db.get_device(pin)
    if device is None:
        return redirect(url_for('error'))
    LEDC.set.switch(pin)
    state = LEDC.get.led(pin)
    db.update_device_state_by_pin(pin, state)
    create_record(int(device["id"]), state)

# Wir "patchen" die Methode hier für das Beispiel, falls du db.py nicht ändern willst:
DBWrapper.get_all_history_extended = get_all_history_extended

app = Flask(__name__)

config = configparser.ConfigParser()
config.read('.conf')

# Initialisierung der Datenbank über den bestehenden Wrapper
db = DBWrapper(config["DEFAULT"]["db_name"])
db.init_db()
db.init_tables()

buttons = []

@app.route('/')
def home():
    """Übersicht: Geräte gruppiert nach Raum"""
    devices = db.get_all_devices()
    num_rooms = db.get_number_of_rooms()
    grouped_devices = db.get_all_devices_grouped_by_room()
    all_buttons = db.get_all_buttons()

    # if config['SYSTEM']['connect2api'].strip('"') == "true":
    #     for response in call_all_apis("json"):
    #         devices += response

    return render_template('index.html', devices_by_room=grouped_devices, all_devices=devices, all_button_devices=all_buttons)

@app.route('/air_measurement')
def air_measurement():
    air_measurement_entries = db.get_air_measurements()
    return render_template('air_measurement.html', history=air_measurement_entries)

@app.route('/device/<pin>/')
def device(pin):
    """Detailansicht eines Geräts"""
    pin = int(pin)
    device = db.get_device(pin)
    if device is None:
        return redirect(url_for('error'))
    try:
        state = int(device["state"])
    except:
        db.update_device_state_by_pin(pin, 0)
    return render_template('device.html', device=device)

@app.route('/switch/<pin>/')
def device_switch(pin):
    """UI: Gerät toggeln"""
    pin = int(pin)
    switch(pin)
    return redirect(f'/device/{pin}')

@app.route('/unset/<pin>/')
def unset_pin(pin):
    """Gerät entfernen & Pin freigeben"""
    pin = int(pin)
    device = db.get_device(pin)
    if device is None:
        return redirect(url_for('error'))
    db.remove_device(pin)
    LEDC.clear_led(pin)
    
    flash(f'Pin "{pin}" is now unset and cleand.', 'success')
    return redirect('/')

@app.route('/add-device', methods=['POST'])
def add_device():
    """Neues Output-Gerät hinzufügen"""
    device_name = request.form.get('deviceName')
    pin = int(request.form.get('pin'))
    device_type = request.form.get('deviceType')
    roomID = int(request.form.get('roomID'))
    if not db.get_device(pin):
        db.add_device(device_name, pin, device_type, roomID)
    else:
        flash(f'Error: Pin "{pin}" is already in use.', 'error')
        return redirect(url_for('home'))
    try:
        if device_type == 'output':
            if LEDC.setup_led(pin):
                flash(f'Device "{device_name}" added successfully.', 'success')
                pass
            else:
                db.remove_device(pin)
                flash(f'Error by pin setup "{device_name}" are not created.', 'error')
        else:
            flash("Not implemented yet! Use Add Button to add button devices!")
            pass
    except:
        FA.remove(pin)
        flash(f'Error "{device_name}" are not created.', 'error')

    return redirect("/")

@app.route("/add-button", methods=['POST'])
def add_button():
    """Button (Input->Output) anlegen"""
    device_name = request.form.get('deviceName')
    input_pin = int(request.form.get('inputPin')) #24
    output_pin = int(request.form.get('outputPin'))
    button_type = int(request.form.get('buttonType'))
    device_type = 2
    try:
        if not db.get_device(input_pin):
            db.add_device(device_name, input_pin, device_type , secondary_pin=output_pin,room_id=1000)
        else:
            flash(f'Error: Pin "{input_pin}" is already in use.', 'error')
            return redirect(url_for('home'))
    except DeviceTypeNotFoundException:
        flash(f"Device type with id {device_type} does not exist", 'error')
        return redirect(url_for('home'))

    if button_type == 1:
            btn = SwitchButton(input_pin,output_pin)
            buttons.append(btn)
    elif button_type == 2:
            btn = PressButton(input_pin, output_pin)
            buttons.append(btn)
    else:
        flash("Button Type does not exist!")
        redirect(url_for('home'))
    flash(f"Added button {device_name} successfully on pin {input_pin}")
    return redirect("/")

@app.route("/room/<roomID>")
def room_toggle(roomID):
    """Alle Geräte in Raum toggeln"""
    roomID = int(roomID)
    devices_in_room = db.get_all_devices_for_room(roomID)
    for device in devices_in_room:
        switch(int(device['pin']))
    
    return redirect("/")

@app.route('/stats')
def stats():
    """Statistik / History"""
    stats = db.get_num_state_updates()
    history = db.get_history()
    return render_template("stats.html", stats=stats, history_by_minute=history)

@app.route('/<all>')
def catch(all = None):
    return render_template('error.html')

@app.route('/error')
def error():
    return render_template('error.html')

def start():
    """Startet Flask"""
    port_val = config['DEFAULT'].get('port', '5000').strip('"')
    app.run(debug=True, port=int(port_val), host='0.0.0.0')
    app.run(debug=True, port=config['DEFAULT']['port'].strip('"'), host='0.0.0.0')

if __name__ == '__main__':
    start()