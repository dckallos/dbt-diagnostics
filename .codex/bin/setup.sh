#!/usr/bin/env bash
# Idempotently prepare a credential-free development environment for a worktree.
#
# Set CODEX_INSTALL_LIVE=1 only for an issue whose approved test plan requires
# the Snowflake connector. Installation never loads .env, parses dbt profiles,
# or opens a warehouse connection.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"

TOOLS_FILE="${CODEX_REPO_ROOT}/.codex/requirements-tools.txt"
MARKER_FILE="${CODEX_VENV_DIR}/.codex-managed"
FINGERPRINT_FILE="${CODEX_VENV_DIR}/.codex-setup.sha256"
MODE_FILE="${CODEX_VENV_DIR}/.codex-live-mode"
LOCK_KEY="$(printf '%s' "$CODEX_REPO_ROOT" | cksum | awk '{print $1}')"
LOCK_DIR="${TMPDIR:-/tmp}/${CODEX_POLICY_ENVIRONMENT_NAME}-codex-${LOCK_KEY}.lock"
LOCK_HELD=0

[ -f "$TOOLS_FILE" ] \
  || codex_die "missing Codex tool requirements: ${TOOLS_FILE}"

cleanup_lock() {
  if [ "$LOCK_HELD" -eq 1 ]; then
    rm -rf "$LOCK_DIR" 2>/dev/null || true
  fi
}
trap cleanup_lock EXIT HUP INT TERM

acquire_lock() {
  local attempts=0 owner_pid=''
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    if [ -f "$LOCK_DIR/pid" ]; then
      owner_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
      if [ -n "$owner_pid" ] && ! kill -0 "$owner_pid" 2>/dev/null; then
        rm -rf "$LOCK_DIR"
        continue
      fi
    fi

    attempts=$((attempts + 1))
    if [ "$attempts" -ge 120 ]; then
      codex_die "timed out waiting for another setup process: ${LOCK_DIR}"
    fi
    sleep 1
  done
  printf '%s\n' "$$" > "$LOCK_DIR/pid"
  LOCK_HELD=1
}

verify_environment() {
  local python_path="${CODEX_VENV_DIR}/bin/python"
  local install_live="$1"

  [ -x "$python_path" ] || return 1

  "$python_path" - "$install_live" "$CODEX_POLICY_REQUIRED_MODULES" "$CODEX_POLICY_LIVE_MODULES" <<'PY' >/dev/null 2>&1
from __future__ import annotations

import importlib.util
import sys

required = [item for item in sys.argv[2].split() if item]
if sys.argv[1] == "1":
    required.extend(item for item in sys.argv[3].split() if item)

missing = [name for name in required if importlib.util.find_spec(name) is None]
raise SystemExit(1 if missing else 0)
PY
  local command_line command_name
  local -a command_args
  while IFS= read -r command_line; do
    [ -n "$command_line" ] || continue
    IFS=' ' read -r -a command_args <<< "$command_line"
    [ "${#command_args[@]}" -ge 1 ] || return 1
    command_name="${command_args[0]}"
    command_args=("${command_args[@]:1}")
    [ -x "${CODEX_VENV_DIR}/bin/${command_name}" ] || return 1
    "${CODEX_VENV_DIR}/bin/${command_name}" "${command_args[@]}" >/dev/null 2>&1 || return 1
  done < <("$python_path" scripts/triage/repo_config.py cli-commands)
  "$python_path" -m pip check >/dev/null 2>&1 || return 1
}

install_live="$(codex_policy_live_install_value)"
force_setup="${CODEX_SETUP_FORCE:-0}"
case "$install_live" in
  0|1) ;;
  *) codex_die "CODEX_INSTALL_LIVE must be 0 or 1" ;;
esac
case "$force_setup" in
  0|1) ;;
  *) codex_die "CODEX_SETUP_FORCE must be 0 or 1" ;;
esac

bootstrap_python="$(codex_find_bootstrap_python)" \
  || codex_die "Python 3.11 or newer is required (Python 3.12 is preferred)"
bootstrap_version="$("$bootstrap_python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

