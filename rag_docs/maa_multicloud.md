# Oracle Maximum Availability Architecture (MAA) for Multicloud

Source: Oracle Database 19c/26c High Availability Overview (haovw)
Covers: Oracle AI Database@AWS, Oracle AI Database@Azure, Oracle AI Database@Google Cloud

---

## MAA Tier Definitions

### MAA Silver
- Scope: HA database platform — configuration and lifecycle best practices
- Components: ExaDB-D cluster in multicloud partner's data center, redundant application tier across multiple AZs, Key Management Service (KMS), Autonomous Recovery Service (ARS), Object Storage Service (OSS) for backup/restore
- Capabilities: Database creation, elastic operations, software updates, backup and restore
- Application changes: None required
- Failure scope: Local failures only (no regional protection)
- Evaluation: 100s of unplanned outages simulation, RTO/RPO validation, zero downtime verification for elastic changes, exachk health checks

### MAA Gold
- Scope: Comprehensive data protection and disaster recovery with Oracle Active Data Guard standby database
- Components: All MAA Silver components + Oracle Active Data Guard standby ExaDB-D in same/separate AZ or different region
- Capabilities: Local and regional DR failover; auto block repair; reporting offload on standby
- Application changes: None required
- Regional failure protection: Only if standby resides in separate region from primary
- Data Guard Fast-Start Failover (FSFO) must be manually configured — NOT part of standard cloud automation

### MAA Platinum
- Scope: NeverDown option for any outage scenario
- Components: All MAA Gold + Oracle GoldenGate or OCI GoldenGate Marketplace; multiple logical GoldenGate replicas
- Capabilities: Route application to any available replica for any outage; continuous availability
- Application changes: Minimal (routing logic to avoid logical transaction conflicts)

---

## RTO/RPO Targets

| Outage Event | RTO | RPO |
|---|---|---|
| Localized events (storage, network, DB instance, DB server failures) | Near-zero | Zero |
| Restore from backup (no standby): data corruption, AZ failure | Minutes to hours | Near-zero with ARS + Real-Time Data Protection; 30 min without RTDP |
| Data Guard failover: any failure including regional | Seconds to minutes | Zero (SYNC redo); Near-zero (ASYNC redo) |

Notes:
- Validated workload for MAA Gold: up to 300 MB/second per Oracle RAC instance with near-zero standby lag
- Fast-Start Failover + Observer required for automatic failover (reduces RTO to seconds)

---

## Data Guard Configuration

### Redo Transport Modes
- SYNC (Maximum Availability protection mode): RPO = zero, requires RTT < 1ms preferred, impacts application throughput if RTT > 3ms
- ASYNC (Maximum Performance protection mode): RPO = near-zero, minimal application performance impact, default for cross-region (high RTT)

### Critical rule: single-process throughput
Data Guard redo transport is a single process per database instance. If redo generation rate exceeds single-process network bandwidth → transport lag accumulates → RPO degrades. Always ensure single-process throughput exceeds peak redo rate by 20%+.

### Fast-Start Failover (FSFO)
- Required for automatic failover (otherwise failover is manual)
- Requires Data Guard Observer on a separate VM
- Observer VM must be in a different location from both primary and standby (or at minimum in the application network)
- Manual configuration step — not automated by Oracle Cloud

### Data Guard role transitions
- Switchover (planned): application downtime 30 seconds to a few minutes
- Failover (primary unavailable): application downtime 30 seconds to a few minutes
- Console timing shown in OCI Console does NOT reflect actual database downtime
- Rolling database upgrade with Data Guard (near-zero downtime): use DBMS_ROLLING (Doc ID 2832235.1)

---

## Network Performance — AWS

Test regions: Ashburn VA ↔ Boardman OR (cross-region); same-region cross-AZ

### Cross-AZ (same region)
| Metric | OCI Peering | AWS Peering |
|---|---|---|
| RTT Latency | 1,700 µs | 2,200 µs |
| Single Process Throughput | 33 Gbps | 4.9 Gbps |
| Parallel (64 processes) | 90 Gbps | 45 Gbps |

