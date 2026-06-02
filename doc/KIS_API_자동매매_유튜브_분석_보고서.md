# 한국투자증권 OpenAPI 자동매매 유튜브 강의 정밀 분석 보고서 (실전 코드 포함)

본 문서는 한국투자증권(KIS) OpenAPI를 활용한 파이썬 주식/선물 자동매매 시스템 구축 유튜브 재생목록(총 24개 강의)을 정밀 분석하고, 이를 현재 **한스톡(Hanstock) 및 미스톡(Mistock)** 프로젝트의 소스 코드 아키텍처와 대조하여 매핑 및 남은 운영 점검 항목을 제시하는 통합 기술 보고서입니다.

유튜브 강의에서 다루는 주요 기능별 핵심 구현 포인트를 현재 코드 위치와 연결하고, 필요한 경우 참고용 파라미터 스크립트를 함께 정리했습니다. 실제 운영 기준은 본문에 연결된 프로젝트 코드와 테스트를 우선합니다.

---

## 📌 1. 전체 강의 요약 및 기술 분류

유튜브 재생목록(24개 동영상)에 포함된 핵심 강좌들을 6개의 기능적 모듈로 분류하고 요약한 구성표입니다.

| 분류 | 대상 강의 번호 (주제) | 핵심 기술 요소 | 한스톡/미스톡 연관 모듈 |
| :--- | :--- | :--- | :--- |
| **A. 기초 & 환경** | 1편 (장단점 분석)<br>2편 (개발환경 구축)<br>3편 (REST API & 토큰) | Anaconda/venv 설정, OAuth2 토큰 발급, API 초당 호출 스로틀링 보장, HTTP 공통 헤더 규격 | `src/config.py`<br>`src/api/kis_api.py`<br>`.env.example` |
| **B. 국내 주식 REST** | 4편 (주요 TR 1 - 시세/잔고)<br>5편 (주요 TR 2 - 일봉)<br>6편 (현금 지정가/시장가 주문)<br>7편 (정정/취소 주문)<br>22편 (대체거래소 NXT 대응) | 국내주식 시세/일봉 차트 조회, 잔고/예수금 파싱, 주문 해시키(Hashkey) 발급, NXT 대체거래소 다중 호가 대응 | `src/kis_client.py`<br>`src/trader.py`<br>`src/strategy/seven_split.py` |
| **C. 해외 주식 REST** | 8편 (해외 기본 TR - 시세/잔고)<br>9편 (해외 지정가 매수/매도)<br>10편 (해외 정정/취소 주문)<br>24편 (미국 자동매매 실습) | 해외주식 잔고/예수금 필드 파싱, 미국 거래소(NASD/NYSE) 매핑, 해외 주문 TR 연동, yfinance 시세-주문 통합 데몬 | `src/mistock/config.py`<br>`src/mistock/trader.py`<br>`src/mistock/strategy.py` |
| **D. 웹소켓 실시간** | 11편 (국내 실시간 체결/호가)<br>12편 (국내 실시간 주문/체결 통보)<br>13편 (해외 실시간 체결 데이터)<br>14편 (해외 실시간 체결 통보) | WebSocket 프로토콜 프레임 파싱, 실시간 스트리밍 시세 등록, 멀티스레드 비동기 통신 대기, 실시간 체결 알림 | `src/api/kis_websocket.py`<br>`src/dashboard/routes/settings.py` |
| **E. 시스템 설계** | 15~18편 (실시간 시스템 코드 리뷰)<br>19편 (보조지표 결합 매매 시스템) | SQLite 트랜잭션, Robust 예외 처리/재시도 루프, pandas 기술적 보조지표(RSI, MACD, 볼린저밴드) 계산 및 신호 | `src/scheduler.py`<br>`src/db/`<br>`src/strategy/indicators.py` |
| **F. 고급 연동 기능** | 20편 (국내 조건검색식 연동)<br>21편 (해외 조건검색식 연동)<br>23편 (선물옵션 API 가이드) | HTS 조건검색식 동적 호출 API, 선물옵션 계좌/잔고 조회 및 매매 주문 TR 송수신 | `src/api/kis_futures_api.py`<br>`src/futures_signals/` |

