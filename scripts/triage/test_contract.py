from __future__ import annotations

from pathlib import Path

import pytest

from scripts.triage import contract
from scripts.triage import repo_config


ROOT = Path(__file__).resolve().parents[2]
WIDGETS_POLICY = ROOT / "scripts" / "triage" / "fixtures" / "widgets_policy.toml"


def common_body(extra: str = "") -> str:
    return f"""## Summary

I will make one bounded change.

## Evidence and confidence

The current source proves the gap. Confidence is high.

{extra}

## Acceptance criteria

- A positive case succeeds.
- An invalid negative case is rejected.
- A failed probe degrades to unverified offline behavior.
- Existing compatibility remains unchanged as a regression check.

## Focused test plan

Run positive, negative, degradation, and regression tests.

## Scope and likely files

- scripts/triage/triage.py

## Explicit non-goals

- No GitHub mutation.

## Dependencies and traceability

- Parent epic: #4
- Depends on: none.
"""


def test_contract_uses_non_dbt_policy_for_official_docs() -> None:
    widgets_policy = repo_config.load_repo_policy(WIDGETS_POLICY)
    issue = {
        "number": 1,
        "title": "feat: verify GitHub Actions CI service behavior",
        "labels": ["enhancement"],
        "milestone": None,
        "body": common_body(
            """## User-visible problem or current gap

The widgets service relies on GitHub Actions workflow behavior.

## Expected behavior or target outcome

The contract records official docs evidence without product package checks.

## Official documentation evidence

- Provider: GitHub.
  - Official URL: https://docs.github.com/en/actions
  - Supported claim or decision: GitHub Actions CI-service behavior is external platform evidence for this issue.
  - Docs version or product version: current GitHub Docs, no pinned version.
  - Retrieval date: 2026-06-27.
  - Residual uncertainty: docs do not prove this repository interpreted the workflow correctly.
"""
        ),
    }

    result = contract.audit_contract(issue, repo_policy=widgets_policy)

    assert result["contract_id"] == "widgets.issue-contract.v1"
    assert result["contract_accepted"] is True
    assert "dbt-diagnostics" not in repr(result)


@pytest.mark.parametrize(
    ("title", "labels", "extra", "expected_kind"),
    [
        (
            "fix: preserve unknown evidence",
            ["bug"],
            """## Current wrong behavior or gap

Unknown becomes missing.

## Root cause or architectural reason

The return type collapses states.

## Expected behavior or target outcome

Unknown remains unknown.
""",
            "bug_fix",
        ),
        (
            "feat: add a bounded packet",
            ["enhancement"],
            """## User-visible problem or current gap

Workers receive too much context.

## Expected behavior or target outcome

Emit one bounded packet.
""",
            "feature_enhancement",
        ),
        (
            "refactor: separate evidence",
            ["architecture"],
            """## Current wrong behavior or gap

Mutable prose stores state.

## Expected behavior or target outcome

Typed evidence drives one resolver.

## Migration, coexistence, and rollback

Switch one capability and revert the PR if needed.

## Compatibility and canonical JSON implications

Existing schema-major-1 keys remain additive.
""",
            "refactor_architecture",
        ),
        (
            "test: verify live evidence",
            ["test"],
            """## User-visible problem or current gap

Mock rows do not establish live semantics.

## External evidence, permissions, credentials, or fixtures

A disposable credential-gated account is required.

## Offline behavior

Offline tests use recorded rows.

## Live behavior and cost tier

Tier A metadata only.
""",
            "test_verification",
        ),
        (
            "spike: choose identity attestation",
            ["spike"],
            """## Question to answer

Should identity be attested?

## Investigation tasks

- Compare two approaches.

## Deliverable

Record a go/no-go decision.

## Decision criteria

Choose only when evidence establishes value.
""",
            "spike_decision",
        ),
        (
            "governance: choose issue contract shape",
            ["governance"],
            """## Decision criteria

The selected issue kind must drive the required section set.
""",
            "governance",
        ),
        (
            "[Epic] Release correctness",
            ["epic"],
            """## Thesis or decision

Facts and confidence remain separate.

## Initial-release gate or build order

- [ ] #55

## Children and backlog

- Release: #55
- Deferred: #5

## Maintainer decisions and blockers

- OPEN: cost ceiling.

## Workflow

One issue per PR.
""",
            "epic",
        ),
        (
            "chore: publish package",
            ["chore"],
            """## Deliverable

Publish one tested wheel and sdist.

## Release relevance and priority

This blocks the initial release.
""",
            "docs_chore_release",
        ),
    ],
)
def test_every_contract_kind(
    title: str,
    labels: list[str],
    extra: str,
    expected_kind: str,
) -> None:
    body = common_body(extra)
    if expected_kind == "epic":
        body = (
            """## Summary

Track the release architecture.

## Evidence and confidence

The live tracker and source establish the need.

"""
            + extra
        )
    issue = {"number": 1, "title": title, "labels": labels, "body": body}

    result = contract.audit_contract(issue)

    assert result["issue_kind"] == expected_kind
    assert result["governance_state"] == "conformant", result["findings"]


