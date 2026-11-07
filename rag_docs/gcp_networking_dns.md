# Oracle AI DB@GCP — Networking Topologies, IP Sizing, and DNS

## ODB Network overview
The ODB network creates a metadata construct for a Google VPC, centralising network configuration (subnets, routing) for Oracle AI Database@GCP. It maps OCI network resources back to Google Cloud and supports both Standalone VPC and Shared VPC. Up to 5 non-overlapping ODB Subnets can be created per ODB network. CIDR ranges for ODB subnets must not conflict with existing CIDR ranges in the associated VPC.

---

## Client Subnet CIDR requirements

Minimum /27, Maximum /22. Must be RFC1918 (10.0.0.0/8, 172.16.0.0/12, or 192.168.0.0/16).

IP consumption formula:
- 3 IPs: fixed service overhead (2 at start of CIDR + 1 at end, reserved regardless of cluster count)
- 3 IPs per VM cluster: reserved for SCAN (Single Client Access Name) listeners
- 4 IPs per VM node
- 1 IP per Autonomous AI Database instance
- 1 IP per Base Database VM

Examples:
- 1 cluster × 2 VMs = 3 + 3 + 8 = 14 IPs → minimum /27 (32 IPs)
- 1 cluster × 4 VMs = 3 + 3 + 16 = 22 IPs → minimum /27 (32 IPs)
- 1 cluster × 8 VMs = 3 + 3 + 32 = 38 IPs → minimum /26 (64 IPs)

Capacity planning — max VM clusters (2-VM) per CIDR size:

| Cluster config (IPs per cluster) | /27 | /26 | /25 | /24 | /23 | /22 |
|---|---|---|---|---|---|---|
| 1 cluster × 2 VMs (11 IPs) | 2 | 5 | 11 | 23 | 46 | 92 |
| 1 cluster × 3 VMs (15 IPs) | 1 | 4 | 8 | 16 | 33 | 68 |
| 1 cluster × 4 VMs (19 IPs) | 1 | 3 | 6 | 13 | 26 | 53 |

Recommendation: use at least /24 for the client subnet to allow future expansion.

---

## Backup Subnet CIDR requirements

Minimum /27, Maximum /22. Must be RFC1918.

NOTE: GCP backup subnet minimum is /27 — this differs from AWS where backup minimum is /28.

IP consumption formula:
- 3 IPs: fixed service overhead (2 at start + 1 at end)
- 3 IPs per VM node (minimum 2 VMs per cluster = 6 IPs)

Examples:
- 1 cluster × 2 VMs = 3 + 6 = 9 IPs → minimum /27 (note: /28 is not allowed on GCP)
- 1 cluster × 4 VMs = 3 + 12 = 15 IPs → minimum /27
- 1 cluster × 8 VMs = 3 + 24 = 27 IPs → minimum /27

Capacity planning — max VM clusters per CIDR size:

| Cluster config (IPs per cluster) | /27 | /26 | /25 | /24 | /23 | /22 |
|---|---|---|---|---|---|---|
| 1 cluster × 2 VMs (6 IPs) | 4 | 10 | 20 | 42 | 84 | 170 |
| 1 cluster × 3 VMs (9 IPs) | 3 | 6 | 13 | 28 | 56 | 113 |
| 1 cluster × 4 VMs (12 IPs) | 2 | 5 | 10 | 21 | 42 | 85 |

---

## Combined client + backup sizing reference

| Configuration | Client IPs | Client min CIDR | Backup IPs | Backup min CIDR |
|---|---|---|---|---|
| 1 cluster × 2 VMs | 14 | /27 | 9 | /27 |
| 1 cluster × 3 VMs | 18 | /27 | 12 | /27 |
| 1 cluster × 4 VMs | 22 | /27 | 15 | /27 |
| 1 cluster × 8 VMs | 38 | /26 | 27 | /27 |

---

## Forbidden and restricted IP ranges

