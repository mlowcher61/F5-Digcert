# ServiceNow Change Request Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open a ServiceNow Standard (pre-approved) change request for every certificate expiring within the renewal window, append work notes at each renewal milestone, and auto-close the change on successful verification.

**Architecture:** Extends the existing `f5_digicert_cert_renewal` role. A new ticket-opening phase runs after `detect` and builds a per-host `profile_ticket_map` (profile_name → {number, sys_id}). The existing per-profile request/deploy/verify task files gain work-note calls and (request/verify) `block`/`rescue` wrappers. Ticket identity is persisted to the per-device state file so scheduled re-runs reuse the open change. Everything is gated on `servicenow_enabled` and skipped in `dry_run`.

**Tech Stack:** Ansible (AAP / ansible-core ≥ 2.14), `servicenow.itsm` collection, `f5networks.f5_modules`, `community.crypto`, `infra.aap_configuration` (config-as-code), Molecule (docker), ansible-lint, yamllint, ansible-builder (EE).

**Design reference:** `docs/superpowers/specs/2026-07-23-servicenow-cert-renewal-tickets-design.md`

## Global Constraints

- **Collections single source of truth:** `collections/requirements.yml`. Root `requirements.yml` is removed; `execution-environment.yml` and `molecule/default/molecule.yml` reference the `collections/` file. Every collection list edit happens in that one file.
- **Collection version floors (verbatim):** `community.crypto >=2.0.0`, `f5networks.f5_modules >=1.0.0`, `ansible.utils >=2.0.0`, `servicenow.itsm >=2.0.0`.
- **FQCN everywhere:** e.g. `servicenow.itsm.change_request`, `servicenow.itsm.change_request_info`, `ansible.builtin.set_fact`.
- **Secrets:** any task that receives `sn_password` (or resolves `sn_instance`) into a module runs under `no_log: true`. No secret is ever written to disk or a log line.
- **Custom credentials, not vaulted role files:** ServiceNow auth is injected by a custom AAP credential type (`ServiceNow ITSM`) as extra_vars `sn_host`/`sn_username`/`sn_password`. The role builds `sn_instance` from them, mirroring `bigip_provider`.
- **Gating:** every ServiceNow task is gated `when: servicenow_enabled | bool` and additionally skipped when `dry_run | bool` is true (no side effects in dry-run).
- **Cardinality:** exactly one change request per expiring certificate instance `(device, SSL profile)`. Reuse the open change across runs; never open a duplicate.
- **Idempotency:** re-running produces no new tickets and no duplicate work is done; ticket reuse is driven by `state/<host>.yml` plus a `change_request_info` liveness check.
- **Non-fatal ticketing:** a ServiceNow API failure must not abort certificate renewal; it is logged and the run continues.

## File Structure

**Create:**
- `collections/requirements.yml` — single source of truth for Galaxy collections.
- `credential_types/servicenow.yml` — standalone `ServiceNow ITSM` custom credential type (import reference).
- `roles/f5_digicert_cert_renewal/tasks/tickets.yml` — Phase 1b orchestrator (loops expiring profiles).
- `roles/f5_digicert_cert_renewal/tasks/_open_ticket_single.yml` — open-or-reuse one change request.
- `roles/f5_digicert_cert_renewal/tasks/_add_work_note.yml` — parameterized work-note helper.

**Modify:**
- `execution-environment.yml` — point `dependencies.galaxy` at `collections/requirements.yml`.
- `molecule/default/molecule.yml` — point galaxy `requirements-file` at the `collections/` file.
- `molecule/default/converge.yml` — set `servicenow_enabled: false`.
- `aap_config/group_vars/all/credential_types.yml` — add `ServiceNow ITSM` type.
- `aap_config/group_vars/all/credentials.yml` — add ServiceNow credential instance.
- `aap_config/group_vars/all/job_templates.yml` — attach ServiceNow credential to the template.
- `aap_config/example_vault.yml` — add `vault_sn_*` placeholders.
- `roles/f5_digicert_cert_renewal/defaults/main.yml` — ServiceNow defaults + `sn_instance` + `profile_ticket_map` default.
- `playbooks/renew_certificates.yml` — extend the credential assertion for ServiceNow vars.
- `roles/f5_digicert_cert_renewal/tasks/main.yml` — insert the ticket-opening phase.
- `roles/f5_digicert_cert_renewal/tasks/detect.yml` — dry-run "would open" log + sn fields in dry-run record.
- `roles/f5_digicert_cert_renewal/tasks/_request_single.yml` — block/rescue + placed/issued work notes + failed record.
- `roles/f5_digicert_cert_renewal/tasks/_deploy_single.yml` — deployed work note + rescue error note + sn fields.
- `roles/f5_digicert_cert_renewal/tasks/_verify_single.yml` — block/rescue + verified note + close + sn fields.
- `roles/f5_digicert_cert_renewal/tasks/verify.yml` — sn fields in the skipped record.
- `roles/f5_digicert_cert_renewal/templates/state.yml.j2` — persist `servicenow_number` / `servicenow_sys_id`.
- `README.md`, `aap_config/README.md` — document the integration.

**Delete:**
- `requirements.yml` (root).

## Prerequisites (run once before Task 1)

- [ ] **Install collections and lint tools into the working environment**

```bash
cd /Users/mlowcher/claude-repos/F5-Digcert
python3 -m pip install --quiet ansible-lint yamllint 2>/dev/null || true
```

(Collections are installed in Task 1 once `collections/requirements.yml` exists. Molecule/docker are optional; where a step calls `molecule` and it is unavailable, run the yamllint + ansible-lint + syntax-check checks in that step and note molecule as skipped.)

---

### Task 1: Collections single source of truth + EE + molecule wiring

**Files:**
- Create: `collections/requirements.yml`
- Delete: `requirements.yml`
- Modify: `execution-environment.yml`, `molecule/default/molecule.yml`

