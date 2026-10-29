#!/usr/bin/env bash
# Smoke-test the Aegis Guard gateway end to end.
#
# Usage: smoke.sh [--port N] [--keep] [--no-cache] [--ollama-url URL]
#        smoke.sh --stop [--port N]
#
# - If nothing listens on the port, starts `poetry run uvicorn src.proxy.main:app`
#   from the repo root in the background, and stops it at the end unless --keep
#   is given. If something already listens there (local uvicorn or
#   `docker compose up`), tests it as-is and leaves it running.
# - --no-cache starts that server with DISABLE_SEMANTIC_CACHE=true, so the
#   completions reach the LLM. It has no effect on a server already running.
# - --ollama-url URL sets OLLAMA_BASE_URL for the server it starts (overriding
#   .env) and the Ollama probe, e.g. http://localhost:11434.
# - --stop stops a gateway that this script started with --keep, and leaves
#   any other listener (Docker, another app) alone.
# - Checks GET /health, GET /metrics, and that requests without a key or with
#   an invalid key are rejected. When Ollama answers with the model pulled,
#   also sends one JSON and one streaming chat completion with the seeded dev
#   key; both count against the key's 5 RPM.
# - Exit code 0 means every check that ran passed.
#
# Env overrides: AEGIS_API_KEY (default: the seed.py key), AEGIS_MODEL
# (default llama3), OLLAMA_URL (default: $OLLAMA_BASE_URL, else localhost).
set -uo pipefail

PORT=8000
KEEP=0
STOP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="${2:-}"; shift; [ $# -gt 0 ] && shift ;;
    --keep) KEEP=1; shift ;;
    --no-cache) export DISABLE_SEMANTIC_CACHE=true; shift ;;
    --ollama-url) export OLLAMA_BASE_URL="${2:-}" OLLAMA_URL="${2:-}"; shift; [ $# -gt 0 ] && shift ;;
    --stop) STOP=1; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 64 ;;
  esac
done
case "$PORT" in
  ''|*[!0-9]*) echo "--port needs a number, got: '$PORT'" >&2; exit 64 ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
BASE="http://127.0.0.1:${PORT}"
API_KEY="${AEGIS_API_KEY:-ak_live_dario123456789}"
MODEL="${AEGIS_MODEL:-llama3}"
OLLAMA_URL="${OLLAMA_URL:-${OLLAMA_BASE_URL:-http://127.0.0.1:11434}}"
TMP_DIR="${TMPDIR:-/tmp}"
LOG="${TMP_DIR%/}/aegis-guard-smoke-${PORT}.log"
SERVER_PID=""
FAILED=0

ok()   { printf '  ok    %s\n' "$1"; }
bad()  { printf '  FAIL  %s\n' "$1"; FAILED=$((FAILED + 1)); }
skip() { printf '  skip  %s\n' "$1"; }

listener_pids() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null; }

# True when pid $1 is a gateway started by this script on $PORT.
is_own_gateway() {
  ps -ww -o command= -p "$1" 2>/dev/null | grep -Eq "uvicorn src\.proxy\.main:app --host 127\.0\.0\.1 --port ${PORT}\$"
}

# SIGTERM pid $1 and wait up to 5 s for uvicorn's graceful shutdown.
# Returns 0 when it stopped, 1 when it is still running, 2 when it wasn't running.
stop_pid() {
  kill "$1" 2>/dev/null || return 2
  for _ in $(seq 1 20); do
    kill -0 "$1" 2>/dev/null || return 0
    sleep 0.25
  done
  echo "the gateway on :$PORT (pid $1) is still shutting down" >&2
  return 1
}

# --- STOP MODE ---
if [ "$STOP" -eq 1 ]; then
  found=0
  for pid in $(listener_pids); do
    if is_own_gateway "$pid"; then
      stop_pid "$pid" && echo "stopped the gateway on :$PORT (pid $pid)"
      found=1
    else
      echo "pid $pid on :$PORT was not started by smoke.sh; leaving it running" >&2
    fi
  done
  [ "$found" -eq 1 ] || echo "no smoke.sh gateway is listening on :$PORT"
  exit 0
fi

BODY="$(mktemp "${TMP_DIR%/}/aegis-guard-smoke-body.XXXXXX")"

cleanup() {
  rm -f "$BODY"
  if [ -n "$SERVER_PID" ] && [ "$KEEP" -eq 0 ]; then
    stop_pid "$SERVER_PID" && echo "stopped the gateway on :$PORT"
  fi
}
trap cleanup EXIT

# Print the HTTP status code; the response body goes to $BODY.
request() {
  local method="$1" path="$2"
  shift 2
  curl -s -m 60 -o "$BODY" -w '%{http_code}' -X "$method" "$BASE$path" "$@"
}

# Short provider/status summary from the _aegis_guard_meta field of the last JSON body.
meta() {
  command -v jq >/dev/null 2>&1 || return 0
  jq -r '"(provider=\(._aegis_guard_meta.provider // "?"), status=\(._aegis_guard_meta.status // "?"))"' "$BODY" 2>/dev/null
}