- 100.64.0.0/10: reserved for Exadata X9M and X11M cluster interconnect — MUST NOT be used for client or backup subnets or database client networks
- Non-RFC1918 addresses: not supported for ODB subnets
- Overlapping CIDRs: client and backup subnets must not overlap each other or any existing VPC subnet CIDR in the same region
- Cross-region routing: consider cross-region CIDR conflicts when planning addresses

---

## Network topology patterns

### 1. Single VPC (recommended for low latency)
Applications hosted in the same VPC as the ODB network. Use separate subnets within the VPC for application isolation (e.g. sales app in 192.168.1.0/24, HR app in 172.16.0.0/24). Best latency and simplest configuration.

### 2. VPC Peering
Different projects/teams host applications in separate VPCs; connect to database in a dedicated VPC/project via VPC peering. VPC peering works within same project, across projects in same org, or across organisations. DNS peering zone required alongside VPC peering for hostname resolution. Note: VPC peering incurs costs.

### 3. Shared VPC (Hub project model)
Organisation hosts a Shared VPC in a Host project. Service projects attach to the Shared VPC and deploy databases into it. Central control over networking policies (firewall, routes, DNS) while granting controlled access to service project teams. Avoids VPC sprawl and manual peering setup. Supports both standalone and shared VPC modes on ODB network.

### 4. Hub-and-Spoke (NVA transit)
A Network Virtual Appliance (NVA) with multiple VNICs acts as centralized connectivity point. Spoke VPCs (Finance, Sales, etc.) connect to a transit VPC via the NVA. ODB network connects to the transit VPC. The NVA subnet in the transit VPC must be created before ODB network deployment. Use case: traffic inspection, centralised security controls.

### 5. Multiple VPCs (workload isolation)
Multiple VM clusters each connected to different VPCs/projects. Isolates database workloads per business unit at the VM Cluster level. Multiple VM clusters can share the same Exadata Infrastructure while connecting to entirely separate VPCs. Exadata Infrastructure and VM Cluster can belong to different GCP projects — select the infrastructure project during VM Cluster creation.

---

## DNS architecture

### Domain name mappings
- `*.oraclevcn.com` — ExaDB VM clusters and Base Database
- `*.oraclecloud.com` and `*.oraclecloudapps.com` — Autonomous AI Database (ADB)

### Google Cloud side: Cloud DNS forwarding
A private Cloud DNS zone is automatically deployed in the GCP project and associated with the ODB network's VPC. Forwarding rules direct queries for Oracle-managed domains (*.oraclevcn.com etc.) to the OCI DNS Listener IP provisioned during ODB network creation. Any query from the GCP VPC for a database FQDN is forwarded to OCI and resolved there.

### OCI side: automatically provisioned DNS components
These are created automatically — no user configuration required:
1. DNS Resolver — one per VCN, enables internal DNS resolution
2. Private DNS View — default view created and managed by the resolver
3. Private DNS Zones — one per subnet (client and backup) in the VCN
4. DNS Listener Endpoint — provisioned per VCN; its IP is allocated inside the client subnet
   - Governed by an automatically created NSG rule controlling ingress IPs and ports
   - One listener can be shared across all DB attachments in a VCN
   - IMPORTANT: the client subnet that holds the listener IP cannot be deleted or reallocated until all associated resources (DB attachments) are removed first

### Additional DNS options
- Create a GCP DNS peering zone to share DNS zones from one project/VPC to others
- Configure OCI-to-GCP DNS forwarding to resolve non-OCI domain names from database hosts

---

## Key GCP vs AWS networking differences

| Topic | GCP | AWS |
|---|---|---|
| Subnet minimum (client) | /27 | /27 |
| Subnet minimum (backup) | /27 | /28 |
| Subnet maximum | /22 | /16 |
| Max subnets per ODB network | 5 | 2 (client + backup fixed) |
| Peering mechanism | GCP VPC Peering or Shared VPC | ODB Peering Connection |
| DNS listener location | client subnet IP | client subnet IP |
| Reserved range | 100.64.0.0/10 | 100.64.0.0/10 |
| Topology with central hub | NVA hub-and-spoke | Transit Gateway |
