# Oracle AI Database@Azure — Network Anchor Design, Subnet, DNS & Topologies

Source: Oracle Cloud Infrastructure Documentation — database-at-azure networking section

---

## Anchors Overview

Anchors are constructs that logically bind Azure resources to OCI resources, enabling multicloud deployments with consistent billing, visibility, and observability.

### Resource Anchors
- Bridge Azure resource groups to OCI compartments (1:1 mapping)
- **Global constructs** — replicated across all regions after creation
- OCI compartment naming: `resourceGroupName_resourceAnchorName_uniqueDateTimeStampID`
- Carry: Azure subscription, resource group, Azure AD group, OCI compartment (uses global OCID, not region-tied)
- Enable federation of Azure AD groups with OCI user groups for access control

### Network Anchors
- Bridge Azure VNets/subnets/DNS to OCI VCNs/subnets/DNS
- **Regional constructs** — tied to specific Azure region and availability zone
- **Mandatory prerequisite for Base Database service** — cannot provision Base DB without a Network Anchor
- Expose DNS Listening Endpoint IP (for outbound Azure → OCI DNS resolution)
- Customers retain full management control of resources

---

## Delegated Subnet Design

A delegated subnet is a dedicated Azure VNet subnet with `Oracle.Database/networkAttachments` delegation that hosts Oracle Exadata VM Clusters, Autonomous VM Clusters, Base Database, ADB, and GoldenGate instances.

### Client Subnet CIDR
- Minimum: /27 (32 IPs). Maximum: /22 (1024 IPs). Recommended: /24 minimum for expansion.
- Fixed overhead: **13 IPs** reserved by Oracle AI Database@Azure networking services regardless of cluster count
  - Positions: IPs 0-3, 8-15, and last IP (e.g. for 10.0.0.0/24: 10.0.0.0–3, 10.0.0.8–15, 10.0.0.255)
- Per VM Cluster: 3 IPs (SCANs)
- Per VM node: 4 IPs
- Per Base Database VM: 1 IP; +1 DNS Listening Endpoint; +1 DNS Forwarding Endpoint (if enabled)
- Per Autonomous AI Database instance: 1 IP
- Per GoldenGate instance: 1 IP
- DNS services: 2 IPs (1 Listening + 1 Forwarding endpoint)

### Backup Subnet CIDR
- Minimum: /27. Maximum: /22. Only required for Exadata VM Cluster — NOT for Base DB or ADB.
- Fixed overhead: 3 IPs (2 at start of range, 1 at end)
- Per VM node: 3 IPs

### IP Consumption Scenarios — Client Subnet

| Configuration | IPs consumed | Min CIDR |
|---|---|---|
| 1 cluster / 2 VMs | 24 (13+3+4×2) | /27 |
| 1 cluster / 3 VMs | 28 (13+3+4×3) | /27 |
| 1 cluster / 4 VMs | 32 (13+3+4×4) | /27 |
| 1 cluster / 8 VMs | 48 (13+3+4×8) | /26 |
| Base DB without DNS | 14 (13+1) | /27 |
| Base DB with DNS (both endpoints) | 16 (13+1+1+1) | /27 |
| 1 Autonomous AI DB | 14 (13+1) | /27 |

### VM Cluster capacity per client subnet CIDR size (2-VM clusters = 24 IPs each)

| CIDR | /27 (32) | /26 (64) | /25 (128) | /24 (256) | /23 (512) | /22 (1024) |
|---|---|---|---|---|---|---|
| 2-VM clusters | 1 | 4 | 10 | 22 | 45 | 91 |
| 4-VM clusters | 1 | 2 | 6 | 12 | 26 | 53 |

### IP Consumption Scenarios — Backup Subnet

| Configuration | IPs consumed | Min CIDR |
|---|---|---|
| 1 cluster / 2 VMs | 9 (3+3×2) | /28 |
| 1 cluster / 4 VMs | 15 (3+3×4) | /28 |
| 1 cluster / 8 VMs | 27 (3+3×8) | /27 |

### CIDR restrictions
- Must be private IPv4 (RFC 1918): 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
- **Reserved — do not use:** 100.64.0.0/10 (Exadata X9M and X11M cluster interconnect)
- No overlapping CIDR blocks between client subnet, backup subnet, other VNet subnets, or cross-region subnets
- Plan for cross-region routing at CIDR selection time

