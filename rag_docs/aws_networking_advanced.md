# ODB@AWS — Advanced Networking: Routing, Peering Patterns, and Operational Gotchas

## CRITICAL: Routes are NOT added automatically after ODB peering

Creating an ODB peering connection does NOT automatically add routes in the VPC route table. You must add them manually or via Terraform.

After establishing peering, add routes for both subnets:

```bash
# Route for client subnet
aws ec2 create-route \
  --route-table-id rtb-xxxxxxxx \
  --destination-cidr-block <ODB-CLIENT-SUBNET-CIDR> \
  --peering-connection-id pcx-xxxxxxxx

# Route for backup subnet
aws ec2 create-route \
  --route-table-id rtb-xxxxxxxx \
  --destination-cidr-block <ODB-BACKUP-SUBNET-CIDR> \
  --peering-connection-id pcx-xxxxxxxx
```

Without these routes, applications in the VPC cannot reach the database even though peering is established.

---

## CRITICAL: Secondary VPC CIDRs must be added manually to peering

When a VPC has secondary CIDR blocks (in addition to its primary CIDR):
- The primary VPC CIDR is automatically added to the ODB peering's allowed list
- Secondary CIDRs are NOT automatically added — they must be added explicitly

```bash
aws odb add-peered-cidr \
  --peering-connection-id pcx-xxxxxxxx \
  --peered-cidr <SECONDARY-VPC-CIDR>
```

If secondary CIDRs are not added, applications in those subnets cannot reach the database.

---

## What OCI automation does when a peered CIDR is added

When you add a peered CIDR to an ODB peering connection, OCI automatically (no manual action needed on Oracle side):
1. Adds static routes directing traffic to the peered CIDR blocks
2. Creates security rules allowing:
   - ICMP (ping and diagnostics)
   - TCP port 22 (SSH)
   - TCP ports for Oracle database traffic (SQL*Net 1521, monitoring, management)

You do not need to configure OCI security lists or route tables manually.

---

## Three connectivity patterns and their constraints

### Pattern 1: Direct VPC Peering
Simplest. Application VPC peers directly with ODB network. Best latency. Suitable when one or a few VPCs need database access.
- Cross-account sharing: possible via AWS RAM
- Requirement: non-overlapping CIDRs between VPC and ODB subnets

### Pattern 2: Transit Gateway (single region, multi-VPC)
Multiple VPCs and on-premises networks connect through a Transit Gateway. A transit VPC in the same AWS account as the ODB network acts as the peering bridge.

IMPORTANT constraints:
- Built-in Transit Gateway attachment for ODB network is NOT supported — manual transit VPC setup required
- Transit Gateway attachment subnet must be in the same Availability Zone as the ODB network — cross-AZ TGW attachments cause routing problems
- Transit VPC and ODB network must be in the same buyer account
- Cannot use the same transit VPC for both Transit Gateway AND Cloud WAN simultaneously

### Pattern 3: AWS Cloud WAN (multi-region / hybrid)
Extends connectivity across regions and on-premises using dynamic route propagation. Requires a transit VPC in the same AZ as the ODB network.

IMPORTANT constraints:
- Built-in Cloud WAN attachment for ODB network is NOT supported — manual transit VPC required
- Transit VPC must be in the same AZ as the ODB network
- Transit VPC cannot attach to both Transit Gateway and Cloud WAN at the same time

---

## AWS Placement Groups for high-performance networking

After ODB network creation, AWS automatically creates a Placement Group for High Performance Networking (HPN). Retrieve the Placement Group ID:

```bash
aws odb get-odb-network --odb-network-id odbnet_xxxxxxxx
# Look for ec2PlacementGroupIds in the output
```

Use this Placement Group when launching EC2 application instances to minimise latency to the database:

```bash
aws ec2 run-instances \
  --placement GroupId=pg-0e6faa731d3df801e \
  --instance-type r6i.large \
  ...
```

Use Placement Groups selectively — ODB@AWS inherently has slightly higher latency than on-premises Exadata; Placement Groups help minimise the EC2-to-database portion.

---

## Capacity Reservations

Use On-Demand Capacity Reservations in the same AZ as your ODB network to minimise EC2 capacity exceptions when launching application instances alongside the database workload.

---

## Peering limit and per-VPC constraint recap

- Maximum 45 ODB peering connections per ODB network
- A VPC can peer with multiple ODB networks, but only ONE peering connection per (VPC, ODB network) pair
- ODB network subnet CIDRs are IMMUTABLE — plan carefully before creation
- VM clusters cannot be moved between ODB networks after creation

---

## Pre-February 2026 network recreation requirement

ODB networks in us-east-1 or us-west-2 created before 2026-02-07 require full recreation before:
- Adding a second or subsequent ODB peering connection
- Deleting multiple ODB peering connections

Recreation process:
1. Delete all Exadata VMs (required)
2. Delete and recreate the ODB network (Exadata Infrastructure does NOT need to be deleted)

If you only need one peering connection, no action is required.

---

## DNS: Route 53 Resolver outbound endpoint

Applications in the VPC use Route 53 to resolve Oracle database hostnames (*.oraclevcn.com or custom domain). Configure a Route 53 Resolver outbound endpoint that forwards those queries to the OCI DNS Listener IP in the client subnet.

Two OCI DNS endpoints provisioned in the client subnet:
1. OCI DNS Listener Endpoint (always created) — AWS → OCI direction; 1 IP consumed from client subnet
2. OCI DNS Forwarding Endpoint (optional) — OCI → AWS direction (for resolving AWS hostnames from database hosts); 1 additional IP consumed from client subnet

---

## ODB network creation CLI reference

```bash
aws odb create-odb-network \
  --display-name "prod-odb-network" \
  --availability-zone-id "use1-az4" \
  --client-subnet-cidr "10.2.0.0/24" \
  --backup-subnet-cidr "10.2.1.0/24"
```

Retrieve details (including Placement Group ID) after creation:

```bash
aws odb get-odb-network --odb-network-id odbnet_xxxxxxxx
```