def test_required_section_is_error() -> None:
    issue = {
        "number": 1,
        "title": "fix: incomplete contract",
        "labels": ["bug"],
        "body": "## Summary\n\nOnly a summary.",
    }
    result = contract.audit_contract(issue)
    assert result["governance_state"] == "needs_contract_revision"
    assert any(
        item["code"] == "missing-required-section" for item in result["findings"]
    )


def test_governance_contract_accepts_decision_body_without_product_test_sections() -> None:
    issue = {
        "number": 80,
        "title": "governance: add issue-kind decision",
        "labels": ["governance"],
        "body": """## Summary

I will record one governance decision.

## Evidence and confidence

The contract rules define a governance issue kind. Confidence is high.

## Decision criteria

The issue kind must select the correct required section set.

## Explicit non-goals

- No product issue-kind behavior changes beyond additive classification.

## Dependencies and traceability

- Parent epic: #85.
""",
    }

    result = contract.audit_contract(issue)

    assert result["issue_kind"] == "governance"
    assert result["governance_state"] == "conformant", result["findings"]
    assert "Focused test plan" not in result["missing_required_sections"]
    assert "Scope and likely files" not in result["missing_required_sections"]
    assert "External evidence, permissions, credentials, or fixtures" not in result[
        "missing_required_sections"
    ]


def test_live_conditional_sections_are_required() -> None:
    issue = {
        "number": 1,
        "title": "fix: live probe",
        "labels": ["bug", "live"],
        "body": common_body(
            """## Current wrong behavior or gap

A probe fails.

## Root cause or architectural reason

The state is collapsed.

## Expected behavior or target outcome

Preserve unknown.
"""
        ),
    }
    result = contract.audit_contract(issue)
    assert "Offline behavior" in result["missing_required_sections"]
    assert "Live behavior and cost tier" in result["missing_required_sections"]


def official_docs_body(url: str, *, uncertainty: str | None = None) -> str:
    uncertainty_text = (
        uncertainty
        if uncertainty is not None
        else "Maintainer review must verify the issue interpretation."
    )
    return f"""## Official documentation evidence

- Provider: GitHub Actions
- Official URL: {url}
- Supported claim: GitHub Actions workflow dispatch semantics are external to this repository.
- Docs version or product version: Current hosted GitHub Docs; no pinned product version.
- Retrieval date: 2026-06-27.
- Residual uncertainty: {uncertainty_text}
"""


def github_actions_contract_body(extra: str = "") -> str:
    return common_body(
        f"""## User-visible problem or current gap

The implementation depends on GitHub Actions workflow_dispatch behavior.

## Expected behavior or target outcome

The issue records the official GitHub Actions documentation that supports the claim.

{extra}
"""
    )


def test_official_docs_required_for_external_provider_contracts() -> None:
    issue = {
        "number": 115,
        "title": "feat: verify GitHub Actions workflow dispatch",
        "labels": ["enhancement"],
        "body": github_actions_contract_body(),
    }

    result = contract.audit_contract(issue)

    assert "Official documentation evidence" in result["missing_required_sections"]
    assert any(
        item["code"] == "missing-required-section"
        and item["message"].endswith("Official documentation evidence")
        for item in result["findings"]
    )


