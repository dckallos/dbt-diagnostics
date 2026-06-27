#!/usr/bin/env bash
# Launch a local Codex hook through the repository-controlled Python runtime.

set -u

script_name="${1:-}"
event_name="${2:-}"

fail_closed() {
  message="${1:-Hook launcher failed safely.}"
  case "$event_name" in
    PreToolUse)
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$message"
      ;;
    PermissionRequest)
      printf '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"deny","message":"%s"}}}\n' "$message"
      ;;
    Stop)
      printf '{"decision":"block","reason":"%s"}\n' "$message"
      ;;
    *)
      printf '{"decision":"block","reason":"%s"}\n' "$message"
      ;;
  esac
  exit 0
}

case "$script_name:$event_name" in
  pre_tool_use.py:PreToolUse|permission_request.py:PermissionRequest|stop.py:Stop)
    ;;
  *)
    fail_closed "Hook launcher failed safely: unsupported hook event or script."
    ;;
esac

root="$(git rev-parse --show-toplevel 2>/dev/null)" || \
  fail_closed "Hook launcher failed safely: cannot resolve git root."
python_path="$root/.venv/bin/python"
hook_path="$root/.codex/hooks/$script_name"

if [ ! -x "$python_path" ]; then
  fail_closed "Hook launcher failed safely: missing repository .venv/bin/python."
fi

if [ ! -f "$hook_path" ]; then
  fail_closed "Hook launcher failed safely: missing hook script."
fi

stdout_path="$(mktemp)"
stderr_path="$(mktemp)"
cleanup() {
  rm -f "$stdout_path" "$stderr_path"
}
trap cleanup EXIT

if "$python_path" "$hook_path" >"$stdout_path" 2>"$stderr_path"; then
  cat "$stdout_path"
  exit 0
fi

if [ -s "$stderr_path" ]; then
  cat "$stderr_path" >&2
fi
fail_closed "Hook launcher failed safely: hook script exited nonzero."
