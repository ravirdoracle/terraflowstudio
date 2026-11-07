"""Oracle AI Database@AWS payload validation.

Rules for the form payload the browser POSTs to /api/validate - required fields,
value ranges, CIDR sanity. Distinct from schema.py, which describes the Terraform
provider's own resource schema and is used by tf_validator.

Owned entirely by this cloud: nothing here is imported by another cloud package,
so a rule change cannot affect GCP or Azure.
"""
import json
import re

import regions

#: Endpoint policy -> the access flag that has to be on for it to do anything.
_POLICY_PAIRS = (
    ('s3_policy_document', 's3_access', 'S3'),
    ('sts_policy_document', 'sts_access', 'STS'),
    ('kms_policy_document', 'kms_access', 'KMS'),
)

_REGION_RE = re.compile(r'^[a-z]{2}(-[a-z]+)+-\d+$')


def _check_az_region(item, mn, _err):
    """An AZ ID the catalogue files under a different region than the card's.

    Only a contradiction is an error: an AZ the catalogue does not list at all
    is allowed through, because the card offers it as "(custom)" for zones the
    catalogue has not caught up with yet.
    """
    az, region = item.get('availability_zone_id'), item.get('region')
    if not az or not region:
        return
    owner = regions.zone_to_region('aws').get(az)
    if owner and owner != region:
        _err(mn, 'availability_zone_id', f'{az} is in {owner}, not {region}')


def _check_network_service_access(net, mn, _err):
    """sts/kms access flags, endpoint policies and cross-region restore sources.

    sts_access and kms_access are Optional + Computed in the provider, so an
    empty value is meaningful - it leaves the choice to the service - and is not
    an error. What is an error is a value that is neither of the two statuses,
    an endpoint policy that is not valid JSON, or a policy paired with an access
    flag explicitly turned off, where the policy would silently do nothing.
    """
    for field in ('sts_access', 'kms_access'):
        val = (net.get(field) or '').strip()
        if val and val.upper() not in ('ENABLED', 'DISABLED'):
            _err(mn, field, 'Must be ENABLED or DISABLED, or left unset')

    for policy_field, access_field, label in _POLICY_PAIRS:
        doc = (net.get(policy_field) or '').strip()
        if not doc:
            continue
        try:
            parsed = json.loads(doc)
        except ValueError as exc:
            _err(mn, policy_field, f'Must be valid JSON ({exc.args[0]})')
            continue
        if not isinstance(parsed, dict):
            _err(mn, policy_field, 'Must be a JSON object, not a list or scalar')
        # Only an explicit DISABLED is a contradiction. An unset flag may still
        # come up enabled, so the policy is not necessarily inert.
        if (net.get(access_field) or '').strip().upper() == 'DISABLED':
            _err(mn, policy_field,
                 f'{label} access is DISABLED, so this policy would have no effect')

    sources = net.get('cross_region_s3_restore_sources_access') or []
    if isinstance(sources, str):
        sources = [s.strip() for s in re.split(r'[,\s]+', sources) if s.strip()]
    for src in sources:
        if not _REGION_RE.match(str(src).strip()):
            _err(mn, 'cross_region_s3_restore_sources_access',
                 f'"{src}" is not an AWS region name (e.g. us-east-1)')
            break
    if sources and (net.get('s3_access') in (False, 'DISABLED')):
        _err(mn, 'cross_region_s3_restore_sources_access',
             'Cross-region S3 restore needs S3 access enabled')


def validate(data, errors):
    """Populate `errors` as {{module_name: {{field: message}}}}. Returns nothing."""
    return _validate_aws(data, errors)


def _require_server_types(cloud, inf, mn, _err):
    """Both server types are required for shapes the catalogue flags.

    Which shapes those are lives in config/<cloud>_shapes.json, not here — AWS
    documents both as mandatory for Exadata.X11M, and the same Oracle service
    constraint applies on Azure. A catalogue that cannot be read must not take
    validation down with it, so a broken file simply skips the rule.
    """
    try:
        import shapes
        if inf.get('shape') not in shapes.requires_server_types(cloud):
            return
    except Exception:
        return
    if not inf.get('database_server_type'):
        _err(mn, 'database_server_type', f'Required for {inf.get("shape")}')
    if not inf.get('storage_server_type'):
        _err(mn, 'storage_server_type', f'Required for {inf.get("shape")}')