@pytest.mark.parametrize(
    ("title", "body_text"),
    [
        (
            "feat: document AcmeCloud CLI contract",
            "The implementation depends on an AcmeCloud CLI contract outside this repository.",
        ),
        (
            "feat: preserve hosted API schema guarantees",
            "The issue depends on a hosted API schema guarantee from the vendor.",
        ),
        (
            "feat: mirror CI service retry behavior",
            "The implementation relies on CI service behavior for retry semantics.",
        ),
        (
            "feat: validate package-manager resolution behavior",
            "The issue depends on package-manager behavior for dependency resolution.",
        ),
        (
            "feat: ingest published schema semantics",
            "The implementation relies on published schema semantics maintained outside this repository.",
        ),
    ],
)
def test_official_docs_required_for_unknown_or_generic_external_contracts(
    title: str, body_text: str
) -> None:
    issue = {
        "number": 123,
        "title": title,
        "labels": ["enhancement"],
        "body": common_body(
            f"""## User-visible problem or current gap

{body_text}

## Expected behavior or target outcome

The issue records the official source or explicit uncertainty before implementation.
"""
        ),
    }

    result = contract.audit_contract(issue)

    assert "Official documentation evidence" in result["missing_required_sections"]
    assert any(
        item["code"] == "missing-required-section"
        and item["message"].endswith("Official documentation evidence")
        for item in result["findings"]
    )


def test_official_docs_not_required_for_repository_local_tracker_state() -> None:
    issue = {
        "number": 116,
        "title": "governance: document tracker handoff",
        "labels": ["governance"],
        "body": """## Summary

I will clarify one repository-local governance handoff.

## Evidence and confidence

The current repository docs mention GitHub tracker metadata and local triage artifacts.

## Current wrong behavior or gap

The handoff wording is too vague.

## Acceptance criteria

The repository docs name the local handoff boundary.

## Explicit non-goals

- No GitHub metadata mutation.
- No external platform behavior change.

## Dependencies and traceability

- Parent epic: #93.
""",
    }

    result = contract.audit_contract(issue)

    assert result["governance_state"] == "conformant", result["findings"]
    assert "Official documentation evidence" not in result[
        "missing_required_sections"
    ]


def test_official_docs_meta_governance_issue_does_not_require_itself() -> None:
    issue = {
        "number": 115,
        "title": "feat(governance): require official docs evidence",
        "labels": ["enhancement"],
        "body": common_body(
            """## User-visible problem or current gap

Issue-governance needs a first-class `Official documentation evidence` section.
The trigger list may include examples such as OpenAI/Codex, dbt, GitHub,
Snowflake, BigQuery, Postgres, DuckDB, Python, PyPI, and package managers.

## Expected behavior or target outcome

The local issue contract enforces the section structurally without fetching
the web or treating documentation URLs as semantic proof.

## Offline behavior

The contract and standardize commands parse local issue text without network
retrieval.

## Live behavior and cost tier

No live provider call is added; this is a deterministic local governance check.
"""
        ),
    }

    result = contract.audit_contract(issue)

    assert result["governance_state"] == "conformant", result["findings"]
    assert "Official documentation evidence" not in result[
        "missing_required_sections"
    ]


def test_official_docs_meta_wording_does_not_suppress_real_external_claim() -> None:
    issue = {
        "number": 124,
        "title": "feat(governance): require official docs evidence for GitHub API",
        "labels": ["enhancement"],
        "body": common_body(
            """## User-visible problem or current gap

Issue-governance needs a first-class `Official documentation evidence` section.
The implementation also depends on GitHub API behavior for closing issue
references across pull requests.

## Expected behavior or target outcome

The contract enforces the section structurally and records the official GitHub
documentation that supports the API behavior.

## Offline behavior

The contract parses local issue text without network retrieval.
"""
        ),
    }

    result = contract.audit_contract(issue)

    assert "Official documentation evidence" in result["missing_required_sections"]


def test_official_docs_accepts_known_provider_official_url() -> None:
    issue = {
        "number": 117,
        "title": "feat: verify GitHub Actions workflow dispatch",
        "labels": ["enhancement"],
        "body": github_actions_contract_body(
            official_docs_body("https://docs.github.com/en/actions")
        ),
    }

    result = contract.audit_contract(issue)

    assert "official_docs" in result["present_sections"]
    assert result["governance_state"] == "conformant", result["findings"]
    assert not any(
        item["code"].startswith("official-docs-") for item in result["findings"]
    )


