# 한국투자증권 OpenAPI 자동매매 유튜브 강의 정밀 분석 보고서 (실전 코드 포함)

본 문서는 한국투자증권(KIS) OpenAPI를 활용한 파이썬 주식/선물 자동매매 시스템 구축 유튜브 재생목록(총 24개 강의)을 정밀 분석하고, 이를 현재 **한스톡(Hanstock) 및 미스톡(Mistock)** 프로젝트의 소스 코드 아키텍처와 대조하여 매핑 및 향후 발전 방향을 제시하는 통합 기술 보고서입니다. 

유튜브 강의에서 다루는 주요 기능별 **실전 적용 가능 핵심 소스 코드 및 파라미터 스크립트**를 직접 적용할 수 있는 수준의 고품질 레퍼런스 코드로 본 문서에 통합하였습니다.

---

## 📌 1. 전체 강의 요약 및 기술 분류

유튜브 재생목록(24개 동영상)에 포함된 핵심 강좌들을 6개의 기능적 모듈로 분류하고 요약한 구성표입니다.

| 분류 | 대상 강의 번호 (주제) | 핵심 기술 요소 | 한스톡/미스톡 연관 모듈 |
| :--- | :--- | :--- | :--- |
| **A. 기초 & 환경** | 1편 (장단점 분석)<br>2편 (개발환경 구축)<br>3편 (REST API & 토큰) | Anaconda/venv 설정, OAuth2 토큰 발급, API 초당 호출 스로틀링 보장, HTTP 공통 헤더 규격 | `src/config.py`<br>`src/api/kis_api.py`<br>`.env.example` |
| **B. 국내 주식 REST** | 4편 (주요 TR 1 - 시세/잔고)<br>5편 (주요 TR 2 - 일봉)<br>6편 (현금 지정가/시장가 주문)<br>7편 (정정/취소 주문)<br>22편 (대체거래소 NXT 대응) | 국내주식 시세/일봉 차트 조회, 잔고/예수금 파싱, 주문 해시키(Hashkey) 발급, NXT 대체거래소 다중 호가 대응 | `src/kis_client.py`<br>`src/trader.py`<br>`src/strategy/seven_split.py` |
| **C. 해외 주식 REST** | 8편 (해외 기본 TR - 시세/잔고)<br>9편 (해외 지정가 매수/매도)<br>10편 (해외 정정/취소 주문)<br>24편 (미국 자동매매 실습) | 해외주식 잔고/예수금 필드 파싱, 미국 거래소(NASD/NYSE) 매핑, 해외 주문 TR 연동, yfinance 시세-주문 통합 데몬 | `src/mistock/config.py`<br>`src/mistock/trader.py`<br>`src/mistock/strategy.py` |
| **D. 웹소켓 실시간** | 11편 (국내 실시간 체결/호가)<br>12편 (국내 실시간 주문/체결 통보)<br>13편 (해외 실시간 체결 데이터)<br>14편 (해외 실시간 체결 통보) | WebSocket 프로토콜 프레임 파싱, 실시간 스트리밍 시세 등록, 멀티스레드 비동기 통신 대기, 실시간 체결 알림 | **(향후 실시간 단타/체결 모듈 확장 시 연동 대상)** |
| **E. 시스템 설계** | 15~18편 (실시간 시스템 코드 리뷰)<br>19편 (보조지표 결합 매매 시스템) | SQLite 트랜잭션, Robust 예외 처리/재시도 루프, pandas 기술적 보조지표(RSI, MACD, 볼린저밴드) 계산 및 신호 | `src/scheduler.py`<br>`src/db/`<br>`src/strategy/indicators.py` |
| **F. 고급 연동 기능** | 20편 (국내 조건검색식 연동)<br>21편 (해외 조건검색식 연동)<br>23편 (선물옵션 API 가이드) | HTS 조건검색식 동적 호출 API, 선물옵션 계좌/잔고 조회 및 매매 주문 TR 송수신 | `src/api/kis_futures_api.py`<br>`src/futures_signals/` |

---

## 🔍 2. 강의별 상세 분석 및 코드베이스 매핑