def _validate_aws(data, errors):
    def _err(mn, f, m): errors.setdefault(mn, {})[f] = m
    tab = data.get('tab', 0)

    if tab == 0:   # ODB Networks
        for net in data.get('aws_networks', [data.get('module_0', {})]):
            mn = net.get('module_name', 'odb_network')
            # Externally provisioned: nothing is created, so only the ID matters.
            if net.get('is_existing'):
                if not net.get('existing_id'):
                    _err(mn, 'existing_id', 'Required when already provisioned')
                continue
            if not net.get('display_name'):            _err(mn, 'display_name',        'Required')
            if not net.get('availability_zone_id'):    _err(mn, 'availability_zone_id', 'Required')
            _check_az_region(net, mn, _err)
            if not re.match(r'^\d+\.\d+\.\d+\.\d+/\d+$', net.get('client_subnet_cidr', '')):
                _err(mn, 'client_subnet_cidr', 'Valid CIDR required')
            if not re.match(r'^\d+\.\d+\.\d+\.\d+/\d+$', net.get('backup_subnet_cidr', '')):
                _err(mn, 'backup_subnet_cidr', 'Valid CIDR required')
            _check_network_service_access(net, mn, _err)

    elif tab == 1:  # Exadata Infras
        for inf in data.get('aws_infras', [data.get('module_1', {})]):
            mn = inf.get('module_name', 'odb_exaInfra')
            # Externally provisioned: nothing is created, so only the ID matters.
            if inf.get('is_existing'):
                if not inf.get('existing_id'):
                    _err(mn, 'existing_id', 'Required when already provisioned')
                continue
            if not inf.get('display_name'):             _err(mn, 'display_name',        'Required')
            if not inf.get('shape'):                    _err(mn, 'shape',               'Required')
            if not inf.get('availability_zone_id'):     _err(mn, 'availability_zone_id', 'Required')
            _check_az_region(inf, mn, _err)
            if int(inf.get('compute_count', 0) or 0) < 2: _err(mn, 'compute_count', 'Minimum 2')
            if int(inf.get('storage_count', 0) or 0) < 3: _err(mn, 'storage_count', 'Minimum 3')
            _require_server_types('aws', inf, mn, _err)

    elif tab == 2:  # Peerings
        for peer in data.get('aws_peerings', [data.get('module_2', {})]):
            mn = peer.get('module_name', 'odb_peering')
            if not peer.get('display_name'):    _err(mn, 'display_name',    'Required')
            if not peer.get('peer_network_id'): _err(mn, 'peer_network_id', 'Required')

    elif tab == 3:  # VM Clusters
        for cl in data.get('aws_clusters', [data.get('module_3', {})]):
            mn = cl.get('module_name', 'odb_vmcluster')
            if not cl.get('display_name'):                  _err(mn, 'display_name',    'Required')
            if int(cl.get('cpu_core_count', 0) or 0) < 2:  _err(mn, 'cpu_core_count',  'Minimum 2')
            if not cl.get('gi_version'):                    _err(mn, 'gi_version',       'Required')
            if not cl.get('hostname_prefix'):               _err(mn, 'hostname_prefix',  'Required')
            if not cl.get('ssh_public_keys'):               _err(mn, 'ssh_public_keys',  'At least one SSH key required')
            # Infras can be removed to zero now (Serverless-only configs), so a
            # cluster may have nothing to run on.
            if 'aws_infras' in data and not data.get('aws_infras'):
                _err(mn, 'infra_ref', 'Add an Exadata Infrastructure first — a VM Cluster runs on one')

    elif tab == 4:  # Autonomous VM Clusters
        for av in data.get('aws_avmclusters', []):
            mn = av.get('module_name', 'odb_avmcluster')
            if not av.get('display_name'):                                       _err(mn, 'display_name', 'Required')
            if float(av.get('autonomous_data_storage_size_in_tbs', 0) or 0) <= 0: _err(mn, 'autonomous_data_storage_size_in_tbs', 'Required, must be > 0')
            if int(av.get('cpu_core_count_per_node', 0) or 0) < 1:              _err(mn, 'cpu_core_count_per_node', 'Required, minimum 1')
            if int(av.get('memory_per_oracle_compute_unit_in_gbs', 0) or 0) < 1: _err(mn, 'memory_per_oracle_compute_unit_in_gbs', 'Required, minimum 1')
            if int(av.get('total_container_databases', 0) or 0) < 1:            _err(mn, 'total_container_databases', 'Required, minimum 1')
            if 'aws_infras' in data and not data.get('aws_infras') and not (
                    av.get('cloud_exadata_infrastructure_arn') and av.get('odb_network_arn')):
                _err(mn, 'infra_ref', 'Add an Exadata Infrastructure first, or name one by ARN')

    elif tab == 5:  # Autonomous Databases (Serverless)
        net_names = {n.get('module_name') for n in data.get('aws_networks', [])}
        for adb in data.get('aws_autonomous_dbs', []):
            _check_adb(adb, adb.get('module_name', 'odb_adb'), net_names, _err)

    elif tab == 7:  # AWS RAM resource shares
        nets   = {n.get('module_name'): n for n in data.get('aws_networks', [])}
        infras = {i.get('module_name'): i for i in data.get('aws_infras', [])}
        for share in data.get('aws_ram_shares', []):
            _check_ram_share(share, share.get('module_name', 'odb_ram_share'), nets, infras, _err)

    elif tab == 8:  # TDE master keys in AWS KMS
        keys = data.get('aws_kms_keys') or []
        if keys:
            _check_kms_settings(data.get('aws_kms_tde') or {}, _err)
        nets     = {n.get('module_name'): n for n in data.get('aws_networks', [])}
        clusters = {c.get('module_name'): c for c in data.get('aws_clusters', [])}
        owner = {}
        for key in keys:
            # One field can collect several problems (two bad cluster_refs), and
            # _err keeps only the last message per field, so join them.
            found = {}
            _check_kms_key(key, key.get('module_name', 'tde_key'), clusters, nets, owner,
                           lambda m, f, msg: found.setdefault((m, f), []).append(msg))
            for (m, f), msgs in found.items():
                _err(m, f, '; '.join(msgs))


