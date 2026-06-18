# 미스톡 MACD+RSI 유튜브 전략 분석

## 1. 대상 영상

- URL: https://www.youtube.com/watch?v=a72BOk1yiAE
- 제목: The 90% Win Rate MACD + RSI Trading Strategy of a Top 1% Trader Who Turned $600 into $20 Million
- 확인일: 2026-06-18
- 자막 확인 결과:
  - 한국어 자동 생성 자막 제공
  - 자막 조각 수: 710개
  - 영상 길이: 약 26분 45초

주의: 자막 원문 전체를 그대로 저장하지 않는다. 영상 자막은 저작권 보호 대상일 수 있으므로, 이 문서는 수집 방법, 시간대별 요약, 전략 규칙, 미스톡 적용 방안만 정리한다.

## 2. 영상 내용을 모두 가져오는 방법

### 2.1. 1순위: `youtube-transcript-api`

이 영상은 한국어 자동자막이 공개되어 있어 `youtube-transcript-api`로 자막을 가져올 수 있다.

설치 확인:

```powershell
python -m pip show youtube-transcript-api
```

사용 가능한 자막 목록 확인:

```powershell
@'
from youtube_transcript_api import YouTubeTranscriptApi

video_id = "a72BOk1yiAE"
api = YouTubeTranscriptApi()

for transcript in api.list(video_id):
    print(transcript.language, transcript.language_code, transcript.is_generated)
'@ | python -
```

자막 추출:

```powershell
@'
from youtube_transcript_api import YouTubeTranscriptApi

video_id = "a72BOk1yiAE"
api = YouTubeTranscriptApi()
transcript = api.fetch(video_id, languages=["ko"])

for item in transcript:
    print(item.start, item.duration, item.text)
'@ | python -
```

시간대별 묶음 생성:

```powershell
@'
from youtube_transcript_api import YouTubeTranscriptApi
from collections import defaultdict

video_id = "a72BOk1yiAE"
api = YouTubeTranscriptApi()
transcript = api.fetch(video_id, languages=["ko"])

chunks = defaultdict(list)
for item in transcript:
    minute = int(float(item.start) // 180) * 3
    chunks[minute].append(" ".join(str(item.text).split()))

for minute in sorted(chunks):
    print(f"[{minute:02d}:00-{minute + 3:02d}:00]")
    print(" ".join(chunks[minute]))
'@ | python -
```

### 2.2. 2순위: `yt-dlp` 자막 다운로드

`youtube-transcript-api`가 막히거나 자막 목록을 못 가져오면 `yt-dlp`를 사용한다.

```powershell
python -m pip install yt-dlp
yt-dlp --skip-download --write-auto-subs --sub-langs ko --sub-format vtt "https://www.youtube.com/watch?v=a72BOk1yiAE"
```

생성되는 `.vtt` 파일에서 타임코드와 중복 문장을 정리하면 된다.

### 2.3. 3순위: YouTube 웹 transcript

브라우저에서 영상 페이지를 열고:

1. 영상 하단 더보기 메뉴
2. `Transcript` 또는 `스크립트 표시`
3. 전체 선택 후 복사

이 방식은 자동화에는 불리하지만, API가 막힐 때 가장 단순한 수동 대안이다.

### 2.4. 4순위: 오디오 다운로드 후 STT

자막이 없는 영상이면 오디오를 받아 Whisper 등 STT로 변환한다.

```powershell
python -m pip install yt-dlp openai-whisper
yt-dlp -x --audio-format mp3 "https://www.youtube.com/watch?v=a72BOk1yiAE"
whisper "audio.mp3" --language Korean --task transcribe
```

이 방식은 시간이 오래 걸리고, 영상 원음 품질에 따라 오인식이 많을 수 있다.

## 3. 영상 전체 흐름 요약

### 00:00-03:00: 전략 소개와 핵심 지표

영상은 Ross Cameron의 매매법을 소개하면서 시작한다. 그는 소액으로 시작해 큰 수익을 냈고, 매매에서 주로 MACD를 중심 지표로 사용하고 RSI를 보조 지표로 활용한다고 설명한다.

핵심 전제는 다음과 같다.

