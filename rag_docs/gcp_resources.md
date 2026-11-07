# GCP Oracle Database Resources (AI DB@GCP)

Google Cloud Oracle Database deploys via the google provider (≥ 7.0) alongside the OCI provider (≥ 7.29.0).

## Creation order
1. google_oracle_database_odb_network (5–10 min)
2. google_oracle_database_odb_subnet — client and backup (2–3 min each, can run in parallel)
3. google_oracle_database_cloud_exadata_infrastructure (60–90 min)
4. google_oracle_database_cloud_vm_cluster (after infra is healthy)

Exascale is a different chain with no Exadata Infrastructure: steps 1 and 2 (it
needs the client AND backup subnet), then google_oracle_database_exascale_db_storage_vault,
then google_oracle_database_exadb_vm_cluster. Oracle publishes no typical durations.

Autonomous AI Database Serverless is NOT part of that chain. It needs only steps 1
and 2 (and only the CLIENT subnet), takes 5–15 minutes, and can be deployed in
parallel with the Exadata Infrastructure and VM Cluster. It has no Exadata
Infrastructure and no VM Cluster underneath — Oracle runs the fleet.

---

## ODB Network (google_oracle_database_odb_network)
Foundation resource — all other GCP Oracle DB resources depend on it. Provisioning: 5–10 minutes.

Required fields:
- odb_network_id: unique short ID. 1–63 chars, lowercase letters/numbers/hyphens, must start AND end with lowercase letter or number. IMMUTABLE.
- display_name: user-facing name, letters/digits/underscores/hyphens, starts with letter or underscore.
- location: GCP region (e.g. us-east4, us-central1, europe-west1, europe-west4, asia-northeast1). IMMUTABLE.
- network: existing GCP VPC network ID or self-link. Must exist before creating the ODB network.
- gcp_oracle_zone: Oracle zone within the region, format "<region>-<letter>-r<number>" e.g. "us-east4-b-r1", "us-central1-a-r1". IMMUTABLE.
- project: GCP project ID.

Optional fields:
- deletion_protection: bool, default false.
- labels: map of string labels (Terraform-only; not visible in GCP Console).

Module outputs: odb_network_id, odb_network_name (full resource path used by subnets and VM clusters)

Naming: module_name examples: gcp_odb_net_prod, gcp_network_dev, odb_net_us_east4

Note: The first deployment creates an OCI service-managed compartment with restrictive IAM policies. Do NOT modify, move, or delete this compartment — the service will lose the ability to manage resources.

---

## ODB Subnet (google_oracle_database_odb_subnet)
Client and backup subnets are created as separate modules per ODB network. Provisioning: 2–3 minutes each.

Required fields:
- odb_subnet_id: unique short ID. 1–63 chars, lowercase letters/numbers/hyphens, starts with letter, ends with letter/number. IMMUTABLE.
- location: GCP region — must match the parent ODB network region. IMMUTABLE.
- odb_network: parent ODB Network short ID (the odb_network_id value, not the full resource path). IMMUTABLE.
- cidr_range: CIDR block for the subnet. Minimum /27, maximum /22. Must be RFC1918. IMMUTABLE.
  Examples: "10.2.0.0/24" for client, "10.2.1.0/24" for backup. Must not overlap each other or existing VPC subnets.
- purpose: CLIENT_SUBNET or BACKUP_SUBNET. IMMUTABLE — cannot be changed after creation; cannot convert between types.

Optional fields:
- project: GCP project ID.
- deletion_protection: bool, default false.
- labels: map of string labels.

Module outputs: odb_subnet_id, odb_subnet_name (full resource path, used by VM cluster)

The root main.tf creates two subnet modules per ODB network:
- client subnet: module name typically <network_module>_client_subnet — wired as odb_subnet in VM cluster
- backup subnet: module name typically <network_module>_backup_subnet — wired as backup_odb_subnet in VM cluster

---

## Exadata Infrastructure (google_oracle_database_cloud_exadata_infrastructure)
Physical Exadata hardware. Provisioning: 60–90 minutes. Must be fully healthy before creating VM clusters.

Required fields:
- cloud_exadata_infrastructure_id: unique short ID. 1–63 chars, lowercase. IMMUTABLE.
- display_name: user-facing name.
- location: GCP region. IMMUTABLE.
- gcp_oracle_zone: Oracle zone e.g. "us-east4-b-r1". IMMUTABLE.
- project: GCP project ID.