_DB_NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9]{0,29}$')
_ARN_RE     = re.compile(r'^arn:aws[a-z-]*:[a-z0-9-]+:')
_IPV4_RE    = re.compile(r'^\d{1,3}(\.\d{1,3}){3}(/\d{1,2})?$')


def _num_or_none(v):
    if v in (None, ''):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return 'invalid'


def _check_adb(adb, mn, net_names, _err):
    """aws_odb_autonomous_database — the ranges below are the provider's own.

    Everything here is Optional in the provider schema because the valid
    combination depends on `source`; this configuration only ever creates new
    databases (source = NONE), which is what makes display_name, db_name and a
    network effectively required.
    """
    if not adb.get('display_name'):
        _err(mn, 'display_name', 'Required')
    db_name = (adb.get('db_name') or '').strip()
    if db_name and not _DB_NAME_RE.match(db_name):
        _err(mn, 'db_name', 'Must start with a letter, alphanumeric only, max 30 characters')
    if not net_names:
        _err(mn, 'network_ref', 'Add an ODB Network first — a Serverless ADB attaches to one')
    elif adb.get('network_ref') and adb['network_ref'] not in net_names:
        _err(mn, 'network_ref', f'No ODB Network named "{adb["network_ref"]}" in this configuration')

    if adb.get('db_workload') and adb['db_workload'] not in ('OLTP', 'LH', 'AJD', 'APEX'):
        _err(mn, 'db_workload', 'Must be OLTP, LH, AJD or APEX')

    cc = _num_or_none(adb.get('compute_count'))
    if cc == 'invalid' or (cc is not None and not 0.1 <= cc <= 512):
        _err(mn, 'compute_count', 'ECPUs must be between 0.1 and 512')
    ts = _num_or_none(adb.get('data_storage_size_in_tbs'))
    # ValidateConfig in the provider rejects a fractional TB size outright.
    if ts == 'invalid' or (ts is not None and (ts != int(ts) or not 1 <= ts <= 384)):
        _err(mn, 'data_storage_size_in_tbs', 'A whole number of TB, 1-384')
    br = _num_or_none(adb.get('backup_retention_period_in_days'))
    if br == 'invalid' or (br is not None and (br != int(br) or br < 1)):
        _err(mn, 'backup_retention_period_in_days', 'A whole number of days, at least 1')

    if adb.get('database_edition') and adb.get('license_model') != 'BRING_YOUR_OWN_LICENSE':
        _err(mn, 'database_edition', 'Only applies to BRING_YOUR_OWN_LICENSE')

    ips = adb.get('allowlisted_ips') or []
    if isinstance(ips, str):
        ips = [s.strip() for s in re.split(r'[,\s]+', ips) if s.strip()]
    bad = next((ip for ip in ips if not _IPV4_RE.match(str(ip).strip())), None)
    if bad:
        _err(mn, 'allowlisted_ips', f'"{bad}" is not an IPv4 address or CIDR')
    elif len(ips) > 1024:
        _err(mn, 'allowlisted_ips', 'At most 1024 entries')

    kms = (adb.get('kms_key_id') or '').strip()
    if adb.get('encryption_key_provider') == 'AWS_KMS' and not kms:
        _err(mn, 'kms_key_id', 'Required when encryption_key_provider is AWS_KMS')
    elif kms and adb.get('encryption_key_provider') != 'AWS_KMS':
        _err(mn, 'kms_key_id', 'Only used when encryption_key_provider is AWS_KMS')

    source = adb.get('admin_password_source') or 'write_only'
    if source not in ('write_only', 'secrets_manager'):
        _err(mn, 'admin_password_source', 'Must be write_only or secrets_manager')
    elif source == 'secrets_manager':
        for field in ('secret_arn', 'secret_iam_role_arn'):
            val = (adb.get(field) or '').strip()
            if not val:
                _err(mn, field, 'Required for a Secrets Manager password')
            elif not _ARN_RE.match(val):
                _err(mn, field, 'Must be an ARN')
        if adb.get('secret_external_id_type') and adb['secret_external_id_type'] not in (
                'database_ocid', 'compartment_ocid', 'tenant_ocid'):
            _err(mn, 'secret_external_id_type', 'Must be database_ocid, compartment_ocid or tenant_ocid')
    # A password value never travels in the payload — reject one that does
    # rather than let it be saved under data/ with the rest of the config.
    for field in ('admin_password', 'admin_password_wo'):
        if adb.get(field):
            _err(mn, field, 'Never stored in the config — supply it as TF_VAR_aws_adb_admin_passwords at apply time')


