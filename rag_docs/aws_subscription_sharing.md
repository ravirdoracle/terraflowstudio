# Oracle AI Database@AWS — Subscription Sharing and Resource Sharing

Source: Oracle Cloud Infrastructure Documentation — database-at-aws subscription sharing
Source URL: https://docs.oracle.com/en-us/iaas/Content/database-at-aws/onboard-multi.htm

---

## Overview

Two distinct sharing mechanisms exist for Oracle AI Database@AWS:

1. **Subscription Sharing** (AWS License Manager) — Share the AWS Marketplace private offer entitlement so multiple AWS accounts in the same organisation can provision Oracle AI DB@AWS resources without each purchasing separately.
2. **Resource Sharing** (AWS RAM) — Share specific Exadata infrastructure or ODB network resources with trusted accounts so they can create VM clusters on shared infrastructure.

---

## Part 1: Subscription Sharing via AWS License Manager

### What It Does

A grantor (buyer) account shares its Oracle AI Database@AWS Marketplace subscription with grantee accounts within the same AWS Organisation. Each grantee account can then provision and manage Oracle AI DB@AWS resources without buying their own subscription.

Use cases: multiple Lines of Business sharing one subscription; using one subscription across dev/test/prod environments for SDLC compliance.

### Prerequisites

- Oracle AI Database@AWS **private offer** purchased through AWS Marketplace (public offer not supported)
- Grantor and all grantee accounts must belong to the **same AWS Organisation**
- Grant operations must be performed from **us-east-1 (N. Virginia)** region

### Limits

| Constraint | Value |
|---|---|
| Max grantee accounts per grantor | 50 |
| Grantors a grantee can accept from | 1 (only one grantor at a time) |
| Sharing scope | Same AWS Organisation only — no OU or org-wide sharing |
| Grantor-to-grantor sharing | Not supported |
| Console-only | AWS CLI / Terraform not supported for subscription sharing |

### IAM Policy — Grantor Account

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "ODBGrantManagement",
    "Effect": "Allow",
    "Action": [
      "license-manager:GetServiceSettings",
      "license-manager:ListReceivedLicenses",
      "license-manager:ListReceivedLicensesForOrganization",
      "license-manager:ListReceivedGrants",
      "license-manager:ListReceivedGrantsForOrganization",
      "license-manager:GetGrant",
      "license-manager:CreateGrant",
      "license-manager:CreateGrantVersion",
      "license-manager:DeleteGrant",
      "license-manager:GetLicense",
      "license-manager:DeleteLicense",
      "organizations:DescribeOrganization",
      "license-manager:ListDistributedGrants",
      "iam:CreateServiceLinkedRole",
      "odb:CreateGrantShare",
      "odb:UpdateGrantShare",
      "odb:DeleteGrantShare"
    ],
    "Resource": ["*"]
  }]
}
```

### IAM Policy — Grantee Account

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "ODBGrantManagement",
    "Effect": "Allow",
    "Action": [
      "license-manager:GetGrant",
      "license-manager:ListReceivedGrants",
      "license-manager:ListReceivedGrantsForOrganization",
      "license-manager:CreateGrantVersion",
      "license-manager:AcceptGrant",
      "iam:CreateServiceLinkedRole",
      "odb:UpdateGrantShare",
      "odb:DeleteGrantShare"
    ],
    "Resource": ["*"]
  }]
}
```

### Sharing Workflow

#### Step 1: Grantor Creates a Grant (AWS License Manager)

1. Sign in to AWS Console as **grantor account** in **us-east-1**
2. Open **AWS License Manager** → **Granted licenses**
3. First-time users: accept IAM permissions via "Start using AWS License Manager"
4. Select the **License ID** for Oracle AI Database@AWS
5. Select **Create grant**:
   - **Grant name**: descriptive name
   - **AWS account ID**: grantee account ID
6. Select **Create grant**
7. Wait up to **15 minutes** for grant to appear in grantee account

#### Step 2: Accept and Activate (Grantee Account)

**Option A — Grantee accepts AND activates:**
1. Sign in to AWS Console as **grantee account**
2. AWS License Manager → **Granted licenses** → select License ID
3. Select **Accept & activate license**
4. In confirmation dialog type `accept and activate` → **Accept & activate grant**
5. Grantee account can now provision Oracle AI DB@AWS resources

**Option B — Grantee accepts, Grantor activates:**
- Grantee: AWS License Manager → License ID → **Accept license**
- Grantor: AWS License Manager → **Granted licenses** → find accepted grant → **Activate license**

#### Step 3: Grantee Activates Account for OCI

1. Sign in to AWS Console as **grantee account**
2. Oracle AI Database@AWS dashboard → select AWS region matching grantor's **OCI Home Region**
3. Select **Activate account**
4. Wait up to **15 minutes** for activation
5. When **Dashboard** button becomes enabled — service is ready
6. A dedicated child compartment is auto-created in OCI Multicloud Link compartment

