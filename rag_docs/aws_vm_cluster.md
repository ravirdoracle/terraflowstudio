# AWS VM Cluster (aws_odb_cloud_vm_cluster)

The VM Cluster runs Oracle Database on top of Exadata Infrastructure.
Provisioning time: 4–6 hours. Provision one at a time — wait for this resource to reach ACTIVE before starting the next. Concurrent, parallel or simultaneous applies are not supported. Full order: Exadata Infrastructure → ODB Network → ODB Peering → VM/AVM Cluster. Set Terraform timeouts accordingly (create = "24h").
Terraform provider: hashicorp/aws version 6.42.0+

## Required fields
- display_name: e.g. "odb-vmcluster-prod". Max 255 chars; letters/digits/underscores/hyphens; must start with letter or underscore.
- cpu_core_count: number of OCPUs allocated. Minimum 2, typical values 4, 8, 16, 32, 64.
- gi_version: Grid Infrastructure version. Values: "19.0.0.0.0", "21.0.0.0.0", "23.0.0.0.0" (latest, recommended for new clusters). Use "23.0.0.0" not "23.0.0.0.0" for the aws provider field.
- hostname_prefix: lowercase alphanumeric prefix for node hostnames, max ~12 chars. e.g. "exa-prod", "vmc-hr".
- license_model: LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE.
- cloud_exadata_infrastructure_id: wired from module.<infra_module>.infra_id.
- odb_network_id: wired from module.<network_module>.network_id.
- db_servers: list of DB server IDs from aws_odb_db_servers data source. Required to pin cluster to specific servers. Get via: data.aws_odb_db_servers.<name>.db_server_ids.
- ssh_public_keys: list of RSA SSH public key strings. Must be RSA format (.pub from ssh-keygen -t rsa). Multiple keys supported.
- memory_size_in_gbs: total memory allocated in GB. Required. Minimum depends on infra shape; typical: 60–240.
- data_storage_size_in_tbs: total Exadata data storage in TB. Required. Minimum 2 TB.
- db_node_storage_size_in_gbs: local node storage per node in GB. Required. Typical: 120–900.
- data_collection_options block: is_diagnostics_events_enabled, is_health_monitoring_enabled, is_incident_logs_enabled (all bool, default true).

## Optional fields
- cluster_name: GI cluster name. Max 11 chars; letters/digits/underscores/hyphens; must start with letter/underscore. IMMUTABLE after creation — choose carefully.
- timezone: timezone string, e.g. "UTC", "America/New_York", "Asia/Tokyo". Default UTC.
- scan_listener_port_tcp: SCAN listener TCP port. Default 1521. Valid range 1024–8999. Forbidden values: 2484, 6100, 6200, 7060, 7070, 7085, 7879.
- is_local_backup_enabled: bool, enables local Exadata storage backups. Default false. IMMUTABLE after creation.
- is_sparse_diskgroup_enabled: bool, sparse disk group (reduces storage for dev/test). Default false. IMMUTABLE after creation.
- tags: map of string tags.

## IMMUTABLE settings — set correctly before apply
These cannot be changed after the cluster is created. A destroy-and-recreate is required to change them:
- cluster_name
- is_sparse_diskgroup_enabled
- is_local_backup_enabled

## Terraform example (full)
```hcl
resource "aws_odb_cloud_vm_cluster" "this" {
  cloud_exadata_infrastructure_id = aws_odb_cloud_exadata_infrastructure.this.id
  cpu_core_count                  = 16
  db_servers                      = data.aws_odb_db_servers.this.db_server_ids
  display_name                    = "tf-vmc-prod"
  gi_version                      = "23.0.0.0"
  hostname_prefix                 = "vm"
  odb_network_id                  = local.odb_network_id
  ssh_public_keys                 = [file("~/.ssh/demo-ssh-key.pub")]
  memory_size_in_gbs              = 60
  data_storage_size_in_tbs        = 2
  db_node_storage_size_in_gbs     = 120
  license_model                   = "BRING_YOUR_OWN_LICENSE"

  data_collection_options {
    is_diagnostics_events_enabled = true
    is_health_monitoring_enabled  = true
    is_incident_logs_enabled      = true
  }

  # Optional
  cluster_name                = "gic-prod"   # max 11 chars, IMMUTABLE
  scan_listener_port_tcp      = 1521
  timezone                    = "UTC"
  is_local_backup_enabled     = false
  is_sparse_diskgroup_enabled = false

  tags = {
    created_via = "terraform"
    env         = "prod"
  }

  timeouts {
    create = "24h"
    update = "2h"
    delete = "8h"
  }
}

output "oci_cloud_vm_cluster_ocid" {
  value = aws_odb_cloud_vm_cluster.this.ocid
}
```

## SSH key requirements
Keys must be RSA format. Generate with:
```bash
ssh-keygen -t rsa -b 4096 -f vm-cluster-key -N ""
```
The public key content (.pub file) goes in ssh_public_keys.

## Module outputs
- vm_cluster_id: used as cloud_vm_cluster_id in OCI DB Home resources
- ocid: Oracle Cloud ID, used by OCI DB Home resources

## Naming
module_name examples: odb_vmcluster_prod, odb_vmcluster_nonprod, odb_vmc_hr

## Infra and network wiring
The root main.tf wires:
  cloud_exadata_infrastructure_id = module.<infra_ref>.infra_id
  odb_network_id = module.<network_ref>.network_id
Set infra_ref and network_ref to the module_name of the corresponding infrastructure and network.

## License model guidance
- LICENSE_INCLUDED: Oracle manages licensing as part of the service cost (higher hourly rate)
- BRING_YOUR_OWN_LICENSE: use existing Oracle licenses (lower hourly cost — most common for enterprises)
