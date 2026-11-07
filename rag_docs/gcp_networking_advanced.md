# Oracle AI DB@GCP — Advanced Networking: Routing, Security, Zones, and Operational Details

Source: Oracle A-Team blog "Networking Fundamentals for Oracle AI DB@GCP" by Shawn Moore, Principal Cloud Network Architect (December 2025)

---

## Underlying connectivity mechanism: Cloud Router + Partner Interconnect

The ODB network connects to the GCP VPC through an automatically provisioned Cloud Router with Partner Interconnect. This is done entirely by Oracle automation during ODB network creation — no VPN, no Direct Connect, no third-party connectivity setup required.

The ODB network is a representation of an OCI VCN (Virtual Cloud Network) within the GCP VPC. The OCI side of this is called the OCI Child Site. The paired OCI region that supports a given GCP region is called the Parent Site.

---

## CRITICAL: No additional routing configuration needed (GCP differs from AWS)

Unlike AWS where routes must be added manually after peering, on GCP:
- Provisioning the ODB network automatically links it to the Cloud Router in the VPC
- No additional route table configuration is needed for VPC subnets to reach the ODB network
- All subnets within the same VPC — even subnets in different GCP regions — have network reachability to the ODB network by default

This is a key difference from ODB@AWS, where routes for both client and backup subnet CIDRs must be added manually to the VPC route table after peering.

---

## Zonal vs regional resource scope

Understanding resource scope is important for planning availability and multi-zone deployments.

Zonal resources (must be placed in a specific GCP Oracle Zone):
- Exadata Infrastructure
- Exadata VM Clusters
- Exadata VM Clusters + Exascale Storage Vaults
- ODB Networks and ODB Subnets
- DB Systems

Regional resources (can run in any zone within the region):
- Oracle Autonomous Databases (ADB)

Note: Oracle AI Database@GCP zones are referred to as GCP Oracle Zones. Format: `<region>-<zone>-r<number>` e.g. `us-east4-b-r1`.

---

## Backup subnets are only for Exadata VM Clusters

Client subnets: used by BOTH Autonomous Databases AND Exadata VM Clusters.
Backup subnets: used ONLY by Exadata VM Clusters — NOT by Autonomous Databases.

Implication for Terraform: when deploying only Autonomous Databases, a backup subnet is not required. When deploying an Exadata VM Cluster, both client and backup subnets are required.

---

## ODB Network security: Network Security Groups (NSG)

Security within the ODB network is controlled by OCI Network Security Groups (NSGs), not GCP firewall rules.

How NSGs work:
- An NSG acts as a virtual firewall for cloud resources sharing the same security posture
- NSG rules define ingress and egress traffic by: IP address (or another NSG), Protocol, and Port
- The NSG is applied to the VNIC of each resource — the ADB instance, Exadata VM Cluster, or Base DB instance

Default open ports on database resources:
- TCP port 22 — SSH access
- TCP port 1521 — Oracle SQL*Net (database connections)

The DNS listener endpoint is also governed by an NSG rule that controls precisely which ingress IPs and ports can query it.

---

## DNS: FQDN format and zone naming

GCP Cloud DNS private zone is automatically provisioned when the ODB network is created.

DNS zone names by database type:
- `oraclevcn.com` — Exadata VM Clusters and Base Database
- `oraclecloud.com` and `oraclecloudapps.com` — Autonomous AI Database (ADB)

FQDN format for Exadata/BaseDB:
```
<hostname>.<subnet_name>.oraclevcn.com
```
Example: a VM cluster with hostname `db1` in subnet `subnet1` has FQDN: `db1.subnet1.oraclevcn.com`

GCP Cloud DNS forwarding rules are configured to send queries for these domains to the DNS Listener IP provisioned in the ODB network client subnet. The listener IP is governed by an NSG rule.

---

## VPC peering requires a Cloud DNS peering zone

When using VPC peering topology (applications in a different VPC or project than the ODB network), two things are required:
1. VPC peering connection between the application VPC and the ODB network VPC
2. Cloud DNS peering zone — allows the application VPC to resolve Oracle database FQDNs via the ODB network's private DNS zone

Without the DNS peering zone, applications can route to the database IP but cannot resolve the hostname.

---

## Up to 5 ODB subnets per ODB network

Each ODB network supports up to 5 subnets total (client and backup combined). This enables more granular network segmentation than the default 2-subnet model. All subnet CIDRs must be non-overlapping and within RFC1918 ranges.

---

## Subnet CIDR rules summary (from A-Team blog)

Both client and backup subnets:
- Minimum: /27
- Maximum: /22
- Must be RFC1918: 10.0.0.0/8, 172.16.0.0/12, or 192.168.0.0/16
- Must not overlap with the associated VPC's existing subnets

---

## Topology patterns confirmed by Oracle A-Team

Three validated multi-VPC designs:

1. Multiple VPCs — each project/business unit has its own VPC and ODB network; multiple VM clusters can share the same Exadata Infrastructure while connecting to separate VPCs. Example: Marketing VPC (192.168.2.0/24 client, 192.168.3.0/24 backup) and Sales VPC (10.1.2.0/24 client, 10.1.3.0/24 backup) both pointing to the same Exadata Infrastructure.

2. VPC Peering — centralised database project/VPC; application projects connect via VPC peering + Cloud DNS peering zone. A transit VPC holds the ODB network and peers with spoke application VPCs.

3. NVA Hub & Spoke — Network Virtual Appliance in a transit VPC with multiple VNICs connecting to spoke VPCs (Finance, Sales, etc.). NIC1 connects to transit VPC (which hosts ODB network), NIC2+ connect to spoke VPCs. Provides centralised traffic inspection and security control.
