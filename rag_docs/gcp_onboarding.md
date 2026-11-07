# Oracle AI Database@Google Cloud — Onboarding Guide

Source: Oracle Cloud Infrastructure Documentation — database-at-gcp onboarding section
Source URL: https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/onboard.htm

---

## Onboarding Overview

One-time setup process. Tasks completed sequentially:
1. Prerequisites → 2. Request Offer → 3. Purchase → 4. Link OCI Account → 5. Verify → 6. Support Registration → 7. RBAC → 8. Federation (optional)

Offer types: **Private Offer** (negotiated with Oracle Sales) or **Public Offer / Pay As You Go** (Google Cloud Marketplace directly).

---

## Task 1: Prerequisites

### GCP Permissions by Task

| Task | Persona | Required GCP Permissions |
|---|---|---|
| Request Offer (Private) | GCP Administrator | Project owner or contributor |
| Accept Private Offer | GCP Billing Administrator | `roles/billing.admin` OR (`roles/billing.user` AND `roles/consumerprocurement.orderAdmin`) on billing account |
| Public Offer (PAYG) | GCP Administrator | Billing Account Owner, Contributor |
| Subscribe Standard/Public Offer | GCP Billing Administrator | `roles/billing.admin` OR `roles/consumerprocurement.orderAdmin` on billing account |
| Link OCI Account | GCP Administrator | Project owner or editor |
| Setup RBAC | GCP IAM & Admin Administrator | Groups Administrator, User Administrator |
| Identity Federation | GCP IAM & Admin Administrator | External Identity Provider Administrator, Groups Administrator, User Administrator |

### OCI Permissions by Task

| Task | Persona | Required OCI Permissions |
|---|---|---|
| Link OCI Account (existing) | OCI Administrator | Account Owner, Administrator |
| Link OCI Account (new) | User becomes Owner/Administrator automatically | — |
| Register with My Oracle Support | OCI Support Owner | OCI Support Owner |
| Verify Subscription/Limits | OCI Support Owner | OCI Support Owner |
| Identity Federation | OCI Identity Domain Administrator | Identity Domain Administrator |

### Account Requirements

- Google Cloud project for deploying Oracle AI Database@GCP resources
- Google Cloud billing account (becomes primary billing account for the offer; all resources in projects sharing this billing account can be deployed)
- OCI tenancy (existing for private offer, new for public/PAYG offer)

### Public vs Private Offer — OCI Account Rule

- **Private Offer**: Can create NEW or link EXISTING OCI account
- **Pay As You Go (Public)**: Must create NEW OCI account — linking existing is NOT supported

---

## Task 2 & 3: Request and Purchase Offer

### Private Offer
1. GCP Console → Marketplace → Oracle AI Database@GCP product page → request offer via Oracle Sales
2. Google Cloud Marketplace → Your orders → locate offer → accept

### Public Offer (PAYG)
1. Google Cloud Marketplace → Oracle AI Database@GCP → purchase directly
2. No Oracle Sales contact required

---

## Task 4: Link OCI Account

### Prerequisites
- Google Cloud project role: **Owner** OR **Editor**
- Active "Active" status order in Google Cloud Marketplace

### Workflow A: Create New OCI Account (required for PAYG; optional for Private)

1. `https://console.cloud.google.com` → search "Marketplace" → **Your orders**
2. Select "Oracle AI Database@Google Cloud"
3. Select **Manage on Console**
4. On Overview page → select **Create Account**
5. Complete OCI Account Signup Form:
   - Customer Type: Personal or Business
   - Country, Name, Address, Email, Password
   - **Cloud Account Name**: unique OCI tenancy identifier
   - **Home Region**: must support Oracle AI Database@GCP — **immutable after creation**
6. Check acknowledgment: "I understand the OCI home region can't be changed later"
7. Click **Create Cloud Account**
8. Return to GCP console — message: "Please wait for your account linking to become active"
9. Activation takes a few minutes

### Workflow B: Link Existing OCI Account (Private Offer only)

1. `https://console.cloud.google.com` → Marketplace → **Your orders**
2. Select "Oracle AI Database@Google Cloud"
3. Select **Link Existing Account**
4. Sign in dialog → enter OCI account credentials
5. System authenticates and links account

**Key constraint:** PAYG offers do NOT support linking existing OCI accounts.

---

## Task 5: Verify Setup

### 1. Subscription Mapping (OCI Console)
- Search "Subscription mapping" → confirm subscription type = `ORACLEDBATGOOGLE`
- Select Subscription ID → verify **Mapped date** is present

