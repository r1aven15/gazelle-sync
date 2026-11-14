from flask import Flask
import os
import requests
import json
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

# --- НАСТРОЙКА FIREBASE ---
# Ключ Firebase мы добавим позже в настройках Render (в переменных окружения)
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
    print("ВНИМАНИЕ: Ключ Firebase не настроен. Данные не будут сохраняться.")

# --- НАСТРОЙКА ГЛОНАСС (ПОКА ЗАГЛУШКА) ---
GLONASS_LOGIN = os.environ.get('GLONASS_LOGIN', 'demo')
GLONASS_PASSWORD = os.environ.get('GLONASS_PASSWORD', 'demo')
GLONASS_URL = "https://hosting.glonasssoft.ru/api/v3"

def fetch_glonass_data():
    """
    Здесь будет реальный код запроса к ГЛОНАСС.
    Пока возвращает статус, чтобы мы могли проверить работу сервера.
    """
    print("Проверка связи с ГЛОНАСС...")
    return {"status": "success", "message": "Сервер работает, ждём реальные доступы"}

# --- ВЕБ-СЕРВЕР ДЛЯ UPTIMEROBOT ---
@app.route('/')
def index():
    """Этот адрес будет дёргать UptimeRobot, чтобы сервер не засыпал."""
    return "Сервер активен. Жду данные."

@app.route('/sync')
def sync():
    """Этот адрес будет вызывать синхронизацию."""
    result = fetch_glonass_data()
    return f"Синхронизация: {result['message']}"

if __name__ == '__main__':
    # Render передаёт порт через переменную окружения PORT
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)