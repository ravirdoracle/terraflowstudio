# GCP — customer-managed TDE key in Google Cloud KMS (ExaDB-D)

## What it is
Oracle AI Database@Google Cloud ExaDB-D can encrypt the Oracle TDE master
encryption keys with a key you hold in **Google Cloud KMS** (GCP CMEK) instead of
an Oracle-managed key. Terraflow Studio's GCP page has a **customer-managed key
(KMS)** tab: one card per ExaDB-D VM cluster.

## What Terraflow generates — two separate Terraform roots
Each card generates `kms/<name>/gcp/`, `kms/<name>/oci/` and `kms/<name>/README.md`,
**outside** the main GCP root:

- `gcp/` — `google_kms_key_ring`, `google_kms_crypto_key` (purpose
  `RAW_ENCRYPT_DECRYPT`, algorithm `AES_256_CBC`, protection level HSM or SOFTWARE,
  `prevent_destroy`), a least-privilege `google_project_iam_custom_role`, and
  `google_kms_key_ring_iam_member` granting it to the cluster's Identity Connector
  service agent. Also enables `cloudkms.googleapis.com`.
- `oci/` — `oci_dbmulticloud_oracle_db_gcp_key_ring` registering the key ring with
  OCI, and optionally an `oci_identity_policy` letting Cloud VM Clusters read GCP keys.

Why separate roots: the OCI side authenticates differently (a federated session
token) and in two regions; both run only after the VM cluster exists; and the
crypto key's `prevent_destroy` would otherwise block `terraform destroy` of the
whole environment. Keep their state separate from the main root's.

## Order
1. Deploy the ODB network, Exadata infrastructure and **VM cluster** first.
2. From the OCI console — the VM cluster > **Multicloud Information** > **Identity
   connector** — copy the **Workload resource service agent** email and the
   connector's **OCID** into the card.
3. Apply `kms/<name>/gcp` (Google Application Default Credentials).
4. `oci session authenticate --profile-name FEDERATED_TF --region <home-region>`,
   then apply `kms/<name>/oci`.
5. Console only: the VM cluster > Multicloud Information > **GCP CMEK** > Enable.
   Then create the CDB/PDB with **GCP Customer Managed Encryption Key**, choosing
   the registered key ring and the crypto key. The Terraform provider does not
   expose the "Enable GCP CMEK" switch.

## Error: Unknown resource Entity of type DBGcpConnector
Cause: a compartment OCID was put in `oracle_db_connector_id`
(`oci_gcp_identity_connector_ocid`). The GCP key-ring registration needs the **GCP
Identity Connector's own OCID** (`ocid1.oracledbgcpidentityconnector...`), whatever
some OCI API references say. Fix: copy the connector OCID from the VM cluster >
Multicloud Information > Identity connector. Terraflow's validator and the OCI root
both reject a compartment or tenancy OCID in this field.

## Error: Invalid URL ... /cryptoKeys: No schema supplied
Cause: OCI received the key ring's relative name. OCI appends `/cryptoKeys` and needs
the full Cloud KMS REST URL. Fix: keep `gcp_key_ring_id` relative in tfvars —
`projects/<project>/locations/<location>/keyRings/<name>` — the OCI root adds
`https://cloudkms.googleapis.com/v1/` itself and rejects a value that already has it.
Terraflow prefills the relative name, so no hand-off from the GCP output is needed.

## Error: NotAuthorizedOrNotFound creating the OCI policy (GCP CMEK)
Causes: the IAM policy was not written in the **tenancy home region**; Terraform used
an API-key identity instead of the federated console identity; or the policy already
exists. The OCI root writes the policy through its `home` provider alias. Leave
`create_cluster_gcp_key_policy = false` (the default) when the compartment already
has the Cloud VM Cluster read policy for `oracle-db-gcp-keys`.

## GCP key ring not offered when creating the database
The key ring is not registered in OCI, **GCP CMEK** is not enabled on the VM cluster
(console), or the IAM grant to the Identity Connector's service agent is missing.
The VM cluster must also reach `iamcredentials.googleapis.com`, `sts.googleapis.com`
and `cloudkms.googleapis.com`.

## Other GCP KMS details
- The custom IAM role is **project-wide**: Terraflow gives each card its own role ID
  by default so two key rings in one project do not collide.
- KMS location = the VM cluster's location. The OCI multicloud region is the one
  paired with it (Terraflow prefills it from the region catalogue, e.g. us-east4 →
  us-ashburn-1, europe-west3 → eu-frankfurt-1).

## Provider versions
- `oracle/oci >= 7.17.0` — the first release with
  `oci_dbmulticloud_oracle_db_gcp_key_ring` (7.16.0 fails validate with "Invalid
  resource type"). Validated up to 9.x.
- `hashicorp/google >= 7.5.0`, the same floor as the main GCP root.

## Key safety
- Never disable or destroy the active key version while a database uses it — the
  database becomes unreadable. The crypto key has `prevent_destroy`.
- Raw AES keys have **no automatic Cloud KMS rotation**: create and activate a new
  key version, then rotate the database key through ExaDB-D. Test in non-production first.
- Key rings cannot be deleted in Google Cloud; the name stays taken in that project
  and location.
- Do not commit `terraform.tfvars`, OCI session tokens or Terraform state.
