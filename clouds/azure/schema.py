"""Azure AI DB@Azure provider schemas — hashicorp/azurerm (4.74.0)."""

AZURE_SCHEMAS = {
    'azurerm_virtual_network': {
        'required': ['name', 'address_space', 'location', 'resource_group_name'],
        'optional': ['tags'],
    },
    'azurerm_subnet': {
        'required': ['name', 'resource_group_name', 'virtual_network_name', 'address_prefixes'],
        'optional': ['delegation'],
    },
    'azurerm_oracle_exadata_infrastructure': {
        'required': ['name', 'resource_group_name', 'location', 'shape',
                     'compute_count', 'storage_count', 'zones'],
        'optional': ['display_name', 'maintenance_window', 'tags',
                     'database_server_type', 'storage_server_type'],
    },
    'azurerm_oracle_cloud_vm_cluster': {
        'required': ['name', 'resource_group_name', 'location',
                     'cloud_exadata_infrastructure_id', 'subnet_id',
                     'virtual_network_id', 'hostname', 'cpu_core_count',
                     'data_storage_size_in_tbs', 'gi_version',
                     'license_model', 'ssh_public_keys'],
        'optional': ['display_name', 'cluster_name', 'domain', 'backup_subnet_cidr',
                     'data_storage_percentage', 'time_zone',
                     'scan_listener_port_tcp', 'db_servers',
                     'data_collection_options', 'tags'],
    },
    'azurerm_oracle_autonomous_database': {
        'required': ['name', 'display_name', 'resource_group_name', 'location',
                     'db_workload', 'db_version', 'license_model', 'compute_model',
                     'compute_count', 'data_storage_size_in_tbs',
                     'auto_scaling_enabled', 'auto_scaling_for_storage_enabled',
                     'backup_retention_period_in_days', 'character_set',
                     'national_character_set', 'admin_password',
                     'mtls_connection_required'],
        'optional': ['subnet_id', 'virtual_network_id', 'allowed_ips',
                     'customer_contacts', 'long_term_backup_schedule', 'tags'],
    },
    # azurerm 5.12.0: location and linked_compartment_id are computed.
    'azurerm_oracle_resource_anchor': {
        'required': ['name', 'resource_group_name'],
        'optional': ['tags'],
    },
    # azure/azapi 2.13.0 - the Network Anchor (Oracle.Database/networkAnchors),
    # which azurerm has no resource for. Only `type` is schema-required; name and
    # parent_id are required by the API for a resource like this one.
    'azapi_resource': {
        'required': ['type'],
        'optional': ['name', 'parent_id', 'location', 'body', 'tags',
                     'ignore_null_property', 'response_export_values', 'timeouts'],
    },
}

AZURE_RESOURCE_OUTPUTS = {
    'azurerm_virtual_network': ['id', 'name', 'location', 'resource_group_name'],
    'azurerm_subnet': ['id', 'name'],
    'azurerm_oracle_exadata_infrastructure': ['id', 'name'],
    'azurerm_oracle_cloud_vm_cluster': ['id', 'name', 'ocid'],
    'azurerm_oracle_autonomous_database': ['id', 'name'],
    'azurerm_oracle_resource_anchor': ['id', 'name', 'location', 'linked_compartment_id'],
    'azapi_resource': ['id', 'name', 'output'],
}
