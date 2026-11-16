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
glonass_token = None
today_iso = datetime.now().strftime('%Y-%m-%d')

def get_glonass_token():
    global glonass_token
    if glonass_token: return glonass_token, None
    url = f"{GLONASS_URL}/api/v3/auth/login"
    try:
        response = requests.post(url, json={"login": GLONASS_LOGIN, "password": GLONASS_PASSWORD}, timeout=15)
        response.raise_for_status()
        glonass_token = response.json().get('AuthId')
        return glonass_token, None
    except Exception as e: return None, str(e)

def fetch_vehicles(token):
    url = f"{GLONASS_URL}/api/v3/vehicles/find"
    try:
        response = requests.post(url, headers={"X-Auth": token}, json={}, timeout=15)
        response.raise_for_status()
        return response.json(), None
    except Exception as e: return [], str(e)

def get_vehicle_last_data(token, vehicle_id):
    """Запрашиваем последние показания телеметрии (топливо, зажигание)"""
    url = f"{GLONASS_URL}/api/v3/vehicles/{vehicle_id}/lastdata"
    try:
        response = requests.get(url, headers={"X-Auth": token}, timeout=15)
        if response.status_code == 200:
            return response.json(), None
        else:
            return None, f"Код {response.status_code}"
    except Exception as e: return None, str(e)

def get_default_items():
    return [
        {"key":"oil", "label":"Масло двигателя", "lastMileage":0, "lastDate":today_iso, "interval":10000, "intervalDays":0},
        {"key":"air", "label":"Воздушный фильтр", "lastMileage":0, "lastDate":today_iso, "interval":15000, "intervalDays":0},
        {"key":"fuel", "label":"Топливный фильтр", "lastMileage":0, "lastDate":today_iso, "interval":20000, "intervalDays":0},
        {"key":"brakes", "label":"Тормозные колодки", "lastMileage":0, "lastDate":today_iso, "interval":30000, "intervalDays":0},
        {"key":"tires", "label":"Шиномонтаж", "lastMileage":0, "lastDate":today_iso, "interval":20000, "intervalDays":0}
    ]

@app.route('/sync')
def sync():
    token, auth_error = get_glonass_token()
    if not token: return f"ОШИБКА АВТОРИЗАЦИИ: {auth_error}", 500
    
    vehicles, fetch_error = fetch_vehicles(token)
    if fetch_error: return f"ОШИБКА МАШИН: {fetch_error}", 500
        
    if not vehicles: return "Список машин пуст."

    main_doc_ref = db.collection('gazelle_app').document('main_data')
    main_doc = main_doc_ref.get()
    
    if not main_doc.exists: return "Документ main_data не найден в Firebase."
    
    current_data = main_doc.to_dict()
    html_cars = current_data.get('cars', [])
    
    created_count = 0
    updated_count = 0
    log_msgs = []

    for g_vehicle in vehicles:
        g_name = g_vehicle.get('name', 'Без названия').strip()
        g_id = g_vehicle.get('vehicleId')
        
        # Ищем машину в программе
        existing_car = next((c for c in html_cars if c.get('glonassName', '').strip() == g_name or c.get('name', '').strip() == g_name), None)
        
        # Запрашиваем последние данные (топливо)
        last_data, _ = get_vehicle_last_data(token, g_id)
        time.sleep(1) 
        
        fuel_level = None
        if last_data:
            # Ищем датчик топлива flex_fuel1
            sensors = last_data.get('sensors', [])
            for s in sensors:
                if s.get('parameterName') == 'flex_fuel1':
                    # Берем значение из поля value (если есть)
                    fuel_level = s.get('value')
                    break

        if existing_car:
            if fuel_level is not None:
                existing_car['fuelLevel'] = fuel_level
                updated_count += 1
                log_msgs.append(f"Обновлена: {g_name} -> Топливо: {fuel_level} л")
        else:
            new_car = {
                "id": f"glonass_{g_id}",
                "name": g_name,
                "glonassName": g_name,
                "odometer": 0,
                "fuelLevel": fuel_level if fuel_level else 0,
                "vin": "", "model": g_vehicle.get('modelName', ''),
                "bodyType": "фургон", "fridgeModel": "",
                "insuranceFrom": "", "insuranceTo": "",
                "items": get_default_items()
            }
            html_cars.append(new_car)
            created_count += 1
            log_msgs.append(f"Создана: {g_name}")

    if created_count > 0 or updated_count > 0:
        main_doc_ref.update({'cars': html_cars})
        return f"УСПЕХ! Создано: {created_count}, Обновлено: {updated_count}.<br><br>" + "<br>".join(log_msgs)
    else:
        return "Синхронизация прошла. Данных для обновления нет."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
