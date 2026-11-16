from flask import Flask
import os
import requests
import json
import time
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

app = Flask(__name__)

# --- НАСТРОЙКА FIREBASE ---
firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
if firebase_creds_json:
    try:
        cred_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase успешно подключен!")
    except Exception as e:
        print(f"Ошибка подключения Firebase: {e}")

# --- НАСТРОЙКА ГЛОНАСС ---
GLONASS_LOGIN = os.environ.get('GLONASS_LOGIN')
GLONASS_PASSWORD = os.environ.get('GLONASS_PASSWORD')
GLONASS_URL = "https://hosting.glonasssoft.ru"

glonass_token = None
today_iso = datetime.now().strftime('%Y-%m-%d')

def get_glonass_token():
    global glonass_token
    if glonass_token: return glonass_token, None
    url = f"{GLONASS_URL}/api/v3/auth/login"
    payload = {"login": GLONASS_LOGIN, "password": GLONASS_PASSWORD}
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        glonass_token = response.json().get('AuthId')
        return glonass_token, None
    except Exception as e: return None, str(e)

def fetch_vehicles(token):
    url = f"{GLONASS_URL}/api/v3/vehicles/find"
    headers = {"X-Auth": token, "Content-Type": "application/json"}
    try:
        response = requests.post(url, headers=headers, json={}, timeout=15)
        response.raise_for_status()
        return response.json(), None
    except Exception as e: return [], str(e)

def get_vehicle_details(token, vehicle_id):
    url = f"{GLONASS_URL}/api/v3/vehicles/{vehicle_id}"
    headers = {"X-Auth": token}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json(), None
    except Exception as e: return None, str(e)

def get_default_items():
    return [
        {"key":"oil", "label":"Масло двигателя", "lastMileage":0, "lastDate":today_iso, "interval":10000, "intervalDays":0},
        {"key":"air", "label":"Воздушный фильтр", "lastMileage":0, "lastDate":today_iso, "interval":15000, "intervalDays":0},
        {"key":"fuel", "label":"Топливный фильтр", "lastMileage":0, "lastDate":today_iso, "interval":20000, "intervalDays":0},
        {"key":"brakes", "label":"Тормозные колодки", "lastMileage":0, "lastDate":today_iso, "interval":30000, "intervalDays":0},
        {"key":"tires", "label":"Шиномонтаж", "lastMileage":0, "lastDate":today_iso, "interval":20000, "intervalDays":0}
    ]

@app.route('/')
def index():
    return "Сервер активен."

@app.route('/sync')
def sync():
    token, auth_error = get_glonass_token()
    if not token: return f"ОШИБКА АВТОРИЗАЦИИ: {auth_error}", 500
    
    vehicles, fetch_error = fetch_vehicles(token)
    if fetch_error: return f"ОШИБКА МАШИН: {fetch_error}", 500
        
    if not vehicles: return "Список машин в ГЛОНАСС пуст."

    main_doc_ref = db.collection('gazelle_app').document('main_data')
    main_doc = main_doc_ref.get()
    
    if not main_doc.exists:
        return "Ошибка: Документ main_data не найден в Firebase. Сначала откройте HTML-программу."
    
    current_data = main_doc.to_dict()
    html_cars = current_data.get('cars', [])
    
    created_count = 0
    updated_count = 0
    log_msgs = []

    for g_vehicle in vehicles:
        g_name = g_vehicle.get('name', 'Без названия').strip()
        g_id = g_vehicle.get('vehicleId')
        g_model = g_vehicle.get('modelName', '')
        
        existing_car = next((c for c in html_cars if c.get('name', '').strip() == g_name), None)
        
        details, _ = get_vehicle_details(token, g_id)
        time.sleep(1) 
        
        g_mileage_km = 0
        if details:
            counters = details.get('counters', {})
            g_mileage_km = int(counters.get('mileage', 0.0) / 1000.0)

        if existing_car:
            if g_mileage_km > 0:
                if 'glonassBaseMileage' not in existing_car or existing_car['glonassBaseMileage'] is None:
                    existing_car['glonassBaseMileage'] = g_mileage_km
                    existing_car['manualBaseMileage'] = existing_car.get('odometer', 0)
                else:
                    diff = g_mileage_km - existing_car['glonassBaseMileage']
                    existing_car['odometer'] = existing_car['manualBaseMileage'] + diff

                updated_count += 1
                log_msgs.append(f"Обновлена: {g_name} -> {existing_car['odometer']} км (ГЛОНАСС: {g_mileage_km} км)")
        else:
            new_car = {
                "id": f"glonass_{g_id}",
                "name": g_name,
                "odometer": g_mileage_km,
                "glonassBaseMileage": g_mileage_km,
                "manualBaseMileage": 0,
                "vin": "",
                "model": g_model,
                "bodyType": "фургон",
                "fridgeModel": "",
                "insuranceFrom": "",
                "insuranceTo": "",
                "items": get_default_items()
            }
            html_cars.append(new_car)
            created_count += 1
            log_msgs.append(f"Создана: {g_name}")

    if created_count > 0 or updated_count > 0:
        main_doc_ref.update({'cars': html_cars})
        return f"УСПЕХ! Создано: {created_count}, Обновлено: {updated_count}.<br><br>" + "<br>".join(log_msgs)
    else:
        return "Синхронизация прошла. Все машины есть в базе, но пробег в ГЛОНАСС = 0."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
