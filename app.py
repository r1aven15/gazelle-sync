from flask import Flask
import os
import requests
import json
import time
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

app = Flask(__name__)

# --- FIREBASE ---
firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
if firebase_creds_json:
    try:
        cred_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception as e: print(f"Ошибка Firebase: {e}")

# --- ГЛОНАСС ---
GLONASS_LOGIN = os.environ.get('GLONASS_LOGIN')
GLONASS_PASSWORD = os.environ.get('GLONASS_PASSWORD')
GLONASS_URL = "https://hosting.glonasssoft.ru"

def get_glonass_token():
    url = f"{GLONASS_URL}/api/v3/auth/login"
    try:
        response = requests.post(url, json={"login": GLONASS_LOGIN, "password": GLONASS_PASSWORD}, timeout=15)
        response.raise_for_status()
        return response.json().get('AuthId'), None
    except Exception as e: return None, str(e)

def get_vehicle_fuel(token, v_id):
    """Правильный запрос топлива с includeSensors и vehiclesIds"""
    url = f"{GLONASS_URL}/api/v3/vehicles/getlastdata"
    
    # ИСПРАВЛЕНО: vehiclesIds (с маленькой v, но с s на конце)
    payload = {
        "vehiclesIds": [v_id], 
        "includeSensors": True
    }
    
    try:
        r = requests.post(url, headers={"X-Auth": token, "Content-Type": "application/json"}, json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0:
                sensors = data[0].get('sensors', [])
                for s in sensors:
                    if s.get('parameterName') == 'flex_fuel1':
                        return s.get('value', 0)
            return 0
        else:
            print(f"Ошибка топлива: {r.status_code} {r.text}")
            return 0
    except Exception as e:
        print(f"Сбой топлива: {e}")
        return 0

def get_vehicle_daily_mileage(token, v_id):
    today = datetime.now().strftime('%Y-%m-%d')
    start_time = f"{today}T00:00:00.000Z"
    end_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')
    
    url = f"{GLONASS_URL}/api/v3/vehicles/mileageAndMotohours"
    payload = {"vehicleIds": [v_id], "from": start_time, "to": end_time}
    
    try:
        r = requests.post(url, headers={"X-Auth": token, "Content-Type": "application/json"}, json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0 and data[0].get('periods'):
                return data[0]['periods'][0].get('mileage', 0)
        return 0
    except Exception as e: return 0

@app.route('/sync')
def sync():
    token, err = get_glonass_token()
    if not token: return f"Ошибка токена: {err}", 500
    
    res = requests.post(f"{GLONASS_URL}/api/v3/vehicles/find", headers={"X-Auth": token}, json={})
    vehicles = res.json()
    
    doc_ref = db.collection('gazelle_app').document('main_data')
    doc = doc_ref.get()
    
    if doc.exists:
        current_data = doc.to_dict()
        html_cars = current_data.get('cars', [])
    else:
        current_data = {}
        html_cars = []

    updated_count = 0
    log_msgs = []

    for g_vehicle in vehicles:
        g_name = g_vehicle.get('name', 'Без названия').strip()
        g_id = g_vehicle.get('vehicleId')
        
        existing_car = next((c for c in html_cars if c.get('name', '').strip() == g_name), None)
        
        if existing_car:
            daily_mileage = get_vehicle_daily_mileage(token, g_id)
            time.sleep(1) 
            
            fuel_liters = get_vehicle_fuel(token, g_id)
            time.sleep(1)

            if daily_mileage > 0:
                if 'manualBaseMileage' not in existing_car:
                    existing_car['manualBaseMileage'] = existing_car.get('odometer', 0)
                new_odo = int(existing_car['manualBaseMileage'] + daily_mileage)
                existing_car['odometer'] = new_odo
                updated_count += 1
                log_msgs.append(f"{g_name}: Пробег +{daily_mileage} (Итого: {new_odo})")
            
            if fuel_liters > 0:
                existing_car['fuelLevel'] = fuel_liters
                log_msgs.append(f"{g_name}: Топливо {fuel_liters} л")

    if updated_count > 0 or len(log_msgs) > 0:
        full_data = {
            "cars": html_cars,
            "log": current_data.get('log', []),
            "drivers": current_data.get('drivers', []),
            "trips": current_data.get('trips', []),
            "expenses": current_data.get('expenses', []),
            "theme": current_data.get('theme', 'light'),
            "snapshots": current_data.get('snapshots', []),
            "trash": current_data.get('trash', [])
        }
        doc_ref.set(full_data)
        return f"СИНХРОНИЗАЦИЯ!<br>" + "<br>".join(log_msgs)
    else:
        return "Данных для обновления нет (пробег 0, топливо 0)."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
