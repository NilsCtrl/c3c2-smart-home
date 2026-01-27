from flask import Flask, render_template, redirect, request, url_for, render_template_string, flash, abort
import led as LEDC
import file_access as FA
import requests
import json
import urllib.parse
import configparser
import run_on_start as setup2
from db import DBWrapper
from buttons.press_button import PressButton
from buttons.switch_button import SwitchButton

# Zentrale Flask-App für Smart-Home Mini-System
# Kern-Funktionen: Geräteverwaltung, Buttons, Remote-API, History

buttons = []

from exceptions import DeviceTypeNotFoundException

app = Flask(__name__)

config = configparser.ConfigParser()
config.read('.conf')

# Debugging: Print available sections in the config
print(config.sections())

# if config['SYSTEM']['secret_key'].strip('"') != " ":
#     app.secret_key = config['SYSTEM']['secret_key'].strip('"')  # Needed for flashing messages
# else:
#     secret_key = str(setup2.generate.token())
#     app.secret_key = secret_key
#     config.set('SYSTEM', 'secret_key', f'"{secret_key}"')

# if config['SYSTEM']['system_id'].strip('"') != " ":
#     system_id = config['SYSTEM']['system_id'].strip('"')  # Needed for flashing messages
# else:
#     system_id = str(setup2.generate.system_id())
#     config.set('SYSTEM', 'system_id', f'"{system_id}"')

# global api_active
# global api_token
# global api_list
# api_active = bool(config['DEFAULT']['api_active'].strip('"'))

# api_config = configparser.ConfigParser()
# api_config.read('api.conf')

# api_list = []  # Verknüpfte Fremd-Systeme
# for api_group in api_config:
#     if api_group != "DEFAULT":
#         api_list += [{ "url": api_config[api_group]['url'].strip('"'), "token": api_config[api_group]['token'].strip('"')}]

# global connect2api
# global access_url
# connect2api =  config['SYSTEM']['connect2api']
# access_token = config['DEFAULT']['access_token'].strip('"')  # Remove quotes

# if config['DEFAULT']['access_url'].strip('"') != "":
#     access_url = config['DEFAULT']['access_url'].strip('"')  # Remove quotes
# else:
#     access_url = "http://" +setup2.get.ip() + ":" + config['DEFAULT']['port'].strip('"')
# access_url = urllib.parse.quote(access_url)  # URL kodieren

with open('.conf', 'w') as configfile:
    config.write(configfile)

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

# def call_api_info():
    # """Initial: hole System-IDs verbundener APIs"""
    # for api in api_list:
    #     print()
    #     url = api['url'] + f'/api/info?code='+ api['token']
    #     response = requests.get(url)
    #     response = json.loads(response.text)[0]
    #     api['system_id'] = str(response['system_id'])

# def get_api(api_id):
    # for api in api_list:
    #     if api['system_id'] == api_id:
    #         return api
    # return "[{ 'response': 'error'}]"

db = DBWrapper(config["DEFAULT"]["db_name"])  # SQLite Instanz
db.init_db()
db.init_tables()

# -------------------------- Web-Ansichten --------------------------
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

#--------------------------------------------------------------
# call_api's

# def call_all_apis(url_part):
#     """Fragt alle verbundenen APIs ab (GET)"""
#     if api_active == True:
#         full_response = []
#         for api in api_list:
#             try:
#                 url = api['url'] + f'/api/get/{url_part}?code='+ api['token']  
#                 response = requests.get(url)
#                 if str(response) == "<Response [401]>":
#                     flash( '"'+ api['url'] +'" Authorisation failed', 'error')
#                 else:
#                     full_response += [json.loads(response.text)]
#             except:
#                 flash( api['url'] +' is not available', 'error')
#                 pass
            
#         return full_response
    
# def call_api(url_part, use_api):
#     """Einzel-API Anfrage"""
#     if api_active == True:
#         url = use_api['url'] + f'/api/{url_part}?code='+use_api['token']  
#         response = json.loads(requests.get(url).text)[0]
#         return response

