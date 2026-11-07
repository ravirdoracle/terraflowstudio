# Oracle AI Database@Azure — Onboarding Guide

Source: Oracle Cloud Infrastructure Documentation — database-at-azure onboarding section
Source URL: https://docs.oracle.com/en-us/iaas/Content/database-at-azure/oaaonboard.htm

---

## Onboarding Overview

One-time setup process. Tasks completed sequentially:
1. Prerequisites → 2. Request/Purchase Offer → 3. Link Accounts → 4. Verify Setup → 5. Support Registration → 6. RBAC → 7. Federation (optional)

Offer types: **Private Offer** (negotiated with Oracle Sales) or **Public Offer / Pay As You Go** (Azure Marketplace directly, no Oracle Sales contact).

---

## Task 1: Prerequisites

### Azure Permissions by Task

| Task | Required Azure Persona | Permissions |
|---|---|---|
| Accept Private Offer | Billing Account Owner/Contributor OR Enterprise Administrator | Billing Account Owner (MCA) or Enterprise Administrator (EA) |
| Purchase | Subscription Owner/Contributor | Subscription Owner or Contributor |
| Purchase (Public Offer) | Billing Account Owner/Contributor | Billing Account Owner, Contributor |
| Link OCI Account | Subscription Owner/Contributor | Azure Contributor |
| Setup RBAC | EntraID Administrator | Groups Administrator, User Administrator |
| Identity Federation | EntraID Administrator | External Identity Provider Administrator, Groups Administrator, User Administrator |
| Multi-subscription | Owner/Contributor of Oracle Subscription | Oracle Subscriptions Manager Role |

### OCI Permissions by Task

| Task | Required OCI Persona | Permissions |
|---|---|---|
| Link OCI Account (existing) | OCI Administrator | Account Owner, Administrator |
| Link OCI Account (new) | User becomes Owner/Administrator automatically | — |
| Register with My Oracle Support | OCI Support Owner | OCI Support Owner |
| Identity Federation | Identity Domain Administrator | Identity Domain Administrator |

### Required Azure Resource Providers

Register ALL of these in your Azure subscription before onboarding:

| Resource Provider | Required For |
|---|---|
| `Oracle.Database` | Mandatory for all onboarding |
| `Microsoft.BareMetal` | Exadata Database Service & Autonomous AI Database |
| `Microsoft.Network` | All deployments |
| `Microsoft.Compute` | All deployments |

**Registration steps:**
1. Azure Portal → Subscriptions → select your subscription
2. Settings → Resource providers
3. Search "Oracle" → select `Oracle.Database` → click **Register**
4. Repeat for `Microsoft.BareMetal`, `Microsoft.Network`, `Microsoft.Compute`
5. Wait for "registered" status (may take several minutes)

### Account Requirements

- Azure subscription with appropriate billing type (MCA or EA)
- OCI tenancy (existing or new)
- My Oracle Support account
- Microsoft EntraID (for RBAC and optional federation)

---

## Public Offer vs Private Offer

| Aspect | Public Offer (PAYG) | Private Offer |
|---|---|---|
| Purchase method | Azure Marketplace directly | Oracle Sales negotiation required |
| OCI tenancy | Must create NEW (cannot link existing) | Can create new OR link existing |
| Commitment | None — start/stop anytime | Negotiated terms |
| Billing | Microsoft Azure invoice; counts toward MACC | Negotiated |
| License options | BYOL or ULA supported | Negotiated |
| Multi-subscription | Not supported | Supported |
| Azure Marketplace URL | azuremarketplace.microsoft.com | Private offer via Oracle Sales |

**One offer per Azure subscription** — cannot have both Public and Private simultaneously.

---

## Task 2 & 3: Request and Purchase Offer

### Private Offer
1. Contact Oracle Sales (or existing Oracle sales rep) to request a private offer
2. Oracle creates offer in AWS Marketplace
3. Azure Marketplace → Private offers → locate by Offer ID → **Commit** → **Accept**

### Public Offer
1. Navigate to Azure Marketplace Oracle AI Database@Azure listing
2. Purchase directly (Pay As You Go) — no Oracle Sales contact needed

---

## Task 4: Link OCI Account

### Option A: Create New OCI Account

1. Navigate to Oracle purchase details page in Azure portal
2. Select **Overview** tab → **Essentials** section → click "Not configured" under **Status**
3. Select **Create a new OCI account**
4. Enter admin credentials: email, first name, last name, password
5. Select **Apply**
6. Provide **Oracle Cloud account name** and **Home region** (immutable after creation)
7. System validates and links
8. Confirm **Status** under Oracle Cloud account section = **"Subscribed"**

### Option B: Link Existing OCI Account (Private Offer only)

1. Navigate to Oracle purchase details page → **Overview** → **Essentials** → "Not configured"
2. Select **Link an existing OCI account** → **Link account on OCI**
3. Sign in to OCI with existing credentials
4. Provide **Oracle Cloud account name** and **Home region**
5. Confirm Status = **"Subscribed"**

**Warning:** Public Offer accounts **cannot** be linked to Private Offers. De-linking requires Oracle Support.

### Account Status Indicators

| Status | Meaning |
|---|---|
| Not configured | No OCI account linked yet |
| Subscribed | Account successfully linked |
| Validated | Validation in progress |

---

## Task 5: Verify Setup

### 1. Subscription Mapping (OCI Console)
- Search "Subscription mapping" → confirm subscription type = `Oracle AI Database@Azure`
- Select Subscription ID → verify **Mapped date** is present