### Delegated subnet limits
- Default: 5 delegated subnets per region; can be increased via Service Request

---

## DNS Configuration

### Default DNS (oraclevcn.com)
- Azure Private DNS Zone automatically created and linked to VNet during provisioning
- Domain: `*.oraclevcn.com`
- Leave "Custom DNS" checkbox unchecked; provide only a Hostname prefix (e.g. `oradb`)
- No manual DNS zone creation required

### Custom DNS
- Pre-create OCI Private DNS Zone in OCI Console (Networking → DNS Management → Private Views)
- During provisioning: check "Use custom DNS", select private view containing the custom zone
- Post-provisioning: manually copy SCAN and VIP records from OCI to Azure Private DNS zones or on-premises DNS servers

### Network Anchor DNS resolution modes

**Outbound DNS (Azure/on-premises → OCI):**
- Network Control Plane creates Listening DNS endpoint in network link VCN
- Updates NSG to allow DNS traffic: UDP+TCP port 53 from VNet CIDR (e.g. 10.45.0.0/16)
- Listening endpoint IP exposed in Network Anchor overview
- Manual config required for on-premises: configure outbound rules for `oraclecloud.com` and `oraclecloudapps.com` using Azure DNS Private Resolver (subnets delegated to `Microsoft.Network/dnsResolvers`), Azure VMs as DNS forwarders, or on-premises DNS servers

**Inbound DNS (OCI → Azure/on-premises):**
- Provide the DNS forwarding rules on the Network Anchor (`dnsForwardingRules` in the `Oracle.Database/networkAnchors` API — not on the Resource Anchor)
- Network Control Plane creates forwarding endpoint in network link VCN

**Bidirectional DNS:** Both inbound and outbound config applied simultaneously.

### Hostname and domain constraints

| Constraint | Value |
|---|---|
| Hostname prefix max length (Exadata) | 23 characters |
| Hostname prefix format | Start with letter, end with alphanumeric; hyphens allowed; no `localhost` or `-version` |
| Cluster name max length | 11 characters |
| Cluster name format | Start with alphabetic, letters/numbers/hyphens only (no underscores) |
| Host + Domain FQDN max | 112 characters combined |

### DNS port requirement
- Protocol: UDP and TCP
- Port: 53
- Source CIDR: VNet CIDR (e.g. 10.45.0.0/16)

### Supported services for DNS options
Exadata Database, Autonomous AI Database, Exascale Database, Oracle Base Database Service (Network Anchors only)

---

## Network Topologies

### 1. Local VNet
- Applications and Oracle DB in same VNet; separate subnets for isolation
- Lowest latency, lowest cost (no peering charges)
- Limited security segmentation (subnet-level NSGs only)
- Best for: latency-critical apps, single-region simplicity

### 2. VNet Peering
- Application VNets peer directly to Oracle AI Database@Azure VNet
- No hub VNet required; ranges from 1:1 to full mesh
- Regional peering: low latency over Azure backbone
- Global peering: cannot use directly for Oracle traffic without VPN/vWAN overlay
- Requires non-overlapping address spaces between all peered VNets
- Cost: ingress/egress data transfer charges per peering
- Best for: multi-app, dev/test isolation, microservices

### 3. Hub-and-Spoke VNet Peering
- Hub VNet hosts Azure Firewall or NVA; Spoke VNets connect via peering
- UDRs on spoke subnets force traffic through Hub firewall
- **Critical UDR rule:** prefix CIDR must be `>= delegated subnet CIDR` (cannot be more specific than the delegated subnet)
- Provides centralized inspection, security policy enforcement, NAT
- Extra hop adds latency — problematic for chatty applications
- Best for: enterprise security, shared services, hybrid cloud

### 4. Global Connectivity Between Regions (Cross-Region DR)
- Cross-region Active Data Guard with primary and standby in separate Azure regions
- Connectivity via Azure Virtual WAN, VPN Gateways, or VNet Peering + VPN overlay
- Asynchronous replication required (synchronous not recommended cross-region due to latency)
- OCI path alternative: use OCI backbone (requires Azure UDRs + OCI routing policy — more complex but potentially better performance)
- OCI cross-region: first 10 TB/month free
- Azure inter-region: egress charges apply
- Cannot use direct Global VNet Peering for Oracle AI Database@Azure without VPN tunneling