### Sharing Workflow Summary

| Phase | Who | Action | Wait |
|---|---|---|---|
| Create Grant | Grantor | AWS License Manager → Create grant with grantee account ID | Up to 15 min |
| Accept | Grantee | Accept license (or Accept & Activate) | — |
| Activate | Grantee or Grantor | Activate license in License Manager | — |
| OCI Activate | Grantee | Activate account in ODB Dashboard (same region as grantor's OCI home) | Up to 15 min |

---

## Part 2: Resource Sharing via AWS RAM

### What It Does

Share specific Exadata infrastructure or ODB network resources with trusted AWS accounts so those accounts can create VM clusters on shared infrastructure — without the shared account needing their own Exadata hardware.

Shareable resource types:
- `Oracle Database@AWS ODB network`
- `Oracle Database@AWS Exadata Infrastructure`

### Prerequisites

- Active Oracle AI DB@AWS subscription (buyer account only)
- Resource IDs/names to share
- Target AWS account IDs (must be in same AWS Organisation)
- Enable resource sharing with AWS Organisations in RAM settings

### Create a Resource Share (Console)

1. Open AWS RAM console → **Create resource share**
2. Enter a **Name** for the share
3. Under **Select resource type** choose:
   - `Oracle Database@AWS ODB network`, or
   - `Oracle Database@AWS Exadata Infrastructure`
4. Select the resources to share → **Next**
5. Under **Principals** → **AWS accounts** → enter account IDs
6. Under **Managed permissions** assign:
   - `AWSRAMDefaultPermissionODBNetwork`
   - `AWSRAMDefaultPermissionODBCloudExadataInfrastructure`
7. **Create resource share**

### Create a Resource Share (AWS CLI)

```bash
aws ram create-resource-share --region us-east-1 \
  --name "ExadataInfraShare" \
  --resource-arns arn:aws:odb:us-east-1:111111111111:cloud-exadata-infrastructure/exa_infra_1 \
  --principals 222222222222
```

### Create a Resource Share (Terraform)

**Sharing resources this configuration builds** — use the **ram_resource_share** tab on
the AWS page. It adds `module "aws_ram_share"` (for_each over `aws_ram_shares`) to the
main root: each share names Exadata Infrastructures (`infra_refs`) and ODB Networks
(`network_refs`) by module name, and the ARNs are wired from
`module.aws_exadata_infra[...].infra_arn` / `module.aws_odb_network[...].network_arn` —
nothing to paste after apply. Principals are 12-digit account IDs in the same
Organization. Share the ODB Network together with the Exadata Infrastructure so the
other account can build VM clusters on it. Apply after the shared resources are ACTIVE:

```bash
terraform apply -target='module.aws_ram_share["prod_share"]'
```

**Resources owned by another account** cannot be shared from this configuration: a
resource share is created in the account that owns the resource. Share those from that
account — with the `aws ram create-resource-share` command above, or from that account's
own Terraform configuration. A share holds resources from one region only; an ODB
Network and an Exadata Infrastructure can be in the same share. Use Terraform or the
CLI for a given share, not both.

### View Resource Shares (AWS CLI)

```bash
# List your resource shares
aws ram get-resource-shares --resource-owner SELF

# List resources in a specific share
aws ram list-resources \
  --resource-owner SELF \
  --resource-share-arns arn:aws:ram:us-east-1:111111111111:resource-share/12345678-abcd-1234-efgh-111111111111

# List accounts a share is shared with
aws ram list-principals \
  --resource-owner SELF \
  --resource-share-arns arn:aws:ram:us-east-1:111111111111:resource-share/12345678-abcd-1234-efgh-111111111111
```

### Removing/Unsharing Resources

To stop sharing: remove the resource from the share, remove the trusted account, or delete the share.

**Important implications before unsharing:**
- Trusted accounts can no longer create **new** resources on unshared infrastructure
- **Existing** resources created by trusted accounts continue to function
- Cannot delete Exadata infrastructure that has VM clusters created by trusted accounts until those VM clusters are removed

---

## Subscription Sharing vs Resource Sharing

| | Subscription Sharing | Resource Sharing |
|---|---|---|
| Mechanism | AWS License Manager | AWS RAM |
| What is shared | Marketplace subscription entitlement | Specific Exadata infra or ODB network |
| Grantee can provision | Their own independent resources | VM clusters on owner's infrastructure |
| Requires private offer | Yes | Yes (buyer account must have subscription) |
| OCI compartment created | Yes — child compartment per grantee | No additional OCI setup |
| CLI / Terraform support | No (console only) | Yes (`aws ram` commands, or the `ram_resource_share` tab's Terraform) |
| Max accounts | 50 per grantor | No stated limit |
| Grant operations region | us-east-1 only | Any supported region |
