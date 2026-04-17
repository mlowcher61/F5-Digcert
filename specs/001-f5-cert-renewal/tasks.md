---
description: "Task list for Automated Certificate Renewal — F5 BIG-IP via DigiCert"
---

# Tasks: Automated Certificate Renewal — F5 BIG-IP via DigiCert

**Input**: Design documents from `specs/001-f5-cert-renewal/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: Tasks are grouped by user story to enable independent implementation
and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths are included in all descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and Ansible role scaffolding

- [ ] T001 Create Ansible role directory structure: `roles/f5_digicert_cert_renewal/defaults/`, `tasks/`, `handlers/`, `templates/`, `meta/`
- [ ] T002 [P] Create `roles/f5_digicert_cert_renewal/meta/main.yml` declaring collection dependencies: `community.crypto`, `f5networks.f5_modules`
- [ ] T003 [P] Create `playbooks/renew_certificates.yml` — top-level playbook targeting `bigip_devices` host group
- [ ] T004 [P] Create `inventory/hosts.yml` with sample `bigip_devices` group and `ansible_connection: local`
- [ ] T005 [P] Create `inventory/group_vars/bigip_devices.yml` with all default variables from contracts/inventory-schema.md
- [ ] T006 [P] Create `inventory/host_vars/bigip-example.yml` with sample `bigip_ssl_profiles` list
- [ ] T007 [P] Create `state/` directory and add `.gitkeep`; add `state/*.yml` to `.gitignore`
- [ ] T008 [P] Create `molecule/default/molecule.yml` with Docker driver configuration
- [ ] T009 [P] Create `molecule/default/converge.yml` targeting the role
- [ ] T010 [P] Create `tests/mock_digicert/server.py` — Flask-based mock HTTP server for DigiCert API endpoints

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure MUST be complete before any user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T011 Create `roles/f5_digicert_cert_renewal/defaults/main.yml` with all default variable values: `renewal_threshold_days: 30`, `dry_run: false`, `key_size: 4096`, `digicert_validity_years: 1`, `state_dir: "{{ playbook_dir }}/state"`, `max_retries: 3`, `retry_delay_seconds: 10`, `sequential_devices: true`
- [ ] T012 [P] Create `roles/f5_digicert_cert_renewal/templates/state.yml.j2` — Jinja2 template for per-device state file matching schema in data-model.md
- [ ] T013 [P] Create `roles/f5_digicert_cert_renewal/tasks/main.yml` — orchestration entry point that includes detect.yml, request.yml, deploy.yml, verify.yml in sequence; short-circuits on `dry_run: true` after detect
- [ ] T014 Create BIG-IP provider variable block in `roles/f5_digicert_cert_renewal/defaults/main.yml`: `bigip_provider` dict with `server`, `server_port`, `user`, `password`, `validate_certs`, `no_f5_teem: true`
- [ ] T015 [P] Create `roles/f5_digicert_cert_renewal/handlers/main.yml` (empty handler file for future use)

**Checkpoint**: Role skeleton, defaults, templates, and playbook entry points are complete. User story implementation can begin.

---

## Phase 3: User Story 1 — Certificates Renewed Before Expiry (Priority: P1) 🎯 MVP

**Goal**: Detect expiring certs, order from DigiCert, deploy to BIG-IP, verify, and
persist renewal state — all idempotently.

**Independent Test**: Run `ansible-playbook playbooks/renew_certificates.yml -i
inventory/hosts.yml --limit <test-device>` against a BIG-IP with a cert expiring within
30 days. Confirm certificate serial number changes and new expiry is ~1 year out.

### Implementation for User Story 1

- [ ] T016 [US1] Implement `roles/f5_digicert_cert_renewal/tasks/detect.yml` — query BIG-IP iControl REST (`GET /mgmt/tm/sys/file/ssl-cert`) for each `bigip_ssl_profiles` entry; parse `expirationDate`; set `expiring_profiles` list for certs within `renewal_threshold_days`; emit structured log entry per cert checked
- [ ] T017 [US1] Add dry-run short-circuit in `roles/f5_digicert_cert_renewal/tasks/detect.yml` — when `dry_run: true`, print preview report of `expiring_profiles` and set `renewal_required: false`; skip request/deploy/verify phases
- [ ] T018 [US1] Implement state file read in `roles/f5_digicert_cert_renewal/tasks/detect.yml` — load `state/<inventory_hostname>.yml` if it exists; mark profile as `skipped` if `current_serial` matches BIG-IP live serial (idempotency check)
- [ ] T019 [US1] Implement `roles/f5_digicert_cert_renewal/tasks/request.yml` — for each profile in `expiring_profiles`: (1) generate RSA private key via `community.crypto.openssl_privatekey` (in-memory, `no_log: true`); (2) generate CSR via `community.crypto.openssl_csr` with CN and SANs from detected cert; (3) check state file for existing `order_id` in `pending`/`issued` status (idempotency); (4) POST to DigiCert `/order/certificate/ssl` via `ansible.builtin.uri` with exponential backoff (max `max_retries` attempts); (5) write `order_id` and `status: pending` to state file
- [ ] T020 [US1] Implement DigiCert order polling in `roles/f5_digicert_cert_renewal/tasks/request.yml` — poll `GET /order/certificate/{order_id}` every 30 seconds up to 20 attempts; set `cert_id` when `status == issued`; fail with structured log if `status == rejected` or timeout exceeded
- [ ] T021 [US1] Implement certificate download in `roles/f5_digicert_cert_renewal/tasks/request.yml` — `GET /certificate/{cert_id}/download/format/pem_all` via `uri`; parse PEM chain to extract leaf cert; verify CN, SANs, and serial match the order response; store cert PEM and key PEM as facts (`no_log: true` for key)
- [ ] T022 [US1] Implement `roles/f5_digicert_cert_renewal/tasks/deploy.yml` — for each successfully issued profile: (1) upload cert via `f5networks.f5_modules.bigip_ssl_certificate`; (2) upload key via `f5networks.f5_modules.bigip_ssl_key` with `no_log: true`; (3) update SSL profile via `f5networks.f5_modules.bigip_profile_client_ssl`; emit structured log at each step; on any module failure, log error and set `status: failed` in state file without modifying remaining profiles
- [ ] T023 [US1] Implement `roles/f5_digicert_cert_renewal/tasks/verify.yml` — query BIG-IP `GET /mgmt/tm/sys/file/ssl-cert/~<partition>~<cert_name>` for each deployed profile; assert `serialNumber` matches DigiCert-issued serial; assert expiry is ≥ 364 days in future; on pass: write `status: verified`, `current_serial`, `renewed_at` to state file; emit success structured log
- [ ] T024 [US1] Implement state file write in `roles/f5_digicert_cert_renewal/tasks/verify.yml` — render `templates/state.yml.j2` and write to `state/{{ inventory_hostname }}.yml` with all profile renewal records after each device completes (success or failure)

**Checkpoint**: User Story 1 fully functional — automation detects, orders, deploys, verifies, and persists state. Test by running the playbook against a device with an expiring cert.

---

## Phase 4: User Story 2 — Renewal Failure Surfaced and Logged (Priority: P2)

**Goal**: Any failure at any phase is surfaced with a structured log entry, leaves
existing certs untouched, and continues processing remaining devices.

**Independent Test**: Set `DIGICERT_API_KEY` to an invalid value; run the playbook.
Verify: existing cert on BIG-IP is unchanged, structured error log entry is emitted,
playbook exits with non-zero status.

### Implementation for User Story 2

- [ ] T025 [P] [US2] Add DigiCert API error classification block in `roles/f5_digicert_cert_renewal/tasks/request.yml` — catch HTTP 401 and `fail` entire run with structured log; catch HTTP 400/403/404 and `set_fact: profile_status=failed` then continue to next profile; catch 429/5xx and retry with exponential backoff (`retry_delay_seconds * 2^attempt`, cap 60s)
- [ ] T026 [P] [US2] Add BIG-IP error handler in `roles/f5_digicert_cert_renewal/tasks/deploy.yml` — wrap each `f5networks.f5_modules` module call in `block/rescue`; on rescue: emit structured error log with device hostname, profile name, failure reason; set `status: failed` in state record; use `ignore_errors: false` so the rescue block runs but the play continues to next device via `any_errors_fatal: false` at play level
- [ ] T027 [US2] Add `any_errors_fatal: false` and `max_fail_percentage: 100` to `playbooks/renew_certificates.yml` so a failure on one BIG-IP device does not prevent processing of subsequent devices
- [ ] T028 [US2] Implement structured log helper in `roles/f5_digicert_cert_renewal/tasks/main.yml` — define a standard `debug` task format emitting JSON-structured messages: `{"timestamp": "...", "device": "...", "profile": "...", "event": "...", "outcome": "...", "detail": "..."}` for every lifecycle event across all task files
- [ ] T029 [US2] Add playbook-level failure summary task in `roles/f5_digicert_cert_renewal/tasks/main.yml` — at end of role execution, emit a summary log entry listing all profiles with `status: failed` and their reasons; set `ansible_failed_task` if any failures exist to produce non-zero exit code

**Checkpoint**: User Story 2 independently testable — simulate auth failure and network failure; confirm existing certs untouched, errors logged, remaining devices processed.

---

## Phase 5: User Story 3 — Dry-Run Preview Mode (Priority: P3)

**Goal**: Operator can run the automation with `dry_run: true` to see which certs would
be renewed without any API calls to DigiCert or any changes to BIG-IP.

**Independent Test**: Run `ansible-playbook ... -e dry_run=true` against any device.
Verify: zero DigiCert API calls made (check mock server logs), zero BIG-IP config
changes, output lists affected certificates with expiry dates.

### Implementation for User Story 3

- [ ] T030 [US3] Implement dry-run report task in `roles/f5_digicert_cert_renewal/tasks/detect.yml` — when `dry_run: true`, after building `expiring_profiles`, output a formatted preview report via `ansible.builtin.debug` listing each profile: cert name, current expiry, days remaining, action that would be taken; then set `renewal_required: false` to skip all subsequent phases
- [ ] T031 [US3] Add dry-run guard at top of `roles/f5_digicert_cert_renewal/tasks/request.yml` — `when: renewal_required | default(true)` condition on all tasks; ensures zero DigiCert API calls when `dry_run: true`
- [ ] T032 [US3] Add dry-run guard at top of `roles/f5_digicert_cert_renewal/tasks/deploy.yml` — `when: renewal_required | default(true)` condition on all tasks; ensures zero BIG-IP write calls when `dry_run: true`
- [ ] T033 [US3] Add dry-run guard at top of `roles/f5_digicert_cert_renewal/tasks/verify.yml` — `when: renewal_required | default(true)` condition on all tasks; state file write also skipped in dry-run mode

**Checkpoint**: All three user stories independently functional. Full integration testable end-to-end.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements affecting all user stories

- [ ] T034 [P] Write `molecule/default/verify.yml` — pytest-testinfra assertions: role idempotency (run converge twice, confirm no changes on second run); state file created with correct schema; `no_log` applied to all key-handling tasks
- [ ] T035 [P] Write Molecule test scenario for DigiCert mock server integration in `molecule/default/converge.yml` — start `tests/mock_digicert/server.py` before role execution; verify CSR submitted, cert downloaded, state file updated
- [ ] T036 [P] Create `requirements.yml` at repo root declaring: `community.crypto >= 2.0`, `f5networks.f5_modules >= 1.0`, `ansible.builtin >= 2.14`
- [ ] T037 [P] Write `README.md` at repo root referencing quickstart at `specs/001-f5-cert-renewal/quickstart.md`
- [ ] T038 [P] Add `.gitignore` entries: `state/*.yml`, `*.retry`, `*.pyc`, `__pycache__/`, `.molecule/`
- [ ] T039 Run `ansible-lint roles/f5_digicert_cert_renewal/` and fix all warnings; confirm no `no_log` missing on key-handling tasks
- [ ] T040 Run quickstart.md validation — execute dry-run against test BIG-IP and confirm preview output matches expected format

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; all T001–T010 parallelizable
- **Foundational (Phase 2)**: Depends on Phase 1 completion — blocks all user stories; T011–T015 mostly parallelizable
- **User Story 1 (Phase 3)**: Depends on Foundational — MUST complete fully before US2/US3 (error handling and dry-run build on the happy path)
- **User Story 2 (Phase 4)**: Depends on Phase 3 — adds error handling to existing task files
- **User Story 3 (Phase 5)**: Depends on Phase 3 — adds guards to existing task files; can run in parallel with US2
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Core detection → order → deploy → verify pipeline. No dependencies on US2/US3.
- **User Story 2 (P2)**: Adds error handling to US1 task files. Depends on US1 (modifies same files).
- **User Story 3 (P3)**: Adds dry-run guards to US1 task files. Can proceed after US1; independent of US2.

### Within Each User Story

- T016 (detect) must complete before T019 (request)
- T019–T021 (request phases) must complete in order
- T022 (deploy) depends on T021 (cert downloaded)
- T023–T024 (verify + state write) depends on T022 (deployed)
- All [P]-marked tasks within a phase run in parallel

### Parallel Opportunities

```bash
# Phase 1: All setup tasks can run in parallel
T002, T003, T004, T005, T006, T007, T008, T009, T010 (after T001 creates directories)

# Phase 2: Most foundational tasks parallel
T012, T013, T014, T015 (after T011 creates defaults/main.yml)

# Phase 4: Both error handler tasks parallel
T025, T026 (both modify different task files)

# Phase 5: All dry-run guard tasks parallel
T031, T032, T033 (each targets a different task file)

# Phase 6: All polish tasks parallel
T034, T035, T036, T037, T038 (independent files)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (T016–T024)
4. **STOP and VALIDATE**: Run playbook in dry-run mode, then against a test BIG-IP device
5. Confirm: cert renewed, state file written, serial changed, expiry ~1 year out

### Incremental Delivery

1. Setup + Foundational → role skeleton ready
2. User Story 1 → detection, ordering, deployment, verification pipeline (MVP)
3. User Story 2 → error handling, multi-device resilience
4. User Story 3 → dry-run preview mode
5. Polish → linting, Molecule tests, documentation

---

## Notes

- [P] tasks = different files, no shared-state dependencies — safe to run in parallel
- [Story] label maps each task to its user story for traceability to spec.md
- `no_log: true` is non-negotiable on any task touching private key material (Principle II)
- State file is the idempotency mechanism — never skip reading it before placing a DigiCert order
- Verify tests fail before implementing (Principle IV): write Molecule verify assertions before role tasks
- Commit after each user story phase is validated end-to-end