def test_official_docs_rejects_unofficial_known_provider_url() -> None:
    issue = {
        "number": 118,
        "title": "feat: verify GitHub Actions workflow dispatch",
        "labels": ["enhancement"],
        "body": github_actions_contract_body(
            official_docs_body("https://example.com/github-actions-notes")
        ),
    }

    result = contract.audit_contract(issue)

    assert result["governance_state"] == "needs_contract_revision"
    assert any(
        item["code"] == "official-docs-unofficial-url"
        for item in result["findings"]
    )


def test_unknown_provider_official_docs_require_explicit_uncertainty() -> None:
    issue = {
        "number": 119,
        "title": "feat: document AcmeCloud CLI contract",
        "labels": ["enhancement"],
        "body": common_body(
            """## User-visible problem or current gap

The issue relies on an AcmeCloud CLI contract outside this repository.

## Expected behavior or target outcome

The issue records external source uncertainty.

## Official documentation evidence

- Provider: AcmeCloud
- Official URL: https://docs.acme.invalid/cli
- Supported claim: The CLI flag is documented by AcmeCloud.
- Docs version or product version: Current hosted docs.
- Retrieval date: 2026-06-27.
- Residual uncertainty: None.
"""
        ),
    }

    result = contract.audit_contract(issue)

    assert result["governance_state"] == "needs_contract_revision"
    assert any(
        item["code"] == "official-docs-unknown-provider"
        for item in result["findings"]
    )


def test_unknown_provider_field_is_not_masked_by_known_provider_url() -> None:
    issue = {
        "number": 125,
        "title": "feat: document AcmeCloud CLI contract",
        "labels": ["enhancement"],
        "body": common_body(
            """## User-visible problem or current gap

The issue relies on an AcmeCloud CLI contract outside this repository.

## Expected behavior or target outcome

The issue records external source uncertainty.

## Official documentation evidence

- Provider: AcmeCloud
- Official URL: https://docs.github.com/en/actions
- Supported claim: The AcmeCloud CLI flag is documented by AcmeCloud.
- Docs version or product version: Current hosted docs.
- Retrieval date: 2026-06-27.
- Residual uncertainty: None.
"""
        ),
    }

    result = contract.audit_contract(issue)

    assert result["governance_state"] == "needs_contract_revision"
    assert any(
        item["code"] == "official-docs-unknown-provider"
        for item in result["findings"]
    )


def test_unknown_url_host_is_not_masked_by_known_provider_text() -> None:
    issue = {
        "number": 126,
        "title": "feat: verify GitHub Actions workflow dispatch",
        "labels": ["enhancement"],
        "body": github_actions_contract_body(
            """## Official documentation evidence

- Provider: GitHub Actions
- Official URL: https://docs.github.com/en/actions
- Official URL: https://docs.acme.invalid/actions
- Supported claim: GitHub Actions workflow dispatch semantics are external to this repository.
- Docs version or product version: Current hosted GitHub Docs; no pinned product version.
- Retrieval date: 2026-06-27.
- Residual uncertainty: Maintainer review must verify the issue interpretation.
"""
        ),
    }

    result = contract.audit_contract(issue)

    assert result["governance_state"] == "needs_contract_revision"
    assert any(
        item["code"] == "official-docs-unknown-provider"
        for item in result["findings"]
    )


def test_unknown_provider_official_docs_accepts_maintainer_verified_source() -> None:
    issue = {
        "number": 121,
        "title": "feat: document AcmeCloud CLI contract",
        "labels": ["enhancement"],
        "body": common_body(
            """## User-visible problem or current gap

The issue relies on an AcmeCloud CLI contract outside this repository.

## Expected behavior or target outcome

The issue records external source uncertainty.

## Official documentation evidence

- Provider: AcmeCloud
- Official URL: https://docs.acme.invalid/cli
- Supported claim: The CLI flag is documented by AcmeCloud.
- Docs version or product version: Current hosted docs.
- Retrieval date: 2026-06-27.
- Residual uncertainty: Unknown provider; maintainer verification completed on 2026-06-27 that this is the official provider documentation. Interpretation still requires review.
"""
        ),
    }

    result = contract.audit_contract(issue)

    assert result["governance_state"] == "conformant", result["findings"]


