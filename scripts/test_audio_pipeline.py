#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit("This script requires the 'requests' package.") from exc


DEFAULT_AUDIO = "/home/noted/audio_07085_0-60s_focus-Alice_other.wav"
DEFAULT_BACKEND_BASE = "http://127.0.0.1:8000/api/v1"
DEFAULT_LOGIN = os.getenv("DEMO_LOGIN", "demo")
DEFAULT_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1")
BACKEND_CONTAINER = "noted-backend"

CONTAINERS = [
    "noted-backend",
    "noted-frontend",
    "qwen3-asr",
    "sortformer-diarizer",
    "llama-gen",
    "vllm-embed",
    "qdrant",
]


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    extra: Optional[Dict[str, Any]] = None


class Report:
    def __init__(self) -> None:
        self.results: List[CheckResult] = []

    def add(self, name: str, ok: bool, detail: str, **extra: Any) -> None:
        self.results.append(CheckResult(name=name, ok=ok, detail=detail, extra=extra or None))
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        if extra:
            print(json.dumps(extra, indent=2, sort_keys=True))

    @property
    def failures(self) -> List[CheckResult]:
        return [result for result in self.results if not result.ok]

    def summary(self) -> Dict[str, Any]:
        return {
            "passed": len(self.results) - len(self.failures),
            "failed": len(self.failures),
            "results": [
                {
                    "name": result.name,
                    "ok": result.ok,
                    "detail": result.detail,
                    "extra": result.extra,
                }
                for result in self.results
            ],
        }


