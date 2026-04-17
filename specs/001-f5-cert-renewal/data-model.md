# Data Model: Automated Certificate Renewal — F5 BIG-IP via DigiCert

**Phase 1 output** | **Branch**: `001-f5-cert-renewal` | **Date**: 2026-04-17

---

## Entity: BIG-IP Device

Represents a managed F5 BIG-IP appliance or VE targeted for certificate operations.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `hostname` | string | ✅ | FQDN or IP of BIG-IP management interface |
| `port` | integer | no | Management port; default 443 |
| `username` | string | ✅ | Admin credential reference (vault path or env var) |
| `password` | string | ✅ | Credential reference — NEVER plaintext in inventory |
| `partition` | string | no | BIG-IP partition; default `Common` |
| `validate_certs` | boolean | no | Verify management TLS; default `true` |
| `ssl_profiles` | list\<SSLProfile\> | ✅ | SSL profiles to manage on this device |

**Constraints**:
- `hostname` must be reachable from the Ansible control node on `port` before any
  operation is attempted.
- `password` MUST be sourced from `ansible-vault`, HashiCorp Vault lookup, or
  environment variable. Plaintext passwords in inventory files are a constitution
  violation (Principle II).

---

## Entity: SSL Profile

A BIG-IP client SSL profile that references a certificate and key pair.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `profile_name` | string | ✅ | BIG-IP SSL profile name (e.g., `clientssl-myapp`) |
| `cert_name` | string | ✅ | BIG-IP certificate object name |
| `key_name` | string | ✅ | BIG-IP key object name |
| `partition` | string | no | Overrides device-level partition |
| `cert_cn` | string | derived | Common Name — read from live cert at detection time |
| `cert_sans` | list\<string\> | derived | SANs — read from live cert at detection time |
| `cert_expiry` | datetime | derived | Expiry date — read from live cert at detection time |
| `cert_serial` | string | derived | Serial number — used for idempotency checks |

**State transitions**:
```
CURRENT → EXPIRING (when days_to_expiry ≤ renewal_threshold)
EXPIRING → RENEWING (renewal job starts)
RENEWING → RENEWED (certificate deployed and verified on BIG-IP)
RENEWING → FAILED (any step fails; existing cert preserved)
RENEWED → CURRENT (next detection cycle confirms new cert is valid)
```

---

## Entity: DigiCert Order

A certificate issuance request submitted to DigiCert CertCentral.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `order_id` | string | ✅ | DigiCert order ID (returned at order placement) |
| `cert_id` | string | conditional | DigiCert certificate ID (available after issuance) |
| `requested_cn` | string | ✅ | Common Name submitted in CSR |
| `requested_sans` | list\<string\> | no | SANs submitted in CSR |
| `status` | enum | ✅ | `pending`, `issued`, `rejected`, `revoked` |
| `placed_at` | datetime | ✅ | Timestamp of order placement |
| `issued_at` | datetime | conditional | Timestamp of certificate issuance |
| `expiry` | datetime | derived | Certificate expiry from issued cert |
| `device_hostname` | string | ✅ | BIG-IP device this order is for |
| `profile_name` | string | ✅ | SSL profile this order is for |

**Constraints**:
- One `DigiCertOrder` per `(device_hostname, profile_name)` per renewal cycle.
- If an order already exists in `pending` or `issued` state for a profile, no new order
  MUST be placed (idempotency — Principle III).

---

## Entity: Renewal Record

Persisted state file entry for a single certificate renewal attempt. Written to
`state/<device_hostname>.yml`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `profile_name` | string | ✅ | BIG-IP SSL profile name |
| `previous_serial` | string | ✅ | Serial of cert before renewal |
| `current_serial` | string | conditional | Serial of deployed cert (set after verification) |
| `order_id` | string | conditional | DigiCert order ID (if order was placed) |
| `status` | enum | ✅ | `skipped`, `pending`, `deployed`, `verified`, `failed` |
| `last_checked_at` | datetime | ✅ | Timestamp of last detection check |
| `renewed_at` | datetime | conditional | Timestamp of successful deployment |
| `failure_reason` | string | conditional | Human-readable error if `status == failed` |

**Validation rules**:
- `current_serial != previous_serial` MUST be true after a successful renewal.
- `status == verified` requires `current_serial` to be populated and match the serial
  read back from the live BIG-IP profile.

---

## Entity: Playbook Configuration

The runtime configuration passed to the Ansible playbook per invocation.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `renewal_threshold_days` | integer | 30 | Renew certs expiring within N days |
| `dry_run` | boolean | false | Preview mode — no changes made |
| `digicert_api_key` | string | — | DigiCert API key (vault/env only) |
| `digicert_org_id` | integer | — | DigiCert organization ID |
| `digicert_validity_years` | integer | 1 | Certificate validity period |
| `key_size` | integer | 4096 | RSA key size in bits |
| `state_dir` | string | `state/` | Directory for per-device state YAML files |
| `max_retries` | integer | 3 | Max DigiCert API retries on transient failure |
| `retry_delay_seconds` | integer | 10 | Base delay for exponential backoff |
| `sequential_devices` | boolean | true | Process devices one at a time |

---

## Relationships

```
Playbook Configuration
  └─ targets → BIG-IP Device [1..*]
                 └─ manages → SSL Profile [1..*]
                               ├─ triggers → DigiCert Order [0..1 per renewal cycle]
                               └─ records → Renewal Record [1 per run]
```

---

## State File Schema (`state/<hostname>.yml`)

```yaml
device: bigip-prod-01.example.com
last_run: "2026-04-17T08:00:00Z"
profiles:
  - profile_name: clientssl-myapp
    cert_name: myapp-cert
    previous_serial: "0A1B2C3D4E5F"
    current_serial: "1A2B3C4D5E6F"
    order_id: "dg-order-12345"
    status: verified
    last_checked_at: "2026-04-17T08:00:00Z"
    renewed_at: "2026-04-17T08:05:12Z"
  - profile_name: clientssl-api
    cert_name: api-cert
    previous_serial: "AABBCCDDEEFF"
    current_serial: null
    order_id: null
    status: skipped
    last_checked_at: "2026-04-17T08:00:00Z"
    renewed_at: null
```
