# AWS Network Peering and Autonomous VM Cluster

## Network Peering (aws_odb_network_peering_connection)
Connects an ODB Network to a customer VPC, enabling database clients to reach Oracle DB.
Provisioning time: 15–30 minutes. Provision one at a time — wait for this resource to reach ACTIVE before starting the next. Concurrent, parallel or simultaneous applies are not supported. Full order: Exadata Infrastructure → ODB Network → ODB Peering → VM/AVM Cluster.

Required fields:
- display_name: e.g. "odb-peering-prod". Max 255 chars; letters/digits/underscores/hyphens; must start with letter/underscore; no consecutive hyphens.
- odb_network_id: wired from module.<network_module>.network_id.
- peer_network_id: the customer VPC ID to peer with. IMPORTANT: the correct Terraform argument name is peer_network_id — do not use peer_vpc_id (that is an AWS console term, not the Terraform argument).

Optional fields:
- peer_network_cidrs: set of CIDR blocks to restrict peering access to specific subnets (e.g. ["10.0.1.0/24", "10.0.2.0/24"]). Defaults to all VPC CIDRs if not set. Note: this field is update-only and cannot be set on initial creation; add after the peering resource exists.
- tags: map of string tags.
- region: AWS region string — informational, auto-derived.

Peering limits and constraints:
- Maximum 45 peering connections per ODB network.
- Only 1 ODB network peering per VPC (a VPC can connect to multiple ODB networks, but each ODB network can connect to a VPC only once).
- CIDR overlap not allowed between ODB subnets and VPC CIDRs.
- Supernet CIDR blocks (blocks that group multiple existing subnets) are not supported in peer_network_cidrs.
- Cross-account peering is supported — requires ODB network shared via AWS RAM.
- Cross-AZ peering is supported — VPC and ODB network can be in different AZs.
- Legacy networks created before February 7, 2026 in US East or US West cannot have more than one peering. The network must be recreated to support additional peerings.

Module outputs: peering_connection_id

Naming: module_name examples: odb_peering_prod, net_peering_dev, vpc_peer_hr

---

## Autonomous VM Cluster (aws_odb_cloud_autonomous_vm_cluster)
Hosts Oracle Autonomous Databases on Exadata Infrastructure. Use when running ADB-D instead of traditional CDB/PDB.
Provisioning time: 4+ hours.

Required fields:
- display_name: e.g. "odb-avmcluster-prod".
- cloud_exadata_infrastructure_id: wired from module.<infra>.infra_id.
- odb_network_id: wired from module.<network>.network_id.
- db_servers: list of DB server IDs from aws_odb_db_servers data source. Minimum 2 servers required (more than VM Cluster which needs minimum 1).
- autonomous_data_storage_size_in_tbs: storage for Autonomous DBs in TB. Minimum 1.
- cpu_core_count_per_node: CPU cores enabled per node.
- memory_per_oracle_compute_unit_in_gbs: memory per Oracle Compute Unit in GB. Typical value: 2.
- total_container_databases: maximum number of Autonomous Container Databases. Minimum 1.
- scan_listener_port_non_tls: SCAN port for non-TLS connections. Default 1521. Forbidden values: 808, 1522, 1525, 5000, 6100, 6200, 7060, 7070, 7879, 8181, 8888, 8895.
- scan_listener_port_tls: SCAN port for TLS connections. Default 2484. Same forbidden values as above.

Note: AVM cluster reserved ports differ from VM Cluster. VM Cluster forbids: 2484, 6100, 6200, 7060, 7070, 7085, 7879. AVM Cluster forbids: 808, 1522, 1525, 5000, 6100, 6200, 7060, 7070, 7879, 8181, 8888, 8895.

Optional fields:
- cloud_exadata_infrastructure_arn: ARN alternative to cloud_exadata_infrastructure_id — use for cross-account references.
- odb_network_arn: ARN alternative to odb_network_id — use for cross-account references.
- license_model: LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE. Default BRING_YOUR_OWN_LICENSE.
- is_mtls_enabled_vm_cluster: bool, enable mutual TLS authentication. Default false.
- description: free text, max 400 chars.
- time_zone: timezone string e.g. "UTC", "America/New_York". Default UTC.
- maintenance_window: preference (NO_PREFERENCE, CUSTOM_PREFERENCE), patching_mode (ROLLING, NON_ROLLING), plus optional schedule fields.
- tags: map of string tags.

Cross-account usage: when the Exadata Infrastructure or ODB Network are in a different AWS account, use the ARN fields (cloud_exadata_infrastructure_arn, odb_network_arn) instead of the ID fields.

Module outputs: avmc_id, avmc_arn

Naming: module_name examples: odb_avmcluster_prod, odb_avmc_dev
