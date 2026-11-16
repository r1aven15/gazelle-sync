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
        glonass_token = response.json().get('AuthId')
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

def get_vehicle_details(token, vehicle_id):
    """Получаем полную информацию об объекте (там должен быть пробег)"""
    url = f"{GLONASS_URL}/api/v3/vehicles/{vehicle_id}"
    headers = {"X-Auth": token}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json(), None
    except Exception as e:
        return None, f"Код {e.response.status_code if hasattr(e, 'response') else '?'} | {e}"

@app.route('/sync')
def sync():
    token, auth_error = get_glonass_token()
    if not token:
        return f"❌ ОШИБКА АВТОРИЗАЦИИ: {auth_error}", 500
    
    vehicles, fetch_error = fetch_vehicles(token)
    if fetch_error:
        return f"❌ ОШИБКА МАШИН: {fetch_error}", 500
        
    if vehicles:
        first_vehicle = vehicles[0]
        vehicle_id = first_vehicle.get('vehicleId')
        vehicle_name = first_vehicle.get('name')
        
        # Запрашиваем детали по ID
        details, details_err = get_vehicle_details(token, vehicle_id)
        
        mileage_value = None
        if details:
            # Пытаемся достать пробег из разных возможных мест
            # Обычно это в counters -> mileage (в метрах)
            counters = details.get('counters', {})
            mileage_value = counters.get('mileage')
            if mileage_value is not None:
                mileage_value = mileage_value / 1000.0 # переводим метры в км
        
        debug_info = {
            "vehicle_name": vehicle_name,
            "mileage_km": mileage_value,
            "raw_details": details if details else details_err
        }

        if db:
            db.collection('glonass_debug').document('test_mileage').set(debug_info)
        
        return f"✅ Тест: {vehicle_name} | Пробег: {mileage_value} км | Ошибка: {details_err}"
    else:
        return "✅ Список машин пуст."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
