"""AWS contribution to the /api/test self-check run.

Everything /api/test needs to know about AWS lives here: how to read the payload,
what makes the inputs valid, which module directories the generator produces, and
what the root module should contain. app.py drives the run and knows none of it.
"""
import re

from clouds.aws.generator import (
    _aws_net_defaults, _aws_infra_defaults, _aws_peer_defaults, _aws_cluster_defaults,
    _aws_avmc_defaults, _aws_adb_defaults, _MOD4, _MOD4_ARN, _MOD5, _MOD6, _MOD7,
    _MOD8, _MOD8_ACCESS, _MOD8_OCI,
)
from oci import _avmc_filled

CIDR_RE = re.compile(r'^\d+\.\d+\.\d+\.\d+/\d+$')

#: Payload keys the generator reads, used to rebuild a single-cloud payload.
#: Keys are the names derive() returns, values the payload keys the generator
#: reads. They must line up - a mismatch silently generates from empty input.
PAYLOAD_KEYS = {
    'nets': 'aws_networks', 'infras': 'aws_infras',
    'peerings': 'aws_peerings', 'clusters': 'aws_clusters',
    'avmcs': 'aws_avmclusters', 'adbs': 'aws_autonomous_dbs', 'ram_shares': 'aws_ram_shares',
    'kms_keys': 'aws_kms_keys',
}

#: Shared for_each module directories the root emits, one set regardless of how
#: many instances are configured.
MODULE_DIRS = ('aws-odb-network', 'aws-exadata-infra', 'aws-peering', 'aws-vm-cluster')


def derive(payload):
    """Raw and defaulted resource lists from the posted payload."""
    raw_nets     = payload.get('aws_networks') or []
    raw_infras   = payload.get('aws_infras') or []
    raw_peerings = payload.get('aws_peerings') or []
    raw_clusters = payload.get('aws_clusters') or []

    # Configs saved before the UI supported multiple instances stored one
    # resource per module_N key. Still loadable.
    if not raw_nets and payload.get('module_0'):
        mn = payload.get('module_names', {})
        raw_nets     = [{**payload['module_0'],       'module_name': mn.get('0', 'odb_network')}]
        raw_infras   = [{**payload.get('module_1', {}), 'module_name': mn.get('1', 'odb_exaInfra')}]
        raw_peerings = [{**payload.get('module_2', {}), 'module_name': mn.get('2', 'odb_peering')}]
        raw_clusters = [{**payload.get('module_3', {}), 'module_name': mn.get('3', 'odb_vmcluster')}]

    # Same filter the generator applies - a card with no display_name generates
    # nothing, so checking for its tfvars entry would fail on an empty form.
    raw_avmcs = [a for a in (payload.get('aws_avmclusters') or []) if _avmc_filled(a)]

    nets   = [_aws_net_defaults(n) for n in raw_nets]
    infras = [_aws_infra_defaults(i) for i in raw_infras]
    first_net = nets[0]['module_name'] if nets else 'odb_network'
    first_inf = infras[0]['module_name'] if infras else 'odb_exaInfra'
    return {
        'raw_nets': raw_nets, 'raw_infras': raw_infras,
        'raw_peerings': raw_peerings, 'raw_clusters': raw_clusters,
        'nets': nets, 'infras': infras,
        'peerings': [_aws_peer_defaults(p, first_net) for p in raw_peerings],
        'clusters': [_aws_cluster_defaults(c, first_net, first_inf) for c in raw_clusters],
        'avmcs': [_aws_avmc_defaults(a, first_net, first_inf) for a in raw_avmcs],
        'adbs': [_aws_adb_defaults(a, first_net) for a in (payload.get('aws_autonomous_dbs') or [])],
        'adb_integration': bool(payload.get('aws_adb_secrets_integration')),
        'ram_shares': list(payload.get('aws_ram_shares') or []),
        'kms_keys': list(payload.get('aws_kms_keys') or []),
    }