_ACCOUNT_ID_RE = re.compile(r'^\d{12}$')
_ODB_ARN_RE    = re.compile(r'^arn:aws[a-z-]*:odb:[a-z0-9-]+:\d{12}:(odb-network|cloud-exadata-infrastructure)/.+$')


def _as_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x for x in re.split(r'[\s,]+', v or '') if x]


_OIDC_ARN_RE = re.compile(r'^arn:aws[a-z-]*:iam::\d{12}:oidc-provider/[^/\s]+$')
_OIDC_URL_RE = re.compile(r'^https://[A-Za-z0-9.-]+$')
_KMS_ARN_RE  = re.compile(r'^arn:aws[a-z-]*:kms:[a-z0-9-]+:\d{12}:key/[A-Za-z0-9-]+$')
_OCI_COMPARTMENT_RE = re.compile(r'^ocid1\.(compartment|tenancy)\.')

#: Error key for the page-level TDE settings, which belong to no card.
KMS_SETTINGS = 'aws_kms_tde'


def _check_kms_settings(kms, _err):
    """The OIDC provider the cluster roles trust, and the token audience.

    Reuse names the account's provider by ARN; create needs the identity domain
    URL exactly as the token's issuer — https, no path, no trailing slash — and
    the audience, which a new provider has no other way to learn.
    """
    mode = kms.get('oidc_mode') or 'existing'
    audience = (kms.get('oidc_audience') or '').strip()
    if mode == 'create':
        url = (kms.get('oidc_provider_url') or '').strip().rstrip('/')
        if not _OIDC_URL_RE.match(url):
            _err(KMS_SETTINGS, 'oidc_provider_url',
                 'The OCI identity domain URL, e.g. https://idcs-<id>.identity.oraclecloud.com')
        if not audience:
            _err(KMS_SETTINGS, 'oidc_audience', 'Required to create the provider — copy it from Oracle\'s CloudFormation template')
    elif not _OIDC_ARN_RE.match((kms.get('oidc_provider_arn') or '').strip()):
        _err(KMS_SETTINGS, 'oidc_provider_arn',
             'The IAM OIDC provider ARN, arn:aws:iam::<account>:oidc-provider/<identity domain host>')
    if '*' in audience:
        _err(KMS_SETTINGS, 'oidc_audience', 'An exact value — wildcards are not allowed')
    comp = (kms.get('oci_policy_compartment_id') or '').strip()
    if comp and not _OCI_COMPARTMENT_RE.match(comp):
        _err(KMS_SETTINGS, 'oci_policy_compartment_id', 'A compartment or tenancy OCID')


