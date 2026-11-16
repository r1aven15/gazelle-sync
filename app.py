from flask import Flask
import os
import requests
import json
import firebase_admin
from firebase_admin import credentials, firestore

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
else:
    print("ВНИМАНИЕ: Ключ Firebase не настроен.")

# --- НАСТРОЙКА ГЛОНАСС ---
GLONASS_LOGIN = os.environ.get('GLONASS_LOGIN')
GLONASS_PASSWORD = os.environ.get('GLONASS_PASSWORD')
GLONASS_URL = "https://hosting.glonasssoft.ru"

glonass_token = None

def get_glonass_token():
    global glonass_token
    if glonass_token:
        return glonass_token, None
    
    url = f"{GLONASS_URL}/api/v3/auth/login"
    payload = {"login": GLONASS_LOGIN, "password": GLONASS_PASSWORD}
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        glonass_token = data.get('AuthId')
        return glonass_token, None
    except Exception as e:
        return None, str(e)

def fetch_vehicles(token):
    url = f"{GLONASS_URL}/api/v3/vehicles/find"
    headers = {"X-Auth": token, "Content-Type": "application/json"}
    try:
        response = requests.post(url, headers=headers, json={}, timeout=15)
        response.raise_for_status()
        return response.json(), None
    except Exception as e:
        return [], str(e)

def fetch_vehicle_mileage(token, vehicle_id):
    """Пытаемся получить пробег по ID машины"""
    # Используем метод получения данных датчиков (телеметрии)
    url = f"{GLONASS_URL}/api/v3/vehicles/{vehicle_id}/sensors"
    headers = {"X-Auth": token, "Content-Type": "application/json"}
    try:
        response = requests.post(url, headers=headers, json={}, timeout=15)
        # Если метод не сработал, вернем None
        if response.status_code != 200:
            return None, f"Код {response.status_code}"
        
        data = response.json()
        # Пытаемся найти пробег в ответе (обычно это поле mileage или can_mileage)
        mileage = None
        if isinstance(data, list):
            for sensor in data:
                if 'mileage' in sensor.get('name', '').lower():
                    mileage = sensor.get('value')
                    break
        elif isinstance(data, dict):
             mileage = data.get('mileage') or data.get('totalMileage')
             
        return mileage, None
    except Exception as e:
        return None, str(e)

@app.route('/')
def index():
    return "Сервер активен."

@app.route('/sync')
def sync():
    token, auth_error = get_glonass_token()
    if not token:
        return f"❌ ОШИБКА АВТОРИЗАЦИИ: {auth_error}", 500
    
    vehicles, fetch_error = fetch_vehicles(token)
    if fetch_error:
        return f"❌ ОШИБКА МАШИН: {fetch_error}", 500
        
    if vehicles:
        # Берем первую машину для теста
        first_vehicle = vehicles[0]
        vehicle_id = first_vehicle.get('vehicleId')
        vehicle_name = first_vehicle.get('name')
        
        # Запрашиваем пробег
        mileage, mileage_err = fetch_vehicle_mileage(token, vehicle_id)
        
        debug_info = {
            "vehicle_id": vehicle_id,
            "vehicle_name": vehicle_name,
            "mileage": mileage,
            "mileage_error": mileage_err
        }

        if db:
            try:
                db.collection('glonass_debug').document('test_mileage').set(debug_info)
                print("Данные сохранены в Firebase для отладки.")
            except Exception as e:
                print(f"Ошибка сохранения в Firebase: {e}")
        
        return f"✅ Тест пробега для {vehicle_name}: {mileage} (Ошибка: {mileage_err})"
    else:
        return "✅ Список машин пуст."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
