"""Oracle AI Database@Azure payload validation.

Rules for the form payload the browser POSTs to /api/validate - required fields,
value ranges, CIDR sanity. Distinct from schema.py, which describes the Terraform
provider's own resource schema and is used by tf_validator.

Owned entirely by this cloud: nothing here is imported by another cloud package,
so a rule change cannot affect AWS or GCP.
"""
import ipaddress
import re


def validate(data, errors):
    """Populate `errors` as {{module_name: {{field: message}}}}. Returns nothing."""
    return _validate_azure(data, errors)


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


def _validate_azure(data, errors):
    def _err(mn, f, m): errors.setdefault(mn, {})[f] = m
    tab = data.get('tab', 0)

    if tab == 20:  # Azure VNet + Subnet
        for vnet in data.get('azure_vnets', []):
            mn = vnet.get('module_name', 'azure_vnet')
            if not vnet.get('resource_group_name'): _err(mn, 'resource_group_name', 'Required')
            if not vnet.get('location'):             _err(mn, 'location',            'Required')
            if not vnet.get('vnet_name'):            _err(mn, 'vnet_name',           'Required')
            if not re.match(r'^\d+\.\d+\.\d+\.\d+/\d+$', vnet.get('address_space', '')):
                _err(mn, 'address_space', 'Valid CIDR required')
            if not re.match(r'^\d+\.\d+\.\d+\.\d+/\d+$', vnet.get('subnet_address_prefix', '')):
                _err(mn, 'subnet_address_prefix', 'Valid CIDR required')

    elif tab == 21:  # Azure Exadata Infrastructure
        for inf in data.get('azure_infras', []):
            mn = inf.get('module_name', 'azure_exainfra')
            if not inf.get('resource_group_name'): _err(mn, 'resource_group_name', 'Required')
            if not inf.get('location'):             _err(mn, 'location',            'Required')
            if not inf.get('name'):                 _err(mn, 'name',                'Required')
            if not inf.get('display_name'):         _err(mn, 'display_name',        'Required')
            if not inf.get('shape'):                _err(mn, 'shape',               'Required')
            if int(inf.get('compute_count', 0) or 0) < 2: _err(mn, 'compute_count', 'Minimum 2')
            if int(inf.get('storage_count', 0) or 0) < 3: _err(mn, 'storage_count', 'Minimum 3')
            _require_server_types('azure', inf, mn, _err)

    elif tab == 23:  # Azure Autonomous Database (Serverless)
        for adb in data.get('azure_autonomous_dbs', []):
            mn = adb.get('module_name', 'azure_adbs')
            if not adb.get('resource_group_name'): _err(mn, 'resource_group_name', 'Required')
            if not adb.get('location'):            _err(mn, 'location',            'Required')
            if not adb.get('name'):                _err(mn, 'name',                'Required')
            if not adb.get('display_name'):        _err(mn, 'display_name',        'Required')
            if float(adb.get('compute_count', 0) or 0) < 1:
                _err(mn, 'compute_count', 'Required, minimum 1 (2 for ECPU)')
            if int(adb.get('data_storage_size_in_tbs', 0) or 0) < 1:
                _err(mn, 'data_storage_size_in_tbs', 'Required, minimum 1 TB')
            days = int(adb.get('backup_retention_period_in_days', 0) or 0)
            if not 1 <= days <= 60:
                _err(mn, 'backup_retention_period_in_days', 'Must be between 1 and 60')
            if adb.get('db_workload') not in ('OLTP', 'DW', 'AJD', 'APEX'):
                _err(mn, 'db_workload', 'Must be OLTP, DW, AJD or APEX')

    elif tab == 22:  # Azure VM Cluster
        clusters = data.get('azure_clusters', [])
        # Delegated subnet is shared by design — several VM clusters attach to the
        # same one. The backup range is not: Oracle carves it inside the VNet per
        # cluster, so two clusters on one delegated subnet must not collide.
        vnets_by_name = {v.get('module_name'): v for v in data.get('azure_vnets', [])}
        sharing = {}
        for cl in clusters:
            sharing.setdefault(cl.get('vnet_ref'), []).append(cl)
        # Backup ranges are carved inside the VNet, so they can only collide
        # with other clusters on that same VNet.
        claimed = {}   # vnet_ref -> [(module_name, ip_network)] accepted so far

        for cl in clusters:
            mn = cl.get('module_name', 'azure_vmcluster')
            if not cl.get('resource_group_name'): _err(mn, 'resource_group_name', 'Required')
            if not cl.get('location'):             _err(mn, 'location',            'Required')
            if not cl.get('name'):                 _err(mn, 'name',                'Required')
            if not cl.get('display_name'):         _err(mn, 'display_name',        'Required')
            if not cl.get('hostname'):             _err(mn, 'hostname',            'Required')
            if not cl.get('gi_version'):           _err(mn, 'gi_version',          'Required')
            if int(cl.get('cpu_core_count', 0) or 0) < 2:
                _err(mn, 'cpu_core_count', 'Minimum 2')
            if float(cl.get('data_storage_size_in_tbs', 0) or 0) < 2:
                _err(mn, 'data_storage_size_in_tbs', 'Minimum 2 TiB')
            if not cl.get('ssh_public_keys'):
                _err(mn, 'ssh_public_keys', 'At least one SSH key required')

            vnet_ref = cl.get('vnet_ref')
            backup   = (cl.get('backup_subnet_cidr') or '').strip()
            if not backup:
                # Only enforced when the delegated subnet is shared — a lone
                # cluster can let Oracle pick the default backup range.
                if len(sharing.get(vnet_ref, [])) > 1:
                    _err(mn, 'backup_subnet_cidr',
                         'Required when clusters share a delegated subnet - each needs its own range')
                continue
            if not re.match(r'^\d+\.\d+\.\d+\.\d+/\d+$', backup):
                _err(mn, 'backup_subnet_cidr', 'Valid CIDR required')
                continue
            try:
                backup_net = ipaddress.ip_network(backup, strict=False)
            except ValueError:
                _err(mn, 'backup_subnet_cidr', 'Valid CIDR required')
                continue
            delegated = (vnets_by_name.get(vnet_ref) or {}).get('subnet_address_prefix', '')
            if delegated:
                try:
                    if backup_net.overlaps(ipaddress.ip_network(delegated, strict=False)):
                        _err(mn, 'backup_subnet_cidr',
                             f'Overlaps the delegated subnet {delegated}')
                        continue
                except ValueError:
                    pass
            peers = claimed.setdefault(vnet_ref, [])
            clash = next((other for other, net in peers if net.overlaps(backup_net)), None)
            if clash:
                _err(mn, 'backup_subnet_cidr', f'Overlaps the backup subnet of {clash}')
                continue
            peers.append((mn, backup_net))

    elif tab == 24:  # Oracle Resource Anchors
        for anc in data.get('azure_resource_anchors', []):
            mn = anc.get('module_name', 'azure_resource_anchor')
            if not (anc.get('name') or '').strip():
                _err(mn, 'name', 'Required')

    elif tab == 25:  # Oracle Network Anchors
        _check_network_anchors(data, _err)


