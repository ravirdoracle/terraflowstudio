"""
Spreadsheet import for Terraflow Studio.

Supported formats: .xlsx, .xls, .csv
Sheet names determine the resource type. Columns map directly to form field names.
Rows starting with '#' are treated as comments and skipped.
"""

import csv
import io
import re


# ── Column normalisation ───────────────────────────────────────────────────────

def _norm(s):
    # Drop the '▾' dropdown-arrow decoration that template headers add (e.g. "network_ref ▾").
    return re.sub(r'[\s\-/]+', '_', str(s).strip().lower().replace('▾', '')).strip('_')


def _coerce(val, field):
    if val is None or val == '':
        return None
    s = str(val).strip()
    if field in ('add_ssh', 'manage_route_table', 'create_pdb', 'auto_backup_enabled',
                 'local_backup_enabled', 'sparse_diskgroup_enabled', 'deletion_protection',
                 's3_access', 'zero_etl_access', 'is_local_backup_enabled',
                 'is_sparse_diskgroup_enabled', 'is_mtls_enabled_vm_cluster',
                 'delete_associated_resources', 'mw_is_custom_action_timeout_enabled',
                 'dco_is_diagnostics_events_enabled', 'dco_is_health_monitoring_enabled',
                 'dco_is_incident_logs_enabled'):
        return s.lower() in ('true', '1', 'yes', 'on')
    if field in ('cpu_core_count', 'storage_count', 'compute_count', 'memory_size_in_gbs',
                 'db_node_storage_size_in_gbs', 'recovery_window_in_days',
                 'scan_listener_port_tcp', 'total_container_databases',
                 'cpu_core_count_per_node', 'mw_lead_time_in_weeks',
                 'mw_custom_action_timeout_mins', 'scan_listener_port_non_tls',
                 'scan_listener_port_tls'):
        try: return int(float(s))
        except (ValueError, TypeError): return s
    if field in ('data_storage_size_in_tbs', 'data_storage_size_tb',
                 'autonomous_data_storage_size_in_tbs', 'memory_per_oracle_compute_unit_in_gbs'):
        try: return float(s)
        except (ValueError, TypeError): return s
    # Comma-separated columns must become real lists: the form merges the parsed
    # doc straight into its state arrays and maps over these, so a bare string
    # breaks rendering, and the HCL templates emit them as list literals.
    if field in ('ssh_public_keys', 'customer_contacts', 'peer_network_cidrs',
                 'db_servers', 'db_server_ocids'):
        return [x.strip() for x in s.split(',') if x.strip()]
    return s


def _rows_to_dicts(headers, rows):
    result = []
    for row in rows:
        first = str(row[0]).strip() if row and row[0] is not None else ''
        if first.startswith('#'):
            continue
        d = {}
        for h, v in zip(headers, row):
            if h and v is not None and str(v).strip():
                d[h] = _coerce(v, h)
        if any(v for v in d.values()):
            result.append(d)
    return result


# ── Sheet name → resource type mapping ───────────────────────────────────────

