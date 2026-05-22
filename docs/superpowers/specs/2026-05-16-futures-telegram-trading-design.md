# 텔레그램 신호 기반 해외선물 자동매매 시스템 설계

**날짜**: 2026-05-16  
**프로젝트**: hanstockauto  
**목표**: 텔레그램 신호 수집 → 모의계좌 성과 검증 → 실계좌 자동매매

---

## 1. 개요

텔레그램 채널에서 실시간으로 해외선물(나스닥 MNQ/NQ) 신호를 수집하여, 내부 Mock Simulator와 KIS 모의계좌에서 동시에 검증한다. 대시보드에서 성과를 확인한 후 수동으로 실계좌(KIS 해외선물 + Bybit)를 활성화한다. 모의계좌는 실계좌 전환 후에도 계속 병행 운용한다.

---

## 2. 아키텍처

```
[텔레그램 채널]
    │ Telethon (API ID/Hash)
    ▼
[poll.py - 신호 폴링] ──→ [parser.py - 신호 파싱 + 계약수]
                                    │
                              [db.py - SQLite 저장]
                                    │
                    FuturesExecutor.execute(signal)
                    ├── MockSimulator          # 항상 실행
                    ├── KISFuturesAPI(demo=True) # 항상 실행
                    └── [live_trading_enabled 시]
                            ├── KISFuturesAPI(demo=False)
                            └── BybitTrader
                                    │
                        [통합 성과 대시보드]
```

---

## 3. 신호 실행 파이프라인

### 3.1 신호 수신 및 파싱

- Telethon으로 타겟 채널 실시간 모니터링
- `parser.py`에서 영문/한글 혼합 신호 파싱
- `FuturesSignal` 모델에 `qty: int = 1` 필드 추가
- 계약수 미명시 시 기본값 1계약

### 3.2 실행 상태 관리

`.runtime/executor_state.json`:
```json
{
  "mock_enabled": true,
  "kis_demo_enabled": true,
  "live_trading_enabled": false,
  "bybit_enabled": false,
  "default_qty": 1,
  "polling_interval_sec": 30
}
```

### 3.3 FuturesExecutor (신규: src/futures_signals/executor.py)

```python
class FuturesExecutor:
    def execute(signal: FuturesSignal):
        # 1. MockSimulator.open_position(signal)
        # 2. KISFuturesAPI(demo=True).place_order(signal)
        # 3. if live_trading_enabled:
        #      KISFuturesAPI(demo=False).place_order(signal)
        #      BybitTrader.place_order(signal)
    
    def close(signal_id: str, direction: str):
        # 포지션 청산 (전체 실행기)
```

---

## 4. KIS 해외선물 API (src/api/kis_futures_api.py)

### 4.1 모의/실계좌 환경 분리

```python
class KISFuturesAPI:
    def __init__(self, demo: bool = True):
        self.base_url = (
            "https://openapivts.koreainvestment.com:29443"  # 모의
            if demo else
            "https://openapi.koreainvestment.com:9443"      # 실전
        )
        self.app_key = env.KIS_FUTURES_DEMO_KEY if demo else env.KIS_FUTURES_REAL_KEY
```

### 4.2 주요 메서드

- `get_token()` - 토큰 발급 (모의/실계좌 별도 캐싱)
- `place_order(symbol, side, qty, price)` - 주문 제출
- `get_positions()` - 보유 포지션 조회
- `get_balance()` - 계좌 잔고/증거금 조회
- `get_executions()` - 체결 내역 조회

---

## 5. Telegram 인증 흐름

단계별 인증 (설정 탭에서 실행):
```
1. API ID/Hash 입력 → .env 저장
2. POST /api/futures-signals/collector/auth/start
   → Telethon이 SMS 인증 코드 발송
3. POST /api/futures-signals/collector/auth/verify {code: "12345"}
   → 세션 파일 생성
4. 이후 자동 폴링 시작
```

---

## 6. 대시보드 API 변경사항

### 신규 엔드포인트

```
GET  /api/futures-signals/executor/state      # 실행 상태 조회
PUT  /api/futures-signals/executor/state      # 스위치 ON/OFF
GET  /api/futures-signals/performance/mock    # Mock 성과
GET  /api/futures-signals/performance/paper   # KIS 모의 성과
GET  /api/futures-signals/performance/live    # 실계좌 성과
POST /api/futures-signals/collector/auth/start   # Telegram 인증 시작
POST /api/futures-signals/collector/auth/verify  # Telegram 인증 완료
```

---

## 7. 프론트엔드 탭 구조

```
개요 | 신호목록 | 모의성과 | 실계좌성과 | 설정
```

- **개요**: Telegram 연결 상태, 오늘 신호 수, 모의/실계좌 PnL 요약
- **신호목록**: 파싱된 신호 테이블 (심볼, 방향, 진입가, 손절, 익절, 계약수)
- **모의성과**: Mock + KIS 모의계좌 포지션/거래이력/PnL 차트
- **실계좌성과**: 실계좌 전환 스위치, KIS 실 + Bybit 성과
- **설정**: Telegram API 설정, 채널 목록, 기본 계약수, 폴링 간격

---

## 8. 파일 변경 목록

### 신규 생성
- `src/futures_signals/executor.py` - FuturesExecutor 클래스
- `.runtime/executor_state.json` - 실행 상태
- `web/templates/fragments/futures_tab_mock_performance.html`
- `web/templates/fragments/futures_tab_live_performance.html`

### 수정
- `src/futures_signals/models.py` - qty 필드 추가
- `src/futures_signals/parser.py` - 계약수 파싱 추가
- `src/futures_signals/poll.py` - executor 연동
- `src/api/kis_futures_api.py` - demo/real 환경 완성
- `src/dashboard.py` - 신규 API 엔드포인트
- `web/templates/futures_signals.html` - 탭 재구성
- `web/static/js/futures_signals.js` - 스위치 UI

### 통합/정리
- `signal_trader.py` → executor.py로 기능 흡수
- `bybit_auto_trade.py` → executor.py에서 호출

---

## 9. 환경변수 추가

```env
# KIS 해외선물 모의계좌
KIS_FUTURES_DEMO_KEY=
KIS_FUTURES_DEMO_SECRET=
KIS_FUTURES_DEMO_ACCOUNT=

# KIS 해외선물 실계좌
KIS_FUTURES_REAL_KEY=
KIS_FUTURES_REAL_SECRET=
KIS_FUTURES_REAL_ACCOUNT=

# Telegram
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_TARGET_CHANNELS=
```

---

## 10. 성공 기준

1. Telegram 설정 탭에서 API ID/Hash 입력 → 인증 → 신호 수집 작동
2. 신호 수신 시 Mock + KIS 모의계좌 동시 주문 실행
3. 대시보드에서 모의 성과(승률, PnL) 실시간 확인
4. 실계좌 스위치 ON → KIS 실계좌 + Bybit 자동 주문
5. 모의계좌는 실계좌 전환 후에도 계속 병행 운용