def test_critical_unverified_unknown_provider_requires_blocker_section() -> None:
    body = common_body(
        """## User-visible problem or current gap

The issue relies on an AcmeCloud CLI contract outside this repository.

## Expected behavior or target outcome

The issue records external source uncertainty.

## Official documentation evidence

- Provider: AcmeCloud
- Official URL: https://docs.acme.invalid/cli
- Supported claim: The CLI flag is documented by AcmeCloud.
- Docs version or product version: Current hosted docs.
- Retrieval date: 2026-06-27.
- Residual uncertainty: Critical unknown provider; maintainer verification is required before implementation.
"""
    )
    issue = {
        "number": 122,
        "title": "feat: document AcmeCloud CLI contract",
        "labels": ["enhancement"],
        "body": body,
    }

    result = contract.audit_contract(issue)

    assert result["governance_state"] == "needs_contract_revision"
    assert any(
        item["code"] == "official-docs-missing-verification-blocker"
        for item in result["findings"]
    )

    accepted = contract.audit_contract(
        {
            **issue,
            "body": body
            + """## Maintainer decisions and blockers

- BLOCKED: Maintainer must verify that the AcmeCloud URL is official before implementation starts.
""",
        }
    )
    assert accepted["governance_state"] == "conformant", accepted["findings"]


def test_proposed_body_includes_official_docs_placeholder_when_required() -> None:
    issue = {
        "number": 120,
        "title": "feat: verify GitHub Actions workflow dispatch",
        "labels": ["enhancement"],
        "body": github_actions_contract_body(),
    }

    proposed = contract.propose_normalized_body(issue)
    result = contract.audit_contract({**issue, "body": proposed})

    assert "## Official documentation evidence" in proposed
    assert contract.UNRESOLVED_PLACEHOLDER in proposed
    assert result["missing_required_sections"] == []
    assert any(
        item["code"] == "unresolved-placeholder-section"
        and item["section"] == "official_docs"
        for item in result["findings"]
    )


def test_proposed_body_includes_official_docs_placeholder_for_unknown_trigger() -> None:
    issue = {
        "number": 127,
        "title": "feat: document AcmeCloud CLI contract",
        "labels": ["enhancement"],
        "body": common_body(
            """## User-visible problem or current gap

The implementation depends on an AcmeCloud CLI contract outside this repository.

## Expected behavior or target outcome

The issue records official documentation evidence or explicit uncertainty.
"""
        ),
    }

    proposed = contract.propose_normalized_body(issue)
    result = contract.audit_contract({**issue, "body": proposed})

    assert "## Official documentation evidence" in proposed
    assert contract.UNRESOLVED_PLACEHOLDER in proposed
    assert result["missing_required_sections"] == []
    assert any(
        item["code"] == "unresolved-placeholder-section"
        and item["section"] == "official_docs"
        for item in result["findings"]
    )


def test_duplicate_heading_is_error() -> None:
    issue = {
        "number": 1,
        "title": "fix: duplicate",
        "labels": ["bug"],
        "body": common_body(
            """## Current wrong behavior

One.

## Current behavior

Two.

## Root cause

Cause.

## Expected behavior

Expected.
"""
        ),
    }
    result = contract.audit_contract(issue)
    assert any(item["code"] == "duplicate-section" for item in result["findings"])


def test_malformed_heading_is_error() -> None:
    sections, findings = contract.parse_sections("##Summary\n\nText")
    assert sections == []
    assert findings[0]["code"] == "malformed-heading"


def test_heading_parser_ignores_code_fences_and_shell_text() -> None:
    body = """## Summary

Never execute $(touch /tmp/not-created) or `echo $TOKEN`.

```bash
## Acceptance criteria
$(rm -rf /)
```

## Acceptance criteria

- Valid input succeeds.
"""
    sections, findings = contract.parse_sections(body)
    assert not findings
    assert [section.key for section in sections] == ["summary", "acceptance_criteria"]
    assert "$(touch" in sections[0].content
    assert not Path("/tmp/not-created").exists()


