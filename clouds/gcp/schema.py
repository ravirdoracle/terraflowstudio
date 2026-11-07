"""GCP Oracle Database provider schemas — hashicorp/google (7.33.0)."""

GCP_SCHEMAS = {
    'google_oracle_database_odb_network': {
        'required': ['odb_network_id', 'location', 'network'],
        'optional': ['project', 'gcp_oracle_zone', 'deletion_protection', 'labels'],
    },
    'google_oracle_database_odb_subnet': {
        'required': ['odb_subnet_id', 'location', 'odbnetwork', 'cidr_range', 'purpose'],
        'optional': ['project', 'deletion_protection', 'labels'],
    },
    'google_oracle_database_cloud_exadata_infrastructure': {
        'required': ['cloud_exadata_infrastructure_id', 'location', 'shape',
                     'compute_count', 'storage_count'],
        'optional': ['display_name', 'gcp_oracle_zone', 'project',
                     'total_storage_size_gb', 'maintenance_window',
                     'customer_contacts', 'deletion_protection', 'labels'],
    },
    'google_oracle_database_cloud_vm_cluster': {
        'required': ['cloud_vm_cluster_id', 'location', 'exadata_infrastructure',
                     'odb_network', 'odb_subnet', 'backup_odb_subnet',
                     'gi_version', 'hostname_prefix', 'cpu_core_count',
                     'ssh_public_keys'],
        'optional': ['display_name', 'project', 'memory_size_gb',
                     'db_node_storage_size_gb', 'data_storage_size_tb',
                     'local_backup_enabled', 'sparse_diskgroup_enabled',
                     'license_type', 'db_server_ocids', 'cluster_name',
                     'scan_listener_port_tcp', 'time_zone',
                     'deletion_protection', 'labels'],
    },
    # Serverless: regional, so no gcp_oracle_zone, and no exadata_infrastructure.
    # Networking is either the odb_network/odb_subnet pair (what this app
    # generates) or the legacy network/cidr pair against a plain VPC.
    'google_oracle_database_autonomous_database': {
        'required': ['autonomous_database_id', 'location'],
        'optional': ['project', 'database', 'display_name', 'admin_password',
                     'network', 'cidr', 'odb_network', 'odb_subnet',
                     'properties', 'source_config', 'deletion_policy',
                     'deletion_protection', 'labels'],
    },
    # Exascale — hashicorp/google >= 7.20.0 (7.19.0 lacks both).
    'google_oracle_database_exascale_db_storage_vault': {
        'required': ['exascale_db_storage_vault_id', 'display_name', 'location', 'properties'],
        'optional': ['project', 'gcp_oracle_zone', 'exadata_infrastructure',
                     'deletion_protection', 'deletion_policy', 'labels'],
    },
    # No zone input and no Exadata Infrastructure: it runs in its vault's zone.
    'google_oracle_database_exadb_vm_cluster': {
        'required': ['exadb_vm_cluster_id', 'display_name', 'location', 'odb_subnet',
                     'backup_odb_subnet', 'properties'],
        'optional': ['project', 'odb_network', 'deletion_protection', 'deletion_policy', 'labels'],
    },
}

GCP_RESOURCE_OUTPUTS = {
    'google_oracle_database_odb_network': [
        'id', 'name', 'create_time', 'state', 'effective_labels',
        'terraform_labels',
    ],
    'google_oracle_database_odb_subnet': [
        'id', 'name', 'create_time', 'state',
    ],
    'google_oracle_database_cloud_exadata_infrastructure': [
        'id', 'name', 'create_time', 'state', 'display_name',
        'shape', 'compute_count', 'storage_count', 'total_storage_size_gb',
        'available_storage_size_gb', 'effective_labels',
    ],
    'google_oracle_database_cloud_vm_cluster': [
        'id', 'name', 'create_time', 'display_name',
        'hostname_prefix', 'scan_dns_name', 'effective_labels',
    ],
    'google_oracle_database_autonomous_database': [
        'id', 'name', 'create_time', 'entitlement_id',
        'peer_autonomous_databases', 'disaster_recovery_supported_locations',
        'effective_labels', 'terraform_labels',
    ],
    'google_oracle_database_exascale_db_storage_vault': [
        'id', 'name', 'create_time', 'entitlement_id', 'properties',
    ],
    'google_oracle_database_exadb_vm_cluster': [
        'id', 'name', 'exadb_vm_cluster_id', 'create_time', 'entitlement_id',
        'gcp_oracle_zone', 'identity_connector', 'properties',
    ],
}
