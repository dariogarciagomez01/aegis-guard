#!/usr/bin/env bash
# SessionStart hook: print a short live status of this repo's environment.
# A SessionStart hook's plain stdout is added to Claude's context.
# Every probe has a 1 s timeout, so a stopped service costs almost nothing.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" 2>/dev/null || exit 0

# --- GIT ---
branch=$(git branch --show-current 2>/dev/null)
[[ -n "$branch" ]] || branch="(detached HEAD)"
changes=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
sync=""
if counts=$(git rev-list --left-right --count origin/main...HEAD 2>/dev/null); then
  behind=${counts%%[[:space:]]*}
  ahead=${counts##*[[:space:]]}
  sync="; vs origin/main (last fetch): ${ahead} ahead, ${behind} behind"
fi

# --- SERVICES ---
ollama="down"
if tags=$(curl -sf -m 1 http://localhost:11434/api/tags 2>/dev/null); then
  ollama="up"
  if command -v jq >/dev/null 2>&1; then
    names=$(printf '%s' "$tags" | jq -r '.models[]?.name' 2>/dev/null)
    models=""
    for m in llama3 nomic-embed-text; do
      if printf '%s\n' "$names" | grep -Eq "^${m}(:|$)"; then models="$models $m=yes"; else models="$models $m=MISSING"; fi
    done
    ollama="up (models:${models})"
  fi
fi

gateway="down"
code=$(curl -s -o /dev/null -m 1 -w '%{http_code}' http://localhost:8000/health 2>/dev/null)
[[ "$code" == "200" ]] && gateway="up"

docker="down"
[[ "$(curl -s -m 1 --unix-socket /var/run/docker.sock http://localhost/_ping 2>/dev/null)" == "OK" ]] && docker="up"

# --- TERRAFORM ---
tf="no local state file"
if [[ -f terraform/terraform.tfstate ]] && command -v jq >/dev/null 2>&1; then
  n=$(jq '[.resources[]? | select(.mode == "managed")] | length' terraform/terraform.tfstate 2>/dev/null)
  [[ -n "$n" ]] && tf="local state tracks ${n} managed resource(s)"
fi

echo "[aegis-guard] git: branch ${branch}, ${changes} uncommitted path(s)${sync}"
echo "[aegis-guard] services: ollama :11434 ${ollama} | gateway :8000 ${gateway} | docker daemon ${docker}"
echo "[aegis-guard] terraform: ${tf}"
exit 0
