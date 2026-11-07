# Terraflow Studio v5.6

**Oracle AI DB@Cloud · Terraform Generator**

A Python/Flask web app that generates production-ready, modular Terraform/OpenTofu for Oracle Database across AWS, GCP, Azure, and OCI Data Guard. Fill in the form, see live HCL output, and download a ZIP or push directly to GitHub.

---

## Features

- **Multi-cloud** — AWS, GCP, Azure, and OCI Data Guard pages; cloud switcher in header
- **Multi-instance** — add as many networks, infras, peerings, and clusters as needed; all auto-wired in root `main.tf`
- **Live output** — Terraform HCL generates in real time as you fill in fields; file tree + syntax-highlighted code viewer
- **✦ AI fill** — describe your infrastructure in plain English and the AI fills the entire form
- **✦ Explain** — click Explain on any file for an AI explanation of what that Terraform does and why
- **✦ Plan Analyser** — paste `terraform plan` output for an AI risk + change summary
- **✦ Error Troubleshooter** — paste a Terraform error and get root cause + fix steps
- **✦ Security Review** — AI security scan of the current config with severity-graded findings
- **RAG knowledge base** — AI answers grounded in curated ODB documentation (BM25 or ChromaDB)
- **RAG admin UI** — upload PDF/DOCX/PPTX/Markdown, manage docs, search, rebuild index at `/rag`
- **Info Hub** — ask any Oracle AI DB@Cloud question, cloud-filtered, at `/hub`
- **CIDR Planner** — calculate ExaCS IP requirements, suggest non-overlapping CIDRs at `/cidr`
- **Customer config persistence** — save/load configs by customer name; FileStore (default) or CouchDB backend
- **Validation** — per-field inline errors with card highlighting; Validate & Generate All per tab
- **Testing** — 🧪 Test button runs 451 functional checks + mock Terraform validator per config
- **GitHub push** — push generated Terraform directly to a GitHub repo via the Contents API
- **Load ZIP** — load a previously downloaded ZIP back into the form to restore full configuration
- **CloudFormation** — generate AWS CloudFormation YAML for ODB resources (AWS page only)
- **Docker Compose** — single `docker compose up` for app + CouchDB

---

## Pages

| URL | Description |
|-----|-------------|
| `/` | Product chooser — select cloud or tool |
| `/aws` | Oracle AI DB@AWS — ODB networks, Exadata, VM Clusters, AVMC, DB Home/CDB/PDB |
| `/gcp` | Oracle AI DB@GCP — ODB networks, Exadata, VM Clusters, DB Home/CDB/PDB |
| `/azure` | Oracle AI DB@Azure — Virtual Networks, Oracle-delegated Subnets, Exadata, VM Clusters |
| `/dg` | OCI Data Guard — Multi-AZ (LPG) and Cross-Region (DRG + RPC) networking |
| `/cidr` | CIDR Planner — IP requirement calculator for ExaCS deployments |
| `/rag` | RAG admin — upload docs, manage index, test search |
| `/hub` | Info Hub — RAG-powered Q&A across all clouds |

---

## Supported Resources

### AWS (`hashicorp/aws ≥ 6.42.0`)

| Tab | Resource | Module name |
|-----|----------|-------------|
| 1 | `aws_odb_network` | `odb_network` |
| 2 | `aws_odb_cloud_exadata_infrastructure` | `odb_exaInfra` |
| 3 | `aws_odb_network_peering_connection` | `odb_peering` |
| 4 | `aws_odb_cloud_vm_cluster` | `odb_vmcluster` |
| 5 | `aws_odb_cloud_autonomous_vm_cluster` | `odb_avmcluster` |
| 6 | OCI DB Home / CDB / PDB (`oracle/oci` provider) | `oci_db_home` / `oci_cdb` / `oci_pdb` |

### GCP (`hashicorp/google ≥ 6.0.0`, `oracle/oci ≥ 6.0.0`)

| Tab | Resource | Module name |
|-----|----------|-------------|
| A | `google_oracle_database_odb_network` + client & backup subnets | `gcp-odb-network` |
| C | `google_oracle_database_cloud_exadata_infrastructure` | `gcp-exadata-infra` |
| D | `google_oracle_database_exadb_vm_cluster` | `gcp-vm-cluster` |
| E | OCI DB Home / CDB / PDB (`oracle/oci` provider) | `<name>_dbhome` / `_cdb` / `_pdb` |

