# Oracle AI DB@AWS — Gotchas, Immutable Fields, and Provisioning Notes

## Provisioning times
- aws_odb_network: ~4 hours
- aws_odb_cloud_exadata_infrastructure: 15–30 minutes
- aws_odb_cloud_vm_cluster: 4–6 hours (set create timeout to "24h")
- aws_odb_cloud_autonomous_vm_cluster: 4+ hours
- aws_odb_network_peering_connection: 15–30 minutes
- aws_odb_autonomous_database (Serverless): can take several hours (provider default timeouts 24h)
- aws_odb_autonomous_database_secrets_manager_integration: up to 15 minutes

## Deployment order and concurrency (creation order, deploy sequence)

Deploy in this order:

1. **aws_odb_cloud_exadata_infrastructure** — references nothing else in the configuration, so it goes first
2. **aws_odb_network**
3. **aws_odb_network_peering_connection** — needs its ODB Network
4. **aws_odb_cloud_vm_cluster / aws_odb_cloud_autonomous_vm_cluster** — need both the infrastructure and the network
5. **aws_odb_autonomous_database_secrets_manager_integration** — only if a database reads its ADMIN password from Secrets Manager; one per account and Region
6. **aws_odb_autonomous_database** (Serverless) — needs only its ODB Network; no Exadata Infrastructure or VM cluster

Run them **one resource at a time, sequentially**. Wait for each resource to reach
ACTIVE before starting the next one. Two Exadata Infrastructures means two separate
applies, not one — do not create them simultaneously, in parallel, or at the same time.
Concurrent or parallel applies are not supported for ODB@AWS provisioning.

Because the generated configuration uses `for_each` modules, a bare `terraform apply`
would start every instance concurrently. Target one instance per apply instead:

```bash
terraform apply -target='module.aws_exadata_infra["infra_1"]'
terraform apply -target='module.aws_odb_network["net_1"]'
terraform apply -target='module.aws_peering["peer_1"]'
terraform apply -target='module.aws_vm_cluster["cluster_1"]'
terraform apply -target='module.aws_autonomous_db["adb_1"]'
```

## IMMUTABLE settings (cannot change after creation — destroy/recreate required)
- aws_odb_cloud_vm_cluster: cluster_name, is_sparse_diskgroup_enabled, is_local_backup_enabled
- aws_odb_network: availability_zone_id (changing AZ requires full network recreate)
- aws_odb_cloud_exadata_infrastructure: shape, availability_zone_id
- aws_odb_autonomous_database: odb_network_id, character_set, ncharacter_set (and source / source_configuration once set)

## CIDR validation rules (aws_odb_network)
- client_subnet_cidr minimum size: /27 (32 IPs). Recommended /24.
- backup_subnet_cidr minimum size: /28 (16 IPs). Recommended /24.
- Forbidden CIDR ranges: 100.64.0.0/10 (cluster interconnect), 169.254.0.0/16 (OCI link-local), 224.0.0.0/4 and above (multicast/reserved).
- CIDRs must not overlap each other, the VPC CIDR, or on-premises networks via Transit Gateway or Cloud WAN.
- Supernet blocks (blocks covering multiple existing subnets) are rejected in peering configurations.

## DNS prefix — hyphen causes VM Cluster failure
If you set default_dns_prefix on an aws_odb_network, do NOT include hyphens in the value.
Hyphens in default_dns_prefix cause aws_odb_cloud_vm_cluster creation to fail silently.
Use alphanumeric prefixes only: "prod", "dev1", "hr" — not "prod-db" or "us-east".

## SSH keys must be RSA format
aws_odb_cloud_vm_cluster ssh_public_keys must be RSA keys. ed25519 keys are not supported.
Generate with: ssh-keygen -t rsa -b 4096 -f vm-cluster-key -N ""

## db_servers must come from data source
Both aws_odb_cloud_vm_cluster and aws_odb_cloud_autonomous_vm_cluster require db_servers.
Get the IDs from the data source after infrastructure is created:
  data "aws_odb_db_servers" "this" {
    cloud_exadata_infrastructure_id = module.<infra>.infra_id
  }
Then reference: data.aws_odb_db_servers.this.db_server_ids
AVM Cluster requires minimum 2 db_servers. VM Cluster requires minimum 1.

## Patching mode values — NON_ROLLING not NONROLLING
The correct Terraform value for the patching mode is NON_ROLLING (with underscore between NON and ROLLING).
Using NONROLLING will cause a provider validation error.
Valid values: ROLLING, NON_ROLLING.

## peer_network_id vs peer_vpc_id
In aws_odb_network_peering_connection, the Terraform argument is peer_network_id.
The AWS console and some Oracle docs use the term "peer_vpc_id" — this is the same thing but the Terraform argument name is peer_network_id.

## peer_network_cidrs is update-only
peer_network_cidrs cannot be set during initial creation of aws_odb_network_peering_connection.
Create the resource first, then add peer_network_cidrs in a subsequent apply.

## Legacy network peering limit (pre-February 7, 2026)
Networks created before February 7, 2026 in US East or US West can only have one peering connection.
To add more peerings, the ODB network must be destroyed and recreated.

## Reserved SCAN listener ports
VM Cluster (aws_odb_cloud_vm_cluster) — cannot use: 2484, 6100, 6200, 7060, 7070, 7085, 7879
AVM Cluster (aws_odb_cloud_autonomous_vm_cluster) — cannot use: 808, 1522, 1525, 5000, 6100, 6200, 7060, 7070, 7879, 8181, 8888, 8895
Default: non-TLS port 1521, TLS port 2484.

## NSG quota
If peering creation fails with a quota error, request an OCI quota increase for:
securityrules-per-networksecuritygroup-count
