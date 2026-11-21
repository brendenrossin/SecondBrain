---
id: '002'
title: Langfuse starts reliably at login
project: second-brain
tier: quick
status: Draft
version: 0.1.0
created: '2026-11-21'
updated: '2026-11-21'
tags: []
history:
- status: Draft
  date: '2026-11-21'
  note: created
---
# 002 — Langfuse starts reliably at login

## Intent
`com.secondbrain.langfuse` exits 1 at every login. It runs `docker compose up --wait` once
(RunAtLoad, no KeepAlive). Docker Desktop has `AutoStart: false`, so the daemon is never up, and
`data/langfuse.log` shows "Cannot connect to the Docker daemon". Even when Docker is up, the API
checks Langfuse reachability **only at its own startup** (`tracing.py` `_langfuse_reachable`, PR #14).
The API starts in seconds and Langfuse's 6 containers take a minute or more, so the API settles on
JSONL-only tracing.

Brent chose **always-on** (2026-11-21). The fix is to replace the job's one-shot command with a repo
script, `etc/langfuse/start.sh`, which does four things:
1. Starts Docker Desktop if its daemon isn't up (`open -a Docker`). Docker's own AutoStart setting is
   left untouched.
2. Waits for the daemon, then runs `docker compose up -d --wait`.
3. Waits for Langfuse's health endpoint.
4. Restarts `com.secondbrain.api`, so the API's startup probe sees Langfuse and attaches the OTLP
   exporter.

launchd re-runs the script after a failure (`KeepAlive.SuccessfulExit=false`, 60s throttle). Tracing
stays optional: if any step times out, the API keeps its JSONL-only fallback. Nothing in spec 001
depends on Langfuse. The plist moves into the repo so it's versioned like the other three.

Timeouts: 180s for the Docker daemon and 180s for Langfuse health. They can be overridden with
`LANGFUSE_DOCKER_TIMEOUT` and `LANGFUSE_HEALTH_TIMEOUT` so tests run fast. The script logs to
`data/langfuse.log`, one timestamped line per step.

## Acceptance Criteria
```gherkin
Feature: Langfuse start script

  # Tests run etc/langfuse/start.sh with fake `docker`, `open`, `curl` and `launchctl` executables
  # first on PATH. Each fake records its argv to a file. Timeouts are set to 2s.

  Scenario: Docker is down at login, then everything comes up
    Given `docker info` fails twice and then succeeds
    And the health check returns 200 on its first call
    When start.sh runs
    Then it exits 0
    And `open -a Docker` was called exactly once
    And `docker compose up -d --wait` ran in etc/langfuse
    And `launchctl kickstart -k gui/{uid}/com.secondbrain.api` was called exactly once, after the health check passed

  Scenario: Docker is already running
    Given `docker info` succeeds immediately and health returns 200
    When start.sh runs
    Then it exits 0 and `open` was never called

  Scenario: Docker never comes up
    Given `docker info` always fails and LANGFUSE_DOCKER_TIMEOUT is 2
    When start.sh runs
    Then it exits non-zero
    And the log's last line contains "docker daemon not ready after 2s"
    And neither `docker compose` nor `launchctl` was called

  Scenario: compose fails
    Given `docker info` succeeds and `docker compose up` exits 1
    When start.sh runs
    Then it exits non-zero, the log contains "compose up failed", and `launchctl` was not called

  Scenario: Langfuse never turns healthy
    Given compose succeeds, curl always returns 503, and LANGFUSE_HEALTH_TIMEOUT is 2
    When start.sh runs
    Then it exits non-zero
    And the log contains "langfuse not healthy after 2s"
    And `launchctl` was not called, so the API keeps its JSONL-only fallback

  Scenario: the plist retries failures but not success
    When com.secondbrain.langfuse.plist is parsed with plistlib
    Then ProgramArguments is ["/bin/bash", "{repo}/etc/langfuse/start.sh"] where {repo} is the repo root
    And KeepAlive is {"SuccessfulExit": false}, ThrottleInterval is 60 and RunAtLoad is true
    And WorkingDirectory is {repo}/etc/langfuse
    And PATH includes /usr/local/bin and /Applications/Docker.app/Contents/Resources/bin

  Scenario: live check after install (verify-time, manual)
    Given the new plist is installed and loaded, and Docker Desktop is quit
    When `launchctl kickstart -k gui/$(id -u)/com.secondbrain.langfuse` runs
    Then within 5 minutes `curl -s localhost:3000/api/public/health` returns 200
    And data/logs/api.stderr.log shows "Langfuse tracing enabled" after the restart
    And `launchctl list | grep langfuse` shows exit status 0
```

## Files
| File | Action | Note |
|---|---|---|
| `etc/langfuse/start.sh` | New | wait for Docker → compose up → wait for health → kickstart API |
| `com.secondbrain.langfuse.plist` | New | versioned copy of the job: bash + start.sh, KeepAlive SuccessfulExit=false, 60s throttle |
| `tests/test_langfuse_start.py` | New | runs start.sh against fake binaries on PATH; checks the plist |
| `.witt/PROJECT.md` | Update | Langfuse row and known issue reflect the fix |