### 5. On-Premises Hybrid (Hub-and-Spoke with Gateway)
- Hub VNet hosts VPN Gateway or ExpressRoute Gateway + optional Firewall
- Gateway Transit must be enabled on VNet peering (Hub → Oracle spoke)
- VPN: Active/Passive or Active/Active Zone-Redundant supported; Standard Active/Active NOT supported
- ExpressRoute: Local and Global circuits supported; **ExpressRoute FastPath NOT supported for Oracle AI Database@Azure**
- BGP for dynamic route propagation or static routes + UDRs
- Best for: hybrid cloud, migration, compliance, on-prem failover

### Topology comparison

| Topology | Latency | Cost | Security | Best For |
|---|---|---|---|---|
| Local VNet | Best | Lowest | Subnet-level | Latency-critical single-region |
| VNet Peering | Low (regional) | Medium | Distributed | Multi-app, dev/test |
| Hub-and-Spoke | Medium | High | Centralized | Enterprise, hybrid |
| Global Regions | High | High | Centralized | Cross-region DR |
| On-Prem Hybrid | Medium-High | High | Centralized | Hybrid cloud, migration |

---

## Oracle Interconnect for Azure (OCI FastConnect ↔ Azure ExpressRoute)

Establishes a direct private connection between OCI VCNs and Azure VNets — no public internet.

### Architecture
- OCI side: FastConnect private virtual circuit + Dynamic Routing Gateway (DRG)
- Azure side: ExpressRoute circuit + Virtual network gateway
- Protocol: BGP dynamic routing (two redundant BGP sessions)
- Traffic flow: VNet ↔ ExpressRoute ↔ FastConnect virtual circuit ↔ DRG ↔ VCN

### What is supported
- Private IP traffic between VNet and directly connected VCN
- Traffic from VNet through connected VCN to peered VCNs (same or different OCI regions)

### What is NOT supported
- On-premises → VCN → VNet (or reverse) transit traffic

### BGP address configuration
Each BGP session pair requires a /28 to /31 CIDR block:
- 10.0.0.20/30 example: .20 internal, .21 Oracle BGP IP, .22 Azure BGP IP ("Customer"), .23 internal
- Primary and secondary sessions must use **separate** CIDR blocks

### Setup steps (summary)
1. Configure OCI VCN security rules (ICMP, SSH port 22, SQL*Net port 1521 from VNet CIDR)
2. Create Azure ExpressRoute circuit with provider "Oracle Cloud Infrastructure FastConnect"; save the service key
3. Create OCI FastConnect virtual circuit: partner = "Microsoft Azure: ExpressRoute"; enter Azure service key; set bandwidth to match ExpressRoute; configure BGP IPs
4. Verify FastConnect status = UP and ExpressRoute private peering provisioned
5. Add route table entry in OCI VCN: destination = VNet CIDR, target = DRG
6. Add route table entry in Azure VNet: destination = VCN CIDR, next hop = VNet gateway

### Key constraints
- No overlapping CIDRs between VNet and VCN
- Both networks must belong to the same organization
- Regional pairing required: OCI and Azure locations must be in the supported availability table
- Changing the DRG on a provisioned circuit causes downtime
- Termination sequence: delete Azure ExpressRoute connections first, then delete OCI FastConnect circuit, then delete Azure ExpressRoute circuit

### Supported regions (sample)
- US East: OCI Ashburn (IAD) ↔ Azure Washington DC / Washington DC2
- UK: OCI London (LHR) ↔ Azure London
- Germany: OCI Frankfurt (FRA) ↔ Azure Frankfurt / Frankfurt2
- Japan: OCI Tokyo (NRT) ↔ Azure Tokyo
- Australia: not in the list above — check current Oracle docs for full region table

---

## Security Notes

- All application-to-database traffic routes privately over Azure backbone — no public internet exposure
- NSGs and routing tables control traffic at the delegated subnet level
- Azure NSG rule changes update OCI NSG ingress only — Azure VNet rules must be updated separately
- ExpressRoute FastPath NOT supported for Oracle AI Database@Azure (gateway processing required)
- Default OCI security lists allow SSH (port 22) and ICMP from 0.0.0.0/0 — restrict to VNet CIDR
- On Oracle Linux: use `firewalld` (not iptables directly) to open port 1521 for SQL*Net
