# ODB@AWS — Networking Topologies, IP Sizing, and DNS

## What is an ODB Network
A private, isolated network hosting Oracle Exadata VM Clusters and Autonomous VM Clusters within a single AWS Availability Zone. By default it has NO connectivity to AWS VPCs, on-premises networks, or the internet — explicit ODB peering connections are required for any traffic.

## Two required subnets per ODB network
Every ODB network requires exactly two CIDR ranges specified at creation time — client subnet and backup subnet. Both are IMMUTABLE after creation.

---

## Client Subnet CIDR sizing

Minimum /27 (32 IPs), Maximum /16.

IP consumption formula:
- 6 IPs: fixed ODB overhead (reserved regardless of VM cluster count)
- 3 IPs per VM cluster: reserved for SCAN (Single Client Access Name) listeners
- 4 IPs per VM node created
- 1 IP optional: OCI DNS Listening Endpoint

Examples:
- 1 cluster × 2 VMs = 6 + 3 + 8 + 1 = 18 IPs → minimum /27 (32 IPs)
- 1 cluster × 8 VMs = 6 + 3 + 32 + 1 = 42 IPs → minimum /26 (64 IPs)
- 2 clusters × 3 VMs each = 6 + 6 + 18 + 1 = 31 IPs → minimum /27 (32 IPs) — tight, use /26

Multi-cluster capacity planning — how many cluster×VM combinations fit per CIDR:

| Configuration (IPs needed) | /27 | /26 | /25 | /24 |
|---|---|---|---|---|
| 1 cluster × 2 VMs (18 IPs) | 1 | 3 | 7 | 15 |
| 1 cluster × 4 VMs (26 IPs) | 1 | 2 | 5 | 10 |
| 2 clusters × 2 VMs each (28 IPs) | 1 | 2 | 4 | 9 |
| 2 clusters × 3 VMs each (36 IPs) | 0 | 1 | 3 | 7 |
| 2 clusters × 4 VMs each (44 IPs) | 0 | 1 | 2 | 5 |

Rule of thumb: for any multi-cluster or >2-VM deployment, start at /26 or larger.

---

## Backup Subnet CIDR sizing

Minimum /28 (16 IPs), Maximum /16.

IP consumption formula:
- 3 IPs: fixed ODB overhead (reserved regardless of VM cluster count)
- 3 IPs per VM node created

Examples:
- 1 cluster × 2 VMs = 3 + 6 = 9 IPs → minimum /28 (16 IPs)
- 1 cluster × 8 VMs = 3 + 24 = 27 IPs → minimum /27 (32 IPs)
- 2 clusters × 4 VMs each = 3 + 24 = 27 IPs → minimum /27 (32 IPs)

Multi-cluster capacity planning:

| Configuration (IPs needed) | /28 | /27 | /26 | /25 | /24 |
|---|---|---|---|---|---|
| 1 cluster × 2 VMs (9 IPs) | 1 | 3 | 7 | 14 | 28 |
| 1 cluster × 4 VMs (15 IPs) | 1 | 2 | 4 | 8 | 17 |
| 2 clusters × 2 VMs each (15 IPs) | 1 | 2 | 4 | 8 | 17 |
| 2 clusters × 3 VMs each (21 IPs) | 0 | 1 | 3 | 6 | 12 |
| 2 clusters × 4 VMs each (27 IPs) | 0 | 1 | 2 | 7 | 9 |

---

## Forbidden / restricted CIDR ranges

Cannot use these for client or backup subnets:
- 100.64.0.0/10 — reserved for cluster interconnect by OCI automation
- 169.254.0.0/16 — Oracle Cloud reserved range
- 224.0.0.0–239.255.255.255 — Class D multicast
- 240.0.0.0–255.255.255.255 — Class E reserved

Overlap restrictions:
- Client and backup subnets must not overlap each other
- Neither subnet may overlap any VPC CIDR connected to the ODB network via peering
- No overlap with on-premises or other networks reachable via Transit Gateway or Cloud WAN
- No overlap with any existing VPC CIDR in the same AWS region (buyer or owner account)

---

## DNS configuration

Default domain: oraclevcn.com
Custom domain: can be set at ODB network creation time. Only usable with Exadata Database Service on Dedicated Infrastructure — Autonomous Database always uses the default name.