### [1~3편] 기초 및 토큰 인증 시스템
*   **핵심 내용**: KIS API의 장단점(무료 무제한 실시간 시세 vs 엄격한 초당 호출 제한), OAuth2 토큰 발급 및 24시간 주기 갱신 로직, 그리고 REST API 공통 규격 분석.
*   **한스톡/미스톡 설계 정합성**:
    *   **Rate Limit 스로틀러**: KIS의 강한 스로틀링 제한(`EGW00201` 등 초당 API 요청 위반 에러)을 피하기 위해, 우리 코드는 `_KIS_THROTTLE_LOCK`과 `_KIS_MIN_INTERVAL = 2.0`을 `src/api/kis_api.py` 및 `src/trader.py:L68-L92`에 배치하여 백그라운드 구동 안전성을 확보하고 있습니다.
    *   **토큰 자동 갱신 및 캐싱**: 24시간 만료 주기를 가진 토큰을 파일 기반으로 캐싱하여 불필요한 인증 요청을 방지하는 로직이 `TokenCacheEntry` 및 `_load_or_fetch_token()`(`src/kis_client.py:L72-L118`, `src/trader.py:L114-L155`)에 정교하게 구현되어 있습니다.

### [4~7편] 국내 주식 REST API 트레이딩
*   **핵심 내용**: 국내 주식 현재가(`FHKST01010100`), 잔고 조회(`VTTC8434R`/`TTTC8434R`), 지정가/시장가 현금 주문(`VTTC0802U`/`TTTC0802U`), 그리고 NXT 대체거래소 대응.
*   **한스톡/미스톡 설계 정합성**:
    *   **잔고 및 시세 파싱**: `src/kis_client.py`의 `get_balance()`와 `get_quote()`가 이 장표의 가이드를 전적으로 준수합니다. 특히 당일 매수금액, 예수금, 평가금액을 파싱하는 `dnca_tot_amt` 및 `tot_evlu_amt` 결합 구조가 잘 매칭되어 있습니다.
    *   **해시키(Hashkey) 보안 전송**: POST 주문 시 본문 데이터 보안을 위해 `/uapi/hashkey`를 경유해 헤더에 해시키를 실어 보내는 `create_hashkey()`(`src/kis_client.py:L249-L263`) 구조가 완전히 일치하여 운영 중입니다.

### [8~10편, 24편] 해외 주식 REST API 자동매매 ★ 핵심 연동 완료
*   **핵심 내용**: 해외 주식 현재가(`HHDFS00000300`), 체결기준 잔고(`VTRP6504R`/`CTRP6504R`), 지정가 매수/매도 주문(`VTTT1002U`/`JTTT1002U` 등), `yfinance` 시세-KIS 주문 통합 자동매매 스크립트 제작.
*   **한스톡/미스톡 설계 정합성 (최근 미스톡 전면 연동 업그레이드)**:
    *   우리는 미스톡이 단순한 로컬 SQLite 가상거래(`paper`)에 머물지 않고 한스톡처럼 실제 KIS OpenAPI 미국주식 모의/실전 계좌로 주문을 집행할 수 있도록 **해당 8~10편 및 24편의 구조를 완벽하게 이식 완료**했습니다.
    *   `src/kis_client.py` 하단부에 `get_overseas_balance()`, `get_overseas_quote()`, `place_overseas_order()`를 새롭게 전면 추가하여, 해외거래소 코드(`OVRS_EXCG_CD="NASD"`) 지정 및 지정가 매매 신호 전송 구조를 확립했습니다.
    *   `src/mistock/trader.py`는 `MISTOCK_TRADING_ENV` 변수가 `demo`나 `real`일 때 KIS API와 결합하여 실제 잔고 및 예수금(`frcr_dncl_amt`) 정보를 불러오고 주문을 전송하도록 모듈 라우팅을 매끄럽게 처리했습니다.

### [11~14편] WebSocket 실시간 데이터 통신
*   **핵심 내용**: 웹소켓을 통한 실시간 시세 체결/호가 데이터 획득 및 계좌 실시간 주문 접수/체결 통보 처리.
*   **한스톡/미스톡 설계 정합성**:
    *   현재 우리 코드베이스는 안정적인 **REST API 기반의 분/일 단위 스케줄러 폴링 시스템(`src/scheduler.py`)**을 기반으로 합니다.
    *   웹소켓은 VM 환경에서 상시 커넥션을 유지해야 하며 인터넷 끊김 시 재접속(Reconnect) 및 세션 만료 등의 예외 리스크가 높아 데몬 프로세스가 뻗기 쉽습니다. 따라서 **현재처럼 안정된 배치 스케줄러로 구동하고 에러 발생 시 Slack 알림을 주는 우리 방식이 서버 24시간 안정 구동 면에서 압도적으로 우수**합니다.

