# Oracle AI DB@GCP — Gotchas, Immutable Fields, and Provisioning Notes

## Provisioning times
- google_oracle_database_odb_network: 5–10 minutes
- google_oracle_database_odb_subnet: 2–3 minutes each (client and backup can be created in parallel)
- google_oracle_database_cloud_exadata_infrastructure: 60–90 minutes
- google_oracle_database_exadb_vm_cluster: 45–60 minutes
- google_oracle_database_autonomous_database: 5–15 minutes

Creation order: ODB Network → Subnets (parallel) + Exadata Infrastructure (can start in parallel with subnets) → VM Cluster (must wait for infrastructure to be healthy).

Autonomous AI Database Serverless is outside that chain: it needs only the ODB
Network and its client subnet, and can be created in parallel with the Exadata
Infrastructure and VM Cluster.

## IMMUTABLE fields — cannot change after creation
google_oracle_database_odb_network:
- odb_network_id, location, gcp_oracle_zone, network (VPC association)

google_oracle_database_odb_subnet:
- odb_subnet_id, location, odb_network (parent), cidr_range, purpose (CLIENT_SUBNET / BACKUP_SUBNET)

google_oracle_database_cloud_exadata_infrastructure:
- cloud_exadata_infrastructure_id, location, gcp_oracle_zone, shape, compute_count, storage_count

google_oracle_database_exadb_vm_cluster:
- exadb_vm_cluster_id, location, odb_network, odb_subnet, backup_odb_subnet, exadata_infrastructure
- hostname_prefix, node_count, enabled_ecpu_count_per_node, ssh_public_keys, license_type, cluster_name

## Exascale VM Cluster: grid_image_id is the input — gi_version is computed
This applies to google_oracle_database_exadb_vm_cluster (Exascale) only. The
Exadata Dedicated cluster, google_oracle_database_cloud_vm_cluster, takes
gi_version as an input.
- CORRECT on Exascale: set grid_image_id
- WRONG on Exascale: set gi_version (read-only there, populated after creation)
- grid_image_id: The Grid Infrastructure image OCID, `ocid1.dbpatch...` — e.g.
"ocid1.dbpatch.oc1.uk-london-1.anwgiljrt5t4sqqa7anvf..." in the provider's own
example. Oracle publishes no API for it: read it in the OCI Console.

## time_zone is a nested block — not a string
CORRECT Terraform HCL:
  time_zone {
    id = "UTC"
  }
WRONG:
  time_zone = "UTC"
Using the flat string form will fail at plan time with a schema error.

## exascale_db_storage_vault is required
The exascale_db_storage_vault field in the properties block is required for google_oracle_database_exadb_vm_cluster (Exascale VM Cluster).
Format: "projects/<project>/locations/<region>/exascaleDbStorageVaults/<vault-name>"
Example: "projects/my-proj/locations/us-east4/exascaleDbStorageVaults/my-vault"

## shape_attribute is required
shape_attribute must be set in the properties block. Valid values: SMART_STORAGE or BLOCK_STORAGE.
SMART_STORAGE is recommended for most workloads.

## ODB subnet purpose is immutable — plan CLIENT vs BACKUP upfront
Cannot change a CLIENT_SUBNET to a BACKUP_SUBNET or vice versa after creation.
The root module always creates two subnets per ODB network: one CLIENT_SUBNET, one BACKUP_SUBNET.

## CIDR range is immutable on subnets
Once a subnet is created, its cidr_range cannot be changed. Plan non-overlapping CIDRs carefully.
Subnets must not overlap each other or existing GCP VPC subnets in the same region.
Minimum subnet size: /27. Maximum: /22.

## Infrastructure must be fully healthy before VM cluster creation
Exadata Infrastructure provisioning takes 60–90 minutes. Do not attempt to create a VM Cluster until the infrastructure lifecycle_state = ACTIVE. Terraform handles this automatically via resource dependencies.

## Service-managed OCI compartment — do not modify
The first ODB Network deployment automatically creates an OCI compartment for the service.
Do NOT rename, move, or delete this compartment. The service will lose the ability to manage Oracle resources in the project.

## Autonomous AI Database Serverless has no Exadata Infrastructure and no VM Cluster
google_oracle_database_autonomous_database is Serverless, not Dedicated. Oracle runs
the fleet, so you do NOT create an Exadata Infrastructure or a VM Cluster for it and
the resource has no exadata_infrastructure argument. It needs only an ODB Network and
that network's CLIENT subnet, wired through odb_network and odb_subnet.

An Autonomous Database never uses a backup subnet — backup subnets serve Exadata VM
Clusters only. Deploying only Autonomous Databases does not require one.

ADB is a REGIONAL resource: unlike the Exadata Infrastructure, VM Clusters and ODB
Subnets, it is not placed in a gcp_oracle_zone and has no such field.

Practical consequence for Terraform: a deployment that is Autonomous Serverless
only needs just an ODB Network and its client subnet. Do not write an Exadata
Infrastructure module, a VM Cluster module, an Autonomous VM Cluster module, or a
backup subnet for it — none of them apply. The module set you generate depends on
whether the deployment is Dedicated (Exadata) or Serverless.

Requires hashicorp/google >= 7.0 — odb_network and odb_subnet on this resource were
added in 7.0. Below that, the only networking option is the legacy network + cidr
pair against a plain VPC.

## Autonomous Database autoscaling rewrites compute and storage — guard with ignore_changes
When auto scaling is enabled, the service changes compute_count and the storage size
in place. The next terraform plan then proposes shrinking the database back to the
seed value in your configuration, on every run.

Oracle's published fix is a lifecycle ignore_changes block on the resource covering
properties[0].compute_count, data_storage_size_gb, data_storage_size_tb, db_version,
db_edition, is_auto_scaling_enabled, is_storage_auto_scaling_enabled and
backup_retention_period_days.

Trade-off: with that block in place, editing those values in tfvars produces no plan
at all. To resize deliberately, comment the field out of ignore_changes, apply, then
put it back.

## customer_contacts on the Autonomous Database is a nested block — not a list
- CORRECT: customer_contacts { email = "dba@example.com" }
- WRONG: customer_contacts = ["dba@example.com"]

Repeat the block once per address, or generate it with a dynamic block.

## labels are Terraform-only — not visible in GCP Console
Resource labels applied via Terraform are not shown in the Google Cloud Console for Oracle DB resources. This is expected behaviour — labels are still applied and queryable via the API.

## data_storage_size_in_tbs can increase but not decrease
The data storage allocation for a VM Cluster can be expanded post-creation but cannot be reduced.
Other storage-related fields (db_node_storage_size_per_vm_in_gbs, spare_snapshot_space_in_gbs) are set at creation and may be immutable depending on provider version.

## Exadata Infrastructure shape availability is region-specific
Not all Exadata shapes are available in all GCP regions. Verify shape availability for your target region before configuring. Exadata.X11M is generally available in us-east4 and us-central1.

## Resource ID naming rules (odb_network_id, odb_subnet_id, etc.)
- 1–63 characters
- Lowercase letters, numbers, hyphens only
- Must start with a lowercase letter or number
- Must end with a lowercase letter or number
- No consecutive hyphens
