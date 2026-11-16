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
    """Авторизация в ГЛОНАСС."""
    global glonass_token
    if glonass_token:
        return glonass_token, None
    
    print("--- ПОПЫТКА АВТОРИЗАЦИИ ---")
    
    # --- ОТЛАДКА: Выводим в логи, видит ли сервер переменные ---
    print(f"DEBUG: Логин из настроек = {GLONASS_LOGIN}")
    print(f"DEBUG: Пароль из настроек = {GLONASS_PASSWORD}")
    # -----------------------------------------------------------

    url = f"{GLONASS_URL}/api/v3/auth/login"
    params = {"username": GLONASS_LOGIN, "password": GLONASS_PASSWORD}
    
    try:
        response = requests.post(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        glonass_token = data.get('AuthId')
        
        if glonass_token:
            print("УСПЕХ: Токен получен!")
            return glonass_token, None
        else:
            error_msg = f"В ответе нет поля AuthId. Ответ сервера: {data}"
            print(error_msg)
            return None, error_msg
            
    except requests.exceptions.RequestException as e:
        error_msg = f"Сетевая ошибка: {e}"
        if hasattr(e, 'response') and e.response is not None:
            error_msg += f" | Код: {e.response.status_code} | Текст: {e.response.text}"
        print(error_msg)
        return None, error_msg

def fetch_vehicles(token):
    """Получение списка машин."""
    print("Запрос списка машин...")
    url = f"{GLONASS_URL}/api/v3/vehicles/find"
    headers = {"X-Auth": token, "Content-Type": "application/json"}
    payload = {} 
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        vehicles = response.json()
        print(f"Получено машин: {len(vehicles)}")
        return vehicles, None
    except Exception as e:
        error_msg = f"Ошибка запроса машин: {e}"
        if hasattr(e, 'response') and e.response is not None:
            error_msg += f" | Код: {e.response.status_code} | Текст: {e.response.text}"
        print(error_msg)
        return [], error_msg

@app.route('/')
def index():
    return "Сервер активен."

@app.route('/sync')
def sync():
    token, auth_error = get_glonass_token()
    if not token:
        return f"ОШИБКА АВТОРИЗАЦИИ: {auth_error}", 500
    
    vehicles, fetch_error = fetch_vehicles(token)
    if fetch_error:
        return f"ОШИБКА ПОЛУЧЕНИЯ МАШИН: {fetch_error}", 500
        
    if vehicles:
        if db:
            try:
                db.collection('glonass_debug').document('vehicles').set({'data': vehicles})
                print("Данные сохранены в Firebase для отладки.")
            except Exception as e:
                print(f"Ошибка сохранения в Firebase: {e}")
        
        first_car_name = vehicles[0].get('name', 'Без имени') if vehicles else 'нет'
        return f"Успех! Получено {len(vehicles)} машин. Первая: {first_car_name}"
    else:
        return "Успех, но список машин пуст."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