**Interfaces:**
- Produces: `collections/requirements.yml` as the only Galaxy requirements file, including `servicenow.itsm >=2.0.0`. All later tasks assume `servicenow.itsm` resolves from here.

- [ ] **Step 1: Create `collections/requirements.yml`**

```yaml
---
# Single source of truth for Galaxy collections used by this project.
# Referenced by execution-environment.yml and molecule/default/molecule.yml.
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

- [ ] **Step 2: Delete the root `requirements.yml`**

```bash
git rm requirements.yml
```

- [ ] **Step 3: Point the EE at the collections file**

Replace the `dependencies:` block in `execution-environment.yml` with:

```yaml
dependencies:
  galaxy: collections/requirements.yml
  python:
    - pyOpenSSL
    - cryptography
  system: []
```

- [ ] **Step 4: Point molecule at the collections file**

In `molecule/default/molecule.yml`, replace the `dependency:` block with:

```yaml
dependency:
  name: galaxy
  options:
    requirements-file: ${MOLECULE_PROJECT_DIRECTORY}/collections/requirements.yml
```

- [ ] **Step 5: Install collections and validate the requirements file resolves**

Run:
```bash
ansible-galaxy collection install -r collections/requirements.yml
```
Expected: installs succeed, including `servicenow.itsm` and `f5networks.f5_modules` (output ends without an ERROR line). Then:
```bash
yamllint collections/requirements.yml execution-environment.yml molecule/default/molecule.yml
```
Expected: no errors (warnings acceptable per repo style).

- [ ] **Step 6: Confirm the root requirements file is gone**

Run: `test ! -f requirements.yml && echo REMOVED`
Expected: `REMOVED`

- [ ] **Step 7: Commit**

```bash
git add collections/requirements.yml execution-environment.yml molecule/default/molecule.yml
git commit -m "build: make collections/requirements.yml the single source of truth; add servicenow.itsm"
```

---

### Task 2: ServiceNow custom credential type + config-as-code wiring

**Files:**
- Create: `credential_types/servicenow.yml`
- Modify: `aap_config/group_vars/all/credential_types.yml`, `aap_config/group_vars/all/credentials.yml`, `aap_config/group_vars/all/job_templates.yml`, `aap_config/example_vault.yml`

**Interfaces:**
- Produces: a `ServiceNow ITSM` credential type that injects extra_vars `sn_host`, `sn_username`, `sn_password`. Task 3 consumes those to build `sn_instance`.

- [ ] **Step 1: Create the standalone credential type reference `credential_types/servicenow.yml`**

```yaml
---
# AAP Custom Credential Type — ServiceNow ITSM
# Import via: Credentials > Credential Types > Add
name: ServiceNow ITSM
description: API credentials for the ServiceNow ITSM REST API (servicenow.itsm collection)
kind: cloud

inputs:
  fields:
    - id: sn_host
      type: string
      label: ServiceNow Host URL
      help_text: Full instance URL, e.g. https://dev12345.service-now.com
    - id: sn_username
      type: string
      label: ServiceNow Username
    - id: sn_password
      type: string
      label: ServiceNow Password
      secret: true
  required:
    - sn_host
    - sn_username
    - sn_password

injectors:
  extra_vars:
    sn_host: "{{ sn_host }}"
    sn_username: "{{ sn_username }}"
    sn_password: "{{ sn_password }}"
```

- [ ] **Step 2: Add the type to config-as-code**

Append to `aap_config/group_vars/all/credential_types.yml`, under the existing `controller_credential_types:` list (add as a new list item — keep the DigiCert entry intact):

```yaml
  - name: ServiceNow ITSM
    description: API credentials for the ServiceNow ITSM REST API (servicenow.itsm collection)
    kind: cloud
    inputs:
      fields:
        - id: sn_host
          type: string
          label: ServiceNow Host URL
          help_text: Full instance URL, e.g. https://dev12345.service-now.com
        - id: sn_username
          type: string
          label: ServiceNow Username
        - id: sn_password
          type: string
          label: ServiceNow Password
          secret: true
      required:
        - sn_host
        - sn_username
        - sn_password
    injectors:
      extra_vars:
        sn_host: "{{ sn_host }}"
        sn_username: "{{ sn_username }}"
        sn_password: "{{ sn_password }}"
    state: present
```

- [ ] **Step 3: Add the credential instance**

Append to `aap_config/group_vars/all/credentials.yml`, under the existing `controller_credentials:` list:

```yaml
  - name: ServiceNow ITSM
    description: ServiceNow instance URL and API account
    organization: F5-Digicert
    credential_type: ServiceNow ITSM
    inputs:
      sn_host: "{{ vault_sn_host }}"
      sn_username: "{{ vault_sn_username }}"
      sn_password: "{{ vault_sn_password }}"
    state: present
```

- [ ] **Step 4: Attach the credential to the job template**

In `aap_config/group_vars/all/job_templates.yml`, add `- ServiceNow ITSM` to the `credentials:` list of `F5-Digicert - Renew Certificates` so it reads:

```yaml
    credentials:
      - F5 BIG-IP Admin
      - DigiCert CertCentral API
      - ServiceNow ITSM
```

- [ ] **Step 5: Add vault placeholders**

Append to `aap_config/example_vault.yml`:

```yaml

# ServiceNow ITSM (AAP custom credential)
vault_sn_host: https://dev12345.service-now.com
vault_sn_username: svc_ansible
vault_sn_password: CHANGE_ME
```

- [ ] **Step 6: Validate YAML**

Run:
```bash
yamllint credential_types/servicenow.yml aap_config/group_vars/all/credential_types.yml aap_config/group_vars/all/credentials.yml aap_config/group_vars/all/job_templates.yml aap_config/example_vault.yml
```
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add credential_types/servicenow.yml aap_config/
git commit -m "feat(aap): add ServiceNow ITSM custom credential type and config-as-code wiring"
```

