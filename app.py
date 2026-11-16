from flask import Flask
import os
import requests
import json
from datetime import datetime, timedelta

app = Flask(__name__)

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

@app.route('/sync')
def sync():
    token, err = get_glonass_token()
    if not token: return f"Ошибка токена: {err}", 500
    
    # Получаем ID машины
    res = requests.post(f"{GLONASS_URL}/api/v3/vehicles/find", headers={"X-Auth": token}, json={})
    vehicles = res.json()
    target = next((v for v in vehicles if '445' in v.get('name', '')), vehicles[0] if vehicles else None)
    if not target: return "Машины не найдены"
    
    v_id = target.get('vehicleId')
    headers = {"X-Auth": token}
    
    results = []
    
    # Пробуем разные методы API
    methods_to_test = [
        ("/api/v3/vehicles/{id}/lastdata", "POST"),  # Последние данные (POST)
        ("/api/v3/vehicles/{id}/last", "GET"),       # Альтернативный метод
        ("/api/v3/vehicles/{id}/state", "GET"),      # Состояние
        ("/api/v3/vehicles/{id}/sensors/last", "GET") # Последние данные датчиков
    ]
    
    for path, method in methods_to_test:
        url = f"{GLONASS_URL}{path.format(id=v_id)}"
        try:
            if method == "POST":
                r = requests.post(url, headers=headers, json={}, timeout=10)
            else:
                r = requests.get(url, headers=headers, timeout=10)
                
            res_text = r.text[:500] + "..." if len(r.text) > 500 else r.text
            results.append(f"<b>{method} {path}</b><br>Код: {r.status_code}<br>Ответ: {res_text}<br><br>")
        except Exception as e:
            results.append(f"<b>{method} {path}</b><br>Ошибка: {e}<br><br>")
            
    return f"<h3>Тест методов для {target.get('name')}</h3>" + "".join(results)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
