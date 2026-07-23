# Design: ServiceNow Change Request integration for F5-DigiCert cert renewal

**Date**: 2026-07-23
**Branch**: `002-servicenow-tickets`
**Status**: Approved (design phase)
**Builds on**: `roles/f5_digicert_cert_renewal`, `specs/001-f5-cert-renewal/`

## Summary

Extend the existing F5 BIG-IP + DigiCert certificate-renewal role with ServiceNow ITSM
integration. For every certificate detected as expiring within `renewal_threshold_days`
(default 30), the role opens a **Standard (pre-approved) Change Request** in ServiceNow,
appends a **work note** at each lifecycle milestone as the certificate is requested from
DigiCert and deployed to the BIG-IP, and **auto-closes** the change as `successful` once
verification passes. Any failure adds an error work note and leaves the change **open**
for human triage. Tickets are **reused** across scheduled runs via the existing per-device
state file. The whole integration is gated behind a `servicenow_enabled` flag so the
solution still runs for customers without ServiceNow.

**Scope decisions (YAGNI):**
- Exactly **one ticket per expiring certificate instance** — the identity is
  `(device, SSL profile)`, because the role runs once per BIG-IP host and `expiring_profiles`
  is built per host. The same logical CN present on two devices yields two tickets. No
  per-run or per-device summary ticket.
- No mock-ServiceNow test server in this pass (noted as a follow-up).

## Decisions locked with the user

| Decision | Choice |
|----------|--------|
| Record type | ServiceNow **Change Request**, `type: standard` (pre-approved) |
| De-duplication | **Reuse** one open ticket per cert; ticket number/sys_id persisted to the state file |
| On success | **Auto-close** the change (`close_code: successful`); failures left open |
| Cardinality | **One ticket per expiring certificate instance** |
| `collections/requirements.yml` | **Single source of truth** — root `requirements.yml` removed; EE references this file |
| Request-phase failures | Wrap per-cert request logic in `block`/`rescue` so one cert's failure posts an error work note, records `failed`, and lets other certs continue (behavior change, approved) |

## Architecture

The role keeps its four-phase structure and gains one phase plus in-phase hooks:

```
Phase 1  detect        (unchanged) -> builds expiring_profiles
Phase 1b open_tickets   (NEW)       -> one Standard change per expiring cert; builds profile_ticket_map
Phase 2  request        (+ work notes; + block/rescue failure handling)
Phase 3  deploy         (+ work notes; existing rescue also posts error work note)
Phase 4  verify         (+ work notes; auto-close change on success)
```

Everything ServiceNow-related is gated on `servicenow_enabled | bool` and skipped when
`dry_run | bool` is true (dry-run logs what *would* be opened, creates nothing).

### Ticket threading: `profile_ticket_map`

Rather than enriching the existing `expiring_profiles` / `profiles_to_deploy` /
`deployed_profiles` structures, a per-host dictionary carries ticket identity:

```yaml
profile_ticket_map:
  web_clientssl:
    number: CHG0031234
    sys_id: a1b2c3d4e5f6...
  api_clientssl:
    number: CHG0031235
    sys_id: 0f9e8d7c6b5a...
```

The work-note helper and the closure step look up the ticket by `profile_name`. This keeps
the existing data flow untouched and confines ServiceNow state to one structure.

## Components

### 1. Collections & execution environment

- **`collections/requirements.yml`** (NEW, single source of truth):
  ```yaml
  collections:
    - name: community.crypto
      version: ">=2.0.0"
    - name: f5networks.f5_modules
      version: ">=1.0.0"
    - name: ansible.utils
      version: ">=2.0.0"
    - name: servicenow.itsm
      version: ">=2.0.0"
  ```
- **Root `requirements.yml`**: removed.
- **`execution-environment.yml`**: `dependencies.galaxy` points at `collections/requirements.yml`
  instead of inlining a second list, so `servicenow.itsm` is baked into the EE and there is
  one authoritative collection list.

### 2. ServiceNow custom credential type (config-as-code)

Mirrors the existing DigiCert custom credential type; no secrets stored in the role or git.

- **`credential_types/servicenow.yml`** (standalone, mirrors `credential_types/digicert.yml`):
  - `name: ServiceNow ITSM`, `kind: cloud`
  - fields: `sn_host` (string), `sn_username` (string), `sn_password` (string, secret)
  - required: all three
  - injectors: **extra_vars** `sn_host`, `sn_username`, `sn_password`
