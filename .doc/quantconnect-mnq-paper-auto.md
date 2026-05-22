# QuantConnect MNQ 자동 모의투자 검증

## 결론

QuantConnect Cloud Paper Trading 방식은 별도 로컬 프로그램 설치 없이 브라우저에서 Micro E-mini Nasdaq-100 futures(MNQ) 자동 모의투자를 실행할 수 있는 경로다.

공식 문서 기준:

- QuantConnect Paper Trading은 simulated fills로 주문을 체결하며, 별도 실계좌 없이 사용할 수 있다.
- 최신 v2 Paper Trading 문서는 Futures와 Future Options를 지원 자산으로 명시한다.
- US Futures 데이터셋 문서는 MNQ를 `Futures.Indices.MicroNASDAQ100EMini` / `Futures.Indices.MICRO_NASDAQ_100_E_MINI`로 제공한다고 명시한다.

주의할 점:

- 오래된 v1 Paper Trading 문서에는 Futures paper trading 미지원 문구가 남아 있다. 이 문서는 v2 문서와 충돌하므로 최신 v2 문서를 기준으로 판단했다.
- 이 repo 안에서는 QuantConnect Cloud 주문 체결까지 검증할 수 없다. 실제 live-paper 배포 검증은 QuantConnect 계정, live node, live futures data 권한 또는 플랜 상태가 필요하다.

## 추가된 파일

- `quantconnect/mnq_paper_auto/main.py`
  - MNQ front contract를 선택한다.
  - 1분봉 SMA fast/slow 교차로 자동 market order를 낸다.
  - 기본 최대 수량은 1계약이다.
  - 일 손실 제한에 걸리면 보유 포지션을 청산한다.

- `quantconnect/mnq_paper_auto/config.json`
  - QuantConnect/LEAN 프로젝트 메타데이터와 기본 파라미터다.

## QuantConnect Cloud 배포 절차

1. QuantConnect Cloud에서 새 Python 프로젝트를 만든다.
2. `quantconnect/mnq_paper_auto/main.py` 내용을 프로젝트 `main.py`에 넣는다.
3. Backtest를 먼저 실행해 문법과 futures chain 선택이 통과하는지 확인한다.
4. Deploy Live를 선택한다.
5. Brokerage는 `QuantConnect Paper Trading`을 선택한다.
6. Data Provider는 QuantConnect 기본 데이터 provider를 선택한다.
7. 파라미터는 처음에는 기본값을 사용한다.
   - `FAST_PERIOD=12`
   - `SLOW_PERIOD=48`
   - `MAX_CONTRACTS=1`
   - `DAILY_LOSS_LIMIT=750`
8. 배포 후 Orders 탭에서 MNQ market order가 simulated fill로 발생하는지 확인한다.

## 실패 시 확인할 항목

- Paper Trading 배포 화면에서 brokerage가 real brokerage가 아니라 `QuantConnect Paper Trading`인지 확인한다.
- Futures live data 권한 또는 플랜 제한 메시지가 있는지 확인한다.
- Backtest에서 MNQ contract chain이 비어 있으면 기간, 해상도, 데이터 권한을 확인한다.
- 자동 주문이 너무 늦게 나오는 경우 `FAST_PERIOD`와 `SLOW_PERIOD`를 줄여 테스트한다.