---

## 🔍 2. 강의별 상세 분석 및 코드베이스 매핑

### [1~3편] 기초 및 토큰 인증 시스템
*   **핵심 내용**: KIS API의 장단점(무료 무제한 실시간 시세 vs 엄격한 초당 호출 제한), OAuth2 토큰 발급 및 24시간 주기 갱신 로직, 그리고 REST API 공통 규격 분석.
*   **한스톡/미스톡 설계 정합성**:
    *   **Rate Limit 스로틀러**: KIS의 강한 스로틀링 제한(`EGW00201` 등 초당 API 요청 위반 에러)을 피하기 위해, `_KIS_THROTTLE_LOCK`, `_KIS_MIN_INTERVAL`, `_kis_order_throttle()` 기반 최소 호출 간격 보장 로직을 `src/api/kis_api.py` 및 `src/trader.py`에 배치했습니다.
    *   **토큰 자동 갱신 및 캐싱**: 24시간 만료 주기를 가진 토큰을 파일 기반으로 캐싱하여 불필요한 인증 요청을 방지하는 로직이 `TokenCacheEntry`, `KISClient._load_or_fetch_token()`, `trader.KIStockAPI._load_or_fetch_token()`에 구현되어 있습니다.

### [4~7편] 국내 주식 REST API 트레이딩
*   **핵심 내용**: 국내 주식 현재가(`FHKST01010100`), 잔고 조회(`VTTC8434R`/`TTTC8434R`), 지정가/시장가 현금 주문(`VTTC0802U`/`TTTC0802U`), 그리고 NXT 대체거래소 대응.
*   **한스톡/미스톡 설계 정합성**:
    *   **잔고 및 시세 파싱**: `src/kis_client.py`의 `get_balance()`와 `get_quote()`가 잔고/시세 TR 구조를 따르며, 대시보드 파싱 계층에서 예수금, 평가금액, 손익 필드를 정규화합니다.
    *   **해시키(Hashkey) 보안 전송**: POST 주문 시 본문 데이터 보안을 위해 `/uapi/hashkey`를 경유해 헤더에 해시키를 실어 보내는 `create_hashkey()` 및 `KIStockAPI._hashkey()` 구조가 국내/해외 주문 경로에 적용되어 있습니다.

### [8~10편, 24편] 해외 주식 REST API 자동매매
*   **핵심 내용**: 해외 주식 현재가(`HHDFS00000300`), 체결기준 잔고(`VTRP6504R`/`CTRP6504R`), 지정가 매수/매도 주문(`VTTT1002U`/`JTTT1002U` 등), `yfinance` 시세-KIS 주문 통합 자동매매 스크립트 제작.
*   **한스톡/미스톡 설계 정합성**:
    *   미스톡은 로컬 SQLite 가상거래(`paper`)뿐 아니라 KIS OpenAPI 미국주식 모의/실전 계좌 주문 경로를 사용할 수 있도록 `src/mistock/trader.py`와 `src/kis_client.py`를 연결했습니다.
    *   `src/kis_client.py`에 `get_overseas_balance()`, `get_overseas_quote()`, `place_overseas_order()`를 추가하여 해외거래소 코드(`OVRS_EXCG_CD`) 지정 및 지정가 매매 신호 전송 구조를 확립했습니다. NASDAQ 기본값 외에 `MISTOCK_EXCHANGE_MAP`으로 NYSE/AMEX 등 명시 매핑도 지원합니다.
    *   `src/mistock/trader.py`는 `MISTOCK_TRADING_ENV` 변수가 `demo`나 `real`일 때 KIS API와 결합하여 실제 잔고 및 예수금(`frcr_dncl_amt`) 정보를 불러오고 주문을 전송하도록 모듈 라우팅을 매끄럽게 처리했습니다.