def test_spike_forbids_implementation_plan() -> None:
    body = common_body(
        """## Question to answer

Which option should be chosen?

## Investigation tasks

- Compare evidence.

## Deliverable

Record a decision.

## Decision criteria

Choose the safer option.

## Implementation plan

Implement option A now.
"""
    )
    issue = {"number": 2, "title": "spike: decide", "labels": ["spike"], "body": body}
    result = contract.audit_contract(issue)
    assert result["governance_state"] == "unsafe"
    assert any(item["code"] == "forbidden-section" for item in result["findings"])


def test_acceptance_coverage_reports_missing_categories() -> None:
    body = (
        common_body(
            """## Current wrong behavior

Wrong.

## Root cause

Cause.

## Expected behavior

Expected.
"""
        )
        .replace(
            "- A positive case succeeds.\n- An invalid negative case is rejected.\n- A failed probe degrades to unverified offline behavior.\n- Existing compatibility remains unchanged as a regression check.",
            "- A valid case succeeds.",
        )
        .replace(
            "Run positive, negative, degradation, and regression tests.",
            "Run the focused test.",
        )
    )
    issue = {"number": 3, "title": "fix: coverage", "labels": ["bug"], "body": body}
    result = contract.audit_contract(issue)
    assert set(result["missing_acceptance_coverage"]) >= {
        "negative",
        "degradation",
        "regression",
    }


def test_proposed_body_reaudits_without_required_section_errors() -> None:
    issue = {
        "number": 4,
        "title": "fix: normalize this",
        "labels": ["bug"],
        "body": "## Summary\n\nCurrent text.",
    }
    proposed = contract.propose_normalized_body(issue)
    result = contract.audit_contract({**issue, "body": proposed})
    # The proposed skeleton has all required sections present...
    assert result["missing_required_sections"] == []
    # ...but unresolved placeholders must keep it non-conformant until a
    # maintainer supplies real content.
    assert result["governance_state"] == "needs_contract_revision"
    assert result["contract_accepted"] is False
    assert any(
        finding["code"] == "unresolved-placeholder-section"
        for finding in result["findings"]
    )


def test_proposed_body_is_conformant_once_placeholders_are_resolved() -> None:
    issue = {
        "number": 4,
        "title": "fix: normalize this",
        "labels": ["bug"],
        "body": "## Summary\n\nCurrent text.",
    }
    proposed = contract.propose_normalized_body(issue)
    resolved = proposed.replace(
        contract.UNRESOLVED_PLACEHOLDER, "Concrete maintainer-supplied content."
    )
    result = contract.audit_contract({**issue, "body": resolved})
    assert contract.UNRESOLVED_PLACEHOLDER not in resolved
    assert result["missing_required_sections"] == []
    assert not any(
        finding["code"] == "unresolved-placeholder-section"
        for finding in result["findings"]
    )
    assert result["governance_state"] == "conformant"


def test_governance_proposed_body_uses_reduced_section_set() -> None:
    issue = {
        "number": 80,
        "title": "governance: normalize this",
        "labels": ["governance"],
        "body": "## Summary\n\nCurrent text.",
    }

    proposed = contract.propose_normalized_body(issue)

    assert "## Acceptance criteria" in proposed
    assert "## Explicit non-goals" in proposed
    assert "## Dependencies and traceability" in proposed
    assert "## Focused test plan" not in proposed
    assert "## Scope and likely files" not in proposed


def test_governance_proposed_body_prefers_existing_decision_criteria() -> None:
    issue = {
        "number": 80,
        "title": "governance: normalize this",
        "labels": ["governance"],
        "body": """## Summary

Current text.

## Decision criteria

Keep the already-written decision rule.
""",
    }

    proposed = contract.propose_normalized_body(issue)

    assert "## Decision criteria" in proposed
    assert "Keep the already-written decision rule." in proposed
    assert "## Acceptance criteria" not in proposed


def test_governance_proposed_body_includes_conditional_sections() -> None:
    issue = {
        "number": 80,
        "title": "governance: normalize warehouse review",
        "labels": ["governance"],
        "body": """## Summary

Current text mentions warehouse access.
""",
    }

    proposed = contract.propose_normalized_body(issue)

    assert "## Live behavior and cost tier" in proposed
    assert "## Offline behavior" in proposed