### Azure (`hashicorp/azurerm ≥ 4.9.0`)

| Tab | Resource | Module name |
|-----|----------|-------------|
| A | `azurerm_virtual_network` | `azure_vnet` |
| B | `azurerm_oracle_exadata_infrastructure` | `azure_exainfra` |
| C | `azurerm_oracle_cloud_vm_cluster` | `azure_vmcluster` |

### OCI Data Guard (`oracle/oci ≥ 6.0.0`)

| Tab | Type | What it generates |
|-----|------|-------------------|
| A | Multi-AZ | LPG pair, NSG rules (TCP 1521), default route table entries — standalone dir |
| B | Cross-Region | Hub VCNs, LPGs, DRGs, DRG attachments, Remote Peering Connections, transit route tables — 3-module structure |

---

## Generated Output Structure

### AWS

```
terraflow-studio-aws/
├── main.tf                    # root — wires all modules
├── variables.tf
├── terraform.auto.tfvars
└── modules/
    ├── odb_network/           # aws_odb_network
    ├── odb_exaInfra/          # aws_odb_cloud_exadata_infrastructure
    ├── odb_peering/           # aws_odb_network_peering_connection
    ├── odb_vmcluster/         # aws_odb_cloud_vm_cluster
    ├── odb_avmcluster/        # aws_odb_cloud_autonomous_vm_cluster
    ├── oci_db_home/           # oci_database_db_home
    ├── oci_cdb/               # oci_database_database (CDB)
    └── oci_pdb/               # oci_database_pluggable_database (PDB)
```

### GCP

```
terraflow-studio-gcp/
├── main.tf
├── variables.tf
├── terraform.auto.tfvars
├── README.md
└── modules/
    ├── gcp-odb-network/          # google_oracle_database_odb_network (shared)
    ├── gcp-exadata-infra/        # google_oracle_database_cloud_exadata_infrastructure (shared)
    ├── gcp-vm-cluster/           # google_oracle_database_exadb_vm_cluster (shared)
    ├── <name>_dbhome/            # oci_database_db_home (per-instance)
    ├── <name>_cdb/               # oci_database_database
    └── <name>_pdb/               # oci_database_pluggable_database
```

### Azure

```
terraflow-studio-azure/
├── main.tf
├── variables.tf
├── terraform.auto.tfvars
└── modules/
    ├── <vnet_name>/              # azurerm_virtual_network
    ├── <infra_name>/             # azurerm_oracle_exadata_infrastructure
    └── <cluster_name>/           # azurerm_oracle_cloud_vm_cluster
```

### OCI Data Guard — Multi-AZ

```
terraflow-studio-dg/
└── dg_multi_az_<name>/
    ├── main.tf          # LPG pair, NSG rules, default route tables
    ├── variables.tf
    ├── terraform.tfvars
    ├── outputs.tf
    └── README.md        # import commands + apply guide
```

### OCI Data Guard — Cross-Region

```
terraflow-studio-dg/
└── dg_cross_region_<name>/
    ├── main.tf          # 2x provider aliases + 3 module calls
    ├── variables.tf
    ├── terraform.tfvars
    ├── README.md        # staged apply guide + terraform import commands
    └── modules/
        ├── oci-dg-region/     # reusable — instantiated for primary AND dr
        │   ├── main.tf        # Hub VCN, LPGs, DRG, route tables, NSG rules
        │   ├── variables.tf
        │   └── outputs.tf     # hub_vcn_id, drg_id, lpg IDs
        └── oci-dg-peering/    # activates after both regions via depends_on
            ├── main.tf        # DR RPC (acceptor) + Primary RPC (sets peer_id)
            ├── variables.tf
            └── outputs.tf     # rpc IDs, peering_status → "PEERED"
```

---

## Quick Start

```bash
git clone https://github.com/ravirdoracle/terraflowstudio.git
cd terraflowstudio

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python app.py
# open http://localhost:8000
```

---

## Run the container (Podman or Docker)

See [Container run and publishing instructions](CONTAINERS.md) for loading the image,
running on `http://localhost:8080` or `http://<host-ip>:8080`, saving configuration
data, and publishing to GitHub Container Registry.

