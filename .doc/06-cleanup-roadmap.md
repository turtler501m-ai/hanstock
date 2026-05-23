# Cleanup Roadmap

## 이번에 정리된 사항

- `hanstock_loc/`, `hanstock_vm/` 중복 폴더 제거
- 기준 원격 저장소를 `https://github.com/turtler501m-ai/hanstock.git`로 통합
- VM 실행용 shell script를 루트 프로젝트에 포함
- 오래된 `.doc/`, `docs/` 문서를 제거하고 현재 프로젝트 기준 문서로 재작성

## 우선순위 높은 개선

1. README 재작성
   - 현재 README는 인코딩이 깨져 있습니다.
   - `.doc` 문서를 기준으로 새 README를 만들어야 합니다.

2. GitHub Actions 정리
   - `.github/workflows/auto_trade.yml`의 한글 인코딩이 깨져 있습니다.
   - `database` 브랜치에 거래 DB를 push하는 방식은 운영 정책상 재검토가 필요합니다.
   - 우선은 수동 검증 workflow와 배포 안내 중심으로 단순화하는 것이 안전합니다.

3. `src/dashboard.py` 분리
   - 현재 파일이 너무 큽니다.
   - 권장 분리:
     - `src/dashboard/app.py`
     - `src/dashboard/routes/account.py`
     - `src/dashboard/routes/futures.py`
     - `src/dashboard/routes/quantconnect.py`
     - `src/dashboard/routes/settings.py`
     - `src/dashboard/services/*.py`

4. Telegram 기본 credential 제거
   - `src/futures_signals/poll.py`의 코드 내 fallback credential은 보안 리스크입니다.
   - 값이 없으면 명확히 오류를 내도록 바꾸는 편이 안전합니다.

5. 환경변수 문서화 보강
   - `.env.example`에 QuantConnect, Anthropic, Signals DB 관련 키가 일부 빠져 있습니다.
   - 운영 문서와 `.env.example`을 맞춰야 합니다.

## 중간 우선순위 개선

- 대시보드 API 라우트별 테스트 강화
- 해외선물 executor의 실거래 전 dry-run 시뮬레이션 로그 보강
- `.runtime` DB schema migration 정책 추가
- VM systemd 서비스 파일 추가
- `server.sh`의 host/port 설정 문서화 및 외부 접속 옵션 분리

## 낮은 우선순위 개선

- 오래된 mock/test helper 파일 정리
- `vendor/` 사용 정책 명확화
- QuantConnect 문서와 대시보드 UI 문구 정리
- Windows/VM 스크립트 명령 이름 통일
