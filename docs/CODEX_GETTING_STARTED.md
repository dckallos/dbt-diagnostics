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

## 6. Configuration

User-level config lives at `~/.codex/config.toml`. A common mistake is nesting
model and reasoning keys inside a `[projects."<path>"]` table; that table only
carries `trust_level`. Model, reasoning, and document keys must be top-level (or
in a profile). A working baseline:

```toml
# ~/.codex/config.toml -- applies to every project

# model = "..."        # leave unset to use Codex's current default for your account.
                       # If you pin one, use a value your /model picker lists; do NOT hardcode
                       # an old model -- several are periodically retired for ChatGPT sign-in.
model_reasoning_effort  = "xhigh"              # max thinking; use a lighter profile for routine edits
model_reasoning_summary = "concise"
model_verbosity         = "low"
approval_policy         = "on-request"
sandbox_mode            = "workspace-write"
project_doc_max_bytes   = 49152                # headroom above the 32 KiB default; only matters if you add nested AGENTS.md files (docs/ never counts)

[tools]
web_search = true

[history]
persistence = "save-all"

# trust_level is the ONLY key that belongs in a per-project table
[projects."/absolute/path/to/dbt-diagnostics"]
trust_level = "trusted"
```

### Profiles (thinking vs task)

The profile mechanism changed at Codex 0.134.0, so check `codex --version`
first. Both forms define a read-only "thinking" profile and a write-enabled
"task" profile; invoke with `codex --profile thinking` or `codex --profile
task`. A one-off override needs no profile: `codex -c model_reasoning_effort=xhigh`.

Codex < 0.134.0 -- define `[profiles.NAME]` tables inside `~/.codex/config.toml`
(overlay files are ignored on these versions):

```toml
[profiles.thinking]
model_reasoning_effort  = "xhigh"
model_reasoning_summary = "detailed"
sandbox_mode            = "read-only"
approval_policy         = "on-request"

[profiles.task]
model_reasoning_effort = "xhigh"
model_verbosity        = "low"
sandbox_mode           = "workspace-write"
approval_policy        = "on-request"
```

Codex >= 0.134.0 -- `--profile` no longer reads `[profiles.NAME]` tables; put
each profile in its own overlay file (`~/.codex/thinking.config.toml`,
`~/.codex/task.config.toml`) with the same keys. If `--profile NAME` reports
"config profile not found", your binary's form does not match how the profile is
defined (most often a pre-0.134.0 binary that was given an overlay file).

### Model selection

Do not hardcode a model. The Codex model lineup for ChatGPT sign-in changes
frequently and models are periodically retired for ChatGPT accounts (a retired
model may linger only under API-key auth). What you can actually select is gated
by your installed CLI version and your account, so the only reliable source is
your own runtime: run the `/model` slash command in a session to list what is
available (and `/reasoning` to switch effort). If a model you expect is missing,
update the CLI (`codex --version`, then `codex update`) and refresh auth
(`codex logout` then `codex login`). Leaving `model` unset lets Codex pick its
current default for your account.

### Tools

`web_search` is an opt-in `[tools]` toggle. Command execution, `apply_patch`
file edits, file reads, `view_image`, and the plan tool are built into the
harness (not toggles). Add external tools via `[mcp_servers.<name>]`; extend
behavior with custom slash commands (`~/.codex/prompts`), skills (`SKILL.md`),
and subagents (`[agents]`).

### Context Codex reads at startup

Codex assembles its initial understanding from its built-in system prompt plus
the AGENTS.md hierarchy, walked root to cwd: in each directory it picks one file
in priority `AGENTS.override.md` > `AGENTS.md` > `project_doc_fallback_filenames`,
concatenated root-first with closer-to-cwd winning conflicts. Skills load on
demand. The merged AGENTS.md set is capped at `project_doc_max_bytes` (32 KiB by
default); once the cap is hit, later (more specific) files are dropped -- the
most common cause of "Codex ignored my instructions." Only the AGENTS.md
hierarchy counts toward this cap; `docs/` is loaded on demand and never merged
in, so it does not consume the budget. This repository has a single root
`AGENTS.md` of about 7 KiB, well under the default, so nothing is truncated
today; raising the cap (above) only matters if you later add nested `AGENTS.md`
files whose combined size approaches 32 KiB. When Codex repeats a mistake,
capture the lesson in `AGENTS.md`.

## References

- Authentication: https://developers.openai.com/codex/auth
- CLI overview: https://developers.openai.com/codex/cli
- CLI command-line options: https://developers.openai.com/codex/cli/reference
- Using Codex with your ChatGPT plan:
  https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
- Models: https://developers.openai.com/codex/models
- Config basics: https://developers.openai.com/codex/config-basic
- Advanced configuration (profiles): https://developers.openai.com/codex/config-advanced
- Configuration reference: https://developers.openai.com/codex/config-reference
- Custom instructions with AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- Best practices: https://developers.openai.com/codex/learn/best-practices
