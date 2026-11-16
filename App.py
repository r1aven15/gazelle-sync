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

# Глобальная переменная для токена
glonass_token = None

def get_glonass_token():
    """Авторизация в ГЛОНАСС и получение токена X-Auth"""
    global glonass_token
    if glonass_token:
        return glonass_token
    
    print("Авторизация в ГЛОНАСС...")
    url = f"{GLONASS_URL}/api/v3/auth/login"
    params = {"username": GLONASS_LOGIN, "password": GLONASS_PASSWORD}
    
    try:
        response = requests.post(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        glonass_token = data.get('AuthId')
        if glonass_token:
            print("Токен получен!")
            return glonass_token
        else:
            print(f"Ошибка: в ответе нет AuthId. Ответ: {data}")
            return None
    except Exception as e:
        print(f"Ошибка авторизации: {e}")
        return None

def fetch_vehicles(token):
    """Получение списка транспортных средств с пробегом"""
    print("Запрос списка машин...")
    url = f"{GLONASS_URL}/api/v3/vehicles/find"
    headers = {"X-Auth": token}
    # Ищем все объекты. В идеале нужно передать parentId, но попробуем без него.
    payload = {} 
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        vehicles = response.json()
        print(f"Получено машин: {len(vehicles)}")
        return vehicles
    except Exception as e:
        print(f"Ошибка получения списка машин: {e}")
        return []

@app.route('/')
def index():
    return "Сервер активен. Готов к синхронизации с ГЛОНАСС."

@app.route('/sync')
def sync():
    """Этот адрес будет вызывать UptimeRobot или мы вручную для проверки"""
    token = get_glonass_token()
    if not token:
        return "Ошибка: не удалось авторизоваться в ГЛОНАСС", 500
    
    vehicles = fetch_vehicles(token)
    
    # Тут будет логика сохранения в Firebase
    # Пока просто выведем данные, чтобы проверить, что они приходят
    if vehicles:
        # Пробуем сохранить в Firebase для теста (в отдельную коллекцию)
        if db:
            try:
                # Сохраняем сырой ответ, чтобы посмотреть структуру
                db.collection('glonass_debug').document('vehicles').set({'data': vehicles})
                print("Данные сохранены в Firebase для отладки.")
            except Exception as e:
                print(f"Ошибка сохранения в Firebase: {e}")
        
        return f"Успех! Получено {len(vehicles)} машин. Первая: {vehicles[0].get('name', 'Без имени') if vehicles else 'нет'}"
    else:
        return "Машины не найдены или ошибка запроса."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
