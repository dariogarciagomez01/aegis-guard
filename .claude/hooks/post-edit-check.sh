#!/usr/bin/env bash
# PostToolUse hook (Edit|Write): fast checks on the file Claude just changed.
#   *.py -> compile() plus a Python 3.11 grammar parse with the project venv (no .pyc files)
#   *.tf -> terraform fmt on that file
# Exit 2 sends stderr back to Claude so it can fix the problem; every other
# case exits 0 silently. Missing tools (jq, python, terraform) skip the check.
set -uo pipefail

input=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[[ -n "$file" && -f "$file" ]] || exit 0

project_dir="${CLAUDE_PROJECT_DIR:-$(pwd)}"

case "$file" in
  *.py)
    py="$project_dir/.venv/bin/python"
    [[ -x "$py" ]] || py=$(command -v python3 || true)
    [[ -n "$py" ]] || exit 0
    if ! err=$("$py" -I - "$file" 2>&1 <<'PY'
import ast
import sys
import traceback

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    compile(source, path, "exec")
    # The Docker image runs Python 3.11; reject newer grammar such as `type` statements.
    ast.parse(source, path, feature_version=(3, 11))
except (SyntaxError, ValueError) as exc:
    sys.stderr.write("".join(traceback.format_exception_only(type(exc), exc)))
    sys.exit(1)
PY
    ); then
      printf 'Python syntax check failed for %s:\n%s\n' "$file" "$err" >&2
      exit 2
    fi
    ;;
  *.tf)
    command -v terraform >/dev/null 2>&1 || exit 0
    if ! err=$(terraform fmt -no-color "$file" 2>&1); then
      printf 'terraform fmt failed for %s:\n%s\n' "$file" "$err" >&2
      exit 2
    fi
    ;;
esac
exit 0