### [11~14편] WebSocket 실시간 데이터 통신
*   **핵심 내용**: 웹소켓을 통한 실시간 시세 체결/호가 데이터 획득 및 계좌 실시간 주문 접수/체결 통보 처리.
*   **한스톡/미스톡 설계 정합성**:
    *   현재 우리 코드베이스는 안정적인 **REST API 기반의 분/일 단위 스케줄러 폴링 시스템(`src/scheduler.py`)**을 기본 실행 축으로 유지합니다.
    *   동시에 `src/api/kis_websocket.py`에 KIS 실시간 주문체결 통보 웹소켓 클라이언트를 구현했습니다. Approval Key 발급, 자동 재연결, 주문체결 평문 프레임 파싱, 체결 이벤트 Slack 알림 전송을 포함합니다.
    *   대시보드 운영 API(`/api/kis/websocket/status`, `/api/kis/websocket/start`, `/api/kis/websocket/stop`)를 통해 웹소켓 데몬을 제어할 수 있으며, `KIS_WEBSOCKET_ENABLED=true`이면 서버 시작 시 자동 구동할 수 있습니다.

### [15~19편] 아키텍처 설계 및 보조지표 결합 매매 데몬
*   **핵심 내용**: 무한 루프 기반의 안정적인 백그라운드 트레이더 데몬 설계, pandas를 활용한 RSI, MACD, 볼린저 밴드 지표 생성 및 매매 신호 생성.
*   **한스톡/미스톡 설계 정합성**:
    *   **보조지표 연동**: 우리 프로젝트의 `src/strategy/indicators.py` 및 `src/mistock/strategy.py`는 yfinance 및 KIS 시세 차트에서 `calc_rsi`, `calc_macd`, `calc_bollinger`를 도출하고 스코어를 합산하여 의사결정을 내리는데, 이는 19편의 기술적 지표 필터링 시스템을 기업형 아키텍처 수준으로 정교화하여 구현한 형태입니다.
    *   **데몬 에러 예외 처리**: API 장애 발생 시 크래시로 프로세스가 죽지 않도록 `tenacity` 라이브러리 기반 재시도와 Slack 오류 알림 경로를 둡니다. 운영 안정성은 전체 테스트와 모의투자 리허설로 계속 확인해야 합니다.

### [20~23편] 선물옵션 및 고급 동적 종목 매수 기능
*   **핵심 내용**: HTS 조건 검색식 API 연동, 대체거래소 대응, 선물옵션 매매 연동.
*   **한스톡/미스톡 설계 정합성**:
    *   **조건검색식 연동 확보**: `src/kis_client.py`, `src/api/kis_api.py`, `src/trader.py`에 HTS 조건검색식 목록/결과 조회 API가 구현되어 있습니다. `KIS_CONDITION_SEARCH_ENABLED=true`, `KIS_CONDITION_USER_ID`, `KIS_CONDITION_SEQ`, `KIS_CONDITION_NAME`을 설정하면 `build_scan_universe()`가 조건검색식 결과를 매수 후보 스캔 1순위 유니버스로 사용합니다.
    *   **선물옵션 연동 확보**: 텔레그램 메신저로 수신되는 시그널을 해석해 선물 주문 경로로 연결하는 **해외선물 전용 모듈(`src/api/kis_futures_api.py` 및 `src/futures_signals/`)**을 갖추고 있습니다. 실거래 투입 전에는 모의계좌 리허설과 주문 로그 대조가 필요합니다.

---

## 📈 3. 구현 완료도 및 운영 체크리스트

유튜브 강의 기반 기능은 REST 자동매매, 미스톡 해외주식 주문, 웹소켓 체결통보, 조건검색식 유니버스 반영까지 코드와 테스트 기준으로 목표 범위가 닫힌 상태입니다. 다만 실제 계좌/HTS/조건검색식 값으로 운영 리허설을 통과해야 실전 준비 완료로 판단합니다.

