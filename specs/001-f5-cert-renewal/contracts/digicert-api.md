# Contract: DigiCert CertCentral REST API

**Type**: External API contract — documents DigiCert API calls used by the automation.
**Base URL**: `https://www.digicert.com/services/v2`
**Auth**: `X-DC-DEVKEY: <api_key>` header on all requests.

---

## POST /order/certificate/ssl — Place Certificate Order

**Purpose**: Request a new SSL certificate from DigiCert.

**Request**:

```json
{
  "certificate": {
    "common_name": "myapp.example.com",
    "dns_names": ["myapp.example.com", "www.myapp.example.com"],
    "csr": "<PEM-encoded CSR>",
    "signature_hash": "sha256"
  },
  "organization": {
    "id": 12345
  },
  "order_validity": {
    "years": 1
  },
  "payment_method": "balance"
}
```

**Success Response (201)**:

```json
{
  "id": "dg-order-12345",
  "certificate_id": null,
  "status": "pending"
}
```

**Error Responses**:

| HTTP Status | Meaning | Automation action |
|-------------|---------|------------------|
| 400 | Invalid CSR or missing fields | Log error, halt renewal for this profile |
| 401 | Invalid API key | Log error, halt entire run |
| 403 | Org not validated for this domain | Log error, halt renewal for this profile |
| 429 | Rate limited | Retry with exponential backoff (max 3 attempts) |
| 5xx | DigiCert server error | Retry with exponential backoff (max 3 attempts) |

**Idempotency**: Before placing an order, the automation checks the state file for an
existing `order_id` in `pending` or `issued` status for this profile. If one exists,
this call is skipped.

---

## GET /order/certificate/{order_id} — Poll Order Status

**Purpose**: Check whether DigiCert has issued the certificate.

**Success Response (200)**:

```json
{
  "id": "dg-order-12345",
  "status": "issued",
  "certificate": {
    "id": "cert-67890",
    "serial_number": "1A2B3C4D5E6F",
    "valid_till": "2027-04-17"
  }
}
```

**Polling contract**:
- Poll every 30 seconds, up to 20 attempts (10 minutes total).
- If `status == "issued"` → proceed to download.
- If `status == "pending"` after 20 attempts → log timeout, set record status to
  `failed`, preserve existing cert on BIG-IP.
- If `status == "rejected"` → log rejection reason, set record status to `failed`.

---

## GET /certificate/{cert_id}/download/format/pem_all — Download Certificate

**Purpose**: Download the issued certificate bundle (leaf + intermediates).

**Success Response (200)**:
- `Content-Type: application/x-pem-file`
- Body: PEM chain — leaf certificate, then intermediate CA certificates.

**Automation handling**:
- Parse the PEM chain to extract the leaf certificate.
- Verify the leaf certificate CN and SANs match what was ordered.
- Verify the leaf certificate serial matches the order poll response.
- If any verification fails → log error, do NOT deploy to BIG-IP.

---

## Error Handling Summary

All DigiCert API errors are classified as:

| Class | HTTP Codes | Action |
|-------|-----------|--------|
| Transient | 429, 500, 502, 503, 504 | Retry with exponential backoff |
| Client error | 400, 403, 404 | Log and halt for this profile; continue to next |
| Auth error | 401 | Log and halt entire run immediately |
