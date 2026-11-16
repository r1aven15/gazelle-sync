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
    headers = {"X-Auth": token, "Content-Type": "application/json"}
    
    # Период: сегодня с 00:00 до сейчас
    today = datetime.now().strftime('%Y-%m-%d')
    start_time = f"{today}T00:00:00Z"
    end_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # Пробуем запросить историю сообщений (телеметрию)
    endpoints = [
        "/api/v3/messages",
        "/api/v3/messages/find",
        "/api/v3/messages/history"
    ]
    
    results = []
    
    for ep in endpoints:
        url = f"{GLONASS_URL}{ep}"
        payload = {
            "vehicleIds": [v_id],
            "startDate": start_time,
            "endDate": end_time
        }
        
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=15)
            if r.status_code == 200:
                return f"<h3>УСПЕХ! Найден рабочий метод: {ep}</h3><pre>{json.dumps(r.json(), ensure_ascii=False, indent=2)[:3000]}</pre>"
            else:
                results.append(f"{ep}: Код {r.status_code} ({r.text[:100]})")
        except Exception as e:
            results.append(f"{ep}: Ошибка {e}")
            
    return f"<h3>Проверка завершена</h3><p>" + "<br>".join(results) + "</p>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
