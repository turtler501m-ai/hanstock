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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


KST = timezone(timedelta(hours=9))
ACTIVE_STATES = {"PROVISIONING", "RUNNING", "STARTING", "STOPPED", "STOPPING"}


@dataclass(frozen=True)
class Target:
    name: str
    region: str
    compartment_id: str
    availability_domain: str
    subnet_id: str
    image_id: str


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
        self.ssh_key_file = os.getenv("OCI_SSH_PUBLIC_KEY_FILE", str(Path.home() / ".ssh/id_ed25519.pub"))
        self.shape = os.getenv("OCI_SHAPE", "VM.Standard.A1.Flex")
        self.display_name = os.getenv("OCI_DISPLAY_NAME", "my-free-instance")
        self.capacity_mode = os.getenv("OCI_RETRY_CAPACITY_REPORT_MODE", "gate").lower()
        self.stop_on_config_error = parse_bool(os.getenv("OCI_RETRY_STOP_ON_CONFIG_ERROR"), True)
        self.max_launches = int(os.getenv("OCI_RETRY_MAX_LAUNCHES_PER_RUN", "1"))
        self.timeout = int(os.getenv("OCI_RETRY_COMMAND_TIMEOUT_SECONDS", "120"))
        self.jitter_min = int(os.getenv("OCI_RETRY_JITTER_MIN_SECONDS", "15"))
        self.jitter_max = int(os.getenv("OCI_RETRY_JITTER_MAX_SECONDS", "240"))
        self.profiles = self._profiles()
        self.targets = self._targets()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _targets(self) -> list[Target]:
        raw = os.getenv("OCI_RETRY_TARGETS_JSON")
        target_file = os.getenv("OCI_RETRY_TARGETS_FILE")
        if target_file and Path(target_file).exists():
            raw = Path(target_file).read_text(encoding="utf-8")
        if raw:
            data = json.loads(raw)
            targets = [
                Target(
                    name=str(item.get("name") or item["region"]),
                    region=str(item.get("region") or ""),
                    compartment_id=str(item.get("compartment_id") or item.get("compartmentId") or required("OCI_COMPARTMENT_ID")),
                    availability_domain=str(item.get("availability_domain") or item.get("availabilityDomain")),
                    subnet_id=str(item.get("subnet_id") or item.get("subnetId")),
                    image_id=str(item.get("image_id") or item.get("imageId")),
                )
                for item in data
            ]
            if not targets:
                raise SystemExit("OCI_RETRY_TARGETS_JSON must contain at least one target")
            return targets

        region = os.getenv("OCI_REGION") or os.getenv("OCI_CLI_REGION") or ""
        return [
            Target(
                name=os.getenv("OCI_RETRY_TARGET_NAME", region or "default"),
                region=region,
                compartment_id=required("OCI_COMPARTMENT_ID"),
                availability_domain=required("OCI_AVAILABILITY_DOMAIN"),
                subnet_id=required("OCI_SUBNET_ID"),
                image_id=required("OCI_IMAGE_ID"),
            )
        ]

    def _profiles(self) -> list[dict[str, object]]:
        raw = os.getenv("OCI_RETRY_PROFILES", "1:6,2:12")
        profiles: list[dict[str, object]] = []
        for part in raw.split(","):
            if not part.strip():
                continue
            ocpus_s, mem_s = part.strip().split(":", 1)
            ocpus = int(ocpus_s)
            memory = int(mem_s)
            suffix = f"-{ocpus}c{memory}g"
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

    def oci(self, args: list[str], target: Target | None = None) -> str:
        command = ["oci", *args]
        if target and target.region:
            command = ["oci", "--region", target.region, *args]
        if self.dry_run:
            self.log("DRYRUN " + " ".join(command))
            return ""
        proc = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=self.timeout,
            check=False,
        )
        return proc.stdout or ""

    def oci_json(self, args: list[str], target: Target | None = None) -> dict | None:
        output = self.oci(args, target=target)
        match = re.search(r"({.*})", output, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            self.log(f"WARN - Could not parse OCI JSON: {output[:500]}")
            return None

    def active_instance(self, target: Target | None = None) -> tuple[Target, dict] | None:
        targets = [target] if target else self.targets
        for current_target in targets:
            if current_target is None:
                continue
            found = self._active_instance_for(current_target)
            if found:
                return current_target, found
        return None

    def _active_instance_for(self, target: Target) -> dict | None:
        for profile in self.profiles:
            payload = self.oci_json([
                "compute", "instance", "list",
                "--compartment-id", target.compartment_id,
                "--display-name", str(profile["name"]),
                "--all",
            ], target=target)
            for item in (payload or {}).get("data", []):
                if item.get("lifecycle-state") in ACTIVE_STATES:
                    return item
        return None

    def capacity_statuses(self, target: Target | None = None) -> dict[str, str]:
        target = target or self.targets[0]
        if self.capacity_mode == "off":
            return {profile_key(p): "SKIPPED" for p in self.profiles}
        capacity_file = self.root / f"oci-capacity-request-{safe_name(target.name)}.json"
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
            "--availability-domain", target.availability_domain,
            "--compartment-id", target.compartment_id,
            "--shape-availabilities", f"file://{capacity_file}",
        ], target=target)
        statuses = {profile_key(p): "UNKNOWN" for p in self.profiles}
        for item in ((data or {}).get("data") or {}).get("shape-availabilities", []):
            cfg = item.get("instance-shape-config") or {}
            key = f"{int(cfg.get('ocpus', 0))}c/{int(cfg.get('memory-in-gbs', 0))}g"
            statuses[key] = item.get("availability-status") or "UNKNOWN"
        return statuses

    def diagnose(self) -> int:
        checks: list[tuple[str, bool, str]] = []

        def add(name: str, ok: bool, detail: str) -> None:
            checks.append((name, ok, detail))

        add("shape", self.shape == "VM.Standard.A1.Flex", self.shape)
        add("profiles", True, ",".join(profile_key(p) for p in self.profiles))
        add("capacity_mode", self.capacity_mode == "gate", self.capacity_mode)

        print("== OCI retry diagnosis ==")
        print(f"time={ts()} KST")
        print(f"targets={len(self.targets)}")
        print("")

        for target in self.targets:
            prefix = f"target[{target.name}]"
            add(f"{prefix}.region", bool(target.region), target.region or "default from OCI config")
            add(f"{prefix}.compartment", bool(target.compartment_id), target.compartment_id)
            add(f"{prefix}.availability_domain", bool(target.availability_domain), target.availability_domain)
            add(f"{prefix}.subnet_id", bool(target.subnet_id), target.subnet_id)
            add(f"{prefix}.image_id", bool(target.image_id), target.image_id)

            active = self.active_instance(target)
            if active:
                _, instance = active
                add(f"{prefix}.active_instance", True, f"{instance.get('display-name')} {instance.get('lifecycle-state')} {instance.get('id')}")
            else:
                add(f"{prefix}.active_instance", True, "none")

            subnet = self.oci_json(["network", "subnet", "get", "--subnet-id", target.subnet_id], target=target)
            subnet_data = (subnet or {}).get("data") or {}
            add(f"{prefix}.subnet", bool(subnet_data.get("id")), subnet_data.get("id") or "not found or unauthorized")

            image = self.oci_json(["compute", "image", "get", "--image-id", target.image_id], target=target)
            image_data = (image or {}).get("data") or {}
            add(f"{prefix}.image", bool(image_data.get("id")), image_data.get("display-name") or image_data.get("id") or "not found or unauthorized")

            ads = self.oci_json(["iam", "availability-domain", "list", "--compartment-id", target.compartment_id], target=target)
            ad_names = [item.get("name") for item in ((ads or {}).get("data") or []) if item.get("name")]
            add(f"{prefix}.availability_domain_known", target.availability_domain in ad_names, target.availability_domain)

            shapes = self.oci_json([
                "compute", "shape", "list",
                "--compartment-id", target.compartment_id,
                "--availability-domain", target.availability_domain,
            ], target=target)
            shape_names = [item.get("shape") for item in ((shapes or {}).get("data") or []) if item.get("shape")]
            add(f"{prefix}.shape_available_in_ad", self.shape in shape_names, self.shape)

            statuses = self.capacity_statuses(target)
            for profile in self.profiles:
                key = profile_key(profile)
                add(f"{prefix}.capacity_{key}", statuses.get(key) == "AVAILABLE", statuses.get(key, "UNKNOWN"))

        failed = False
        for name, ok, detail in checks:
            marker = "OK" if ok else "WARN"
            print(f"{marker} {name}: {detail}")
            failed = failed or not ok
        print("")
        if failed:
            print("diagnosis=attention_required")
            print("note=Fix WARN items before enabling repeated launch attempts.")
        else:
            print("diagnosis=ready")
        return 1 if failed else 0

    def launch(self, target: Target, profile: dict[str, object]) -> str:
        shape_file = self.root / f"shape-{safe_name(target.name)}-{profile['ocpus']}c-{profile['memory']}g.json"
        availability_file = self.root / f"availability-config-{safe_name(target.name)}.json"
        options_file = self.root / f"instance-options-{safe_name(target.name)}.json"
        shape_file.write_text(
            json.dumps({"ocpus": float(profile["ocpus"]), "memoryInGBs": float(profile["memory"])}),
            encoding="utf-8",
        )
        availability_file.write_text('{"recoveryAction":"RESTORE_INSTANCE"}', encoding="utf-8")
        options_file.write_text('{"areLegacyImdsEndpointsDisabled":false}', encoding="utf-8")
        self.log(f"TRY - Launch {profile['name']} on {target.name}/{target.region or 'default'} {profile['ocpus']} OCPU / {profile['memory']} GB")
        return self.oci([
            "compute", "instance", "launch",
            "--availability-domain", target.availability_domain,
            "--compartment-id", target.compartment_id,
            "--shape", self.shape,
            "--shape-config", f"file://{shape_file}",
            "--image-id", target.image_id,
            "--subnet-id", target.subnet_id,
            "--assign-public-ip", "true",
            "--availability-config", f"file://{availability_file}",
            "--instance-options", f"file://{options_file}",
            "--display-name", str(profile["name"]),
            "--ssh-authorized-keys-file", self.ssh_key_file,
        ], target=target)

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
                target, instance = existing
                self.log(f"SUCCESS! Existing instance found on {target.name}/{target.region or 'default'}: {instance.get('id')} ({instance.get('display-name')})")
                return 0

            all_statuses: dict[str, dict[str, str]] = {}
            for target in self.targets:
                statuses = self.capacity_statuses(target)
                all_statuses[target.name] = statuses
                for profile in self.profiles:
                    self.log(
                        f"INFO - Capacity report {target.name}/{target.region or 'default'} "
                        f"{profile['name']} {profile_key(profile)}: {statuses[profile_key(profile)]}"
                    )

            pairs = [(target, profile) for target in self.targets for profile in self.profiles]
            pair_index = int(state.get("pairIndex", state.get("profileIndex", 0))) % len(pairs)
            launch_pairs = [pairs[(pair_index + i) % len(pairs)] for i in range(min(self.max_launches, len(pairs)))]
            next_pair_index = (pair_index + len(launch_pairs)) % len(pairs)

            saw_capacity = saw_throttle = saw_limit = saw_error = False
            for target, profile in launch_pairs:
                status = all_statuses.get(target.name, {}).get(profile_key(profile), "UNKNOWN")
                if self.capacity_mode == "gate" and status != "AVAILABLE":
                    self.log(
                        f"SKIP - Capacity gate blocked {target.name}/{target.region or 'default'} "
                        f"{profile['name']} ({profile_key(profile)}): {status}"
                    )
                    saw_capacity = True
                    continue
                output = self.launch(target, profile)
                if re.search(r"Out of host capacity|Out of capacity|out of capacity|InternalError", output):
                    self.log(f"FAIL - Out of capacity for {target.name}/{profile['name']} (will retry)")
                    saw_capacity = True
                elif re.search(r"TooManyRequests|User-rate limit|status\"?:\\s*429", output):
                    self.log(f"THROTTLED - TooManyRequests while launching {target.name}/{profile['name']}")
                    saw_throttle = True
                elif re.search(r"LimitExceeded|service limits were exceeded|standard-a1-(memory|core)", output):
                    self.log(f"LIMIT - Service limit exceeded while launching {target.name}/{profile['name']}: {compact(output)}")
                    saw_limit = True
                elif re.search(r"NotAuthorizedOrNotFound|Authorization failed or requested resource not found", output):
                    self.log(f"CONFIG - Launch blocked by authorization/resource mismatch for {target.name}/{profile['name']}: {compact(output)}")
                    if self.stop_on_config_error:
                        self.write_state(
                            "config_error",
                            now_kst() + timedelta(days=365),
                            pairIndex=next_pair_index,
                            lastError=compact(output),
                        )
                        self.log("STOP - Repeated launches paused until OCI ids, region, image, subnet, and policies are fixed")
                        return 2
                    saw_error = True
                elif '"lifecycle-state"' in output:
                    instance_id = extract_instance_id(output)
                    self.log(f"SUCCESS! Instance ID: {instance_id} ({target.name}/{profile['name']}, {profile_key(profile)})")
                    self.write_state("success", now_kst() + timedelta(days=365), pairIndex=next_pair_index)
                    return 0
                elif self.dry_run:
                    self.log(f"DRYRUN - Completed command generation for {target.name}/{profile['name']}")
                else:
                    self.log(f"ERROR - Launch failed for {target.name}/{profile['name']}: {compact(output)}")
                    saw_error = True

            if self.dry_run:
                self.log("DRYRUN - Finished without OCI launch")
                return 0
            if saw_throttle:
                minutes = random.randint(45, 75)
                self.write_state("throttled", now_kst() + timedelta(minutes=minutes), pairIndex=next_pair_index)
                self.log(f"NEXT - Cooldown {minutes}m due to throttling")
            elif saw_limit:
                minutes = random.randint(360, 720)
                self.write_state("limit", now_kst() + timedelta(minutes=minutes), pairIndex=next_pair_index)
                self.log(f"NEXT - Cooldown {minutes}m due to service limit")
            elif saw_capacity:
                self.write_state("capacity", now_kst() + timedelta(minutes=random.randint(4, 8)), pairIndex=next_pair_index)
            elif saw_error:
                self.write_state("error", now_kst() + timedelta(minutes=random.randint(10, 20)), pairIndex=next_pair_index)
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
            target, instance = current
            current_text = f"{target.name}/{target.region or 'default'} {instance.get('display-name')} / {instance.get('lifecycle-state')}"
            instance_id = instance.get("id") or "-"
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


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", text or "target").strip("-") or "target"


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
    parser.add_argument("command", choices=["attempt", "report", "test-slack", "diagnose"])
    parser.add_argument("--root", default=os.getenv("OCI_RETRY_ROOT", str(Path(__file__).resolve().parent)))
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ignore-cooldown", action="store_true")
    parser.add_argument("--no-sleep", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    venv_bin = root / ".venv" / "bin"
    if venv_bin.is_dir():
        os.environ["PATH"] = f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}"
    load_env(Path(args.env_file) if args.env_file else root / ".env")
    app = RetryApp(root=root, dry_run=args.dry_run)
    if args.command == "attempt":
        return app.attempt(ignore_cooldown=args.ignore_cooldown, no_sleep=args.no_sleep)
    if args.command == "report":
        return app.send_report(test=False)
    if args.command == "test-slack":
        return app.send_report(test=True)
    if args.command == "diagnose":
        return app.diagnose()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