---

### Task 3: Role defaults, `sn_instance`, playbook guard, molecule gate

**Files:**
- Modify: `roles/f5_digicert_cert_renewal/defaults/main.yml`, `playbooks/renew_certificates.yml`, `molecule/default/converge.yml`

**Interfaces:**
- Consumes: injected `sn_host` / `sn_username` / `sn_password` (Task 2).
- Produces: `sn_instance` (dict: host, username, password), `profile_ticket_map` (dict, default `{}`), and the `servicenow_*` config knobs consumed by Tasks 5–9.

- [ ] **Step 1: Append ServiceNow defaults**

Add to the end of `roles/f5_digicert_cert_renewal/defaults/main.yml`:

```yaml

# ServiceNow ITSM integration
servicenow_enabled: true
servicenow_change_type: standard          # pre-approved Standard change
servicenow_change_template: ""            # optional: Standard Change template name or sys_id
servicenow_assignment_group: ""           # optional assignment group
servicenow_close_code: successful         # close_code used on successful verification

# sn_host / sn_username / sn_password are injected by the ServiceNow ITSM credential type
sn_instance:
  host: "{{ sn_host | default('') }}"
  username: "{{ sn_username | default('') }}"
  password: "{{ sn_password | default('') }}"

# Per-host map of profile_name -> {number, sys_id}; populated by tickets.yml
profile_ticket_map: {}
```

- [ ] **Step 2: Extend the playbook credential assertion**

In `playbooks/renew_certificates.yml`, replace the `Validate required credentials are present` task's `that:` list so ServiceNow vars are required only when enabled. The task becomes:

```yaml
    - name: Validate required credentials are present
      ansible.builtin.assert:
        that:
          - ansible_user is defined and ansible_user | length > 0
          - ansible_password is defined and ansible_password | length > 0
          - digicert_api_key is defined and digicert_api_key | length > 0
          - digicert_org_id is defined and digicert_org_id | int > 0
          - not (servicenow_enabled | bool) or (sn_host is defined and sn_host | length > 0)
          - not (servicenow_enabled | bool) or (sn_username is defined and sn_username | length > 0)
          - not (servicenow_enabled | bool) or (sn_password is defined and sn_password | length > 0)
        fail_msg: >-
          Missing required credentials. Attach a Network credential, the DigiCert
          custom credential, and (when servicenow_enabled) the ServiceNow ITSM
          custom credential to this job template in AAP.
      no_log: true
```

- [ ] **Step 3: Gate ServiceNow off in molecule**

In `molecule/default/converge.yml`, add `servicenow_enabled: false` to the `vars:` block:

```yaml
  vars:
    dry_run: true
    servicenow_enabled: false
    bigip_username: testuser
    bigip_password: testpass
    digicert_api_key: test-api-key
    digicert_org_id: 12345
    state_dir: /tmp/f5_cert_renewal_state
    renewal_threshold_days: 30
```

- [ ] **Step 4: Validate**

Run:
```bash
yamllint roles/f5_digicert_cert_renewal/defaults/main.yml playbooks/renew_certificates.yml molecule/default/converge.yml
ansible-playbook playbooks/renew_certificates.yml --syntax-check -i inventory/hosts.yml
```
Expected: yamllint clean; syntax-check prints the playbook path with no error.

- [ ] **Step 5: Commit**

```bash
git add roles/f5_digicert_cert_renewal/defaults/main.yml playbooks/renew_certificates.yml molecule/default/converge.yml
git commit -m "feat: add ServiceNow role defaults, sn_instance, playbook guard, molecule gate"
```

---

### Task 4: State schema — persist ticket identity

**Files:**
- Modify: `roles/f5_digicert_cert_renewal/templates/state.yml.j2`, `roles/f5_digicert_cert_renewal/tasks/detect.yml`

**Interfaces:**
- Consumes: `profile_ticket_map` (Task 3).
- Produces: state records carrying `servicenow_number` / `servicenow_sys_id`; a `change_request_info`-ready reuse signal for Task 5.

- [ ] **Step 1: Add the two fields to the state template**

In `roles/f5_digicert_cert_renewal/templates/state.yml.j2`, insert two lines after the `order_id:` line so the per-profile block reads:

```jinja
  - profile_name: {{ record.profile_name }}
    cert_name: {{ record.cert_name }}
    previous_serial: {{ record.previous_serial | default('null') }}
    current_serial: {{ record.current_serial | default('null') }}
    order_id: {{ record.order_id | default('null') }}
    servicenow_number: {{ record.servicenow_number | default('null') }}
    servicenow_sys_id: {{ record.servicenow_sys_id | default('null') }}
    status: {{ record.status }}
    last_checked_at: "{{ record.last_checked_at | default(ansible_date_time.iso8601) }}"
    renewed_at: {{ record.renewed_at | default('null') }}
    failure_reason: {{ record.failure_reason | default('null') }}
```

- [ ] **Step 2: Add sn fields to the dry-run skipped record builder**

In `roles/f5_digicert_cert_renewal/tasks/detect.yml`, inside the `DRY RUN - Build skipped state records` task, add the two keys to the appended dict (right after `'order_id': null,`):

```jinja
            'order_id': null,
            'servicenow_number': profile_ticket_map.get(profile.profile_name, {}).get('number', 'null'),
            'servicenow_sys_id': profile_ticket_map.get(profile.profile_name, {}).get('sys_id', 'null'),
```

- [ ] **Step 3: Add a dry-run "would open" log to detect.yml**

In `roles/f5_digicert_cert_renewal/tasks/detect.yml`, after the existing `DRY RUN - Report certificates that would be renewed` task, add:

