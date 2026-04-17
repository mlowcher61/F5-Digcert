# Feature Specification: Automated Certificate Renewal — F5 BIG-IP via DigiCert

**Feature Branch**: `001-f5-cert-renewal`
**Created**: 2026-04-17
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Certificates Renewed Before Expiry (Priority: P1)

A network engineer runs the renewal automation against one or more F5 BIG-IP devices.
The system detects certificates within a configurable expiry window (default: 30 days),
requests replacement certificates from DigiCert, deploys them to the BIG-IP SSL profiles,
and confirms the new certificates are active — all without manual intervention.

**Why this priority**: Expired certificates cause immediate, customer-facing outages.
Automated, reliable renewal before expiry is the primary value of this feature.

**Independent Test**: Run the automation against a BIG-IP device that has a certificate
expiring within 30 days. Verify the certificate serial number on the device changes and
the new expiry date is at least 1 year in the future.

**Acceptance Scenarios**:

1. **Given** a BIG-IP device has a certificate expiring in 15 days,
   **When** the renewal job runs,
   **Then** DigiCert issues a new certificate, it is deployed to the matching SSL profile,
   and the previous certificate is archived.

2. **Given** a BIG-IP device has a certificate expiring in 45 days (outside the 30-day
   window), **When** the renewal job runs, **Then** no renewal action is taken and the
   job reports the certificate as current.

3. **Given** the renewal job has already renewed a certificate in the current run,
   **When** the job is re-run (idempotent retry), **Then** no duplicate certificate
   request is submitted to DigiCert and the device state is unchanged.

---

### User Story 2 - Renewal Failure Surfaced and Logged (Priority: P2)

When any step of the renewal process fails (DigiCert API unreachable, BIG-IP
authentication error, certificate validation failure), the system surfaces a clear,
actionable error, logs a structured failure event, and leaves the existing certificate
untouched on the device.

**Why this priority**: Silent failures are worse than outages — operators must know when
automation has not protected them.

**Independent Test**: Simulate a DigiCert API failure (invalid API key). Verify the
existing certificate remains on the BIG-IP, a structured error log entry is emitted, and
the process exits with a non-zero status.

**Acceptance Scenarios**:

1. **Given** the DigiCert API key is invalid, **When** the renewal job runs,
   **Then** no certificate changes are made on the BIG-IP, an error is logged with
   timestamp and reason, and the job exits with a failure status.

2. **Given** BIG-IP credentials are incorrect, **When** the renewal job attempts to
   deploy a certificate, **Then** the deployment is aborted, the error is logged, and
   the previously-issued DigiCert certificate order is flagged for manual review.

---

### User Story 3 - Operator Runs Dry-Run to Preview Actions (Priority: P3)

An operator can invoke the automation in a read-only "dry-run" mode that reports which
certificates would be renewed without making any changes to DigiCert or BIG-IP.

**Why this priority**: Operators need confidence before running automation in production.
Dry-run reduces risk of unintended changes.

**Independent Test**: Run the automation in dry-run mode against a BIG-IP with expiring
certificates. Verify no DigiCert orders are placed, no BIG-IP configuration changes
occur, and the output lists the certificates that would be renewed.

**Acceptance Scenarios**:

1. **Given** dry-run mode is enabled, **When** the job identifies certificates due for
   renewal, **Then** it prints a preview report of affected certificates and exits
   without contacting the DigiCert ordering API or modifying the BIG-IP.

---

### Edge Cases

- What happens when a BIG-IP SSL profile references the same certificate used by
  multiple virtual servers? The renewed certificate MUST be deployed once and all
  referencing profiles updated atomically.
- What happens when DigiCert issues the certificate but BIG-IP deployment fails? The
  issued certificate MUST be retained and the failure logged so the certificate can be
  deployed in a subsequent run rather than ordering a duplicate.
