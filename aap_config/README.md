# aap_config — Config-as-Code for F5-Digicert on AAP

This directory defines every AAP object the F5-Digicert solution needs
(organization, credential type, credentials, project, execution environment,
inventory, job template, schedule) as declarative YAML. It's applied to a
controller with the `infra.aap_configuration` collection.

## Prerequisites

1. An AAP 2.5+ controller reachable from where you run the playbook.
2. An admin user or OAuth token that can create the objects above.
3. The F5-Digicert EE image already built with `ansible-builder` from
   `../execution-environment.yml` and pushed to a registry your controller
   can reach. Update `image:` in `group_vars/all/execution_environments.yml`
   to match.
4. This repo pushed to a git remote your controller can reach (the project
   URL is set to `https://github.com/mlowcher61/F5-Digcert.git`).

## Apply

```bash
cd aap_config

# Install the config collection
ansible-galaxy collection install -r requirements.yml -p ./collections/

# Create and encrypt your vault file from the example
cp example_vault.yml vault.yml
# edit vault.yml and fill in real values
ansible-vault encrypt vault.yml

# Edit group_vars/all/aap_connection.yml for your controller hostname +
# admin username (the password comes from vault.yml).

ansible-playbook -i inventory configure.yml -e @vault.yml --ask-vault-pass
```

## What gets created

| File | AAP object(s) |
|------|---------------|
| `organizations.yml` | `F5-Digicert` organization |
| `credential_types.yml` | `DigiCert CertCentral` custom credential type |
| `credentials.yml` | `F5 BIG-IP Admin` (Network) + `DigiCert CertCentral API` |
| `execution_environments.yml` | `F5-Digicert EE` |
| `projects.yml` | `F5-Digicert` git project |
| `inventories.yml` | `F5 BIG-IP Devices` inventory, `bigip_devices` group, sample host |
| `job_templates.yml` | `F5-Digicert - Renew Certificates` |
| `schedules.yml` | Daily 02:00 UTC renewal schedule |

## Secrets

All secrets live in `vault.yml` (copied from `example_vault.yml` and
encrypted with `ansible-vault`). `vault.yml` is gitignored — never commit
it. The config YAML references these values via `{{ vault_* }}` Jinja
lookups, so the repo itself stays safe to share.

Vaulted values:

| Variable | Used by |
|----------|---------|
| `vault_aap_password` | `aap_connection.yml` — AAP admin login |
| `vault_bigip_username` / `vault_bigip_password` | `credentials.yml` — F5 BIG-IP Admin |
| `vault_digicert_api_key` / `vault_digicert_org_id` | `credentials.yml` — DigiCert CertCentral API |