Properties block (required, nested inside resource):
- shape: Exadata hardware model. e.g. "Exadata.X9M", "Exadata.X11M" (latest, recommended). IMMUTABLE. Not all shapes available in all regions.
- compute_count: number of database servers. Minimum 2. IMMUTABLE.
- storage_count: number of storage servers. Minimum 3. IMMUTABLE.

Maintenance window (optional, nested inside properties):
- mw_preference (preference): NO_PREFERENCE or CUSTOM_PREFERENCE. Default NO_PREFERENCE.
- mw_patching_mode (patching_mode): ROLLING (zero downtime, recommended for production) or NON_ROLLING (faster, causes downtime).
- When CUSTOM_PREFERENCE: also set mw_months (e.g. ["JANUARY","APRIL"]), mw_weeks_of_month ([1,4]), mw_days_of_week (["SUNDAY"]), mw_hours_of_day ([2,14] in UTC), mw_lead_time_week (1–4).
- mw_is_custom_action_timeout_enabled: bool. mw_custom_action_timeout_mins: 15–120.

Optional fields:
- customer_contacts: list of email addresses for Oracle maintenance notifications. Max 10.
- total_storage_size_gb: total storage size override.
- labels: map of string labels.
- deletion_protection: bool.

Module outputs: infra_name (full resource path, wired as exadata_infrastructure in VM cluster)

---

## Exascale VM Cluster (google_oracle_database_exadb_vm_cluster)
The **Exascale** VM cluster: VMs on Oracle-managed Exascale infrastructure, with
databases in an Exascale Database Storage Vault. It does **not** run on an Exadata
Infrastructure and takes no `exadata_infrastructure` or `gcp_oracle_zone` input — it
runs in its vault's zone. Not to be confused with google_oracle_database_cloud_vm_cluster,
the Exadata Dedicated cluster (which takes gi_version). hashicorp/google >= 7.20.0.
Checked against the provider schema (8.10.0) and Oracle's "Create an Exascale VM
Cluster" page.

Top-level arguments:
- exadb_vm_cluster_id (required): 1–63 lowercase letters, digits, hyphens; starts with a letter.
- display_name (required), location (required; region cannot change after creation).
- odb_subnet, backup_odb_subnet (required) and odb_network: the ODB Network's client AND
  backup subnet, so an "adbs" (Serverless-only) network cannot be used.
- project, labels, deletion_protection (optional).

properties block — required:
- exascale_db_storage_vault: full name "projects/<p>/locations/<region>/exascaleDbStorageVaults/<id>".
- grid_image_id: the Grid Infrastructure image OCID, "ocid1.dbpatch...". Oracle publishes
  no API for it — read it in the OCI Console. (gi_version is computed on this resource.)
- shape_attribute: SMART_STORAGE (Oracle AI Database 26ai and later) or BLOCK_STORAGE (19c).
- node_count: 1 to 10 VMs.
- enabled_ecpu_count_per_node: 8 to 200, in increments of 4.
- hostname_prefix.
- ssh_public_keys: at least one.
- vm_file_system_storage { size_in_gbs_per_node }: 220–1100 GB (smart) or 260–1100 GB (block).

properties block — optional:
- additional_ecpu_count_per_node: reserved ECPUs, 0 to 192, in increments of 4.
- cluster_name: 1–11 letters, digits, hyphens; starts with a letter.
- license_model: LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE.
- scan_listener_port_tcp.
- time_zone: NESTED BLOCK — time_zone { id = "UTC" }, not a flat string.
- data_collection_options { is_diagnostics_events_enabled, is_health_monitoring_enabled,
  is_incident_logs_enabled }.

Computed: gi_version, hostname, memory_size_gb, lifecycle_state, gcp_oracle_zone, identity_connector.

The vault (google_oracle_database_exascale_db_storage_vault): exascale_db_storage_vault_id,
display_name, location, gcp_oracle_zone, and properties { exascale_db_storage_details
{ total_size_gbs = 300 to 100,000 }, additional_flash_cache_percent = 34 to 300 }.
See gcp_exascale.md for the gotchas.

Module outputs (Terraflow gcp-exascale-vm-cluster): vm_cluster_name, vm_cluster_id,
gcp_oracle_zone, gi_version, memory_size_gb

---