```yaml
- name: DRY RUN - Report ServiceNow change requests that would be opened
  ansible.builtin.debug:
    msg: >-
      DRY RUN: Would open a {{ servicenow_change_type }} ServiceNow change request for
      {{ item.cert_name }} (CN {{ item.cert_cn }}) on profile {{ item.profile_name }}
  loop: "{{ expiring_profiles }}"
  loop_control:
    label: "{{ item.profile_name }}"
  when:
    - dry_run | bool
    - servicenow_enabled | bool
```

- [ ] **Step 4: Validate**

Run:
```bash
yamllint roles/f5_digicert_cert_renewal/tasks/detect.yml
ansible-lint roles/f5_digicert_cert_renewal
```
Expected: yamllint clean; ansible-lint reports no new errors (pre-existing warnings, if any, unchanged).

- [ ] **Step 5: Commit**

```bash
git add roles/f5_digicert_cert_renewal/templates/state.yml.j2 roles/f5_digicert_cert_renewal/tasks/detect.yml
git commit -m "feat: persist ServiceNow ticket identity in state and dry-run reporting"
```

---

### Task 5: Ticket-opening phase (open-or-reuse)

**Files:**
- Create: `roles/f5_digicert_cert_renewal/tasks/tickets.yml`, `roles/f5_digicert_cert_renewal/tasks/_open_ticket_single.yml`
- Modify: `roles/f5_digicert_cert_renewal/tasks/main.yml`

**Interfaces:**
- Consumes: `expiring_profiles` (from detect.yml — each item has `profile_name`, `cert_name`, `cert_cn`, `cert_serial`, `expiry_str`, `days_remaining`), `existing_state.profiles`, `sn_instance`, `servicenow_*` knobs.
- Produces: `profile_ticket_map` populated with `{ <profile_name>: { number, sys_id } }` for every expiring profile that has a live change request.

- [ ] **Step 1: Create `tasks/tickets.yml`**

```yaml
---
# Phase 1b: open (or reuse) one ServiceNow Standard change request per expiring certificate.
# Runs only when ServiceNow is enabled and this is not a dry run.

- name: Initialize per-host ticket map
  ansible.builtin.set_fact:
    profile_ticket_map: {}

- name: Open or reuse a change request for each expiring certificate
  ansible.builtin.include_tasks: _open_ticket_single.yml
  loop: "{{ expiring_profiles }}"
  loop_control:
    loop_var: ticket_profile
    label: "{{ ticket_profile.profile_name }}"
```

- [ ] **Step 2: Create `tasks/_open_ticket_single.yml`**

```yaml
---
# Open or reuse a single ServiceNow change request.
# Input: ticket_profile (loop var). Updates: profile_ticket_map.

- name: "{{ ticket_profile.profile_name }} | Find prior ticket number in state"
  ansible.builtin.set_fact:
    prior_ticket_number: >-
      {%- set records = existing_state.profiles
          | selectattr('profile_name', 'equalto', ticket_profile.profile_name)
          | list -%}
      {%- if records | length > 0 and records[0].servicenow_number is defined
             and records[0].servicenow_number not in ['null', '', None] -%}
      {{ records[0].servicenow_number }}
      {%- else -%}
      {%- endif -%}

- name: "{{ ticket_profile.profile_name }} | Look up prior change request state"
  servicenow.itsm.change_request_info:
    instance: "{{ sn_instance }}"
    number: "{{ prior_ticket_number }}"
  register: prior_cr
  no_log: true
  when: prior_ticket_number | length > 0
  failed_when: false

- name: "{{ ticket_profile.profile_name }} | Decide whether prior ticket is reusable"
  ansible.builtin.set_fact:
    reuse_ticket: >-
      {{ prior_ticket_number | length > 0
         and prior_cr.records is defined
         and prior_cr.records | length > 0
         and prior_cr.records[0].state not in ['closed', 'canceled'] }}

- name: "{{ ticket_profile.profile_name }} | Create new Standard change request"
  servicenow.itsm.change_request:
    instance: "{{ sn_instance }}"
    type: "{{ servicenow_change_type }}"
    template: "{{ servicenow_change_template or omit }}"
    assignment_group: "{{ servicenow_assignment_group or omit }}"
    short_description: "Renew SSL certificate {{ ticket_profile.cert_cn }} on {{ inventory_hostname }}"
    description: >-
      Automated renewal (Ansible Automation Platform). Certificate {{ ticket_profile.cert_name }}
      (CN {{ ticket_profile.cert_cn }}, serial {{ ticket_profile.cert_serial }}) on SSL profile
      {{ ticket_profile.profile_name }} of BIG-IP {{ inventory_hostname }} expires
      {{ ticket_profile.expiry_str }} ({{ ticket_profile.days_remaining }} days remaining).
    other:
      work_notes: >-
        Change opened by AAP to renew {{ ticket_profile.cert_cn }} (serial
        {{ ticket_profile.cert_serial }}), expiring {{ ticket_profile.expiry_str }},
        on {{ inventory_hostname }}/{{ ticket_profile.profile_name }}.
  register: new_cr
  no_log: true
  when: not (reuse_ticket | bool)

- name: "{{ ticket_profile.profile_name }} | Add re-detection note to reused change"
  servicenow.itsm.change_request:
    instance: "{{ sn_instance }}"
    number: "{{ prior_ticket_number }}"
    other:
      work_notes: >-
        Re-detected during scheduled run: {{ ticket_profile.cert_cn }} still expiring
        {{ ticket_profile.expiry_str }} ({{ ticket_profile.days_remaining }} days remaining).
  no_log: true
  when: reuse_ticket | bool
  failed_when: false

- name: "{{ ticket_profile.profile_name }} | Record ticket in profile_ticket_map"
  ansible.builtin.set_fact:
    profile_ticket_map: >-
      {{ profile_ticket_map | combine({
           ticket_profile.profile_name: {
             'number': (prior_ticket_number if (reuse_ticket | bool) else new_cr.record.number),
             'sys_id': (prior_cr.records[0].sys_id if (reuse_ticket | bool) else new_cr.record.sys_id)
           }
         }) }}

- name: "{{ ticket_profile.profile_name }} | Log ticket association"
  ansible.builtin.debug:
    msg: >-
      {
        "timestamp": "{{ ansible_date_time.iso8601 }}",
        "device": "{{ inventory_hostname }}",
        "profile": "{{ ticket_profile.profile_name }}",
        "event": "{{ 'change_reused' if (reuse_ticket | bool) else 'change_opened' }}",
        "change_number": "{{ profile_ticket_map[ticket_profile.profile_name].number }}"
      }
```