def _check_kms_key(key, mn, clusters, nets, owner, _err):
    """One TDE key and the clusters it serves.

    A cluster takes one key, so a second claim is an error rather than a silent
    last-wins. A cluster's ODB Network has to reach STS and KMS — the role is
    assumed through the one and the key unwrapped through the other, on every
    database startup — so a managed network with either not ENABLED is caught
    here; an externally provisioned one cannot be checked.
    """
    refs = _as_list(key.get('cluster_refs'))
    if not refs:
        _err(mn, 'cluster_refs', 'Pick at least one VM cluster — the key is registered in OCI through it')
    for r in refs:
        cl = clusters.get(r)
        if cl is None:
            _err(mn, 'cluster_refs', f'No VM cluster named "{r}" in this configuration')
            continue
        if r in owner:
            _err(mn, 'cluster_refs', f'"{r}" already takes key "{owner[r]}" — a cluster takes one TDE key')
        owner.setdefault(r, mn)
        net = nets.get(cl.get('network_ref'))
        if net and not net.get('is_existing'):
            off = [f for f in ('sts_access', 'kms_access')
                   if (net.get(f) or '').strip().upper() != 'ENABLED']
            if off:
                _err(mn, 'cluster_refs', f'"{r}" is on ODB Network "{net.get("module_name")}", '
                                         f'which needs {" and ".join(off)} = ENABLED')
    via = (key.get('register_via') or '').strip()
    if via and via not in refs:
        _err(mn, 'register_via', 'Must be one of this key\'s clusters')

    arn = (key.get('existing_arn') or '').strip()
    if arn:
        if not _KMS_ARN_RE.match(arn):
            _err(mn, 'existing_arn', 'A KMS key ARN, arn:aws:kms:<region>:<account>:key/<id> — not an alias')
    else:
        alias = (key.get('alias') or '').strip()
        if alias and (not alias.startswith('alias/') or alias.startswith('alias/aws/')):
            _err(mn, 'alias', 'Starts with alias/ — and alias/aws/ is reserved for AWS managed keys')
        window = _num_or_none(key.get('deletion_window_in_days'))
        if window == 'invalid' or (window is not None and not 7 <= window <= 30):
            _err(mn, 'deletion_window_in_days', 'Between 7 and 30')
    comp = (key.get('oci_compartment_id') or '').strip()
    if comp and not _OCI_COMPARTMENT_RE.match(comp):
        _err(mn, 'oci_compartment_id', 'A compartment OCID')


def _check_ram_share(share, mn, nets, infras, _err):
    """aws_ram_resource_share over this configuration's networks / infras.

    An externally provisioned network or infra can be shared only by ARN — the
    share has nothing else to resolve it through.
    """
    principals = _as_list(share.get('principals'))
    if not principals:
        _err(mn, 'principals', 'Share with at least one AWS account')
    bad = next((p for p in principals if not _ACCOUNT_ID_RE.match(p)), None)
    if bad:
        _err(mn, 'principals', f'"{bad}" is not a 12-digit AWS account ID')

    net_refs, infra_refs = _as_list(share.get('network_refs')), _as_list(share.get('infra_refs'))
    arns = _as_list(share.get('resource_arns'))
    if not (net_refs or infra_refs or arns):
        _err(mn, 'network_refs', 'Pick at least one ODB Network or Exadata Infrastructure to share')
    for field, refs, pool, label in (('network_refs', net_refs, nets, 'ODB Network'),
                                     ('infra_refs', infra_refs, infras, 'Exadata Infrastructure')):
        for r in refs:
            item = pool.get(r)
            if item is None:
                _err(mn, field, f'No {label} named "{r}" in this configuration')
            elif item.get('is_existing') and not (item.get('existing_arn') or '').strip():
                _err(mn, field, f'"{r}" is provisioned outside Terraform — give its ARN on its card to share it')
    badarn = next((a for a in arns if not _ODB_ARN_RE.match(a)), None)
    if badarn:
        _err(mn, 'resource_arns', f'"{badarn}" is not an ODB Network or Exadata Infrastructure ARN')
    if share.get('allow_external_principals'):
        _err(mn, 'allow_external_principals',
             'Oracle AI Database@AWS sharing is within the AWS Organization only — leave this off')