## Autonomous AI Database Serverless (google_oracle_database_autonomous_database)
Oracle Autonomous AI Database on AI DB@GCP. Provisioning: 5–15 minutes.

Serverless, not Dedicated. Oracle runs the fleet, so there is NO Exadata
Infrastructure and NO VM Cluster underneath it. You cannot and do not reference an
exadata_infrastructure from this resource. Deploy it in parallel with the Exadata
chain — it only needs the ODB Network and its client subnet.

ADB is a REGIONAL resource. Exadata Infrastructure, VM Clusters and ODB Subnets are
zonal and take a gcp_oracle_zone; the Autonomous Database does not and has no such
field.

Requires hashicorp/google provider >= 7.0 — the odb_network / odb_subnet arguments
on this resource were added in 7.0.

Top-level required fields:
- autonomous_database_id: unique short ID. Lowercase letters, digits, hyphens; max 63 chars. IMMUTABLE.
- location: GCP region. No zone.

Top-level optional fields:
- database: Oracle DB name. Must begin with a letter, max 30 alphanumeric chars.
- display_name: user-facing name.
- admin_password: ADMIN user password. 12–30 chars, upper + lower + digit, no double quote, cannot contain the word "admin". Never commit this to a tfvars file — supply it via TF_VAR_ at apply time.
- odb_network: full ODB Network resource path. Format "projects/<project>/locations/<region>/odbNetworks/<name>". Wired from module.<network>.odb_network_name.
- odb_subnet: full CLIENT ODB Subnet resource path. Format "projects/<project>/locations/<region>/odbNetworks/<net>/odbSubnets/<subnet>". Wired from module.<network>.client_subnet_name.
- network + cidr: the LEGACY alternative to odb_network/odb_subnet — attaches the database to a plain VPC instead of an ODB Network. Use one pair or the other, not both.
- project, labels, deletion_protection, deletion_policy (DELETE, PREVENT or ABANDON).
- source_config: for a cross-region Autonomous Data Guard standby.

CRITICAL — ADB uses the CLIENT subnet only:
- The client subnet is used by BOTH Autonomous Databases and Exadata VM Clusters.
- The backup subnet is used ONLY by Exadata VM Clusters. An Autonomous Database
  never takes a backup_odb_subnet, and there is no such argument on this resource.
- Deploying only Autonomous Databases therefore does not require a backup subnet.

Properties block (nested) — required fields:
- db_workload: OLTP (transaction processing), DW (data warehouse), AJD (JSON) or APEX.
- license_type: LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE.

Properties block — optional fields:
- db_edition: STANDARD_EDITION or ENTERPRISE_EDITION.
- db_version: Autonomous Database version, e.g. 23ai or 19c.
- compute_count: ECPUs. Minimum 2. Fractional values allowed.
- data_storage_size_gb / data_storage_size_tb: storage. Set one, not both.
- is_auto_scaling_enabled: allow compute to scale up to 3x the base count on demand.
- is_storage_auto_scaling_enabled: allow storage to grow beyond the reserved size.
- backup_retention_period_days: 1–60 days. Default 60.
- maintenance_schedule_type: EARLY or REGULAR. EARLY patches a week ahead of REGULAR.
- character_set (default AL32UTF8), n_character_set (default AL16UTF16).
- mtls_connection_required: require mutual TLS. Set false to allow TLS-only clients.
- private_endpoint_label: hostname prefix for the private endpoint.
- private_endpoint_ip: must fall inside the client subnet's CIDR. Omit and Oracle picks one.
- operations_insights_state: ENABLED or NOT_ENABLED.
- customer_contacts: NESTED BLOCK, repeated — customer_contacts { email = "..." }. Not a flat list of strings.
- secret_id, vault_id: OCI vault references.

CRITICAL — autonomous scaling causes plan drift:
- When auto scaling is on, the service rewrites compute_count and the storage size
  in place. A later terraform plan then proposes shrinking the database back to the
  value in your configuration.
- Oracle's published fix is a lifecycle ignore_changes block covering
  properties[0].compute_count, data_storage_size_gb, data_storage_size_tb,
  db_version, db_edition, is_auto_scaling_enabled, is_storage_auto_scaling_enabled
  and backup_retention_period_days.
- Consequence: with that block in place, editing any of those values in tfvars
  produces no plan. To resize deliberately, comment the field out of ignore_changes,
  apply, then restore it.

