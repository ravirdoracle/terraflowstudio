# Terraflow Studio — Claude Code Context

## What this is
A Flask web app that generates modular Terraform/OpenTofu for Oracle AI Database@AWS,
AI Database@Azure and AI Database@GCP, plus the OCI database layer (DB Home/CDB/PDB) and
Data Guard networking. Users fill in a form, see live HCL output, and download a ZIP
or push straight to GitHub.

## Architecture — one package per cloud
The codebase is organised so **a change to one cloud cannot reach another**. Some
duplication between clouds is accepted as the price of that.

```
core/          helpers · pages · selftest        knows about no cloud
  ^
oci/           database · dataguard · routes · selftest · templates/ · pages/
  ^                                            depends on core only
clouds/aws/    generator · validator · schema · selftest · routes · templates/ · pages/
clouds/gcp/    ... same shape
clouds/azure/  ... same shape
clouds/registry.py   imports the clouds; nothing imports it back
```

**OCI sits below the clouds, not beside them.** All three cloud packages use it for
DB Home/CDB/PDB and Data Guard; it uses none of them. Its Data Guard templates were
once named `aws_dg_*` but contain only `oci_core_*` resources and declare only the
`oracle/oci` provider — they were never AWS-specific.

`tests/test_architecture.py` enforces all of this (53 tests, real AST inspection
rather than grep). If you break the layering, those fail before anything else does.

### What lives in a cloud package
| File | Purpose |
|------|---------|
| `generator.py` | Builds the HCL files. `generate_<cloud>_tf(data) -> {path: content}` |
| `validator.py` | `validate(data, errors)` — payload rules for `/api/validate` |
| `schema.py` | Terraform provider resource schema, consumed by `tf_validator.py` |
| `selftest.py` | `/api/test` checks + `collect_cidrs()` + `SECURITY_PROMPT_LINE` |
| `routes.py` | Flask Blueprint owning the product page route |
| `templates/` | Jinja2 → **Terraform**, via `core.helpers.make_renderer` |
| `pages/` | Jinja2 → **HTML**, via the blueprint's `template_folder` |

Two Jinja trees per package on purpose: they render different languages for
different consumers. A `.html` under `templates/` or a `.j2` under `pages/` is a
silent mistake, and there is a test for each.

Each package renders **only its own** templates — separate loaders, so reaching for
another cloud's raises `TemplateNotFound` rather than quietly working.

## Shared modules (top level)
| File | Purpose |
|------|---------|
| `app.py` | App factory, blueprint registration, shared API routes |
| `clouds/registry.py` | One `CloudSpec` per cloud: generator, zip name, validator, selftest |
| `catalogue.py` | Generic catalogue machinery: cache, atomic write, the one-line-per-entry writer |
| `regions.py` | Loads `config/<cloud>_regions.json` — region/AZ catalogues |
| `shapes.py` | Loads `config/<cloud>_shapes.json` — Exadata shape / server-type catalogues |
| `tf_validator.py` | Static HCL validation, one pass per Terraform root; merges the three cloud `schema.py` files and `oci/schema.py` |
| `llm.py` | Model-agnostic LLM adapter (Anthropic, OpenAI, Gemini, Ollama, OCI GenAI) |
| `rag.py` | Dual-backend RAG (ChromaDB or BM25) |
| `github.py` | Pushes generated files via the GitHub Contents API |
| `store.py` | FileStore (JSON under `data/`) or CouchDB |
| `templates/` | Pages serving no single cloud: `home`, `cidr`, `config`, `hub`, `rag` |
| `static/app.css` | The one stylesheet; the three cloud pages link it (`dg.html` / `oci_db.html` still carry their own) |
| `static/guide-export.js` | Deploy Guide → PDF (browser print dialog) / Markdown |
| `static/shape-select.js` | Shape and server-type dropdowns, built from the shape catalogue |
| `static/panel-resizer.js` | The form/output divider on every product page. Only a dragged, finite width is stored (`tf-rhs-width`, shared by all pages); an invalid stored value is discarded on load. Per-page copies stored `"NaN"` on a plain click, which collapsed the grid and dropped the output panel below the form |

**Page chrome that is not cloud logic lives in `static/`.** The three cloud pages are
standalone as Jinja templates — none extends or includes another — but they already
share `app.css`, and the Deploy Guide exporters are shared the same way rather than
triplicated. `tests/test_all.py::TestInlineHandlersAreDefined` resolves inline
`onclick=` handlers against both the inline `<script>` blocks and any `static/` script
the page loads.

## Blueprints: shared modules are rendered from this app
`C:\terraflow_studio\odb-terraform-blueprints` publishes standalone, hand-applied
Terraform. Its **AWS and GCP modules are generated from this app's templates** — the
app is the master copy. Roots are not shared: each side keeps its own hand-written
root (the app's is rendered from the cards; the blueprint's is written for editing).