### Cross-Region
| Metric | OCI Peering | AWS Peering |
|---|---|---|
| RTT Latency | 93 ms | 65 ms |
| Single Process Throughput | 1.3 Gbps | 0.7 Gbps |
| Parallel (64 processes) | 35 Gbps | 20 Gbps |

Recommendation: Use OCI VCN peering — higher single-process throughput critical for redo transport. First 10 TB/month free.

### AWS Backup/Restore Performance (2-node, 16+ OCPUs, 3 storage cells)
- Backup rate (baseline): 1.5 TB/hour (~40 MB/sec per RMAN channel)
- Restore rate (baseline): 2.2 TB/hour
- Optimized (more channels): 5 TB/hour backup, 7 TB/hour restore
- Restore scales: ~2 GB/sec per additional Exadata storage cell
- With Autonomous Recovery Service: effective backup rate 20+ TB/hour

### AWS-specific NSG rules for MAA
FAN (Fast Application Notification) — TCP port 6200 ingress from application CIDR — must be added to `exa_1521_adjustable_nsg` on VM Cluster client NSG.
ICMP ping (type 8) ingress from `exa_static_nsg` — required for VM OS updates via patchmgr — must be added to `exa_static_nsg`.

---

## Network Performance — Azure

Test environments: Cross-AZ within Ashburn VA; Cross-region Ashburn VA ↔ London UK

### Application VM to Exadata VM Cluster (same region)
- RTT Latency (same AZ): 300 µs
- RTT Latency (cross-AZ): 500 µs
- Use Azure Proximity Placement Groups to minimize latency
- Avoid network virtual appliances/firewalls in the data path

### Cross-AZ redo transport (London)
| Metric | OCI VCN Peering | Azure Global VNet |
|---|---|---|
| Latency | 1.2 ms | 1.2 ms |
| Single Process Throughput | 13 Gb/sec | 13 Gb/sec |
| Max Parallel Throughput (X11M) | 70 Gb/sec | 70 Gb/sec |

### Cross-Region redo transport (Ashburn ↔ London)
| Metric | OCI VCN Peering | Azure Global VNet |
|---|---|---|
| Latency | ~76 ms | ~76 ms |
| Single Process Throughput | 1.57 Gb/sec | 0.85 Gb/sec |
| Max Parallel Throughput (X11M) | 60 Gb/sec | 45 Gb/sec |

Recommendation: OCI VCN peering provides up to ~85% higher single-process throughput cross-region. Use Azure Global VNet only if redo rate is well below 0.85 Gb/sec.

### Azure Backup/Restore Performance
- Baseline (2-node, 16+ OCPUs, 3 storage cells): 4 TB/hour backup, 8.7 TB/hour restore
- With multiple RMAN channels: up to 42 TB/hour backup
- Autonomous Recovery Service@Azure: real-time data protection, incremental forever model

### Azure Data Guard network peering setup
- OCI Local Peering Gateways (LPG) for same-region cross-AZ
- Dynamic Routing Gateways (DRG) in each VCN for cross-region
- Route table updates require a support request (SR) with Oracle
- Separate VNet per VM Cluster with non-overlapping CIDR ranges
- If multiple databases use different standby clusters: hub VCN with transit routing required (one DRG per VCN max)

### Several VCN pairs on one cross-region hub (Terraflow Studio)
A cross-region Data Guard card builds the foundation once per region pair: a hub
(transit) VCN, a DRG and its hub attachment in each region, and one Remote Peering
Connection pair between the DRGs. **Additional VCN pairs** reuse that foundation —
adding a pair does not create another hub VCN, DRG or RPC.

- Each pair (a primary cluster VCN and its standby cluster VCN) gets, in each region:
  an LPG pair (hub side + cluster side), one rule in each hub route table, a route
  in its cluster VCN's default route table, and NSG ingress rules (1521, optionally 22).
