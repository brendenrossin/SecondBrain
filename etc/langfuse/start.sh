#!/bin/bash
# Bring Langfuse up at login, then restart the API so its startup probe sees it.
# Run by com.secondbrain.langfuse (KeepAlive SuccessfulExit=false): a non-zero exit is
# retried by launchd after ThrottleInterval. stdout/stderr go to data/langfuse.log.
# Spec: docs/specs/002-langfuse-starts-reliably-at-login.md
set -u

DOCKER_TIMEOUT="${LANGFUSE_DOCKER_TIMEOUT:-180}"
HEALTH_TIMEOUT="${LANGFUSE_HEALTH_TIMEOUT:-180}"
POLL_INTERVAL="${LANGFUSE_POLL_INTERVAL:-2}"
HEALTH_URL="${LANGFUSE_HEALTH_URL:-http://localhost:3000/api/public/health}"
API_LABEL="com.secondbrain.api"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') langfuse-start: $*"; }

# wait_for <timeout-seconds> <command...>: poll until the command succeeds or time runs out.
wait_for() {
    local timeout="$1"; shift
    local start=$SECONDS
    until "$@" >/dev/null 2>&1; do
        if (( SECONDS - start >= timeout )); then
            return 1
        fi
        sleep "$POLL_INTERVAL"
    done
}

cd "$(dirname "$0")" || { log "cannot cd to compose dir"; exit 1; }

if ! docker info >/dev/null 2>&1; then
    log "docker daemon not running; starting Docker Desktop"
    open -a Docker
    if ! wait_for "$DOCKER_TIMEOUT" docker info; then
        log "docker daemon not ready after ${DOCKER_TIMEOUT}s"
        exit 1
    fi
fi
log "docker daemon ready"

if ! docker compose up -d --wait; then
    log "compose up failed"
    exit 1
fi
log "compose up done"

if ! wait_for "$HEALTH_TIMEOUT" curl -fsS -o /dev/null --max-time 5 "$HEALTH_URL"; then
    log "langfuse not healthy after ${HEALTH_TIMEOUT}s"
    exit 1
fi
log "langfuse healthy; restarting $API_LABEL"

if ! launchctl kickstart -k "gui/$(id -u)/$API_LABEL"; then
    log "kickstart $API_LABEL failed"
    exit 1
fi
log "done"
