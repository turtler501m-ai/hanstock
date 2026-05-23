# Hanstock Documentation

이 폴더는 현재 통합된 `hanstock` 프로젝트 기준 문서만 보관합니다.

## 문서 목록

- [01-project-analysis.md](01-project-analysis.md): 현재 프로젝트 목적, 기능, 구성 분석
- [02-architecture.md](02-architecture.md): 코드 구조와 주요 실행 흐름
- [03-development-workflow.md](03-development-workflow.md): 로컬 개발, 테스트, 커밋, VM 반영 절차
- [04-operations.md](04-operations.md): 대시보드/트레이더/시그널 수집 운영 방법
- [05-risk-security.md](05-risk-security.md): 실거래 안전장치, 환경변수, 보안 주의사항
- [06-cleanup-roadmap.md](06-cleanup-roadmap.md): 정리된 사항과 다음 개선 과제
- [quantconnect-mnq-paper-auto.md](quantconnect-mnq-paper-auto.md): QuantConnect MNQ paper live 알고리즘 운영 기준

## 기준 원칙

- 개발은 로컬 루트 프로젝트에서만 진행합니다.
- VM에서는 코드를 직접 수정하지 않고 `git pull` 후 재시작합니다.
- `.env`, `.runtime`, `logs`, DB, 토큰, 세션 파일은 Git에 올리지 않습니다.
- 실거래는 `DRY_RUN=false`, `TRADING_ENV=real`, `ENABLE_LIVE_TRADING=true`가 모두 의도적으로 설정된 경우에만 허용합니다.
