# Branch protection governance

Version-controlled branch protection policy for `dckallos/dbt-diagnostics`, plus
thin `gh` wrappers to inspect, apply, and roll it back.

The policy JSON under `policies/` is the source of truth. The scripts are thin
wrappers around the GitHub REST branch-protection endpoint
(`/repos/{owner}/{repo}/branches/{branch}/protection`). Applying a policy is a
local, operator-run step: it needs an admin-scoped token and is deliberately not
automated in CI or done by an agent.

## Prerequisites

- GitHub CLI (`gh`) installed and authenticated: `gh auth login`.
- Your token must have admin rights on the repo (branch protection is an admin
  setting).
- Default repo is `dckallos/dbt-diagnostics`; override with `REPO=owner/name`.

## Policies

| Branch                | File                              | Intent                                  |
|-----------------------|-----------------------------------|-----------------------------------------|
| `donkey-kong-sandbox` | `policies/donkey-kong-sandbox.json` | Integration branch, exactly per CONTRIBUTING.md |
| `main`                | `policies/main.json`              | Release branch; mirrors sandbox (harden if desired) |

The `donkey-kong-sandbox` policy encodes what `CONTRIBUTING.md` specifies:

- Require a pull request before merging (1 approving review).
- Require status checks to pass, strict (branch up to date): the CI job `test`.
- Require linear history.
- No direct pushes (`restrictions: null`, no force pushes, no deletions).
- `enforce_admins: false`.

`main.json` mirrors this. Because `main` is the released branch, you may want to
harden it (for example `enforce_admins: true`, a higher review count, or
`required_conversation_resolution: true`). Edit `policies/main.json` and commit
the change so the policy stays version-controlled.

## Usage

All scripts take the branch name as the first argument.

Inspect current state (do this first, to capture the before-state):

```
./show-protection.sh donkey-kong-sandbox
# save an audit snapshot:
./show-protection.sh main > main.protection.before.json
```

Dry-run (prints the body that would be sent, applies nothing):

```
./apply-protection.sh donkey-kong-sandbox --dry-run
```

Apply (defaults to `policies/<branch>.json`):

```
./apply-protection.sh donkey-kong-sandbox
./apply-protection.sh main
# or an explicit policy file:
./apply-protection.sh donkey-kong-sandbox policies/donkey-kong-sandbox.json
```

Roll back (removes all protection from the branch):

```
./remove-protection.sh donkey-kong-sandbox
```

## Notes

- The required status check context is the CI job name `test` (see
  `.github/workflows/ci.yml`). If the job is renamed, update the `contexts`
  array in the policy JSON to match, or the check will never be satisfied.
- The GET response shape (what `show-protection.sh` prints) is NOT identical to
  the PUT request body (what the policy JSON holds): the GET response is nested
  with `url`/`enabled` fields. Treat `show-protection.sh` output as an audit
  snapshot, not a re-appliable body. The policy JSON is the appliable form.
- Classic branch protection is used here (not rulesets) to match the existing
  CONTRIBUTING.md guidance. Switching to rulesets is a separate decision.
- Re-running `apply-protection.sh` is idempotent: the PUT replaces the full
  protection config each time.
