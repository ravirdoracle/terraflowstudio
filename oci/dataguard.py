"""OCI Data Guard generator — cross-region and multi-AZ networking."""
import datetime
import os

from core.helpers import make_renderer

# This package renders only its own templates. Reaching for another cloud's
# raises TemplateNotFound rather than quietly working.
render_tf = make_renderer(os.path.join(os.path.dirname(__file__), 'templates'))


# ── Defaults ──────────────────────────────────────────────────────────────────

def _dg_maz_defaults(d):
    return {**d,
        'prefix':                 d.get('prefix') or 'dg',
        'oci_region':             d.get('oci_region') or 'us-ashburn-1',
        'compartment_id':         d.get('compartment_id') or '',
        'primary_vcn_id':         d.get('primary_vcn_id') or '',
        'primary_nsg_id':         d.get('primary_nsg_id') or '',
        'primary_client_cidr':    d.get('primary_client_cidr') or '10.10.1.0/24',
        'primary_route_table_id': d.get('primary_route_table_id') or '',
        'standby_vcn_id':         d.get('standby_vcn_id') or '',
        'standby_nsg_id':         d.get('standby_nsg_id') or '',
        'standby_client_cidr':    d.get('standby_client_cidr') or '10.20.1.0/24',
        'standby_route_table_id': d.get('standby_route_table_id') or '',
        'add_ssh':                bool(d.get('add_ssh', False)),
        'manage_route_table':     bool(d.get('manage_route_table', False)),
    }


def _dg_cr_defaults(d):
    return {**d,
        'prefix':                   d.get('prefix') or 'dg',
        'primary_oci_region':       d.get('primary_oci_region') or 'us-ashburn-1',
        'standby_oci_region':       d.get('standby_oci_region') or 'us-portland-1',
        'compartment_id':           d.get('compartment_id') or '',
        'primary_vcn_id':           d.get('primary_vcn_id') or '',
        'primary_nsg_id':           d.get('primary_nsg_id') or '',
        'primary_client_cidr':      d.get('primary_client_cidr') or '10.10.1.0/24',
        'primary_route_table_id':   d.get('primary_route_table_id') or '',
        'primary_hub_cidr':         d.get('primary_hub_cidr') or '10.15.0.0/24',
        'standby_vcn_id':           d.get('standby_vcn_id') or '',
        'standby_nsg_id':           d.get('standby_nsg_id') or '',
        'standby_client_cidr':      d.get('standby_client_cidr') or '10.30.1.0/24',
        'standby_route_table_id':   d.get('standby_route_table_id') or '',
        'standby_hub_cidr':         d.get('standby_hub_cidr') or '10.16.0.0/24',
        'add_ssh':                  bool(d.get('add_ssh', False)),
        'manage_route_table':       bool(d.get('manage_route_table', False)),
        'additional_pairs':         _dg_cr_pairs(d),
    }


_PAIR_FIELDS = ('vcn_id', 'nsg_id', 'client_cidr', 'route_table_id')


def _dg_cr_pairs(d):
    """More primary/standby cluster VCN pairs on the same hub, DRG and RPC.

    The card's own VCNs stay the first pair, at the addresses they always had,
    so a configuration already applied plans no change; these are additive. A
    pair with no name gets one from its position, since the name is the
    for_each key every one of its resources is addressed by.
    """
    pairs = []
    for n, pr in enumerate(d.get('additional_pairs') or []):
        name = (pr.get('name') or '').strip() or f'pair{n + 2}'
        pairs.append({'name': name, **{f'{side}_{f}': (pr.get(f'{side}_{f}') or '').strip()
                                       for side in ('primary', 'standby') for f in _PAIR_FIELDS}})
    return pairs


def _side_pairs(d, side):
    """The region module's view of the pairs: its own CIDR, and its peer's."""
    me, peer = ('primary', 'standby') if side == 'primary' else ('standby', 'primary')
    return [{'name': p['name'], 'local': p[f'{me}_client_cidr'], 'remote': p[f'{peer}_client_cidr']}
            for p in d.get('additional_pairs') or []]


def _hcl(v):
    return '"' + str(v).replace('\\', '\\\\').replace('"', '\\"') + '"'


