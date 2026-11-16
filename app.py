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

def get_vehicle_daily_mileage(token, v_id):
    today = datetime.now().strftime('%Y-%m-%d')
    start_time = f"{today}T00:00:00.000Z"
    end_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')
    
    url = f"{GLONASS_URL}/api/v3/vehicles/mileageAndMotohours"
    payload = {"vehicleIds": [v_id], "from": start_time, "to": end_time, "timezone": 7}
    
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
    if not isinstance(vehicles, list): return "Ошибка: ГЛОНАСС вернул не список.", 500
    
    # Читаем текущий документ
    doc_ref = db.collection('gazelle_app').document('main_data')
    doc = doc_ref.get()
    
    if doc.exists:
        current_data = doc.to_dict()
        html_cars = current_data.get('cars', [])
    else:
        current_data = {}
        html_cars = []

    updated_count = 0
    created_count = 0
    log_msgs = []

    for g_vehicle in vehicles:
        g_name = g_vehicle.get('name', 'Без названия').strip()
        g_id = g_vehicle.get('vehicleId')
        
        # Ищем машину по имени
        existing_car = next((c for c in html_cars if c.get('name', '').strip() == g_name), None)
        
        # Получаем пробег за сегодня
        daily_mileage = get_vehicle_daily_mileage(token, g_id)
        time.sleep(1) 
        
        if existing_car:
            if daily_mileage > 0:
                if 'manualBaseMileage' not in existing_car:
                    existing_car['manualBaseMileage'] = existing_car.get('odometer', 0)
                new_odo = int(existing_car['manualBaseMileage'] + daily_mileage)
                existing_car['odometer'] = new_odo
                updated_count += 1
                log_msgs.append(f"{g_name}: +{daily_mileage} км (Итого: {new_odo})")
        else:
            # Если машины нет, создаем её
            new_car = {
                "id": f"glonass_{g_id}",
                "name": g_name,
                "glonassName": g_name,
                "odometer": int(daily_mileage),
                "manualBaseMileage": 0,
                "fuelLevel": 0,
                "vin": "", "model": g_vehicle.get('modelName', ''),
                "bodyType": "фургон", "fridgeModel": "",
                "insuranceFrom": "", "insuranceTo": "",
                "items": [
                    {"key":"oil", "label":"Масло двигателя", "lastMileage":0, "lastDate":"2026-11-16", "interval":10000, "intervalDays":0},
                    {"key":"air", "label":"Воздушный фильтр", "lastMileage":0, "lastDate":"2026-11-16", "interval":15000, "intervalDays":0},
                    {"key":"fuel", "label":"Топливный фильтр", "lastMileage":0, "lastDate":"2026-11-16", "interval":20000, "intervalDays":0},
                    {"key":"brakes", "label":"Тормозные колодки", "lastMileage":0, "lastDate":"2026-11-16", "interval":30000, "intervalDays":0},
                    {"key":"tires", "label":"Шиномонтаж", "lastMileage":0, "lastDate":"2026-11-16", "interval":20000, "intervalDays":0}
                ]
            }
            html_cars.append(new_car)
            created_count += 1
            log_msgs.append(f"Создана: {g_name}")

    # Жесткая перезапись всего документа
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

    return f"СИНХРОНИЗАЦИЯ: Создано {created_count}, Обновлено {updated_count}.<br>" + "<br>".join(log_msgs)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
