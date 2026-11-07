"""Oracle AI Database@GCP payload validation.

Rules for the form payload the browser POSTs to /api/validate - required fields,
value ranges, CIDR sanity. Distinct from schema.py, which describes the Terraform
provider's own resource schema and is used by tf_validator.

Owned entirely by this cloud: nothing here is imported by another cloud package,
so a rule change cannot affect AWS or Azure.
"""
import re


def validate(data, errors):
    """Populate `errors` as {{module_name: {{field: message}}}}. Returns nothing."""
    return _validate_gcp(data, errors)


def _validate_gcp(data, errors):
    def _err(mn, f, m): errors.setdefault(mn, {})[f] = m
    tab = data.get('tab', 0)

    if tab == 10:  # GCP Networks
        for net in data.get('gcp_networks', [data.get('gcp_module_0', {})]):
            mn = net.get('module_name', 'gcp_network')
            purpose = net.get('purpose') or 'both'
            if purpose not in ('dedicated', 'adbs', 'both'):
                _err(mn, 'purpose', 'Must be dedicated, adbs or both')
            if not net.get('odb_network_id'): _err(mn, 'odb_network_id', 'Required')
            if not net.get('location'):        _err(mn, 'location',       'Required')
            if not net.get('client_cidr') and not net.get('client_subnet_cidr'):
                _err(mn, 'client_cidr', 'Required')
            # An ADB-S-only network has no backup subnet: backup subnets serve
            # Exadata VM Clusters, and an Autonomous Database never uses one.
            if purpose != 'adbs':
                if not net.get('backup_cidr') and not net.get('backup_subnet_cidr'):
                    _err(mn, 'backup_cidr', 'Required')

    elif tab == 12:  # GCP Infras
        for inf in data.get('gcp_infras', [data.get('gcp_module_3', {})]):
            mn = inf.get('module_name', 'gcp_infra')
            if not inf.get('cloud_exadata_infrastructure_id'): _err(mn, 'cloud_exadata_infrastructure_id', 'Required')
            if not inf.get('location'):  _err(mn, 'location', 'Required')
            if not inf.get('shape'):     _err(mn, 'shape',    'Required')
            if int(inf.get('compute_count', 0) or 0) < 2: _err(mn, 'compute_count', 'Minimum 2')
            if int(inf.get('storage_count', 0) or 0) < 3: _err(mn, 'storage_count', 'Minimum 3')

    elif tab == 13:  # GCP VM Clusters
        adbs_only_nets = {n.get('module_name') for n in data.get('gcp_networks', [])
                          if n.get('purpose') == 'adbs'}
        for cl in data.get('gcp_clusters', [data.get('gcp_module_4', {})]):
            mn = cl.get('module_name', 'gcp_cluster')
            if not cl.get('cloud_vm_cluster_id'):  _err(mn, 'cloud_vm_cluster_id', 'Required')
            if not cl.get('location'):             _err(mn, 'location',            'Required')
            if not cl.get('hostname_prefix'):      _err(mn, 'hostname_prefix',     'Required')
            if int(cl.get('cpu_core_count', 0) or 0) < 2:
                _err(mn, 'cpu_core_count', 'Minimum 2')
            if not cl.get('ssh_public_keys'):
                _err(mn, 'ssh_public_keys', 'At least one SSH key required')
            # A VM Cluster needs a backup subnet, which an ADB-S-only network
            # does not build. Set that network to "both" or point elsewhere.
            if cl.get('network_ref') in adbs_only_nets:
                _err(mn, 'network_ref',
                     'That ODB Network is ADB-S only and has no backup subnet — set it to "both"')

    elif tab == 14:  # GCP OCI DB Home / CDB / PDB
        for db in data.get('gcp_oci_databases', []):
            mn = db.get('module_name', 'oci_database')
            if not db.get('vmcluster_ref'): _err(mn, 'vmcluster_ref', 'VM Cluster reference required')
            if not db.get('db_version'):    _err(mn, 'db_version',    'Required')
            if not db.get('db_name'):       _err(mn, 'db_name',       'Required')

    elif tab == 15:  # GCP Autonomous AI Database (Serverless)
        dedicated_only_nets = {n.get('module_name') for n in data.get('gcp_networks', [])
                               if n.get('purpose') == 'dedicated'}
        for adb in data.get('gcp_autonomous_dbs', []):
            mn = adb.get('module_name', 'gcp_adb')
            if adb.get('network_ref') in dedicated_only_nets:
                _err(mn, 'network_ref',
                     'That ODB Network is marked Dedicated (Exadata) only — set it to "both" or "adbs"')
            if not adb.get('autonomous_database_id'):
                _err(mn, 'autonomous_database_id', 'Required')
            if not adb.get('database'):    _err(mn, 'database', 'Required')
            if not adb.get('location'):    _err(mn, 'location', 'Required')
            # Serverless takes no infra_ref, but the private endpoint still
            # lands in an ODB Network's client subnet.
            if not adb.get('network_ref'): _err(mn, 'network_ref', 'ODB Network reference required')
            if float(adb.get('compute_count', 0) or 0) < 2:
                _err(mn, 'compute_count', 'Minimum 2 ECPU')
            if int(adb.get('data_storage_size_gb', 0) or 0) < 20:
                _err(mn, 'data_storage_size_gb', 'Minimum 20 GB')
            days = int(adb.get('backup_retention_period_days', 0) or 0)
            if days and not (1 <= days <= 60):
                _err(mn, 'backup_retention_period_days', 'Must be 1–60 days')
            if adb.get('db_workload') not in ('OLTP', 'DW', 'AJD', 'APEX'):
                _err(mn, 'db_workload', 'Must be OLTP, DW, AJD or APEX')

    elif tab == 16:  # Customer-managed TDE keys (Google Cloud KMS)
        clusters = {c.get('module_name'): c for c in data.get('gcp_clusters', [])}
        net_project = next((n.get('project') for n in data.get('gcp_networks', []) if n.get('project')), '')
        names = [k.get('module_name') for k in data.get('gcp_kms_keys', [])]
        for k in data.get('gcp_kms_keys', []):
            _check_kms(k, k.get('module_name', 'exadb_kms'), clusters, names, _err, net_project)

    elif tab == 17:  # Exascale Database Storage Vaults
        for v in data.get('gcp_exascale_vaults', []):
            _check_xs_vault(v, v.get('module_name', 'gcp_xs_vault'), _err)

    elif tab == 18:  # Exascale VM Clusters
        nets = {n.get('module_name'): n.get('purpose') or 'both' for n in data.get('gcp_networks', [])}
        vaults = {v.get('module_name') for v in data.get('gcp_exascale_vaults', [])}
        for c in data.get('gcp_exascale_clusters', []):
            _check_xs_cluster(c, c.get('module_name', 'gcp_xs_cluster'), nets, vaults, _err)