def _dg_cr_pairs_tfvars(d):
    """`additional_pairs = { ... }`, built here so terraform fmt finds it aligned.

    Every pair carries the same keys, so one column width serves all of them.
    The pair names are not padded: fmt aligns only single-line values.
    Root variables say `dr_`, the card says `standby_`; the mapping is here.
    """
    pairs = d.get('additional_pairs') or []
    if not pairs:
        return ''
    placeholder = {'vcn_id': '<{s}-vcn-ocid>', 'nsg_id': '<{s}-nsg-ocid>',
                   'client_cidr': '', 'route_table_id': '<{s}-default-rt-ocid>'}
    # Route table IDs are only read when Terraform manages the route tables.
    fields = [f for f in _PAIR_FIELDS if f != 'route_table_id' or d.get('manage_route_table')]
    keys = [(f'{tf}_{f}', f'{side}_{f}', tf, f)
            for side, tf in (('primary', 'primary'), ('standby', 'dr')) for f in fields]
    w = max(len(k) for k, *_ in keys)
    lines = ['additional_pairs = {']
    for i, pr in enumerate(pairs):
        if i:
            lines.append('')
        lines.append(f'  {_hcl(pr["name"])} = {{')
        for key, src, tf, f in keys:
            val = pr[src] or placeholder[f].format(s=f'{pr["name"]}-{tf}')
            lines.append(f'    {key.ljust(w)} = {_hcl(val)}')
        if d.get('manage_route_table'):
            lines += ['',
                      "    # Each default route table's rules from before import (terraform state show).",
                      '    # Left out, the table keeps only the Data Guard rule: every other route is removed.',
                      '    # primary_existing_route_rules = [',
                      '    #   { destination = "0.0.0.0/0", network_entity_id = "<nat-gateway-ocid>" },',
                      '    # ]',
                      '    # dr_existing_route_rules = []']
        lines.append('  }')
    lines.append('}')
    return '\n'.join(lines)


# ── DG Multi-AZ ───────────────────────────────────────────────────────────────

def dg_maz_main(mn, d):
    return render_tf('oci_dg_multi_az/main.tf.j2',
        prefix=d.get('prefix', 'dg'),
        add_ssh=d.get('add_ssh', False),
        manage_route_table=d.get('manage_route_table', False),
        primary_route_table_id=d.get('primary_route_table_id', ''),
        standby_route_table_id=d.get('standby_route_table_id', ''),
        primary_client_cidr=d.get('primary_client_cidr', '10.10.1.0/24'),
        standby_client_cidr=d.get('standby_client_cidr', '10.20.1.0/24'),
    )


def dg_maz_vars(mn, d):
    return render_tf('oci_dg_multi_az/variables.tf.j2',
        prefix=d.get('prefix', 'dg'),
        oci_region=d.get('oci_region', ''),
        compartment_id=d.get('compartment_id', ''),
        primary_vcn_id=d.get('primary_vcn_id', ''),
        primary_nsg_id=d.get('primary_nsg_id', ''),
        primary_client_cidr=d.get('primary_client_cidr', '10.10.1.0/24'),
        primary_route_table_id=d.get('primary_route_table_id', ''),
        standby_vcn_id=d.get('standby_vcn_id', ''),
        standby_nsg_id=d.get('standby_nsg_id', ''),
        standby_client_cidr=d.get('standby_client_cidr', '10.20.1.0/24'),
        standby_route_table_id=d.get('standby_route_table_id', ''),
    )


def dg_maz_outputs(mn):
    return render_tf('oci_dg_multi_az/outputs.tf.j2')


def dg_maz_readme(mn, d):
    return render_tf('oci_dg_multi_az/README.md.j2',
        prefix=d.get('prefix', 'dg'),
        customer_name=d.get('customer_name', ''),
        oci_region=d.get('oci_region', ''),
        primary_client_cidr=d.get('primary_client_cidr', '10.10.1.0/24'),
        primary_route_table_id=d.get('primary_route_table_id', ''),
        standby_client_cidr=d.get('standby_client_cidr', '10.20.1.0/24'),
        standby_route_table_id=d.get('standby_route_table_id', ''),
        add_ssh=d.get('add_ssh', False),
        manage_route_table=d.get('manage_route_table', False),
        generated_date=datetime.date.today().isoformat(),
    )


def dg_maz_tfvars(mn, d):
    return render_tf('oci_dg_multi_az/terraform.tfvars.j2',
        prefix=d.get('prefix', 'dg'),
        oci_region=d.get('oci_region', ''),
        compartment_id=d.get('compartment_id', ''),
        primary_vcn_id=d.get('primary_vcn_id', ''),
        primary_nsg_id=d.get('primary_nsg_id', ''),
        primary_client_cidr=d.get('primary_client_cidr', '10.10.1.0/24'),
        primary_route_table_id=d.get('primary_route_table_id', ''),
        standby_vcn_id=d.get('standby_vcn_id', ''),
        standby_nsg_id=d.get('standby_nsg_id', ''),
        standby_client_cidr=d.get('standby_client_cidr', '10.20.1.0/24'),
        standby_route_table_id=d.get('standby_route_table_id', ''),
    )


