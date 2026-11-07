# AWS ODB Network (aws_odb_network)

The ODB Network is the virtual network container required by all ODB@AWS resources.
Every Exadata Infrastructure and VM Cluster must reference an ODB Network.
Provisioning time: ~4 hours. Provision one at a time — wait for this resource to reach ACTIVE before starting the next. Concurrent, parallel or simultaneous applies are not supported. Full order: Exadata Infrastructure → ODB Network → ODB Peering → VM/AVM Cluster.

## Required fields
- display_name: human-readable name, e.g. "odb-network-prod". Max 255 chars; letters/digits/underscores/hyphens; must start with letter or underscore; no consecutive hyphens.
- availability_zone_id: AZ ID where the network is located, e.g. "use1-az4", "use1-az6", "usw2-az3". Use AZ IDs (not AZ names) — AZ IDs are consistent across accounts.
- client_subnet_cidr: CIDR block for the client subnet (Oracle Net traffic from clients to DB). Minimum /27 (32 IPs). Recommended /24 for room to grow. Example: "10.2.0.0/24".
- backup_subnet_cidr: CIDR block for the backup subnet (RMAN backup traffic). Minimum /28 (16 IPs). Recommended /24. Example: "10.2.1.0/24".

## Optional fields
- s3_access: ENABLED or DISABLED. Controls whether Oracle DB nodes can access Amazon S3 directly for data loading, exports, and self-managed backups. Default DISABLED. Set to ENABLED if using S3-based backups. Required by the provider — always emitted.
- zero_etl_access: ENABLED or DISABLED. Enables Oracle-to-Redshift Zero-ETL replication. Default DISABLED. Required by the provider — always emitted.
- sts_access: ENABLED or DISABLED. Lets the Oracle DB nodes reach AWS STS to assume IAM roles — the usual prerequisite for anything on the DB nodes that calls an AWS API with temporary credentials. Optional + Computed, so leaving it unset accepts whatever the service assigns and does not produce plan drift.
- kms_access: ENABLED or DISABLED. Lets the DB nodes reach AWS KMS, for customer-managed keys. Optional + Computed, same semantics as sts_access.
- s3_policy_document: VPC endpoint policy (JSON) scoping what the S3 endpoint permits. Leave unset for the default full-access endpoint policy.
- sts_policy_document: VPC endpoint policy (JSON) for the STS endpoint. Only has effect when sts_access is ENABLED.
- kms_policy_document: VPC endpoint policy (JSON) for the KMS endpoint. Only has effect when kms_access is ENABLED.
- cross_region_s3_restore_sources_access: set of AWS region names (e.g. ["us-east-1", "eu-west-1"]) this ODB network may restore S3 backups from. Requires s3_access = ENABLED.

## Service access: which flags are Required and which are Computed
Four service-access flags exist on aws_odb_network and they do NOT behave the same way:
- s3_access and zero_etl_access are Required. They are always present in the configuration, and omitting them is a provider error.
- sts_access and kms_access are Optional + Computed. Omitted, each adopts the status the service assigned and does not diff against the configuration, so there is no need for a lifecycle ignore_changes guard on them. Send null rather than an empty string when unset — "" is not a valid status.

Each of the three endpoint policies (s3, sts, kms) is only meaningful alongside its access flag. An endpoint policy set while its access flag is DISABLED is inert, and Terraflow Studio rejects that combination at validation time rather than letting it reach apply.
- availability_zone: AZ name (e.g. "us-east-1a") — informational only; auto-derived from availability_zone_id. Optional.
- region: AWS region string, e.g. "us-east-1" — informational only. Optional.
- delete_associated_resources: bool — when true, deleting the network also destroys associated subnets and peerings. Default false.
- tags: map of string tags, e.g. {"Env" = "prod", "Team" = "dba"}.

## DNS: custom_domain_name vs default_dns_prefix
These two fields are mutually exclusive — use one or the other, never both:
- default_dns_prefix: 1–15 alphanumeric chars, must start with letter. IMPORTANT: do NOT use hyphens — hyphens in default_dns_prefix cause VM Cluster creation to fail.
- custom_domain_name: fully qualified custom domain (e.g. "db.internal.example.com") — for organisations that manage DNS centrally.
If neither is set, the provider assigns a system-generated prefix.

