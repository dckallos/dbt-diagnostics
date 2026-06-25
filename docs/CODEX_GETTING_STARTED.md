# Getting started: dbt-diagnostics governance work with Codex

This guide gets a new contributor from a clean clone to running the read-only
issue-governance toolchain, and explains how to authenticate the Codex CLI with
a ChatGPT plan (no OpenAI API key required). It complements `AGENTS.md`,
`docs/ISSUE_GOVERNANCE.md`, and `docs/ISSUE_CONTRACT_V1.md`; read those for the
conventions and the full command surface.

## 1. Clone and bootstrap (one-time per worktree)

```bash
git clone <repo-url> dbt-diagnostics && cd dbt-diagnostics
git checkout donkey-kong-sandbox          # branch your work from here
bash .codex/bin/action.sh setup           # builds the credential-free .venv
bash .codex/bin/action.sh doctor          # verifies readiness, changes nothing
```

The `.codex` environment is credential-free by default. Set `CODEX_INSTALL_LIVE=1`
only for explicitly approved Snowflake work; do not run a live test merely
because the connector is installed.

## 2. Start a task

```bash
bash .codex/bin/action.sh context <issue-number>   # live issue plus local context
```

If you omit the number, `context` infers it from the current branch. It reads
the live issue and the local checkout without writing another stale cache.

## 3. The implementation gate

The stable command surface (from `.codex/bin/action.sh`):

```bash
bash .codex/bin/action.sh check        # the normal credential-free gate; run before pushing
bash .codex/bin/action.sh compile      # byte-compile repository-owned Python
bash .codex/bin/action.sh fast         # tests except the live and chaos tiers
bash .codex/bin/action.sh offline      # every credential-free test, including chaos
bash .codex/bin/action.sh full         # the repository's exact `pytest -q` suite
bash .codex/bin/action.sh unit         # tests marked unit
bash .codex/bin/action.sh last-failed  # re-run the last credential-free failures
bash .codex/bin/action.sh compat       # the local compatibility schema gate
bash .codex/bin/action.sh package      # build, inspect, install, smoke-test wheel and sdist
```

CI `pytest` is the authority. `action.sh full` is the local parity check.

## 4. The issue-governance toolchain (read-only)

```bash
# read-only audit (live needs an authenticated gh; or audit a snapshot offline)
bash .codex/bin/action.sh audit
python scripts/triage/triage.py audit --snapshot output/triage/snapshot.json

# read-only frontier selection
bash .codex/bin/action.sh frontier <mode>

# per-issue review packet: writes contract.json, review-packet.json, proposed-body.md
python scripts/triage/triage.py review-packet --issue <n> \
  --output-dir output/triage/issues/<n>
```

### AI-assisted drafting of missing sections

`review-packet` writes `proposed-body.md` with a placeholder for any section it
cannot establish, and the contract audit rejects a body that still contains the
placeholder. The deterministic tool is unchanged: it still emits placeholders
and gates. The `issue-governance` skill adds an optional assist layer:

1. Read `output/triage/issues/<n>/contract.json` for `missing_required_sections`
   and `missing_recommended_sections`.
2. Draft only the placeholder sections, grounded in `review-packet.json` and the
   cited repository files. Cite sources with verifiable anchors (`path:symbol` or
   `path "snippet"`), never a bare `path:line`.
3. Hypothesis-label anything you cannot ground, list residual open questions, and
   prefix each drafted section with
   `> Draft (machine-authored; needs maintainer verification)`. Never fabricate
   acceptance facts, test results, or decisions to clear the gate.
4. Validate locally and require exit 0:

   ```bash
   python scripts/triage/triage.py standardize --issue <n> \
     --proposed-body output/triage/issues/<n>/proposed-body.md
   ```

5. Present the placeholder-to-draft diff for review. Stop before any GitHub
   mutation; the maintainer applies the edit. The deterministic audit remains the
   source of truth.

## 5. Codex authentication with a ChatGPT plan (no API key)

You do not need an OpenAI API key. Codex supports two sign-in modes: "Sign in
with ChatGPT" (uses your Plus/Pro/Team/Business/Edu/Enterprise plan) or an API
key. Choose the ChatGPT sign-in.

Logging into ChatGPT via Google is fine: Google is only the identity provider
for your ChatGPT account. There is no Codex-specific Google setting.

```bash
codex login          # no flags: opens a browser for the ChatGPT OAuth flow
```

1. The browser opens the OpenAI sign-in page. Click "Continue with Google",
   complete Google SSO, and approve access.
2. The page redirects to a local callback the CLI is listening on; Codex writes
   tokens to `~/.codex/auth.json`.
3. Verify:

   ```bash
   codex login status   # prints the active auth mode; exits 0 when logged in
   ```

### Headless or remote machines (no browser)

```bash
codex login --device-auth   # prints a URL and a one-time code
```

Open the URL on your laptop, sign in with Google there, and enter the code. The
tokens are saved on the remote box. Alternatively, SSH-port-forward the local
callback port and use plain `codex login`.

### Gotchas

- Managed workspace: if your ChatGPT account belongs to a Team, Business, or
  Enterprise workspace, `--device-auth` may require an admin to enable Device
  Code auth. A personal Pro plan generally does not.
- Do not get silently forced into API-key mode: if `OPENAI_API_KEY` is exported
  in your shell, Codex may use it instead of your ChatGPT plan. Unset it (or keep
  it out of the Codex profile) so usage draws from ChatGPT Pro. For scripted
  token injection there are `codex login --with-access-token` and
  `codex login --with-api-key` (both read from stdin).
- Credentials persist at `~/.codex/auth.json`; `codex logout` clears them.
- Connected services carry over from ChatGPT (for example, a Google Drive
  connection made in ChatGPT also appears in Codex). Disconnect anytime.

## 6. Configuration notes

User-level config lives at `~/.codex/config.toml`. Useful keys: `model`,
`model_reasoning_effort` (medium is the recommended daily driver; `high` or
`xhigh` for hard, non-latency-sensitive work), `plan_mode_reasoning_effort`,
`approval_policy`, and `sandbox_mode`. Prefer per-task profiles (for example a
read-only `governance` profile) over pinning a global maximum effort. When Codex
repeats a mistake, capture the lesson in `AGENTS.md`.

## References

- Authentication: https://developers.openai.com/codex/auth
- CLI overview: https://developers.openai.com/codex/cli
- CLI command-line options: https://developers.openai.com/codex/cli/reference
- Using Codex with your ChatGPT plan:
  https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
- Configuration reference: https://developers.openai.com/codex/config-reference
- Best practices: https://developers.openai.com/codex/learn/best-practices
