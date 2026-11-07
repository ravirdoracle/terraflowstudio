# AWS Autonomous Database Serverless and the Secrets Manager integration

## Autonomous Database Serverless (aws_odb_autonomous_database)
Autonomous Database **Serverless** (ADB-S) on Oracle AI Database@AWS.

Requires hashicorp/aws **6.68.0** or later (the resource arrived in 6.68.0, October 2026),
and Terraform or OpenTofu **1.11** or later, because the ADMIN password goes through an
ephemeral variable into a write-only argument.

### Does Autonomous Database Serverless need Exadata Infrastructure?
No. A Serverless autonomous database does not need an Exadata Infrastructure, a VM
Cluster or an Autonomous VM Cluster. Oracle runs the shared Exadata fleet; the database
needs only an existing ODB Network. That is the difference from the Autonomous VM Cluster
(ADB-D, aws_odb_cloud_autonomous_vm_cluster), which runs on your own Exadata
Infrastructure.

### Provisioning autonomous databases — one at a time
Can I provision two autonomous databases at the same time? No. Provision one autonomous
database at a time — wait for each to reach AVAILABLE before starting the next.
Concurrent, parallel or simultaneous applies are not supported for ODB@AWS. Provisioning
an autonomous database can take several hours (provider default timeouts are 24h). It
needs only its ODB Network to be ACTIVE. Full order: Exadata Infrastructure → ODB Network →
ODB Peering → VM/AVM Cluster → Secrets Manager integration → Autonomous Database.

```bash
terraform apply -target='module.aws_autonomous_db["sales_adb"]'
terraform apply -target='module.aws_autonomous_db["hr_adb"]'
```

### Autonomous database fields
Generated layout: one shared `modules/aws-autonomous-db/` driven by the
`aws_autonomous_dbs` map in terraform.auto.tfvars. Each entry names its ODB Network by
`network_ref` (a key of aws_networks, or of existing_odb_network_ids for a network
provisioned outside Terraform).

Fields the card asks for:
- display_name, db_name (starts with a letter, alphanumeric only, max 30 characters).
- network_ref — the ODB Network. **Changing it replaces the database.**
- db_workload: OLTP (transaction processing), LH (lakehouse), AJD (JSON), APEX.
  Note AWS uses LH where GCP uses DW.
- license_model: LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE.
- compute_count: ECPUs, 0.1–512 (fractional values allowed).
- data_storage_size_in_tbs: a **whole number** of TB, 1–384. The provider rejects a fractional TB value.
- source is always "NONE" — this configuration creates new databases only.

Optional + Computed fields — left unset they adopt the value the service assigns and
produce no diff, so they are omitted from tfvars unless set: db_version (19c, 23ai),
database_edition (STANDARD_EDITION / ENTERPRISE_EDITION, BYOL only),
is_auto_scaling_enabled, is_auto_scaling_for_storage_enabled,
backup_retention_period_in_days, autonomous_maintenance_schedule_type (EARLY patches a
week ahead of REGULAR), is_mtls_connection_required, private_endpoint_label,
private_endpoint_ip (must sit in the network's client subnet), allowlisted_ips (1–1024
IPs or CIDRs), character_set and ncharacter_set (**changing either replaces the
database**), encryption_key_provider (ORACLE_MANAGED or AWS_KMS) with kms_key_id (the
KMS key ARN, AWS_KMS only), customer_contacts (emails OCI notifies).

### ADMIN password — two sources, neither stored
The provider has three mutually exclusive inputs: admin_password (stored in state),
admin_password_wo (write-only) and the admin_password_source block. The generated
configuration never uses admin_password. Per database, `admin_password_source` picks:

- **write_only** (default) — the password is supplied at apply time and sent through the
  write-only `admin_password_wo`. The root variable `aws_adb_admin_passwords` is a map
  keyed by database, declared `sensitive` and `ephemeral`, so the value never reaches a
  generated file, a saved plan file or state:
  `export TF_VAR_aws_adb_admin_passwords='{ sales_adb = "..." }'`
  12–30 characters. To rotate: change the password and bump `admin_password_wo_version`.
  A write_only database with no entry in the map fails at plan with "Invalid index".
- **secrets_manager** — OCI reads the password from AWS Secrets Manager. Needs
  `secret_arn`, `secret_iam_role_arn` (a customer-managed IAM role OCI assumes) and
  `secret_external_id_type` (compartment_ocid, database_ocid or tenant_ocid; default
  compartment_ocid). The account's Secrets Manager integration must be enabled first.

Not surfaced by the form: clones and Data Guard / disaster-recovery sources
(source_configuration), refreshable clones, scheduled start/stop (scheduled_operations),
long_term_backup_schedule, resource pools, db_tools_details, transportable tablespaces,
standby allowlists, local Data Guard, cpu_core_count (legacy OCPU) and
data_storage_size_in_gbs.

Module outputs: adb_id, adb_arn, adb_ocid, private_endpoint. Root output: autonomous_databases.

---

## Secrets Manager integration (aws_odb_autonomous_database_secrets_manager_integration)
Enables Autonomous Database Serverless to read ADMIN passwords from AWS Secrets Manager.
It provisions an Oracle-managed service role, exported as `role_arn`.

- **One per AWS account and Region**, shared by every Autonomous Database there —
  including databases outside this configuration. Creating it adopts an integration that
  is already enabled.
- **Destroying it disables the integration for the whole account and Region**, which can
  break other teams' databases. The generated module sets `lifecycle { prevent_destroy = true }`.
  To stop managing it from a configuration without disabling it, remove it from state:
  `removed { from = module.aws_adb_secrets_integration  lifecycle { destroy = false } }`.
- Manage it in only one Terraform configuration. On the AWS page it is a single toggle,
  not a card; leave it off if another configuration already manages it.
- Takes no arguments beyond the provider region. Provisioning: up to 15 minutes. Import
  by Region, e.g. `us-east-1`.

After enabling it, create the customer-managed IAM role yourself (the configuration does
not generate it): its trust policy must allow the `adb_secrets_manager_service_role_arn`
output to assume it, and its permissions must allow `secretsmanager:GetSecretValue` on
the secret. Then name that role and the secret on each database.

```bash
terraform apply -target='module.aws_adb_secrets_integration'
# create the IAM role trusting the role_arn output, outside Terraform
terraform apply -target='module.aws_autonomous_db["sales_adb"]'
```

Naming: module_name examples: sales_adb, hr_adb_dev, analytics_lh