- **Paired routing:** a cluster VCN routes to, and its NSG admits, only its own peer's
  client CIDR — never another pair's.
- **Limit:** each pair adds one LPG to each hub VCN; OCI allows **10 LPGs per VCN** by
  default, so one hub serves 10 pairs (the card's first pair plus 9) unless the limit
  is raised.
- Client CIDRs must not overlap on a side, and a primary CIDR must not overlap a
  standby CIDR.
- The card's own VCNs stay the first pair at their original Terraform addresses, so
  adding pairs to an applied configuration only adds resources; the hub route tables
  change in place.
- With Terraform-managed route tables, each extra pair's default route table must be
  imported, and its pre-existing rules go in that pair's
  `primary_existing_route_rules` / `dr_existing_route_rules` in `terraform.tfvars` —
  left empty, every other route in that table is removed.

---

## Network Performance — GCP

Test regions: Frankfurt, Germany ↔ London, England

### Application VM to Exadata VM Cluster
- RTT Latency: ~300 µs (same region/zone)
- Throughput: depends on VM shape (e.g. n2-standard-4 = 10 Gbps)
- For guaranteed close placement: file a Google support ticket

### Cross-region redo transport (FRA ↔ LHR)
| Processes | OCI VCN Peering | Google Cloud VPC Networking |
|---|---|---|
| 1 | 2.1 Gb/s | 2.7 Gb/s |
| 4 | 9.1 Gb/s | 8.3 Gb/s |
| 10 | 22.6 Gb/s | 11.4 Gb/s |

Critical GCP requirement: Cloud Interconnect VLAN attachments must be set to 10 Gbps bandwidth (default is 2 Gbps — file a Google support ticket to increase). Without this, multi-process throughput is severely limited.

GCP VPC Networking MTU: Must be set to jumbo frames (8896); default is 1460.

### GCP Data Guard networking options
Option 1 — Google Cloud VPC Networking: Both VM Clusters in same VPC network (different regions); no additional routing steps needed; MTU must be 8896; VLAN attachments must be 10 Gbps.
Option 2 — OCI VCN Peering: Each VM Cluster in its own OCI VCN; VCNs peered through hub VCNs. Consistent with OCI peering setup used in AWS/Azure.

Both options: Primary and standby client+backup subnet CIDR ranges must NOT overlap.

---

## Planned Maintenance Impact — Exadata Software Updates

| Update | Database Impact | Application Impact |
|---|---|---|
| Network Fabric Switches | Zero downtime | 0 to single-digit seconds brownout |
| Storage Servers | Zero downtime | 0 to single-digit seconds brownout |
| DB Host Monthly Security Maintenance | Zero downtime | Zero downtime |
| DB Host Quarterly Infrastructure Maintenance | Zero downtime (RAC rolling) | Zero downtime; reduced compute until done |
| Database Guest / DB Quarterly Update | Zero downtime (RAC rolling) | Zero downtime; reduced compute |
| Oracle GI Quarterly Update/Upgrade | Zero downtime (RAC rolling) | Zero downtime; reduced compute |
| Oracle DB Upgrade with Downtime | Minutes to hours | Minutes to hours |
| Oracle DB Upgrade Near-Zero Downtime | Minimal (DBMS_ROLLING, GoldenGate, or PDB relocate) | Minimal |

Exadata 21.2+: Storage server restarts maintain Persistent Storage Index, Persistent Columnar Cache, and smart flash for DB buffers. OLTP performance is preserved across restart.

---

## Planned Maintenance Impact — Elastic Operations

| Operation | Duration | Application Impact |
|---|---|---|
| Scale Up/Down Memory | 15-30 min per node | 0 to single-digit seconds brownout |
| Scale Up/Down CPU | < 5 min (10+ OCPU increase: ~10 min) | Zero downtime; CPU change affects performance |
| Resize ASM Storage | Minutes to hours (query GV$ASM_OPERATION every 30 min) | Zero downtime; minimal performance impact |
| Scale Up /u02 File System (X9M+) | < 5 min per cluster | Zero downtime |
| Scale Down /u02 File System (X9M+) | 15-30 min per node | 0 to single-digit seconds brownout |
| Add Exadata Storage Cells | 3-72 hours | 0 to single-digit seconds brownout |
| Add Exadata Database Servers | 1-6 hours per server | 0 to single-digit seconds brownout |
| Add/Drop Database Nodes | 3-6 hours add; 1-2 hours drop | 0 to single-digit seconds brownout |

Monitor ASM rebalance:
```sql
select operation, pass, state, sofar, est_work, est_minutes
from gv$asm_operation where operation='REBAL';
```

---

## Backup Strategy

Full backup: weekly. Incremental: all other days. Archived log backup: every 30 minutes (default).
Backup targets: Autonomous Recovery Service (Azure, GCP, OCI); Object Storage (OCI); S3 (AWS).
RMAN validates backups for physical corruptions.

### Autonomous Recovery Service (recommended over S3/OSS)
- Incremental-forever model (eliminates weekly full backup overhead)
- Real-Time Data Protection: near-zero data loss on restore
- Policy-driven lifecycle management
- Malware protection, long-term retention, built-in HA

---

## Service Drain Timeout (DRAIN_TIMEOUT) Reference

| Event | DRAIN_TIMEOUT default | MAX_DRAIN_TIMEOUT default | Oracle Cloud Max |
|---|---|---|---|
| DB Guest VM OS update | 180 s | 300 s | 500 s |
| /u02 Scale Down (X9M+) | 180 s | 300 s | 300 s |
| Memory Scale Up/Down (X9M+) | 180 s | 300 s | 900 s |
| DB Home patch / DB move | Honored from service | — | 2 hours |
| GI patch / GI upgrade | Honored from service | — | 2 hours |

For drains longer than Oracle Cloud internal maximums: use Enhanced Infrastructure Maintenance Controls (suspend maintenance, manually stop/relocate services, then resume).

---

## Application Continuity Best Practices

- Use Oracle Clusterware-managed database services; role-based services for Data Guard environments
- Connection strings: include built-in timeouts, retries, delays
- Enable Fast Application Notification (FAN) — requires TCP port 6200 open from app subnet
- Use Application Continuity (AC) or Transparent Application Continuity (TAC) to replay in-flight uncommitted transactions after failures
- Long-running batch jobs may not drain within max timeout — schedule maintenance outside batch windows
- Validate app failover readiness: My Oracle Support Doc ID 2758734.1

---

## Network Test Quick Reference

Minimum throughput thresholds:
- Single process: ≥ 2.4 Gb/sec (300 MB/sec) — must exceed peak database redo rate by 20%+
- Multi-process (16 parallel): ≥ 8 Gb/sec (1000 MB/sec)
- RTT for SYNC redo transport: < 1 ms preferred; > 3 ms causes application impact

Tools (pre-installed on Exadata):
- iperf3 (throughput, port 5201): `iperf3 -s` on server; `iperf3 -c <VIP>` on client; `-P 4/10/16` for parallel
- qperf (latency, port 5201): `qperf -lp 5201` on server; `qperf <IP> -lp 5201 tcp_lat` on client — run both directions, sum for RTT

Port 5201 must be open for ingress/egress in OCI VCN security rules before testing.

---

## Key Support Doc IDs
- 2217053.1 — OJVM rolling DB quarterly update considerations
- 2371860.1 — RMAN nettest details
- 2385790.1 — Service drain timeout settings
- 2628228.1 — DB upgrade with Data Guard/standby
- 2701789.1 — DB home patch + out-of-place DB move with Data Guard
- 2758734.1 — Validating Application Failover Readiness
- 2832235.1 — DB upgrade near-zero downtime with DBMS_ROLLING
