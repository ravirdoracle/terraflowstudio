"""AWS ODB provider schemas — hashicorp/aws."""

AWS_SCHEMAS = {
    'aws_odb_network': {
        'required': ['display_name', 'availability_zone_id', 'client_subnet_cidr',
                     'backup_subnet_cidr', 's3_access', 'zero_etl_access'],
        'optional': ['availability_zone', 'region', 'default_dns_prefix',
                     'custom_domain_name', 'delete_associated_resources', 'tags',
                     # Optional + Computed in the provider; omitted means "let
                     # the service decide", which is why none of these is required.
                     'sts_access', 'kms_access',
                     's3_policy_document', 'sts_policy_document',
                     'kms_policy_document',
                     'cross_region_s3_restore_sources_access'],
    },
    'aws_odb_cloud_exadata_infrastructure': {
        'required': ['display_name', 'shape', 'compute_count', 'storage_count',
                     'availability_zone_id', 'maintenance_window'],
        'optional': ['availability_zone', 'region', 'database_server_type',
                     'storage_server_type', 'customer_contacts', 'tags'],
    },
    'aws_odb_network_peering_connection': {
        'required': ['display_name'],
        'optional': ['odb_network_id', 'odb_network_arn', 'peer_network_id',
                     'peer_network_cidrs', 'region', 'tags'],
    },
    'aws_odb_cloud_vm_cluster': {
        'required': ['display_name', 'cpu_core_count', 'gi_version',
                     'hostname_prefix', 'license_model', 'ssh_public_keys',
                     'data_collection_options'],
        'optional': ['cloud_exadata_infrastructure_id', 'cloud_exadata_infrastructure_arn',
                     'odb_network_id', 'odb_network_arn', 'db_servers',
                     'cluster_name', 'timezone', 'data_storage_size_in_tbs',
                     'db_node_storage_size_in_gbs', 'memory_size_in_gbs',
                     'scan_listener_port_tcp',
                     'is_local_backup_enabled', 'is_sparse_diskgroup_enabled',
                     'region', 'tags'],
    },
    # Every argument is Optional: the AWS API accepts whichever combination
    # `source` calls for. Nearly all are Optional + Computed as well.
    'aws_odb_autonomous_database': {
        'required': [],
        'optional': ['odb_network_id', 'source', 'display_name', 'db_name',
                     'db_workload', 'license_model', 'compute_count',
                     'data_storage_size_in_tbs', 'database_edition', 'db_version',
                     'is_auto_scaling_enabled', 'is_auto_scaling_for_storage_enabled',
                     'backup_retention_period_in_days',
                     'autonomous_maintenance_schedule_type',
                     'is_mtls_connection_required', 'private_endpoint_label',
                     'private_endpoint_ip', 'allowlisted_ips', 'character_set',
                     'ncharacter_set', 'encryption_key_provider', 'kms_key_id',
                     'admin_password', 'admin_password_wo', 'admin_password_wo_version',
                     'admin_password_source', 'customer_contacts_to_send_to_oci',
                     'region', 'tags'],
    },
    'aws_ram_resource_share': {
        'required': ['name'],
        'optional': ['allow_external_principals', 'permission_arns', 'region', 'tags'],
    },
    'aws_ram_principal_association': {
        'required': ['principal', 'resource_share_arn'],
        'optional': ['region'],
    },
    'aws_ram_resource_association': {
        'required': ['resource_arn', 'resource_share_arn'],
        'optional': ['region'],
    },
    # Account- and Region-scoped singleton; takes nothing but the region.
    'aws_odb_autonomous_database_secrets_manager_integration': {
        'required': [],
        'optional': ['region'],
    },
    # TDE master keys in AWS KMS: the key, the role a VM cluster assumes through
    # the OCI identity domain's OIDC provider, its KmsTde association, and the
    # key's registration in OCI (an oracle/oci resource the AWS root emits).
    'aws_kms_key': {
        'required': [],
        'optional': ['description', 'key_usage', 'customer_master_key_spec', 'policy',
                     'deletion_window_in_days', 'multi_region', 'enable_key_rotation',
                     'bypass_policy_lockout_safety_check', 'is_enabled', 'region', 'tags'],
    },
    'aws_kms_alias': {
        'required': ['target_key_id'],
        'optional': ['name', 'name_prefix', 'region'],
    },
    'aws_iam_openid_connect_provider': {
        'required': ['url', 'client_id_list'],
        'optional': ['thumbprint_list', 'tags'],
    },
    'aws_iam_role': {
        'required': ['assume_role_policy'],
        'optional': ['name', 'name_prefix', 'description', 'path', 'max_session_duration',
                     'permissions_boundary', 'force_detach_policies', 'tags'],
    },
    'aws_iam_role_policy': {
        'required': ['policy', 'role'],
        'optional': ['name', 'name_prefix'],
    },
    'aws_odb_iam_role_association': {
        'required': ['aws_integration', 'iam_role_arn', 'resource_arn'],
        'optional': ['region'],
    },
    'oci_dbmulticloud_oracle_db_aws_key': {
        'required': ['compartment_id', 'display_name', 'oracle_db_connector_id'],
        'optional': ['aws_key_arn', 'aws_account_id', 'location', 'type', 'properties',
                     'is_aws_key_enabled', 'defined_tags', 'freeform_tags'],
    },
}

AWS_RESOURCE_OUTPUTS = {
    'aws_odb_network': [
        'id', 'arn', 'oci_network_anchor_id', 'oci_vcn_id', 'display_name',
        'status', 'status_reason', 'peering_connection_id',
    ],
    'aws_odb_cloud_exadata_infrastructure': [
        'id', 'arn', 'oci_exadata_infrastructure_id', 'display_name',
        'shape', 'compute_count', 'storage_count', 'status', 'status_reason',
        'activated_storage_count', 'additional_storage_count',
        'availability_zone', 'availability_zone_id',
    ],
    'aws_odb_network_peering_connection': [
        'id', 'arn', 'display_name', 'status', 'status_reason',
        'odb_network_id', 'peer_network_id',
    ],
    'aws_odb_cloud_vm_cluster': [
        'id', 'arn', 'display_name', 'gi_version', 'hostname_prefix',
        'hostname_prefix_computed', 'license_model', 'cpu_core_count',
        'cluster_name', 'scan_dns_name', 'scan_ip_ids', 'status', 'status_reason',
        'lifecycle_state', 'node_count', 'shape', 'storage_size_in_gbs',
        'data_storage_size_in_tbs', 'db_node_storage_size_in_gbs',
        'memory_size_in_gbs', 'scan_listener_port_tcp', 'system_version',
    ],
    'aws_odb_autonomous_database': [
        'id', 'arn', 'ocid', 'display_name', 'db_name', 'status', 'status_reason',
        'private_endpoint', 'private_endpoint_ip', 'odb_network_arn',
        'service_console_url', 'sql_web_developer_url', 'oci_url',
        'compute_model', 'database_type', 'allocated_storage_size_in_tbs',
        'actual_used_data_storage_size_in_tbs', 'availability_zone',
        'availability_zone_id', 'oci_resource_anchor_name',
    ],
    'aws_odb_autonomous_database_secrets_manager_integration': [
        'id', 'role_arn', 'status', 'status_reason',
    ],
    'aws_ram_resource_share': ['id', 'arn', 'name', 'status', 'owning_account_id'],
}
