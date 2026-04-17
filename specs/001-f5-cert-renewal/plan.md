# Implementation Plan: Automated Certificate Renewal — F5 BIG-IP via DigiCert

**Branch**: `001-f5-cert-renewal` | **Date**: 2026-04-17 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-f5-cert-renewal/spec.md`

## Summary

Ansible role and playbook that detects SSL certificates within a configurable expiry
window on F5 BIG-IP devices, requests replacement certificates from DigiCert
CertCentral REST API, generates CSRs using the `community.crypto` collection on the
control node, deploys the issued certificate and private key via `f5networks.f5_modules`,
verifies the deployment, and persists renewal state for idempotency. Supports dry-run
mode, structured logging, and multi-device sequential processing.

## Technical Context

**Language/Version**: Python 3.11+ (Ansible control node); Ansible ≥ 2.14
**Primary Dependencies**: `community.crypto` (CSR/key gen), `f5networks.f5_modules`
(BIG-IP management), `ansible.builtin.uri` (DigiCert REST calls), `pyOpenSSL`,
`cryptography`
**Storage**: YAML state files per device at `state/<hostname>.yml` on control node
**Testing**: Molecule (role testing), pytest-testinfra (assertions), mock HTTP server
(DigiCert API simulation)
**Target Platform**: Linux control node; targeting F5 BIG-IP management plane (iControl
REST, port 443)
**Project Type**: Ansible role + playbook (CLI automation tool)
**Performance Goals**: Full renewal cycle for 20 devices × 50 certs in < 10 minutes
**Constraints**: Idempotent; no plaintext key storage; sequential per device by default;
exponential backoff on transient API failures (max 3 retries, max 60s)
**Scale/Scope**: Designed for up to ~20 BIG-IP devices and ~50 SSL profiles per device

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|---------|
| I. API-First Integration | ✅ PASS | All F5 ops via iControl REST (`f5networks.f5_modules` + `uri`); all DigiCert ops via CertCentral REST API. No filesystem or UI operations. |
| II. Security by Default | ✅ PASS | Private keys: never logged (`no_log: true`), never written to disk unencrypted. Credentials via env/vault only. TLS enforced on all outbound connections (`validate_certs: true` default). |
| III. Idempotent Operations | ✅ PASS | State file checked before every DigiCert order (no duplicate orders). `f5networks.f5_modules` modules are idempotent by design. Re-run on already-renewed cert produces no changes. |
| IV. Test-First Delivery | ✅ PASS | Molecule scenarios defined before implementation. Tests written to fail first. Integration tests use mock DigiCert server. |
| V. Observability | ✅ PASS | Structured log entry emitted for every lifecycle event (FR-006). Certificate expiry monitored; 30-day alerting threshold is the renewal trigger. |

**Post-Phase 1 re-check**: All principles remain satisfied. No violations to track.

## Project Structure

### Documentation (this feature)

```text
specs/001-f5-cert-renewal/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── inventory-schema.md   # Operator configuration interface
│   ├── digicert-api.md       # DigiCert REST API contract
│   └── f5-api.md             # F5 iControl REST contract
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
roles/
└── f5_digicert_cert_renewal/
    ├── defaults/
    │   └── main.yml             # Default variable values
    ├── tasks/
    │   ├── main.yml             # Entry point; orchestrates phases
    │   ├── detect.yml           # Phase: detect expiring certs on BIG-IP
    │   ├── request.yml          # Phase: generate CSR + order from DigiCert
    │   ├── deploy.yml           # Phase: upload cert+key to BIG-IP, update profile
    │   └── verify.yml           # Phase: confirm deployment, update state file
    ├── handlers/
    │   └── main.yml
    ├── templates/
    │   └── state.yml.j2         # Jinja2 template for per-device state file
    └── meta/
        └── main.yml             # Collection dependencies declaration

playbooks/
└── renew_certificates.yml       # Main entry point playbook

inventory/
├── hosts.yml                    # Device inventory
├── group_vars/
│   └── bigip_devices.yml        # Shared configuration
└── host_vars/
    └── <hostname>.yml           # Per-device SSL profile declarations

state/                           # Runtime state files (gitignored)
└── <hostname>.yml               # Per-device renewal state

molecule/
└── default/
    ├── molecule.yml
    ├── converge.yml
    └── verify.yml

tests/
└── mock_digicert/
    └── server.py                # Mock DigiCert HTTP server for integration tests
```

**Structure Decision**: Single-project Ansible role layout. Chosen because this is a
pure automation/operations project with no frontend or mobile components. The role
encapsulates all logic and is consumed by a thin top-level playbook, enabling reuse
across different inventory environments without modification.

## Complexity Tracking

> No constitution violations requiring justification.