- [ ] **Step 3: Insert the phase into `tasks/main.yml`**

In `roles/f5_digicert_cert_renewal/tasks/main.yml`, add between the detect phase and the request phase:

```yaml
- name: Phase 1 - Detect expiring certificates
  ansible.builtin.include_tasks: detect.yml

- name: Phase 1b - Open ServiceNow change requests
  ansible.builtin.include_tasks: tickets.yml
  when:
    - servicenow_enabled | bool
    - not dry_run | bool
    - expiring_profiles | length > 0

- name: Phase 2 - Request certificates from DigiCert
  ansible.builtin.include_tasks: request.yml
  when: renewal_required | bool
```

- [ ] **Step 4: Validate**

Run:
```bash
yamllint roles/f5_digicert_cert_renewal/tasks/tickets.yml roles/f5_digicert_cert_renewal/tasks/_open_ticket_single.yml roles/f5_digicert_cert_renewal/tasks/main.yml
ansible-lint roles/f5_digicert_cert_renewal
ansible-playbook playbooks/renew_certificates.yml --syntax-check -i inventory/hosts.yml
```
Expected: all clean (module `servicenow.itsm.change_request` resolves because the collection was installed in Task 1).

- [ ] **Step 5: Commit**

```bash
git add roles/f5_digicert_cert_renewal/tasks/tickets.yml roles/f5_digicert_cert_renewal/tasks/_open_ticket_single.yml roles/f5_digicert_cert_renewal/tasks/main.yml
git commit -m "feat: open or reuse a ServiceNow Standard change per expiring certificate"
```

---

### Task 6: Work-note helper

**Files:**
- Create: `roles/f5_digicert_cert_renewal/tasks/_add_work_note.yml`

**Interfaces:**
- Consumes: `wn_profile_name` (string), `wn_message` (string), `profile_ticket_map`, `sn_instance`.
- Produces: appends a work note to the mapped change request. No-op when ServiceNow is disabled or the profile has no mapped ticket. Never raises.

- [ ] **Step 1: Create `tasks/_add_work_note.yml`**

```yaml
---
# Append a work note to the ServiceNow change request mapped to a profile.
# Inputs: wn_profile_name, wn_message. Safe no-op when unmapped or disabled.

- name: "{{ wn_profile_name }} | Append ServiceNow work note"
  servicenow.itsm.change_request:
    instance: "{{ sn_instance }}"
    sys_id: "{{ profile_ticket_map[wn_profile_name].sys_id }}"
    other:
      work_notes: "{{ wn_message }}"
  no_log: true
  failed_when: false
  when:
    - servicenow_enabled | bool
    - not dry_run | bool
    - wn_profile_name in profile_ticket_map
```

- [ ] **Step 2: Validate**

Run:
```bash
yamllint roles/f5_digicert_cert_renewal/tasks/_add_work_note.yml
ansible-lint roles/f5_digicert_cert_renewal
```
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add roles/f5_digicert_cert_renewal/tasks/_add_work_note.yml
git commit -m "feat: add reusable ServiceNow work-note helper task"
```

---

### Task 7: Request phase — work notes + graceful per-cert failure

**Files:**
- Modify: `roles/f5_digicert_cert_renewal/tasks/_request_single.yml`

**Interfaces:**
- Consumes: `cert_profile` (loop var), `_add_work_note.yml`, `profile_ticket_map`.
- Produces: on success, unchanged downstream facts (`issued_cert_*`, `profiles_to_deploy`); on failure, appends a `failed` record to `renewal_state_records` (with sn fields) and continues.

- [ ] **Step 1: Wrap the order→download logic in a block, and add a rescue**

Restructure `roles/f5_digicert_cert_renewal/tasks/_request_single.yml` so everything from `Place DigiCert certificate order` through `Register profile for deployment` sits inside a `block:`, followed by a `rescue:`. Indent the existing tasks (from the order-placement task onward) one level under `block:`. Insert the two work-note includes shown in Step 2. Append the rescue shown in Step 3.

The block wrapper to add (immediately before the `Place DigiCert certificate order` task):

```yaml
- name: "{{ cert_profile.profile_name }} | Request and issue certificate"
  block:
```

(Everything from the existing `Place DigiCert certificate order` task through `Register profile for deployment` becomes the body of this block, indented by two spaces.)

- [ ] **Step 2: Add work-note calls inside the block**

Immediately after the existing `... | Log order placed` task (still inside the block), add:

```yaml
    - name: "{{ cert_profile.profile_name }} | Work note: order placed"
      ansible.builtin.include_tasks: _add_work_note.yml
      vars:
        wn_profile_name: "{{ cert_profile.profile_name }}"
        wn_message: "DigiCert order {{ digicert_order_result.json.id }} placed for {{ cert_profile.cert_cn }}."
      when: digicert_order_result is defined and not digicert_order_result is skipped
```

Immediately after the existing `... | Log order issued` task (still inside the block), add:

```yaml
    - name: "{{ cert_profile.profile_name }} | Work note: order issued"
      ansible.builtin.include_tasks: _add_work_note.yml
      vars:
        wn_profile_name: "{{ cert_profile.profile_name }}"
        wn_message: >-
          DigiCert order {{ active_order_id }} issued; certificate id
          {{ order_poll_result.json.certificate.id }}, new serial
          {{ order_poll_result.json.certificate.serial_number }}.
