import requests
import json
from src.config import config

# Token
url = 'https://openapivts.koreainvestment.com:29443/oauth2/tokenP'
body = {'grant_type': 'client_credentials', 'appkey': config.kistock_app_key, 'appsecret': config.kistock_app_secret}
r = requests.post(url, json=body, headers={'User-Agent': 'python-requests/2.31.0', 'Content-Type': 'application/json'}, timeout=10)
token = r.json().get('access_token')
print('Token:', token[:30] if token else 'FAIL')

# Balance API - try with product code 08 (overseas futures)
headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json',
    'appkey': config.kistock_app_key,
    'appsecret': config.kistock_app_secret,
    'tr_id': 'VOTFM1411R',
    'tr_cont': '',
    'custtype': 'P',
    'CANO': '60041778',
    'ACNT_PRDT_CD': '08'
}

params = {
    'CANO': '60041778',
    'ACNT_PRDT_CD': '08',
    'CRCY_CD': 'KRW',
    'INQR_DT': '20260505',
}

r2 = requests.get('https://openapivts.koreainvestment.com:29443/uapi/overseas-futureoption/v1/trading/inquire-deposit', headers=headers, params=params, timeout=15)
print('Status:', r2.status_code)
print('Response:', r2.text[:500])