## Docker Compose (recommended)

```bash
# Edit .env first — set COUCHDB_USER, COUCHDB_PASSWORD, and optionally LLM_API_KEY
docker compose up -d --build
# open http://localhost:5000
```

`docker-compose.yml` starts the Flask app and a CouchDB instance. The app auto-detects CouchDB at `$COUCHDB_URL` and falls back to FileStore if unreachable.

---

## AI Features

### ✦ Fill form with AI

Type a plain-English description in the AI bar at the top of any product page:

> *"Cross-region Data Guard from Ashburn to Portland, compartment ocid1.compartment.oc1..xyz"*

The AI fills in all form fields and explains what it configured.

Supported LLM providers: **Anthropic**, **OpenAI** (and compatible — Groq, etc.), **Gemini**, **Ollama** (local), **OCI GenAI**.

### ✦ Explain Terraform

Select any file in the output panel and click **✦ Explain**. Works on all file types including README.md, module main.tf, variables.tf.

### ✦ AI Tools (Plan · Fix Error · Security)

Accessible from the LLM bar on each product page:
- **Plan** — paste `terraform plan` output, get a risk-graded change summary
- **Fix Error** — paste a Terraform error, get root cause + numbered fix steps
- **Security** — scan current config, get severity-graded findings (critical/high/medium/low/info)

---

## Environment Variables

Edit `.env`:

```bash
# ── CouchDB (optional — FileStore used if not set) ──
COUCHDB_URL=http://couchdb:5984
COUCHDB_USER=admin
COUCHDB_PASSWORD=changeme
COUCHDB_DB=terraflow_studio_configs

# ── LLM provider ───────────────────────────────────
# Provider: anthropic | openai | gemini | ollama | oci_genai
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=                    # optional: Groq, Vertex AI, etc.
LLM_MAX_TOKENS=2048
LLM_TEMPERATURE=0.2
LLM_TIMEOUT=60

# ── OCI GenAI (oci_genai provider only) ────────────
OCI_GENAI_COMPARTMENT_ID=ocid1.compartment.oc1..
OCI_GENAI_REGION=us-chicago-1
OCI_GENAI_AUTH=config_file       # config_file | instance_principal | resource_principal

# ── Embeddings (enables ChromaDB semantic RAG) ─────
# EMBEDDING_PROVIDER=ollama      # ollama | openai | gemini
# EMBEDDING_MODEL=nomic-embed-text
# EMBEDDING_BASE_URL=http://localhost:11434

# ── GitHub push ─────────────────────────────────────
GITHUB_TOKEN=ghp_...
GITHUB_REPO=myorg/my-terraform-repo
GITHUB_BRANCH=main
GITHUB_BASE_PATH=terraform

# ── Terraform / OpenTofu binary (for TF CLI tests) ──
TERRAFORM_PATH=terraform         # or full path
OPENTOFU_PATH=tofu
```

---

## RAG Knowledge Base

AI answers are grounded in `rag_docs/` — curated Markdown covering all supported clouds:

| File | Contents |
|------|----------|
| `aws_odb_network.md` | CIDR constraints, DNS, s3_access defaults |
| `aws_exadata_infra.md` | Shapes, maintenance windows, NON_ROLLING patching |
| `aws_vm_cluster.md` | Required fields, db_servers, immutable fields |
| `aws_hadr.md` | Multi-AZ HA + Cross-Region DR — LPG, DRG, RPC patterns |
| `aws_onboarding.md` | Subscription sharing, account linking |
| `aws_subscription_sharing.md` | Cross-account ODB access |
| `gcp_resources.md` | Full GCP resource schemas, immutable fields, CIDR rules |
| `gcp_hadr.md` | GCP HA/DR — DRG peering, OCI LPG, GCP-native paths |
| `gcp_onboarding.md` | GCP project setup, enabling ODB API |
| `azure_resources.md` | Azure resource schemas, delegated subnet requirements |
| `azure_hadr.md` | Azure cross-zone + cross-region Data Guard |
| `azure_network_design.md` | VNet sizing, peering, Oracle-delegated subnets |
| `azure_onboarding.md` | Azure subscription + ODB service setup |
| `maa_multicloud.md` | Oracle MAA best practices across all three clouds |
| `multicloud_hub.md` | Multi-cloud topology patterns |

