import requests
from src.config import config

print("AppKey:", config.kistock_app_key[:20])
print("Account:", config.kistock_account)

# Step 1: Get token
url = 'https://openapivts.koreainvestment.com:29443/oauth2/tokenP'
body = {'grant_type': 'client_credentials', 'appkey': config.kistock_app_key, 'appsecret': config.kistock_app_secret}
headers = {'User-Agent': 'python-requests/2.31.0', 'Content-Type': 'application/json'}

print("Getting token...")
r = requests.post(url, json=body, headers=headers, timeout=10)
print("Token response:", r.status_code, r.text[:200])

if r.status_code == 200:
    token_data = r.json()
    token = token_data.get('access_token')
    print("Token obtained:", token[:50] if token else "None")
    
    # Step 2: Call API immediately with same token
    api_headers = {
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
    
    params = {'CANO': '60041778', 'ACNT_PRDT_CD': '08', 'CRCY_CD': 'KRW', 'INQR_DT': '20260505'}
    
    print("Calling API...")
    r2 = requests.get('https://openapivts.koreainvestment.com:29443/uapi/overseas-futureoption/v1/trading/inquire-deposit', headers=api_headers, params=params, timeout=15)
    print("API response:", r2.status_code, r2.text[:300])