# Keys are already normalised (lowercase, underscores). More specific keys first.
_SHEET_MAP = {
    # DG — exact matches first
    'dg_multi_az':         'dg_maz',
    'dg_multi-az':         'dg_maz',
    'dg_maz':              'dg_maz',
    'multi-az':            'dg_maz',
    'multi_az':            'dg_maz',
    'dg_cross_region':     'dg_cr',
    'dg_cross-region':     'dg_cr',
    'cross-region':        'dg_cr',
    'cross_region':        'dg_cr',
    'dg_cr':               'dg_cr',
    # GCP — prefix 'gcp_' to avoid collision with AWS
    'gcp_odb_networks':    'gcp_net',
    'gcp_odb_network':     'gcp_net',
    'gcp_networks':        'gcp_net',
    'gcp_network':         'gcp_net',
    'gcp_exadata_infra':   'gcp_infra',
    'gcp_infrastructure':  'gcp_infra',
    'gcp_infra':           'gcp_infra',
    'gcp_vm_clusters':     'gcp_cluster',
    'gcp_vm_cluster':      'gcp_cluster',
    'gcp_clusters':        'gcp_cluster',
    # Azure — prefix 'azure_'
    'azure_virtual_networks': 'azure_vnet',
    'azure_virtual_network':  'azure_vnet',
    'azure_vnets':            'azure_vnet',
    'azure_vnet':             'azure_vnet',
    'virtual_networks':       'azure_vnet',
    'azure_exadata_infra':    'azure_infra',
    'azure_infrastructure':   'azure_infra',
    'azure_infra':            'azure_infra',
    'azure_vm_clusters':      'azure_cluster',
    'azure_vm_cluster':       'azure_cluster',
    'azure_clusters':         'azure_cluster',
    # AWS — generic names (lower priority — matched last via partial)
    'odb_networks':            'aws_net',
    'odb_network':             'aws_net',
    'networks':                'aws_net',
    'exadata_infra':           'aws_infra',
    'infrastructure':          'aws_infra',
    'infra':                   'aws_infra',
    'vm_clusters':             'aws_cluster',
    'vm_cluster':              'aws_cluster',
    'clusters':                'aws_cluster',
    'network_peerings':        'aws_peering',
    'network_peering':         'aws_peering',
    'odb_peering':             'aws_peering',
    'peerings':                'aws_peering',
    'peering':                 'aws_peering',
    'autonomous_vm_clusters':  'aws_avmc',
    'autonomous_vm_cluster':   'aws_avmc',
    'avmc':                    'aws_avmc',
    'oci_databases':           'oci_db',
    'oci_database':            'oci_db',
    'db_home':                 'oci_db',
}


def _detect_sheet_type(headers, sheet_name):
    sn = _norm(sheet_name)
    # Direct lookup on normalised key
    if sn in _SHEET_MAP:
        return _SHEET_MAP[sn]
    # Prefix-based partial match (longer keys win by checking specific prefixes)
    for prefix in ('dg_', 'gcp_', 'azure_'):
        if sn.startswith(prefix):
            for key, rtype in _SHEET_MAP.items():
                if key.startswith(prefix) and (key in sn or sn.startswith(key)):
                    return rtype
    # Generic partial match for AWS sheets
    for key, rtype in _SHEET_MAP.items():
        if key in sn or sn == key:
            return rtype
    # Column-based fallback for DG
    hn = set(headers)
    if 'primary_oci_region' in hn and 'standby_oci_region' in hn:
        return 'dg_cr'
    if 'oci_region' in hn:
        return 'dg_maz'
    return None


# ── Excel parser ──────────────────────────────────────────────────────────────

def _parse_excel(fileobj, cloud_hint=''):
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError('openpyxl is required. Run: pip install openpyxl')

    wb = openpyxl.load_workbook(fileobj, read_only=True, data_only=True)
    result = _empty_result()

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.values)
        if not rows:
            continue
        headers = [_norm(h) for h in rows[0] if h is not None]
        rtype = _detect_sheet_type(headers, sheet_name)
        if rtype is None:
            continue
        data = _rows_to_dicts(headers, rows[1:])
        _add_to_result(result, rtype, data)

    return result


# ── CSV parser ────────────────────────────────────────────────────────────────

def _parse_csv(fileobj, cloud_hint=''):
    text = fileobj.read().decode('utf-8-sig')
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return _empty_result()

    headers = [_norm(h) for h in rows[0]]
    rtype = _detect_sheet_type(headers, '')
    if rtype is None:
        raise ValueError(
            'Could not detect resource type from CSV columns. '
            'Ensure the header row contains recognised column names. '
            'Download the template for the correct column names.'
        )
    data = _rows_to_dicts(headers, rows[1:])
    result = _empty_result()
    _add_to_result(result, rtype, data)
    return result