## CIDR constraints and forbidden ranges
- client_subnet_cidr and backup_subnet_cidr must NOT overlap each other.
- ODB subnet CIDRs must NOT overlap the customer VPC CIDRs in the same region.
- ODB subnet CIDRs must NOT overlap on-premises networks reachable via AWS Transit Gateway or Cloud WAN.
- Forbidden ranges (will be rejected): 100.64.0.0/10 (cluster interconnect), 169.254.0.0/16 (OCI reserved), 224.0.0.0–255.255.255.255 (Class D/E multicast).
- Supernet blocks that group multiple existing subnets are not allowed in peered configurations.
- Client subnet: min /27 (32 IPs), max /16. Backup subnet: min /28 (16 IPs), max /16.

## IP consumption (for capacity planning)
Fixed overhead per ODB network: 6 IPs on client subnet, 3 IPs on backup subnet.
Per VM Cluster: 3 IPs (SCANs) on client subnet.
Per VM node: 4 IPs on client subnet, 3 IPs on backup subnet.
Plus 1 mandatory OCI DNS Listening Endpoint IP on client subnet.

| Config | Client IPs used | Min client CIDR | Backup IPs used | Min backup CIDR |
|---|---|---|---|---|
| 1 cluster / 2 VMs | 18 | /27 | 9 | /28 |
| 1 cluster / 4 VMs | 26 | /27 | 15 | /28 |
| 1 cluster / 8 VMs | 42 | /26 | 27 | /27 |
| 2 clusters / 4 VMs each | 44 | /26 | 27 | /27 |

For /24 subnets: supports up to ~15 clusters of 2-VM each (client), ~28 clusters of 2-VM each (backup).

## Limits
- ODB Peering Connections per ODB network: 45

## Oracle-managed Network Security Groups (NSGs)
Created automatically; do NOT delete or override static NSGs.

| NSG | Purpose | Key ports |
|---|---|---|
| EXA_STATIC_NSG | Intra-cluster Exadata communication | All TCP/ICMP within client+backup subnets |
| EXA_1521_ADJUSTABLE_NSG | App connectivity to Exadata | 1521 (SQL*Net), 2484 (SSL) inbound from app subnet |
| EXA_BACKUP_STATIC_NSG | RMAN backup, Recovery Service | 22 (SSH), 443 (OCI Object Storage) |
| EXA_BACKUP_ADJUSTABLE_NSG | Cross-cloud S3 backups | 443 egress to S3 |
| ADB_STATIC_NSG | Autonomous DB system communication | All TCP/ICMP within client subnet |
| ADB_1521_2484_ADJUSTABLE_NSG | App connectivity to ADB | 1521, 2484, 443 (APEX), 6200 (ONS/FAN) |
| DNS_NSG | DNS resolution | 53 TCP/UDP from app subnet |
| ZRCV_NSG | Zero Data Loss Recovery Service | 2484, 8005 from backup static NSG |

Adjustable NSGs default to allowing access from all peered CIDRs. For stricter control, create customer-managed NSGs, attach them to VM clusters, and detach the adjustable ones.
Static NSGs (EXA_STATIC_NSG, ADB_STATIC_NSG, EXA_BACKUP_STATIC_NSG) must never be modified — Oracle automation will revert changes during updates.

## Module outputs
- network_id: used as odb_network_id in VM clusters and peerings
- network_arn: ARN for cross-account references (used as odb_network_arn)
- network_name: display name

## Naming conventions
module_name examples: odb_network_prod, odb_net_dev, odb_network_nonprod, vpc_odb_hr
Use snake_case, keep it short and environment-specific.

## Relationships
One ODB Network can support multiple Exadata Infrastructures and VM Clusters.
Network Peering (aws_odb_network_peering_connection) connects an ODB Network to a customer VPC.
Each VM Cluster references the ODB Network via odb_network_id (from module.<network>.network_id).

## Typical setup
For each environment (prod, nonprod, dev) create one ODB Network.
All Exadata Infrastructures and VM Clusters in that environment share the same ODB Network.
Example: client_subnet_cidr="10.2.0.0/24", backup_subnet_cidr="10.2.1.0/24", s3_access="ENABLED", zero_etl_access="DISABLED"

## Important gotchas
- ODB networks created BEFORE February 7, 2026 in US East (N. Virginia) or US West (Oregon) must be fully recreated before adding ODB Peering. If you have >1 peering, recreate the ODB network first.
- hyphens in default_dns_prefix cause VM Cluster creation to fail — use alphanumeric only.
- AWS Placement Groups are auto-created after ODB network setup; use these for EC2 high-performance networking.
