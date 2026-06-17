#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


KST = timezone(timedelta(hours=9))
ACTIVE_STATES = {"PROVISIONING", "RUNNING", "STARTING", "STOPPED", "STOPPING"}


def now_kst() -> datetime:
    return datetime.now(KST)


def ts() -> str:
    return now_kst().strftime("%Y-%m-%d %H:%M:%S")


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class RetryApp:
    def __init__(self, root: Path, dry_run: bool = False) -> None:
        self.root = root
        self.dry_run = dry_run
        self.log_path = Path(os.getenv("OCI_RETRY_LOG", root / "oci-retry.log"))
        self.state_path = Path(os.getenv("OCI_RETRY_STATE", root / "oci-retry-state.json"))
        self.lock_path = Path(os.getenv("OCI_RETRY_LOCK", root / "oci-retry.lock"))
        self.remote_log_path = os.getenv("OCI_RETRY_REMOTE_LOG", str(self.log_path))
        self.compartment_id = required("OCI_COMPARTMENT_ID")
        self.subnet_id = required("OCI_SUBNET_ID")
        self.image_id = required("OCI_IMAGE_ID")
        self.availability_domain = required("OCI_AVAILABILITY_DOMAIN")
        self.ssh_key_file = os.getenv("OCI_SSH_PUBLIC_KEY_FILE", str(Path.home() / ".ssh/id_ed25519.pub"))
        self.shape = os.getenv("OCI_SHAPE", "VM.Standard.A1.Flex")
        self.display_name = os.getenv("OCI_DISPLAY_NAME", "my-free-instance")
        self.capacity_mode = os.getenv("OCI_RETRY_CAPACITY_REPORT_MODE", "log").lower()
        self.max_launches = int(os.getenv("OCI_RETRY_MAX_LAUNCHES_PER_RUN", "1"))
        self.timeout = int(os.getenv("OCI_RETRY_COMMAND_TIMEOUT_SECONDS", "120"))
        self.jitter_min = int(os.getenv("OCI_RETRY_JITTER_MIN_SECONDS", "15"))
        self.jitter_max = int(os.getenv("OCI_RETRY_JITTER_MAX_SECONDS", "240"))
        self.profiles = self._profiles()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _profiles(self) -> list[dict[str, object]]:
        raw = os.getenv("OCI_RETRY_PROFILES", "2:12,1:6,4:24")
        profiles: list[dict[str, object]] = []
        for part in raw.split(","):
            if not part.strip():
                continue
            ocpus_s, mem_s = part.strip().split(":", 1)
            ocpus = int(ocpus_s)
            memory = int(mem_s)
            suffix = "" if ocpus == 4 and memory == 24 else f"-{ocpus}c{memory}g"
            profiles.append({"name": f"{self.display_name}{suffix}", "ocpus": ocpus, "memory": memory})
        if not profiles:
            raise SystemExit("OCI_RETRY_PROFILES must contain at least one profile, e.g. 2:12")
        return profiles

    def log(self, message: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{ts()}] {message}\n")

    def read_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            self.log("WARN - Ignoring invalid state file")
            return {}

    def write_state(self, reason: str, next_run_after: datetime, **extra: object) -> None:
        state = {"nextRunAfter": next_run_after.isoformat(), "reason": reason, "updatedAt": now_kst().isoformat()}
        state.update(extra)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def oci(self, args: list[str]) -> str:
        if self.dry_run:
            self.log("DRYRUN oci " + " ".join(args))
            return ""
        proc = subprocess.run(
            ["oci", *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=self.timeout,
            check=False,
        )
        return proc.stdout or ""

    def oci_json(self, args: list[str]) -> dict | None:
        output = self.oci(args)
        match = re.search(r"({.*})", output, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            self.log(f"WARN - Could not parse OCI JSON: {output[:500]}")
            return None

    def active_instance(self) -> dict | None:
        for profile in self.profiles:
            payload = self.oci_json([
                "compute", "instance", "list",
                "--compartment-id", self.compartment_id,
                "--display-name", str(profile["name"]),
                "--all",
            ])
            for item in (payload or {}).get("data", []):
                if item.get("lifecycle-state") in ACTIVE_STATES:
                    return item
        return None

    def capacity_statuses(self) -> dict[str, str]:
        if self.capacity_mode == "off":
            return {profile_key(p): "SKIPPED" for p in self.profiles}
        capacity_file = self.root / "oci-capacity-request.json"
        payload = [
            {
                "instanceShape": self.shape,
                "instanceShapeConfig": {"ocpus": float(p["ocpus"]), "memoryInGBs": float(p["memory"])},
            }
            for p in self.profiles
        ]
        capacity_file.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        data = self.oci_json([
            "compute", "compute-capacity-report", "create",
            "--availability-domain", self.availability_domain,
            "--compartment-id", self.compartment_id,
            "--shape-availabilities", f"file://{capacity_file}",
        ])
        statuses = {profile_key(p): "UNKNOWN" for p in self.profiles}
        for item in ((data or {}).get("data") or {}).get("shape-availabilities", []):
            cfg = item.get("instance-shape-config") or {}
            key = f"{int(cfg.get('ocpus', 0))}c/{int(cfg.get('memory-in-gbs', 0))}g"
            statuses[key] = item.get("availability-status") or "UNKNOWN"
        return statuses

    def launch(self, profile: dict[str, object]) -> str:
        shape_file = self.root / f"shape-{profile['ocpus']}c-{profile['memory']}g.json"
        availability_file = self.root / "availability-config.json"
        options_file = self.root / "instance-options.json"
        shape_file.write_text(
            json.dumps({"ocpus": float(profile["ocpus"]), "memoryInGBs": float(profile["memory"])}),
            encoding="utf-8",
        )
        availability_file.write_text('{"recoveryAction":"RESTORE_INSTANCE"}', encoding="utf-8")
        options_file.write_text('{"areLegacyImdsEndpointsDisabled":false}', encoding="utf-8")
        self.log(f"TRY - Launch {profile['name']} {profile['ocpus']} OCPU / {profile['memory']} GB")
        return self.oci([
            "compute", "instance", "launch",
            "--availability-domain", self.availability_domain,
            "--compartment-id", self.compartment_id,
            "--shape", self.shape,
            "--shape-config", f"file://{shape_file}",
            "--image-id", self.image_id,
            "--subnet-id", self.subnet_id,
            "--assign-public-ip", "true",
            "--availability-config", f"file://{availability_file}",
            "--instance-options", f"file://{options_file}",
            "--display-name", str(profile["name"]),
            "--ssh-authorized-keys-file", self.ssh_key_file,
        ])

    def attempt(self, ignore_cooldown: bool = False, no_sleep: bool = False) -> int:
        if self.lock_path.exists() and time.time() - self.lock_path.stat().st_mtime < 20 * 60:
            self.log("SKIP - Previous retry is still running")
            return 0
        self.lock_path.write_text(str(os.getpid()), encoding="utf-8")
        try:
            state = self.read_state()
            if not ignore_cooldown and state.get("nextRunAfter"):
                next_run = datetime.fromisoformat(state["nextRunAfter"])
                if now_kst() < next_run:
                    self.log(f"SKIP - Cooldown until {next_run.strftime('%Y-%m-%d %H:%M:%S')} ({state.get('reason')})")
                    return 0

            if not no_sleep and not self.dry_run:
                wait = random.randint(self.jitter_min, self.jitter_max)
                self.log(f"WAIT - Jitter {wait}s")
                time.sleep(wait)

            existing = self.active_instance()
            if existing:
                self.log(f"SUCCESS! Existing instance found: {existing.get('id')} ({existing.get('display-name')})")
                return 0

            statuses = self.capacity_statuses()
            for profile in self.profiles:
                self.log(f"INFO - Capacity report {profile['name']} {profile_key(profile)}: {statuses[profile_key(profile)]}")

            profile_index = int(state.get("profileIndex", 0)) % len(self.profiles)
            launch_profiles = [self.profiles[(profile_index + i) % len(self.profiles)] for i in range(min(self.max_launches, len(self.profiles)))]
            next_profile_index = (profile_index + len(launch_profiles)) % len(self.profiles)

            saw_capacity = saw_throttle = saw_limit = saw_error = False
            for profile in launch_profiles:
                status = statuses.get(profile_key(profile), "UNKNOWN")
                if self.capacity_mode == "gate" and status not in {"AVAILABLE", "UNKNOWN", "SKIPPED"}:
                    saw_capacity = True
                    continue
                output = self.launch(profile)
                if re.search(r"Out of host capacity|Out of capacity|out of capacity|InternalError", output):
                    self.log(f"FAIL - Out of capacity for {profile['name']} (will retry)")
                    saw_capacity = True
                elif re.search(r"TooManyRequests|User-rate limit|status\"?:\\s*429", output):
                    self.log(f"THROTTLED - TooManyRequests while launching {profile['name']}")
                    saw_throttle = True
                elif re.search(r"LimitExceeded|service limits were exceeded|standard-a1-(memory|core)", output):
                    self.log(f"LIMIT - Service limit exceeded while launching {profile['name']}: {compact(output)}")
                    saw_limit = True
                elif '"lifecycle-state"' in output:
                    instance_id = extract_instance_id(output)
                    self.log(f"SUCCESS! Instance ID: {instance_id} ({profile['name']}, {profile_key(profile)})")
                    self.write_state("success", now_kst() + timedelta(days=365), profileIndex=next_profile_index)
                    return 0
                elif self.dry_run:
                    self.log(f"DRYRUN - Completed command generation for {profile['name']}")
                else:
                    self.log(f"ERROR - Launch failed for {profile['name']}: {compact(output)}")
                    saw_error = True

            if self.dry_run:
                self.log("DRYRUN - Finished without OCI launch")
                return 0
            if saw_throttle:
                minutes = random.randint(45, 75)
                self.write_state("throttled", now_kst() + timedelta(minutes=minutes), profileIndex=next_profile_index)
                self.log(f"NEXT - Cooldown {minutes}m due to throttling")
            elif saw_limit:
                minutes = random.randint(360, 720)
                self.write_state("limit", now_kst() + timedelta(minutes=minutes), profileIndex=next_profile_index)
                self.log(f"NEXT - Cooldown {minutes}m due to service limit")
            elif saw_capacity:
                self.write_state("capacity", now_kst() + timedelta(minutes=random.randint(4, 8)), profileIndex=next_profile_index)
            elif saw_error:
                self.write_state("error", now_kst() + timedelta(minutes=random.randint(10, 20)), profileIndex=next_profile_index)
            return 0
        finally:
            self.lock_path.unlink(missing_ok=True)

    def report_text(self, hours: int = 24) -> str:
        current = self.active_instance()
        capacity_statuses = self.capacity_statuses()
        state = self.read_state()
        now = now_kst()
        start = now - timedelta(hours=hours)
        lines = read_log_lines(self.log_path)
        period_lines = [(dt, line) for dt, line in parse_log_lines(lines) if start <= dt <= now]
        all_parsed = parse_log_lines(lines)
        counts = aggregate(period_lines)
        recent_attempts = [line for _, line in period_lines if "TRY - " in line or "FAIL - " in line or "THROTTLED - " in line or "LIMIT - " in line][-5:]
        last_line = lines[-1] if lines else "-"
        first_dt = all_parsed[0][0].strftime("%Y-%m-%d %H:%M:%S KST") if all_parsed else "-"
        next_run = state.get("nextRunAfter")
        next_text = "-"
        if next_run:
            try:
                next_dt = datetime.fromisoformat(next_run).astimezone(KST)
                delta_min = max(0, int((next_dt - now).total_seconds() // 60))
                next_text = f"{next_dt.strftime('%Y-%m-%d %H:%M:%S')} KST (약 {delta_min}분 후)"
            except Exception:
                next_text = str(next_run)
        live_capacity_values = set(capacity_statuses.values())
        wait_reason = {
            "throttled": "OCI API 호출 제한 때문에 대기 중",
            "capacity": "오라클 가용 자원 부족으로 재시도 대기 중",
            "limit": "무료 한도/서비스 한도 거절 때문에 대기 중",
            "error": "기타 오류 후 대기 중",
            "success": "인스턴스 생성 완료",
        }.get(str(state.get("reason", "")), "재시도 가능 상태")
        if current:
            wait_reason = "인스턴스 생성 완료"
        elif "AVAILABLE" in live_capacity_values:
            wait_reason = "가용 자원 감지됨 - 다음 생성 시도 대기 중"
        elif live_capacity_values and live_capacity_values <= {"OUT_OF_HOST_CAPACITY"}:
            wait_reason = "오라클 가용 자원 부족으로 재시도 대기 중"
        elif "THROTTLED" in live_capacity_values:
            wait_reason = "OCI API 호출 제한 때문에 대기 중"

        capacity_lines = [
            f"- {profile['name']} ({profile_key(profile)}): {capacity_statuses.get(profile_key(profile), 'UNKNOWN')}"
            for profile in self.profiles
        ]
        current_text = "현재 생성된 인스턴스 없음 / resource_search_no_match"
        instance_id = "-"
        if current:
            current_text = f"{current.get('display-name')} / {current.get('lifecycle-state')}"
            instance_id = current.get("id") or "-"
        recent_text = "\n".join(f"  - {line}" for line in recent_attempts) if recent_attempts else "  - -"
        return "\n".join([
            "[OCI VM 생성 재시도 리포트]",
            f"- 현재 인스턴스: {current_text}",
            f"- 인스턴스 ID: {instance_id}",
            f"- 마지막 확인: {now.isoformat()}",
            f"- 재시도 상태: {'생성 완료' if current else '재시도 진행 중'}",
            f"- 리포트 시각: {now.strftime('%Y-%m-%d %H:%M:%S')} KST",
            f"- 집계 기간: {start.strftime('%Y-%m-%d %H:%M')} ~ {now.strftime('%Y-%m-%d %H:%M')} KST",
            "- 스케줄: 주말 포함 매일 15분마다 생성 시도, 매일 18:00 결과 요약",
            f"- 현재 대기 상태: {wait_reason}",
            f"- 다음 시도 예정: {next_text}",
            "",
            "[현재 OCI A1 Flex 가용 상태]",
            *capacity_lines,
            "",
            "[최근 24시간 집계]",
            f"- 실제 생성 시도: {counts['try']}회",
            f"- 성공: {counts['success']}회",
            f"- 오라클 가용 자원 부족: {counts['capacity']}회",
            f"- OCI API 호출 제한: {counts['throttle']}회",
            f"- 무료 한도/서비스 한도 거절: {counts['limit']}회",
            f"- 기타 오류: {counts['error']}회",
            f"- 쿨다운으로 건너뜀: {counts['cooldown']}회",
            f"- 이전 실행 중이라 건너뜀: {counts['running']}회",
            "",
            "[최근 생성 시도 로그]",
            recent_text,
            "",
            "[마지막 로그]",
            f"- {last_line}",
            "",
            "[전체 로그 참고]",
            f"- 최초 기록: {first_dt}",
            f"- 누적 로그 라인: {len(lines)}개",
            f"- 원격 로그: {self.remote_log_path}",
        ])

    def send_report(self, test: bool = False) -> int:
        text = self.report_text()
        if test:
            text = "[테스트]\n" + text
        ok = post_slack(text)
        self.log(("INFO" if ok else "WARN") + f" - Slack report {'test ' if test else ''}send {'ok' if ok else 'failed'}")
        print(text)
        return 0 if ok else 1


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def profile_key(profile: dict[str, object]) -> str:
    return f"{profile['ocpus']}c/{profile['memory']}g"


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:1200]


def extract_instance_id(text: str) -> str:
    match = re.search(r'"id"\s*:\s*"(ocid1\.instance[^"]+)"', text)
    return match.group(1) if match else "unknown"


def read_log_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def parse_log_lines(lines: list[str]) -> list[tuple[datetime, str]]:
    parsed: list[tuple[datetime, str]] = []
    for line in lines:
        match = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+(.*)", line)
        if not match:
            continue
        parsed.append((datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST), line))
    return parsed


def aggregate(parsed: list[tuple[datetime, str]]) -> dict[str, int]:
    counts = {key: 0 for key in ["try", "success", "capacity", "throttle", "limit", "error", "cooldown", "running"]}
    for _, line in parsed:
        counts["try"] += int("TRY - Launch" in line)
        counts["success"] += int("SUCCESS!" in line)
        counts["capacity"] += int("FAIL - Out of capacity" in line)
        counts["throttle"] += int("THROTTLED -" in line)
        counts["limit"] += int("LIMIT -" in line)
        counts["error"] += int("ERROR -" in line)
        counts["cooldown"] += int("SKIP - Cooldown" in line)
        counts["running"] += int("SKIP - Previous retry" in line)
    return counts


def post_slack(text: str) -> bool:
    webhook = (
        os.getenv("OCI_SLACK_WEBHOOK_URL")
        or os.getenv("OCI_RETRY_SLACK_WEBHOOK_URL")
        or os.getenv("SLACK_WEBHOOK_URL")
    )
    if not webhook:
        print("Missing OCI_SLACK_WEBHOOK_URL, OCI_RETRY_SLACK_WEBHOOK_URL, or SLACK_WEBHOOK_URL", file=sys.stderr)
        return False
    payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            body = res.read().decode("utf-8", errors="replace")
            return 200 <= res.status < 300 and body.strip() == "ok"
    except urllib.error.URLError as exc:
        print(f"Slack send failed: {exc}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["attempt", "report", "test-slack"])
    parser.add_argument("--root", default=os.getenv("OCI_RETRY_ROOT", str(Path(__file__).resolve().parent)))
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ignore-cooldown", action="store_true")
    parser.add_argument("--no-sleep", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    load_env(Path(args.env_file) if args.env_file else root / ".env")
    app = RetryApp(root=root, dry_run=args.dry_run)
    if args.command == "attempt":
        return app.attempt(ignore_cooldown=args.ignore_cooldown, no_sleep=args.no_sleep)
    if args.command == "report":
        return app.send_report(test=False)
    if args.command == "test-slack":
        return app.send_report(test=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