| Piece | What it does |
|---|---|
| `clouds/<cloud>/blueprint.py` | app module dir -> blueprint module dir + template dir, and a payload that emits all of them |
| `scripts/sync_blueprints.py` | renders those modules via the cloud's own generator into `db-at-<cloud>/modules/`, with a "GENERATED — edit in odb_terraform_app" header. `--check`, `--commit` |
| `.githooks/post-commit` | after every commit here: sync, then commit **only those module files** in the blueprints repo (`sync: <subject>`, naming the app sha). Never pushes |
| `tests/test_blueprint_sync.py` | modules are payload-independent; mapping valid; blueprints in sync (skipped when the repo isn't checked out) |

- **Install per clone:** `git config core.hooksPath .githooks`. `.gitattributes` keeps
  the hook LF (sh fails on CRLF) and it is committed executable (macOS needs `+x`).
  The hook picks the Python that can import `jinja2` (skipping the Windows Store
  `python3` stub). `SKIP_BLUEPRINT_SYNC=1` skips one commit;
  `TERRAFLOW_BLUEPRINTS=` points at a repo elsewhere.
- **A hand edit in the blueprints is never overwritten.** A target file is written only
  if it matches its HEAD there or already equals the render; otherwise the sync stops,
  writes nothing, and names the file. Move the change into the template instead.
- **Azure is not shared**: the app still emits one module per instance; the blueprint
  uses `for_each`. Add it to `CLOUDS` once the app moves Azure to for_each.
- Sharing another module = one line in that cloud's `blueprint.py`, once the blueprint
  root uses it (AWS ADB-S and RAM share are not mapped yet).

**Reconciled 2026-10-21 before the first sync** (the two had drifted to 25–100% shared
code):
- Provider floors from the blueprints' CI bisect: aws `>= 6.42.0`, google `>= 7.5.0`
  (6.15.0 / 6.0.0 / 7.0.0 undercut). Verified by validating both blueprints *and* the
  app's own output pinned to exactly those versions.
- `prevent_destroy` on the AWS ODB Network, Exadata Infra, Peering, VM Cluster and AVMC
  (user's choice; the generated README already claimed deletion protection).
- `ignore_changes` only on drift-prone fields — VM Cluster `db_servers`,
  `ssh_public_keys`; AVMC `db_servers` — **not sizing**, so a resize in tfvars still
  plans (user's choice; the blueprints had ignored sizing).
- From the blueprints: `timeouts` 12h/2h/8h, the GCP drift guards, the effective
  S3/STS/KMS network outputs.
- AVMC `db_servers` is always sent: the provider schema marks it required (the
  blueprint's null-when-empty was wrong).

## Deploy sequence (AWS)
Provision **Exadata Infrastructure → ODB Network → ODB Peering → VM / Autonomous
VM Cluster**, one instance at a time — two Exadata infras means two applies, not
one. ODB provisioning is sequential; concurrent applies are not supported. Typical
durations: infra 15–30 min, network **~4 hours**, peering 15–30 min, VM cluster
**4–6 hours**.

Stated in three places, all of which reach a user — keep them in step:
the Deploy Guide in `clouds/aws/pages/aws.html` (`buildDeployGuide()`, exported to
PDF/Markdown), the generated `README.md`, and `rag_docs/aws_gotchas.md` +
`aws_odb_network.md` / `aws_exadata_infra.md` / `aws_vm_cluster.md` /
`aws_peering_avmcluster.md` / `aws_autonomous_database.md`, which is what the LLM
answers from. ADB-S comes last — Secrets Manager integration (if managed), then each
database — and needs only its ODB Network ACTIVE. The GCP and Azure
docs keep their own, different figures.

The rule is repeated on every AWS resource doc rather than living only in
`aws_gotchas.md`: the BM25 backend is lexical, and a question like "can I provision
two infras at the same time" retrieves the resource doc, not the gotchas doc.
`rag_docs/` edits need `rag.rebuild()` (or `/api/rag/rebuild`) — the index under
`data/` is not regenerated on read.

Guide `-target` commands name the **for_each addresses**
(`module.aws_vm_cluster["c1"]`), not the pre-for_each `module.c1`. The OCI DB
Home/CDB/PDB modules are the exception — they are one module per instance, so
`module.<name>_dbhome` is correct there.

## Routes
| Route | Served by | Purpose |
|-------|-----------|---------|
| `GET /` | `app.py` | Product chooser |
| `GET /aws` | `clouds/aws/routes.py` | ODB@AWS |
| `GET /gcp` | `clouds/gcp/routes.py` | AI DB@GCP |
| `GET /azure` | `clouds/azure/routes.py` | AI DB@Azure |
| `GET /oci` | `oci/routes.py` | OCI Database (DB Home/CDB/PDB) |
| `GET /dg` | `oci/routes.py` | Data Guard networking |
| `GET /cidr` | `app.py` | CIDR planner — entirely client-side, posts to no API |
| `GET /hub`, `/rag`, `/config` | `app.py` | Multicloud hub, RAG admin, settings |
| `GET /regions` | `app.py` | Catalogue editor — regions/zones **and** Exadata shapes, all three clouds |

## Region / AZ catalogues
`config/<cloud>_regions.json` — edit these to add a region or zone; no code change.
**`/regions` edits them from the browser** — a tab per cloud, zones as chips, columns
driven by `regions.OPTIONAL_FIELDS` so a new cloud needs a catalogue file and one line
there, not UI work. `GET/POST /api/regions/<cloud>`.
Loaded and validated by `regions.py`, injected into the page so dropdowns populate
on first paint, and used by the generators for the paired OCI provider region. One
schema for all three clouds: `region`, `label`, `zones`, `status`, plus optional
`group` (Azure) and `oci_label` / `oci_region`.

Malformed config raises `RegionConfigError` at load rather than rendering an empty
dropdown. **The editor saves through that same check** (`regions.validate`), so a
rejected save writes nothing and the file on disk is left exactly as it was — a bad
catalogue would otherwise empty every dropdown in the app at the next load. The write
is atomic (temp file + `os.replace`) because truncated JSON breaks every product page,
and `save()` refreshes the cache, so no restart is needed.

`regions.dumps()` writes entries **one line per region, column-aligned**, matching how
the files are kept by hand — `json.dumps(indent=2)` would turn a one-word edit into a
250-line diff. Field order follows the file (Azure puts `group` before `status`), and
saving twice is byte-stable. The first save from the UI still shifts one alignment
column by a space; after that it is a no-op. Azure sets `zones_are_region_scoped` because it numbers zones per region —
`"1"` in `eastus` is unrelated to `"1"` in `uksouth`.

**14 of 22 AWS regions have `oci_region: null`** and fall back to `us-ashburn-1`.
That predates the config file; the file makes it visible rather than guessing at
identifiers. `eu-west-1 → eu-frankfurt-1` also looks wrong (the catalogue pairs
Ireland with Dublin) and is preserved deliberately — changing it changes generated
Terraform.

## Exadata shape catalogue
`config/<cloud>_shapes.json` — the shape dropdown, the database/storage server-type
dropdowns and each generator's default shape. Same arrangement as the region
catalogue, and edited on the same page: **/regions has a catalogue switch**
(Regions & Zones · Exadata Shapes) above the per-cloud tabs.

Before this existed the values were in three places and had already drifted: a
literal `<option>` list per product page (AWS and GCP offered X10M, Azure did
not), a default-shape string literal per generator, and free-text boxes for the
AWS server types with a placeholder standing in for documentation.

Per entry: `shape`, `label`, `status` (`live`/`planned`), plus
`database_server_types`, `storage_server_types` and `server_types_required` where
the cloud has them. Top-level `default_shape` is what a new card starts on;
`shapes.validate` rejects one that names a shape not in the list.

**GCP carries no server-type lists.** `google_oracle_database_cloud_exadata_infrastructure`
has no such input — it reports `db_server_version` / `storage_server_version` as
computed values only. `OPTIONAL_FIELDS['gcp']` is empty, so the editor renders no
server-type columns and the GCP card has no such fields. AWS and Azure both do.

**Azure gained `database_server_type` / `storage_server_type` with this change.**
azurerm supported both all along; the page simply never offered them. They are
optional, emitted only when set, and the module sends `null` rather than `""`
because an empty string is not a valid model name.

`server_types_required` makes **both** server types required — the card marks
them and `/api/validate` rejects a blank one. Set for `Exadata.X11M` on AWS and
Azure: AWS documents both as mandatory there, and it is a constraint of the X11M
generation rather than of one cloud's provider. Turning it on or off for a shape
is a checkbox in the editor, not a code change.

That rule flags **8 of the 11 saved AWS infra cards** under `data/`, which name
X11M with both fields blank — they were generating Terraform AWS documents as
invalid. `tests/test_shapes.py` pins that count so it moving is deliberate.

The card fills in what cannot be chosen wrongly and asks for the rest:
`database_server_type` has one model per shape so it is seeded, while
`storage_server_type` is HC **or** EF and is left blank with a `— select —`
option. `normaliseServerTypes` in `static/shape-select.js` runs from each card's
read function, so switching shape drops a model belonging to the old one instead
of carrying it into the payload.

`terraform fmt` aligns each run of arguments **between comments** separately, so
the comment above `database_server_type` in `azure_exadata_infra/main.tf.j2` is
load-bearing: the block above it stays at its own width and the block below
widens to fit the longer key. `TestTerraformFmt` catches it if that changes.

`static/shape-select.js` renders the dropdowns and holds no shape values of its
own; each page passes its own injected catalogue. A stored value the catalogue no
longer lists is kept and marked `(not in catalogue)` rather than being silently
rewritten — the same reason the region editor keeps a `null` `oci_region`.

## Resources
**AWS** — `aws_odb_network`, `aws_odb_cloud_exadata_infrastructure`,
`aws_odb_network_peering_connection`, `aws_odb_cloud_vm_cluster`,
`aws_odb_cloud_autonomous_vm_cluster`, `aws_odb_autonomous_database` (Serverless),
`aws_odb_autonomous_database_secrets_manager_integration`, plus DB Home/CDB/PDB via
`oracle/oci`.

**Azure** — `azurerm_virtual_network` (+ delegated subnet),
`azurerm_oracle_exadata_infrastructure`, `azurerm_oracle_cloud_vm_cluster`,
`azurerm_oracle_resource_anchor`, `azurerm_oracle_autonomous_database`, and the
Network Anchor as `azapi_resource` (`Oracle.Database/networkAnchors`) — see below.

**GCP** — `google_oracle_database_odb_network` + `google_oracle_database_odb_subnet`,
`google_oracle_database_cloud_exadata_infrastructure`,
`google_oracle_database_cloud_vm_cluster` (note: the template directory is named
`gcp_exadb_vm_cluster`, but the resource is `..._cloud_vm_cluster`),
`google_oracle_database_autonomous_database`, and Exascale —
`google_oracle_database_exascale_db_storage_vault` + `google_oracle_database_exadb_vm_cluster`
(see below). **Which of these a config emits depends on the ODB Network `purpose`
flag** — see below.

The AWS and GCP roots emit **one `for_each` module per resource type**; instances
live in `terraform.auto.tfvars`, so adding one does not change `main.tf`. Azure still
emits one module per instance. The AWS Autonomous VM Cluster was the last holdout —
it is now `aws_avmclusters` (plus `aws_avmclusters_arn`, see below) like the rest.

**Zero Exadata Infrastructures / Peerings is valid too** — a Serverless-only config has
neither. An explicit empty `aws_infras` / `aws_peerings` generates none; only a payload
*without* the key (or a legacy `module_N` one) still gets an invented instance. Both
cards can be removed to zero; the validator rejects a VM Cluster / AVMC left with no
infra, and the ADB card warns when an infra, or a peering with no peer VPC, would be
built beside a Serverless-only config. Before this, every ADB-S config also generated
an X11M infra and a peering to `vpc-CHANGEME`.

**Zero VM Clusters is a valid config.** `clouds/aws/pages/aws.html` seeds a card for
networks, infras and peerings but *not* for VM Clusters or AVMCs, and
`generate_aws_tf` no longer invents a cluster when `aws_clusters` is empty — the
`module_3` shim fires only when that legacy key is actually present, for configs saved
before the UI supported multiple instances. The shared `modules/aws-vm-cluster/`
directory and the `aws_clusters` variable are still emitted either way, so an entry can
be appended to tfvars later without regenerating. The nets/infras/peerings fallbacks are
untouched: those still materialise one instance from an empty payload — which is also
why their cards keep the `length>1` guard on Remove, while both cluster kinds use
`length>0` and can be emptied.

### ODB Network service access — four flags, two behaviours (AWS)
`s3_access` and `zero_etl_access` are **Required** by the provider and are always
emitted. `sts_access` and `kms_access` are **Optional + Computed**: omitted, each
adopts the status the service assigned and does not diff, so they are emitted
only when set and are deliberately **not** in `lifecycle.ignore_changes` — the
same distinction as the Azure VM Cluster's Computed optionals. An unset flag
becomes `null`, never `""`, which is not a valid status.

The three endpoint policies (`s3_policy_document`, `sts_policy_document`,
`kms_policy_document`) are JSON, emitted as heredocs, and each is inert unless
its access flag is on — `/api/validate` rejects a policy paired with an explicit
`DISABLED`, and rejects malformed JSON, rather than letting either reach apply.
`cross_region_s3_restore_sources_access` is a `set(string)` of region names and
requires `s3_access`.

**`opt_pad` in `_aws_net_defaults` exists for `terraform fmt`.** Those five
optional keys share one alignment run in `terraform.auto.tfvars`, and `fmt` pads
a run to *its own* longest key — so the column depends on which of them the
config actually sets. Hardcoding a width makes `TestTerraformFmt` fail for some
combinations and not others; the generator computes it instead. The long
`cross_region_s3_restore_sources_access` sits alone after a blank line for the
same reason, and that is what keeps the pre-existing keys at their original
width so a config setting none of these generates the tfvars entry it always did.

### Externally provisioned networks / infras (brownfield) — AWS only
An ODB Network or Exadata Infra card can be flagged **already provisioned outside
Terraform** (`is_existing` + `existing_id`, optional `existing_arn` for AVMCs):
- The entry is dropped from `aws_networks` / `aws_infras`, so Terraform creates nothing.
- Its ID is emitted as `existing_infra_ids` / `existing_odb_network_ids`, keyed by module name.
- `main.tf` gains a `locals` block merging managed module outputs with those maps, and
  every `infra_ref` / `network_ref` consumer resolves through `local.infra_ids` /
  `local.odb_network_ids`.
- Managed-only configs generate byte-identical output — the `infra_ids` / `odb_network_ids`
  locals and the `existing_*` variables appear only when at least one entry is external.
  (`main.tf` always has *a* `locals` block now, for DB server discovery — assert on
  `infra_ids = merge(`, not on `locals {`.)
- `clouds/aws/validator.py` skips creation-field validation for external entries and
  requires `existing_id`.

**GCP and Azure have no brownfield support.** GCP is the harder one: its ODB network
module creates the network *and both subnets*, so an existing network is a triple
(`odb_network_name`, `client_subnet_name`, `backup_subnet_name`), not one ID.

### `db_servers_mode` — which DB servers a cluster lands on (AWS)
Three values, on both `aws_clusters` and `aws_avmclusters`:

| Value | Servers offered |
|-------|-----------------|
| `auto` (default) | every server on the infrastructure |
| `unallocated` | only servers whose `vm_cluster_ids` **and** `autonomous_vm_cluster_ids` are empty |
| `manual` | exactly the `db_servers` list |

**`auto` deliberately includes servers other clusters already use.** A DB server hosts
one VM per cluster and reports allocated-vs-total capacity — `cpu_core_count` /
`max_cpu_count`, `memory_size_in_gbs` / `max_memory_in_gbs`,
`db_node_storage_size_in_gbs` / `max_db_node_storage_in_gbs` — and `vm_cluster_ids` is a
*list*. Those three pairs and that list only make sense if servers are shared, so a
server already hosting a cluster is a valid target while it has room. Filtering them out
unconditionally would break the ordinary case of adding a second cluster to an existing
infrastructure — usually **every** server is allocated there, so the filter returns an
empty list, and `db_servers` is required.

The filter is therefore opt-in as `unallocated`, for putting a cluster on hardware of
its own. `check "unallocated_db_servers_available"` warns at plan time when nothing is
left (a `check` block warns, it does not block the apply).

Resolution lives in root `main.tf` locals — `discovered_db_servers` keyed by the
clusters that asked for discovery, then `cluster_db_servers` / `avmc_db_servers` over
*every* cluster via `lookup(..., v.db_servers)`, so manual entries need no data source
and nothing indexes a missing key. The data source's `for_each` filters on
`!= "manual"`, not `== "auto"` — filtering on `auto` would leave `unallocated` clusters
without a lookup and silently fall back to their empty list.

`db_servers_mode` is read by this configuration, never by the provider, so root
`variables.tf` carries a `validation` block per map rejecting any other value. The
browser can only ever send the three (radio buttons); a hand-edited `terraform.auto.tfvars`
is the path that needs guarding.

The **standalone blueprints** share their AWS and GCP modules with this app — see
*Blueprints: shared modules* below. Do not edit those modules in the blueprints repo.

### RAM resource shares (`aws_ram_resource_share`) — AWS tab 7
Shares **this configuration's own** ODB Networks and Exadata Infrastructures with other
accounts in the Organization. In the **main root**, because the account that applies it
owns what it builds. One shared `modules/aws-ram-share/` fed by `aws_ram_shares`,
emitted only when a share exists (byte-identical otherwise).
- Cards pick `network_refs` / `infra_refs` by module name; root `locals`
  `ram_network_arns` / `ram_infra_arns` merge the module outputs (`network_arn`,
  `infra_arn`) with `existing_odb_network_arns` / `existing_infra_arns` — so an
  externally provisioned entry is shareable **only if its card has `existing_arn`**
  (validator enforces).
- `resource_arns` into the module is a **map keyed by name** (`"odb-network/net1"`),
  never by ARN: ARNs of resources created in the same apply are unknown at plan time,
  and a `for_each` keyed on them fails. Verified with an offline plan.
- A dangling ref is **dropped, not retargeted** (unlike `network_ref` elsewhere):
  silently sharing a different resource with another account is worse than one fewer.
- `allow_external_principals` is rejected by the validator — Oracle sharing is
  Organization-only. Principals are 12-digit account IDs (root `validation` too).
- It shares only resources this configuration builds (or external ones by ARN that
  this account owns). A resource owned by another account must be shared from that
  account — there is no generator for that.

Tab index **7**; index 6 is unused. A Subscription & RAM sharing discovery tab (the
`Oracle_DBatAWS_Sharing_Discovery_tool.xlsm` replacement: inventory, License Manager
console steps, per-owner `sharing/ram/` roots) was built and then **removed at the
user's request on 2026-10-21** — only RAM sharing is wanted, and only this tab. Don't
re-add subscription sharing.

### TDE master keys in AWS KMS — AWS tab 8
Keeps the TDE master key of this configuration's VM clusters in a customer-managed
KMS key. Three shared modules, emitted only when `aws_kms_keys` has an entry
(byte-identical otherwise — snapshot-verified on every config under `data/`):
`aws-kms-key` (key + alias, `prevent_destroy`), `aws-kms-cluster-access` (IAM role
`OracleDBKMS-<cluster>` + role policy + `aws_odb_iam_role_association`, `KmsTde`)
and `aws-kms-oci-key` (`oci_dbmulticloud_oracle_db_aws_key`). **They are copies of
`odb-terraform-blueprints/aws-kms-tde/modules`** — `tests/test_aws_kms_tde.py`
fails if the two drift; they are not in the `blueprint.py` sync yet.
- Page-level settings (`aws_kms_tde`, not a card): reuse the account's OIDC provider
  by ARN **or** create it from the identity domain URL, the token `aud`, role
  isolation, and the OCI policy compartment. Errors key on `aws_kms_tde`, which
  `vgen` marks on the settings section (no card carries that name).
- Cards (`kk`) pick `cluster_refs` from **this config's** `aws_clusters`; ARN and OCID
  come from `module.aws_vm_cluster`. A dangling ref is dropped (as RAM shares);
  a cluster takes one key — the validator and a root `validation` both reject a
  second claim. Cluster renames are followed in `syncRefDropdowns` (`_refClusters`).
- Trust policy: `<issuer>:rpst_id` = cluster OCID (the key AWS documents for OCI
  resource principals) and `<issuer>:aud` when set. **Oracle does not publish the
  audience** — it is a user input, required only to create the provider.
- The identity connector is **read, not created**: OCI attaches it on association;
  `data.oci_database_cloud_vm_cluster.kms` (depends_on the association) reads
  `multi_cloud_identity_connector_configs`. The OCI key module's precondition
  explains a not-yet-attached connector instead of failing on the API.
- Floors move only with a key: aws `>= 6.61.0` (an ADB's 6.68.0 wins), oci
  `>= 7.27.0`. The `oracle/oci` provider block and `oci_*` auth variables are now
  emitted for `oci_databases or kms_keys`.
- **Not generated**: "Enable AWS Key Management" on the cluster (no API — the page,
  README and Deploy Guide say so), multi-region key replication, and putting
  `oci_key_id` on a CDB (the AWS page has no CDB cards; `/oci` owns those).

### Autonomous Database Serverless (`aws_odb_autonomous_database`) — AWS
New in hashicorp/aws **6.68.0** (7 Oct 2026), with the Secrets Manager integration
below. ADB **Serverless**: an ODB Network and nothing else — no `infra_ref`. One shared
`modules/aws-autonomous-db/` fed by `aws_autonomous_dbs` (the for_each convention),
emitted only when the map has an entry. `network_ref` resolves through
`network_id_expr`, so an externally provisioned network works unchanged; a dangling ref
is retargeted to the first network.

**Version constraints move only when needed.** With an ADB the root requires aws
`>= 6.68.0` and Terraform / OpenTofu `>= 1.11.0` (ephemeral variable + write-only
argument; OpenTofu gained both in 1.11). With only the integration, the provider moves
and core does not. Without either, output is byte-identical — `_version_ctx` in the
generator owns this.

**ADMIN password: `write_only` or `secrets_manager`, never `admin_password`** (which
lands in state). The three provider inputs are `ConflictsWith` each other, but these
are Plugin Framework validators, which **skip null values** — so, unlike the AVMC id/arn
pair, one module serves both modes with the unused inputs `null`. Verified with a real
`terraform plan` against 6.68.0.
- `write_only`: **`TF_VAR_aws_adb_admin_password`** (a plain string, one password for
  every write_only database) is what the docs lead with. The per-database map
  `aws_adb_admin_passwords` wins where it has an entry, via
  `lookup(map, key, single)`. The single variable exists because a map in an env var
  is HCL: a bare password there fails with "Variables not allowed", and losing the
  inner double quotes (easy in PowerShell) with "Unterminated object constructor" —
  both hit by a real user. Verified in PowerShell and bash, with `$ ! #` and quotes.
- Both password variables are `sensitive` **and
  `ephemeral`**, default `{}`. Verified absent from a saved plan file. The root passes
  `lookup(..., each.key, null)`, and a **`precondition` in the module** stops the plan
  with instructions (bash *and* PowerShell) when a `write_only` database has none. It
  used to index the map directly, which failed with a bare `Invalid index` — a real
  user on Windows hit that after `export` (a no-op in PowerShell). A precondition may
  read an ephemeral value; a variable `validation` referencing it may not, and a `check`
  only warns — both tried.
- `admin_password_wo_version` is passed only for `write_only`: it `AlsoRequires`
  `admin_password_wo`, and it cannot be derived from the ephemeral value itself
  (anything computed from an ephemeral value is ephemeral).
- The validator rejects a payload that carries a password, so one can never be saved
  under `data/`.

**Nearly every argument is Optional + Computed.** Unset, they are omitted from tfvars
and the module sends `null`, so the service's value is adopted with no diff. Bools on
the card are tri-state selects for the same reason — `false` is a setting, unset is
not. `odb_network_id`, `character_set` and `ncharacter_set` are RequiresReplace.
`data_storage_size_in_tbs` must be whole (provider `ValidateConfig`).

**No `lifecycle.ignore_changes` for scaling, unlike the GCP ADB.** The AWS provider
reports scaled storage separately (`allocated_storage_size_in_tbs`,
`actual_used_data_storage_size_in_tbs`) and ADB-S auto-scaling does not rewrite the
base `compute_count`, so resizing through tfvars produces a plan. Not yet confirmed
against a live, auto-scaled database — revisit if plans propose shrinking one.

**tfvars entries are built in Python** (`_tfvars_runs`): which optional keys an entry
sets varies, and `terraform fmt` pads each run to its own longest key — the `opt_pad`
problem again, solved per run.

**The Secrets Manager integration is a page toggle, not a card**
(`aws_adb_secrets_integration: bool`). One per account + Region, shared by every ADB
there; creating it adopts an existing one, destroying it disables it for everyone. The
module sets `prevent_destroy`; the README gives the `removed { destroy = false }` way
out. The customer IAM role that trusts its `role_arn` is **not generated** — the
external-ID value is an OCI OCID the configuration does not know.

**Not surfaced:** `source_configuration` (clones, cross-region DG/DR), refreshable
clones, `scheduled_operations`, `long_term_backup_schedule`, resource pools,
`db_tools_details`, transportable tablespaces, standby allowlists, local Data Guard,
`cpu_core_count`, `data_storage_size_in_gbs`. CloudFormation output ignores ADBs.

### Resource Anchor + Network Anchor — Azure tabs E and F
A **Resource Anchor** maps the resource group to an OCI compartment. The generator
always supported `azure_resource_anchors`; the page never offered it until now (tab
E, prefix `ar`, vgen 24). A **Network Anchor** is the network bridge to OCI — not tied
to one database service — on a **delegated subnet of its own** (tab F, prefix `na`,
vgen 25, `azure_network_anchors`). OCI builds a VCN + subnet behind it in the Resource
Anchor's compartment.
- **azapi, because azurerm has no resource** (none up to 5.12.0):
  `Oracle.Database/networkAnchors@2025-09-01`, the GA version (2026-06-01 only adds a
  proximity placement group, not surfaced). Shapes from the Azure REST API specs, not
  from memory. `terraform validate` checks the body against Azure's schema offline.
- **Floor `azure/azapi >= 2.8.0`, bisected**: 2.5.0–2.7.0 reject the type, 2.4.0 has
  no `ignore_null_property`. Validated pinned to exactly 2.8.0.
- azapi enters `required_providers` and gets a `provider "azapi"` block **only when a
  Network Anchor exists** — every config without one is byte-identical
  (snapshot-verified on all of `data/`).
- One static module per anchor (Azure convention): its own `azurerm_subnet` delegated
  to `Oracle.Database/networkAttachments`, then the `azapi_resource` with
  `ignore_null_property = true` so unset optionals stay out of the request. The two
  comma-separated API fields (`dnsListeningEndpointAllowedCidrs`, rule
  `domainNames`) are `join`ed from lists.
- Root passes **one object variable per anchor** (`var.<module>`), and its tfvars
  entry is built in Python (`_azure_na_tfvars_entry`) — the keys present vary, and
  `fmt` pads each run to its own longest key; forwarding rules go last after a blank
  line. `TestTerraformFmt` in `tests/test_azure_network_anchor.py` covers three shapes.
- **Each ref is a card or something existing**: `resource_anchor_ref` or
  `existing_resource_anchor_id`; `vnet_ref` or `existing_vnet_name`. A dangling ref
  falls back to the first card (a missing module fails at apply); an empty ref with an
  existing value is a deliberate choice and is kept.
- Validator: name 3–24 letters/digits/hyphens; the subnet must sit inside the VNet and
  clear its VM-cluster delegated subnet and every other anchor's; DNS zone
  replication + listening endpoint together are rejected (Oracle calls them
  overlapping, pick one); allowed CIDRs / forwarding rules need their endpoint.
- **Only the backup CIDR and the three DNS flags are in the API's update model.**
  Resource Anchor, subnet, zone and VCN DNS label are identity — no replace triggers,
  so changing one fails at apply rather than destroying the anchor.
- Oracle's docs describe creation as portal-only; the API is GA and is what the
  portal calls. **Not verified against a live subscription.**

### Autonomous Database Serverless (`azurerm_oracle_autonomous_database`)
ADB **Serverless**, not Dedicated: Oracle runs the fleet, so there is no Exadata
Infrastructure or VM Cluster underneath. The card takes a `vnet_ref` but **no
`infra_ref`** — the only thing it needs from this configuration is the
Oracle-delegated subnet, and even that is optional (empty `vnet_ref` = public
endpoint, controlled by `allowed_ips`).

- `admin_password` is **Required** by the provider and must never land in a
  generated file. The module declares it `sensitive` with **no default**, the root
  declares `<module>_admin_password` the same way, and `terraform.auto.tfvars`
  carries only a comment naming the env var. A test asserts no generated file
  contains the value.
- A `vnet_ref` naming a VNet this config does not build is blanked in
  `generate_azure_tf`. `first_vnet_name` falls back to the literal `"azure_vnet"`
  when there are no VNets at all, and wiring `module.azure_vnet.subnet_id` to a
  module that was never generated fails at apply with an unknown module reference.
- `subnet_id` / `virtual_network_id` are Optional in the schema, so the module
  sends `null` rather than `""` when unset — an empty string is not a valid ID.
- Verified against the azurerm schema: attributes are **identical in 4.81 and
  5.3**, so the package's `>= 4.9.0` constraint holds.
- **Not surfaced:** the `long_term_backup_schedule` block. Its `time_of_backup` is
  an RFC3339 timestamp that a form field would get wrong more often than right.

### Customer-managed TDE key in Google Cloud KMS — GCP tab F (`gcp_kms_keys`)
ExaDB-D TDE master keys encrypted with a Cloud KMS key the customer holds (GCP CMEK).
Built from the user's reference project `exadb-d-gcp-kms` (its newer split `gcp/` +
`oci/` roots — the combined root in that zip had three bugs: relative key-ring ID,
policy outside the home region, missing `cloudkms.keyRings.list`).

- **Two standalone roots per card, not modules of the main root**:
  `kms/<name>/gcp/` (key ring, `RAW_ENCRYPT_DECRYPT` / `AES_256_CBC` key with
  `prevent_destroy`, least-privilege custom role, IAM grant to the Identity
  Connector's service agent) and `kms/<name>/oci/`
  (`oci_dbmulticloud_oracle_db_gcp_key_ring`, optional home-region policy), plus a
  README. Why: the OCI side authenticates with a federated session token in two
  regions (multicloud + **home**, where IAM policies must be written); both run only
  after the VM cluster exists; and `prevent_destroy` would block destroying the main
  root. Main-root output is byte-identical without a card.
- **No hand-off**: `gcp_key_ring_id` in `oci/terraform.tfvars` is prefilled
  (`projects/<p>/locations/<l>/keyRings/<n>`, relative); the OCI root adds
  `https://cloudkms.googleapis.com/v1/` and rejects a value that already has it.
- Project and location default from the card's VM cluster, then the network; the OCI
  multicloud region from `config/gcp_regions.json`'s `oci_region` pairing. Values
  that exist only after provisioning (service-agent email, connector OCID,
  compartment, home region) are `CHANGEME`; validator tab 16 requires them.
- **The connector field takes the Identity Connector's OCID** — a compartment OCID
  fails at the API with "Unknown resource Entity of type DBGcpConnector". Rejected by
  the validator *and* by a `validation` block in the OCI root.
- Custom role is project-wide → default role ID per card (`oracleExadbKms_<name>`).
- **Floors proven, not inferred**: `oracle/oci >= 7.17.0` (first release with the
  resource; 7.16.0 fails validate with "Invalid resource type"; the reference's
  `~> 8.0` would have blocked 9.x, which validates), `hashicorp/google >= 7.5.0`.
- "Enable GCP CMEK" on the VM cluster is console-only (not in the provider) — the
  README and Deploy Guide say so. Not synced to the blueprints (app only, by choice).

### Autonomous AI Database Serverless (`google_oracle_database_autonomous_database`)
The GCP counterpart to the Azure card above, and the same Serverless-not-Dedicated
story: no Exadata Infrastructure, no VM Cluster, **no `infra_ref`**. Three things
differ from Azure, all of them provider facts rather than choices:

- **It is regional.** Infras, VM Clusters and ODB Subnets are placed in a
  `gcp_oracle_zone`; ADB is not. The card and the module both omit the field, and a
  test asserts the module never grows one.
- **`network_ref` is required, not optional.** Azure's ADB can take a public
  endpoint with no VNet; a GCP ADB reaches the network through the
  `odb_network` / `odb_subnet` pair, so there is always a network. It attaches to
  that network's **client** subnet — the backup subnet is for VM Clusters and is
  never wired here (`rag_docs/gcp_networking_advanced.md`). A `network_ref` naming
  a network this config does not build is retargeted to the first one in
  `generate_gcp_tf`, because a dangling key fails at apply on a missing map entry.
- **The provider constraint moves to `>= 7.0.0`** when a config has an ADB, since
  `odb_network` / `odb_subnet` on this resource arrived in hashicorp/google 7.0.
  Without one it stays `>= 6.0.0`, so ADB-free configs generate byte-identical output.

### Exascale — GCP tabs G (vault) and H (VM cluster)
`google_oracle_database_exascale_db_storage_vault` (prefix `gv`, vgen 17,
`gcp_exascale_vaults`) and `google_oracle_database_exadb_vm_cluster` (prefix `gx`,
vgen 18, `gcp_exascale_clusters`), from Oracle's "Create an Exascale VM Cluster" page.
Two for_each modules, `gcp-exascale-vault` / `gcp-exascale-vm-cluster`, emitted only
when either list has an entry — every other config is byte-identical
(snapshot-verified on `data/` and 12 synthetic GCP payloads). App only: not in
`blueprint.py`.
- **No Exadata Infrastructure, no zone input.** The cluster runs in its vault's zone.
  It needs the client **and** backup subnet, so an `adbs` network is rejected.
- **Phantom suppression:** with Exascale present, `generate_gcp_tf` invents no
  infra/cluster for an empty list, and `wants_dedicated` is false when there is no
  infra or cluster of its own. The page's infra and VM Cluster cards can now be
  removed to zero (`length>0`), or an Exascale-only config could never be built.
  The root header, README and `selftest.derive` follow the same rule.
- **Floor `hashicorp/google >= 7.20.0`, bisected** (7.19.0: "Invalid resource type");
  validated pinned to exactly 7.20.0. The root constraint moves only with Exascale.
- **`grid_image_id` is an `ocid1.dbpatch...` OCID with no API** (Oracle's page and the
  provider's own example). Placeholder `ocid1.dbpatch.oc1..CHANGEME` validates and
  fails at apply; the validator rejects it, the module variable checks the prefix.
  Four `rag_docs` had it as a `projects/.../giVersions/...` path and conflated this
  resource with the Dedicated `cloud_vm_cluster` (which takes `gi_version`) — fixed.
- Limits enforced by the validator: vault 300–100,000 GB, flash 34–300%; 1–10 VMs;
  ECPU 8–200 step 4, reserved 0–192 step 4; file system 220 (smart) / 260 (block) to
  1100 GB; cluster_name ≤ 11; IDs 1–63 lowercase.
- **Scaling is not in `ignore_changes`** (user's AWS/GCP rule: only drift-prone
  fields) — Oracle's sample ignores the ECPU counts and file system size. Only
  `ssh_public_keys` is ignored; the card, README and module say so.
- A vault is a card (`vault_key`) or an existing one by full name (`existing_vault`);
  a root `validation` requires exactly one. tfvars entries are built in Python
  (`_gcp_xs_tfvars`) for fmt alignment, as elsewhere.

#### `purpose` on the ODB Network — what decides the shape of the output
Each GCP ODB Network card carries a flag: **`dedicated`** (Exadata only),
**`adbs`** (Autonomous Serverless only) or **`both`**. It defaults to `both`, so
every config saved before the flag existed generates byte-identical Terraform.

It is not cosmetic — it selects which modules exist at all:

| All networks are | Network module | Exadata infra + VM cluster |
|---|---|---|
| `adbs` | `gcp-odb-network-adbs` (client subnet only) | **not emitted** |
| anything else | `gcp-odb-network` (client + backup) | emitted |

An ADB-S deployment has no Exadata Infrastructure and no VM Cluster under it, so
emitting those directories, their root module blocks, their map variables and the
`google_oracle_database_db_servers` data source would all be dead weight. The
`main.tf` header, the README and the Deploy Guide follow the same flag.

**Two network modules rather than a `count` on the backup subnet.** Terraform
cannot make a resource conditional without changing its address, so a count would
rewrite `google_oracle_database_odb_subnet.backup` to `...backup[0]` in every
existing configuration — a state move, and a proposed **destroy of a live backup
subnet** for anyone who had already applied. `gcp-odb-network` is therefore
untouched, byte for byte, and ADB-S-only networks get their own directory. A
mixed config emits both, and `locals.adb_odb_networks` merges them so an ADB can
reference either kind; that locals block appears **only when an `adbs` network
exists** (the AWS brownfield precedent).

**The flag suppresses the phantom instance, never a real one.** `generate_gcp_tf`
materialises one infra and one cluster from an empty payload so a half-filled form
still shows something. That is wrong for ADB-S-only, so it is skipped there — but
an infra or cluster the user actually filled in always generates, whatever the
flags say. Dropping it would be silent data loss.

Validation enforces the flag both ways: a VM Cluster may not reference an `adbs`
network (it needs a backup subnet), an ADB may not reference a `dedicated` one,
and an `adbs` network is not asked for a backup CIDR. The card hides the Backup
Subnet section, and the reference dropdowns are filtered so an invalid pairing
cannot be selected in the first place.

Follows the GCP for_each convention: one shared `modules/gcp-autonomous-db/`
directory driven by `gcp_autonomous_dbs` in tfvars, emitted **only when the map has
an entry** (the AVMC precedent). `admin_password` never lands in a generated file —
the root declares one sensitive `gcp_adb_admin_passwords` map with no default,
keyed by module name, and tfvars carries only a comment naming the export. A map
rather than Azure's per-instance variable because a for_each config must stay
scalable by appending to tfvars alone.

**Scaling fields sit in `lifecycle.ignore_changes`** — `compute_count`, both storage
sizes, version, edition, the auto-scaling flags, backup retention. Autonomous scaling
rewrites them in place, so unguarded every plan would propose shrinking the database
back to its seed size. This is Oracle's published list for ADB@GCP and matches how
the sibling `gcp-vm-cluster` module guards its own fields. The cost is real and is
stated in the card, the README and the module: **editing those in tfvars produces no
plan**; a deliberate resize needs the field commented out of the block first.

**Not surfaced:** the legacy `network` + `cidr` pair (plain-VPC attachment instead of
an ODB Network), and `source_config` / cross-region Autonomous Data Guard.

### Azure VM Cluster gotchas (`azurerm_oracle_cloud_vm_cluster`)
Nearly every argument is `ForceNew` and `Update()` handles only `tags` and
`file_system_configuration`, so **drift proposes destroying the cluster**.

Three optional arguments are `ForceNew` *without* being `Computed`, which makes them
the ones that diff against an empty config:
- `backup_subnet_cidr` — never leave blank. The service assigns `192.168.252.0/22`,
  which then differs from a `null` config and replaces the cluster on the next plan.
  Always emitted explicitly.
- `gi_version` — a **major-version selector**. Oracle resolves `19.0.0.0` to the
  running release (`19.32.0.0.0`) and stores that, and it moves again with every
  quarterly patch, so no pinned value stays matching.
- `scan_listener_port_tcp_ssl` — emitted as `null` unless a port is set; guarded only
  in that case.

All three are covered by `lifecycle.ignore_changes`. The `Computed` optional arguments
(`cluster_name`, `domain`, `time_zone`, `system_version`, `zone_id`, …) adopt the state
value when config omits them and are deliberately **not** guarded.

AWS and GCP need none of this: the AWS provider keeps input and resolved value in
separate fields (`gi_version` / `gi_version_computed`), and GCP marks `giVersion`
`ignore_read`.

### Autonomous VM Cluster gotchas (`aws_odb_cloud_autonomous_vm_cluster`)
- Its `maintenance_window` takes **only** `preference` + `days_of_week`, `hours_of_day`,
  `lead_time_in_weeks`, `months`, `weeks_of_month`. `patching_mode`,
  `is_custom_action_timeout_enabled` and `custom_action_timeout_in_mins` belong to the
  **Exadata Infrastructure's** maintenance_window, not this one.
- It accepts the **id pair or the arn pair, never both** — and a `null` value still
  counts as present, so the unused pair must be omitted, not set to `null`. That is
  why there are **two module directories**: `aws-avmcluster` (id pair, fed by
  `aws_avmclusters`) and `aws-avmcluster-arn` (arn pair, fed by
  `aws_avmclusters_arn`). `use_arn_pair` in `_aws_avmc_defaults` — both arns present
  — decides which map an instance lands in. Each directory is emitted only when its
  map has an entry, so a config with no AVMC generates exactly what it did before.
- The arn-pair module cannot auto-discover `db_servers`: the infra lives outside the
  configuration, so there is no id to hand `data.aws_odb_db_servers`. List them.
- `db_servers` is **required**; always emit it, even for an empty manual list.

### Cross-region Data Guard: several VCN pairs on one hub (`additional_pairs`)
A cross-region card builds the **foundation once** — per region a hub VCN, DRG and
hub DRG attachment, plus one RPC pair. `additional_pairs` on the card adds more
primary/standby cluster VCN pairs to that same hub instead of a new card (which
would build a second hub, DRG and RPC).
- **State-compatible by design (user's choice):** the card's own VCNs stay pair #1
  with the resource addresses they always had; extra pairs are `for_each` resources
  (`hub_lpg_extra`, `cluster_lpg_extra`, `dg_ingress_extra`, …) fed by
  `var.extra_spokes` in each region module, and the two hub route tables gain
  `dynamic "route_rules"`. An applied config plans additions only. Without pairs,
  output is byte-identical (snapshot-verified on all of `data/`).
- **Paired routing (user's choice):** each cluster VCN routes to, and its NSG
  admits, only its own peer's CIDR.
- **10 LPGs per VCN** (OCI default, Oracle docs) caps a hub at 10 pairs including
  the first. `oci/validator.py` rejects more, plus duplicate/invalid pair names (they
  are for_each keys) and overlapping client CIDRs. Not a Terraform `validation`:
  that would block anyone who has raised the limit.
- **Managed route tables:** one `for_each` resource serves every extra pair, so their
  pre-existing rules cannot be pasted into the module as for pair #1. They come from
  `primary_existing_route_rules` / `dr_existing_route_rules` per pair in tfvars
  (`dynamic` block); empty means every other route in that table is removed — the
  README and a commented tfvars example say so.
- **`dg` now has a server validator** (`oci/validator.py`, in the registry); `oci`
  still has none. The DG page's `vgen` called `.join` on the errors object and never
  showed a message; fixed.
- **Pre-existing, not fixed:** the root `main.tf` outputs block of a cross-region root
  is padded (`output "dr_hub_vcn_id"      {`), which `terraform fmt -check` rejects.
  Downloads and `/api/tf-cli` run `_fmt_files` first, so users never see it.

## JS state arrays
```js
// clouds/aws/pages/aws.html
awsNets, awsInfras, awsPeerings, awsClusters, awsAvmcs, awsAdbs, awsOciDbs
awsAdbIntegration   // bool — the Secrets Manager integration toggle
awsRamShares        // aws_ram_resource_share cards — prefix rs
awsKmsTde           // TDE page-level settings (OIDC provider, audience, isolation)
awsKmsKeys          // TDE key cards — prefix kk
// clouds/gcp/pages/gcp.html
gcpNets, gcpInfras, gcpClusters, gcpAdbs
gcpXsVaults, gcpXsClusters   // Exascale — prefixes gv, gx
// clouds/azure/pages/azure.html
azureVnets, azureInfras, azureClusters, azureAdbs
azureResourceAnchors, azureNetworkAnchors   // prefixes ar, na
```
The pages are **standalone** — none extends or includes another. That is the only
reason they can live in separate packages; if one grows an `{% extends %}`, the parent
must stay reachable from every blueprint.

## Adding a new AWS resource — checklist
1. Add Jinja2 templates in `clouds/aws/templates/aws_<resource>/` (main, variables, outputs, tfvars)
2. Add the context builder and generators in `clouds/aws/generator.py`
3. In `clouds/aws/pages/aws.html`: `defAwsX(i)`, `addAwsX()`, `readAwsX(i)`,
   `awsXCardHTML(d,i)`, `renderAwsXs()`, state array
4. Add the tab and its page div in the same file
5. Wire into `buildPayload()`, `renderAll()`, `applyConfig()`
6. Wire into `generate_aws_tf()` in `clouds/aws/generator.py`
7. Add rules to `clouds/aws/validator.py`, and checks to `clouds/aws/selftest.py`
8. Run the suite — see below

## Adding a new cloud
1. `clouds/<cloud>/` with `generator.py`, `validator.py`, `schema.py`, `selftest.py`,
   `routes.py`, `templates/`, `pages/`
2. One `CloudSpec` line in `clouds/registry.py`
3. Register the blueprint in `app.py`
4. `config/<cloud>_regions.json` and `config/<cloud>_shapes.json`
5. Merge its schema in `tf_validator.py`

Nothing else should need to change. If it does, that is coupling worth removing.

## Tests
```bash
python -m unittest discover -s tests -p "test_*.py"     # 1277 tests, all must pass
```
| File | Tests | Covers |
|------|-------|--------|
| `tests/test_all.py` | 530 | End-to-end generation, API routes, cross-cloud |
| `tests/test_azure.py` | 143 | Azure modules and validation |
| `tests/test_azure_network_anchor.py` | 42 | Network Anchor (azapi) + Resource Anchor card: module, root wiring, tfvars/fmt, validation, page |
| `tests/test_gcp.py` | 172 | GCP modules and validation, customer-managed KMS key |
| `tests/test_gcp_exascale.py` | 29 | Exascale vault + VM cluster: no phantom Exadata, floor, wiring, limits, page, fmt |
| `tests/test_architecture.py` | 53 | Package layering and ownership rules |
| `tests/test_aws.py` | 95 | AWS modules and validation, ADB-S + Secrets Manager integration |
| `tests/test_aws_ram_share.py` | 14 | RAM resource shares in the main root, and their validation |
| `tests/test_aws_kms_tde.py` | 18 | TDE keys in AWS KMS: wiring, floors, tfvars, validation, parity with the blueprint modules |
| `tests/test_blueprint_sync.py` | 5 | Shared blueprint modules: payload-independent, mapped, in sync |
| `tests/test_regions.py` | 59 | Region catalogues and OCI region mapping |
| `tests/test_shapes.py` | 57 | Shape catalogues, the editor API, required server types |
| `tests/test_dg_hub_spoke.py` | 23 | Cross-region DG: extra VCN pairs on one hub — addresses kept, paired routing, managed route tables, validation, fmt |
| `tests/test_tf_roots.py` | 28 | Multi-root testing: Data Guard / KMS roots through the mock validator, `/api/tf-cli`, `/api/test`, the DG test tabs |

**Every Terraform root is tested on its own.** `tf_validator.tf_roots(files)` is every
directory holding a `.tf` file outside a `modules/` path: `''` for a cloud's main root,
plus one per Data Guard card (`dg_multi_az_<name>/`, `dg_cross_region_<name>/`, and no
top level at all), `kms/<name>/gcp|oci/` per GCP KMS key, and `<name>_dbhome|cdb|pdb/` for
OCI DB. `init` and `validate` only read the directory they run in, so `/api/tf-cli` runs
both in each root — before this it ran them at the top level only and passed DG and KMS
code it never looked at. The mock validator checks the top-level root against the
cloud's provider exactly as before and every other root against the providers it
declares, groups prefixed `<root>/ · `. The Data Guard page has all three test tabs.

For refactors, a passing suite is not sufficient evidence. Snapshot generated output
(`{path: sha256}`) for every config under `data/` before and after and diff it — that
technique caught two regressions during the package split that the suite missed.

## Conventions
- AWS generator functions: `mod0_*` = ODB Network, `mod1_*` = Exadata Infra, `mod2_*` =
  Peering, `mod3_*` = VM Cluster, `mod4_*` = AVMC; `_MOD5` = ADB-S, `_MOD6` = Secrets
  Manager integration (module files via `_adb_module_files` / `_adb_integration_module_files`)
- GCP: `gcp_build_root_*`, `_gcp_*_defaults`; Azure: `azure_*`, `_azure_*_defaults`
- OCI: `oci_dbhome_*`, `oci_cdb_*`, `oci_pdb_*`
- JS card prefixes — AWS: `an` net, `ai` infra, `ap` peering, `ac` cluster, `av` AVMC,
  `ad` autonomous db, `rs` RAM share, `kk` TDE key, `od` OCI DB · GCP: `gn`, `gi`, `gc`, `ga` autonomous db, `gk` KMS key, `gv` Exascale vault, `gx` Exascale cluster · Azure: `av` vnet, `ai` infra, `ac` cluster,
  `ad` autonomous db, `ar` resource anchor, `na` network anchor
- `tf_bool(v)` converts a Python bool to `true`/`false` for HCL
- Never hardcode secrets in templates — use `sensitive = true` on the variable
- OCI payload keys are canonical (`dg_multi_az`, `oci_databases`); `<cloud>_`-prefixed
  variants are accepted as deprecated aliases so saved configs keep working

## RAG layer
- `rag.py` — dual backend, chosen at runtime:
  - **ChromaDB** (semantic) when `chromadb` is installed *and* `EMBEDDING_PROVIDER` is set
  - **BM25** (lexical) otherwise — pure Python, no extra deps
- `rag_docs/*.md` — knowledge base, 32 files, git-tracked
- `data/chroma/`, `data/rag_index.json` — runtime stores, not in git
- `/api/rag/stats` (includes `backend`), `/api/rag/rebuild`, `/api/rag/search`, `/api/rag/upload`
- `/api/llm/fill` augments the system prompt with the top 5 retrieved chunks

## Running
```bash
pip install -r requirements.txt && python app.py     # http://localhost:5000
docker compose up -d --build                         # edit .env first
```

## Environment variables (.env)
```
COUCHDB_USER, COUCHDB_PASSWORD, COUCHDB_DB
LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL      # anthropic|openai|gemini|ollama|oci_genai
LLM_MAX_TOKENS=2048, LLM_TEMPERATURE=0.2, LLM_TIMEOUT=60
EMBEDDING_PROVIDER, EMBEDDING_MODEL, EMBEDDING_BASE_URL # ollama|openai|gemini
GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH=main, GITHUB_BASE_PATH=terraform
```

## Known loose ends
- `templates/base.html` (1875 lines) is **dead** — nothing extends, includes or renders
  it. The pages became standalone at some point and it was never removed.
- `oci/pages/oci_db.html` has no test modal — its Test button only shows a toast. The
  backend handles its roots (`<name>_dbhome/`, `_cdb/`, `_pdb/`); the page was never wired.
- `oci/__init__.py` exports 20 names, most underscore-prefixed, because the cloud
  generators reach into OCI internals (`_ocidb_filled`, `_mn_dbhome`). Worth narrowing.
- `app.py` still holds cloud-aware prompt text in `api_llm_ask` — the same shape as the
  `_collect_cidrs` bug that silently gave Azure no CIDR findings at all.