# ── DG Cross-Region: reusable child modules ───────────────────────────────────

def dg_cr_region_main(d, side='primary'):
    remote_cidr = d.get('standby_client_cidr', '10.30.1.0/24') if side == 'primary' \
                  else d.get('primary_client_cidr', '10.10.1.0/24')
    return render_tf('oci_dg_region/main.tf.j2',
        add_ssh=d.get('add_ssh', False),
        side=side,
        manage_route_table=d.get('manage_route_table', False),
        remote_client_cidr=remote_cidr,
        extra_pairs=_side_pairs(d, side),
    )


def dg_cr_region_vars(d=None):
    return render_tf('oci_dg_region/variables.tf.j2',
                     extra_pairs=(d or {}).get('additional_pairs') or [])


def dg_cr_region_outputs(d=None):
    return render_tf('oci_dg_region/outputs.tf.j2',
                     extra_pairs=(d or {}).get('additional_pairs') or [])


def dg_cr_peering_main():
    return render_tf('oci_dg_peering/main.tf.j2')


def dg_cr_peering_vars():
    return render_tf('oci_dg_peering/variables.tf.j2')


def dg_cr_peering_outputs():
    return render_tf('oci_dg_peering/outputs.tf.j2')


# ── DG Cross-Region: root module ─────────────────────────────────────────────

def dg_cr_root_main(d=None):
    return render_tf('oci_dg_root/main.tf.j2',
                     extra_pairs=(d or {}).get('additional_pairs') or [])


def dg_cr_root_vars(d):
    return render_tf('oci_dg_root/variables.tf.j2',
        prefix=d.get('prefix', 'dg'),
        compartment_id=d.get('compartment_id', ''),
        primary_oci_region=d.get('primary_oci_region', ''),
        standby_oci_region=d.get('standby_oci_region', ''),
        primary_vcn_id=d.get('primary_vcn_id', ''),
        primary_nsg_id=d.get('primary_nsg_id', ''),
        primary_client_cidr=d.get('primary_client_cidr', '10.10.1.0/24'),
        primary_route_table_id=d.get('primary_route_table_id', ''),
        primary_hub_cidr=d.get('primary_hub_cidr', '10.15.0.0/24'),
        standby_vcn_id=d.get('standby_vcn_id', ''),
        standby_nsg_id=d.get('standby_nsg_id', ''),
        standby_client_cidr=d.get('standby_client_cidr', '10.30.1.0/24'),
        standby_route_table_id=d.get('standby_route_table_id', ''),
        standby_hub_cidr=d.get('standby_hub_cidr', '10.16.0.0/24'),
        extra_pairs=d.get('additional_pairs') or [],
    )


def dg_cr_root_tfvars(d):
    return render_tf('oci_dg_root/terraform.tfvars.j2',
        prefix=d.get('prefix', 'dg'),
        compartment_id=d.get('compartment_id', ''),
        primary_oci_region=d.get('primary_oci_region', ''),
        standby_oci_region=d.get('standby_oci_region', ''),
        primary_vcn_id=d.get('primary_vcn_id', ''),
        primary_nsg_id=d.get('primary_nsg_id', ''),
        primary_client_cidr=d.get('primary_client_cidr', '10.10.1.0/24'),
        primary_route_table_id=d.get('primary_route_table_id', ''),
        primary_hub_cidr=d.get('primary_hub_cidr', '10.15.0.0/24'),
        standby_vcn_id=d.get('standby_vcn_id', ''),
        standby_nsg_id=d.get('standby_nsg_id', ''),
        standby_client_cidr=d.get('standby_client_cidr', '10.30.1.0/24'),
        standby_route_table_id=d.get('standby_route_table_id', ''),
        standby_hub_cidr=d.get('standby_hub_cidr', '10.16.0.0/24'),
        extra_pairs=d.get('additional_pairs') or [],
        extra_pairs_tfvars=_dg_cr_pairs_tfvars(d),
    )