```

- [ ] **Step 3: Add the rescue at the end of the file**

Append (at the same indent level as `block:`):

```yaml
  rescue:
    - name: "{{ cert_profile.profile_name }} | Log request failure"
      ansible.builtin.debug:
        msg: >-
          {
            "timestamp": "{{ ansible_date_time.iso8601 }}",
            "device": "{{ inventory_hostname }}",
            "profile": "{{ cert_profile.profile_name }}",
            "event": "request_failed",
            "reason": "{{ ansible_failed_result.msg | default('request error') }}"
          }

    - name: "{{ cert_profile.profile_name }} | Work note: request failure"
      ansible.builtin.include_tasks: _add_work_note.yml
      vars:
        wn_profile_name: "{{ cert_profile.profile_name }}"
        wn_message: >-
          ERROR during certificate request: {{ ansible_failed_result.msg | default('request error') }}.
          Change left open for manual review.

    - name: "{{ cert_profile.profile_name }} | Record request failure in state"
      ansible.builtin.set_fact:
        renewal_state_records: >-
          {{ renewal_state_records + [{
            'profile_name': cert_profile.profile_name,
            'cert_name': cert_profile.cert_name,
            'previous_serial': cert_profile.cert_serial,
            'current_serial': null,
            'order_id': (active_order_id | default(null)),
            'servicenow_number': profile_ticket_map.get(cert_profile.profile_name, {}).get('number', 'null'),
            'servicenow_sys_id': profile_ticket_map.get(cert_profile.profile_name, {}).get('sys_id', 'null'),
            'status': 'failed',
            'last_checked_at': ansible_date_time.iso8601,
            'renewed_at': null,
            'failure_reason': (ansible_failed_result.msg | default('request error'))
          }] }}
```

- [ ] **Step 4: Validate**

Run:
```bash
yamllint roles/f5_digicert_cert_renewal/tasks/_request_single.yml
ansible-lint roles/f5_digicert_cert_renewal
ansible-playbook playbooks/renew_certificates.yml --syntax-check -i inventory/hosts.yml
```
Expected: clean; syntax-check passes (block/rescue balanced).

- [ ] **Step 5: Commit**

```bash
git add roles/f5_digicert_cert_renewal/tasks/_request_single.yml
git commit -m "feat: request-phase work notes and graceful per-cert failure handling"
```

---

### Task 8: Deploy phase — deployed work note + failure note

**Files:**
- Modify: `roles/f5_digicert_cert_renewal/tasks/_deploy_single.yml`

**Interfaces:**
- Consumes: `deploy_profile` (loop var), `_add_work_note.yml`, `profile_ticket_map`.
- Produces: a *deployed* work note on success; an *ERROR* work note and sn fields in the failed record on the existing rescue.

- [ ] **Step 1: Add the deployed work note in the success path**

In `roles/f5_digicert_cert_renewal/tasks/_deploy_single.yml`, immediately after the existing `... | Log deployment success` task (inside the `block:`), add:

```yaml
    - name: "{{ deploy_profile.profile_name }} | Work note: deployed"
      ansible.builtin.include_tasks: _add_work_note.yml
      vars:
        wn_profile_name: "{{ deploy_profile.profile_name }}"
        wn_message: >-
          Certificate {{ deploy_profile.cert_name }} and key uploaded to {{ inventory_hostname }};
          SSL profile {{ deploy_profile.profile_name }} updated to the new cert/key
          (order {{ deploy_profile.order_id }}).
```

- [ ] **Step 2: Add the failure work note in the rescue**

In the `rescue:` of `_deploy_single.yml`, after the existing `... | Log deployment failure` task, add:

```yaml
    - name: "{{ deploy_profile.profile_name }} | Work note: deployment failure"
      ansible.builtin.include_tasks: _add_work_note.yml
      vars:
        wn_profile_name: "{{ deploy_profile.profile_name }}"
        wn_message: >-
          ERROR during deployment: {{ ansible_failed_result.msg | default('deployment error') }}.
          Change left open for manual review.
```

- [ ] **Step 3: Add sn fields to the rescue failed record**

In the same rescue, in the `... | Record failure in state` task, add the two keys right after `'order_id': deploy_profile.order_id,`:

```jinja
            'order_id': deploy_profile.order_id,
            'servicenow_number': profile_ticket_map.get(deploy_profile.profile_name, {}).get('number', 'null'),
            'servicenow_sys_id': profile_ticket_map.get(deploy_profile.profile_name, {}).get('sys_id', 'null'),
```

- [ ] **Step 4: Validate**

Run:
```bash
yamllint roles/f5_digicert_cert_renewal/tasks/_deploy_single.yml
ansible-lint roles/f5_digicert_cert_renewal
```
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add roles/f5_digicert_cert_renewal/tasks/_deploy_single.yml
git commit -m "feat: deploy-phase work notes and ticket fields in failed records"
```

---

### Task 9: Verify phase — verified note, auto-close, failure handling

**Files:**
- Modify: `roles/f5_digicert_cert_renewal/tasks/_verify_single.yml`, `roles/f5_digicert_cert_renewal/tasks/verify.yml`

**Interfaces:**
- Consumes: `verify_profile` (loop var), `_add_work_note.yml`, `profile_ticket_map`, `servicenow_close_code`, `sn_instance`.
- Produces: a *verified* work note + closed change on success; an *ERROR* note + `failed` record on assertion failure; sn fields in the skipped record.

- [ ] **Step 1: Wrap verification in a block and add success work note + close**

