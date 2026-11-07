# Oracle Multicloud Hub

Oracle Multicloud Hub is a unified management interface (single pane of glass) within the OCI Console for Oracle database services deployed across multiple cloud providers.

## Supported clouds
- Microsoft Azure (Subscription ID, Resource Groups, Virtual Networks)
- Amazon Web Services (AWS) (Account IDs, VPCs)
- Google Cloud Platform (GCP) (VPCs)

## Key capabilities

### FinOps Management
- View OCI Multicloud subscriptions
- Access partner cloud account details (Azure Subscription ID, AWS Account ID)
- Manage private offer commitments (committed amounts and timeframes)

### Resource Discovery & Navigation
- List all Multicloud resources in one place
- Navigate to resource details in both OCI and partner cloud consoles

### Interconnectivity Mapping
- Resource anchors: map OCI compartments to partner CSP constructs
  - Azure: Subscription ID → Resource Groups
  - AWS: Account ID → VPCs
- Network anchors: map OCI VCNs to partner CSP networking
  - Azure VNETs, AWS VPCs, GCP VPCs

### HA/DR Planning
- Design high availability and disaster recovery strategies across clouds
- Map OCI availability domains to partner CSP availability zones (physical and logical)

## How it fits with Terraform
Multicloud Hub is an OCI Console feature for operational visibility, not a Terraform resource type. Terraform manages the underlying database resources (networks, infra, VM clusters); Multicloud Hub provides the operational view of those resources across clouds.

## Source
https://docs.oracle.com/en-us/iaas/Content/multicloud-hub/home.htm
