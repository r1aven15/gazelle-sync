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
    except Exception as e: 
        print(f"Ошибка Firebase: {e}")

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
    except Exception as e: 
        return None, str(e)

def get_vehicle_data(token, v_id):
    today = datetime.now().strftime('%Y-%m-%d')
    start_time = f"{today}T00:00:00.000Z"
    end_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')
    
    mileage = 0
    try:
        r = requests.post(f"{GLONASS_URL}/api/v3/vehicles/mileageAndMotohours", 
            headers={"X-Auth": token}, json={"vehicleIds": [v_id], "from": start_time, "to": end_time}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0 and data[0].get('periods'):
                mileage = data[0]['periods'][0].get('mileage', 0)
    except: 
        pass

    fuel = 0
    try:
        r = requests.post(f"{GLONASS_URL}/api/v3/vehicles/getlastdata", 
            headers={"X-Auth": token}, json={"vehiclesIds": [v_id], "includeSensors": True}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0 and data[0].get('sensors'):
                for s in data[0]['sensors']:
                    if s.get('name') == 'Топливо' and s.get('isValid'):
                        fuel = s.get('rawValue', 0)
                        break
    except: 
        pass

    return mileage, fuel

@app.route('/sync')
def sync():
    token, err = get_glonass_token()
    if not token: 
        return f"Ошибка токена: {err}", 500
    
    res = requests.post(f"{GLONASS_URL}/api/v3/vehicles/find", headers={"X-Auth": token}, json={})
    vehicles = res.json()
    
    cars_to_save = []
    
    for g_vehicle in vehicles:
        g_name = g_vehicle.get('name', 'Без названия').strip()
        g_id = g_vehicle.get('vehicleId')
        
        daily_mileage, fuel_liters = get_vehicle_data(token, g_id)
        time.sleep(1)
        
        car_obj = {
            "id": f"glonass_{g_id}",
            "name": g_name,
            "glonassName": g_name,
            "odometer": int(daily_mileage),
            "fuelLevel": round(fuel_liters, 1),
            "manualBaseMileage": 0,
            "vin": "",
            "model": g_vehicle.get('modelName', ''),
            "bodyType": "фургон",
            "fridgeModel": "",
            "insuranceFrom": "",
            "insuranceTo": "",
            "items": [
                {"key":"oil", "label":"Масло двигателя", "lastMileage":0, "lastDate":"2026-11-21", "interval":10000, "intervalDays":0},
                {"key":"air", "label":"Воздушный фильтр", "lastMileage":0, "lastDate":"2026-11-21", "interval":15000, "intervalDays":0},
                {"key":"fuel", "label":"Топливный фильтр", "lastMileage":0, "lastDate":"2026-11-21", "interval":20000, "intervalDays":0},
                {"key":"brakes", "label":"Тормозные колодки", "lastMileage":0, "lastDate":"2026-11-21", "interval":30000, "intervalDays":0},
                {"key":"tires", "label":"Шиномонтаж", "lastMileage":0, "lastDate":"2026-11-21", "interval":20000, "intervalDays":0}
            ]
        }
        cars_to_save.append(car_obj)

    if db:
        doc_ref = db.collection('gazelle_app').document('main_data')
        doc_ref.set({"cars": cars_to_save}, merge=True)
    
    return f"УСПЕХ! Восстановлено машин: {len(cars_to_save)}. Проверь программу!"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
