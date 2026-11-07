# Constraints and Valid Values

## Shapes
- Exadata.X9M: older generation quarter rack. Server types X9M / X9M-HC, X9M-EF.
- Exadata.X10M: previous generation quarter rack. Server types X10M / X10M-HC, X10M-EF. Live on AWS and GCP; planned on Azure.
- Exadata.X11M: latest generation quarter rack (default on AWS and Azure, recommended). Server types X11M / X11M-HC, X11M-EF. Both server types are MANDATORY on this shape for AWS and Azure — a blank one is rejected.
- Exadata.X11MV: X11M-generation variant, AWS only. Server types X11MV / X11MV-HC. Server types are optional here, unlike X11M.
- GCP carries no server-type lists at all: google_oracle_database_cloud_exadata_infrastructure reports db_server_version and storage_server_version as computed values only. GCP's default shape is Exadata.X9M.
- The per-cloud source of truth is config/<cloud>_shapes.json, edited at /regions. Not all shapes are available in all regions.

## AWS Regions with live ODB support
- us-east-1 (N. Virginia): AZ IDs use1-az4, use1-az6
- us-east-2 (Ohio): AZ IDs use2-az1, use2-az2
- us-west-2 (Oregon): AZ IDs usw2-az3, usw2-az4
- eu-central-1 (Frankfurt): AZ IDs euc1-az1, euc1-az2
- ap-northeast-1 (Tokyo): AZ IDs apne1-az1, apne1-az4

## availability_zone_id vs availability_zone (AWS)
These are two separate fields — both exist on aws_odb_network and aws_odb_cloud_exadata_infrastructure:
- availability_zone_id: the AZ ID (e.g. "use1-az4") — this is the PRIMARY required field for ODB resources. AZ IDs are consistent across accounts; use this to target a specific ODB-enabled AZ.
- availability_zone: the AZ name (e.g. "us-east-1a") — informational/optional. AZ names vary per account and are less reliable for cross-account coordination.
Always set availability_zone_id. Setting availability_zone is optional and only needed for informational tagging.

## s3_access and zero_etl_access (aws_odb_network)
- s3_access: ENABLED or DISABLED. Controls whether Oracle DB nodes can access Amazon S3 directly for data loading, exports, and backups to S3. Default ENABLED.
- zero_etl_access: ENABLED or DISABLED. Enables AWS Zero-ETL integration so Oracle DB data can replicate to Amazon Redshift or other analytics services without ETL pipelines. Default DISABLED.
Both fields accept only the string values "ENABLED" or "DISABLED" — not booleans.

## Compute and storage counts
- Minimum: compute_count=2, storage_count=3 (quarter rack)
- Half rack: compute_count=4, storage_count=6
- Full rack: compute_count=8, storage_count=12
- compute_count must be even; storage_count must be a multiple of 3

## Grid Infrastructure versions (gi_version — AWS only)
AWS aws_odb_cloud_vm_cluster uses gi_version as a required INPUT:
- "23.0.0.0.0" — latest, recommended for new clusters
- "21.0.0.0.0" — previous long-term support
- "19.0.0.0.0" — older long-term support

## GCP grid_image_id (Exascale VM Cluster)
Two different GCP cluster resources — do not mix their inputs:
- google_oracle_database_cloud_vm_cluster (Exadata Dedicated, on an Exadata
  Infrastructure) takes gi_version, e.g. "23.0.0.0".
- google_oracle_database_exadb_vm_cluster (Exascale, on a storage vault) takes
  grid_image_id as a required input; its gi_version is computed.
grid_image_id: The Grid Infrastructure image OCID, `ocid1.dbpatch...` — e.g.
"ocid1.dbpatch.oc1.uk-london-1.anwgiljrt5t4sqqa7anvf..." in the provider's own
example. Oracle publishes no API for it: read it in the OCI Console.

## GCP shape_attribute
Required for google_oracle_database_exadb_vm_cluster (Exascale):
- SMART_STORAGE: Exascale smart storage — Oracle AI Database 26ai and later
- BLOCK_STORAGE: Exascale block storage — Oracle AI Database 19c

## License models
- LICENSE_INCLUDED: Oracle license included in service cost
- BRING_YOUR_OWN_LICENSE: customer provides Oracle license, lower cost

## Naming constraints
- module_name: snake_case, letters/digits/underscores only, unique across all modules
- db_name: max 8 characters, alphanumeric, must start with a letter (e.g. ORCL, MYDB, HR, FINDB)
- pdb_name: same rules as db_name (e.g. MYPDB, HRPDB, APP1)
- hostname_prefix: lowercase alphanumeric, recommended max 12 chars (e.g. exa-prod, vmc-hr)
- display_name: free text, human readable

## SCAN listener port
- Default: 1521
- Valid range: 1024-8999
- Reserved (do not use): 2484, 6100, 6200, 7060, 7070, 7085, 7879

## Patching modes
- ROLLING: nodes patched one at a time, database stays online (recommended for production)
- NON_ROLLING: all nodes patched simultaneously, faster but causes downtime (acceptable for dev/test)
Note: the correct Terraform value is NON_ROLLING (with underscore). NONROLLING is invalid and will fail provider validation.

## Auto backup windows (OCI)
SLOT_TWO=02:00-04:00 UTC, SLOT_FOUR=04:00-06:00, SLOT_SIX=06:00-08:00, SLOT_EIGHT=08:00-10:00
SLOT_TEN=10:00-12:00, SLOT_TWELVE=12:00-14:00, SLOT_FOURTEEN=14:00-16:00

## Sensitive variables
Never hardcode: admin_password, oci_tenancy_ocid, oci_user_ocid, oci_fingerprint, oci_private_key_path
Set via TF_VAR_ environment variables: export TF_VAR_oci_database_admin_password=...

## data_storage_size_in_tbs
Minimum: 2 TB. Increment: 1 TB. dev/test: 2, production: 4-20+ depending on workload.
