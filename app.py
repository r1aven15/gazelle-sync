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
    
    # Получаем ID машины
    res = requests.post(f"{GLONASS_URL}/api/v3/vehicles/find", headers={"X-Auth": token}, json={})
    vehicles = res.json()
    target = next((v for v in vehicles if '445' in v.get('name', '')), vehicles[0] if vehicles else None)
    if not target: return "Машины не найдены"
    
    v_id = target.get('vehicleId')
    headers = {"X-Auth": token, "Content-Type": "application/json"}
    
    # Период: сегодня с 00:00 до сейчас
    today = datetime.now().strftime('%Y-%m-%d')
    start_time = f"{today}T00:00:00.000Z"
    end_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')
    
    results = []
    
    # 1. ПРОБЕГ (mileageAndMotohours)
    url_mileage = f"{GLONASS_URL}/api/v3/vehicles/mileageAndMotohours"
    payload_mileage = {
        "vehicleIds": [v_id],
        "from": start_time,
        "to": end_time,
        "timezone": 7
    }
    try:
        r = requests.post(url_mileage, headers=headers, json=payload_mileage, timeout=15)
        results.append(f"<b>1. ПРОБЕГ (Код {r.status_code}):</b><br><pre>{r.text[:1000]}</pre>")
    except Exception as e:
        results.append(f"<b>1. ПРОБЕГ:</b> Ошибка {e}")

    # 2. ТОПЛИВО (getlastdata)
    url_fuel = f"{GLONASS_URL}/api/v3/vehicles/getlastdata"
    payload_fuel = {
        "vehicleIds": [v_id],
        "timezone": 7
    }
    try:
        r = requests.post(url_fuel, headers=headers, json=payload_fuel, timeout=15)
        results.append(f"<b>2. ТОПЛИВО (Код {r.status_code}):</b><br><pre>{r.text[:1000]}</pre>")
    except Exception as e:
        results.append(f"<b>2. ТОПЛИВО:</b> Ошибка {e}")
            
    return "<h3>Результаты проверки:</h3>" + "<hr>".join(results)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