| 영역 | 구현 상태 | 핵심 근거 |
| :--- | :--- | :--- |
| OAuth2 토큰/공통 헤더 | 완료 | `src/kis_client.py`의 토큰 캐시 및 헤더 생성, `tests/test_kis_client.py` |
| 국내주식 REST 잔고/시세/일봉/주문 | 완료 | `src/trader.py`, `src/api/kis_api.py`, 주문 해시키 전송 테스트 |
| 해외주식 REST 잔고/시세/주문 | 완료 | `get_overseas_balance()`, `get_overseas_quote()`, `place_overseas_order()` |
| 해외주식 거래소 매핑 | 완료 | `MISTOCK_EXCHANGE_MAP` 및 `심볼=거래소` 명시 매핑 |
| 웹소켓 실시간 체결통보 | 완료 | `KISWebSocketClient`, Slack 체결 알림, 대시보드 start/stop/status API |
| 조건검색식 유니버스 | 완료 | 조건검색식 조회 API 및 `build_scan_universe()` 우선 반영 |
| 선물옵션 API/시그널 집행 | 완료 | `src/api/kis_futures_api.py`, `src/futures_signals/` |

운영 전 점검 항목:

1. `.env`에 KIS 계좌, HTS ID, 조건검색식 번호/이름을 실제 값으로 설정합니다.
2. 실전 주문은 `TRADING_ENV=real`, `DRY_RUN=false`, `ENABLE_LIVE_TRADING=true`가 모두 맞을 때만 활성화합니다.
3. 웹소켓은 `KIS_WEBSOCKET_ENABLED=true` 설정 후 `/api/kis/websocket/status`로 구동 상태를 확인합니다.
4. 조건검색식은 `/api/kis/condition-search/result`로 종목 수신을 확인한 뒤 자동 스캔에 투입합니다.

---

## 📈 4. 시스템 고도화를 위한 향후 발전 로드맵

유튜브 재생목록 범위는 구현 완료 상태입니다. 이후 과제는 기능 구현이 아니라 운영 품질과 관측성 강화를 위한 고도화입니다.

1.  **운영 모니터링 강화**: 웹소켓 재연결 횟수, 마지막 체결통보 수신 시각, 조건검색식 조회 성공/실패 카운트를 대시보드에 표시합니다.
2.  **브로커 응답 리플레이 검증**: KIS 실계좌/모의계좌 응답 샘플을 고정 fixture로 보관하여 주문/잔고 파싱 회귀 테스트를 강화합니다.
3.  **실거래 전 리허설 자동화**: `DRY_RUN=true` 상태에서 주문 후보, 승인, 주문 payload, 해시키 생성까지 리허설 결과를 한 번에 점검하는 도구를 추가합니다.

---

## 💻 5. 참고용 핵심 소스 코드 & 스크립트

아래 코드는 유튜브 강의의 화면 구성과 핵심 파라미터를 이해하기 위한 참고용 스크립트입니다. 현재 프로젝트의 운영 코드는 `src/kis_client.py`, `src/trader.py`, `src/api/kis_websocket.py`, `src/dashboard/routes/settings.py`를 우선 확인해야 합니다.

### ① 공통 OAuth2 토큰 발급 및 REST API 호출 뼈대
초당 호출 에러(`EGW00201`)를 방지하는 스로틀링(Throttling) 및 토큰 갱신 로직이 완비된 REST 통신 기본 스크립트입니다.

```python
import time
import requests
from datetime import datetime, timedelta

class KISRestBase:
    def __init__(self, app_key: str, app_secret: str, base_url: str = "https://openapivts.koreainvestment.com:29443"):
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = base_url
        self.token = None
        self.token_expired_at = datetime.now()
        
    def get_access_token(self):
        """[3편 구현] OAuth2 토큰 발급 및 자동 갱신"""
        if self.token and datetime.now() < self.token_expired_at:
            return self.token
            
        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        # 초당 호출 제한 방지를 위한 안전 간격
        time.sleep(1.0)
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        self.token = data["access_token"]
        # 안전하게 23시간 후 만료로 계산
        self.token_expired_at = datetime.now() + timedelta(hours=23)
        return self.token

    def get_headers(self, tr_id: str) -> dict:
        """[3편 구현] 공통 요청 헤더 생성"""
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }
```