- What happens when the BIG-IP is unreachable during deployment? The job MUST log the
  failure, skip that device, and continue processing remaining devices.
- What happens when a certificate's SANs on the BIG-IP do not match what can be
  requested from DigiCert? The job MUST halt renewal for that certificate and alert
  the operator.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST detect all SSL certificates on managed BIG-IP devices that
  expire within a configurable threshold (default: 30 days).
- **FR-002**: The system MUST request a replacement certificate from DigiCert for each
  expiring certificate, preserving the same Common Name and Subject Alternative Names.
- **FR-003**: The system MUST deploy the newly issued certificate and private key to the
  corresponding BIG-IP SSL profile upon successful issuance.
- **FR-004**: The system MUST verify the deployed certificate is active and matches the
  expected serial number before marking the renewal complete.
- **FR-005**: All certificate operations MUST be idempotent — re-running the job on an
  already-renewed certificate MUST produce no changes and no duplicate DigiCert orders.
- **FR-006**: The system MUST emit a structured log entry for every lifecycle event:
  detection, order placed, certificate issued, deployment started, deployment confirmed,
  and any failure.
- **FR-007**: The system MUST support a dry-run mode that reports planned actions without
  executing them.
- **FR-008**: Private keys MUST never be written to persistent storage unencrypted and
  MUST NOT appear in logs.
- **FR-009**: The system MUST operate against multiple BIG-IP devices in a single
  invocation, processing each independently so failure on one device does not block
  others.
- **FR-010**: The expiry threshold (days before renewal) MUST be configurable per
  invocation without code changes.

### Key Entities

- **Certificate**: An SSL/TLS certificate bound to one or more BIG-IP SSL profiles.
  Key attributes: CN, SANs, serial number, expiry date, issuing CA, associated BIG-IP
  device and profile name.
- **BIG-IP Device**: A managed F5 load balancer. Key attributes: hostname/IP, management
  credentials reference, list of SSL profiles.
- **DigiCert Order**: A certificate issuance request sent to DigiCert. Key attributes:
  order ID, requested CN/SANs, status, issued certificate serial number.
- **Renewal Record**: A log of each renewal attempt. Key attributes: timestamp, device,
  certificate CN, outcome (success/failure/skipped), DigiCert order ID.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of certificates within the configured expiry window are renewed
  without operator intervention during a scheduled run.
- **SC-002**: A renewed certificate is active on the BIG-IP within 10 minutes of
  DigiCert issuing it.
- **SC-003**: A failed renewal on one BIG-IP device does not prevent renewal on other
  devices in the same run — overall job success rate reflects per-device outcomes.
- **SC-004**: Every renewal attempt (success or failure) produces a structured log entry
  that can be queried by device, certificate CN, and outcome within an operator's
  existing log aggregation system.
- **SC-005**: Dry-run mode produces a preview report in under 60 seconds for an
  inventory of up to 20 BIG-IP devices with up to 50 certificates each.
- **SC-006**: Re-running the job against already-renewed certificates results in zero
  new DigiCert orders and zero BIG-IP configuration changes.

## Assumptions

- BIG-IP devices are reachable over the network from the host running the automation,
  using credentials stored in a secrets manager or encrypted variable store.
- DigiCert organization validation (OV) or domain validation (DV) is already completed;
  this automation handles only the certificate ordering and deployment lifecycle, not
  initial CA enrollment.
- The BIG-IP management API (iControl REST) is enabled on all target devices.
- Certificate private key generation occurs on the automation host or the BIG-IP itself;
  the exact location is determined during planning.
- Multi-device runs are sequential by default (not parallel) unless explicitly configured
  otherwise, to limit blast radius of misconfiguration.
- The automation is invoked on a schedule (e.g., daily cron) by an existing orchestration
  platform; this feature does not include scheduling infrastructure.
- The `community.crypto` collection provides cryptographic primitives (CSR generation,
  certificate parsing) used during the renewal workflow.
