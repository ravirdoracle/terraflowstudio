# ODB@AWS — CloudFormation Resource Types and Property Reference

Source: AWS blog "Provision Oracle AI Database@AWS stack using AWS CloudFormation"
GitHub sample: aws-samples/sample-odb-launch-using-cfn

This reference is useful for understanding the full property surface of ODB@AWS resources. CloudFormation property names map closely to Terraform argument names (CamelCase vs snake_case).

---

## AWS::ODB::OdbNetwork

| Property | Type | Notes |
|---|---|---|
| `AvailabilityZone` | String | e.g. us-east-1a |
| `AvailabilityZoneId` | String | e.g. use1-az4, use1-az6 — preferred over AZ name |
| `ClientSubnetCidr` | String | Min /27, max /16, RFC1918 only |
| `BackupSubnetCidr` | String | Min /28, max /16, RFC1918 only |
| `DisplayName` | String | Human-readable name |
| `DefaultDnsPrefix` | String | No hyphens — hyphens in DefaultDnsPrefix cause VM cluster creation failure |
| `CustomDomainName` | String | Optional; only usable with Exadata, not ADB |
| `S3Access` | String | ENABLED or DISABLED (default DISABLED) |
| `S3PolicyDocument` | String | IAM policy document for S3 access |
| `ZeroEtlAccess` | String | ENABLED or DISABLED (default DISABLED) |
| `DeleteAssociatedResources` | Boolean | Whether to delete child resources on stack deletion |
| `Tags` | List of Tag | Key-value tags |

Supported AvailabilityZoneId values:
- us-east-1 (N. Virginia): use1-az4, use1-az6
- us-east-2 (Ohio): use2-az1, use2-az2
- us-west-2 (Oregon): usw2-az3, usw2-az4
- eu-central-1 (Frankfurt): euc1-az1, euc1-az2
- ap-northeast-1 (Tokyo): apne1-az1, apne1-az4

---

## AWS::ODB::CloudExadataInfrastructure

| Property | Type | Notes |
|---|---|---|
| `AvailabilityZone` | String | |
| `AvailabilityZoneId` | String | Must match ODB network AZ |
| `DisplayName` | String | |
| `Shape` | String | e.g. Exadata.X11M — IMMUTABLE |
| `ComputeCount` | Integer | Min 2 — IMMUTABLE |
| `StorageCount` | Integer | Min 3 — IMMUTABLE |
| `DatabaseServerType` | String | Server type for compute nodes |
| `StorageServerType` | String | Server type for storage nodes |
| `MaintenanceWindow` | Object | See maintenance window properties below |
| `CustomerContactsToSendToOCI` | List of CustomerContact | Emails for Oracle maintenance notifications, max 10 |
| `Tags` | List of Tag | |

MaintenanceWindow properties: Preference (NO_PREFERENCE or CUSTOM_PREFERENCE), PatchingMode (ROLLING or NON_ROLLING), Months, WeeksOfMonth, DaysOfWeek, HoursOfDay, LeadTimeInWeeks, IsCustomActionTimeoutEnabled, CustomActionTimeoutInMins (15–120).

---

## AWS::ODB::CloudVmCluster

| Property | Type | Notes |
|---|---|---|
| `OdbNetworkId` | String | Reference to ODB network — IMMUTABLE |
| `CloudExadataInfrastructureId` | String | Reference to infra — IMMUTABLE |
| `DisplayName` | String | |
| `Hostname` | String | Max 12 chars, no hyphens — IMMUTABLE |
| `ClusterName` | String | Max 11 chars — IMMUTABLE |
| `GiVersion` | String | e.g. 23.0.0.0.0 |
| `CpuCoreCount` | Integer | **Changes trigger full resource replacement** |
| `MemorySizeInGBs` | Integer | REQUIRED |
| `DataStorageSizeInTBs` | Number | REQUIRED; can increase but not decrease |
| `DbNodeStorageSizeInGBs` | Integer | REQUIRED |
| `DbServers` | List of String | **Changes trigger full resource replacement** |
| `SshPublicKeys` | List of String | RSA only — IMMUTABLE |
| `LicenseModel` | String | LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE |
| `IsLocalBackupEnabled` | Boolean | IMMUTABLE |
| `IsSparseDiskgroupEnabled` | Boolean | IMMUTABLE; use true for dev/test to reduce storage |
| `ScanListenerPortTcp` | Integer | Default 1521 |
| `TimeZone` | String | e.g. UTC |
| `SystemVersion` | String | |
| `DbNodes` | List of DbNode | |
| `DataCollectionOptions` | Object | IsDiagnosticsEventsEnabled, IsHealthMonitoringEnabled, IsIncidentLogsEnabled |
| `Tags` | List of Tag | |