def check_inputs(d, t):
    """Group 1: the posted values are usable before anything is generated."""
    for net in d['raw_nets']:
        mn = net.get('module_name', '?')
        t.check(f'Network "{mn}": display_name present',
                lambda n=net: bool(n.get('display_name')), 'display_name missing')
        t.check(f'Network "{mn}": availability_zone_id present',
                lambda n=net: bool(n.get('availability_zone_id')),
                'availability_zone_id missing')
        for field in ('client_subnet_cidr', 'backup_subnet_cidr'):
            t.check(f'Network "{mn}": {field} valid CIDR',
                    lambda n=net, f=field: bool(CIDR_RE.match(n.get(f, ''))),
                    lambda n=net, f=field: f'Invalid CIDR: {n.get(f)}')
    for inf in d['raw_infras']:
        mn = inf.get('module_name', '?')
        t.check(f'Infra "{mn}": compute_count >= 2',
                lambda i=inf: int(i.get('compute_count', 0) or 0) >= 2,
                lambda i=inf: f'compute_count={i.get("compute_count")} < 2')
        t.check(f'Infra "{mn}": storage_count >= 3',
                lambda i=inf: int(i.get('storage_count', 0) or 0) >= 3,
                lambda i=inf: f'storage_count={i.get("storage_count")} < 3')
    for cl in d['raw_clusters']:
        mn = cl.get('module_name', '?')
        t.check(f'Cluster "{mn}": ssh_public_keys not empty',
                lambda c=cl: bool(c.get('ssh_public_keys')), 'No SSH keys')
        t.check(f'Cluster "{mn}": gi_version present',
                lambda c=cl: bool(c.get('gi_version')), 'gi_version missing')
        t.check(f'Cluster "{mn}": hostname_prefix present',
                lambda c=cl: bool(c.get('hostname_prefix')), 'hostname_prefix missing')


def module_keys(d):
    """Generated file paths that must exist, given these inputs."""
    mods = list(MODULE_DIRS)
    # The AVMC directories are emitted only when something uses them, and the
    # arn pair gets its own because the provider takes one pair or the other.
    if any(not a['use_arn_pair'] for a in d.get('avmcs', [])):
        mods.append(_MOD4)
    if any(a['use_arn_pair'] for a in d.get('avmcs', [])):
        mods.append(_MOD4_ARN)
    if d.get('adbs'):
        mods.append(_MOD5)
    if d.get('adb_integration'):
        mods.append(_MOD6)
    if d.get('ram_shares'):
        mods.append(_MOD7)
    if d.get('kms_keys'):
        mods += [_MOD8, _MOD8_ACCESS, _MOD8_OCI]
    return [f'modules/{mod}/{f}'
            for mod in mods
            for f in ('main.tf', 'variables.tf', 'outputs.tf')]


