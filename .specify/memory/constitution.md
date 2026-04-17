<!--
SYNC IMPACT REPORT
==================
Version change: (none) → 1.0.0 (initial ratification)
Modified principles: N/A (initial)
Added sections:
  - Core Principles (5 principles)
  - Operational Standards
  - Development Workflow
  - Governance
Removed sections: N/A (initial)
Templates updated:
  - .specify/templates/plan-template.md ✅ Constitution Check gate already present
  - .specify/templates/spec-template.md ✅ Structure compatible with principles
  - .specify/templates/tasks-template.md ✅ Task phases align with principle-driven categories
  - .specify/templates/commands/ ⚠️ No command override files found — no updates needed
Follow-up TODOs:
  - TODO(RATIFICATION_DATE): Confirm original adoption date; set to 2026-04-17 (today) as first ratification.
  - TODO(TECH_STACK): Confirm target language/framework once first feature spec is created.
-->

# F5 DigiCert Integration Constitution

## Core Principles

### I. API-First Integration

All interactions with F5 BIG-IP/NGINX and DigiCert MUST be performed through their
official REST APIs. Direct file-system access to F5 devices, manual certificate uploads
via UI, or out-of-band operations are prohibited.

**Rationale**: API-driven operations are auditable, repeatable, and automatable.
Bypassing the API layer creates untracked state that undermines the reliability of the
integration.

### II. Security by Default

Private keys MUST never be transmitted in plaintext or logged. All API credentials
(DigiCert API key, F5 admin credentials) MUST be sourced from a secrets manager or
environment variables — never hardcoded or committed to source control. TLS 1.2 or
higher MUST be enforced on all outbound connections.

**Rationale**: Certificate management systems are high-value targets; a single credential
leak can compromise the entire PKI chain.

### III. Idempotent Operations

Every certificate operation (request, renewal, revocation, deployment) MUST be
idempotent. Re-running the same command against the same target MUST produce the same
end-state without errors or duplicate side effects.

**Rationale**: Automation pipelines may retry on failure. Non-idempotent operations cause
duplicate certificate requests (wasting quota) or partial deployments that break traffic.

### IV. Test-First Delivery

All new integration paths MUST have tests written and confirmed to fail before
implementation begins. The Red-Green-Refactor cycle is enforced. Integration tests MUST
run against a real (or sandbox) DigiCert API and a real F5 management endpoint, not
mocks that diverge from production behavior.

**Rationale**: Certificate renewals silently failing in production are a P0 outage risk.
Mocked tests have historically masked this class of failure.

### V. Observability

Every certificate lifecycle event (requested, issued, deployed, expiry warning, revoked)
MUST emit a structured log entry with: timestamp, certificate CN/SAN, serial number, F5
target device, and outcome. Certificate expiry MUST be monitored and alerting thresholds
configured at ≥30 days before expiry.

**Rationale**: Certificate-related outages are almost always caused by missed renewals.
Structured, queryable logs are required for post-incident analysis.

## Operational Standards

- All operations MUST handle transient API failures with exponential backoff (max 3
  retries, max 60s delay). Permanent failures MUST surface a clear error and halt.
- Certificate state (serial, expiry, deployment targets) MUST be persisted after each
  successful operation so that the system can resume from partial failures.
- Configuration MUST be validated at startup against a schema before any API call is made.
- Breaking changes to the configuration schema MUST increment the MAJOR version and
  provide a migration guide.

## Development Workflow

- All feature work MUST be done on a feature branch following the naming convention
  defined in `.specify/extensions.yml` (sequential branch numbering).
- A spec (`spec.md`), plan (`plan.md`), and task list (`tasks.md`) MUST exist before
  implementation begins.
- PRs MUST verify all five Core Principles are satisfied. Complexity violations MUST be
  documented in the plan's Complexity Tracking table with justification.
- The constitution supersedes all other practices. Amendments require a PR, a version
  bump, and updates to dependent templates within the same commit.

## Governance

This constitution supersedes all other project conventions. Any practice not covered here
defaults to the most secure and observable option.

**Amendment procedure**:
1. Open a PR updating `.specify/memory/constitution.md` with a version bump.
2. Run `/speckit-constitution` to propagate changes to dependent templates.
3. Include a Sync Impact Report in the PR description.
4. At least one reviewer MUST confirm all templates are updated before merge.

**Versioning policy**: Semantic versioning (MAJOR.MINOR.PATCH).
- MAJOR: Principle removal or backward-incompatible redefinition.
- MINOR: New principle or section added.
- PATCH: Clarifications, wording, non-semantic refinements.

**Compliance review**: Every feature plan (`plan.md`) MUST include a Constitution Check
gate before Phase 0 research and re-verify after Phase 1 design.

**Version**: 1.0.0 | **Ratified**: 2026-04-17 | **Last Amended**: 2026-04-17