def _empty_result():
    return {
        'dg_multi_az': [], 'dg_cross_region': [],
        'aws_networks': [], 'aws_infras': [], 'aws_clusters': [],
        'aws_peerings': [], 'aws_avmclusters': [], 'aws_oci_databases': [],
        'gcp_networks': [], 'gcp_infras': [], 'gcp_clusters': [],
        'azure_vnets': [], 'azure_infras': [], 'azure_clusters': [],
    }


def _add_to_result(result, rtype, data):
    mapping = {
        'dg_maz':        'dg_multi_az',
        'dg_cr':         'dg_cross_region',
        'aws_net':       'aws_networks',
        'aws_infra':     'aws_infras',
        'aws_peering':   'aws_peerings',
        'aws_cluster':   'aws_clusters',
        'aws_avmc':      'aws_avmclusters',
        'oci_db':        'aws_oci_databases',
        'gcp_net':       'gcp_networks',
        'gcp_infra':     'gcp_infras',
        'gcp_cluster':   'gcp_clusters',
        'azure_vnet':    'azure_vnets',
        'azure_infra':   'azure_infras',
        'azure_cluster': 'azure_clusters',
    }
    key = mapping.get(rtype)
    if key and key in result:
        result[key].extend(data)


# ── Public entry point ────────────────────────────────────────────────────────

def parse_spreadsheet(fileobj, filename: str, cloud_hint: str = '') -> dict:
    fn = filename.lower()
    if fn.endswith('.csv'):
        result = _parse_csv(fileobj, cloud_hint)
    elif fn.endswith(('.xlsx', '.xls')):
        result = _parse_excel(fileobj, cloud_hint)
    else:
        raise ValueError(f'Unsupported file type. Use .xlsx or .csv')

    # Determine the cloud from populated keys
    if not cloud_hint:
        if result['dg_multi_az'] or result['dg_cross_region']:
            cloud_hint = 'dg'
        elif result['gcp_networks'] or result['gcp_infras'] or result['gcp_clusters']:
            cloud_hint = 'gcp'
        elif result['azure_vnets'] or result['azure_infras'] or result['azure_clusters']:
            cloud_hint = 'azure'
        elif result['aws_networks'] or result['aws_infras'] or result['aws_clusters']:
            cloud_hint = 'aws'
        else:
            cloud_hint = 'aws'

    result['cloud'] = cloud_hint
    return result


# ── Template column definitions ───────────────────────────────────────────────

