# Contract: F5 BIG-IP iControl REST API

**Type**: External API contract — documents F5 BIG-IP management API calls used by the
automation, implemented via `f5networks.f5_modules` Ansible modules and direct
`uri` calls.
**Base URL**: `https://<bigip_hostname>:<bigip_port>/mgmt/`
**Auth**: Basic auth or token (handled by f5_modules).

---

## Certificate Detection (Read)

**Module**: `ansible.builtin.uri` → `GET /mgmt/tm/sys/file/ssl-cert`

**Purpose**: List all SSL certificate objects in a partition and their expiry dates.

**Response (used fields)**:

```json
{
  "items": [
    {
      "name": "myapp-cert",
      "partition": "Common",
      "expirationDate": "Apr 17 00:00:00 2026 GMT",
      "expirationString": "Apr 17 00:00:00 2026 GMT",
      "serialNumber": "0A1B2C3D4E5F",
      "subject": "CN=myapp.example.com"
    }
  ]
}
```

**Automation action**: Parse `expirationDate` and compare to today + `renewal_threshold_days`.
Certs within threshold are marked `EXPIRING` and queued for renewal.

---

## Upload Certificate (Write)

**Module**: `f5networks.f5_modules.bigip_ssl_certificate`

**Purpose**: Upload a newly issued certificate PEM to a BIG-IP certificate object.

**Ansible task contract**:

```yaml
- name: Upload renewed certificate
  f5networks.f5_modules.bigip_ssl_certificate:
    name: "{{ profile.cert_name }}"
    content: "{{ renewed_cert_pem }}"
    partition: "{{ profile.partition | default(bigip_partition) }}"
    state: present
    provider: "{{ bigip_provider }}"
  no_log: false   # cert is not sensitive; key upload uses no_log: true
```

**Success**: Module returns `changed: true` on first upload; `changed: false` on
subsequent runs with identical content (idempotent).

---

## Upload Private Key (Write)

**Module**: `f5networks.f5_modules.bigip_ssl_key`

**Purpose**: Upload the private key paired with the renewed certificate.

**Ansible task contract**:

```yaml
- name: Upload renewed private key
  f5networks.f5_modules.bigip_ssl_key:
    name: "{{ profile.key_name }}"
    content: "{{ renewed_key_pem }}"
    partition: "{{ profile.partition | default(bigip_partition) }}"
    state: present
    provider: "{{ bigip_provider }}"
  no_log: true    # REQUIRED — private key must never appear in logs
```

---

## Update SSL Profile (Write)

**Module**: `f5networks.f5_modules.bigip_profile_client_ssl`

**Purpose**: Associate the SSL profile with the newly uploaded certificate and key objects.

**Ansible task contract**:

```yaml
- name: Update SSL profile with renewed cert
  f5networks.f5_modules.bigip_profile_client_ssl:
    name: "{{ profile.profile_name }}"
    cert_key_chain:
      - cert: "{{ profile.cert_name }}"
        key: "{{ profile.key_name }}"
    partition: "{{ profile.partition | default(bigip_partition) }}"
    state: present
    provider: "{{ bigip_provider }}"
```

---

## Verify Deployed Certificate (Read)

**Module**: `ansible.builtin.uri` →
`GET /mgmt/tm/sys/file/ssl-cert/~<partition>~<cert_name>`

**Purpose**: Read back the deployed certificate serial number to confirm deployment.

**Response (used fields)**:

```json
{
  "serialNumber": "1A2B3C4D5E6F",
  "expirationDate": "Apr 17 00:00:00 2027 GMT"
}
```

**Verification contract**:
- `serialNumber` MUST match the serial from the DigiCert-issued certificate.
- `expirationDate` MUST be in the future (at least `digicert_validity_years` × 365 days).
- If either check fails → log error, set record status to `failed`.

---

## Provider Configuration

All `f5networks.f5_modules` tasks reference a shared `bigip_provider` variable:

```yaml
bigip_provider:
  server: "{{ inventory_hostname }}"
  server_port: "{{ bigip_port | default(443) }}"
  user: "{{ bigip_username }}"
  password: "{{ bigip_password }}"
  validate_certs: "{{ bigip_validate_certs | default(true) }}"
  no_f5_teem: true
```

**Security**: `bigip_provider` is populated at runtime from vault/env variables.
It MUST NOT be logged (tasks using it set `no_log: true` where the password could appear
in diff output).

---

## Error Classification

| Error type | Module behavior | Automation action |
|------------|----------------|------------------|
| Auth failure (401/403) | Module raises fatal error | Log, skip device, continue to next |
| Network timeout | Module raises connection error | Log, skip device, continue to next |
| Resource not found (404) | Module raises error | Log, skip profile, continue to next |
| BIG-IP internal error (5xx) | Module raises error | Log, skip device, continue to next |

**Key invariant**: Any BIG-IP API error MUST leave the existing certificate and key
objects untouched. The `bigip_ssl_certificate` module is idempotent — a failed upload
does not partially overwrite the existing cert object.
