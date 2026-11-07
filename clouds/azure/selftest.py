"""Azure contribution to the /api/test self-check run.

Unlike AWS and GCP, the Azure root emits one module per instance rather than a
shared for_each module, so the expected file paths depend on the configured
module names and the content checks look for per-instance module blocks.
"""
import re

from clouds.azure.generator import (
    _azure_vnet_defaults, _azure_infra_defaults, _azure_cluster_defaults,
    _azure_adb_defaults, _azure_anchor_defaults, _azure_na_defaults,
)

CIDR_RE = re.compile(r'^\d+\.\d+\.\d+\.\d+/\d+$')

#: Keys are the names derive() returns; see clouds/aws/selftest.py.
PAYLOAD_KEYS = {
    'nets': 'azure_vnets', 'infras': 'azure_infras',
    'clusters': 'azure_clusters', 'adbs': 'azure_autonomous_dbs',
    'resource_anchors': 'azure_resource_anchors', 'network_anchors': 'azure_network_anchors',
}


def derive(payload):
    raw_nets     = payload.get('azure_vnets') or []
    raw_infras   = payload.get('azure_infras') or []
    raw_clusters = payload.get('azure_clusters') or []
    nets   = [_azure_vnet_defaults(n) for n in raw_nets]
    infras = [_azure_infra_defaults(i) for i in raw_infras]
    first_vnet = nets[0]['module_name'] if nets else 'azure_vnet'
    first_inf  = infras[0]['module_name'] if infras else 'azure_exainfra'
    anchors = [_azure_anchor_defaults(a) for a in (payload.get('azure_resource_anchors') or [])]
    return {
        'raw_nets': raw_nets, 'raw_infras': raw_infras,
        'raw_peerings': [], 'raw_clusters': raw_clusters,
        'nets': nets, 'infras': infras, 'peerings': [],
        'clusters': [_azure_cluster_defaults(c, first_vnet, first_inf)
                     for c in raw_clusters],
        'adbs': [_azure_adb_defaults(a, first_vnet)
                 for a in (payload.get('azure_autonomous_dbs') or [])],
        'resource_anchors': anchors,
        'network_anchors': [_azure_na_defaults(n, [a['module_name'] for a in anchors],
                                               [v['module_name'] for v in nets])
                            for n in (payload.get('azure_network_anchors') or [])],
    }