_TEMPLATES = {

# ── DG Multi-AZ ──────────────────────────────────────────────────────────────
'dg_maz': ('DG Multi-AZ', [
    ('module_name',            'primary',              'Unique name — used as directory name suffix'),
    ('prefix',                 'dg',                   'Resource name prefix'),
    ('oci_region',             'us-ashburn-1',         'OCI region (both AZs in same region)'),
    ('compartment_id',         '',                     'OCI compartment OCID'),
    ('primary_vcn_id',         '',                     'Primary VM Cluster VCN OCID'),
    ('primary_nsg_id',         '',                     'Primary VM Cluster NSG OCID'),
    ('primary_client_cidr',    '10.10.1.0/24',         'Primary client subnet CIDR'),
    ('primary_route_table_id', '',                     'Primary default route table OCID (leave blank = manual)'),
    ('standby_vcn_id',         '',                     'Standby VM Cluster VCN OCID'),
    ('standby_nsg_id',         '',                     'Standby VM Cluster NSG OCID'),
    ('standby_client_cidr',    '10.20.1.0/24',         'Standby client subnet CIDR'),
    ('standby_route_table_id', '',                     'Standby default route table OCID'),
    ('add_ssh',                'false',                'true/false — add SSH port 22 NSG rules'),
    ('manage_route_table',     'false',                'true = Terraform-managed; false = manual'),
]),

# ── DG Cross-Region ───────────────────────────────────────────────────────────
'dg_cr': ('DG Cross-Region', [
    ('module_name',              'primary',            'Unique name'),
    ('prefix',                   'dg',                 'Resource name prefix'),
    ('primary_oci_region',       'us-ashburn-1',       'Primary OCI region'),
    ('standby_oci_region',       'us-portland-1',      'DR OCI region'),
    ('compartment_id',           '',                   'OCI compartment OCID'),
    ('primary_vcn_id',           '',                   'Primary VM Cluster VCN OCID'),
    ('primary_nsg_id',           '',                   'Primary VM Cluster NSG OCID'),
    ('primary_client_cidr',      '10.10.1.0/24',       'Primary client subnet CIDR'),
    ('primary_hub_cidr',         '10.15.0.0/24',       'Primary Hub VCN CIDR'),
    ('primary_route_table_id',   '',                   'Primary default route table OCID'),
    ('standby_vcn_id',           '',                   'DR VM Cluster VCN OCID'),
    ('standby_nsg_id',           '',                   'DR VM Cluster NSG OCID'),
    ('standby_client_cidr',      '10.30.1.0/24',       'DR client subnet CIDR'),
    ('standby_hub_cidr',         '10.16.0.0/24',       'DR Hub VCN CIDR'),
    ('standby_route_table_id',   '',                   'DR default route table OCID'),
    ('add_ssh',                  'false',              'true/false — SSH NSG rules'),
    ('manage_route_table',       'false',              'true = Terraform-managed; false = manual'),
]),

# ── AWS ODB Network (UI screen: "ODB Network" tab) ───────────────────────────
'aws_net': ('ODB Networks', [
    ('module_name',                 'odb_network',    'Unique name — referenced by VM Cluster / Peering sheets'),
    ('display_name',                'my-odb-network', 'Display name for the ODB network'),
    ('region',                      'us-east-1',      'AWS region'),
    ('availability_zone_id',        'use1-az6',       'AZ ID (not name), e.g. use1-az6'),
    ('client_subnet_cidr',          '10.2.0.0/24',    'Client subnet CIDR'),
    ('backup_subnet_cidr',          '10.2.1.0/24',    'Backup subnet CIDR'),
    ('s3_access',                   'false',          'true/false — enable S3 access'),
    ('zero_etl_access',             'false',          'true/false — enable Zero-ETL access'),
    ('availability_zone',           '',               'Optional AZ name (prefer availability_zone_id)'),
    ('default_dns_prefix',          '',               'Optional DNS prefix (blank if using custom_domain_name)'),
    ('custom_domain_name',          '',               'Optional custom domain'),
    ('delete_associated_resources', 'false',          'true/false — delete associated resources on destroy'),
]),

# ── AWS Exadata Infra (UI screen: "Exadata Infra" tab) ───────────────────────
'aws_infra': ('Exadata Infra', [
    ('module_name',                         'odb_exaInfra',  'Unique name — referenced by VM Cluster / AVMC sheets'),
    ('display_name',                        'my-exainfra',   'Display name'),
    ('region',                              'us-east-1',     'AWS region'),
    ('availability_zone_id',                'use1-az6',      'AZ ID — must match the ODB network'),
    ('shape',                               'Exadata.X11M',  'Shape: Exadata.X9M / X10M / X11M'),
    ('compute_count',                       '2',             'Compute nodes (min 2)'),
    ('storage_count',                       '3',             'Storage nodes (min 3)'),
    ('database_server_type',                '',              'Optional DB server type, e.g. X11M'),
    ('storage_server_type',                 '',              'Optional storage server type'),
    ('customer_contacts',                   '',              'Comma-separated notification emails'),
    ('mw_preference',                       'NO_PREFERENCE', 'NO_PREFERENCE or CUSTOM_PREFERENCE'),
    ('mw_patching_mode',                    'ROLLING',       'ROLLING or NON_ROLLING'),
    ('mw_is_custom_action_timeout_enabled', 'false',         'true/false'),
    ('mw_custom_action_timeout_mins',       '15',            'Custom action timeout (mins)'),
]),

# ── AWS Network Peering (UI screen: "Network Peering" tab) ───────────────────
'aws_peering': ('Network Peerings', [
    ('module_name',        'odb_peering',           'Unique name'),
    ('display_name',       'my-peering',            'Display name'),
    ('network_ref',        '',                      'ODB network module_name (dropdown)'),
    ('peer_network_id',    'vpc-0123456789abcdef0', 'Peer VPC ID to connect to'),
    ('region',             '',                      'Optional region override'),
    ('peer_network_cidrs', '',                      'Comma-separated CIDRs (update-only; add after first apply)'),
]),

# ── AWS VM Cluster (UI screen: "VM Cluster" tab) ─────────────────────────────
'aws_cluster': ('VM Clusters', [
    ('module_name',                      'odb_vmcluster',    'Unique name'),
    ('display_name',                     'my-vmcluster',     'Display name'),
    ('region',                           'us-east-1',        'AWS region'),
    ('infra_ref',                        '',                 'Exadata infra module_name (dropdown)'),
    ('network_ref',                      '',                 'ODB network module_name (dropdown)'),
    ('gi_version',                       '23.0.0.0',         'Grid Infrastructure version'),
    ('hostname_prefix',                  'exadb',            'Hostname prefix'),
    ('cpu_core_count',                   '16',               'CPU core count'),
    ('license_model',                    'LICENSE_INCLUDED', 'LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE'),
    ('ssh_public_keys',                  'ssh-rsa AAAA...',  'Comma-separated SSH public keys'),
    ('db_servers_mode',                  'auto',             'auto (discover from infra) or manual'),
    ('cluster_name',                     '',                 'Optional cluster name'),
    ('timezone',                         'UTC',              'Time zone'),
    ('data_storage_size_in_tbs',         '2',                'Data storage in TiB'),
    ('db_node_storage_size_in_gbs',      '120',              'Local node storage in GiB'),
    ('memory_size_in_gbs',               '60',               'Memory in GiB'),
    ('scan_listener_port_tcp',           '1521',             'SCAN listener TCP port'),
    ('is_local_backup_enabled',          'false',            'true/false'),
    ('is_sparse_diskgroup_enabled',      'false',            'true/false'),
    ('dco_is_diagnostics_events_enabled','true',             'true/false — diagnostics events collection'),
    ('dco_is_health_monitoring_enabled', 'true',             'true/false — health monitoring'),
    ('dco_is_incident_logs_enabled',     'true',             'true/false — incident logs'),
]),

# ── AWS Autonomous VM Cluster (UI screen: "Autonomous VM Cluster" tab) ───────
'aws_avmc': ('Autonomous VM Clusters', [
    ('module_name',                          'odb_avmcluster',  'Unique name'),
    ('display_name',                         'my-avmc',         'Display name'),
    ('infra_ref',                            '',                'Exadata infra module_name (dropdown)'),
    ('network_ref',                          '',                'ODB network module_name (dropdown)'),
    ('autonomous_data_storage_size_in_tbs',  '5',               'Autonomous storage in TiB'),
    ('cpu_core_count_per_node',              '40',              'CPU cores per node'),
    ('memory_per_oracle_compute_unit_in_gbs','2',               'Memory per OCU in GiB'),
    ('total_container_databases',            '2',               'Max number of CDBs'),
    ('license_model',                        'LICENSE_INCLUDED','LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE'),
    ('scan_listener_port_non_tls',           '1521',            'Non-TLS SCAN listener port'),
    ('scan_listener_port_tls',               '2484',            'TLS SCAN listener port'),
    ('is_mtls_enabled_vm_cluster',           'false',           'true/false — enable mTLS'),
    ('db_servers_mode',                      'auto',            'auto or manual'),
    ('time_zone',                            'UTC',             'Time zone'),
    ('description',                          '',                'Optional description'),
    ('mw_preference',                        'NO_PREFERENCE',   'NO_PREFERENCE or CUSTOM_PREFERENCE'),
    ('mw_patching_mode',                     'ROLLING',         'ROLLING or NON_ROLLING'),
]),

# ── GCP ODB Network ───────────────────────────────────────────────────────────
'gcp_net': ('GCP ODB Networks', [
    ('module_name',       'gcp-odb-network',  'Module name'),
    ('odb_network_id',    'my-odb-network',   'ODB network resource ID'),
    ('location',          'us-east4',         'GCP region'),
    ('network',           'projects/PROJECT/global/networks/default', 'GCP VPC network self-link'),
    ('client_subnet_id',  'client-subnet',    'Client subnet ID'),
    ('client_cidr',       '10.0.1.0/24',      'Client subnet CIDR'),
    ('backup_subnet_id',  'backup-subnet',    'Backup subnet ID'),
    ('backup_cidr',       '10.0.2.0/24',      'Backup subnet CIDR'),
    ('deletion_protection','true',            'true/false'),
]),

# ── GCP Exadata Infra ─────────────────────────────────────────────────────────
'gcp_infra': ('GCP Exadata Infra', [
    ('module_name',                     'gcp-exadata-infra', 'Module name'),
    ('cloud_exadata_infrastructure_id', 'my-exadb-infra',    'Resource ID'),
    ('display_name',                    'my-exadb-infra',    'Display name'),
    ('location',                        'us-east4',          'GCP region'),
    ('shape',                           'Exadata.X9M',       'Shape'),
    ('compute_count',                   '2',                 'Compute nodes (min 2)'),
    ('storage_count',                   '3',                 'Storage nodes (min 3)'),
    ('deletion_protection',             'true',              'true/false'),
]),

# ── GCP VM Cluster ────────────────────────────────────────────────────────────
'gcp_cluster': ('GCP VM Clusters', [
    ('module_name',         'gcp-vm-cluster',   'Module name'),
    ('cloud_vm_cluster_id', 'my-vm-cluster',    'Cluster resource ID'),
    ('display_name',        'my-vm-cluster',    'Display name'),
    ('location',            'us-east4',         'GCP region'),
    ('gi_version',          '23.0.0.0',         'GI version'),
    ('hostname_prefix',     'vm',               'Hostname prefix'),
    ('cpu_core_count',      '16',               'CPU cores'),
    ('memory_size_gb',      '60',               'Memory in GiB'),
    ('data_storage_size_tb','4.0',              'Data storage in TiB'),
    ('license_type',        'LICENSE_INCLUDED', 'LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE'),
    ('local_backup_enabled','false',            'true/false'),
    ('infra_ref',           '',                 'Exadata infra module_name'),
    ('network_ref',         '',                 'ODB network module_name'),
    ('deletion_protection', 'true',             'true/false'),
]),

# ── Azure VNet ────────────────────────────────────────────────────────────────
'azure_vnet': ('Azure Virtual Networks', [
    ('module_name',           'azure_vnet',    'Module name'),
    ('resource_group_name',   '',              'Azure resource group name'),
    ('location',              'eastus',        'Azure region'),
    ('vnet_name',             'my-odb-vnet',   'Virtual network name'),
    ('address_space',         '10.0.0.0/16',   'VNet address space CIDR'),
    ('subnet_name',           'oracle-subnet', 'Oracle-delegated subnet name'),
    ('subnet_address_prefix', '10.0.1.0/24',   'Subnet CIDR (must be /29 or larger)'),
]),

# ── Azure Exadata Infra ───────────────────────────────────────────────────────
'azure_infra': ('Azure Exadata Infra', [
    ('module_name',           'azure_exainfra',  'Module name'),
    ('resource_group_name',   '',                'Azure resource group'),
    ('location',              'eastus',          'Azure region'),
    ('name',                  'my-exainfra',     'Resource name'),
    ('display_name',          'my-exainfra',     'Display name'),
    ('shape',                 'Exadata.X11M',    'Shape: Exadata.X9M / X10M / X11M'),
    ('compute_count',         '2',               'Compute nodes (min 2)'),
    ('storage_count',         '3',               'Storage nodes (min 3)'),
    ('zone',                  '1',               'Availability zone (1/2/3)'),
    ('mw_preference',         'NoPreference',    'Maintenance preference'),
]),

# ── Azure VM Cluster ──────────────────────────────────────────────────────────
'azure_cluster': ('Azure VM Clusters', [
    ('module_name',            'azure_vmcluster', 'Module name'),
    ('resource_group_name',    '',                'Azure resource group'),
    ('location',               'eastus',          'Azure region'),
    ('name',                   'my-vmcluster',    'Resource name'),
    ('display_name',           'my-vmcluster',    'Display name'),
    ('cpu_core_count',         '4',               'CPU core count'),
    ('gi_version',             '19.0.0.0',        'GI version'),
    ('license_model',          'LicenseIncluded', 'LicenseIncluded or BringYourOwnLicense'),
    ('data_storage_size_in_tbs','2',              'Data storage in TiB'),
    ('memory_size_in_gbs',     '60',              'Memory in GiB'),
    ('hostname',               '',                'Hostname prefix'),
    ('infra_ref',              '',                'Exadata infra module_name'),
    ('vnet_ref',               '',                'VNet module_name'),
    ('time_zone',              'UTC',             'Time zone'),
]),

}