# True when Ollama lists a model whose name is $1 (any tag).
has_model() {
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$TAGS" | jq -r '.models[]?.name' 2>/dev/null | grep -Eq "^$1(:|$)"
  else
    printf '%s' "$TAGS" | grep -Eq "\"name\": ?\"$1(:|\")"
  fi
}

# --- LAUNCH ---
if [ -n "$(listener_pids)" ]; then
  echo "testing the server already listening on :$PORT"
  [ "${DISABLE_SEMANTIC_CACHE:-}" = "true" ] && echo "note: --no-cache only applies to a server this script starts"
else
  echo "starting the gateway on :$PORT (log: $LOG)"
  # `exec` makes the background job become uvicorn itself, so $! is its pid.
  (cd "$REPO_ROOT" && exec nohup poetry run uvicorn src.proxy.main:app --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1) &
  SERVER_PID=$!
  disown
  ready=0
  for _ in $(seq 1 60); do
    if curl -sf -m 1 -o /dev/null "$BASE/health"; then ready=1; break; fi
    kill -0 "$SERVER_PID" 2>/dev/null || break
    sleep 0.5
  done
  if [ "$ready" -ne 1 ]; then
    echo "the gateway did not become healthy within 30 s; last log lines:" >&2
    tail -n 20 "$LOG" >&2
    exit 1
  fi
fi

# --- CHECKS ---
echo "checks against $BASE:"

code=$(request GET /health)
if [ "$code" = "200" ] && grep -q '"healthy"' "$BODY"; then
  ok "GET /health -> 200"
else
  bad "GET /health -> $code $(head -c 200 "$BODY")"
fi

code=$(request GET /metrics)
if [ "$code" = "200" ] && grep -q 'aegis_guard_requests_total' "$BODY"; then
  ok "GET /metrics -> 200 with aegis_guard_* metrics"
else
  bad "GET /metrics -> $code"
fi

ping_payload='{"model": "'"$MODEL"'", "messages": [{"role": "user", "content": "ping"}]}'
code=$(request POST /v1/chat/completions -H 'Content-Type: application/json' -d "$ping_payload")
case "$code" in
  401|403) ok "POST /v1/chat/completions without a key -> $code" ;;
  *) bad "POST /v1/chat/completions without a key -> $code (expected 401 or 403)" ;;
esac

code=$(request POST /v1/chat/completions -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer ak_invalid_smoke_test' -d "$ping_payload")
if [ "$code" = "401" ]; then
  ok "POST /v1/chat/completions with an invalid key -> 401"
else
  bad "POST /v1/chat/completions with an invalid key -> $code (expected 401)"
fi

if ! TAGS=$(curl -sf -m 2 "$OLLAMA_URL/api/tags" 2>/dev/null); then
  skip "chat completions: Ollama is not reachable at $OLLAMA_URL (no completion was tested)"
elif ! has_model "$MODEL"; then
  skip "chat completions: model '$MODEL' is not pulled (ollama pull $MODEL)"
else
  has_model nomic-embed-text || skip "semantic cache: nomic-embed-text is not pulled, so requests go straight to the LLM"
  auth=(-H 'Content-Type: application/json' -H "Authorization: Bearer $API_KEY")

  code=$(request POST /v1/chat/completions "${auth[@]}" \
    -d '{"model": "'"$MODEL"'", "messages": [{"role": "user", "content": "Reply with the single word: pong"}], "stream": false}')
  case "$code" in
    200)
      if grep -q '"chat.completion"' "$BODY"; then
        ok "chat completion, stream=false -> 200 $(meta)"
      else
        bad "chat completion, stream=false -> 200 but not a chat.completion body: $(head -c 200 "$BODY")"
      fi ;;
    401) bad "chat completion -> 401: seed the dev key first (poetry run python seed.py)" ;;
    429) bad "chat completion -> 429: the key's per-minute limit is used up; retry in a minute" ;;
    502) bad "chat completion -> 502 $(head -c 300 "$BODY") (if Ollama is up, check the server's OLLAMA_BASE_URL)" ;;
    *) bad "chat completion, stream=false -> $code $(head -c 300 "$BODY")" ;;
  esac

  code=$(request POST /v1/chat/completions "${auth[@]}" \
    -d '{"model": "'"$MODEL"'", "messages": [{"role": "user", "content": "Count from 1 to 3."}], "stream": true}')
  if [ "$code" = "200" ] && grep -q 'data: \[DONE\]' "$BODY" && ! grep -q '"error"' "$BODY"; then
    if grep -q '"semantic_cache"' "$BODY"; then src="served from the semantic cache"; else src="live from the LLM"; fi
    ok "chat completion, stream=true -> 200, $(grep -c 'chat.completion.chunk' "$BODY") SSE chunks ending in [DONE], $src"
  elif [ "$code" = "429" ]; then
    bad "chat completion, stream=true -> 429: the key's per-minute limit is used up; retry in a minute"
  else
    bad "chat completion, stream=true -> $code $(grep -m1 '"error"' "$BODY" | head -c 300)"
  fi
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "smoke test passed"
else
  echo "smoke test: $FAILED check(s) failed"
fi
if [ -n "$SERVER_PID" ]; then echo "server log: $LOG"; fi
if [ "$FAILED" -eq 0 ]; then exit 0; else exit 1; fi
