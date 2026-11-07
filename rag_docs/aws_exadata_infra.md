# AWS Exadata Infrastructure (aws_odb_cloud_exadata_infrastructure)

Provides the physical Exadata hardware layer. One infrastructure can host multiple VM Clusters.
Provisioning time: 15–30 minutes. Provision one at a time — wait for this resource to reach ACTIVE before starting the next. Concurrent, parallel or simultaneous applies are not supported. Full order: Exadata Infrastructure → ODB Network → ODB Peering → VM/AVM Cluster.
Terraform provider: hashicorp/aws version 6.42.0+

## Required fields
- display_name: e.g. "exadb-infra-prod". Max 255 chars; letters/digits/underscores/hyphens; must start with letter or underscore; no consecutive hyphens.
- shape: hardware model — Exadata.X9M, Exadata.X10M, Exadata.X11M or Exadata.X11MV. X11M is the default and the recommendation for new deployments. Note: X10M has at times not been listed as available in ODB@AWS. The authoritative list per region comes from the ListDbSystemShapes API; config/aws_shapes.json is what this app offers.
- compute_count: number of database servers (nodes). Minimum 2, maximum 32. Must be even.
- storage_count: number of storage cells. Minimum 3, maximum 64. Must be a multiple of 3.
- availability_zone_id: AWS AZ ID where the infrastructure is located. Examples: use1-az4, use1-az6, usw2-az3, usw2-az4, euc1-az1, euc1-az2, apne1-az1, apne1-az4.

## Optional fields
- database_server_type: specific database server model. One model per shape — "X9M", "X10M", "X11M", "X11MV". Required on X11M (AWS documents both server types as mandatory for that generation); optional elsewhere.
- storage_server_type: specific storage server model. HC = high capacity, EF = extreme flash: "X9M-HC"/"X9M-EF", "X10M-HC"/"X10M-EF", "X11M-HC"/"X11M-EF". X11MV offers "X11MV-HC" only. Required on X11M; optional elsewhere.
- Exadata.X11MV: a variant of the X11M generation. Its server types are X11MV and X11MV-HC, and unlike X11M neither is mandatory.
- customer_contacts_to_send_to_oci: list of email objects for Oracle maintenance notifications. Maximum 10. Syntax: [{ email = "dba@example.com" }]
- availability_zone: AZ name (e.g. "us-east-1a") — informational, auto-derived from availability_zone_id.
- region: AWS region string — informational, auto-derived.
- tags: map of string tags.

## Maintenance window
The maintenance_window block configures Oracle-managed patching schedules.
- preference: NO_PREFERENCE (Oracle chooses window) or CUSTOM_PREFERENCE (you specify schedule). Default: NO_PREFERENCE.
- patching_mode: ROLLING (nodes patched one at a time, zero downtime — recommended for production) or NON_ROLLING (all nodes patched simultaneously, faster but causes downtime — acceptable for dev/test). Note: the value is NON_ROLLING (with underscore), not NONROLLING.
- is_custom_action_timeout_enabled: bool, whether custom timeout is enforced. Default false.
- custom_action_timeout_in_mins: integer 15–120. Custom patching action timeout. Only applies when is_custom_action_timeout_enabled = true.
- When preference = CUSTOM_PREFERENCE: set lead_time_in_weeks (1–4), hours_of_day, days_of_week, weeks_of_month, months.

## Terraform example (minimum viable)
```hcl
resource "aws_odb_cloud_exadata_infrastructure" "this" {
  display_name         = "exadb-inf-prod"
  shape                = "Exadata.X11M"
  compute_count        = 2
  storage_count        = 3
  availability_zone_id = "usw2-az3"

  customer_contacts_to_send_to_oci = [
    { email = "dba@example.com" }
  ]

  maintenance_window {
    patching_mode                    = "ROLLING"
    preference                       = "NO_PREFERENCE"
    is_custom_action_timeout_enabled = false
    custom_action_timeout_in_mins    = 15
  }

  tags = {
    env  = "prod"
    team = "dba"
  }
}
```

## Post-creation: getting DB server IDs
After infrastructure is created, query the DB server IDs with the data source:
```hcl
data "aws_odb_db_servers" "this" {
  cloud_exadata_infrastructure_id = module.<infra_module>.infra_id
}
```
These IDs are required when creating a VM Cluster (db_servers field).
Access via: data.aws_odb_db_servers.<name>.db_server_ids

## Module outputs
- infra_id: used as cloud_exadata_infrastructure_id in VM clusters and AVM clusters
- infra_arn: ARN for cross-account references

## Naming
module_name examples: odb_infra_prod, odb_exaInfra_us_east, exadb_infra_nonprod

## Capacity guidance
- X11M quarter rack: 2 compute, 3 storage — minimum viable configuration
- X11M half rack: 4 compute, 6 storage
- X11M full rack: 8 compute, 12 storage
- compute_count must be even; storage_count must be a multiple of 3

## Storage server types
- X11M-HC: high-capacity storage (large HDD-based, lower cost per TB)
- X11M-EF: extreme flash (all-NVMe, highest IOPS)
- X11MV-HC: the only storage server type offered on Exadata.X11MV — there is no EF option on that shape
- X10M-HC / X10M-EF and X9M-HC / X9M-EF for the earlier generations
On Exadata.X11M both database_server_type and storage_server_type are mandatory. On every other shape they are optional, and if storage_server_type is not set Oracle assigns a default for the shape.