ODB network automatically provisions:
- OCI DNS Forwarder Endpoint (OCI → AWS direction)
- OCI DNS Listener Endpoint (AWS → OCI direction)

### DNS resolution: AWS application → Oracle database (AWS to OCI)
1. EC2 application resolves hostname
2. Route 53 resolver outbound endpoint forwards query to OCI Private DNS listener endpoint (IP in client subnet)
3. OCI Private DNS resolves hostname to IP, returns to client

### DNS resolution: database agent → AWS resource (OCI to AWS)
1. Agent on DB host queries hostname
2. OCI Private DNS forwarder sends query to Route 53 private hosted zone linked to VPC
3. Route 53 returns IP to database

DNS setup required on AWS side: Route 53 resolver rule forwarding the ODB domain (e.g. *.oraclevcn.com) to the OCI listener endpoint IP.

---

## Network topology patterns

### 1. Default — single VPC to ODB network
Simplest topology. One Application VPC connects to ODB network via single ODB peering connection. Application and database in same AZ for lowest latency. Supports multiple apps in same VPC using subnet isolation.

### 2. Transit VPC (hub-and-spoke through Transit Gateway)
ODB network connected to Transit VPC, which attaches to Transit Gateway. Application VPCs route through Transit Gateway to reach the database. Transit VPC must be in the same AWS account as the ODB network. Transit Gateway attachment should be in the same AZ as the ODB network for best performance.

### 3. Multiple VPCs → one ODB network
Multiple application VPCs (even from different AWS accounts) each establish their own ODB peering connection to a single ODB network. Maximum 45 peering connections per ODB network. Each VPC/CIDR added to the peering connection configuration. Recommended for latency-sensitive apps requiring direct peering.

### 4. One VPC → multiple ODB networks (multi-AZ)
Single application VPC connects to ODB networks in separate Availability Zones. Lowest latency for apps spanning multiple AZs. Each ODB network in its own AZ with its own peering connection from the single VPC.

### 5. Multiple VM clusters per ODB network
Multiple VM clusters can coexist within a single ODB network. Use for dev/prod isolation (separate clusters, shared network) or scaling (more clusters, same physical zone). VM clusters cannot be moved between ODB networks after creation.

### 6. Cross-VPC hub-and-spoke (same region)
Use cases: traffic inspection between app and DB tier; HA apps across multiple AZs sharing same Oracle DB; centralized DB access across business units.
Route traffic through AWS Transit Gateway or AWS Cloud WAN — optionally through a Firewall. AWS Transit Gateway attachment in same AZ as ODB network is recommended. Latency is higher than direct VPC peering; validate app performance.

### 7. Cross-region hub-and-spoke
Use cases: regional DR; cross-region data replication; centralized management.
Two Transit Gateways (one per region) with peering. AWS Cloud WAN is an alternative. Higher latency than same-region — validate application requirements.

### 8. Hybrid (on-premises) connectivity
Use cases: migration from on-premises; on-prem → cloud DR replication; hybrid apps.
Connect via Direct Connect (preferred — better latency/bandwidth) or VPN through Transit Gateway. AWS Cloud WAN also supported. Validate latency requirements.

---

## Topology limits and constraints

- One ODB network per Availability Zone per deployment
- Maximum 45 ODB peering connections per ODB network
- One peering connection per (VPC, ODB network) pair — cannot peer the same VPC to the same ODB network twice
- VMs cannot be moved between ODB networks
- Deleting an ODB network requires deleting all Exadata VMs but does NOT require deleting Exadata Infrastructure
- ODB networks in us-east-1 or us-west-2 created before 2026-02-07 must be fully recreated before adding ODB peering or deleting multiple peering connections (regional upgrade requirement)
- AWS Placement Group is created automatically for High Performance Networking (HPN) after ODB network setup

---

## Performance guidance

- Co-locate application and database in the same AZ for lowest latency
- Prefer direct VPC peering (topology 1 or 3) over Transit Gateway for latency-sensitive workloads
- When using Transit Gateway, attach it in the same AZ as the ODB network
- Cross-AZ, cross-region, and on-premises connectivity introduces additional latency — benchmark before production use
- Cross-AZ/cross-region traffic through Transit Gateway or Cloud WAN incurs additional AWS data transfer costs
