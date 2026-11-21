"""Spec 002: etc/langfuse/start.sh against fake docker/open/curl/launchctl, plus the plist."""

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "etc" / "langfuse" / "start.sh"
PLIST = REPO / "com.secondbrain.langfuse.plist"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

# Each fake appends "<name> <pwd> <argv>" to $FAKE_LOG. Behaviour comes from env vars:
#   DOCKER_INFO_FAILS=N   `docker info` fails N times, then succeeds (-1 = always fails)
#   COMPOSE_EXIT=N        exit code of `docker compose ...`
#   CURL_FAILS=N          curl fails N times, then succeeds (-1 = always fails)
FAKE = r"""#!/bin/bash
echo "$(basename "$0") $PWD $*" >> "$FAKE_LOG"
countdown() {  # countdown <counter-file> <fails>: succeed once <fails> calls have failed
    local n; n=$(cat "$1" 2>/dev/null || echo 0); echo $((n + 1)) > "$1"
    [ "$2" -ge 0 ] && [ "$n" -ge "$2" ]
}
case "$(basename "$0")" in
  docker)
    if [ "$1" = info ]; then countdown "$FAKE_DIR/docker_info.n" "${DOCKER_INFO_FAILS:-0}"; exit; fi
    if [ "$1" = compose ]; then exit "${COMPOSE_EXIT:-0}"; fi ;;
  curl) countdown "$FAKE_DIR/curl.n" "${CURL_FAILS:-0}" || exit 22 ;;
esac
exit 0
"""


def run(tmp_path: Path, **env: str) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("docker", "open", "curl", "launchctl"):
        fake = bin_dir / name
        fake.write_text(FAKE)
        fake.chmod(0o755)
    fake_log = tmp_path / "calls.log"
    full_env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "FAKE_LOG": str(fake_log),
        "FAKE_DIR": str(tmp_path),
        "LANGFUSE_DOCKER_TIMEOUT": "2",
        "LANGFUSE_HEALTH_TIMEOUT": "2",
        "LANGFUSE_POLL_INTERVAL": "0.1",
        **env,
    }
    proc = subprocess.run(
        ["/bin/bash", str(SCRIPT)], env=full_env, capture_output=True, text=True, timeout=30
    )
    calls = fake_log.read_text().splitlines() if fake_log.exists() else []
    return proc, calls


def named(calls: list[str], name: str) -> list[str]:
    return [c for c in calls if c.startswith(name + " ")]


def test_docker_down_then_everything_comes_up(tmp_path):
    proc, calls = run(tmp_path, DOCKER_INFO_FAILS="3")  # first check + 2 polls fail
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert len(named(calls, "open")) == 1
    assert named(calls, "open")[0].endswith("-a Docker")
    compose = [c for c in named(calls, "docker") if " compose " in c]
    assert compose == [f"docker {SCRIPT.parent} compose up -d --wait"]
    kick = named(calls, "launchctl")
    assert kick == [
        f"launchctl {SCRIPT.parent} kickstart -k gui/{os.getuid()}/com.secondbrain.api"
    ]
    assert calls.index(kick[0]) > max(calls.index(c) for c in named(calls, "curl"))


def test_docker_already_running(tmp_path):
    proc, calls = run(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert named(calls, "open") == []
    assert len(named(calls, "launchctl")) == 1


def test_docker_never_comes_up(tmp_path):
    proc, calls = run(tmp_path, DOCKER_INFO_FAILS="-1")
    assert proc.returncode != 0
    assert "docker daemon not ready after 2s" in proc.stdout.strip().splitlines()[-1]
    assert not [c for c in named(calls, "docker") if " compose " in c]
    assert named(calls, "launchctl") == []


def test_compose_fails(tmp_path):
    proc, calls = run(tmp_path, COMPOSE_EXIT="1")
    assert proc.returncode != 0
    assert "compose up failed" in proc.stdout
    assert named(calls, "launchctl") == []


def test_langfuse_never_healthy(tmp_path):
    proc, calls = run(tmp_path, CURL_FAILS="-1")
    assert proc.returncode != 0
    assert "langfuse not healthy after 2s" in proc.stdout
    assert named(calls, "launchctl") == []


def test_plist_retries_failures_but_not_success():
    plist = plistlib.loads(PLIST.read_bytes())
    repo = "/Users/brentrossin/code/second-brain"
    assert plist["Label"] == "com.secondbrain.langfuse"
    assert plist["ProgramArguments"] == ["/bin/bash", f"{repo}/etc/langfuse/start.sh"]
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert plist["ThrottleInterval"] == 60
    assert plist["RunAtLoad"] is True
    assert plist["WorkingDirectory"] == f"{repo}/etc/langfuse"
    path = plist["EnvironmentVariables"]["PATH"].split(":")
    assert "/usr/local/bin" in path
    assert "/Applications/Docker.app/Contents/Resources/bin" in path