def test_contract_output_is_ascii() -> None:
    issue = {
        "number": 5,
        "title": "fix: ascii",
        "labels": ["bug"],
        "body": common_body(
            """## Current wrong behavior

Wrong.

## Root cause

Cause.

## Expected behavior

Expected.
"""
        ),
    }
    text = str(contract.audit_contract(issue))
    text.encode("ascii")


def test_scoped_conventional_commit_prefixes_infer_kind_without_label() -> None:
    assert contract.infer_issue_kind("fix(cli): resolve crash", []) == "bug_fix"
    assert contract.infer_issue_kind("bug(parser): bad token", []) == "bug_fix"
    assert (
        contract.infer_issue_kind("refactor(core): split module", [])
        == "refactor_architecture"
    )
    assert (
        contract.infer_issue_kind("feat(api): add endpoint", [])
        == "feature_enhancement"
    )
    assert (
        contract.infer_issue_kind("test(triage): add cases", [])
        == "test_verification"
    )
    # Unscoped conventional-commit prefixes still classify correctly.
    assert contract.infer_issue_kind("fix: resolve crash", []) == "bug_fix"


@pytest.mark.parametrize(
    ("title", "labels", "expected_kind"),
    [
        ("governance: decide tracker shape", [], "governance"),
        ("governance: decide tracker shape", ["test"], "governance"),
        ("test: verify live evidence", [], "test_verification"),
        ("test(triage): keep product-test classification", [], "test_verification"),
        ("spike: choose identity attestation", [], "spike_decision"),
        ("feat: add packet", [], "feature_enhancement"),
        ("fix(cli): resolve crash", [], "bug_fix"),
    ],
)
def test_infer_issue_kind_governance_and_existing_prefix_regressions(
    title: str,
    labels: list[str],
    expected_kind: str,
) -> None:
    assert contract.infer_issue_kind(title, labels) == expected_kind


def test_configured_docs_type_label_infers_docs_kind() -> None:
    # policy.toml defines the documentation type label as "docs"; a neutral
    # title must still be recognized via that configured label spelling.
    assert (
        contract.infer_issue_kind("update the contributor guide", ["docs"])
        == "docs_chore_release"
    )
    # The legacy "documentation" spelling and "chore" remain recognized.
    assert (
        contract.infer_issue_kind("update the contributor guide", ["documentation"])
        == "docs_chore_release"
    )
    assert (
        contract.infer_issue_kind("housekeeping", ["chore"]) == "docs_chore_release"
    )


_REDUNDANT_COVERAGE_SECTION = "Negative, degradation, and regression coverage"


def test_redundant_coverage_recommendation_suppressed_when_coverage_present() -> None:
    # common_body() demonstrates negative/degradation/regression coverage in its
    # acceptance and test sections but has no separate edge_cases heading. The
    # named coverage recommendation is then redundant and must be suppressed.
    result = contract.audit_contract(
        {
            "title": "test: dogfood the governance lifecycle",
            "body": common_body(),
            "labels": [{"name": "test"}],
            "milestone": None,
        }
    )
    coverage = result["acceptance_coverage"]
    assert all(coverage[name] for name in ("negative", "degradation", "regression"))
    assert _REDUNDANT_COVERAGE_SECTION not in result["missing_recommended_sections"]
    assert not any(
        finding.get("code") == "missing-recommended-section"
        and finding.get("message", "").endswith(_REDUNDANT_COVERAGE_SECTION)
        for finding in result["findings"]
    )


def test_redundant_coverage_recommendation_kept_when_coverage_absent() -> None:
    # A body with no coverage language must still be reminded of the section.
    result = contract.audit_contract(
        {
            "title": "test: thin fixture",
            "body": "## Summary\n\nA bare summary with no coverage language.\n",
            "labels": [{"name": "test"}],
            "milestone": None,
        }
    )
    coverage = result["acceptance_coverage"]
    assert not any(coverage[name] for name in ("negative", "degradation", "regression"))
    assert _REDUNDANT_COVERAGE_SECTION in result["missing_recommended_sections"]