- 대상 시장은 주식, 선물, 외환, 코인 모두 가능하다고 설명한다.
- 핵심 지표는 MACD다.
- RSI는 MACD의 후행성과 가짜 신호를 걸러내는 보조 필터다.
- 단순 알고리즘보다 강한 모멘텀이 발생한 종목의 타점을 찾는 것이 핵심이다.

MACD는 이동평균선 간 수렴과 발산을 지표화한 것이며, RSI는 특정 기간 가격 움직임의 상대적 강도를 보여주는 지표로 설명된다.

### 03:00-06:00: MACD의 구성과 단점

MACD는 세 가지 요소로 구성된다.

- MACD 선
- Signal 선
- Histogram

기본 매매 신호는 다음과 같다.

- MACD 선이 Signal 선을 상향 돌파하면 매수 신호
- MACD 선이 Signal 선을 하향 돌파하면 매도 신호

하지만 MACD는 이동평균 기반 지표라 후행성이 있다. 가격이 이미 크게 움직인 뒤 신호가 나오기 때문에, 단기 급등락 구간에서는 고점 매수와 늦은 매도로 이어질 수 있다. 영상은 이 단점을 RSI로 보완한다고 설명한다.

### 06:00-09:00: 첫 번째 매매법, MACD 크로스 + RSI 필터

첫 번째 전략은 MACD 골든크로스와 RSI 위치를 함께 보는 방식이다.

매수 조건:

- MACD 골든크로스 발생
- RSI가 50 이상 70 미만

MACD 골든크로스가 나왔더라도 RSI가 50 미만이면 바로 진입하지 않는다. 대신 MACD 정배열이 유지되는지 보고, 이후 RSI가 50을 상향 돌파할 때 진입한다.

MACD 골든크로스가 나왔지만 RSI가 70 이상이면 과열로 보고 바로 진입하지 않는다. 이 경우에도 MACD 정배열이 유지되고 RSI가 식은 뒤 50 부근에서 지지를 받으면 매수 후보로 본다.

이 규칙의 의도는 다음과 같다.

- RSI 50 이상은 상승 힘이 살아나는 구간
- RSI 70 이상은 단기 과열 구간
- MACD 정배열은 상승 모멘텀 유지
- RSI 50 지지는 과열 해소 후 재상승 가능성

### 09:00-12:00: 손절, 익절, RSI 다이버전스

진입과 동시에 손절선을 먼저 정한다. 손절선은 진입가 근처의 가장 가까운 저점이다.

목표가는 손절폭의 2배로 잡는다.

예:

- 손절폭이 -3%이면 1차 목표가는 +6%

첫 번째 매매법의 청산 구조:

- 1차 목표가 도달 시 보유 수량의 절반 매도
- 남은 절반은 MACD 데드크로스 또는 RSI 50 하향 이탈 시 매도
- 남은 절반이 본전까지 내려오면 수익 보호 차원에서 매도

이후 RSI 다이버전스 개념을 설명한다. 가격 고점은 높아지는데 RSI 고점은 낮아지면 하락 다이버전스로 해석한다. 이는 가격은 오르지만 매수 에너지가 약해지는 상태이므로, 이후 조정 가능성이 높다고 본다.

### 12:00-15:00: 두 번째 매매법, RSI 하락 다이버전스 후 MACD 재골든크로스

두 번째 전략은 1차 상승 이후 조정과 2차 상승을 노리는 방식이다.

조건:

- 강한 1차 상승이 먼저 발생
- 이후 가격 고점은 높아지지만 RSI 고점은 낮아지는 하락 다이버전스 발생
- 조정 구간에서 MACD 데드크로스가 나오며 눌림 형성
- 이후 MACD가 다시 골든크로스로 전환될 때 매수

이 전략에서는 RSI가 70 이상이어도 반드시 제외하지 않는다. 이미 1차 상승으로 강한 탄력이 확인된 뒤 2차 상승을 노리는 구조이기 때문이다.

매도 방식:

- 손절은 가까운 저점
- 목표가는 손절폭의 2배
- 목표가 도달 시 전량 매도
- 목표가 도달 전이라도 MACD 데드크로스가 나오면 전량 매도

