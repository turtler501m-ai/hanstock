# OCI VM Retry

Linux VM에서 Oracle Cloud `VM.Standard.A1.Flex` 생성을 계속 재시도하고, 매일 18:00 KST에 Slack으로 요약 리포트를 보냅니다.

## Files

- `oci_retry.py`: OCI CLI 기반 재시도/리포트/Slack 전송 본체
- `oci-retry.sh`: 15분마다 실행할 생성 재시도 wrapper
- `oci-report.sh`: 매일 18:00 실행할 Slack 리포트 wrapper
- `test-slack.sh`: Slack 리포트 테스트
- `install-cron.sh`: Linux crontab 등록
- `.env.example`: VM에서 `.env`로 복사해 채울 설정 템플릿

## VM Setup

```bash
cd /home/turtler800/oci-vm-retry
cp .env.example .env
vi .env
chmod +x *.sh oci_retry.py
./oci-retry.sh --dry-run --no-sleep
./test-slack.sh
./install-cron.sh /home/turtler800/oci-vm-retry
```

Cron:

- 주말 포함 매일 15분마다 생성 시도
- 주말 포함 매일 18:00 KST 결과 요약 Slack 전송

기본 profile은 `2:12,1:6,4:24` 순서입니다. 작은 A1 Flex를 먼저 잡은 뒤 콘솔/CLI에서 키우는 성공 사례가 많아 기본값을 이렇게 둡니다.
