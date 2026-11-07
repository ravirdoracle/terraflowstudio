# AWS KMS for TDE master keys (Oracle AI Database@AWS)

Keeps the Transparent Data Encryption (TDE) master encryption key of Exadata VM cluster databases in a customer-managed AWS KMS key instead of the local Oracle wallet. Generated from the AWS page, tab 8 (kms_tde_key). Oracle guide: https://docs.oracle.com/en/learn/exadb-d-aws-kms-integration-tde/index.html

## What the generated Terraform creates
- aws_kms_key + aws_kms_alias (module aws-kms-key): symmetric ENCRYPT_DECRYPT key, AWS default key policy that delegates to IAM, prevent_destroy. Or adopt an existing key by ARN (existing_arn) — Terraform never deletes an adopted key.
- Per VM cluster (module aws-kms-cluster-access): an IAM role named OracleDBKMS-<cluster>, trusted through the OCI identity domain's OIDC provider; an inline policy with kms:DescribeKey, kms:Encrypt, kms:Decrypt on the key and kms:ListKeys; and aws_odb_iam_role_association with aws_integration = "KmsTde" (the only valid value).
- The key registered in OCI (module aws-kms-oci-key): oci_dbmulticloud_oracle_db_aws_key, through the AWS identity connector OCI attaches to the cluster when the role is associated. The connector is discovered from oci_database_cloud_vm_cluster.multi_cloud_identity_connector_configs — it is not created by Terraform.
- Optional oci_identity_policy: "Allow any-user to read oracle-db-aws-keys in compartment id <c> where all { request.principal.type = 'cloudvmcluster' }".

## Trust policy
Federated principal = the IAM OIDC provider for the identity domain (https://idcs-<id>.identity.oraclecloud.com). Conditions (StringEquals): <issuer-host>:rpst_id = the VM cluster OCID when isolate_role_to_cluster is true — rpst_id is the condition key AWS documents for OCI resource principals; and <issuer-host>:aud = the token audience when aws_kms_oidc_audience is set. Oracle does not publish the audience: copy it from the provider's Audiences in IAM (IAM > Identity providers) or from the cluster's CloudFormation template.

## OIDC provider
One per AWS account per issuer URL. If Oracle's CloudFormation stack has ever run in the account, the provider already exists — reuse it with aws_kms_oidc_provider_arn rather than creating a second (creating fails). To create, set aws_kms_oidc_provider_url (no trailing slash) and aws_kms_oidc_audience.

## Prerequisites
- The VM cluster's ODB Network needs sts_access = ENABLED and kms_access = ENABLED. The database unwraps its master key through the KMS endpoint on every startup, so KMS is on the availability path.
- OCI identity domain Available (AWS console > Oracle AI Database@AWS > Settings).
- Provider floors: hashicorp/aws >= 6.61.0 (aws_odb_iam_role_association), oracle/oci >= 7.27.0 (key registration).

## Manual step — no provider or CLI exposes it
After apply: OCI console > Exadata VM Clusters > the cluster > VM Cluster information > AWS Key Management > Enable. Once enabled, new databases on that cluster can use only AWS KMS or the Oracle wallet.

## Using the key
terraform output aws_kms_keys gives oci_key_id per key. A CDB uses it as encryption_key_location_details { provider_type = "AWS", aws_encryption_key_id = <oci_key_id> } — aws_encryption_key_id is the OCID of the registered key, not the AWS ARN. Adding it to an existing CDB migrates the key from the wallet in place (ChangeEncryptionKeyLocation, brief outage); switching to another key or removing it is rejected by the provider — rotate in the OCI console instead.

## Constraints
- A VM cluster takes one TDE key; a Data Guard pair in one region shares a key (both clusters in its cluster_refs).
- Cross-region Data Guard or restore needs multi_region = true and replication in AWS and OCI, which is not generated.
- If the apply stops with "No AWS identity connector", OCI has not attached it yet after the association — re-run apply in a few minutes.
- Destroying the KMS key schedules its deletion (7-30 day window); every database whose master key it wraps is lost with it. prevent_destroy blocks this until removed deliberately.