- **Role builds `sn_instance`** from the injected vars, exactly as `bigip_provider` is built
  from the injected Network credential:
  ```yaml
  sn_instance:
    host: "{{ sn_host }}"
    username: "{{ sn_username }}"
    password: "{{ sn_password }}"
  ```
  Every `servicenow.itsm.*` module call passes `instance: "{{ sn_instance }}"`.
- Config-as-code wiring:
  - `aap_config/group_vars/all/credential_types.yml` — add the `ServiceNow ITSM` type.
  - `aap_config/group_vars/all/credentials.yml` — add a `ServiceNow ITSM` credential
    instance referencing `vault_sn_*`.
  - `aap_config/group_vars/all/job_templates.yml` — attach the credential to
    `F5-Digicert - Renew Certificates`.
  - `aap_config/example_vault.yml` — add `vault_sn_host`, `vault_sn_username`,
    `vault_sn_password` placeholders.
  - `aap_config/requirements.yml` — **no change** (`servicenow.itsm` is a runtime collection,
    not a config-as-code dependency).

### 3. Role task changes

**New files:**

- **`tasks/tickets.yml`** — Phase 1b orchestrator. Loops `expiring_profiles`, including
  `_open_ticket_single.yml`. Runs only when
  `servicenow_enabled and not dry_run and expiring_profiles | length > 0`.
- **`tasks/_open_ticket_single.yml`** — for one profile:
  1. Look up any prior state record for this `profile_name`. If it carries a
     `servicenow_number`, query `servicenow.itsm.change_request_info` to confirm the change
     is still open (state not in `closed`/`canceled`).
  2. If a still-open change exists, **reuse** it (add a "re-detected, still expiring" work
     note); otherwise **create** a new change via `servicenow.itsm.change_request`
     (`type: "{{ servicenow_change_type }}"`, optional `template: "{{ servicenow_change_template }}"`,
     `short_description`, `description`, `assignment_group`).
  3. Record `{number, sys_id}` into `profile_ticket_map`.
- **`tasks/_add_work_note.yml`** — parameterized helper (`wn_profile_name`, `wn_message`).
  Resolves the sys_id from `profile_ticket_map[wn_profile_name]` and appends a work note via
  the `change_request` module (journal `work_notes` field). No-op when the profile has no
  mapped ticket (e.g., ServiceNow disabled). Included from the request/deploy/verify
  single-profile files with `vars:`.

**Modified files:**

- **`tasks/_request_single.yml`** — wrap the request/order/poll/download logic in a
  `block`/`rescue`:
  - on **block** milestones: include `_add_work_note.yml` after *order placed* and *order issued*.
  - on **rescue**: post an `ERROR: <phase> failed: <reason>` work note, append a `failed`
    state record, and continue to the next cert (no host-level abort).
- **`tasks/_deploy_single.yml`** — add a *deployed* work note in the success path; the
  existing `rescue` gains an error work note.
- **`tasks/_verify_single.yml`** — wrap the verification asserts in a `block`/`rescue`. On
  success: add a *verified* work note, then **close** the change (`servicenow.itsm.change_request`
  with `state: closed`, `close_code: "{{ servicenow_close_code }}"`, `close_notes`) after the
  verified state record is appended. On `rescue`: post an `ERROR: verification failed` work
  note, record a `failed` state, leave the change open.
- **`tasks/main.yml`** — insert `include_tasks: tickets.yml` after detect, gated on
  `servicenow_enabled and not dry_run`.
- **`tasks/detect.yml`** — no logic change; the dry-run path additionally logs the tickets
  that *would* be opened.

**Work-note milestones** (reuse existing lifecycle events):

| Event | Work note (abbreviated) |
|-------|-------------------------|
| opened | `Change opened to renew <cn> (serial <old>), expires <date>, <N> days remaining, on <device>/<profile>.` |
| order placed | `DigiCert order <order_id> placed for <cn>.` |
| order issued | `DigiCert order <order_id> issued; cert id <cert_id>, new serial <serial>.` |
| deployed | `Certificate + key uploaded to <device>; SSL profile <profile> updated.` |
| verified | `Deployment verified on <device>: serial <serial>, expiry <date>. Renewal complete.` (then close) |
| failure | `ERROR during <phase>: <reason>. Change left open for manual review.` |

