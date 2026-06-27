#!/usr/bin/env bash
# Shared helpers for repository-local Codex commands.
# Compatible with the macOS system Bash 3.2 and modern Linux Bash.

set -Eeuo pipefail

codex_die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

codex_note() {
  printf '%s\n' "$*"
}

codex_warn() {
  printf 'WARNING: %s\n' "$*" >&2
}

codex_header() {
  printf '\n== %s ==\n' "$*" >&2
}

codex_repo_root() {
  local script_root git_root
  script_root="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/../.."
    pwd -P
  )"

  if command -v git >/dev/null 2>&1 \
    && git_root="$(git -C "$script_root" rev-parse --show-toplevel 2>/dev/null)"; then
    printf '%s\n' "$git_root"
  else
    printf '%s\n' "$script_root"
  fi
}

codex_policy_python() {
  local candidate resolved
  local candidates=()

  if [ -n "${CODEX_PYTHON:-}" ]; then
    candidates+=("${CODEX_PYTHON}")
  fi

  candidates+=(python3.12 python3.11 python3.14 python3.13 python3)
  for candidate in "${candidates[@]}"; do
    if resolved="$(command -v "$candidate" 2>/dev/null)" \
      && "$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done
  return 1
}

CODEX_REPO_ROOT="$(codex_repo_root)"

codex_load_policy_exports() {
  local python_path exports
  python_path="$(codex_policy_python)" \
    || codex_die "Python 3.11 or newer is required to load repository policy"
  exports="$("$python_path" "${CODEX_REPO_ROOT}/scripts/triage/repo_config.py" export-shell)" \
    || codex_die "failed to load repository policy"
  eval "$exports"
}

codex_load_policy_exports

CODEX_VENV_DIR="${CODEX_VENV_DIR:-${CODEX_REPO_ROOT}/${CODEX_POLICY_VENV_DIR}}"

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1
export PYTHONUNBUFFERED=1

codex_run() {
  local arg
  printf '+' >&2
  for arg in "$@"; do
    printf ' %q' "$arg" >&2
  done
  printf '\n' >&2
  "$@"
}

codex_command_exists() {
  command -v "$1" >/dev/null 2>&1
}

codex_require_command() {
  codex_command_exists "$1" || codex_die "required command not found: $1"
}

codex_require_repo_layout() {
  [ -f "${CODEX_REPO_ROOT}/pyproject.toml" ] \
    || codex_die "missing pyproject.toml at repository root: ${CODEX_REPO_ROOT}"
  [ -f "${CODEX_REPO_ROOT}/AGENTS.md" ] \
    || codex_die "missing AGENTS.md at repository root: ${CODEX_REPO_ROOT}"
  local package_root
  for package_root in $CODEX_POLICY_PACKAGE_ROOTS; do
    [ -d "${CODEX_REPO_ROOT}/${package_root}" ] \
      || codex_die "missing configured package root at repository root: ${package_root}"
  done
}

codex_python_is_supported() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
    >/dev/null 2>&1
}

codex_find_bootstrap_python() {
  local candidate resolved
  local candidates=()

  if [ -n "${CODEX_PYTHON:-}" ]; then
    candidates+=("${CODEX_PYTHON}")
  fi

  # Prefer the repository's current CI interpreter, then its minimum supported
  # version. Newer stable interpreters are fallbacks rather than silent policy.
  candidates+=(python3.12 python3.11 python3.14 python3.13 python3)

  for candidate in "${candidates[@]}"; do
    if resolved="$(command -v "$candidate" 2>/dev/null)" \
      && codex_python_is_supported "$resolved"; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done

  return 1
}

codex_venv_python() {
  local python_path="${CODEX_VENV_DIR}/bin/python"
  [ -x "$python_path" ] || return 1
  printf '%s\n' "$python_path"
}

codex_require_venv() {
  local python_path
  if ! python_path="$(codex_venv_python)"; then
    codex_die "virtual environment missing; run: bash .codex/bin/setup.sh"
  fi
  printf '%s\n' "$python_path"
}

codex_policy_live_install_value() {
  local name value
  for name in $CODEX_POLICY_LIVE_INSTALL_ENV_VARS; do
    value="${!name:-}"
    if [ -n "$value" ]; then
      printf '%s\n' "$value"
      return 0
    fi
  done
  printf '0\n'
}

codex_is_git_checkout() {
  command -v git >/dev/null 2>&1 \
    && git -C "$CODEX_REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

codex_branch_issue_number() {
  local branch
  branch="$(git -C "$CODEX_REPO_ROOT" branch --show-current 2>/dev/null || true)"
  printf '%s\n' "$branch" \
    | sed -nE 's#^([^/]+/)?(issue[-_/]?)?([0-9]+)([-_/].*)?$#\3#p' \
    | head -n 1
}