_PLACEHOLDER = 'CHANGEME'
_KMS_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]{1,63}$')
_ROLE_ID_RE = re.compile(r'^[a-zA-Z0-9_.]{3,64}$')
_PROJECT_RE = re.compile(r'^[a-z][a-z0-9-]{4,28}[a-z0-9]$')
_SA_EMAIL_RE = re.compile(r'^[a-z0-9-]+@[a-z0-9.-]+\.gserviceaccount\.com$')
_OCI_REGION_RE = re.compile(r'^[a-z]{2,3}-[a-z]+-\d+$')


def _set(v):
    """A real value, not blank and not the generator's CHANGEME placeholder."""
    v = (v or '').strip()
    return v if v and v != _PLACEHOLDER else ''


def _check_kms(k, mn, clusters, names, _err, net_project=''):
    """The values the ExaDB-D / Cloud KMS guide calls easy to get wrong.

    The service-agent email, connector OCID, compartment and home region only
    exist once the VM cluster is provisioned, so a card can be saved without
    them - but not validated, since the roots cannot apply until they are set.
    """
    if names.count(mn) > 1:
        _err(mn, 'module_name', 'Two KMS cards share this name - each gets its own kms/<name>/ directory')
    if k.get('cluster_ref') and clusters and k['cluster_ref'] not in clusters:
        _err(mn, 'cluster_ref', f'No VM cluster named "{k["cluster_ref"]}" in this configuration')

    project = _set(k.get('gcp_project_id'))
    # Blank derives from the VM cluster, then the network - the same order as
    # the generator. With none of them set it would write projects/CHANGEME/.
    derived = _set((clusters.get(k.get('cluster_ref')) or {}).get('project')) or _set(net_project)
    if not project and not derived:
        _err(mn, 'gcp_project_id', 'Required - no project on this card, its VM cluster or the ODB network')
    if project and not _PROJECT_RE.match(project):
        _err(mn, 'gcp_project_id', 'Not a GCP project ID (6-30 lowercase letters, digits, hyphens)')
    for field, label in (('gcp_key_ring_name', 'Key ring'), ('gcp_crypto_key_name', 'Crypto key')):
        v = (k.get(field) or '').strip()
        if v and not _KMS_NAME_RE.match(v):
            _err(mn, field, f'{label} names are 1-63 letters, digits, _ or -')
    role = (k.get('oracle_kms_role_id') or '').strip()
    if role and not _ROLE_ID_RE.match(role):
        _err(mn, 'oracle_kms_role_id', 'Role IDs are 3-64 letters, digits, _ or .')
    if (k.get('key_protection_level') or 'HSM').upper() not in ('HSM', 'SOFTWARE'):
        _err(mn, 'key_protection_level', 'Must be HSM or SOFTWARE')

    sa = _set(k.get('oracle_workload_resource_service_agent'))
    if not sa:
        _err(mn, 'oracle_workload_resource_service_agent',
             'Required - copy it from the VM cluster\'s GCP Identity Connector in the OCI console')
    elif not _SA_EMAIL_RE.match(sa):
        _err(mn, 'oracle_workload_resource_service_agent', 'Not a Google service-account email')

    conn = _set(k.get('oci_gcp_identity_connector_ocid'))
    if not conn:
        _err(mn, 'oci_gcp_identity_connector_ocid', 'Required - the Identity Connector\'s OCID, from the VM cluster')
    elif conn.startswith(('ocid1.compartment.', 'ocid1.tenancy.')):
        # The guide's most common failure: "Unknown resource Entity of type DBGcpConnector".
        _err(mn, 'oci_gcp_identity_connector_ocid',
             'That is a compartment/tenancy OCID - this field needs the GCP Identity Connector\'s own OCID')
    elif not conn.startswith('ocid1.'):
        _err(mn, 'oci_gcp_identity_connector_ocid', 'Not an OCID')

    comp = _set(k.get('oci_compartment_ocid'))
    if not comp:
        _err(mn, 'oci_compartment_ocid', 'Required - the compartment of the ExaDB-D VM cluster')
    elif not comp.startswith(('ocid1.compartment.', 'ocid1.tenancy.')):
        _err(mn, 'oci_compartment_ocid', 'Must be a compartment (or tenancy) OCID')

    for field, label in (('oci_home_region', 'Tenancy home region'), ('oci_multicloud_region', 'OCI multicloud region')):
        v = _set(k.get(field))
        if field == 'oci_home_region' and not v:
            _err(mn, field, f'{label} required - IAM policies can only be written there')
        elif v and not _OCI_REGION_RE.match(v):
            _err(mn, field, f'{label} is not an OCI region name (e.g. us-ashburn-1)')


