from flask import Flask
import os
import requests
import json
from datetime import datetime

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
    
    res = requests.post(f"{GLONASS_URL}/api/v3/vehicles/find", headers={"X-Auth": token}, json={})
    vehicles = res.json()
    target = next((v for v in vehicles if '445' in v.get('name', '')), vehicles[0] if vehicles else None)
    if not target: return "Машины не найдены"
    
    v_id = target.get('vehicleId')
    headers = {"X-Auth": token, "Content-Type": "application/json"}
    
    today = datetime.now().strftime('%Y-%m-%d')
    start_time = f"{today}T00:00:00.000Z"
    end_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')
    
    # СПИСОК ВСЕХ ВАРИАНТОВ ДЛЯ ТЕСТА
    tests = [
        # 1. Пробег (MoveStop) с большой буквы
        {"method": "POST", "url": "/api/v3/Reports/MoveStop", "payload": {"vehicleIds": [v_id], "from": start_time, "to": end_time, "timezone": 7}},
        # 2. Пробег (MoveStop) с маленькой буквы
        {"method": "POST", "url": "/api/v3/reports/movestop", "payload": {"vehicleIds": [v_id], "from": start_time, "to": end_time, "timezone": 7}},
        # 3. getlastdata с большой буквы
        {"method": "POST", "url": "/api/v3/Vehicles/GetLastData", "payload": {"vehicleIds": [v_id], "from": start_time, "to": end_time, "timezone": 7}},
        # 4. getlastdata с маленькой буквы
        {"method": "POST", "url": "/api/v3/vehicles/getlastdata", "payload": {"vehicleIds": [v_id], "from": start_time, "to": end_time, "timezone": 7}},
        # 5. getlastdata без дат (просто ID)
        {"method": "POST", "url": "/api/v3/vehicles/getlastdata", "payload": {"vehicleIds": [v_id]}},
        # 6. Отчет по топливу (Fuel) с большой буквы
        {"method": "POST", "url": "/api/v3/Reports/Fuel", "payload": {"vehicleIds": [v_id], "from": start_time, "to": end_time, "timezone": 7}}
    ]
    
    results = []
    
    for test in tests:
        url = f"{GLONASS_URL}{test['url']}"
        try:
            if test['method'] == "POST":
                r = requests.post(url, headers=headers, json=test['payload'], timeout=10)
            else:
                r = requests.get(url, headers=headers, timeout=10)
                
            if r.status_code == 200:
                # Если данные не пустые (не "Массив пуст")
                if "Массив пуст" not in r.text and len(r.text) > 50:
                    results.append(f"<b style='color:green'>УСПЕХ: {test['url']}</b><br><pre>{r.text[:1500]}</pre>")
                else:
                    results.append(f"<span style='color:orange'>Пусто: {test['url']}</span>")
            else:
                results.append(f"Ошибка {r.status_code}: {test['url']}")
        except Exception as e:
            results.append(f"Сбой: {test['url']} ({e})")
            
    return "<h3>Результаты проверки:</h3>" + "<hr>".join(results)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