# @app.route('/api/device/<pin>/', methods=['GET'])
# def call_api_device(pin):
#     """Geräte-Detail (fremdes System)"""
#     api_id = request.args.get('system_id')
#     api_call = get_api(api_id)
#     response = call_api(f"get/device/{pin}", api_call)
#     return render_template('device.html', device=response)
    

# @app.route('/api/switch/<pin>/', methods=['GET'])
# def call_api_device_switch(pin):
#     """Remote: Toggle Gerät"""
#     api_id = request.args.get('system_id')
#     api_call = get_api(api_id)
#     response = call_api(f"set/switch/{pin}", api_call)
#     return redirect(f'/api/device/'+str(response['pin'])+'?system_id='+str(response['system_id']))

# @app.route('/api/unset/<pin>/', methods=['GET'])
# def call_unset_device(pin):
#     """Remote: Entfernt Gerät"""
#     api_id = request.args.get('system_id')
#     api_call = get_api(api_id)
#     pin = int(pin)
#     if call_api(f"set/unset/{pin}", api_call)['response'] == 'success':
#         flash(f'Pin "{pin}" removed successfully.', 'success')
#     else:
#         flash(f'Pin "{pin}" could not be removed.', 'error')

#     return redirect('/')

# #--------------------------------------------------------------
# # api response

# @app.route('/api/info/')
# def info():
#     return '[{ "system_id": "'+system_id+'", "version": "0.0.1", "allow_connection": "'+str(api_active)+'"}]'

# def auth_check(code):
#     """Tokenprüfung"""
#     if code == access_token:
#         return True
#     else:
#         return False

# @app.route('/api/get/json/')
# def home_json():
#     """API: Alle Geräte (JSON)"""
#     code = request.args.get('code')
#     if auth_check(code):
#         devices = FA.get_devices()
#         for device in devices:
#             try:
#                 device['state'] = LEDC.state(device['pin'])
#             except:
#                 device['state'] = False
#             device['system_id'] = system_id
#         return devices
#     else:
#         abort(401)

# @app.route('/api/get/device/<pin>/')
# def api_device(pin):
#     """API: Einzel-Gerät Status"""
#     code = request.args.get('code')
#     if auth_check(code):
#         pin = int(pin)
#         if LEDC.get.led(pin):
#             return '[{ "devicename": "API", "pin": '+str(pin)+', "device_type": "output", "state": true, "system_id": "'+system_id+'" }]'
#         else:
#             return '[{ "devicename": "API", "pin": '+str(pin)+', "device_type": "output", "state": false, "system_id": "'+system_id+'" }]'
#     abort(401)

# @app.route('/api/set/switch/<pin>/')
# def api_device_switch(pin):
#     """API: Toggle Gerät"""
#     code = request.args.get('code')
#     if auth_check(code):
#         pin = int(pin)
#         device = db.get_device(pin)
#         if device is None:
#             return '[{ "state": false}]'
#         LEDC.set.switch(pin)
#         return '[{ "pin": '+str(pin)+', "system_id": "'+system_id+'" }]'
#     return "[{ 'error': 'Authorisation failed' }]"

# @app.route('/api/set/unset/<pin>')
# def api_set_unset_device(pin):
#     """API: Gerät entfernen"""
#     code = request.args.get('code')
#     if auth_check(code):
#         pin = int(pin)
#         call_url = request.args.get('url')
#         try:
#             LEDC.clear_led(pin)
#             FA.remove_device(pin)
#             return [{"response": "success"}]
#         except:
#             return [{"response": "error"}]
#     return "[{ 'error': 'Authorisation failed' }]"

# #--------------------------------------------------------------

# call_api_info()

def start():
    """Startet Flask (extern aufrufbar)"""
    app.run(debug=True, port=config['DEFAULT']['port'].strip('"'), host='0.0.0.0')

start()