### ② 해외주식(미국주식) 지정가 주문 전송 스크립트
거래소 코드(`NASD`/`NYSE`) 판별 기능과 KIS 해외주식 매수/매도 주문 파라미터가 최적화된 지정가 주문 전송 함수입니다.

```python
    def place_us_order(self, account_no: str, symbol: str, action: str, price: float, qty: int, is_demo: bool = True) -> dict:
        """[9편/24편 구현] 미국주식 지정가 주문 전송"""
        # 1. TR ID 매핑
        if is_demo:
            tr_id = "VTTT1002U" if action == "buy" else "VTTT1006U"
        else:
            tr_id = "JTTT1002U" if action == "buy" else "JTTT1006U"
            
        # 2. 해외 거래소 매핑 (NASDAQ: NASD, NYSE: NYSE, AMEX: AMEX)
        # 운영 코드에서는 MISTOCK_EXCHANGE_MAP 또는 "NYSE:BRK.B" 같은 접두어를 우선 사용합니다.
        exchange_code = "NASD"
        
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/order"
        body = {
            "CANO": account_no[:8],
            "ACNT_PRDT_CD": account_no[8:] if len(account_no) > 8 else "01",
            "OVRS_EXCG_CD": exchange_code,
            "PDNO": symbol.upper().strip(),
            "ORD_DVSN": "00",  # "00" = 지정가
            "ORD_QTY": str(int(qty)),
            "ORD_UNPR": f"{price:.2f}"  # 소수점 둘째자리까지 단가 포맷팅
        }
        
        headers = self.get_headers(tr_id)
        # 해시키(Hashkey) 생성
        hash_res = requests.post(
            f"{self.base_url}/uapi/hashkey", 
            headers={"content-type": "application/json", "appkey": self.app_key, "appsecret": self.app_secret},
            json=body
        )
        if hash_res.status_code == 200:
            headers["hashkey"] = hash_res.json().get("HASH")

        # 스로틀링 대기
        time.sleep(1.5)
        response = requests.post(url, headers=headers, json=body, timeout=15)
        return response.json()
```

### ③ 실시간 웹소켓(WebSocket) 데이터 수신 멀티스레드 구현체
11편~14편에서 설명되는 KIS 웹소켓 서버를 통해 실시간 호가/체결 데이터 및 계좌 체결 통보를 상시 수신하는 독립 구동형 모듈입니다.

```python
import json
import threading
import websocket

class KISWebSocketClient(threading.Thread):
    """[11~14편 구현] KIS 실시간 시세 및 체결 알림 웹소켓 클라이언트"""
    def __init__(self, app_key: str, app_secret: str, approval_key: str = None, is_demo: bool = True):
        super().__init__()
        self.app_key = app_key
        self.app_secret = app_secret
        self.approval_key = approval_key  # 웹소켓 접속용 별도 Approval Key
        self.url = "wss://ops.koreainvestment.com:3100" if is_demo else "wss://ops.koreainvestment.com:2100"
        self.ws = None
        self.running = False
        
    def get_approval_key(self) -> str:
        """웹소켓 등록용 실시간 Approval Key 발급 (REST 경유)"""
        if self.approval_key:
            return self.approval_key
        url = "https://openapi.koreainvestment.com:9443/uapi/token/approval"
        payload = {"grant_type": "client_credentials", "appid": self.app_key, "secretkey": self.app_secret}
        res = requests.post(url, json=payload, timeout=10)
        self.approval_key = res.json()["approval_key"]
        return self.approval_key

    def run(self):
        self.running = True
        self.ws = websocket.WebSocketApp(
            self.url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        self.ws.run_forever()

    def on_open(self, ws):
        print("[WS] Connection Opened. Sending subscriptions...")
        self.subscribe("H0STCNT0", "005930") # 삼성전자 실시간 체결 등록 (11편)
        
    def subscribe(self, custtype: str, symbol: str):
        """특정 TR ID와 종목코드 실시간 시세 구독"""
        payload = {
            "header": {
                "approval_key": self.get_approval_key(),
                "custtype": "P",
                "tr_type": "1", # "1" = 등록, "2" = 해제
                "content-type": "utf-8"
            },
            "body": {
                "input": {
                    "tr_id": custtype,
                    "tr_key": symbol
                }
            }
        }
        self.ws.send(json.dumps(payload))

    def on_message(self, ws, message):
        """수신된 실시간 프레임 파싱"""
        if message.startswith("0") or message.startswith("1"):
            # 실시간 체결/호가 평문 데이터 파싱
            parts = message.split("|")
            tr_id = parts[1]
            data_count = int(parts[2])
            raw_data = parts[3]
            print(f"[WS RECEIVE] TR_ID={tr_id}, Data Count={data_count}, Raw={raw_data[:100]}...")
        else:
            # 핑퐁 제어 및 응답 메시지 (JSON)
            data = json.loads(message)
            if data.get("header", {}).get("tr_id") == "PING":
                # PING 수신 시 PONG 응답 전송해 커넥션 유지
                self.ws.send(json.dumps({"header": {"tr_id": "PONG"}}))
                
    def on_error(self, ws, error):
        print(f"[WS ERROR] {error}")
        
    def on_close(self, ws, close_status_code, close_msg):
        print("[WS CLOSED]")
        self.running = False
        
    def stop(self):
        if self.ws:
            self.ws.close()
```