CRITICAL — customer_contacts is a nested block:
- CORRECT: customer_contacts { email = "dba@example.com" }
- WRONG: customer_contacts = ["dba@example.com"]

Module outputs: autonomous_database_name, autonomous_database_id, ocid, create_time.
The OCID lives at properties[0].ocid.

---

## GCP Regions with Oracle DB support
- us-east4 (N. Virginia): gcp_oracle_zone examples: us-east4-b-r1
- us-central1 (Iowa): gcp_oracle_zone examples: us-central1-a-r1
- europe-west1 (Belgium)
- europe-west4 (Netherlands)
- asia-northeast1 (Tokyo)

## Root variables for GCP
gcp_project: GCP project ID
gcp_region: GCP region
labels: map of string labels applied to all resources

---

## Available Exadata service variants on GCP

### Exadata Database Service on Dedicated Infrastructure
- Versions: 19c, 26ai
- Fully managed dedicated physical hardware
- Elastic vertical and horizontal scaling
- Manual DBA tuning and configuration required
- Complete isolation (dedicated infrastructure)
- Use case: mission-critical, latency-sensitive workloads in regulated industries

### Exadata Database Service on Exascale Infrastructure
- Versions: 19c, 26ai
- Shared managed infrastructure with virtual isolation
- Elastic: 1–10 node VM Cluster, up to 200 ECPU per VM
- Lower entry cost than dedicated; pay-per-use ECPUs
- Use case: mission-critical apps where shared infrastructure economics are acceptable

---

## GCP Network Topologies

GCP uses Cloud Router + Partner Interconnect automatically provisioned during ODB network creation. No additional routing configuration needed — all subnets in the VPC automatically have reachability to the ODB network (unlike AWS where routes must be manually added).

### 1. Single VPC
- Applications and database in same VPC with separate subnets for isolation
- Lowest latency, simplest setup
- Example: Sales subnet 192.168.1.0/24, HR subnet 172.16.0.0/24

### 2. VPC Peering
- Applications in one VPC/project, database in a separate project/VPC
- Enables centralized database service across lines of business
- Requires: VPC peering connection AND Cloud DNS peering zone (without DNS peering, hostnames won't resolve)
- Incurs VPC peering data transfer charges

### 3. Shared VPC
- Host project manages one centralized VPC; service projects deploy databases
- Recommended for organizations wanting centralized network control
- Benefits: consistent firewall policies, reduces VPC sprawl, delegates DB management to service project admins

### 4. Hub-and-Spoke with NVA
- Network Virtual Appliance (NVA) in transit VPC; multiple spokes connect through NVA NICs
- Provides centralized traffic inspection and security policy enforcement
- ODB network placed in transit VPC; NVA NIC1 connects to it; NIC2+ connect to spoke VPCs (Finance, Sales, etc.)

### 5. Multiple VPC
- Workload isolation at VM Cluster level
- Multiple VM Clusters on same Exadata Infrastructure, each connected to a different VPC/project
- Example: Marketing VPC and Sales VPC both using same physical Exadata Infrastructure

---

## GCP Resource Scope

Zonal resources (must be placed in a specific GCP Oracle Zone):
- Exadata Infrastructure, Exadata VM Clusters, ODB Networks, ODB Subnets, DB Systems

Regional resources (can run in any zone within the region):
- Oracle Autonomous Databases (ADB)

Oracle AI Database@GCP zones use format: `<region>-<zone>-r<number>` e.g. `us-east4-b-r1`

---

## GCP Subnet Limits
- Max 5 ODB subnets per ODB network (client and backup combined)
- Subnet CIDR: min /27, max /22, must be RFC1918
- CIDRs must not overlap with the associated VPC's existing subnets

---

## GCP DNS
- Cloud DNS private zone auto-provisioned when ODB network is created
- Exadata VM Clusters and Base DB: domain `oraclevcn.com`; FQDN: `<hostname>.<subnet_name>.oraclevcn.com`
- Autonomous AI Database (ADB): domains `oraclecloud.com` and `oraclecloudapps.com`
- When using VPC peering: must also create a Cloud DNS peering zone so the application VPC can resolve Oracle FQDNs

---

## GCP Migration tools supported
RMAN, Oracle Data Guard, Transportable Tablespaces, Oracle Data Pump, Oracle GoldenGate, Oracle Zero Downtime Migration (ZDM)
