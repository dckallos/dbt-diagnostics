#!/usr/bin/env bash
# Fail if automated AI-authorship markers appear in source files OR commit messages.
# Enforces the AGENTS.md "Voice and authorship" rule across the known AI coding
# tools (Claude Code, Cortex Code/CoCo, GitHub Copilot, Cursor, aider, Devin,
# OpenCode, Gemini/Jules, Codex, Cody, Tabnine, Windsurf, ...). The forbidden thing
# is an AUTOMATED authorship CLAIM -- a legitimate human "Co-authored-by: Jane" is
# intentionally NOT flagged.
#
# Why both files and commits: the most common marker is a COMMIT TRAILER
# (e.g. "Co-authored-by: Claude <noreply@anthropic.com>", "Generated with Claude
# Code", VS Code's "Co-authored-by: Copilot", aider's "(aider)" author tag), which
# a file-only scan never sees. We scan:
#   1. Tracked source files: *.py *.sql *.ipynb (incl. notebook JSON + escaped emoji).
#   2. Commit messages and author/committer identity over a range (PR base..HEAD).
#
# Escape hatch: put the token  authorship-marker-ok  on the same line (or in the
# commit body) to intentionally allow a reference -- e.g. this guard's own tests,
# or a doc that quotes a marker.
#
# Usage:
#   check_no_attribution.sh                     # files + commits (base auto-detected)
#   check_no_attribution.sh --base <ref>        # set the commit-range base explicitly
#   check_no_attribution.sh --files-only        # skip the commit scan
#   check_no_attribution.sh --commits-only      # skip the file scan
#   check_no_attribution.sh <path> [<path>...]  # scan only the given files (pre-commit)
#
# Env: BASE overrides the commit-range base; GITHUB_BASE_REF (set in PR CI) is used
# if present. CI should checkout with fetch-depth: 0 so the base ref is reachable.
#
# Exit: 0 clean; 1 if any marker is found; 2 on usage error.
set -uo pipefail

ALLOW='authorship-marker-ok'

# Known AI tool identities and their no-reply emails. Extend as new tools appear.
AI_NAMES='claude code|claude|cortex code|coco|codex|copilot|cursor|gemini|google jules|jules|aider|devin|opencode|open code|windsurf|amazon q|sourcegraph cody|cody|tabnine|continue\.dev|sweep|codeium'
AI_EMAILS='noreply@anthropic\.com|noreply@snowflake\.com|noreply@cursor\.com|noreply@openai\.com|copilot@users\.noreply\.github\.com|[0-9]+\+copilot@users\.noreply\.github\.com|devin-ai-integration'

# Text markers (POSIX ERE, matched case-insensitively). Each branch is anchored to
# an attribution CONTEXT to avoid flagging innocent prose or human co-authors.
ERE="co-authored-by:[[:space:]].*(${AI_NAMES})"                       # AI co-author trailer
ERE="${ERE}|co-authored[ -]with[[:space:]]+(${AI_NAMES})"             # "Co-authored with CoCo" style
ERE="${ERE}|generated[[:space:]]+(with|by)[[:space:]:]+\[?(${AI_NAMES})"  # "Generated with [Claude Code]"
ERE="${ERE}|(${AI_EMAILS})"                                          # any known AI no-reply email
ERE="${ERE}|claude\.(com/claude-code|ai/code)"                       # Claude Code footer URLs
ERE="${ERE}|\\(aider\\)"                                             # aider appends "(aider)" to the author
ERE="${ERE}|\\\\ud83e\\\\udd16"                                      # robot emoji, JSON-escaped (notebooks)

GLOBS=( '*.py' '*.sql' '*.ipynb' )
MODE='all'   # all | files | commits

err() { printf '%s\n' "$*" >&2; }
drop_allowed() { grep -v -- "$ALLOW" | grep -v -E '^[[:space:]]*$' || true; }

scan_tracked_files() {
  { git grep -nI -i -E -e "$ERE" -- "${GLOBS[@]}" 2>/dev/null || true
    # Raw robot-emoji bytes (needs a PCRE-enabled git; skipped silently otherwise).
    git grep -nI -P -e '\x{1F916}' -- "${GLOBS[@]}" 2>/dev/null || true
  } | drop_allowed
}

scan_explicit_files() {
  local f
  for f in "$@"; do
    case "$f" in
      *.py|*.sql|*.ipynb)
        [ -f "$f" ] && { grep -nHI -i -E -e "$ERE" -- "$f" 2>/dev/null || true; } ;;
    esac
  done | drop_allowed
}

resolve_base() {
  if [ -n "${BASE:-}" ]; then printf '%s' "$BASE"; return; fi
  if [ -n "${GITHUB_BASE_REF:-}" ] && git rev-parse --verify -q "origin/${GITHUB_BASE_REF}" >/dev/null; then
    printf '%s' "origin/${GITHUB_BASE_REF}"; return
  fi
  if git rev-parse --verify -q origin/donkey-kong-sandbox >/dev/null; then
    printf '%s' "origin/donkey-kong-sandbox"; return
  fi
  printf '%s' ''
}

scan_commits() {
  local base range; base="$(resolve_base)"
  if [ -n "$base" ]; then
    range="${base}..HEAD"
  else
    range='HEAD'
    err "note: no base ref reachable; scanning all reachable commit messages (use --base or fetch-depth: 0)"
  fi
  # Author/committer identity + subject + body for every commit in range.
  git log --no-merges --format='commit %h | %an <%ae> | %cn <%ce> | %s%n%b' "$range" 2>/dev/null \
    | grep -nI -i -E -e "$ERE" | drop_allowed
}

# --- argument parsing ----------------------------------------------------------
PATHS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --base) BASE="${2:-}"; shift 2 || { err "usage: --base <ref>"; exit 2; } ;;
    --files-only) MODE='files'; shift ;;
    --commits-only) MODE='commits'; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    --) shift; while [ "$#" -gt 0 ]; do PATHS+=("$1"); shift; done ;;
    -*) err "unknown flag: $1"; exit 2 ;;
    *) PATHS+=("$1"); shift ;;
  esac
done

# --- run -----------------------------------------------------------------------
violations=''
if [ "${#PATHS[@]}" -gt 0 ]; then
  violations="$(scan_explicit_files "${PATHS[@]}")"
else
  [ "$MODE" != 'commits' ] && violations+="$(scan_tracked_files)"$'\n'
  [ "$MODE" != 'files' ]   && violations+="$(scan_commits)"$'\n'
fi
violations="$(printf '%s' "$violations" | grep -v -E '^[[:space:]]*$' || true)"

if [ -n "$violations" ]; then
  err "ERROR: automated AI-authorship marker(s) found (AGENTS.md Voice and authorship rule forbids them):"
  err "$violations"
  err ""
  err "Remove the marker. If a hit is a deliberate reference, add the token '${ALLOW}' on that line."
  exit 1
fi
echo "OK: no AI-authorship markers in source files or commit messages."
