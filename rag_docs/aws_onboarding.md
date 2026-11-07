# Oracle AI Database@AWS — Onboarding Guide

Source: Oracle Cloud Infrastructure Documentation — database-at-aws onboarding section
Source URL: https://docs.oracle.com/en-us/iaas/Content/database-at-aws/oaaws-onboard.htm

---

## Onboarding Overview

Onboarding is a one-time setup process. Tasks must be completed sequentially:

1. Prerequisites → 2. Request Offer → 3. Purchase → 4. Link Accounts → 5. Verify Setup → 6. Support Registration → 7. RBAC → 8. Federation (optional)

Requires access to both **AWS Console** and **OCI Console**.

---

## Task 1: Prerequisites

### OCI IAM Permissions

Non-tenancy-administrators must be in a group with required policy statements (root compartment):

| Task | Required OCI Policy |
|---|---|
| Task 4: Link OCI Account | `Allow group <group> to manage all-resources in tenancy` |
| Task 5: Verify Setup | `Allow group <group> to read subscription in tenancy` |
| Task 5: Verify Setup | `Allow group <group> to read compartments in tenancy` |
| Task 5: Verify Setup | `Allow group <group> to read limits in tenancy` |
| Task 5: Verify Setup | `Allow group <group> to read quotas in tenancy` |

### AWS IAM Permissions

AWS account administrators need no extra permissions. Non-administrators require:

**Purchasing offer** — attach this policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AcceptOffer",
      "Effect": "Allow",
      "Action": [
        "aws-marketplace:ViewSubscriptions",
        "aws-marketplace:Subscribe",
        "aws-marketplace:ListPrivateListings",
        "aws-marketplace:ListAgreementCharges",
        "aws-marketplace:AcceptAgreementRequest",
        "odb:AcceptMarketplaceRegistration",
        "odb:GetOciOnboardingStatus"
      ],
      "Resource": "*"
    }
  ]
}
```

**CRITICAL**: AWS Service Control Policies (SCPs) and permissions boundaries at the organisation level can override user permissions and cause provisioning failures. Work with org-level AWS admins to modify SCPs if onboarding fails.

### AWS Account Requirements

- One specific AWS account ID where resources will be provisioned
- Account must be subscribed to the target AWS region
- The selected AWS account receives all billing for Oracle AI Database@AWS
- AWS and OCI accounts must be subscribed to paired regions

### OCI Account Requirements

- Option 1: Link existing OCI tenancy
- Option 2: Create a new OCI tenancy during onboarding (the creating user becomes tenancy admin)
- OCI tenancy must be subscribed to the OCI region paired with the target AWS region
- Home region of OCI tenancy **cannot be changed** after creation

### Region Pairing Examples

- AWS US East (N. Virginia) ↔ OCI US East (Ashburn)
- AWS US West (Oregon) ↔ OCI US West (Phoenix)

See [Regional Availability](https://docs.oracle.com/en-us/iaas/Content/database-at-aws/oaaws-regions.htm) for full region pair list.

### Private Marketplace Access

If your organisation restricts to a private AWS marketplace, add Oracle AI Database@AWS to it before purchasing.

---

## Task 2: Request Private Offer

1. In AWS Console → Database → Oracle AI Database@AWS product page
2. Click **Request Private Offer** → redirected to Oracle website
3. Select region and submit contact information
4. Oracle Sales representative contacts you to agree on terms
5. Private offer is created and available in AWS Marketplace

Note: Public offer is **not currently available**.

---

## Task 3: Purchase Offer

1. In AWS Console → AWS Marketplace → **Private offers**
2. Find offer by Offer ID
3. Open offer → confirm type is **Private offer** → under **Available units** select **Commit** → click **Accept**
4. Purchase confirmation appears within seconds

**Verify subscription:**
- AWS Marketplace → Manage subscriptions → Active subscriptions → search "Oracle AI Database@AWS"

**Post-purchase timeline:** Oracle email arrives within **24 hours** with subject "Action Required: Welcome to New Oracle Cloud Service Subscription(s)". This email contains the account linking instructions.

---

## Task 4: Link OCI Account

### Option A: Create New OCI Account

1. Open activation email or in AWS Console select **Activate new Oracle account**
2. Click **Create new cloud account**
3. Complete OCI sign-up form:
   - Customer type, country, name, email, password
   - **Cloud Account Name** — unique OCI tenancy identifier
   - **Home Region** — must support Oracle AI Database@AWS; **immutable after creation**
4. Check acknowledgment that home region is permanent → **Create Cloud Account**
5. Confirmation email: "Your services are ready!"

### Option B: Link Existing OCI Account

1. Open activation email or in AWS Console select **Activate existing Oracle account**
2. Click **Add to existing cloud account**
3. Sign in to OCI account (MFA if enabled)
4. On **Add subscription** page → click **Add subscription**
5. Activates `ORACLEDBATAWS` subscription (~20 minutes)
6. Oracle sends email when activation is complete

**Warning:** De-linking an account after offer purchase requires Oracle Support and cannot be self-serviced. For POC/short-term use, create a new OCI account or a child tenancy.

### Subscribe to Additional OCI Regions

Required to provision resources in multiple AWS regions:

1. OCI Console → Regions (top-right) → **Manage regions**
2. Search for OCI region name (OCI names differ from AWS names)
3. Click **Actions** → **Subscribe** → confirm
4. If region supports specialised workloads: replicate Identity Domain to the new region

---

## Task 5: Verify Setup

After linking, verify three things in OCI Console:

### 1. Subscription Mapping

- Search "Subscription Mapping" in OCI Console
- Verify subscription type `ORACLEDBATAWS` is listed with a **Mapped date**

### 2. Limits, Quotas and Usage

- Navigate to **Limits, Quotas and Usage**
- Filter: Service = `Database`, Scope = availability domain, Subscription = ends in `ORACLEDBATAWS`, Compartment = root
- Confirm **Available** database infrastructure resources are listed

### 3. Compartments

- Navigate to **Compartments**
- Verify compartment starting with `Multicloudlink_AWS_` exists
- Verify child compartment with `resource-anchor` in name exists and status is **Active**

**CRITICAL**: Do NOT rename, modify, move, or delete the `Multicloudlink_AWS_` compartment or any of its child resources. The service cannot function if these are modified.

### 4. AWS Dashboard (Optional)

- AWS Console → Oracle AI Database@AWS → Getting started → **Dashboard**
- Available after `resource-anchor` compartment reaches Active state

---

## Task 6: My Oracle Cloud Support Registration

- Welcome email contains a **group ID number** required for registration
- Register via instructions in the welcome email or the OCI User Guide
- Prerequisites: active `ORACLEDBATAWS` subscription and welcome email

---

## Task 7: Role-Based Access Control (RBAC)

### Automatic Resources Created During Onboarding

Oracle AI Database@AWS automatically creates:
- A **Multicloud compartment** in OCI
- IAM policies for service operation
- All prefixed with `MulticloudLink`

**CRITICAL — Do NOT:**
- Modify, move, or delete resources prefixed with `MulticloudLink`
- Apply Deny IAM policies that target `MulticloudLink` resources or compartments

Violating these rules breaks the AWS–OCI service integration entirely.

### Recovery from Accidental Deny Policy

If a tenancy-wide deny policy blocks access:

**Via OCI Console** (sign in as default administrator group member — exempt from deny policies):
1. Identity & Security → Identity → Policies
2. Locate and edit or delete the deny policy
3. Test with OCI IAM Policy Simulator

**Via OCI CLI:**
```bash
oci iam policy update --policy-id <policy-id> \
  --statements '["Deny group Interns to inspect all-resources in tenancy"]'