### 2. Limits, Quotas and Usage (OCI Console)
- Navigate to **Limits, Quotas and Usage** → **Edit filter**
- Filter: Service = `Database`, Scope = AD, Subscription = ends in `ORACLEDBATGOOGLE`, Compartment = root
- Confirm database service resources listed in table

### 3. Multicloud Link Compartment (OCI Console)
- Navigation Menu → Identity & Security → Identity → **Compartments**
- Verify compartment starting with `MulticloudLink_ODBG_` exists
- Auto-created during account linking

### 4. Google Cloud Console Verification
- GCP Console → Marketplace → **Your Orders** → select billing account used during onboarding
- Find `Oracle Database@Google Cloud` order

| Field | Expected Value |
|---|---|
| Status | Active |
| Provider | Oracle |
| Plan | Private Offer Monthly Subscription (or PAYG equivalent) |
| Start/End dates | Valid subscription period |

- Search "Oracle AI Database@Google Cloud" in GCP to access product page

---

## Task 6: My Oracle Cloud Support Registration

- Welcome email contains group ID required for registration
- Follow instructions in email or OCI User Guide

---

## Task 7: Role-Based Access Control (RBAC)

### Autonomous AI Database Groups

| Group Name | GCP Role Assignment | Purpose |
|---|---|---|
| `odbg-adbs-db-administrators` | Oracle AI Database@GCP Autonomous AI Database Admin | Manage all Autonomous Database resources in GCP |
| `odbg-adbs-db-readers` | Oracle AI Database@GCP Autonomous AI Database Viewer | View all Autonomous Database resources in GCP |
| `odbg-db-family-administrators` | Oracle AI Database@GCP admin | Manage all Oracle AI Database resources in OCI (replicated) |
| `odbg-db-family-readers` | Oracle AI Database@GCP viewer | View all Oracle AI Database resources in OCI (replicated) |
| `odbg-network-administrators` | N/A | Network resource admins in OCI (replicated) |
| `odbg-costmgmt-administrators` | N/A | Cost/billing admins in OCI (replicated) |

### Exadata Database Service Groups

| Group Name | GCP Role Assignment | Purpose |
|---|---|---|
| `odbg-exa-infra-administrators` | Oracle AI Database@GCP Exadata Infrastructure Admin | Manage all Exadata resources in GCP |
| `odbg-exa-infra-readers` | Oracle AI Database@GCP Exadata Infrastructure Viewer | View all Exadata resources in GCP |
| `odbg-vm-cluster-administrators` | Oracle AI Database@GCP VM Cluster Admin | Manage VM Clusters in GCP |
| `odbg-vm-cluster-readers` | Oracle AI Database@GCP VM Cluster Viewer | View VM Clusters in GCP |
| `odbg-exa-cdb-administrators` | None | Manage CDB resources in OCI (replicated) |
| `odbg-exa-pdb-administrators` | None | Manage PDB resources in OCI (replicated) |
| `odbg-db-family-administrators` | Oracle AI Database@GCP admin | Manage Oracle AI Database resources in OCI (replicated) |
| `odbg-db-family-readers` | Oracle AI Database@GCP viewer | View Oracle database resources in OCI (replicated) |
| `odbg-network-administrators` | None | Network admins in OCI (replicated) |
| `odbg-costmgmt-administrators` | None | Cost/billing admins in OCI (replicated) |

### Exadata Database Service on Exascale Infrastructure Groups

| Group Name | GCP Role Assignment | Purpose |
|---|---|---|
| `odbg-exascale-db-storage-vault-administrators` | Exascale Infrastructure Storage Vault Admin | Manage Exascale Storage Vault resources in GCP |
| `odbg-exascale-db-storage-vault-readers` | Exascale Infrastructure Storage Vault Viewer | View Exascale Storage Vault resources |
| `odbg-exadb-vm-cluster-administrators` | Exascale Infrastructure VM Cluster Admin | Manage ExaDB VM Clusters in GCP |
| `odbg-exadb-vm-cluster-readers` | Exascale Infrastructure VM Cluster Viewer | View ExaDB VM Clusters |
| `odbg-exa-cdb-administrators` | None | CDB admins in OCI (replicated) |
| `odbg-exa-pdb-administrators` | None | PDB admins in OCI (replicated) |

**Deployment scope:**
- PAYG (public offer): Autonomous Database groups only
- Private offer: complete both Autonomous Database AND relevant Exadata groups

### GCP Group Creation Steps

