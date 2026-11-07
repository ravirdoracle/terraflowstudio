# Example Configurations

## AWS production single environment
1 ODB Network + 1 Exadata Infra (X11M, 2 compute, 3 storage) + 1 VM Cluster + OCI Database

module_names: odb_network_prod, odb_exaInfra_prod, odb_vmcluster_prod, oci_database_prod
cpu_core_count: 16, gi_version: 23.0.0.0.0, data_storage_size_in_tbs: 4
license_model: LICENSE_INCLUDED, is_local_backup_enabled: true
OCI DB: db_name ORCL, pdb_name PROD, auto_backup_enabled: true

## AWS dev/test environment (minimal cost)
module_names: odb_network_dev, odb_exaInfra_dev, odb_vmcluster_dev
cpu_core_count: 4, gi_version: 23.0.0.0.0, data_storage_size_in_tbs: 2
is_sparse_diskgroup_enabled: true (reduces storage consumption for dev)
is_local_backup_enabled: false, patching_mode: NON_ROLLING

## AWS multi-environment (prod + nonprod sharing one infra)
ODB Network: odb_network_shared
Exadata Infra: odb_infra_shared (4 compute, 6 storage, X11M)
VM Cluster 1: odb_vmcluster_prod (infra_ref: odb_infra_shared, cpu_core_count: 24)
VM Cluster 2: odb_vmcluster_nonprod (infra_ref: odb_infra_shared, cpu_core_count: 8)
Both clusters use the same infra and network.

## AWS multi-environment with separate infras
ODB Network: odb_network_prod
ODB Network: odb_network_nonprod
Exadata Infra: odb_infra_prod (2 compute, 3 storage)
Exadata Infra: odb_infra_nonprod (2 compute, 3 storage)
VM Cluster: odb_vmcluster_prod (network_ref: odb_network_prod, infra_ref: odb_infra_prod)
VM Cluster: odb_vmcluster_nonprod (network_ref: odb_network_nonprod, infra_ref: odb_infra_nonprod)

## AWS with VPC peering
Add a Network Peering per ODB Network to connect to the application VPC.
module_name: odb_peering_prod, network_ref: odb_network_prod

## GCP production setup
gcp_project: my-project-id, gcp_region: us-east4
ODB Network: gcp_odb_net_prod
Exadata Infra: gcp_infra_prod (X11M, 2 compute, 3 storage)
VM Cluster: gcp_vmcluster_prod (google_oracle_database_cloud_vm_cluster, gi_version "23.0.0.0")
network_ref, client_subnet_ref, backup_subnet_ref, infra_ref auto-wired by root module.

## GCP Exascale setup (no Exadata Infrastructure)
ODB Network: gcp_odb_net_prod (purpose "both" or "dedicated" — it needs the backup subnet)
Exascale storage vault: gcp_xs_vault (total_size_gbs 300+, zone us-east4-a-r1)
Exascale VM Cluster: gcp_xs_cluster (google_oracle_database_exadb_vm_cluster)
  vault_key: "gcp_xs_vault"
  grid_image_id: "ocid1.dbpatch.oc1..<from the OCI Console>"
  shape_attribute: "SMART_STORAGE" (26ai+) or "BLOCK_STORAGE" (19c)
  node_count: 2, enabled_ecpu_count_per_node: 8, vm_file_system_size_gbs_per_node: 220
Note: Exascale takes grid_image_id, not gi_version; hashicorp/google >= 7.20.0.

## Financial services high-availability AWS
Two Exadata Infras in different AZs, two VM Clusters.
odb_infra_primary: availability_zone_id: use1-az4
odb_infra_standby: availability_zone_id: use1-az6
odb_vmcluster_primary: infra_ref: odb_infra_primary, cpu_core_count: 32
odb_vmcluster_standby: infra_ref: odb_infra_standby, cpu_core_count: 32
Use Data Guard (OCI-level) to replicate between primary and standby.

## Autonomous VM Cluster (AWS)
Use when running Oracle Autonomous Databases instead of traditional Oracle DB.
module_name: odb_avmcluster_prod
autonomous_data_storage_size_in_tbs: 10
cpu_core_count_per_node: 8
total_container_databases: 4
memory_per_oracle_compute_unit_in_gbs: 2