CRITICAL: CpuCoreCount and DbServers changes require FULL RESOURCE REPLACEMENT — plan carefully before modifying.

---

## AWS::ODB::CloudAutonomousVmCluster

| Property | Type | Notes |
|---|---|---|
| `OdbNetworkId` | String | Reference to ODB network |
| `CloudExadataInfrastructureId` | String | Reference to infra |
| `DisplayName` | String | |
| `Description` | String | |
| `CpuCoreCountPerNode` | Integer | |
| `MemoryPerOracleComputeUnitInGBs` | Integer | |
| `AutonomousDataStorageSizeInTBs` | Number | |
| `TotalContainerDatabases` | Integer | |
| `DbServers` | List of String | |
| `LicenseModel` | String | LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE |
| `IsMtlsEnabledVmCluster` | Boolean | Mutual TLS |
| `ScanListenerPortTls` | Integer | TLS port |
| `ScanListenerPortNonTls` | Integer | Non-TLS port |
| `TimeZone` | String | |
| `MaintenanceWindow` | Object | Same structure as Exadata Infrastructure maintenance window |
| `Tags` | List of Tag | |

---

## AWS::ODB::OdbPeeringConnection

| Property | Type | Notes |
|---|---|---|
| `OdbNetworkId` | String | ODB network to peer from |
| `PeerNetworkId` | String | VPC ID to peer with |
| `DisplayName` | String | |
| `Tags` | List of Tag | |

Note: Creating the peering connection does NOT automatically add VPC routes. After stack deployment you must:
1. Add routes in the VPC route table pointing the ODB client and backup subnet CIDRs to the peering connection
2. Manually add any secondary VPC CIDRs to the peering allowed list

---

## VPC infrastructure provisioned by the sample template

The sample CFN template (aws-samples/sample-odb-launch-using-cfn) creates:
- 1 VPC with configurable CIDR
- 1 Internet Gateway
- 2 public subnets + 2 private subnets
- Public and private route tables with associations

---

## Prerequisites for deployment

1. Oracle AI Database@AWS onboarding completed
2. Private Oracle offer accepted via AWS Marketplace
3. AWS account linked to OCI tenancy (multicloud linking)
4. IAM principal granted policy permissions for ODB resource provisioning
5. Entitlement sharing configured across AWS organization accounts if needed

---

## Post-deployment steps (not automated by CloudFormation)

After the stack completes:
1. Configure VPC route tables for ODB peering connections (add routes for client and backup CIDRs)
2. Establish Route 53 outbound DNS resolver endpoints
3. Create Route 53 resolver rules forwarding ODB domain (*.oraclevcn.com) to OCI DNS listener IP
4. Create Oracle databases via OCI APIs (databases are not provisioned by CloudFormation)

---

## CloudFormation vs Terraform property name mapping

| CloudFormation | Terraform (aws provider) |
|---|---|
| `AvailabilityZoneId` | `availability_zone_id` |
| `ClientSubnetCidr` | `client_subnet_cidr` |
| `BackupSubnetCidr` | `backup_subnet_cidr` |
| `DefaultDnsPrefix` | `default_dns_prefix` |
| `CpuCoreCount` | `cpu_core_count` |
| `GiVersion` | `gi_version` |
| `IsLocalBackupEnabled` | `is_local_backup_enabled` |
| `IsSparseDiskgroupEnabled` | `is_sparse_diskgroup_enabled` |
| `LicenseModel` | `license_model` |
| `CloudExadataInfrastructureId` | `cloud_exadata_infrastructure_id` |
| `OdbNetworkId` | `odb_network_id` |
| `SshPublicKeys` | `ssh_public_keys` |
| `DataStorageSizeInTBs` | `data_storage_size_in_tbs` |
| `MemorySizeInGBs` | `memory_size_in_gbs` |
| `DbNodeStorageSizeInGBs` | `db_node_storage_size_in_gbs` |
