import sys

code = '''import hashlib
import json
import threading
import time
from datetime import datetime, timedelta
import requests
from pathlib import Path

from src.config import config
from src.utils.logger import logger

HTTP = requests.Session()
HTTP.trust_env = False

_KIS_FUTURES_THROTTLE_LOCK = threading.Lock()
_KIS_FUTURES_LAST_CALL = 0.0
_KIS_FUTURES_MIN_INTERVAL = 2.0


def _kis_futures_throttle():
    global _KIS_FUTURES_LAST_CALL
    with _KIS_FUTURES_THROTTLE_LOCK:
        elapsed = time.monotonic() - _KIS_FUTURES_LAST_CALL
        if elapsed < _KIS_FUTURES_MIN_INTERVAL:
            time.sleep(_KIS_FUTURES_MIN_INTERVAL - elapsed)
        _KIS_FUTURES_LAST_CALL = time.monotonic()


class KISFuturesAPI:
    TOKEN_CACHE = Path("data") / "kis_futures_token.json"

    def __init__(self, notify_errors=True):
        self.notify_errors = notify_errors
        self.base_url = "https://openapi.koreainvestment.com:9443" if config.trading_env == "real" else "https://openapivts.koreainvestment.com:29443"
        self.access_token = self._load_or_fetch_token()

    def _app_key_hash(self):
        return hashlib.sha256(config.kistock_app_key.encode("utf-8")).hexdigest()

    def _load_or_fetch_token(self):
        if self.TOKEN_CACHE.exists():
            try:
                cached = json.loads(self.TOKEN_CACHE.read_text(encoding="utf-8"))
                expires_at = datetime.fromisoformat(cached["expires_at"])
                if (
                    cached.get("trading_env") == config.trading_env
                    and cached.get("app_key_hash") == self._app_key_hash()
                    and expires_at > datetime.now() + timedelta(minutes=5)
                ):
                    return cached["token"]
            except Exception:
                pass
        return self._fetch_token()

    def _fetch_token(self):
        _kis_futures_throttle()
        url = f"{self.base_url}/oauth2/tokenP"
        body = {"grant_type": "client_credentials", "appkey": config.kistock_app_key, "appsecret": config.kistock_app_secret}
        try:
            r = HTTP.post(url, json=body, timeout=10)
            if r.status_code != 200:
                logger.error(f"Token fetch HTTP {r.status_code}: {r.text}")
                r.raise_for_status()
            data = r.json()
            token = data.get("access_token", "")
            expires_at = datetime.now() + timedelta(hours=23)
            self.TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
            self.TOKEN_CACHE.write_text(
                json.dumps({
                    "token": token,
                    "expires_at": expires_at.isoformat(),
                    "trading_env": config.trading_env,
                    "app_key_hash": self._app_key_hash(),
                }),
                encoding="utf-8",
            )
            return token
        except Exception as e:
            raise RuntimeError(f"KIS futures token fetch failed: {e}") from e

    def _get_account_code(self):
        account = config.kistock_account
        if len(account) == 10:
            return account[:8], account[8:]
        return account, "08"

    def _request(self, method, path, params=None, body=None, tr_id=""):
        _kis_futures_throttle()
        canoe, acnt_prdt_cd = self._get_account_code()
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "appkey": config.kistock_app_key,
            "appsecret": config.kistock_app_secret,
            "tr_id": tr_id,
            "tr_cont": "",
            "custtype": "P",
            "CANO": canoe,
            "ACNT_PRDT_CD": acnt_prdt_cd,
        }
        url = f"{self.base_url}{path}"
        try:
            if method == "GET":
                r = HTTP.get(url, headers=headers, params=params, timeout=15)
            else:
                r = HTTP.post(url, headers=headers, json=body, timeout=15)

            if r.status_code != 200:
                logger.error(f"KIS futures API error: {r.status_code} {r.text}")
                return {"rt_code": "99999", "rt_msg": f"HTTP {r.status_code}: {r.text}"}

            result = r.json()
            if result.get("rt_code") != "0":
                logger.warn(f"KIS futures API warning: {result.get('rt_msg', '')}")
            return result
        except Exception as e:
            logger.error(f"KIS futures API request failed: {e}")
            return {"rt_code": "99999", "rt_msg": str(e)}

    def get_balance(self):
        today = datetime.now().strftime("%Y%m%d")
        params = {
            "CANO": self._get_account_code()[0],
            "ACNT_PRDT_CD": self._get_account_code()[1],
            "CRCY_CD": "KRW",
            "INQR_DT": today,
        }
        result = self._request("GET", "/uapi/overseas-futureoption/v1/trading/inquire-deposit", params, tr_id="OTFM1411R")
        return result

    def get_positions(self):
        params = {
            "CCLD_NCCS_DVSN": "03",
            "SLL_BUY_DVSN_CD": "%%",
            "FUOP_DVSN": "00",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        result = self._request("GET", "/uapi/overseas-futureoption/v1/trading/inquire-ccld", params, tr_id="OTFM3116R")
        return result

    def get_daily_orders(self, start_date=None, end_date=None):
        if not start_date:
            start_date = datetime.now().strftime("%Y%m%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        params = {
            "STRT_DT": start_date,
            "END_DT": end_date,
            "FUOP_DVSN_CD": "00",
            "FM_PDGR_CD": "",
            "CRCY_CD": "%%%",
            "FM_ITEM_FTNG_YN": "N",
            "SLL_BUY_DVSN_CD": "%%",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        result = self._request("GET", "/uapi/overseas-futureoption/v1/trading/inquire-daily-ccld", params, tr_id="OTFM3122R")
        return result

    def place_order(self, symbol, order_type, qty, price="0"):
        canoe, acnt_prdt_cd = self._get_account_code()
        sll_buy_dvsn_cd = "02" if order_type in ["buy", "매수"] else "01"
        ord_pty_tp = "1" if price == "0" else "0"
        body = {
            "CANO": canoe,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "OVRS_FUTR_FX_PDNO": symbol,
            "SLL_BUY_DVSN_CD": sll_buy_dvsn_cd,
            "ORD_QTY": str(qty),
            "ORD_PRC": price,
            "ORD_TPTY_TP": ord_pty_tp,
            "ORD_SPLIT_TP": "0",
        }
        result = self._request("POST", "/uapi/overseas-futureoption/v1/trading/order", body=body, tr_id="OTFM2105R")
        return result

    def cancel_order(self, order_no):
        canoe, acnt_prdt_cd = self._get_account_code()
        body = {
            "CANO": canoe,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "ORD_ODNO": order_no,
        }
        result = self._request("POST", "/uapi/overseas-futureoption/v1/trading/cancel", body=body, tr_id="OTFM2107R")
        return result

    def get_current_price(self, symbol):
        params = {"SRS_CD": symbol}
        result = self._request("GET", "/uapi/overseas-futureoption/v1/quotations/inquire-price", params, tr_id="HHDFC55010000")
        return result
'''

with open('src/api/kis_futures_api.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('File written')