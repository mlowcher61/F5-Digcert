# Research: Automated Certificate Renewal — F5 BIG-IP via DigiCert

**Phase 0 output** | **Branch**: `001-f5-cert-renewal` | **Date**: 2026-04-17

---

## Decision 1: Automation Runtime

**Decision**: Ansible role + playbook

**Rationale**: The feature description explicitly names the `community.crypto` Ansible
collection. Ansible is the natural runtime for infrastructure-level certificate lifecycle
automation: it provides idempotency primitives, a structured inventory model for
multi-device targeting, native integration with secrets managers (Vault, environment
lookups), and Molecule for testing. A standalone Python script would duplicate all of
this.

**Alternatives considered**:
- Standalone Python script: rejected — requires reimplementing idempotency, inventory
  handling, and secrets integration that Ansible provides for free.
- Terraform: rejected — certificate lifecycle (renewal, deployment) is operational, not
  infrastructure provisioning. Terraform state model is poorly suited to frequent
  renewal cycles.

---

## Decision 2: DigiCert Interface

**Decision**: DigiCert Services REST API (CertCentral REST API)

**Rationale**: The DigiCert CertCentral REST API (`https://www.digicert.com/services/v2/`)
provides full lifecycle control — order, status polling, certificate download, revocation
— for OV and DV certificates. It supports automation without the CA/RA enrollment
complexity of ACME. Given the spec assumption that OV/DV validation is pre-completed,
the REST API is the appropriate interface.

**Key endpoints used**:
- `POST /order/certificate/ssl` — place certificate order
- `GET /order/certificate/{order_id}` — poll order status
- `GET /certificate/{cert_id}/download/format/pem_all` — download issued certificate
- `POST /certificate/{cert_id}/revoke` — revoke certificate (not in scope for v1)

**Alternatives considered**:
- ACME (RFC 8555): rejected — requires domain validation infrastructure (HTTP-01 or
  DNS-01 challenge responders) that the spec does not include in scope. OV certificates
  cannot be issued via ACME.
- DigiCert ACME with EAB: rejected — same challenge-responder requirement.

---

## Decision 3: Private Key Generation Location

**Decision**: Generate private keys on the Ansible control node using
`community.crypto.openssl_privatekey`, then transfer key + certificate to BIG-IP via
the F5 management API.

**Rationale**: The `community.crypto` collection's `openssl_privatekey` and
`openssl_csr` modules run on the control node (or a designated target). F5 BIG-IP does
support CSR generation via iControl REST, but the resulting key material remains on
the device and is not exported — making it impossible to submit the CSR to DigiCert
externally in a standard way. Generating on the control node, then uploading the signed
certificate and key together via the BIG-IP file upload API, is the supported and
documented F5 automation pattern.

**Security controls**:
- Private keys stored as Ansible `no_log` variables in memory; never written to disk on
  the control node in plaintext.
- Key files uploaded to BIG-IP over TLS using iControl REST file upload endpoint.
- Vault or encrypted `ansible-vault` used for credentials; raw secrets never in
  playbook variables.

**Alternatives considered**:
- Generate CSR on BIG-IP device: rejected — BIG-IP does not export the private key,
  making external CA signing impossible without manual steps.
- HashiCorp Vault PKI backend: rejected — out of scope; DigiCert is the specified CA.

---

## Decision 4: F5 BIG-IP API Approach

**Decision**: Hybrid approach — `f5networks.f5_modules` Ansible collection for
certificate and SSL profile management; `ansible.builtin.uri` for file upload operations
not covered by f5_modules.

**Key modules**:
- `f5networks.f5_modules.bigip_ssl_certificate` — manage certificate objects on BIG-IP
- `f5networks.f5_modules.bigip_ssl_key` — manage private key objects on BIG-IP
- `f5networks.f5_modules.bigip_profile_client_ssl` — update SSL profile to reference
  new certificate
- `ansible.builtin.uri` — iControl REST calls for certificate inventory and verification

**Rationale**: `f5networks.f5_modules` is the official Ansible collection maintained by
F5/NGINX for BIG-IP automation. It wraps the iControl REST API with Ansible-idiomatic
modules that handle authentication, error handling, and idempotency. Mixing in `uri`
calls for inventory checks (listing expiring certs) where no module exists is standard
practice.

**Alternatives considered**:
- Pure `uri`/iControl REST calls: rejected — higher maintenance burden, no built-in
  idempotency, no Ansible diff mode support.
- BIG-IQ for cert management: rejected — requires separate BIG-IQ infrastructure; the
  spec targets direct BIG-IP management.

---

## Decision 5: State Persistence & Idempotency

**Decision**: YAML state file per BIG-IP device at `state/<device_hostname>.yml` on the
control node, tracking: last renewal timestamp, current certificate serial number per
profile, and any pending DigiCert order IDs.

**Rationale**: Ansible's built-in fact cache does not persist across control node
restarts by default and is not queryable as structured data. A YAML state file provides
a simple, auditable, human-readable record that enables:
- Idempotency: skip renewal if state shows cert was already renewed this cycle
- Recovery: if BIG-IP deployment fails after DigiCert issues the cert, the order ID is
  preserved so the cert can be deployed without re-ordering
- Audit: operators can inspect state files to understand current renewal status

**Alternatives considered**:
- Ansible fact cache (JSON): rejected — not persistent across control node restarts.
- Database (SQLite/PostgreSQL): rejected — over-engineered for this scope; YAML file
  is sufficient and avoids an additional dependency.

---

## Decision 6: Testing Approach

**Decision**: Molecule with Docker driver for Ansible role unit and integration tests.
DigiCert API interactions tested with a mock HTTP server (pytest + responses library
via a custom Molecule verify step). F5 BIG-IP interactions tested against the F5 BIG-IP
trial/lab environment or using recorded API responses.

**Test levels**:
- **Unit**: Molecule + pytest-testinfra to verify role tasks produce correct file and
  config state on a test target container.
- **Integration**: Molecule scenario against a mock DigiCert HTTP server; verify CSR
  generation, order placement, and state file updates.
- **Contract tests**: Verify the Ansible inventory schema and playbook variable contract
  match the documented interface (schema validation via `jsonschema`).

**Rationale**: Molecule is the standard Ansible role testing framework. Using recorded
API responses (VCR cassettes or a mock server) for external APIs is the appropriate
substitute when a sandbox DigiCert account is not available in CI.

---

## NEEDS CLARIFICATION — All Resolved

| Question | Resolution |
|----------|-----------|
| Automation runtime? | Ansible role + playbook |
| DigiCert API style? | CertCentral REST API |
| Key generation location? | Ansible control node (community.crypto) |
| F5 API approach? | f5networks.f5_modules + uri |
| State persistence? | YAML state files per device |
| Testing framework? | Molecule + pytest-testinfra |