# ── Template generator ────────────────────────────────────────────────────────

_CLOUD_SHEETS = {
    'dg':    ['dg_maz', 'dg_cr'],
    'aws':   ['aws_net', 'aws_infra', 'aws_peering', 'aws_cluster', 'aws_avmc'],
    'gcp':   ['gcp_net', 'gcp_infra', 'gcp_cluster'],
    'azure': ['azure_vnet', 'azure_infra', 'azure_cluster'],
    'oci':   [],   # placeholder — OCI DB Home/CDB/PDB can be added later
}

_CLOUD_HEADER_COLORS = {
    'dg':    '1B6FAB',
    'aws':   'E8500A',
    'gcp':   '4285F4',
    'azure': '1B7F4F',
    'oci':   'C74634',
}


def generate_template(cloud: str = 'dg') -> bytes:
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise RuntimeError('openpyxl is required. Run: pip install openpyxl')

    wb = openpyxl.Workbook()
    color = _CLOUD_HEADER_COLORS.get(cloud, '1B6FAB')

    header_fill = PatternFill('solid', fgColor=color)
    sample_fill = PatternFill('solid', fgColor='F0F6FF' if cloud in ('dg','oci') else 'FFF5F0' if cloud == 'aws' else 'F0F6FF' if cloud == 'gcp' else 'F0F5F2')
    hint_fill   = PatternFill('solid', fgColor='F5F5F5')
    header_font = Font(bold=True, color='FFFFFF', size=10)
    hint_font   = Font(italic=True, color='888888', size=9)

    sheet_keys = _CLOUD_SHEETS.get(cloud, [])
    if not sheet_keys:
        raise ValueError(f'No template defined for cloud: {cloud}')

    for key in sheet_keys:
        if key not in _TEMPLATES:
            continue
        sheet_name, columns = _TEMPLATES[key]
        ws = wb.create_sheet(sheet_name)

        for col_idx, (col_name, _, _) in enumerate(columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')

        for col_idx, (_, sample, _) in enumerate(columns, 1):
            ws.cell(row=2, column=col_idx, value=sample).fill = sample_fill

        ws.cell(row=3, column=1, value='# descriptions →').font = hint_font
        ws.cell(row=3, column=1).fill = hint_fill
        for col_idx, (_, _, hint) in enumerate(columns, 2):
            cell = ws.cell(row=3, column=col_idx, value=hint)
            cell.font = hint_font
            cell.fill = hint_fill

        for col_idx, (col_name, sample, _) in enumerate(columns, 1):
            w = max(len(col_name), len(str(sample))) + 4
            ws.column_dimensions[ws.cell(1, col_idx).column_letter].width = min(w, 45)

        ws.freeze_panes = 'A2'

    if 'Sheet' in wb.sheetnames:
        del wb['Sheet']

    # Add dependency dropdowns now that all sheets exist
    _add_dependency_dropdowns(wb, cloud)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ── Dependency dropdown definitions ──────────────────────────────────────────
# Each tuple: (source_sheet_key, target_sheet_key, target_field, dropdown_label)

_CLOUD_DEPS = {
    'aws': [
        ('aws_net',   'aws_cluster', 'network_ref', 'ODB Network'),
        ('aws_infra', 'aws_cluster', 'infra_ref',   'Exadata Infra'),
        ('aws_net',   'aws_avmc',    'network_ref', 'ODB Network'),
        ('aws_infra', 'aws_avmc',    'infra_ref',   'Exadata Infra'),
        ('aws_net',   'aws_peering', 'network_ref', 'ODB Network'),
    ],
    'gcp': [
        ('gcp_net',   'gcp_cluster', 'network_ref', 'ODB Network'),
        ('gcp_infra', 'gcp_cluster', 'infra_ref',   'Exadata Infra'),
    ],
    'azure': [
        ('azure_vnet',  'azure_cluster', 'vnet_ref',  'Virtual Network'),
        ('azure_infra', 'azure_cluster', 'infra_ref', 'Exadata Infra'),
    ],
}


def _col_letter(n):
    """1-based column index to Excel letter (A, B, ..., Z, AA, ...)."""
    result = ''
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def _add_dependency_dropdowns(wb, cloud):
    """Add cross-sheet Data Validation dropdowns to dependency reference columns."""
    try:
        from openpyxl.worksheet.datavalidation import DataValidation
        from openpyxl.styles import PatternFill, Font
    except ImportError:
        return  # silently skip if openpyxl not available

    deps = _CLOUD_DEPS.get(cloud, [])
    if not deps:
        return

    # Build sheet_key → (sheet_name, {field: col_index}) lookup
    sheet_info = {}
    for key in _CLOUD_SHEETS.get(cloud, []):
        if key not in _TEMPLATES:
            continue
        sheet_name, columns = _TEMPLATES[key]
        field_to_col = {col_name: idx for idx, (col_name, _, _) in enumerate(columns, 1)}
        sheet_info[key] = (sheet_name, field_to_col)

    dep_fill   = PatternFill('solid', fgColor='FFF9E6')   # light yellow — indicates dropdown
    dep_font   = Font(color='8B6800', size=10)

    for src_key, tgt_key, tgt_field, label in deps:
        if src_key not in sheet_info or tgt_key not in sheet_info:
            continue

        src_sheet_name, _ = sheet_info[src_key]
        tgt_sheet_name, tgt_fields = sheet_info[tgt_key]

        if tgt_field not in tgt_fields:
            continue

        tgt_col_idx = tgt_fields[tgt_field]
        tgt_col_ltr = _col_letter(tgt_col_idx)

        # Source is always module_name = column A of the source sheet
        # Data rows start at row 2; allow up to row 200
        src_ref = f"'{src_sheet_name}'!$A$2:$A$200"

        tgt_ws = wb[tgt_sheet_name]

        # Data validation on data rows (2 onward, skip header row 1 and hint row 3)
        dv = DataValidation(
            type='list',
            formula1=src_ref,
            allow_blank=True,
            showDropDown=False,   # False = show dropdown arrow
            showErrorMessage=True,
            errorTitle='Invalid reference',
            error=f'Select a {label} module_name from the "{src_sheet_name}" sheet.',
            showInputMessage=True,
            promptTitle=f'{label} reference',
            prompt=f'Select from "{src_sheet_name}" sheet. Must match a module_name value on that sheet.',
        )
        tgt_ws.add_data_validation(dv)
        # Apply to rows 2–200, skipping row 3 (hint row) by covering the range anyway
        dv.sqref = f'{tgt_col_ltr}2:{tgt_col_ltr}200'

        # Highlight the header cell to indicate it has a dropdown
        hdr_cell = tgt_ws.cell(row=1, column=tgt_col_idx)
        hdr_cell.value = f'{tgt_field} ▾'   # add arrow indicator to header

        # Highlight the sample cell
        sample_cell = tgt_ws.cell(row=2, column=tgt_col_idx)
        sample_cell.fill = dep_fill
        if sample_cell.font:
            sample_cell.font = dep_font