첫 번째 전략보다 신뢰도가 높다고 설명한다. 이유는 단순 첫 반등이 아니라 강한 1차 상승과 조정 이후 2차 상승을 노리기 때문이다.

### 15:00-18:00: 실제 차트 예시와 원칙 매도

SFA반도체 15분봉 예시가 나온다.

첫 번째 전략:

- MACD 골든크로스 발생
- RSI가 50 미만이라 즉시 진입하지 않음
- 이후 RSI가 50을 넘는 캔들 종가에서 매수
- 손절과 목표가를 정하고 1차 수익 실현

두 번째 전략:

- 가격 고점은 높아지지만 RSI 고점은 낮아지는 하락 다이버전스 발생
- MACD 데드크로스 이후 조정 대기
- 이후 MACD 재골든크로스에서 매수
- 목표가 도달 전이라도 MACD 데드크로스가 나오면 전량 매도

영상은 이 구간에서 과감한 원칙 매도를 강조한다. 데드크로스가 나왔는데 버티면 앞선 수익을 반납하고 큰 손실로 이어질 수 있다고 설명한다.

### 18:00-21:00: 일반 MACD 개선 아이디어

영상 후반부는 일반 MACD의 후행성을 개선하는 자체 지표를 소개한다.

개선 아이디어는 두 가지다.

- MACD 선의 실제 교차보다 먼저 반응하는 histogram 방향 전환을 활용
- 거래량이 평균 이상일 때 histogram 신뢰도를 크게 보여줌

추세 기준선으로는 100 HMA를 추가한다.

- HMA가 상승 방향이면 상승 추세
- HMA가 하락 방향이면 하락 추세

영상에서는 이 개선 지표를 `Momentum Scope`라고 부른다. 기본 원리는 MACD 교차 매매를 유지하되, 일반 MACD보다 빠르게 전환 신호를 감지하는 것이다.

### 21:00-24:00: Momentum Scope 예시

레인보우로보틱스 1시간봉과 삼진제약 1시간봉 예시가 나온다.

주요 설명:

- 일반 MACD는 횡보 구간에서 신호가 늦거나 밋밋하게 나타남
- Momentum Scope는 histogram 변화와 거래량을 반영해 더 빠른 골든크로스/데드크로스를 보여줌
- 거래량이 실린 상승에서는 histogram 크기가 커져 신뢰도 높은 상승으로 해석
- 상한가 직전이나 마감 직전 거래량 변화도 위험 신호로 해석 가능

### 24:00-26:45: 마무리와 지표 홍보

후반부는 Momentum Scope 지표 공유 안내와 채널 구독 유도다.

전략적으로 건질 핵심은 다음이다.

- 일반 MACD는 느리다.
- histogram 방향 전환은 더 빠른 조기 신호가 될 수 있다.
- 거래량 필터가 없으면 가짜 신호가 많다.
- RSI는 매수세 강도와 과열 판단에 유용하다.
- MACD 데드크로스는 목표가 미도달 시에도 매도 신호로 존중한다.

## 4. 미스톡 적용 가능성

현재 미스톡에는 이미 다음 계산이 존재한다.

- RSI(14)
- RSI(2)
- MACD histogram
- SMA20
- SMA60
- Bollinger Band
- 거래량 20일 평균

관련 파일:

- `src/mistock/strategy.py`
- `src/mistock/trader.py`
- `src/mistock/scheduler.py`
- `src/strategy/indicators.py`

따라서 영상 전략은 새 지표 엔진 없이도 대부분 구현 가능하다. 다만 영상은 단타/분봉 중심인데, 현재 미스톡의 `fetch_history()`는 기본 `6mo`, `1d` 일봉이다. 따라서 그대로 적용하면 단타가 아니라 일봉 기반 스윙/모멘텀 전략으로 해석해야 한다.

## 5. 미스톡 전략 설계안

### 5.1. 전략 이름

`mistock_macd_rsi_momentum_v1`

### 5.2. 적용 타임프레임

1차 적용은 일봉으로 한다.

이유:

- 현재 미스톡 데이터 수집이 yfinance 일봉 기반
- KIS 해외주식 자동 주문 스케줄도 장중 반복 실행 구조지만, 후보 선정 로직은 일봉 기반
- 분봉 자동매매로 바로 확장하면 데이터 안정성, 거래비용, 슬리피지 위험이 커진다.

추후 확장:

- 30분봉 또는 1시간봉 기반
- pre-market/regular-session 구분
- 거래량 급증 필터 강화

### 5.3. 매수 점수 규칙

총점은 0~8점으로 계산하고, 기본 후보 기준은 4점 이상으로 둔다.

```text
MACD bull cross: +2
MACD histogram > 0: +1
MACD histogram rising: +1
RSI 50 상향 돌파: +2
RSI 50~70 구간: +1
현재가 > SMA60: +1
현재가 > SMA20: +1
거래량 > 20일 평균 * 1.3: +1
RSI >= 70 and no divergence setup: -2
```

### 5.4. 첫 번째 매매법 구현

조건:

```text
MACD 골든크로스
AND RSI >= 50
AND RSI < 70
AND 현재가 > SMA60
```

진입:

- 조건을 만족한 날 종가 기준 후보 등록
- 실제 주문은 다음 스케줄에서 지정가 또는 현재가 근처로 계획

청산:

```text
1차 목표: 손절폭의 2배
절반 매도: 목표 도달 시
잔량 매도: MACD 데드크로스 OR RSI < 50 OR 본전 회귀
```

현재 미스톡은 분할 보유/절반 매도 로직이 단순하므로, 초기 구현에서는 다음처럼 단순화한다.

```text
목표수익 도달: 전량 매도
MACD 데드크로스: 전량 매도
RSI < 50: 전량 매도
손절: -7%
```

### 5.5. 두 번째 매매법 구현

조건:

```text
최근 20~40봉 내 강한 1차 상승
AND 가격 고점 상승
AND RSI 고점 하락
AND 조정 이후 MACD 재골든크로스
AND 현재가 > SMA60
```

일봉 기준 단순 판정:

```text
first_leg_up = 최근 20일 저점 대비 현재가 또는 최근 고점이 +12% 이상
bearish_divergence = 최근 고점은 높아졌지만 같은 구간 RSI 고점은 낮아짐
reentry = MACD bull cross
```

진입:

- `first_leg_up`
- `bearish_divergence`
- 이후 `MACD bull cross`
- RSI는 70 이상이어도 허용하되, 현재가가 SMA20/SMA60 아래면 제외

청산:

- 목표수익: 손절폭의 2배
- 목표 전 MACD 데드크로스 발생 시 전량 매도
- 손절: 가까운 스윙 저점 또는 -7%

### 5.6. Momentum Scope 대체 구현

영상의 Momentum Scope는 원본 코드가 없으므로 그대로 복제할 수 없다. 대신 미스톡에서는 다음과 같이 대체한다.

```text
hist_now = MACD histogram 현재값
hist_prev = MACD histogram 직전값
hist_rising = hist_now > hist_prev
hist_turn_up = hist_prev < 0 and hist_now > hist_prev
volume_confirmed = volume_now > volume_avg20 * 1.3
trend_filter = current > SMA60
```

조기 매수 후보:

```text
hist_turn_up
AND volume_confirmed
AND RSI >= 45
AND current > SMA60
```

조기 매도 후보:

```text
hist_now < hist_prev
AND RSI 하락
AND volume_now > volume_avg20 * 1.3
```

## 6. 기존 미스톡 전략과의 차이

현재 `src/mistock/strategy.py`는 다음 조건을 혼합한다.

- RSI 회복
- MACD 골든크로스
- Bollinger 반등
- RSI2 눌림
- 20일 신고가 + 거래량

영상 전략은 다음 성격이 강하다.

- MACD 중심
- RSI는 50/70 기준 필터
- 손익비 1:2
- MACD 데드크로스 매도 원칙
- 다이버전스 후 2차 상승 공략

따라서 기존 전략을 덮어쓰기보다는 전략 모드를 분리하는 것이 안전하다.

권장 방식:

```text
MISTOCK_STRATEGY_MODEL=macd_rsi_momentum
```