**RAG auto-builds on first use.** To force a rebuild: `POST /api/rag/rebuild`.

Two backends:
- **BM25** (default) — pure Python, no extra dependencies, section-aware with title-boost scoring
- **ChromaDB** (semantic) — install `chromadb` and set `EMBEDDING_PROVIDER`

---

## API Reference

### Pages

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Product chooser |
| `GET` | `/aws` | ODB@AWS page |
| `GET` | `/gcp` | AI DB@GCP page |
| `GET` | `/azure` | AI DB@Azure page |
| `GET` | `/dg` | OCI Data Guard page |
| `GET` | `/cidr` | CIDR Planner |
| `GET` | `/rag` | RAG admin UI |
| `GET` | `/hub` | Info Hub |

### Core generation

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/generate` | Generate a single file; body: `{ cloud, file_key, … }` → `{ content }` |
| `POST` | `/api/files` | List the paths this payload generates → `{ files: [...] }`; the output-panel file tree is built from it, so tree entries always match valid `file_key` values |
| `POST` | `/api/validate` | Validate fields for one tab → `{ valid, errors, errors_by_module }` |
| `POST` | `/api/download` | Stream ZIP of all generated files |
| `POST` | `/api/load-zip` | Parse a downloaded ZIP back into config JSON |

### Config persistence

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/config/save` | Save payload for `{ customer, cloud }` |
| `GET` | `/api/config/load/<customer>/<cloud>` | Load saved config |
| `GET` | `/api/config/list` | List all saved customers |
| `DELETE` | `/api/config/delete/<customer>/<cloud>` | Delete a config |
| `GET` | `/api/config/backend` | Returns active backend (`filestore` or `couchdb`) |

### AI

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/llm/fill` | Fill form from natural language → `{ payload, explanation }` |
| `POST` | `/api/llm/explain` | Explain a Terraform file → `{ explanation }` |
| `POST` | `/api/llm/ask` | Ask a free-form question → `{ answer }` |
| `GET` | `/api/llm/info` | LLM provider info + availability |
| `POST` | `/api/ai/security-review` | Security scan of current config → findings + score |
| `POST` | `/api/ai/explain-plan` | Analyse `terraform plan` output → changes + risks |
| `POST` | `/api/ai/troubleshoot` | Diagnose terraform error → root cause + fix steps |

### RAG

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/rag/stats` | Index stats: `{ backend, n_docs, n_chunks }` |
| `POST` | `/api/rag/rebuild` | Force re-index all `rag_docs/` |
| `POST` | `/api/rag/search` | Search: `{ query, k }` → top-k chunks |
| `GET` | `/api/rag/docs` | List indexed documents |
| `POST` | `/api/rag/upload` | Upload a new RAG document (PDF/DOCX/PPTX/MD) |
| `DELETE` | `/api/rag/docs/<filename>` | Remove a document from the index |

