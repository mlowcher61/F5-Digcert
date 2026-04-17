# Contract: Ansible Inventory & Variable Schema

**Type**: Configuration interface — defines how operators declare BIG-IP devices and
configure the renewal automation.

---

## Inventory Structure

### `inventory/hosts.yml`

```yaml
all:
  children:
    bigip_devices:
      hosts:
        bigip-prod-01.example.com:
          ansible_host: 192.168.1.10
          ansible_connection: local        # iControl REST calls run locally
        bigip-prod-02.example.com:
          ansible_host: 192.168.1.11
          ansible_connection: local
```

**Rules**:
- `ansible_connection: local` is REQUIRED — F5 modules communicate via REST, not SSH.
- Hostnames MUST match the BIG-IP device hostname used in state file naming.

---

## Group Variables (`inventory/group_vars/bigip_devices.yml`)

```yaml
# BIG-IP credentials — MUST reference vault or environment, never plaintext
bigip_username: "{{ lookup('env', 'BIGIP_USERNAME') }}"
bigip_password: "{{ lookup('env', 'BIGIP_PASSWORD') }}"
bigip_port: 443
bigip_validate_certs: true
bigip_partition: Common

# DigiCert credentials — MUST reference vault or environment
digicert_api_key: "{{ lookup('env', 'DIGICERT_API_KEY') }}"
digicert_org_id: "{{ lookup('env', 'DIGICERT_ORG_ID') }}"

# Renewal configuration
renewal_threshold_days: 30
digicert_validity_years: 1
key_size: 4096
state_dir: "{{ playbook_dir }}/state"
max_retries: 3
retry_delay_seconds: 10
sequential_devices: true
dry_run: false
```

---

## Host Variables (`inventory/host_vars/<hostname>.yml`)

```yaml
# Per-device SSL profile declarations
bigip_ssl_profiles:
  - profile_name: clientssl-myapp
    cert_name: myapp-cert
    key_name: myapp-key
    partition: Common          # optional; inherits group default

  - profile_name: clientssl-api
    cert_name: api-cert
    key_name: api-key
```

**Schema constraints**:

| Field | Type | Required | Validation |
|-------|------|----------|-----------|
| `profile_name` | string | ✅ | Must exist on the BIG-IP before the playbook runs |
| `cert_name` | string | ✅ | BIG-IP certificate object name |
| `key_name` | string | ✅ | BIG-IP key object name |
| `partition` | string | no | Default: inherits `bigip_partition` |

---

## Playbook Invocation Interface

### Standard run

```bash
ansible-playbook playbooks/renew_certificates.yml -i inventory/hosts.yml
```

### Dry-run

```bash
ansible-playbook playbooks/renew_certificates.yml -i inventory/hosts.yml \
  -e dry_run=true
```

### Override renewal threshold

```bash
ansible-playbook playbooks/renew_certificates.yml -i inventory/hosts.yml \
  -e renewal_threshold_days=45
```

### Target a single device

```bash
ansible-playbook playbooks/renew_certificates.yml -i inventory/hosts.yml \
  --limit bigip-prod-01.example.com
```

---

## Environment Variable Contract

| Variable | Required | Description |
|----------|----------|-------------|
| `BIGIP_USERNAME` | ✅ | BIG-IP admin username |
| `BIGIP_PASSWORD` | ✅ | BIG-IP admin password |
| `DIGICERT_API_KEY` | ✅ | DigiCert CertCentral API key |
| `DIGICERT_ORG_ID` | ✅ | DigiCert organization ID |

**Alternative**: All of the above may be stored in an `ansible-vault` encrypted file
and passed via `--vault-password-file`.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All devices processed; all renewals succeeded or skipped |
| 1 | One or more devices failed renewal; partial success possible |
| 2 | Configuration error (missing required variable, unreachable device on pre-check) |