또는 DB 전략 profile에 다음 값을 둔다.

```json
{
  "model": "macd_rsi_momentum",
  "min_score": 4,
  "stop_loss_pct": -7,
  "take_profit": 14,
  "rsi_entry_min": 50,
  "rsi_entry_max": 70,
  "use_divergence_reentry": true
}
```

## 7. 구현 우선순위

### 1단계: 점수 산식 추가

`src/mistock/strategy.py`에 전략 모델 분기를 추가한다.

```text
strategy_profile(..., model="")
```

`model == "macd_rsi_momentum"`이면 영상 기반 점수 산식을 사용한다.

### 2단계: 매도 조건 강화

`src/mistock/trader.py`의 `signals()`에서 다음 매도 조건을 추가한다.

```text
MACD bear cross
RSI < 50
stop_loss_pct
take_profit
```

현재는 `RSI >= rsi_sell`, 수익률 목표, 손절 정도만 본다.

### 3단계: 백테스트

`src/strategy/backtest_mistock.py`가 현재 `seven_split.calc_strategy_profile()`을 사용하므로, 미스톡 전용 `strategy_profile()`을 직접 사용하도록 수정하는 것이 맞다.

검증 기준:

```text
기간: 최근 2년
대상: NASDAQ100 + 보유 watchlist
최소 거래 수: 30회 이상
profit factor: 1.15 이상
MDD: 15% 이하
총수익률: QQQ 대비 초과
```

### 4단계: dry-run 스케줄 적용

라이브 주문 전 최소 2주 이상 dry-run으로 확인한다.

확인 항목:

- 후보 선정이 너무 많지 않은지
- RSI 70 이상 추격 매수가 과도하지 않은지
- MACD 데드크로스 매도가 너무 늦지 않은지
- 장중 스케줄에서 같은 종목이 반복 주문되지 않는지

## 8. 운영 권장값

초기값:

```text
MISTOCK_DRY_RUN=true
MISTOCK_TRADING_ENV=demo
MISTOCK_REQUIRE_APPROVAL=true
MISTOCK_MAX_POSITIONS=5
MISTOCK_CASH_BUFFER=0.25
MISTOCK_STOP_LOSS_PCT=-7
MISTOCK_TAKE_PROFIT=14
MISTOCK_RSI_BUY=50
MISTOCK_RSI_SELL=72
```

후보 기준:

```text
min_score=4
```

공격형으로 바꿀 때:

```text
min_score=3
cash_buffer=0.15
take_profit=18
```

보수형으로 바꿀 때:

```text
min_score=5
cash_buffer=0.35
take_profit=10
```

## 9. 리스크

1. 영상 전략은 단타/분봉 기반이다.
   - 미스톡 일봉에 바로 적용하면 신호가 늦어질 수 있다.

2. MACD는 여전히 후행 지표다.
   - histogram 조기 전환을 쓰더라도 횡보장에서는 가짜 신호가 생긴다.

3. RSI 70 이상 예외 진입은 위험하다.
   - 두 번째 매매법에서만 허용해야 한다.

4. 미국장 개별주는 장전/장후 갭이 크다.
   - 손절선을 종가 기준으로만 보면 실제 체결 손실이 커질 수 있다.

5. 영상의 높은 승률 주장은 검증되지 않았다.
   - 미스톡에서는 반드시 백테스트와 dry-run으로 검증해야 한다.

## 10. 결론

이 영상의 전략은 미스톡에 적용 가능하다. 다만 원본 의도는 단타 모멘텀 매매이므로, 현재 미스톡 구조에서는 다음처럼 변환해야 한다.

```text
MACD 골든크로스 + RSI 50~70 + SMA60 추세 필터
RSI 하락 다이버전스 후 MACD 재골든크로스
손절폭 대비 2배 목표가
MACD 데드크로스 또는 RSI 50 이탈 시 매도
```

가장 안전한 적용 방식은 기존 미스톡 기본 전략을 교체하지 않고, `macd_rsi_momentum` 전략 모드로 추가한 뒤 dry-run과 백테스트를 통과한 경우에만 운영 전략으로 승격하는 것이다.