### Testing & GitHub

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/test` | Run functional tests against payload or saved config |
| `POST` | `/api/tf-validate` | Mock Terraform structural validator |
| `POST` | `/api/tf-cli` | Run `terraform fmt + init + validate` via CLI binary |
| `POST` | `/api/github/push` | Push generated files to GitHub repo |
| `GET` | `/api/github/info` | GitHub integration status |

---

## Mock Terraform Validator

Pure-Python structural validator — no Terraform binary required. Checks:

| Group | What is checked |
|-------|----------------|
| File Structure | All required files present per module |
| HCL Syntax | Balanced `{}[]()`, no empty assignments |
| Provider | Correct provider source + version constraint |
| Resource Schema | Resource types match provider schemas; required args present |
| Variable Resolution | Every `var.<n>` in `main.tf` resolves to a declared variable |
| Output Validity | Outputs reference known resource attributes |
| Module Cross-References | `source` paths correct; `module.<n>.<attr>` resolves to declared outputs |
| tfvars Completeness | Variables without tfvars values flagged as warnings |

---

## Test Suite

451 tests — run with:

```bash
python -m unittest tests/test_all.py
```

Covers AWS, GCP, Azure, OCI DG, API routes, storage backends, mock TF validator, and CloudFormation generation.

---

## Project Structure

```
odb_terraform_app/
├── app.py                  # Flask app — all routes
├── llm.py                  # LLM adapter (Anthropic, OpenAI, Gemini, Ollama, OCI GenAI)
├── rag.py                  # RAG engine — BM25 or ChromaDB
├── github.py               # GitHub Contents API integration
├── store.py                # FileStore + CouchDBStore
├── tf_validator.py         # Mock Terraform structural validator
├── requirements.txt
├── docker-compose.yml
├── .env                    # Config (not in git)
├── generators/             # Cloud-specific Terraform generators
│   ├── aws_gen.py          # AWS ODB resources + CloudFormation
│   ├── gcp_gen.py          # GCP ODB resources
│   ├── azure_gen.py        # Azure ODB resources
│   ├── oci_gen.py          # OCI DB Home / CDB / PDB
│   └── oci_dg_gen.py       # OCI Data Guard (Multi-AZ + Cross-Region)
├── rag_docs/               # Knowledge base markdown files (git-tracked)
├── data/                   # Runtime: configs, RAG index (not in git)
├── templates/
│   ├── home.html           # Product chooser
│   ├── base.html           # Shared layout (used by GCP page)
│   ├── aws.html            # ODB@AWS page (standalone)
│   ├── gcp.html            # AI DB@GCP page (standalone)
│   ├── azure.html          # AI DB@Azure page (standalone)
│   ├── dg.html             # OCI Data Guard page (standalone)
│   ├── cidr.html           # CIDR Planner
│   ├── rag.html            # RAG admin UI
│   ├── hub.html            # Info Hub
│   └── tf/                 # Jinja2 Terraform templates
│       ├── aws_odb_network/
│       ├── aws_exadata_infra/
│       ├── aws_peering/
│       ├── aws_vm_cluster/
│       ├── aws_avmcluster/
│       ├── aws_dg_multi_az/
│       ├── aws_dg_cross_region/
│       ├── aws_root/
│       ├── oci_db_home/ · oci_cdb/ · oci_pdb/
│       ├── oci_dg_region/ · oci_dg_peering/ · oci_dg_root/
│       ├── gcp_odb_network/ · gcp_odb_subnet/
│       ├── gcp_exadb_infra/ · gcp_exadb_vm_cluster/ · gcp_root/
│       ├── azure_vnet/ · azure_exadata_infra/ · azure_vm_cluster/
│       └── azure_root/
└── tests/
    └── test_all.py         # 451 tests across all clouds
```

---

## AWS Region & AZ Reference

| AWS Region | Location | AZ IDs |
|------------|----------|--------|
| `us-east-1` | N. Virginia | `use1-az4`, `use1-az6` |
| `us-east-2` | Ohio | `use2-az1`, `use2-az2` |
| `us-west-2` | Oregon | `usw2-az3`, `usw2-az4` |
| `eu-central-1` | Frankfurt | `euc1-az1`, `euc1-az2` |
| `ap-northeast-1` | Tokyo | `apne1-az1`, `apne1-az4` |

Source: [Oracle Regional Availability for ODB@AWS](https://docs.oracle.com/en-us/iaas/Content/database-at-aws/oaaws-regions.htm)

## OCI Regions (Data Guard)

| OCI Region | Location |
|------------|----------|
| `us-ashburn-1` | US East (Ashburn) |
| `us-chicago-1` | US Central (Columbus / Ohio) |
| `us-portland-1` | US West (Portland) |
| `eu-frankfurt-1` | EU (Frankfurt) |
| `ap-singapore-1` | Asia Pacific (Singapore) |
| `ap-tokyo-1` | Asia Pacific (Tokyo) |
| `ap-mumbai-1` | Asia Pacific (Mumbai) |
| `ap-sydney-1` | Asia Pacific (Sydney) |

## GCP Region Reference

| GCP Region | Location |
|------------|----------|
| `us-east4` | N. Virginia |
| `us-central1` | Iowa |
| `europe-west3` | Frankfurt |
| `europe-west2` | London |
| `asia-northeast1` | Tokyo |
| `australia-southeast1` | Sydney |
| `asia-south1` | Mumbai |
| `southamerica-east1` | São Paulo |

Source: [Oracle Regional Availability for AI DB@GCP](https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/get-started-regions.htm)
