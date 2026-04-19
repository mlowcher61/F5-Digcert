# F5 DigiCert Certificate Renewal Automation

Automated SSL certificate renewal for F5 BIG-IP devices via DigiCert CertCentral, designed for Ansible Automation Platform (AAP).

See [specs/001-f5-cert-renewal/quickstart.md](specs/001-f5-cert-renewal/quickstart.md) for full usage details.

---

## AAP Setup

### 1. Execution Environment

Build and publish the execution environment using the provided `execution-environment.yml`:

```bash
ansible-builder build -f execution-environment.yml -t your-registry/f5-digicert-ee:latest
ansible-builder push your-registry/f5-digicert-ee:latest
```

Assign this EE to the job template in AAP.

### 2. Credential Types

Import both custom credential types under **Credentials > Credential Types > Add**
using the definitions in `credential_types/`:

| File | Purpose |
|------|---------|
| `credential_types/bigip.yml` | Injects `bigip_username`, `bigip_password` |
| `credential_types/digicert.yml` | Injects `digicert_api_key`, `digicert_org_id` |

### 3. Credentials

Create one credential of each type per environment and attach both to the job template.

### 4. Project

Add this repository as an AAP Project (SCM type: Git).

### 5. Inventory

Create an AAP Inventory with a `bigip_devices` group. For each BIG-IP host, set
`ansible_connection: local` in the host variables and declare `bigip_ssl_profiles`
per host (see `inventory/host_vars/bigip-example.yml` for the schema).

### 6. Job Template

| Setting | Value |
|---------|-------|
| Playbook | `playbooks/renew_certificates.yml` |
| Execution Environment | your built EE |
| Credentials | F5 BIG-IP + DigiCert CertCentral |
| Extra vars | `dry_run: true` for preview runs |

#### State persistence

The role writes per-device state files to `state_dir` (default: `{{ playbook_dir }}/state`).
In AAP this directory must persist across job runs. Configure a persistent volume mount
or override `state_dir` to a stable path via job template extra vars:

```yaml
state_dir: /mnt/persistent/f5-cert-renewal/state
```

### 7. Schedule

Add a schedule to the job template (e.g., daily at 02:00 UTC) to run renewals automatically.

---

## Configurable variables

| Variable | Default | Description |
|----------|---------|-------------|
| `renewal_threshold_days` | `30` | Renew certs expiring within N days |
| `dry_run` | `false` | Preview mode — no changes made |
| `digicert_validity_years` | `1` | Requested certificate validity |
| `key_size` | `4096` | RSA key size in bits |
| `max_retries` | `3` | DigiCert API retry attempts |
| `sequential_devices` | `true` | Process one BIG-IP at a time |
| `state_dir` | `{{ playbook_dir }}/state` | Path for per-device state files |

---

## Collection dependencies

See `requirements.yml` for the full collection list. These are bundled in the execution environment — do not install them locally.
