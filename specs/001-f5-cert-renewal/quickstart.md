# Quickstart: Automated Certificate Renewal — F5 BIG-IP via DigiCert

**Branch**: `001-f5-cert-renewal` | **Date**: 2026-04-17

---

## Prerequisites

- Ansible ≥ 2.14 installed on the control node
- Collections installed:
  ```bash
  ansible-galaxy collection install community.crypto f5networks.f5_modules
  ```
- Python packages on the control node:
  ```bash
  pip install pyOpenSSL cryptography
  ```
- Network access from the control node to each BIG-IP management interface (port 443)
- Network access from the control node to DigiCert API (`https://www.digicert.com`)
- DigiCert CertCentral API key and Organization ID
- BIG-IP admin credentials

---

## Setup

### 1. Configure credentials

Export credentials as environment variables (or use ansible-vault — see below):

```bash
export BIGIP_USERNAME=admin
export BIGIP_PASSWORD=<bigip-password>
export DIGICERT_API_KEY=<digicert-api-key>
export DIGICERT_ORG_ID=<digicert-org-id>
```

### 2. Declare your BIG-IP devices

Edit `inventory/hosts.yml`:

```yaml
all:
  children:
    bigip_devices:
      hosts:
        bigip-prod-01.example.com:
          ansible_host: 192.168.1.10
          ansible_connection: local
```

### 3. Declare SSL profiles per device

Create `inventory/host_vars/bigip-prod-01.example.com.yml`:

```yaml
bigip_ssl_profiles:
  - profile_name: clientssl-myapp
    cert_name: myapp-cert
    key_name: myapp-key
```

---

## Running the Automation

### Dry-run (preview only — no changes made)

```bash
ansible-playbook playbooks/renew_certificates.yml \
  -i inventory/hosts.yml \
  -e dry_run=true
```

Expected output:
```
TASK [f5_digicert_cert_renewal : Report expiring certificates]
ok: [bigip-prod-01.example.com] =>
  msg: "DRY RUN: Would renew myapp-cert (expires 2026-05-01, 14 days remaining)"
```

### Standard run

```bash
ansible-playbook playbooks/renew_certificates.yml -i inventory/hosts.yml
```

### Single device

```bash
ansible-playbook playbooks/renew_certificates.yml \
  -i inventory/hosts.yml \
  --limit bigip-prod-01.example.com
```

### Custom renewal threshold (45 days)

```bash
ansible-playbook playbooks/renew_certificates.yml \
  -i inventory/hosts.yml \
  -e renewal_threshold_days=45
```

---

## Verifying a Renewal

After a run, check the state file:

```bash
cat state/bigip-prod-01.example.com.yml
```

Confirm on the BIG-IP directly:

```bash
# Via tmsh (SSH to BIG-IP)
tmsh list sys file ssl-cert myapp-cert
```

Expected: `expiration-date` is approximately 1 year in the future.

---

## Using ansible-vault for credentials

```bash
# Create encrypted vault file
ansible-vault create inventory/group_vars/vault.yml
# Add:
# vault_bigip_password: <password>
# vault_digicert_api_key: <key>
# vault_digicert_org_id: <id>

# Reference in group_vars/bigip_devices.yml:
# bigip_password: "{{ vault_bigip_password }}"
# digicert_api_key: "{{ vault_digicert_api_key }}"

# Run with vault
ansible-playbook playbooks/renew_certificates.yml \
  -i inventory/hosts.yml \
  --vault-password-file ~/.vault_pass
```

---

## Scheduling (cron example)

```cron
# Run daily at 02:00 UTC
0 2 * * * cd /opt/f5-digicert-cert-renewal && \
  ansible-playbook playbooks/renew_certificates.yml \
  -i inventory/hosts.yml \
  --vault-password-file ~/.vault_pass \
  >> /var/log/cert-renewal.log 2>&1
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `401 Unauthorized` from DigiCert | Verify `DIGICERT_API_KEY` is set and valid |
| `401 Unauthorized` from BIG-IP | Verify `BIGIP_USERNAME`/`BIGIP_PASSWORD` |
| `Profile not found` on BIG-IP | Confirm `profile_name` exists in the correct partition |
| Order stuck in `pending` | Check DigiCert portal for validation action required |
| `current_serial == previous_serial` after run | Verify deployment task succeeded; check BIG-IP logs |

---

## State Directory

The automation writes one YAML file per device to `state/`:

```
state/
├── bigip-prod-01.example.com.yml
└── bigip-prod-02.example.com.yml
```

These files are safe to inspect and can be deleted to force a full re-evaluation on
the next run (no data is lost — the automation re-reads live state from BIG-IP).