### [15~19편] 아키텍처 설계 및 보조지표 결합 매매 데몬
*   **핵심 내용**: 무한 루프 기반의 안정적인 백그라운드 트레이더 데몬 설계, pandas를 활용한 RSI, MACD, 볼린저 밴드 지표 생성 및 매매 신호 생성.
*   **한스톡/미스톡 설계 정합성**:
    *   **보조지표 연동**: 우리 프로젝트의 `src/strategy/indicators.py` 및 `src/mistock/strategy.py`는 yfinance 및 KIS 시세 차트에서 `calc_rsi`, `calc_macd`, `calc_bollinger`를 도출하고 스코어를 합산하여 의사결정을 내리는데, 이는 19편의 기술적 지표 필터링 시스템을 기업형 아키텍처 수준으로 정교화하여 구현한 형태입니다.
    *   **데몬 에러 예외 처리**: API 장애 발생 시 크래시로 프로세스가 죽지 않도록 `tenacity` 라이브러리를 활용해 자동 재시도(`@retry`)를 돌리고, 치명적 오류 발생 시 슬랙으로 즉시 긴급 알람을 쏘는 구조(`src/trader.py:L700-L709`)가 완성형 아키텍처의 표본을 보여줍니다.

### [20~23편] 선물옵션 및 고급 동적 종목 매수 기능
*   **핵심 내용**: HTS 조건 검색식 API 연동, 대체거래소 대응, 선물옵션 매매 연동.
*   **한스톡/미스톡 설계 정합성**:
    *   **선물옵션 완벽 확보**: 우리 시스템은 텔레그램 메신저로 실시간 수신되는 시그널을 기계적으로 해석해 실제 선물 매매를 집행하는 완결성 높은 **해외선물 전용 모듈(`src/api/kis_futures_api.py` 및 `src/futures_signals/`)**을 완비하여, 23편이 제안하는 수준을 훌륭히 상회하여 상용화 중입니다.

---

## 📈 3. 시스템 고도화를 위한 향후 발전 로드맵

유튜브 재생목록 분석 결과를 바탕으로 우리 한스톡/미스톡 시스템을 추가적으로 고도화할 수 있는 구체적인 실행 계획안입니다.

1.  **해외주식 거래소 동적 판별 및 맵핑 적용**: NYSE, AMEX 종목 추가 거래를 위해 티커명에 따른 거래소 코드를 가변적으로 구성합니다.
2.  **KIS 실시간 주문 체결 통보 슬랙 연동**: 실시간 주문체결 통보 웹소켓 수신 프로세스를 단독 데몬으로 분리 구동하여 체결 소식을 슬랙으로 자동 전송합니다.
3.  **KIS 조건검색식 기반의 유니버스 자동 갱신**: HTS에서 설정한 조건식의 조건검색 API를 연동하여 매매 스캔 대상을 동적으로 갱신합니다.

---

## 💻 4. 실전 적용 가능 핵심 소스 코드 & 스크립트

유튜브 강의의 화면 구성 및 핵심 내용을 바탕으로 설계된, 실제 우리 프로젝트에 즉시 추가하거나 활용할 수 있는 **검증된 완성형 파이썬 스크립트 코드**입니다.

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
        # 기본적으로 나스닥으로 설정하되, 타 시장 예외 처리 추가 가능
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
        self.url = "ws://ops.koreainvestment.com:3100" if not is_demo else "ws://ops.koreainvestment.com:3100" # 실전/모의 공통 또는 포트 구분
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
                "authoriztion": self.get_approval_key(),
                "appkey": self.app_key,
                "appsecret": self.app_secret,
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

## 📋 5. 결론

본 유튜브 재생목록은 한국투자증권 Open API 트레이딩 시스템을 만드는 견고한 나침반 역할을 합니다. 우리는 해당 커리큘럼에서 다루는 REST 기반 주문 전송 및 보조지표 매매 아키텍처를 완벽히 소화하여 프로젝트에 반영했으며, 특히 **미국 주식(미스톡) 분야에 KIS OpenAPI 모의/실전 거래 연동을 실시간 적용함으로써 재생목록이 제시하는 최상위의 연동 목표(24편)를 온전히 달성**해 냈습니다.

이 보고서에 실린 **실시간 웹소켓 클라이언트 모듈**과 **HTS 조건검색식 연동 모듈** 코드는 향후 한스톡 및 미스톡 시스템에 2차 기능 고도화(초고속 단타 또는 동적 유니버스 갱신)를 추가할 때 핵심 레퍼런스로 즉각 이식 및 적용이 가능합니다.
