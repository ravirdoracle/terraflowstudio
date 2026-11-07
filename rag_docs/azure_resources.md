# Oracle AI Database@Azure (AI DB@Azure)

Oracle AI Database@Azure deploys Oracle Exadata infrastructure within Azure data centers, managed by OCI, billed through Azure Marketplace.

## Available database services
- Oracle Exadata Database Service on Dedicated Infrastructure (19c, 26ai)
- Oracle Exadata Database Service on Exascale Infrastructure (19c, 26ai)
- Oracle Base Database Service
- Oracle Autonomous AI Database (Serverless and Dedicated)
- Oracle GoldenGate
- Oracle Database Autonomous Recovery Service

## Architecture
- Azure Region → Azure Availability Zone → OCI Child Site (houses Exadata hardware)
- OCI Parent Region connects to Azure AZ via OCI-managed network
- Azure applications connect to Oracle DB through a delegated subnet
- OCI VCN and subnets are auto-created in OCI tenancy when resources are deployed from Azure
- Management: Azure Portal, Azure CLI, Azure APIs (which invoke OCI APIs internally)
- Billing: single Azure Marketplace invoice; counts toward Azure spend commitments

## Onboarding order
1. Contact Oracle for Private Offer via Azure Marketplace
2. Purchase and link Azure subscription to OCI tenancy (multicloud linking)
3. Create VNet → Delegated Subnet → Exadata Infrastructure → VM Cluster (or Autonomous DB)

---

## Networking: Delegated Subnet

The delegated subnet is the critical networking component — it provides secure, isolated, low-latency connectivity between Azure applications and Oracle databases.

- One delegated subnet per VNet; must have `Oracle.Database/networkAttachments` delegation
- Multiple Oracle Exadata VM Clusters can share the same delegated subnet
- Default backup subnet CIDR: `192.168.252.0/22` (auto-assigned if not specified)
- NSG ingress rules are managed in OCI — Azure VNet rules must be updated separately
- Custom DNS available: if unchecked, uses default OCI domain `oraclevcn.com`
- Host and domain URL: maximum 112 characters
- SCAN Listener Port: valid range 1024–8999, default 1521
- Additional network ingress rules can be added: single port (80), range (80-8080), comma-delimited (80,8080)

---

## Exadata Infrastructure

Provisioning time: up to 15+ minutes. Required before creating VM Clusters.

### Required fields
- Name: up to 255 chars; a-z A-Z 0-9 _ -; must start with letter or _; no successive hyphens
- Microsoft Azure Subscription: required
- Resource Group: new or existing
- Region: Azure region where infrastructure is deployed
- Availability Zone: limited by subscription
- System Model:
  - Exadata.X9M: 2–32 database servers (OCPUs), 3–64 storage servers
  - Exadata.X11M: 2–32 database servers (ECPUs), 3–64 storage servers; enables database_server_type and storage_server_type

### Optional fields
- Maintenance window: Oracle-managed schedule OR Customer-managed
  - Patching mode: Non rolling (default) OR Rolling (recommended for production, zero downtime)
  - Maintenance timeout: 15–120 minutes
  - Notification contacts: up to 10 email addresses
- Tags: Azure tags (note: NOT propagated to OCI portal)

---

## Exadata VM Cluster

Provisioning time: up to 4+ hours.

### Required fields (Basics tab)
- Name: up to 255 chars; a-z A-Z 0-9 _ -; starts with letter or _; no successive hyphens
- VM cluster name: same constraints as Name
- Microsoft Azure Subscription
- Resource Group
- Region
- Exadata Infrastructure: must exist; cross-subscription supported via linking
- License Type: License Included OR Bring Your Own License (BYOL)
- Time Zone: default UTC
- Storage Type: ASM or Exascale
  - ASM: supports Grid Infrastructure 19c and 26ai
  - Exascale: supports 26ai only; requires Database Storage Vault (create new or select existing)
    - Vault name: 1–255 chars; letters/numbers/_/-; starts with letter or _; no successive hyphens
