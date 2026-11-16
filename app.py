from flask import Flask
import os
import requests
import json
import time
import firebase_admin
from firebase_admin import credentials, firestore

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

def get_vehicle_details(token, vehicle_id):
    url = f"{GLONASS_URL}/api/v3/vehicles/{vehicle_id}"
    try:
        response = requests.get(url, headers={"X-Auth": token}, timeout=15)
        response.raise_for_status()
        return response.json(), None
    except Exception as e: return None, str(e)

# === ШПИОНСКАЯ СТРАНИЦА ===
@app.route('/debug')
def debug():
    token, err = get_glonass_token()
    if not token: return f"Ошибка токена: {err}", 500
    
    vehicles, err = fetch_vehicles(token)
    if err: return f"Ошибка машин: {err}", 500
    
    target_car = next((v for v in vehicles if '445' in v.get('name', '')), vehicles[0] if vehicles else None)
    if not target_car: return "Машины не найдены"
    
    details, err = get_vehicle_details(token, target_car.get('vehicleId'))
    if err: return f"Ошибка деталей: {err}", 500
    
    return f"<h1>Данные по машине: {target_car.get('name')}</h1><pre>{json.dumps(details, ensure_ascii=False, indent=2)}</pre>"

@app.route('/sync')
def sync():
    return "Сервер работает. Для синхронизации пока используем /debug."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
