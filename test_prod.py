import requests
from src.config import config

url = 'https://openapivts.koreainvestment.com:29443/oauth2/tokenP'
body = {'grant_type': 'client_credentials', 'appkey': config.kistock_app_key, 'appsecret': config.kistock_app_secret}
r = requests.post(url, json=body, headers={'User-Agent': 'python-requests/2.31.0', 'Content-Type': 'application/json'}, timeout=10)
token = r.json().get('access_token')

# Try different product codes
for prod in ['08', '03', '01', '00']:
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'appkey': config.kistock_app_key,
        'appsecret': config.kistock_app_secret,
        'tr_id': 'VOTFM1411R',
        'tr_cont': '',
        'custtype': 'P',
        'CANO': '60041778',
        'ACNT_PRDT_CD': prod
    }
    params = {'CANO': '60041778', 'ACNT_PRDT_CD': prod, 'CRCY_CD': 'KRW', 'INQR_DT': '20260505'}
    r2 = requests.get('https://openapivts.koreainvestment.com:29443/uapi/overseas-futureoption/v1/trading/inquire-deposit', headers=headers, params=params, timeout=15)
    print(f'Product {prod}: {r2.status_code} - {r2.text[:100]}')