### 2. Limits, Quotas and Usage (OCI Console)
- Navigate to **Limits, Quotas and Usage**
- Filter: Service = `Database`, Scope = AD, Subscription = ends in `ORACLEDBATAZURE`, Compartment = root
- Confirm available database infrastructure resources listed

### 3. Compartments (OCI Console)
- Navigate to **Compartments**
- Verify compartment `MulticloudLink_ODBAA_*` exists with status **Active**
- Child compartments auto-created per Azure subscription when resources deployed

**CRITICAL — DO NOT:**
- Rename or modify the `MulticloudLink_ODBAA_` compartment
- Move or delete service-managed resources within it
- Apply IAM Deny policies targeting `MulticloudLink` resources or compartments

Violation breaks the Azure–OCI service integration completely.

### 4. Azure Portal
- Azure Console → search "Oracle AI Database@Azure" → confirm product page is accessible

---

## Task 6: My Oracle Cloud Support Registration

- Welcome email contains group ID number needed for registration
- Follow link in welcome email or OCI User Guide

---

## Task 7: Role-Based Access Control (RBAC)

### Azure Groups for Autonomous AI Database

| Azure Group Name | Azure Role | Purpose |
|---|---|---|
| `odbaa-adbs-db-administrators` | Oracle.Database Autonomous Database Administrator | Manage all Autonomous Database resources in Azure |
| `odbaa-db-family-administrators` | None | Manage all Oracle DB Service resources in OCI (replicated) |
| `odbaa-db-family-readers` | Oracle.Database Reader | View all Oracle Database resources in OCI (replicated) |
| `odbaa-network-administrators` | None | Manage network resources in OCI (replicated) |
| `odbaa-costmgmt-administrators` | None | Manage cost/billing resources in OCI (replicated) |

### Azure Groups for Exadata Database Service

| Azure Group Name | Azure Role | Purpose |
|---|---|---|
| `odbaa-exa-infra-administrators` | Oracle.Database Exadata Infrastructure Administrator | Manage all Exadata resources in Azure (includes vm-cluster permissions) |
| `odbaa-vm-cluster-administrators` | Oracle.Database VmCluster Administrator | Manage VM cluster resources in Azure |
| `odbaa-db-family-administrators` | None | Manage Oracle DB Service resources in OCI (replicated) |
| `odbaa-db-family-readers` | Oracle.Database Reader | View Oracle Database resources in OCI (replicated) |
| `odbaa-exa-cdb-administrators` | None | Manage CDB resources in OCI (replicated) |
| `odbaa-exa-pdb-administrators` | None | Manage PDB resources in OCI (replicated) |
| `odbaa-network-administrators` | None | Manage network resources in OCI (replicated) |
| `odbaa-costmgmt-administrators` | None | Manage cost/billing resources in OCI (replicated) |

**Deployment scope:**
- Public Offer (PAYG) customers: Autonomous AI Database groups only
- Private Offer customers: Both Autonomous AI Database AND Exadata groups

### Azure Portal Group Creation Steps

1. Azure Portal → search "EntraID" → Microsoft Entra ID → **Groups** → **All groups** → **New group**
2. Group name: use value from table (e.g., `odbaa-adbs-db-administrators`)
3. Add description from "Purpose" column → **Create**
4. Repeat for all required groups
5. Azure Portal → Subscriptions → select subscription → **Access Control (IAM)**
6. **+Add** → **Add role assignment** → search role (e.g., `Oracle.Database Reader`)
7. **Next** → **+Select Members** → search "odbaa" → select group → **Review + assign**
8. Repeat for all group-role assignments

### MulticloudLink Resources — Critical Rules

During OCI account linking, Oracle auto-creates:
- Multicloud compartment (prefix: `MulticloudLink`)
- IAM policies (prefix: `MulticloudLink`)

**Never modify, move, or delete these. Never apply Deny policies targeting them.**

Recovery if accidentally locked out:
1. Sign in as default administrator group member (exempt from deny policies)
2. OCI Console → Identity & Security → Identity → Policies
3. Edit or delete the deny policy
4. Or via OCI CLI: `oci iam policy update --policy-id <id> --statements '[...]'`

---

## Task 8: Identity Federation (Optional)

Federation enables SSO to OCI using Azure Entra ID credentials. Without it, users need separate OCI credentials via the "Manage in OCI" button.

Supported protocols: SAML, OAuth 2.0, OpenID Connect

**Supported providers:** Azure Entra ID, Okta, PingOne Identity, Microsoft ADFS

### High-Level Setup

1. **Azure Entra ID:** Create Oracle AI Database@Azure groups following OCI naming conventions; add users
2. **Azure IAM:** Define policies based on RBAC requirements; associate groups
3. **OCI IAM:** Configure federation with Azure Entra ID; verify provisioning created required policies/groups

---

## Common Error Conditions

| Issue | Cause | Resolution |
|---|---|---|
| Cannot register Azure resource provider | Insufficient Azure permissions | Subscription Owner or Contributor required |
| Status stuck at "Not configured" | Account linking not initiated | Complete linking from Oracle purchase details page |
| Cannot link existing OCI account to Public Offer | Public Offer requires new tenancy | Create new OCI account instead |
| Compartment MulticloudLink_ODBAA_ missing | Activation incomplete | Wait and re-check Verify steps |
| RBAC groups not visible in Azure | Groups not created yet | Complete Azure portal group creation steps |
| OCI access blocked by deny policy | Tenant-wide deny applied to MulticloudLink | Use admin group (exempt) to remove deny policy |
