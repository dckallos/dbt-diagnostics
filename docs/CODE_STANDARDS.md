# Code standards

This document captures the default implementation standard I expect for this
repository when a change is more than small glue. It is not a generic style
guide. It exists to make code durable across Codex sessions, maintainer review,
and future compatibility work.

The short rule: model stable concepts explicitly, validate them deliberately,
keep loose dictionaries at the edges, and keep domain logic independent of IO.

## When this applies

Read this document before editing Python code that touches any of these areas:

- validators, planners, selectors, or scoring logic;
- JSON artifacts, schemas, digests, or `--json` output;
- command handlers or CLI output paths;
- new modules, module boundaries, or service/builder extraction;
- compatibility behavior or migration code;
- code that is likely to grow across more than one issue;
- code where a future maintainer must reason about invariants, not just syntax.

For one-off glue, small tests, or narrow command wiring, do not overbuild. Use
the smallest clear implementation that preserves the local pattern.

## Design principles

- Keep the public contract stable. Internal refactors must preserve existing
  CLI output, JSON keys, digest rules, ordering, and error strings unless the
  issue explicitly authorizes a contract change.
- Push untyped data to the boundary. Parse raw `dict[str, Any]` inputs near IO,
  convert them to typed objects or explicit validators, and serialize back to
  dict/JSON only at the output boundary.
- Prefer named concepts over anonymous shape. If an object has durable fields,
  invariants, ordering, digest behavior, or a schema document, give it a named
  type.
- Make invalid states hard to hide. Validation should collect specific errors
  instead of failing late with generic `KeyError`, `TypeError`, or silently
  accepting malformed input.
- Preserve determinism. Builders for artifact output must make ordering,
  defaults, digest exclusions, and null-vs-empty behavior explicit.
- Let tests prove compatibility. If internals change under a stable artifact,
  add regression coverage for canonical JSON, digests, or error contracts.

## Architecture

Default to a simple layered shape for nontrivial Python changes:

1. CLI command handlers parse arguments, load files, call a service or builder,
   validate output, and write or print results.
2. Application services and builders coordinate workflow: they combine policy,
   snapshots, audit results, validators, and domain objects.
3. Domain objects and validators encode durable concepts, invariants, ordering,
   and compatibility rules.
4. Adapters own IO: GitHub calls, filesystem reads/writes, subprocesses,
   environment access, warehouse access, and raw JSON decoding.

Dependencies point inward. Domain objects and validators must not import CLI
parsers, GitHub clients, subprocess helpers, filesystem writers, or environment
state. CLI code may depend on services. Services may depend on domain types and
explicit adapters. Adapters should return data that is immediately translated
into typed objects or validated at the boundary.

Keep side effects visible:

- Builders should not write files, call GitHub, spawn subprocesses, or read
  environment variables.
- Validators should be pure: same input, same error list, no mutation outside
  the provided validation context.
- Read-only commands should use names and types that make their advisory nature
  obvious, such as `Plan`, `Packet`, `Snapshot`, `Audit`, or `Report`, not
  `Operation` or `Executor`.
- Mutation-capable commands must keep the write path explicit and narrow. Do
  not hide writes behind a helper that also serves read-only code.
- Pass policy, snapshots, clients, and clock-like values as parameters or
  fields. Avoid mutable module globals and implicit singleton state.

Module boundaries should follow ownership, not file size alone:

- Extract a class or module when a concept has durable invariants, multiple
  call sites, an artifact contract, or independent tests.
- Keep related domain objects, builders, and validators close enough that a
  reviewer can follow the contract without jumping across unrelated modules.
- Do not create a new abstraction only to rename one function call.
- If a module begins to mix CLI parsing, IO, domain decisions, and artifact
  serialization, split by responsibility before adding more behavior.
- Prefer dependency injection by constructor or function parameter for clients
  and adapters. Do not patch global clients into domain code.

Compatibility-sensitive architecture needs an explicit boundary:

- Public functions that existing tests, scripts, or users call should remain as
  thin wrappers when internals move behind classes.
- Keep wire-format construction in one place, usually `to_json()` on a domain
  object or one dedicated serializer.
- Keep digest calculation next to the canonical serialization rules it depends
  on.
- When replacing procedural code with objects, prove that the public artifact
  or command behavior is preserved.

## Python object model

Use dataclasses for stable internal shapes:

- Use `@dataclass(frozen=True)` for immutable value objects and artifact parts.
- Use tuples internally for ordered immutable collections when the object should
  not mutate after construction.
- Provide a `to_json()` method when the public artifact must be a dict.
- Provide `from_*()` constructors when translating from repo policy, snapshots,
  audit entries, or other raw input.
- Keep the public wire shape in `to_json()`, not spread across call sites.

Good fit examples:

- a coordinator result envelope;
- a worker packet envelope;
- a project plan, item, column, conflict, safety block, or policy summary;
- a validation finding or structured readiness decision;
- a schema-backed CLI JSON object.

Poor fit examples:

- a local two-field tuple used once in a test;
- a temporary accumulator that never crosses a function boundary;
- a simple mapping that mirrors an existing library API and has no repo-owned
  invariants.

## Validation pattern

For nontrivial validation, prefer a small validator class over one long
procedural function.

Use this shape unless the local code has a better established pattern:

```python
@dataclass
class ValidationContext:
    errors: list[str] = field(default_factory=list)

    def require_string(self, value: object, *, name: str) -> None:
        if not isinstance(value, str):
            self.errors.append(f"{name} must be a string")


@dataclass(frozen=True)
class ArtifactValidator:
    value: Mapping[str, Any]

    def validate(self) -> list[str]:
        context = ValidationContext()
        self._validate_identity(context)
        self._validate_sections(context)
        self._validate_digest(context)
        return context.errors
```

Guidelines:

- Keep each validator method responsible for one concern.
- Reuse helper methods for repeated primitive checks.
- Return `list[str]` when that is the existing API. Do not replace a stable
  error-list contract with exceptions unless the issue calls for it.
- Preserve existing error text when callers or tests already depend on it.
- Validate forbidden shape explicitly, especially mutation-shaped fields such
  as `operations`, issue `body`, or issue `state` in read-only artifacts.
- Recompute digests from the same canonical form used by the builder.

## JSON and compatibility

The `--json` schema is additive-only within a major version. For stable
artifacts:

- Do not remove or rename keys without an explicit schema/version decision.
- Do not change sort order, null-vs-empty behavior, or digest exclusions by
  accident.
- Keep `schema_version` unchanged when internals change but output does not.
- Add a machine schema when the artifact is first-class and consumed outside
  its builder.
- Add a human schema doc when a maintainer or future automation needs to review
  the artifact contract.
- Validate before writing or printing generated artifacts when malformed output
  would mislead a downstream consumer.

When refactoring an existing builder, add one of these proofs:

- a direct expected-output test for the full JSON shape;
- a canonical `json.dumps(..., sort_keys=True)` comparison across two builds;
- a digest-preservation test;
- an in-memory comparison against the previous implementation when practical;
- a golden fixture only when the repo already uses that pattern.

## Command handlers

CLI handlers should stay thin:

- load inputs;
- validate input artifacts;
- call a builder or service object;
- validate the output artifact;
- write or print the result.

Do not bury artifact construction or validation logic inside the CLI command
branch. Put reusable behavior in named functions or classes that tests can call
without invoking a subprocess.

Command handlers are allowed to know about argument names and exit behavior.
They should not own ordering rules, digest exclusions, issue readiness logic,
status mapping, or compatibility decisions.

For read-only commands, tests should prove no GitHub call, subprocess, or
network path is used when that is part of the safety contract.

## Tests

Scale tests to risk:

- Positive: a valid builder output validates cleanly.
- Negative: missing required keys, wrong types, stale digests, and forbidden
  mutation shape fail with specific errors.
- Degradation: empty but well-formed inputs remain valid when that is a
  supported state.
- Regression: existing sibling validators/builders still behave the same.
- Safety: read-only paths do not call GitHub, subprocess, or network helpers.

For compatibility-sensitive code, tests should assert the artifact contract, not
only that the current implementation happens to run.

## Documentation

Docs should follow the code change:

- Update `CHANGELOG.md` under `[Unreleased]` when behavior changes.
- Add or update a schema doc for first-class JSON artifacts.
- Keep `AGENTS.md` short and durable; put detailed standards here.
- Append `docs/PROGRESS_LOG.md` at session end with what changed, validation,
  current state, next steps, and risks.

Do not document an aspirational current state as if it has landed. If a design
doc describes a target state before merge, annotate it as target or pending.

## Review checklist

Before handing off nontrivial Python work, check:

- Stable shapes have named domain objects or a clear reason not to.
- Raw dict handling is limited to input/output boundaries.
- Dependency direction is clean: CLI and adapters depend on services/domain,
  while domain code does not depend on IO, subprocesses, GitHub, or CLI parsing.
- Side effects are explicit and confined to adapter or command boundaries.
- Services/builders coordinate workflow without hiding writes or global state.
- Validators are class-based or otherwise decomposed by concern.
- Public JSON keys, ordering, null-vs-empty behavior, schema version, and digest
  rules are preserved or explicitly changed.
- Tests include positive, negative, degradation, regression, and safety coverage
  where applicable.
- Error messages are specific enough for a maintainer or downstream consumer to
  act on.
- The implementation stays within the project thesis: live,
  database-grounded root-cause analysis, no static linting, and no ungated
  warehouse scans.