# ── Exascale ──────────────────────────────────────────────────────────────────
# Limits from Oracle's "Create an Exascale VM Cluster" page for AI Database@Google Cloud.
_XS_ID_RE = re.compile(r'^[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$')
_XS_DISPLAY_RE = re.compile(r'^[A-Za-z_](?!.*--)[A-Za-z0-9_-]{0,254}$')
_XS_CLUSTER_NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9-]{0,10}$')
_XS_VAULT_NAME_RE = re.compile(r'^projects/[^/]+/locations/[^/]+/exascaleDbStorageVaults/[^/]+$')


def _int_or_none(v):
    try:
        return int(float(v)) if v not in (None, '') else None
    except (TypeError, ValueError):
        return 'bad'


def _check_xs_vault(v, mn, _err):
    if not _XS_ID_RE.match(v.get('exascale_db_storage_vault_id') or ''):
        _err(mn, 'exascale_db_storage_vault_id',
             '1-63 lowercase letters, digits or hyphens; starts with a letter, ends with a letter or digit')
    dn = v.get('display_name') or ''
    if dn and not _XS_DISPLAY_RE.match(dn):
        _err(mn, 'display_name', 'Up to 255 letters, digits, _ or -; starts with a letter or _; no "--"')
    size = _int_or_none(v.get('total_size_gbs'))
    if size in (None, 'bad') or not 300 <= size <= 100000:
        _err(mn, 'total_size_gbs', 'Database storage: 300 to 100,000 GB')
    flash = _int_or_none(v.get('additional_flash_cache_percent'))
    if flash is not None and (flash == 'bad' or not 34 <= flash <= 300):
        _err(mn, 'additional_flash_cache_percent', 'Smart flash and memory cache: 34 to 300 percent, or blank')