### 4. State schema

- **`templates/state.yml.j2`** — add two fields per record:
  ```yaml
  servicenow_number: {{ record.servicenow_number | default('null') }}
  servicenow_sys_id: {{ record.servicenow_sys_id | default('null') }}
  ```
- All record builders (`detect.yml` dry-run/skipped, `_deploy_single.yml` rescue,
  `_verify_single.yml`, `verify.yml` skipped) populate `servicenow_number`/`servicenow_sys_id`
  by looking the profile up in `profile_ticket_map` (default `null` when ServiceNow disabled).

### 5. Playbook guard

- **`playbooks/renew_certificates.yml`** `pre_tasks` — extend the credential assertion to
  also require `sn_host`, `sn_username`, `sn_password` **when `servicenow_enabled | bool`**,
  under `no_log: true`.

### 6. Role defaults (`defaults/main.yml`)

```yaml
# ServiceNow ITSM integration
servicenow_enabled: true
servicenow_change_type: standard          # pre-approved Standard change
servicenow_change_template: ""            # optional: Standard Change template name/sys_id
servicenow_assignment_group: ""           # optional
servicenow_close_code: successful
# sn_host / sn_username / sn_password injected by the ServiceNow ITSM credential type
sn_instance:
  host: "{{ sn_host | default('') }}"
  username: "{{ sn_username | default('') }}"
  password: "{{ sn_password | default('') }}"
```

> **ServiceNow note:** Standard changes are typically produced from a Change Template
> (`std_change_producer`). `servicenow_change_template` lets a customer point at their
> template by name/sys_id; left empty, the module creates a `standard`-type change directly.
> This is validated during the plan/research step.

## Data flow

```
detect ─▶ expiring_profiles ─▶ open_tickets ─▶ profile_ticket_map
                                                     │
   request(cert) ──work note(placed/issued)──────────┤
        │ (rescue) ──work note(ERROR)────────────────┤
   deploy(cert)  ──work note(deployed)───────────────┤
        │ (rescue) ──work note(ERROR)────────────────┤
   verify(cert)  ──work note(verified) + CLOSE───────┘
                                                     │
                                          state/<host>.yml
                              (servicenow_number, servicenow_sys_id persisted)
```

## Error handling

- **Request failure** (order/poll/download): rescue posts an error work note, records a
  `failed` state, continues with other certs. Change left open.
- **Deploy failure**: existing rescue additionally posts an error work note. Change left open.
- **Verify failure**: assertion failure posts an error work note (via a wrapping rescue) and
  records `failed`; change left open.
- **ServiceNow API failure** while opening/updating a ticket: does **not** abort the renewal —
  the certificate work is the priority. The failure is logged (structured log line) and the
  run continues; the missing ticket surfaces in the job output. (Reuse of `until`/`retries`
  on ServiceNow calls for transient errors, consistent with the DigiCert calls.)
- **`servicenow_enabled: false`**: all ticket tasks skip; `profile_ticket_map` stays empty;
  state records write `null` ticket fields. Existing behavior is unchanged.

## Testing

- **Molecule** (`molecule/default/converge.yml`): set `servicenow_enabled: false` so the
  existing scenario stays green without a live ServiceNow instance. The DigiCert mock server
  path is unaffected.
- **Follow-up (not this pass):** a `tests/mock_servicenow/server.py` paralleling
  `tests/mock_digicert/server.py`, plus a molecule scenario exercising the ServiceNow path.

## Documentation

- **`README.md`** — new section covering the ServiceNow integration: the `ServiceNow ITSM`
  credential type, the `servicenow_enabled` flag and related knobs, the work-note lifecycle,
  the reuse/idempotency behavior, and setup steps. Note that `collections/requirements.yml`
  is the single source of truth for collections.
- **`aap_config/README.md`** — document the new credential type, credential, and vault vars.

## Out of scope

- Per-run or per-device summary tickets.
- Change approval workflows (Standard changes are pre-approved by definition).
- Mock-ServiceNow test server and a dedicated molecule scenario (follow-up).
- OAuth / token auth for ServiceNow (basic auth via the credential type for now; OAuth fields
  can be added to the credential type later without role changes).