Restructure `roles/f5_digicert_cert_renewal/tasks/_verify_single.yml` so the read/extract/assert/log/append-record tasks sit inside a `block:`. Immediately after the existing `... | Append verified record to renewal state` task (inside the block), add the verified work note and the close:

```yaml
    - name: "{{ verify_profile.profile_name }} | Work note: verified"
      ansible.builtin.include_tasks: _add_work_note.yml
      vars:
        wn_profile_name: "{{ verify_profile.profile_name }}"
        wn_message: >-
          Deployment verified on {{ inventory_hostname }}: serial {{ deployed_cert.serial_number }},
          expiry {{ deployed_cert.expiration_string }}. Renewal complete.

    - name: "{{ verify_profile.profile_name }} | Close change request as successful"
      servicenow.itsm.change_request:
        instance: "{{ sn_instance }}"
        sys_id: "{{ profile_ticket_map[verify_profile.profile_name].sys_id }}"
        state: closed
        close_code: "{{ servicenow_close_code }}"
        close_notes: >-
          Certificate renewed and verified on {{ inventory_hostname }} by AAP.
          New serial {{ deployed_cert.serial_number }}, expiry {{ deployed_cert.expiration_string }}.
      no_log: true
      failed_when: false
      when:
        - servicenow_enabled | bool
        - not dry_run | bool
        - verify_profile.profile_name in profile_ticket_map
```

Wrap the existing tasks (from `Read deployed certificate from BIG-IP` through `Append verified record to renewal state`) plus the two tasks above under:

```yaml
- name: "{{ verify_profile.profile_name }} | Verify and close"
  block:
```

- [ ] **Step 2: Add the rescue for verification failure**

Append to `_verify_single.yml` (same indent as `block:`):

```yaml
  rescue:
    - name: "{{ verify_profile.profile_name }} | Log verification failure"
      ansible.builtin.debug:
        msg: >-
          {
            "timestamp": "{{ ansible_date_time.iso8601 }}",
            "device": "{{ inventory_hostname }}",
            "profile": "{{ verify_profile.profile_name }}",
            "event": "verification_failed",
            "reason": "{{ ansible_failed_result.msg | default('verification error') }}"
          }

    - name: "{{ verify_profile.profile_name }} | Work note: verification failure"
      ansible.builtin.include_tasks: _add_work_note.yml
      vars:
        wn_profile_name: "{{ verify_profile.profile_name }}"
        wn_message: >-
          ERROR during verification: {{ ansible_failed_result.msg | default('verification error') }}.
          Change left open for manual review.

    - name: "{{ verify_profile.profile_name }} | Record verification failure in state"
      ansible.builtin.set_fact:
        renewal_state_records: >-
          {{ renewal_state_records + [{
            'profile_name': verify_profile.profile_name,
            'cert_name': verify_profile.cert_name,
            'previous_serial': verify_profile.previous_serial,
            'current_serial': null,
            'order_id': verify_profile.order_id,
            'servicenow_number': profile_ticket_map.get(verify_profile.profile_name, {}).get('number', 'null'),
            'servicenow_sys_id': profile_ticket_map.get(verify_profile.profile_name, {}).get('sys_id', 'null'),
            'status': 'failed',
            'last_checked_at': ansible_date_time.iso8601,
            'renewed_at': null,
            'failure_reason': (ansible_failed_result.msg | default('verification error'))
          }] }}
```

- [ ] **Step 3: Add sn fields to the "skipped" record builder in verify.yml**

In `roles/f5_digicert_cert_renewal/tasks/verify.yml`, in the `Build state records for profiles that were not deployed (skipped)` task, add the two keys right after `'order_id': null,`:

```jinja
              'order_id': null,
              'servicenow_number': profile_ticket_map.get(profile.profile_name, {}).get('number', 'null'),
              'servicenow_sys_id': profile_ticket_map.get(profile.profile_name, {}).get('sys_id', 'null'),
```

- [ ] **Step 4: Validate**

Run:
```bash
yamllint roles/f5_digicert_cert_renewal/tasks/_verify_single.yml roles/f5_digicert_cert_renewal/tasks/verify.yml
ansible-lint roles/f5_digicert_cert_renewal
ansible-playbook playbooks/renew_certificates.yml --syntax-check -i inventory/hosts.yml
```
Expected: clean; syntax-check passes.

- [ ] **Step 5: Commit**

```bash
git add roles/f5_digicert_cert_renewal/tasks/_verify_single.yml roles/f5_digicert_cert_renewal/tasks/verify.yml
git commit -m "feat: verify-phase work note, auto-close on success, failure handling"
```

---

### Task 10: Documentation

**Files:**
- Modify: `README.md`, `aap_config/README.md`

**Interfaces:**
- Consumes: everything above. No code produced.

- [ ] **Step 1: Add a ServiceNow section to `README.md`**

Add a section (place it after the DigiCert credential documentation) covering:

```markdown
## ServiceNow ITSM integration

When `servicenow_enabled: true` (the default), the role opens one ServiceNow
**Standard (pre-approved) change request per expiring certificate** and appends a
work note at each step of the renewal:

| Milestone | Work note |
|-----------|-----------|
| Change opened | cert CN, current serial, expiry, device/profile |
| Order placed | DigiCert order id |
| Order issued | order id, new certificate id and serial |
| Deployed | cert/key uploaded, SSL profile updated |
| Verified | deployed serial + expiry — then the change is **closed** as `successful` |
| Any failure | `ERROR …` note; the change is **left open** for manual review |

**Idempotency / reuse:** the change number and sys_id are stored in
`state/<device>.yml`. On the next scheduled run, if the certificate is still
expiring and its change is still open, the role reuses it (adding a re-detection
note) instead of opening a duplicate. After a successful renewal the certificate's
serial changes, so it is no longer detected and no new ticket is opened.

**Configuration (role defaults):**

| Variable | Default | Purpose |
|----------|---------|---------|
| `servicenow_enabled` | `true` | Master on/off switch for the integration |
| `servicenow_change_type` | `standard` | Change type (`standard` = pre-approved) |
| `servicenow_change_template` | `""` | Optional Standard Change template name/sys_id |
| `servicenow_assignment_group` | `""` | Optional assignment group |
| `servicenow_close_code` | `successful` | close_code used on success |

> Some ServiceNow instances require Standard changes to be produced from a
> Change Template. If yours does, set `servicenow_change_template` to your
> template's name or sys_id.

**Credentials:** ServiceNow auth is supplied by the custom **ServiceNow ITSM**
AAP credential type (`credential_types/servicenow.yml`), which injects
`sn_host`, `sn_username`, and `sn_password`. Attach it to the job template
alongside the BIG-IP and DigiCert credentials. In `dry_run` mode no tickets are
created — the role only logs which changes it would open.

**Collections:** `collections/requirements.yml` is the single source of truth for
Galaxy collections (used by both the execution environment and Molecule) and now
includes `servicenow.itsm`.
```

