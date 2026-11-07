# Exascale on Oracle AI Database@Google Cloud — storage vaults and Exascale VM clusters

## What Exascale is here
An Exascale VM Cluster runs VMs on Oracle-managed Exascale infrastructure and keeps
its databases in an **Exascale Database Storage Vault**. Unlike Exadata Database
Service on Dedicated Infrastructure, there is **no Exadata Infrastructure** to
provision. Several clusters can share one vault. Wait for a cluster to finish
provisioning before creating Exascale databases on it.

Terraform resources (hashicorp/google):
- `google_oracle_database_exascale_db_storage_vault` — the vault
- `google_oracle_database_exadb_vm_cluster` — the Exascale VM cluster

**Provider floor: hashicorp/google >= 7.20.0.** Found by validating each release:
7.19.0 fails with "Invalid resource type". Terraflow raises the root constraint to
7.20.0 only when a configuration has Exascale; otherwise it stays at 7.5.0.

## Exascale storage vault fields
| Field | Rule |
|---|---|
| exascale_db_storage_vault_id | 1–63 lowercase letters, digits, hyphens; starts with a letter, ends with a letter or digit |
| display_name | 1–255 letters, digits, `_`, `-`; starts with a letter or `_`; no `--` |
| total_size_gbs (storage capacity for databases) | 300 to 100,000 GB |
| additional_flash_cache_percent (smart flash and memory cache) | 34% to 300% of the storage capacity; optional |
| gcp_oracle_zone | the zone the clusters on this vault run in |

## Exascale VM cluster fields
| Field | Rule |
|---|---|
| exadb_vm_cluster_id | 1–63 lowercase letters, digits, hyphens; starts with a letter |
| cluster_name | optional; 1–11 letters, digits, hyphens; starts with a letter |
| node_count (number of VMs) | 1 to 10 |
| enabled_ecpu_count_per_node | 8 to 200, in increments of 4 |
| additional_ecpu_count_per_node (reserved ECPUs) | 0 to 192, in increments of 4; optional |
| vm_file_system_storage size per VM | 220–1100 GB with smart storage; 260–1100 GB with block storage |
| shape_attribute | `SMART_STORAGE` for Oracle AI Database 26ai and later; `BLOCK_STORAGE` for 19c |
| license_model | `LICENSE_INCLUDED` or `BRING_YOUR_OWN_LICENSE` |
| ssh_public_keys | at least one |
| odb_network, odb_subnet, backup_odb_subnet | the ODB Network's client **and** backup subnet |
| grid_image_id | Grid Infrastructure image OCID, `ocid1.dbpatch...` |

## Exascale gotchas
- **grid_image_id has no API.** Oracle's documentation states it is not available
  programmatically: read the Grid Infrastructure image OCID in the OCI Console.
  Terraflow leaves `ocid1.dbpatch.oc1..CHANGEME` until it is filled in; that
  validates but fails at apply, and the page's validator rejects it.
- **No zone on the cluster.** The resource has no `gcp_oracle_zone` input — the
  cluster runs in its vault's zone. Region cannot be changed after creation.
- **Needs a backup subnet.** An ODB Network marked "adbs" (Autonomous Serverless
  only) builds no backup subnet, so an Exascale VM Cluster cannot use it — mark it
  "both" or "dedicated".
- **Scaling through Terraform.** Oracle's sample Terraform puts the ECPU counts and
  file system size in `lifecycle.ignore_changes` so console scaling is not reverted.
  Terraflow does not: a resize in `terraform.auto.tfvars` plans, and a console change
  is reverted by the next apply. Only `ssh_public_keys` is ignored.
- **Exascale-only configurations** have no Exadata Infrastructure: remove the Exadata
  Infrastructure and VM Cluster cards. With Exascale present, Terraflow does not
  invent placeholder Exadata resources for an empty list.
- A vault can be built in the same configuration (`vault_key`) or referenced by full
  name (`existing_vault`: `projects/<p>/locations/<region>/exascaleDbStorageVaults/<id>`),
  exactly one of the two per cluster.

## Deploy order
ODB Network (client + backup subnets) → Exascale storage vault → Exascale VM cluster
→ databases. Oracle does not publish typical durations; the modules allow 3 hours for
create, update and delete.

## Source
Oracle: Create an Exascale VM Cluster —
https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/gcpcr-create-exascale-vm-cluster.html