codex_header "Codex setup"
codex_note "Repository: ${CODEX_REPO_ROOT}"
codex_note "Bootstrap Python: $("$bootstrap_python" -c 'import sys; print(sys.executable, sys.version.split()[0])')"
codex_note "Virtual environment: ${CODEX_VENV_DIR}"
codex_note "Live extras: ${install_live}"

acquire_lock

if [ -e "$CODEX_VENV_DIR" ] && [ ! -d "$CODEX_VENV_DIR" ]; then
  codex_die "CODEX_VENV_DIR exists but is not a directory: ${CODEX_VENV_DIR}"
fi

if [ -d "$CODEX_VENV_DIR" ] && [ ! -x "$CODEX_VENV_DIR/bin/python" ]; then
  if [ -f "$MARKER_FILE" ] || [ -f "$CODEX_VENV_DIR/pyvenv.cfg" ]; then
    codex_note "Removing an incomplete virtual environment."
    rm -rf "$CODEX_VENV_DIR"
  else
    codex_die "refusing to replace an unrecognized directory: ${CODEX_VENV_DIR}"
  fi
fi

if [ -x "$CODEX_VENV_DIR/bin/python" ] && [ -f "$MARKER_FILE" ]; then
  venv_version="$("$CODEX_VENV_DIR/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  previous_mode="$(cat "$MODE_FILE" 2>/dev/null || printf 'unknown')"
  if [ "$venv_version" != "$bootstrap_version" ] || [ "$previous_mode" != "$install_live" ]; then
    codex_note "Recreating the Codex-managed environment for the selected Python/live mode."
    rm -rf "$CODEX_VENV_DIR"
  fi
fi

if [ ! -d "$CODEX_VENV_DIR" ]; then
  codex_run "$bootstrap_python" -m venv "$CODEX_VENV_DIR"
  : > "$MARKER_FILE"
elif [ ! -f "$MARKER_FILE" ]; then
  codex_note "Using an existing user-managed virtual environment; setup will not delete it."
fi

venv_python="$(codex_require_venv)"
extras="dev"
if [ "$install_live" = "1" ]; then
  extras="dev,live"
fi

fingerprint="$("$venv_python" - "$extras" <<'PY'
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

root = Path.cwd()
extras = sys.argv[1]
paths = (
    root / "pyproject.toml",
    root / ".codex" / "requirements-tools.txt",
    root / ".codex" / "bin" / "common.sh",
    root / ".codex" / "bin" / "setup.sh",
    root / "scripts" / "triage" / "policy.toml",
    root / "scripts" / "triage" / "repo_config.py",
)

digest = hashlib.sha256()
digest.update(f"python={sys.version_info.major}.{sys.version_info.minor}\n".encode())
digest.update(f"extras={extras}\n".encode())
for path in paths:
    digest.update(str(path.relative_to(root)).encode())
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")
print(digest.hexdigest())
PY
)"

if [ "$force_setup" = "0" ] \
  && [ -f "$FINGERPRINT_FILE" ] \
  && [ "$(cat "$FINGERPRINT_FILE")" = "$fingerprint" ] \
  && verify_environment "$install_live"; then
  codex_note "Dependencies are already current for extras: ${extras}."
else
  export PIP_REQUIRE_VIRTUALENV=1
  codex_run "$venv_python" -m pip install --upgrade pip setuptools wheel
  codex_run "$venv_python" -m pip install --requirement "$TOOLS_FILE"
  codex_run "$venv_python" -m pip install --editable ".[${extras}]"
  codex_run "$venv_python" -m pip check
  verify_environment "$install_live" \
    || codex_die "environment verification failed after installation"
  printf '%s\n' "$fingerprint" > "$FINGERPRINT_FILE"
  printf '%s\n' "$install_live" > "$MODE_FILE"
fi

codex_run "$venv_python" -m compileall -q \
  $CODEX_POLICY_PYTHON_COMPILE_ROOTS

codex_note ""
codex_note "Codex environment is ready."
codex_note "Run diagnostics: bash .codex/bin/action.sh doctor"
codex_note "Run the normal gate: bash .codex/bin/action.sh check"
if [ "$install_live" = "0" ]; then
  codex_note "Live extras were not installed. Set CODEX_INSTALL_LIVE=1 only for approved Snowflake work."
fi