def _cidr(value):
    try:
        return ipaddress.ip_network(value, strict=False) if CIDR_RE.match(value or '') else None
    except ValueError:
        return None


CIDR_RE = re.compile(r'^\d+\.\d+\.\d+\.\d+/\d+$')


def _check_network_anchors(data, _err):
    """A Network Anchor is a network bridge to OCI on a delegated subnet of its own.

    Not tied to one database service, so nothing here looks at clusters or ADBs.
    """
    anchors = {a.get('module_name') for a in data.get('azure_resource_anchors', [])}
    vnets = {v.get('module_name'): v for v in data.get('azure_vnets', [])}
    claimed = {}   # vnet_ref -> [(module_name, ip_network)] accepted so far

    for na in data.get('azure_network_anchors', []):
        mn = na.get('module_name', 'azure_netanchor')
        name = (na.get('name') or '').strip()
        if not name:
            _err(mn, 'name', 'Required')
        elif not re.match(r'^[A-Za-z0-9-]{3,24}$', name):
            _err(mn, 'name', '3-24 characters: letters, digits or hyphens')

        # Resource Anchor: a card in this config, or an existing one by ID.
        if na.get('resource_anchor_ref') not in anchors:
            existing = (na.get('existing_resource_anchor_id') or '').strip()
            if not existing:
                _err(mn, 'resource_anchor_ref',
                     'Pick a Resource Anchor from this config, or give an existing one\'s resource ID')
            elif not re.search(r'(?i)/providers/Oracle\.Database/resourceAnchors/[^/]+$', existing):
                _err(mn, 'existing_resource_anchor_id',
                     'Must be the Azure resource ID of an Oracle.Database/resourceAnchors resource')

        # Its own delegated subnet, inside a VNet from this config or an existing one.
        vnet_ref = na.get('vnet_ref')
        vnet = vnets.get(vnet_ref)
        if not vnet and not (na.get('existing_vnet_name') or '').strip():
            _err(mn, 'vnet_ref', 'Pick a VNet from this config, or give an existing VNet\'s name')
        # Blank is fine - the generator names it <module>-subnet.
        sname = (na.get('subnet_name') or '').strip()
        if sname and not re.match(r'^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,78}[A-Za-z0-9_])?$', sname):
            _err(mn, 'subnet_name', 'Azure subnet name: 1-80 of letters, digits, . _ -; '
                                    'starts with a letter or digit, ends with one or _')
        prefix = (na.get('subnet_address_prefix') or '').strip()
        net = _cidr(prefix)
        if not net:
            _err(mn, 'subnet_address_prefix', 'Valid CIDR required')
        elif vnet:
            space = _cidr(vnet.get('address_space', ''))
            delegated = _cidr(vnet.get('subnet_address_prefix', ''))
            clash = next((other for other, n in claimed.get(vnet_ref, []) if n.overlaps(net)), None)
            if space and not net.subnet_of(space):
                _err(mn, 'subnet_address_prefix', f'Must sit inside the VNet address space {space}')
            elif delegated and net.overlaps(delegated):
                _err(mn, 'subnet_address_prefix',
                     f'Overlaps the VNet\'s own delegated subnet {delegated} - a Network Anchor needs a subnet of its own')
            elif clash:
                _err(mn, 'subnet_address_prefix', f'Overlaps the subnet of {clash}')
            else:
                claimed.setdefault(vnet_ref, []).append((mn, net))

        zone = str(na.get('zone') or '').strip()
        if zone and zone not in ('1', '2', '3'):
            _err(mn, 'zone', 'Must be 1, 2 or 3, or blank')
        label = (na.get('oci_vcn_dns_label') or '').strip()
        if label and not re.match(r'^[A-Za-z][A-Za-z0-9]{0,14}$', label):
            _err(mn, 'oci_vcn_dns_label', 'Starts with a letter; letters and digits only; at most 15')
        backup = (na.get('oci_backup_cidr_block') or '').strip()
        if backup and not _cidr(backup):
            _err(mn, 'oci_backup_cidr_block', 'Valid CIDR required')

        # DNS: Oracle's portal treats zone sync and the listening endpoint as
        # overlapping ways to the same end - pick one.
        if na.get('dns_zone_sync_enabled') and na.get('dns_listening_endpoint_enabled'):
            _err(mn, 'dns_listening_endpoint_enabled',
                 'Overlaps DNS zone replication - Oracle asks for one or the other')
        cidrs = na.get('dns_listening_allowed_cidrs') or []
        cidrs = cidrs if isinstance(cidrs, list) else [c.strip() for c in cidrs.split(',') if c.strip()]
        if cidrs and not na.get('dns_listening_endpoint_enabled'):
            _err(mn, 'dns_listening_allowed_cidrs', 'Only used with the DNS listening endpoint')
        bad = [c for c in cidrs if not _cidr(c)]
        if bad:
            _err(mn, 'dns_listening_allowed_cidrs', f'Not a CIDR: {", ".join(bad)}')
        rules = [r for r in (na.get('dns_forwarding_rules') or [])
                 if (r.get('domain_names') or r.get('forwarding_ip_address'))]
        if rules and not na.get('dns_forwarding_endpoint_enabled'):
            _err(mn, 'dns_forwarding_rules', 'Only used with the DNS forwarding endpoint')
        for r in rules:
            domains = r.get('domain_names') or []
            domains = domains if isinstance(domains, list) else [d for d in domains.split(',') if d.strip()]
            try:
                ipaddress.ip_address((r.get('forwarding_ip_address') or '').strip())
                ip_ok = True
            except ValueError:
                ip_ok = False
            if not domains or not ip_ok:
                _err(mn, 'dns_forwarding_rules', 'Each rule needs domain names and a forwarding IP address')
                break
