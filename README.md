# F5 DigiCert Certificate Renewal Automation

Automated SSL certificate renewal for F5 BIG-IP devices via DigiCert CertCentral.

See [specs/001-f5-cert-renewal/quickstart.md](specs/001-f5-cert-renewal/quickstart.md) for setup and usage instructions.

## Quick start

```bash
# Install collections
ansible-galaxy collection install -r requirements.yml

# Dry run (no changes)
export BIGIP_USERNAME=admin BIGIP_PASSWORD=... DIGICERT_API_KEY=... DIGICERT_ORG_ID=...
ansible-playbook playbooks/renew_certificates.yml -i inventory/hosts.yml -e dry_run=true

# Live run
ansible-playbook playbooks/renew_certificates.yml -i inventory/hosts.yml
```
