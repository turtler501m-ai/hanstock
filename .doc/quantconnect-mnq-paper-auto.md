# QuantConnect MNQ Paper Auto

이 문서는 `quantconnect/mnq_paper_auto` 알고리즘의 현재 운영 기준을 기록합니다.

## 목적

- 대상 상품: `MICRO_NASDAQ_100_E_MINI`
- 브로커리지: QuantConnect Paper Trading
- 용도: MNQ paper live 환경에서 대시보드 명령 기반 주문 테스트
- 최대 계약수: `MAX_CONTRACTS=3`

## 현재 상태

- 알고리즘 엔트리포인트는 `quantconnect/mnq_paper_auto/main.py`입니다.
- QuantConnect 설정은 `quantconnect/mnq_paper_auto/config.json`에 있습니다.
- 대시보드 API는 `/api/quantconnect/mnq/status`, `/api/quantconnect/mnq/deploy`, `/api/quantconnect/mnq/order`를 제공합니다.

## 검증 범위

실제 live-paper 배포 검증은 QuantConnect 계정, API token, project ID, live node가 설정된 VM 또는 운영 환경에서 수행해야 합니다. 로컬 테스트는 알고리즘 파일, 설정 파일, 대시보드 API wrapper의 구조와 제한 조건을 검증합니다.

## 제한

- 이 알고리즘은 KIS 실거래 안전장치와 별개로 QuantConnect Paper Trading 표면에서 동작합니다.
- 실계좌 선물 주문이 아니라 paper live 검증용입니다.
- `MAX_CONTRACTS`를 초과하는 주문은 대시보드 API에서 거절해야 합니다.