def check_inputs(d, t):
    for net in d['raw_nets']:
        mn = net.get('module_name', '?')
        t.check(f'VNet "{mn}": resource_group_name present',
                lambda n=net: bool(n.get('resource_group_name')),
                'resource_group_name missing')
        for field in ('address_space', 'subnet_address_prefix'):
            t.check(f'VNet "{mn}": {field} valid CIDR',
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
        t.check(f'Cluster "{mn}": hostname present',
                lambda c=cl: bool(c.get('hostname')), 'hostname missing')


def module_keys(d):
    # One module directory per configured instance, so the expected paths follow
    # the module names rather than a fixed list.
    names = [r['module_name'] for r in d['nets'] + d['infras'] + d['clusters'] + d['adbs']
             + d['resource_anchors'] + d['network_anchors']]
    return [f'modules/{mn}/{f}'
            for mn in filter(None, names)
            for f in ('main.tf', 'variables.tf', 'outputs.tf')]


def check_content(d, files, t):
    root = files.get('main.tf', '')
    t.check('root main.tf contains Azure provider',
            lambda: 'hashicorp/azurerm' in root, 'hashicorp/azurerm missing')
    for n in d['nets']:
        mn = n['module_name']
        t.check(f'root main.tf references VNet "{mn}"',
                lambda m=mn: f'module "{m}"' in root, f'module "{mn}" not in root')
    for cl in d['clusters']:
        mn = cl['module_name']
        ir, vr = cl.get('infra_ref', ''), cl.get('vnet_ref', '')
        if ir:
            t.check(f'Cluster "{mn}" wired to infra "{ir}"',
                    lambda i=ir: f'module.{i}.infra_id' in root, 'infra_id ref missing')
        if vr:
            t.check(f'Cluster "{mn}" wired to VNet "{vr}"',
                    lambda v=vr: f'module.{v}.subnet_id' in root, 'subnet_id ref missing')
    for adb in d['adbs']:
        mn = adb['module_name']
        t.check(f'root main.tf references Autonomous DB "{mn}"',
                lambda m=mn: f'module "{m}"' in root, f'module "{mn}" not in root')
        # The password reaches the module through a variable, never a literal.
        t.check(f'Autonomous DB "{mn}": admin_password stays out of the files',
                lambda m=mn: f'var.{m}_admin_password' in root, 'admin_password not wired from a variable')
        vr = adb.get('vnet_ref', '')
        if vr:
            t.check(f'Autonomous DB "{mn}" wired to VNet "{vr}"',
                    lambda v=vr: f'module.{v}.subnet_id' in root, 'subnet_id ref missing')
    if d['network_anchors']:
        t.check('root main.tf requires azure/azapi (Network Anchor)',
                lambda: 'azure/azapi' in root, 'azure/azapi missing from required_providers')
    for na in d['network_anchors']:
        mn = na['module_name']
        mod = files.get(f'modules/{mn}/main.tf', '')
        t.check(f'Network Anchor "{mn}": Oracle.Database/networkAnchors resource',
                lambda m=mod: 'Oracle.Database/networkAnchors@' in m, 'azapi resource type missing')
        t.check(f'Network Anchor "{mn}": its own delegated subnet',
                lambda m=mod: 'Oracle.Database/networkAttachments' in m, 'subnet delegation missing')
        ra = na['resource_anchor_ref']
        t.check(f'Network Anchor "{mn}" wired to a Resource Anchor',
                lambda r=ra, m=mn: (f'module.{r}.resource_anchor_id' if r else f'var.{m}.resource_anchor_id') in root,
                'resource_anchor_id not wired')


# ── Security review ───────────────────────────────────────────────────────────

def collect_cidrs(data):
    """(label, cidr) for the Azure ranges that must not overlap each other.

    Azure previously returned nothing here: the collector branched aws/else, so an
    Azure payload fell into the GCP branch and was searched for gcp_networks it
    does not have. Overlapping Azure ranges passed the security review silently.

    Only mutually-exclusive ranges are offered, because the shared checker
    compares every pair for overlap and cannot express containment:

    - subnet_address_prefix - the delegated subnet, carved from the VNet.
    - backup_subnet_cidr    - carved inside the VNet too, so it must not collide
      with the delegated subnet or with another cluster's backup range. The
      provider only reports such a collision at apply time, and the attribute is
      ForceNew, so catching it here is worth doing.

    address_space is deliberately excluded. Subnets are *supposed* to sit inside
    it, so including it would report a high-severity overlap for every correct
    configuration - noise that would train people to ignore the finding.
    """
    entries = []
    for i, vnet in enumerate(data.get('azure_vnets', [])):
        name = vnet.get('module_name') or vnet.get('vnet_name') or f'azure_vnet[{i}]'
        v = (vnet.get('subnet_address_prefix') or '').strip()
        if v:
            entries.append((f'{name}.subnet_address_prefix', v))
    # A Network Anchor's subnet is its own: it must clear the VM-cluster subnet
    # and every other anchor's.
    for i, na in enumerate(data.get('azure_network_anchors', [])):
        name = na.get('module_name') or f'azure_network_anchor[{i}]'
        v = (na.get('subnet_address_prefix') or '').strip()
        if v:
            entries.append((f'{name}.subnet_address_prefix', v))
    for i, cl in enumerate(data.get('azure_clusters', [])):
        name = cl.get('module_name') or cl.get('name') or f'azure_cluster[{i}]'
        v = (cl.get('backup_subnet_cidr') or '').strip()
        if v:
            entries.append((f'{name}.backup_subnet_cidr', v))
    return entries


#: Cloud-specific line in the security-review prompt. Azure previously received
#: the AWS line, which named a field azurerm does not have.
SECURITY_PROMPT_LINE = (
    "- backup_subnet_cidr overlapping the VNet address space or another cluster's"
    " backup range (Azure: carved inside the VNet, and ForceNew - a collision"
    " surfaces only at apply time)\n"
)