```

---

## Task 8: Federation (Optional)

Identity Federation enables SSO for Oracle AI Database@AWS users. Without federation, users need separate OCI credentials accessible via the "Manage in OCI" button.

### Supported Protocols

OCI IAM supports SAML, OAuth 2.0, and OpenID Connect — compatible with any IDP supporting these protocols.

### Supported Identity Providers

| Provider | Notes |
|---|---|
| Azure Entra ID | Most common enterprise IdP |
| Okta | OCI IAM + Okta tutorials available |
| PingOne Identity | SSO setup guides available |
| Microsoft ADFS | OCI IAM + ADFS tutorials available |

### Setup High-Level Steps

1. **Configure Identity Provider** (e.g., Azure Entra ID):
   - Create Oracle AI Database@AWS groups following OCI naming conventions
   - Optionally sync groups to AWS
   - Add users to groups

2. **Configure AWS IAM:**
   - Define IAM policies based on RBAC requirements
   - Create groups (if not synced from IdP)
   - Associate policies with groups

3. **Configure OCI IAM:**
   - Configure federation with the chosen IdP
   - Verify provisioning automation created required policies and groups

**Recommended approach:** Principle of least privilege for all group assignments.

---

## Common Error Conditions

| Issue | Cause | Resolution |
|---|---|---|
| Cannot provision in AWS region | OCI tenancy not subscribed to paired region | Subscribe via OCI Console → Manage Regions |
| Onboarding fails despite correct permissions | AWS SCP overriding user permissions | Work with org-level admins to modify SCP |
| Need to de-link account | Switched to newer offer / wrong tenancy linked | Contact Oracle Support — cannot self-service |
| Home region wrong | Incorrect selection at account creation | Create new OCI account with correct region |
| Subscription activation pending | Normal processing | Wait ~20 minutes, check for email |
| Multicloudlink compartment missing | Activation not complete | Wait and re-check Verify Setup steps |