1. `https://admin.google.com/ac/groups` → **Add custom SAML app** (or Google Admin Console → Groups)
2. Create group with name from table (e.g., `odbg-adbs-db-administrators`)
3. Group email: `odbg-adbs-db-administrators@<your-domain.com>`
4. Description: use "Purpose" column from table
5. GCP Console → search "IAM & Admin" → **IAM** → **Grant access**
6. Add principal: group email; assign role from table → **SAVE**
7. Repeat for all groups

### MulticloudLink Resources — Critical Rules

During OCI account linking, Oracle auto-creates:
- Multicloud compartment (prefix: `MulticloudLink`)
- IAM policies (prefix: `MulticloudLink`)

**CRITICAL — Never modify, move, or delete these. Never apply IAM Deny policies targeting them.**

Violation causes complete Oracle AI Database@GCP service failure.

Recovery if accidentally locked out:
1. Sign in as default administrator group member (exempt from deny policies)
2. OCI Console → Identity & Security → Identity → Policies
3. Edit or delete the deny policy
4. Or via CLI: `oci iam policy update --policy-id <id> --statements '[...]'`

---

## Task 8: Identity Federation (Optional)

Federation enables SSO to OCI using Google Cloud IAM & Admin credentials via SAML 2.0. Without it, most day-to-day GCP operations don't require OCI Console access.

### Complete SAML Federation Setup

**Phase 1 — OCI Console:**
1. Identity & Security → Domains → Default domain → Security → Identity providers
2. Add IdP → **Add SAML IdP** → enter name (e.g., "Google Cloud Federation") → Next — keep window open

**Phase 2 — Google Cloud Admin Console (`https://admin.google.com/ac/apps/unified`):**
3. **Add custom SAML app**
4. App name: `OracleCloudFederation`; Description: "Configures identity federation between GCP and OCI for Oracle AI Database@GCP"
5. Select **DOWNLOAD METADATA** (saves XML file) → Continue

**Phase 3 — Back in OCI:**
6. Import IdP metadata → upload the XML file
7. Select **Export SAML metadata** → Manual export → copy and save **Provider ID** and **Assertion consumer service URL**

**Phase 4 — Back in Google Cloud Admin:**
8. Service provider details: set `ACS URL` and `Entity ID` from Step 7 → Continue
9. Add attribute mappings:

| Google Cloud Attribute | App Attribute |
|---|---|
| First name | FirstName |
| Last name | LastName |
| Primary email | PrimaryEmail |

10. Group membership → Add Mapping → App attribute = `MemberOf`; add all RBAC groups → Finish
11. User access → Service status = **ON for everyone** → Save

**Phase 5 — Back in OCI:**
12. Map user identity: Name ID format = Email address; IdP attribute = SAML assertion Name ID; Domain attribute = Username
13. Review and Create IdP → **Activate**
14. Add to IdP policy → Default Identity Provider Policy → Edit IdP rule → add "Google Cloud Federation" alongside Username-Password → Save

**Phase 6 — Just-In-Time (JIT) Provisioning:**
15. IdP details page → Configure JIT → enable JIT provisioning
16. Select: Create a new identity domain user AND Update the existing identity domain user
17. Map JIT attributes:

| IdP Attribute | Maps To OCI |
|---|---|
| NameID | userName |
| LastName | familyName |
| PrimaryEmail | primaryEmailAddress |
| FirstName | firstName |

18. Enable group mapping: attribute name = `MemberOf`; merge with existing; ignore missing groups → Save

**Test:** Sign out of OCI → login screen → "Or sign in with" → select Google Cloud Federation → authenticate with GCP credentials.

### SAML Config Summary

| Parameter | Value |
|---|---|
| Protocol | SAML 2.0 |
| Name ID Format | Email Address |
| JIT Provisioning | Enabled |
| Group Mapping Attribute | MemberOf |
| Identity Provider | Google Cloud IAM & Admin |

---

## Common Error Conditions

| Issue | Cause | Resolution |
|---|---|---|
| Cannot link existing OCI account | Using PAYG/Public offer | Create new OCI account instead |
| Subscription type not showing `ORACLEDBATGOOGLE` | Activation not complete | Wait and retry; check GCP Marketplace order status |
| `MulticloudLink_ODBG_` compartment missing | Account linking incomplete | Wait; verify GCP order status = Active |
| GCP billing role insufficient for offer acceptance | Wrong billing role | Requires `roles/billing.admin` or `roles/consumerprocurement.orderAdmin` |
| OCI access blocked by deny policy | Tenant-wide deny on MulticloudLink | Sign in as admin group member; remove deny policy |
| Federation login fails | JIT or attribute mapping misconfigured | Verify SAML attribute mappings and group membership config |