def _check_xs_cluster(c, mn, nets, vaults, _err):
    if not _XS_ID_RE.match(c.get('exadb_vm_cluster_id') or ''):
        _err(mn, 'exadb_vm_cluster_id',
             '1-63 lowercase letters, digits or hyphens; starts with a letter, ends with a letter or digit')
    dn = c.get('display_name') or ''
    if dn and not _XS_DISPLAY_RE.match(dn):
        _err(mn, 'display_name', 'Up to 255 letters, digits, _ or -; starts with a letter or _; no "--"')
    # It needs the client AND the backup subnet.
    ref = c.get('network_ref')
    if ref not in nets:
        _err(mn, 'network_ref', 'ODB Network reference required')
    elif nets[ref] == 'adbs':
        _err(mn, 'network_ref', 'That ODB Network is ADB-S only and has no backup subnet — set it to "both" or "dedicated"')
    existing = (c.get('existing_vault') or '').strip()
    if c.get('vault_ref') not in vaults:
        if not existing:
            _err(mn, 'vault_ref', 'Pick an Exascale storage vault from this config, or give an existing one')
        elif not _XS_VAULT_NAME_RE.match(existing):
            _err(mn, 'existing_vault', 'Full name: projects/<p>/locations/<region>/exascaleDbStorageVaults/<id>')
    grid = (c.get('grid_image_id') or '').strip()
    if not grid or _PLACEHOLDER in grid:
        _err(mn, 'grid_image_id', 'Required — the Grid Infrastructure image OCID from the OCI Console (no API publishes it)')
    elif not grid.startswith('ocid1.dbpatch.'):
        _err(mn, 'grid_image_id', 'Must be a Grid Infrastructure image OCID, starting ocid1.dbpatch.')
    shape = c.get('shape_attribute') or 'SMART_STORAGE'
    if shape not in ('SMART_STORAGE', 'BLOCK_STORAGE'):
        _err(mn, 'shape_attribute', 'SMART_STORAGE (26ai and later) or BLOCK_STORAGE (19c)')
    nodes = _int_or_none(c.get('node_count'))
    if nodes in (None, 'bad') or not 1 <= nodes <= 10:
        _err(mn, 'node_count', '1 to 10 VMs')
    ecpu = _int_or_none(c.get('enabled_ecpu_count_per_node'))
    if ecpu in (None, 'bad') or not 8 <= ecpu <= 200 or ecpu % 4:
        _err(mn, 'enabled_ecpu_count_per_node', '8 to 200 ECPUs per VM, in steps of 4')
    extra = _int_or_none(c.get('additional_ecpu_count_per_node'))
    if extra is not None and (extra == 'bad' or not 0 <= extra <= 192 or extra % 4):
        _err(mn, 'additional_ecpu_count_per_node', '0 to 192 reserved ECPUs per VM, in steps of 4, or blank')
    fs = _int_or_none(c.get('vm_file_system_size_gbs_per_node'))
    low = 220 if shape == 'SMART_STORAGE' else 260
    if fs is not None and (fs == 'bad' or not low <= fs <= 1100):
        _err(mn, 'vm_file_system_size_gbs_per_node',
             f'{low} to 1100 GB per VM for {"smart" if low == 220 else "block"} storage')
    cn = c.get('cluster_name') or ''
    if cn and not _XS_CLUSTER_NAME_RE.match(cn):
        _err(mn, 'cluster_name', '1-11 letters, digits or hyphens; starts with a letter')
    if not c.get('hostname_prefix'):
        _err(mn, 'hostname_prefix', 'Required')
    if not c.get('ssh_public_keys'):
        _err(mn, 'ssh_public_keys', 'At least one SSH key required')
    if c.get('license_model') and c['license_model'] not in ('LICENSE_INCLUDED', 'BRING_YOUR_OWN_LICENSE'):
        _err(mn, 'license_model', 'LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE')
