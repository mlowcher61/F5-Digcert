#!/usr/bin/env python3
"""Mock DigiCert CertCentral API server for integration testing."""

import json
import uuid
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, Response

app = Flask(__name__)

# In-memory order store: order_id -> order dict
ORDERS: dict = {}
# In-memory cert store: cert_id -> pem string
CERTS: dict = {}

VALID_API_KEY = "test-api-key"


def auth_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-DC-DEVKEY", "")
        if key != VALID_API_KEY:
            return jsonify({"errors": [{"code": "unauthorized", "message": "Invalid API key"}]}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/services/v2/order/certificate/ssl", methods=["POST"])
@auth_required
def place_order():
    body = request.get_json()
    order_id = f"order-{uuid.uuid4().hex[:8]}"
    cert_id = f"cert-{uuid.uuid4().hex[:8]}"
    cn = body.get("certificate", {}).get("common_name", "test.example.com")

    ORDERS[order_id] = {
        "id": order_id,
        "status": "issued",
        "certificate": {
            "id": cert_id,
            "serial_number": uuid.uuid4().hex[:16].upper(),
            "valid_till": (datetime.utcnow() + timedelta(days=365)).strftime("%Y-%m-%d"),
            "common_name": cn,
        },
    }

    CERTS[cert_id] = _generate_self_signed_pem(cn)

    return jsonify({"id": order_id, "certificate_id": None, "status": "pending"}), 201


@app.route("/services/v2/order/certificate/<order_id>", methods=["GET"])
@auth_required
def get_order(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        return jsonify({"errors": [{"message": "Order not found"}]}), 404
    return jsonify(order), 200


@app.route("/services/v2/certificate/<cert_id>/download/format/pem_all", methods=["GET"])
@auth_required
def download_cert(cert_id: str):
    pem = CERTS.get(cert_id)
    if not pem:
        return jsonify({"errors": [{"message": "Certificate not found"}]}), 404
    return Response(pem, mimetype="application/x-pem-file")


def _generate_self_signed_pem(cn: str) -> str:
    """Generate a minimal self-signed PEM for testing."""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime as dt

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(dt.datetime.utcnow())
            .not_valid_after(dt.datetime.utcnow() + dt.timedelta(days=365))
            .sign(key, hashes.SHA256())
        )
        return cert.public_bytes(serialization.Encoding.PEM).decode()
    except ImportError:
        return "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----\n"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8443, debug=False)