def run_command(cmd: List[str], *, input_text: Optional[str] = None, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def docker_inspect(container: str) -> Dict[str, Any]:
    proc = run_command(["docker", "inspect", container], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"docker inspect failed for {container}")
    payload = json.loads(proc.stdout)
    return payload[0]


def docker_exec_python(container: str, code: str, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    return run_command(["docker", "exec", "-i", container, "python3", "-"], input_text=code, timeout=timeout)


def docker_cp_to_container(container: str, local_path: Path, remote_path: str) -> None:
    proc = run_command(["docker", "cp", str(local_path), f"{container}:{remote_path}"], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"docker cp failed to {container}:{remote_path}")


def tail_logs(container: str, lines: int = 80) -> str:
    proc = run_command(["docker", "logs", f"--tail={lines}", container], timeout=60)
    return (proc.stdout or "") + (proc.stderr or "")


def check_containers(report: Report) -> None:
    for container in CONTAINERS:
        try:
            inspect = docker_inspect(container)
        except Exception as exc:
            report.add(f"container:{container}", False, str(exc))
            continue

        state = inspect.get("State", {})
        status = state.get("Status", "unknown")
        health = (state.get("Health") or {}).get("Status")
        networks = sorted((inspect.get("NetworkSettings") or {}).get("Networks", {}).keys())
        ok = status == "running" and (health in (None, "healthy"))
        detail = f"status={status}, health={health or 'n/a'}, networks={','.join(networks) or 'none'}"
        report.add(f"container:{container}", ok, detail)


def check_backend_health(report: Report, backend_base: str) -> None:
    try:
        response = requests.get("http://127.0.0.1:8000/health", timeout=10)
        response.raise_for_status()
        report.add("backend:health", True, "backend /health responded", response=response.json())
    except Exception as exc:
        report.add("backend:health", False, str(exc))

    try:
        login_response = requests.post(
            f"{backend_base}/auth/login",
            json={"username": DEFAULT_LOGIN, "password": DEFAULT_PASSWORD},
            timeout=20,
        )
        login_response.raise_for_status()
        payload = login_response.json()
        token = payload["access_token"]
        report.add("backend:login", True, "login succeeded", user=payload.get("user"))
        return token
    except Exception as exc:
        report.add("backend:login", False, str(exc))
        return None


def test_internal_services(report: Report, remote_audio_path: str) -> None:
    model_checks = {
        "qwen-asr-models": "http://qwen3-asr:8000/v1/models",
        "embed-models": "http://vllm-embed:8000/v1/models",
        "gen-models": "http://llama-gen:8000/v1/models",
        "qdrant-root": "http://qdrant:6333",
        "sortformer-health": "http://sortformer-diarizer:8010/health",
    }

    for name, url in model_checks.items():
        code = f"""
import json, urllib.request
with urllib.request.urlopen({url!r}, timeout=20) as response:
    payload = response.read().decode("utf-8")
print(payload)
"""
        proc = docker_exec_python(BACKEND_CONTAINER, code, timeout=60)
        if proc.returncode == 0:
            report.add(f"internal:{name}", True, f"reachable: {url}")
        else:
            report.add(f"internal:{name}", False, proc.stderr.strip() or proc.stdout.strip() or f"failed: {url}")

    asr_code = f"""
import json
from openai import OpenAI

client = OpenAI(base_url="http://qwen3-asr:8000/v1", api_key="none")
with open({remote_audio_path!r}, "rb") as audio_file:
    response = client.audio.transcriptions.create(
        model="Qwen/Qwen3-ASR-0.6B",
        file=audio_file,
        response_format="json",
        temperature=0.0,
    )

payload = response.model_dump() if hasattr(response, "model_dump") else response
segments = payload.get("segments", []) if isinstance(payload, dict) else []
print(json.dumps({{
    "segment_count": len(segments),
    "language": payload.get("language") if isinstance(payload, dict) else None,
    "text_preview": (payload.get("text") or "")[:240] if isinstance(payload, dict) else "",
}}, indent=2))
"""
    asr_proc = docker_exec_python(BACKEND_CONTAINER, asr_code, timeout=300)
    if asr_proc.returncode == 0:
        try:
            payload = json.loads(asr_proc.stdout)
        except json.JSONDecodeError:
            payload = {"raw": asr_proc.stdout[-1000:]}
        report.add("internal:asr-transcription", True, "direct ASR transcription succeeded", **payload)
    else:
        report.add("internal:asr-transcription", False, asr_proc.stderr.strip() or asr_proc.stdout.strip())

    diar_code = f"""
import json
import httpx

with open({remote_audio_path!r}, "rb") as audio_file:
    response = httpx.post(
        "http://sortformer-diarizer:8010/diarize",
        data={{"session_id": "pipeline-test", "model": "nvidia/diar_streaming_sortformer_4spk-v2.1", "max_speakers": "2"}},
        files={{"file": ("audio.wav", audio_file, "audio/wav")}},
        timeout=240.0,
    )

response.raise_for_status()
payload = response.json()
segments = payload.get("segments", []) if isinstance(payload, dict) else []
print(json.dumps({{
    "segment_count": len(segments),
    "first_segment": segments[0] if segments else None,
}}, indent=2))
"""
    diar_proc = docker_exec_python(BACKEND_CONTAINER, diar_code, timeout=360)
    if diar_proc.returncode == 0:
        try:
            payload = json.loads(diar_proc.stdout)
        except json.JSONDecodeError:
            payload = {"raw": diar_proc.stdout[-1000:]}
        report.add("internal:diarization", True, "direct diarization succeeded", **payload)
    else:
        report.add("internal:diarization", False, diar_proc.stderr.strip() or diar_proc.stdout.strip())


def test_backend_upload(report: Report, backend_base: str, token: str, audio_path: Path) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    session_name = f"PIPE-TEST-{int(time.time())}"

    try:
        create_response = requests.post(
            f"{backend_base}/sessions",
            params={"session_name": session_name},
            headers=headers,
            timeout=30,
        )
        create_response.raise_for_status()
        session_payload = create_response.json()
        session_identifier = session_payload["session_name"]
        report.add("backend:create-session", True, f"created {session_identifier}", session=session_payload)
    except Exception as exc:
        report.add("backend:create-session", False, str(exc))
        return

    try:
        with audio_path.open("rb") as audio_file:
            upload_response = requests.post(
                f"{backend_base}/sessions/{session_identifier}/upload-audio",
                headers=headers,
                files={"file": (audio_path.name, audio_file, "audio/wav")},
                timeout=120,
            )
        upload_response.raise_for_status()
        report.add("backend:upload-audio", True, "upload accepted", response=upload_response.json())
    except Exception as exc:
        report.add("backend:upload-audio", False, str(exc))
        return

    last_progress: Dict[str, Any] = {}
    last_session: Dict[str, Any] = {}
    deadline = time.time() + 240
    final_status = None

    while time.time() < deadline:
        try:
            session_response = requests.get(
                f"{backend_base}/sessions/{session_identifier}",
                headers=headers,
                timeout=20,
            )
            session_response.raise_for_status()
            last_session = session_response.json()
            final_status = last_session.get("status")
        except Exception as exc:
            report.add("backend:poll-session", False, str(exc))
            return

        try:
            progress_response = requests.get(
                f"{backend_base}/sessions/{session_identifier}/progress",
                headers=headers,
                timeout=20,
            )
            if progress_response.ok:
                last_progress = progress_response.json()
        except Exception:
            pass

        if final_status in {"completed", "error"}:
            break

        time.sleep(5)

    ok = final_status == "completed"
    report.add(
        "backend:processing-status",
        ok,
        f"final session status={final_status}",
        session=last_session,
        progress=last_progress,
    )

    if not ok:
        return

    try:
        transcript_response = requests.get(
            f"{backend_base}/sessions/{session_identifier}/transcript",
            headers=headers,
            timeout=30,
        )
        transcript_response.raise_for_status()
        transcript = transcript_response.json()
        preview = transcript[:3]
        distinct_speakers = sorted(
            {
                str(item.get("speaker", "")).strip()
                for item in transcript
                if str(item.get("speaker", "")).strip()
            }
        )
        report.add(
            "backend:transcript",
            len(transcript) > 0,
            f"transcript entries={len(transcript)}",
            preview=preview,
            distinct_speakers=distinct_speakers,
        )
    except Exception as exc:
        report.add("backend:transcript", False, str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise the Noted audio pipeline against a WAV file.")
    parser.add_argument("--audio", default=DEFAULT_AUDIO, help="Path to WAV file to upload/test.")
    parser.add_argument("--backend-base", default=DEFAULT_BACKEND_BASE, help="Direct backend API base URL.")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON summary at the end.")
    args = parser.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"Audio file not found: {audio_path}", file=sys.stderr)
        return 2

    if shutil.which("docker") is None:
        print("docker is required on PATH for this script.", file=sys.stderr)
        return 2

    report = Report()
    print(f"Testing audio pipeline with {audio_path}")

    check_containers(report)

    remote_audio_path = "/tmp/noted_pipeline_test.wav"
    try:
        docker_cp_to_container(BACKEND_CONTAINER, audio_path, remote_audio_path)
        report.add("docker:copy-audio", True, f"copied audio to {BACKEND_CONTAINER}:{remote_audio_path}")
    except Exception as exc:
        report.add("docker:copy-audio", False, str(exc))
        if args.json_output:
            print(json.dumps(report.summary(), indent=2, sort_keys=True))
        return 1

    token = check_backend_health(report, args.backend_base)
    test_internal_services(report, remote_audio_path)

    if token:
        test_backend_upload(report, args.backend_base, token, audio_path)

    for container in ("noted-backend", "qwen3-asr", "sortformer-diarizer"):
        if any(result.name.startswith("backend:") and not result.ok for result in report.results):
            report.add(f"logs:{container}", True, f"tailing {container} logs for debugging", tail=tail_logs(container))

    if args.json_output:
        print(json.dumps(report.summary(), indent=2, sort_keys=True))

    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