def check_content(d, files, t):
    """Group 3: the generated root wires the modules together correctly."""
    root = files.get('main.tf', '')
    tfvars = files.get('terraform.auto.tfvars', '')

    t.check('root main.tf contains AWS provider',
            lambda: 'hashicorp/aws' in root, 'hashicorp/aws missing')
    t.check('root main.tf uses for_each on aws_networks',
            lambda: 'for_each = var.aws_networks' in root,
            'for_each on aws_networks missing')
    t.check('root main.tf uses for_each on aws_clusters',
            lambda: 'for_each = var.aws_clusters' in root,
            'for_each on aws_clusters missing')
    if any(not a['use_arn_pair'] for a in d.get('avmcs', [])):
        t.check('root main.tf uses for_each on aws_avmclusters',
                lambda: 'for_each = var.aws_avmclusters' in root,
                'for_each on aws_avmclusters missing')
    t.check('root main.tf wires infra_id to vm clusters',
            lambda: 'module.aws_exadata_infra' in root and 'infra_id' in root,
            'module.aws_exadata_infra infra_id missing')

    # Instances live in tfvars now, so that is where each one has to appear.
    for n in d['nets']:
        mn = n['module_name']
        t.check(f'network "{mn}" entry in tfvars',
                lambda m=mn: f'"{m}"' in tfvars, f'"{mn}" not in tfvars')
    for cl in d['clusters']:
        mn = cl['module_name']
        ir, nr = cl.get('infra_ref', ''), cl.get('network_ref', '')
        t.check(f'cluster "{mn}" entry in tfvars',
                lambda m=mn: f'"{m}"' in tfvars, f'"{mn}" not in tfvars')
        if ir:
            t.check(f'Cluster "{mn}" wired to infra "{ir}"',
                    lambda i=ir: f'"{i}"' in tfvars,
                    f'infra_ref "{ir}" missing in tfvars')
        if nr:
            t.check(f'Cluster "{mn}" wired to network "{nr}"',
                    lambda n2=nr: f'"{n2}"' in tfvars,
                    f'network_ref "{nr}" missing in tfvars')
    for av in d.get('avmcs', []):
        mn = av['module_name']
        t.check(f'AVM cluster "{mn}" entry in tfvars',
                lambda m=mn: f'"{m}"' in tfvars, f'"{mn}" not in tfvars')
    if d.get('adbs'):
        t.check('root main.tf uses for_each on aws_autonomous_dbs',
                lambda: 'for_each = var.aws_autonomous_dbs' in root,
                'for_each on aws_autonomous_dbs missing')
        t.check('ADB admin password is ephemeral',
                lambda: 'ephemeral   = true' in files.get('variables.tf', ''),
                'aws_adb_admin_passwords is not declared ephemeral')
    if d.get('ram_shares'):
        t.check('root main.tf uses for_each on aws_ram_shares',
                lambda: 'for_each = var.aws_ram_shares' in root,
                'for_each on aws_ram_shares missing')
    if d.get('kms_keys'):
        t.check('root main.tf gives each TDE cluster its own role',
                lambda: 'for_each = local.kms_cluster_keys' in root,
                'aws_kms_cluster_access is not keyed by cluster')
        t.check('root main.tf declares the oracle/oci provider for key registration',
                lambda: 'oracle/oci' in root, 'oracle/oci missing with TDE keys')
    for a in d.get('adbs', []):
        mn = a['module_name']
        t.check(f'Autonomous DB "{mn}" entry in tfvars',
                lambda m=mn: f'"{m}"' in tfvars, f'"{mn}" not in tfvars')


# ── Security review ───────────────────────────────────────────────────────────

def collect_cidrs(data):
    """(label, cidr) for every CIDR the payload carries.

    Feeds the deterministic overlap check that /api/ai/security-review merges
    into the model's findings, so overlaps are detected rather than guessed at.
    """
    entries = []
    for i, net in enumerate(data.get('aws_networks', [])):
        name = net.get('module_name') or net.get('display_name') or f'aws_net[{i}]'
        for field in ('client_subnet_cidr', 'backup_subnet_cidr'):
            v = (net.get(field) or '').strip()
            if v:
                entries.append((f'{name}.{field}', v))
    for i, peer in enumerate(data.get('aws_peerings', [])):
        pname = peer.get('module_name') or peer.get('display_name') or f'peering[{i}]'
        for j, cidr in enumerate(peer.get('peer_network_cidrs', [])):
            if cidr and cidr.strip():
                entries.append((f'{pname}.peer_cidrs[{j}]', cidr.strip()))
    return entries


#: Cloud-specific line in the security-review prompt.
SECURITY_PROMPT_LINE = (
    "- delete_associated_resources enabled on ODB networks"
    " (AWS: setting this true deletes VPCs/subnets on network destroy - risky for prod)\n"
    "- Autonomous Databases (aws_autonomous_dbs) with is_mtls_connection_required false,"
    " or allowlisted_ips containing 0.0.0.0/0 or other very broad ranges\n"
)
