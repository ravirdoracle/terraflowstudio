"""OCI provider schemas — oracle/oci (9.11.0), for the resources this app generates.

Taken from `terraform providers schema -json`, not from the docs: `required` is
what the provider marks Required (or a block with min_items > 0), outputs are the
Computed-only attributes.
"""

OCI_SCHEMAS = {
    # ── Data Guard networking ────────────────────────────────────────────────
    'oci_core_vcn': {
        'required': ['compartment_id'],
        'optional': ['cidr_block', 'cidr_blocks', 'display_name', 'dns_label',
                     'defined_tags', 'freeform_tags'],
    },
    'oci_core_drg': {
        'required': ['compartment_id'],
        'optional': ['display_name', 'defined_tags', 'freeform_tags'],
    },
    'oci_core_drg_attachment': {
        'required': ['drg_id'],
        'optional': ['vcn_id', 'network_details', 'route_table_id',
                     'drg_route_table_id', 'display_name'],
    },
    'oci_core_local_peering_gateway': {
        'required': ['compartment_id', 'vcn_id'],
        'optional': ['peer_id', 'route_table_id', 'display_name',
                     'defined_tags', 'freeform_tags'],
    },
    'oci_core_remote_peering_connection': {
        'required': ['compartment_id', 'drg_id'],
        'optional': ['peer_id', 'peer_region_name', 'display_name',
                     'defined_tags', 'freeform_tags'],
    },
    'oci_core_route_table': {
        'required': ['compartment_id', 'vcn_id'],
        'optional': ['route_rules', 'display_name', 'defined_tags', 'freeform_tags'],
    },
    'oci_core_default_route_table': {
        'required': ['manage_default_resource_id'],
        'optional': ['compartment_id', 'route_rules', 'display_name'],
    },
    'oci_core_network_security_group_security_rule': {
        'required': ['network_security_group_id', 'direction', 'protocol'],
        'optional': ['description', 'source', 'source_type', 'destination',
                     'destination_type', 'stateless', 'tcp_options',
                     'udp_options', 'icmp_options'],
    },
    # ── Database layer (DB Home / CDB / PDB) ─────────────────────────────────
    'oci_database_db_home': {
        'required': [],
        'optional': ['vm_cluster_id', 'db_version', 'display_name', 'source',
                     'database', 'database_software_image_id', 'kms_key_id'],
    },
    'oci_database_database': {
        'required': ['source', 'database'],
        'optional': ['db_home_id', 'db_version', 'vm_cluster_id', 'kms_key_id',
                     'key_store_id', 'vault_id'],
    },
    'oci_database_pluggable_database': {
        'required': ['container_database_id', 'pdb_name'],
        'optional': ['pdb_admin_password', 'tde_wallet_password',
                     'should_pdb_admin_account_be_locked', 'pdb_creation_type_details'],
    },
    # ── Customer-managed TDE keys ────────────────────────────────────────────
    # The AWS key resource is declared by clouds/aws/schema.py, which owns it.
    'oci_identity_policy': {
        'required': ['compartment_id', 'description', 'name', 'statements'],
        'optional': ['version_date', 'defined_tags', 'freeform_tags'],
    },
    'oci_dbmulticloud_oracle_db_gcp_key_ring': {
        'required': ['compartment_id', 'display_name', 'oracle_db_connector_id'],
        'optional': ['gcp_key_ring_id', 'location', 'properties', 'type',
                     'defined_tags', 'freeform_tags'],
    },
}

OCI_RESOURCE_OUTPUTS = {
    'oci_core_vcn': ['id', 'state', 'time_created', 'default_route_table_id',
                     'default_security_list_id', 'default_dhcp_options_id',
                     'vcn_domain_name', 'cidr_blocks'],
    'oci_core_drg': ['id', 'state', 'time_created', 'default_drg_route_tables',
                     'redundancy_status'],
    'oci_core_drg_attachment': ['id', 'state', 'time_created', 'compartment_id'],
    'oci_core_local_peering_gateway': ['id', 'state', 'time_created', 'peering_status',
                                       'peer_advertised_cidr', 'is_cross_tenancy_peering'],
    'oci_core_remote_peering_connection': ['id', 'state', 'time_created', 'peering_status',
                                           'peer_tenancy_id'],
    'oci_core_route_table': ['id', 'state', 'time_created'],
    'oci_core_default_route_table': ['id', 'state', 'time_created'],
    'oci_core_network_security_group_security_rule': ['id', 'is_valid', 'time_created'],
    'oci_database_db_home': ['id', 'state', 'compartment_id', 'db_home_location'],
    'oci_database_database': ['id', 'state', 'db_name', 'db_unique_name',
                              'connection_strings', 'compartment_id'],
    'oci_database_pluggable_database': ['id', 'state', 'open_mode', 'connection_strings'],
    'oci_identity_policy': ['id', 'state', 'time_created'],
    'oci_dbmulticloud_oracle_db_gcp_key_ring': ['id', 'state', 'time_created'],
}
