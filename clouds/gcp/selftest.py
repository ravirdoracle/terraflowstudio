"""GCP contribution to the /api/test self-check run."""
from clouds.gcp.generator import (
    _gcp_net_defaults, _gcp_infra_defaults, _gcp_cluster_defaults,
    _gcp_adb_defaults, _split_networks, _wants_dedicated,
    _GCP_MOD_NET, _GCP_MOD_NET_ADBS, _GCP_MOD_INFRA, _GCP_MOD_CLUSTER, _GCP_MOD_ADB,
    _GCP_MOD_XS_VAULT, _GCP_MOD_XS_CLUSTER,
)

#: Keys are the names derive() returns; see clouds/aws/selftest.py.
PAYLOAD_KEYS = {
    'nets': 'gcp_networks', 'infras': 'gcp_infras',
    'clusters': 'gcp_clusters', 'adbs': 'gcp_autonomous_dbs',
}

#: Shared for_each module directories, one set regardless of instance count.
#: Which of these a config actually gets now depends on the ODB Network purpose
#: flag — see module_keys().
MODULE_DIRS = (_GCP_MOD_NET, _GCP_MOD_INFRA, _GCP_MOD_CLUSTER)


def derive(payload):
    raw_nets     = payload.get('gcp_networks') or []
    raw_infras   = payload.get('gcp_infras') or []
    raw_clusters = payload.get('gcp_clusters') or []
    raw_adbs     = payload.get('gcp_autonomous_dbs') or []

    # Pre-multi-instance configs stored one resource per gcp_module_N key, with
    # the two subnets flattened into the network entry.
    if not raw_nets and payload.get('gcp_module_0'):
        mn = payload.get('gcp_module_names', {})
        d0, d1, d2, d3, d4 = (payload.get(f'gcp_module_{k}', {}) for k in range(5))
        raw_nets = [{**d0,
                     'module_name': mn.get('0', 'gcp_network'),
                     'client_subnet_module': mn.get('1', 'gcp_client_subnet'),
                     'backup_subnet_module': mn.get('2', 'gcp_backup_subnet'),
                     'client_subnet_id': d1.get('odb_subnet_id', ''),
                     'client_cidr': d1.get('cidr_range', ''),
                     'backup_subnet_id': d2.get('odb_subnet_id', ''),
                     'backup_cidr': d2.get('cidr_range', '')}]
        raw_infras   = [{**d3, 'module_name': mn.get('3', 'gcp_infra')}]
        raw_clusters = [{**d4, 'module_name': mn.get('4', 'gcp_cluster')}]

    nets   = [_gcp_net_defaults(n) for n in raw_nets]
    infras = [_gcp_infra_defaults(i) for i in raw_infras]
    dedicated_nets, adbs_nets = _split_networks(nets)
    has_xs = bool(payload.get('gcp_exascale_vaults') or payload.get('gcp_exascale_clusters'))
    return {
        'raw_nets': raw_nets, 'raw_infras': raw_infras,
        'raw_peerings': [], 'raw_clusters': raw_clusters,
        'raw_adbs': raw_adbs,
        'dedicated_nets': dedicated_nets, 'adbs_nets': adbs_nets,
        # Same rule as generate_gcp_tf: Exascale without an infra or cluster of
        # its own means no Exadata modules.
        'wants_dedicated': _wants_dedicated(raw_nets, raw_infras, raw_clusters) and not (
            has_xs and not raw_infras and not raw_clusters),
        'has_xs': has_xs,
        'has_std_nets': bool(dedicated_nets) or not nets,
        'nets': nets, 'infras': infras, 'peerings': [],
        'clusters': [_gcp_cluster_defaults(c, nets[0] if nets else None,
                                           infras[0] if infras else None)
                     for c in raw_clusters],
        'adbs': [_gcp_adb_defaults(a, nets[0] if nets else None)
                 for a in raw_adbs],
    }


def check_inputs(d, t):
    for net in d['raw_nets']:
        mn = net.get('module_name', '?')
        t.check(f'Network "{mn}": odb_network_id present',
                lambda n=net: bool(n.get('odb_network_id')), 'odb_network_id missing')
        t.check(f'Network "{mn}": location present',
                lambda n=net: bool(n.get('location')), 'location missing')
    for inf in d['raw_infras']:
        mn = inf.get('module_name', '?')
        t.check(f'Infra "{mn}": cloud_exadata_infrastructure_id present',
                lambda i=inf: bool(i.get('cloud_exadata_infrastructure_id')),
                'infra id missing')
    for cl in d['raw_clusters']:
        mn = cl.get('module_name', '?')
        t.check(f'Cluster "{mn}": ssh_public_keys not empty',
                lambda c=cl: bool(c.get('ssh_public_keys')), 'No SSH keys')
    for adb in d['raw_adbs']:
        mn = adb.get('module_name', '?')
        t.check(f'Autonomous DB "{mn}": autonomous_database_id present',
                lambda a=adb: bool(a.get('autonomous_database_id')),
                'autonomous_database_id missing')
        t.check(f'Autonomous DB "{mn}": database present',
                lambda a=adb: bool(a.get('database')), 'database missing')