- Grid Infrastructure Version: depends on storage type
- SSH Public Key: generate new key pair, use existing (Azure), or provide RSA public key (ssh-rsa single-line or PEM multi-line)

### Required fields (Configuration tab)
- OCPU count per VM: limited by Exadata Infrastructure capacity
- Memory per VM: limited by Exadata Infrastructure capacity
- Local storage per VM /u02 (GB): slider-based
- Usable Exadata Storage (TB): limited by infrastructure

### Optional fields (Configuration tab)
- Change database servers: assign specific nodes; single-node option available (not HA-capable)
- Additional local file system configuration:

| File System | Min (GB) | Max (GB) |
|---|---|---|
| / | 15 | 900 |
| /var | 5 | 900 |
| /home | 4 | 900 |
| /tmp | 3 | 900 |
| /u01 | 20 | 900 |
| /var/log | 18 | 900 |
| /var/log/audit | 3 | 900 |

- Use Exadata sparse snapshots (IMMUTABLE — set at creation only)
- Use local backups (IMMUTABLE — set at creation only)
- Usable storage allocation (IMMUTABLE — set at creation only)

### Required fields (Networking tab)
- Virtual Network: limited by subscription and resource group
- Client Subnet: delegated subnet from the selected VNet
- Host name prefix: first portion of VM node hostnames

### Optional fields (Networking tab)
- Backup subnet CIDR: defaults to 192.168.252.0/22 if empty
- Custom DNS: enables OCI private DNS view selection; if unchecked uses oraclevcn.com
- Private view: required if Custom DNS enabled; must match OCI compartment of network link
- SCAN Listener Port: default 1521, range 1024–8999; reserved ports checked pre-provisioning
- Additional network ingress rules: CIDR ranges for app/hub subnets (updates OCI NSG only)

### Immutable settings
- Use Exadata sparse snapshots
- Use local backups
- Usable storage allocation
- Storage Type (ASM vs Exascale) cannot change post-creation

### Gotchas
- Azure tags are NOT propagated to OCI portal
- Single-node clusters cannot be used for HA configurations
- Cross-subscription infrastructure requires Azure subscription to be linked to OracleDB@Azure
- Network security rules updated in OCI only — Azure VNet rules must be manually updated separately
- Exascale storage type only supports Oracle AI Database 26ai (not 19c)

---

## Terraform / AzAPI provider

Oracle AI DB@Azure resources are provisioned using the AzAPI Terraform provider (for the Azure-side resources) alongside the OCI Terraform provider (for database-level resources like DB Home, CDB, PDB).

Key AzAPI resource types:
- `azapi_resource` with type `Oracle.Database/cloudExadataInfrastructures@<api-version>` — Exadata Infrastructure
- `azapi_resource` with type `Oracle.Database/cloudVmClusters@<api-version>` — VM Cluster
- `azapi_resource` with type `Oracle.Database/networkAnchors@2025-09-01` — Network Anchor

What Terraflow Studio generates: azurerm resources wherever azurerm has one
(`azurerm_oracle_exadata_infrastructure`, `azurerm_oracle_cloud_vm_cluster`,
`azurerm_oracle_autonomous_database`, `azurerm_oracle_resource_anchor`), and azapi
only for the Network Anchor, which azurerm does not have (see azure_network_anchor.md).

The OCI Terraform provider is used for:
- DB Home (`oci_database_db_home`)
- CDB / PDB (`oci_database_database`, `oci_database_pluggable_database`)

---

## Security & Integration
- OCI Vault: manages encryption keys and Customer Managed Keys (CMK)
- OCI Object Storage: backup destination
- Oracle Database Autonomous Recovery Service: real-time, sub-second recovery
- AWS service integrations: Azure Monitor, Azure Log Analytics, Azure VM, Azure VNet