- [ ] **Step 2: Update `aap_config/README.md`**

Add the `ServiceNow ITSM` credential type, the `ServiceNow ITSM` credential, and the
`vault_sn_host` / `vault_sn_username` / `vault_sn_password` vault variables to the
existing credential/credential-type/vault documentation in that file (follow the
format already used for the DigiCert entries).

- [ ] **Step 3: Validate**

Run: `yamllint README.md aap_config/README.md 2>/dev/null || true` and visually confirm the tables render.
Expected: no blocking errors.

- [ ] **Step 4: Commit**

```bash
git add README.md aap_config/README.md
git commit -m "docs: document ServiceNow ITSM change-request integration"
```

---

### Task 11: Full integration validation

**Files:** none (validation only).

- [ ] **Step 1: Lint the whole role and playbook**

Run:
```bash
ansible-lint roles/f5_digicert_cert_renewal playbooks/renew_certificates.yml
ansible-playbook playbooks/renew_certificates.yml --syntax-check -i inventory/hosts.yml
```
Expected: no errors.

- [ ] **Step 2: Run Molecule (ServiceNow gated off) — confirm no regression**

Run:
```bash
molecule test -s default
```
Expected: converge and verify pass; the `Phase 1b - Open ServiceNow change requests` task is **skipped** (because `servicenow_enabled: false` and `dry_run: true`); no `.key` files remain in `/tmp`. If molecule/docker is unavailable, record it as skipped and rely on Steps 1 and 3.

- [ ] **Step 3: Manual verification against a ServiceNow dev instance (checklist)**

This exercises the live path that Molecule intentionally does not. Requires a ServiceNow developer instance and a BIG-IP (or the DigiCert mock + a test BIG-IP):

- [ ] Attach the ServiceNow ITSM credential to the job template; set `servicenow_enabled: true`, `dry_run: false`.
- [ ] With one certificate inside the renewal window, run the job. Confirm exactly one **Standard** change request is created with the "Change opened…" work note.
- [ ] Confirm work notes appear for *order placed*, *order issued*, *deployed*, *verified*, and that the change is **closed** with `close_code: successful`.
- [ ] Confirm `state/<device>.yml` records the change `number` and `sys_id`.
- [ ] Re-run before renewal completes (e.g., simulate a pending order): confirm the **same** change is reused (a re-detection note is added; no second change is created).
- [ ] Force a failure (e.g., invalid DigiCert key): confirm an `ERROR …` work note is added and the change is **left open**, and the run records a `failed` status.

- [ ] **Step 4: Final commit (if any doc/notes were adjusted during validation)**

```bash
git add -A
git commit -m "test: validate ServiceNow integration (lint, molecule, manual checklist)" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage:**
- Standard pre-approved change per expiring cert → Task 5.
- Work notes at each milestone → Tasks 5 (opened), 7 (placed/issued), 8 (deployed), 9 (verified).
- Auto-close on success → Task 9.
- Failure leaves ticket open + error note → Tasks 7, 8, 9.
- Reuse across runs (state-backed) → Tasks 4, 5.
- One ticket per cert instance → Task 5 (loop over `expiring_profiles`).
- `collections/requirements.yml` single source of truth + `servicenow.itsm` → Task 1.
- Custom credential type + config-as-code → Task 2.
- `sn_instance` mirrors `bigip_provider` + playbook guard → Task 3.
- State schema fields → Task 4 (+ populated in 7, 8, 9).
- dry-run creates nothing → Tasks 3, 4 (gating), 5 (main.yml gate).
- `servicenow_enabled: false` no-op → Tasks 3, 6 gating; Task 11 molecule proof.
- Docs → Task 10.
- Molecule gated off → Tasks 3, 11.

**Placeholder scan:** none — every code step contains full content. `servicenow_change_template`/`servicenow_assignment_group` empty strings are intended config defaults (resolved via `or omit`), not placeholders.

**Type/name consistency:** `profile_ticket_map` keyed by `profile_name` with `{number, sys_id}` used identically in Tasks 4–9; loop var `ticket_profile` (tickets), `cert_profile` (request), `deploy_profile` (deploy), `verify_profile` (verify) match existing files; `sn_instance` keys (host/username/password) consistent; helper inputs `wn_profile_name`/`wn_message` consistent across Tasks 6–9; `new_cr.record.number`/`new_cr.record.sys_id` and `prior_cr.records[0].sys_id`/`.state` consistent.

**Known validation caveat (honest):** the live `servicenow.itsm.change_request` work-note mechanism uses `other: { work_notes: ... }`. If a customer's collection version rejects `other.work_notes`, the fallback is the `servicenow.itsm.api` module (`action: patch`, `resource: change_request`, `data: { work_notes: ... }`). This is called out in Task 11's manual checklist because Molecule does not exercise the live ServiceNow path.