### ④ HTS 사용자 설정 조건식(조건검색) 실시간 연동 스크립트
HTS(영웅문 또는 한국투자증권 eFriend)에서 직접 마우스로 발굴한 정교한 조건검색식 결과를 파이썬으로 동적 추출해 오는 코드입니다.

```python
    def get_condition_load_list(self) -> list:
        """[20~21편 구현] HTS에 등록된 나의 조건식 목록 가져오기"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-condition-search"
        headers = self.get_headers("HHKST03900400") # 조건식 리스트 조회용 TR
        # 조건식 조회를 위한 고유 헤더 및 파라미터 구성
        params = {
            "user_id": "HTS_아이디_입력",
            "seq": "0"
        }
        time.sleep(1.0)
        res = requests.get(url, headers=headers, params=params, timeout=10)
        res.raise_for_status()
        # 등록된 조건명과 일련번호 배열 반환
        return res.json().get("output", [])

    def get_condition_search_result(self, condition_no: str, condition_name: str) -> list[str]:
        """[20~21편 구현] 특정 조건식에 매칭된 실시간 종목코드 목록 추출"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-condition-search-result"
        headers = self.get_headers("HHKST03900300") # 조건 검색 결과 조회용 TR
        params = {
            "user_id": "HTS_아이디_입력",
            "seq": condition_no,        # 조건식 일련번호
            "cond_nm": condition_name,  # 조건식 이름
        }
        time.sleep(1.0)
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code != 200 or res.json().get("rt_cd") != "0":
            return []
        
        # 포착된 종목 리스트 파싱하여 종목 코드 배열만 정제하여 반환
        output = res.json().get("output", [])
        return [row["code"].strip() for row in output if row.get("code")]
```

---

## 📋 6. 결론

본 유튜브 재생목록은 한국투자증권 Open API 트레이딩 시스템을 만드는 견고한 나침반 역할을 합니다. 우리는 해당 커리큘럼에서 다루는 REST 기반 주문 전송, 해시키 보안 전송, 해외주식 주문, 웹소켓 체결통보, 조건검색식 유니버스, 보조지표 매매 아키텍처를 프로젝트에 반영했습니다. 특히 **미국 주식(미스톡) 분야에 KIS OpenAPI 모의/실전 거래 연동을 적용하고, 국내주식 자동 스캔에 조건검색식 결과를 연결함으로써 재생목록이 제시하는 주요 연동 목표를 달성**했습니다.

이제 남은 과제는 신규 기능 구현보다 운영 검증입니다. `.env`의 실제 계좌/HTS/조건검색식 설정을 기준으로 모의투자 리허설을 실행하고, 웹소켓 체결통보와 조건검색식 결과 수신을 운영 로그와 Slack 알림으로 확인하면 실전 전환 준비가 완료됩니다.