def module_keys(d):
    """Module directories this configuration must actually contain.

    The ODB Network purpose flag decides the shape: an ADB-S-only config has no
    Exadata Infrastructure and no VM Cluster under it, and its networks build no
    backup subnet, so it gets gcp-odb-network-adbs instead of gcp-odb-network
    and neither Exadata directory.
    """
    mods = []
    if d.get('has_std_nets', True):
        mods.append(_GCP_MOD_NET)
    if d.get('adbs_nets'):
        mods.append(_GCP_MOD_NET_ADBS)
    if d.get('wants_dedicated', True):
        mods += [_GCP_MOD_INFRA, _GCP_MOD_CLUSTER]
    # Emitted only when something uses it, so a config without an Autonomous
    # Database generates exactly the files it did before ADB support existed.
    if d.get('adbs'):
        mods.append(_GCP_MOD_ADB)
    if d.get('has_xs'):
        mods += [_GCP_MOD_XS_VAULT, _GCP_MOD_XS_CLUSTER]
    return [f'modules/{mod}/{f}'
            for mod in mods
            for f in ('main.tf', 'variables.tf', 'outputs.tf')]


def check_content(d, files, t):
    root = files.get('main.tf', '')
    tfvars = files.get('terraform.auto.tfvars', '')

    t.check('root main.tf contains GCP provider',
            lambda: 'hashicorp/google' in root, 'hashicorp/google missing')
    t.check('root main.tf uses for_each on GCP networks',
            lambda: 'for_each = var.gcp_odb_networks' in root,
            'for_each on gcp_odb_networks missing')
    if d['wants_dedicated']:
        t.check('root main.tf uses for_each on GCP clusters',
                lambda: 'for_each = var.gcp_vm_clusters' in root,
                'for_each on gcp_vm_clusters missing')
    else:
        # No Exadata layer: ADB-S only, or Exascale (which has no infra either).
        t.check('root main.tf omits the Exadata infra and VM cluster modules',
                lambda: 'var.gcp_vm_clusters' not in root and 'var.gcp_exadata_infras' not in root,
                'Exadata infra/VM cluster wiring emitted for a config without them')
    if d.get('has_xs'):
        t.check('root main.tf wires the Exascale VM clusters to a backup subnet',
                lambda: 'module "gcp_exascale_vm_cluster"' in root and 'backup_odb_subnet   = module.gcp_odb_network' in root,
                'Exascale VM cluster module or its backup subnet missing')
    elif not d.get('wants_dedicated', True):
        t.check('ADB-S-only config builds no backup subnet',
                lambda: 'backup_odb_subnet' not in root and 'backup_cidr_range' not in tfvars,
                'a backup subnet reached an ADB-S-only config')
    t.check('root main.tf exposes client_subnet_name',
            lambda: 'client_subnet_name' in root, 'client_subnet_name missing in root')

    for n in d['nets']:
        mn = n['module_name']
        t.check(f'network "{mn}" entry in tfvars',
                lambda m=mn: f'"{m}"' in tfvars, f'"{mn}" not in tfvars')
    for cl in d['clusters']:
        mn = cl['module_name']
        t.check(f'cluster "{mn}" entry in tfvars',
                lambda m=mn: f'"{m}"' in tfvars, f'"{mn}" not in tfvars')

    if d['adbs']:
        t.check('root main.tf uses for_each on GCP autonomous DBs',
                lambda: 'for_each = var.gcp_autonomous_dbs' in root,
                'for_each on gcp_autonomous_dbs missing')
        # odb_network / odb_subnet on this resource arrived in hashicorp/google 7.0.
        t.check('root main.tf requires google >= 7.5.0',
                lambda: '>= 7.5.0' in root, 'provider constraint below 7.5.0')
        # The password map may only ever be named in a comment here — an actual
        # assignment would mean a secret had been written to a generated file.
        t.check('ADB admin passwords not assigned in tfvars',
                lambda: not any(ln.lstrip().startswith('gcp_adb_admin_passwords')
                                for ln in tfvars.splitlines()),
                'gcp_adb_admin_passwords is assigned in terraform.auto.tfvars')
        for adb in d['adbs']:
            mn = adb['module_name']
            t.check(f'autonomous db "{mn}" entry in tfvars',
                    lambda m=mn: f'"{m}"' in tfvars, f'"{mn}" not in tfvars')


# ── Security review ───────────────────────────────────────────────────────────

def collect_cidrs(data):
    """(label, cidr) for every CIDR the payload carries."""
    entries = []
    for i, net in enumerate(data.get('gcp_networks', [])):
        nname = net.get('module_name') or net.get('odb_network_id') or f'gcp_net[{i}]'
        for j, sub in enumerate(net.get('subnets', [])):
            v = (sub.get('cidr_range') or '').strip()
            if v:
                label = f'{nname}.subnet[{j}]({sub.get("purpose", "")}).cidr_range'
                entries.append((label, v))
    return entries


#: Cloud-specific line in the security-review prompt.
SECURITY_PROMPT_LINE = (
    "- deletion_protection disabled on prod-like resources"
    " (GCP: google_oracle_database_* resources support this field)\n"
)