def dg_cr_root_readme(d):
    return render_tf('oci_dg_root/README.md.j2',
        prefix=d.get('prefix', 'dg'),
        customer_name=d.get('customer_name', ''),
        primary_oci_region=d.get('primary_oci_region', 'us-ashburn-1'),
        standby_oci_region=d.get('standby_oci_region', 'us-portland-1'),
        primary_client_cidr=d.get('primary_client_cidr', '10.10.1.0/24'),
        primary_hub_cidr=d.get('primary_hub_cidr', '10.15.0.0/24'),
        primary_route_table_id=d.get('primary_route_table_id', ''),
        standby_client_cidr=d.get('standby_client_cidr', '10.30.1.0/24'),
        standby_hub_cidr=d.get('standby_hub_cidr', '10.16.0.0/24'),
        standby_route_table_id=d.get('standby_route_table_id', ''),
        manage_route_table=d.get('manage_route_table', False),
        extra_pairs=d.get('additional_pairs') or [],
        generated_date=datetime.date.today().isoformat(),
    )


# ── Filled checks ─────────────────────────────────────────────────────────────

def _dg_maz_filled(d):
    """Return True only if the minimum required Multi-AZ fields are present."""
    return bool(d.get('oci_region', '').strip())


def _dg_cr_filled(d):
    """Return True only if the minimum required Cross-Region fields are present."""
    return bool(d.get('primary_oci_region', '').strip()) and \
           bool(d.get('standby_oci_region', '').strip())


# ── Main entry point ──────────────────────────────────────────────────────────

# Data Guard payloads reach us under a canonical key. The cloud-prefixed variants
# are accepted for configs saved before the keys were unified: an OCI module
# should not have to learn a new name every time a cloud is added.
_CLOUD_PREFIXES = ('aws_', 'gcp_', 'azure_')


def _dg_entries(data, key):
    """Entries for `key`, falling back to deprecated <cloud>_<key> aliases."""
    entries = data.get(key)
    if entries:
        return entries
    for prefix in _CLOUD_PREFIXES:
        entries = data.get(f'{prefix}{key}')
        if entries:
            return entries
    return []


def generate_oci_dg_tf(data: dict) -> dict:
    """Return a files dict for all OCI Data Guard modules present in data."""
    files = {}

    for dg in _dg_entries(data, 'dg_multi_az'):
        if not _dg_maz_filled(dg):   # check raw data before defaults fill in placeholders
            continue
        dg = _dg_maz_defaults(dg)
        mn = dg.get('module_name', 'primary')
        files[f'dg_multi_az_{mn}/main.tf']          = dg_maz_main(mn, dg)
        files[f'dg_multi_az_{mn}/variables.tf']     = dg_maz_vars(mn, dg)
        files[f'dg_multi_az_{mn}/outputs.tf']       = dg_maz_outputs(mn)
        files[f'dg_multi_az_{mn}/terraform.tfvars'] = dg_maz_tfvars(mn, dg)
        files[f'dg_multi_az_{mn}/README.md']        = dg_maz_readme(mn, dg)

    for dg in _dg_entries(data, 'dg_cross_region'):
        if not _dg_cr_filled(dg):   # check raw data before defaults fill in placeholders
            continue
        dg = _dg_cr_defaults(dg)
        mn = dg.get('module_name', 'dg')
        base = f'dg_cross_region_{mn}'
        files[f'{base}/main.tf']                              = dg_cr_root_main(dg)
        files[f'{base}/variables.tf']                         = dg_cr_root_vars(dg)
        files[f'{base}/terraform.tfvars']                     = dg_cr_root_tfvars(dg)
        files[f'{base}/README.md']                            = dg_cr_root_readme(dg)
        # Separate module dirs so primary and DR route rules can be edited independently
        files[f'{base}/modules/oci-dg-primary/main.tf']      = dg_cr_region_main(dg, side='primary')
        files[f'{base}/modules/oci-dg-primary/variables.tf'] = dg_cr_region_vars(dg)
        files[f'{base}/modules/oci-dg-primary/outputs.tf']   = dg_cr_region_outputs(dg)
        files[f'{base}/modules/oci-dg-dr/main.tf']           = dg_cr_region_main(dg, side='dr')
        files[f'{base}/modules/oci-dg-dr/variables.tf']      = dg_cr_region_vars(dg)
        files[f'{base}/modules/oci-dg-dr/outputs.tf']        = dg_cr_region_outputs(dg)
        files[f'{base}/modules/oci-dg-peering/main.tf']      = dg_cr_peering_main()
        files[f'{base}/modules/oci-dg-peering/variables.tf'] = dg_cr_peering_vars()
        files[f'{base}/modules/oci-dg-peering/outputs.tf']   = dg_cr_peering_outputs()

    return files
