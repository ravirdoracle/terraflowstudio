"""GCP (AI DB@GCP) generators."""
import datetime
import json
import re
import regions
import shapes
import os

from core.helpers import make_renderer
from core.helpers import parse_list, tf_bool, tf_num

# This package renders only its own templates. Reaching for another cloud's
# raises TemplateNotFound rather than quietly working.
render_tf = make_renderer(os.path.join(os.path.dirname(__file__), 'templates'))
from oci import generate_oci_dg_tf
from oci import (
    _ocidb_filled, _oci_db_defaults,
    _mn_dbhome, _mn_cdb, _mn_pdb,
    oci_dbhome_main, oci_dbhome_vars, oci_dbhome_outputs, oci_dbhome_tfvars,
    oci_cdb_main, oci_cdb_vars, oci_cdb_outputs, oci_cdb_tfvars,
    oci_pdb_main, oci_pdb_vars, oci_pdb_outputs, oci_pdb_tfvars,
)

# Sourced from config/gcp_regions.json — edit that file, not this module.
def _oci_region_for(gcp_region):
    return regions.to_oci_region('gcp').get(gcp_region, regions.default_oci_region('gcp'))

# Shared module directory names (fixed, not per-instance)
_GCP_MOD_NET      = 'gcp-odb-network'
_GCP_MOD_NET_ADBS = 'gcp-odb-network-adbs'
_GCP_MOD_INFRA    = 'gcp-exadata-infra'
_GCP_MOD_CLUSTER  = 'gcp-vm-cluster'
_GCP_MOD_ADB      = 'gcp-autonomous-db'
_GCP_MOD_XS_VAULT   = 'gcp-exascale-vault'
_GCP_MOD_XS_CLUSTER = 'gcp-exascale-vm-cluster'

#: First hashicorp/google release with the Exascale resources, found by
#: validating each release: 7.19.0 fails with "Invalid resource type".
_GCP_EXASCALE_FLOOR = '7.20.0'

#: What an ODB Network is there to serve. Set per network on the card; it is
#: what decides the shape of the generated configuration.
#:
#:   dedicated  Exadata only  — client + backup subnets, infra and VM cluster
#:                             modules emitted
#:   adbs       Autonomous AI Database Serverless only — client subnet only, no
#:                             backup subnet; no Exadata modules if no other
#:                             network wants them
#:   both       serves both    — the historical behaviour, and the default, so
#:                             configs saved before this flag existed generate
#:                             byte-identical output
_GCP_NET_PURPOSES = ('dedicated', 'adbs', 'both')
_GCP_NET_PURPOSE_DEFAULT = 'both'


def _wants_dedicated(networks, infras=(), clusters=()):
    """True when anything in this config needs the Exadata modules.

    A configuration whose every network is ADB-S-only has no Exadata
    Infrastructure and no VM Cluster under it, so those module directories,
    their root module blocks, their map variables and the DB-server data source
    are all left out rather than emitted empty.

    An explicitly configured infra or cluster still counts, whatever the network
    flags say: dropping a resource the user actually filled in would be silent
    data loss. The flag suppresses the *phantom* instance an empty payload would
    otherwise materialise, not a real one.
    """
    if infras or clusters:
        return True
    if not networks:
        return True          # legacy/empty payloads keep the historical shape
    return any(n.get('purpose', _GCP_NET_PURPOSE_DEFAULT) != 'adbs' for n in networks)


def _split_networks(networks):
    """(dedicated-or-both, adbs-only) — they render from different modules."""
    dedicated, adbs_only = [], []
    for n in networks:
        (adbs_only if n.get('purpose') == 'adbs' else dedicated).append(n)
    return dedicated, adbs_only


# ── Shared module file renderers ──────────────────────────────────────────────

def _gcp_adb_module_files() -> dict:
    """Render the Autonomous DB module directory.

    Emitted only when the config has at least one ADB, so a config without one
    generates exactly the files it did before ADB support existed.
    """
    return {
        f'modules/{_GCP_MOD_ADB}/main.tf':      render_tf('gcp_autonomous_db/main.tf.j2'),
        f'modules/{_GCP_MOD_ADB}/variables.tf': render_tf('gcp_autonomous_db/variables.tf.j2'),
        f'modules/{_GCP_MOD_ADB}/outputs.tf':   render_tf('gcp_autonomous_db/outputs.tf.j2'),
    }


def _gcp_adbs_net_module_files() -> dict:
    """The ADB-S-only ODB Network module — client subnet, no backup subnet."""
    return {
        f'modules/{_GCP_MOD_NET_ADBS}/main.tf':      render_tf('gcp_odb_network_adbs/main.tf.j2'),
        f'modules/{_GCP_MOD_NET_ADBS}/variables.tf': render_tf('gcp_odb_network_adbs/variables.tf.j2'),
        f'modules/{_GCP_MOD_NET_ADBS}/outputs.tf':   render_tf('gcp_odb_network_adbs/outputs.tf.j2'),
    }


def _gcp_exadata_module_files() -> dict:
    """Exadata Infrastructure + VM Cluster — the Dedicated half of the config."""
    return {
        f'modules/{_GCP_MOD_INFRA}/main.tf':     render_tf('gcp_exadb_infra/main.tf.j2'),
        f'modules/{_GCP_MOD_INFRA}/variables.tf': render_tf('gcp_exadb_infra/variables.tf.j2'),
        f'modules/{_GCP_MOD_INFRA}/outputs.tf':  render_tf('gcp_exadb_infra/outputs.tf.j2'),
        f'modules/{_GCP_MOD_CLUSTER}/main.tf':      render_tf('gcp_exadb_vm_cluster/main.tf.j2'),
        f'modules/{_GCP_MOD_CLUSTER}/variables.tf': render_tf('gcp_exadb_vm_cluster/variables.tf.j2'),
        f'modules/{_GCP_MOD_CLUSTER}/outputs.tf':   render_tf('gcp_exadb_vm_cluster/outputs.tf.j2'),
    }


def _gcp_exascale_module_files() -> dict:
    """Exascale vault + VM cluster. Emitted only when the config has an Exascale
    vault or VM cluster, so every other config generates exactly what it did before."""
    return {
        f'modules/{_GCP_MOD_XS_VAULT}/main.tf':        render_tf('gcp_exascale_vault/main.tf.j2'),
        f'modules/{_GCP_MOD_XS_VAULT}/variables.tf':   render_tf('gcp_exascale_vault/variables.tf.j2'),
        f'modules/{_GCP_MOD_XS_VAULT}/outputs.tf':     render_tf('gcp_exascale_vault/outputs.tf.j2'),
        f'modules/{_GCP_MOD_XS_CLUSTER}/main.tf':      render_tf('gcp_exascale_vm_cluster/main.tf.j2'),
        f'modules/{_GCP_MOD_XS_CLUSTER}/variables.tf': render_tf('gcp_exascale_vm_cluster/variables.tf.j2'),
        f'modules/{_GCP_MOD_XS_CLUSTER}/outputs.tf':   render_tf('gcp_exascale_vm_cluster/outputs.tf.j2'),
    }


def _gcp_shared_module_files() -> dict:
    """Render the 3 shared, reusable GCP module directories.

    Kept as-is for callers that want the historical full set; generate_gcp_tf
    now assembles the directories the configuration actually needs.
    """
    return {
        f'modules/{_GCP_MOD_NET}/main.tf':       render_tf('gcp_odb_network/main.tf.j2'),
        f'modules/{_GCP_MOD_NET}/variables.tf':  render_tf('gcp_odb_network/variables.tf.j2'),
        f'modules/{_GCP_MOD_NET}/outputs.tf':    render_tf('gcp_odb_network/outputs.tf.j2'),
        **_gcp_exadata_module_files(),
    }


# ── Root builders ─────────────────────────────────────────────────────────────

def gcp_build_root_main(networks, infras, clusters, oci_databases=None, oci_region='us-ashburn-1', iac_tool='terraform', adbs=None,
                        dedicated_nets=None, adbs_nets=None, wants_dedicated=True, has_std_nets=True, **xs):
    return render_tf('gcp_root/main.tf.j2', **_xs_ctx(xs),
        networks=networks, infras=infras, clusters=clusters, adbs=adbs or [],
        dedicated_nets=dedicated_nets if dedicated_nets is not None else networks,
        adbs_nets=adbs_nets or [], wants_dedicated=wants_dedicated, has_std_nets=has_std_nets,
        oci_databases=oci_databases or [], oci_region=oci_region, iac_tool=iac_tool)


def gcp_build_root_vars(networks, infras, clusters, oci_databases=None, oci_region='us-ashburn-1', adbs=None,
                        dedicated_nets=None, adbs_nets=None, wants_dedicated=True, has_std_nets=True, **xs):
    gcp_project = 'my-gcp-project'
    gcp_region  = 'us-east4'
    for n in (networks or []):
        if n.get('project'): gcp_project = n['project']; break
    for items in [networks, infras, clusters]:
        for item in (items or []):
            if item.get('location'): gcp_region = item['location']; break
    return render_tf('gcp_root/variables.tf.j2', **_xs_ctx(xs),
        gcp_project=gcp_project, gcp_region=gcp_region, adbs=adbs or [],
        dedicated_nets=dedicated_nets if dedicated_nets is not None else networks,
        adbs_nets=adbs_nets or [], wants_dedicated=wants_dedicated, has_std_nets=has_std_nets,
        oci_databases=oci_databases or [], oci_region=oci_region)


def gcp_build_readme(networks, infras, clusters, iac_tool='terraform', customer_name='', adbs=None,
                     dedicated_nets=None, adbs_nets=None, wants_dedicated=True, has_std_nets=True, **xs):
    proj = 'my-gcp-project'
    loc  = 'us-east4'
    for items in [networks, infras, clusters]:
        for item in (items or []):
            if item.get('project'): proj = item['project']
            if item.get('location'): loc = item['location']
    # Ensure display-friendly CIDR aliases are present
    nets_doc = [{**n, 'client_cidr_range': n.get('client_cidr_range') or n.get('client_cidr', ''),
                      'backup_cidr_range': n.get('backup_cidr_range') or n.get('backup_cidr', '')}
                for n in networks]
    return render_tf('gcp_root/README.md.j2', **_xs_ctx(xs),
        gcp_project=proj, gcp_region=loc,
        networks=nets_doc, infras=infras, clusters=clusters, adbs=adbs or [],
        adbs_nets=adbs_nets or [], wants_dedicated=wants_dedicated, has_std_nets=has_std_nets,
        iac_tool=iac_tool,
        customer_name=customer_name,
        generated_date=datetime.date.today().isoformat())


def gcp_build_root_tfvars(networks, infras, clusters, adbs=None,
                          dedicated_nets=None, adbs_nets=None, wants_dedicated=True, has_std_nets=True, **xs):
    proj = 'my-gcp-project'
    loc  = 'us-east4'
    for items in [networks, infras, clusters]:
        for item in (items or []):
            if item.get('project'): proj = item['project']
            if item.get('location'): loc = item['location']
    return render_tf('gcp_root/terraform.tfvars.j2', **_xs_ctx(xs),
        exascale_tfvars=_gcp_xs_tfvars(xs.get('xs_vaults') or [], xs.get('xs_clusters') or []),
        gcp_project=proj, gcp_region=loc,
        networks=networks, infras=infras, clusters=clusters, adbs=adbs or [],
        dedicated_nets=dedicated_nets if dedicated_nets is not None else networks,
        adbs_nets=adbs_nets or [], wants_dedicated=wants_dedicated, has_std_nets=has_std_nets)


def _xs_ctx(xs):
    """Exascale template context; empty for a config without Exascale."""
    vaults, clusters = xs.get('xs_vaults') or [], xs.get('xs_clusters') or []
    return dict(exascale=bool(vaults or clusters), xs_vaults=vaults, xs_clusters=clusters,
                exascale_floor=_GCP_EXASCALE_FLOOR)


# ── Default normalizers ───────────────────────────────────────────────────────

def _gcp_net_defaults(d):
    purpose = d.get('purpose') or _GCP_NET_PURPOSE_DEFAULT
    if purpose not in _GCP_NET_PURPOSES:
        purpose = _GCP_NET_PURPOSE_DEFAULT
    return {**d,
        # What this network serves — see _GCP_NET_PURPOSES. Defaults to 'both',
        # so a config saved before the flag existed keeps its exact output.
        'purpose':            purpose,
        'odb_network_id':     d.get('odb_network_id') or 'my-odb-network',
        'network':            d.get('network') or 'projects/PROJECT/global/networks/default',
        'client_subnet_id':   d.get('client_subnet_id') or 'client-subnet',
        'client_cidr':        d.get('client_cidr') or d.get('client_subnet_cidr') or '10.0.1.0/24',
        'backup_subnet_id':   d.get('backup_subnet_id') or 'backup-subnet',
        'backup_cidr':        d.get('backup_cidr') or d.get('backup_subnet_cidr') or '10.0.2.0/24',
        'deletion_protection': d.get('deletion_protection', True),
        'gcp_oracle_zone':    d.get('gcp_oracle_zone') or '',
        'labels':             d.get('labels', {}),
    }


def _gcp_infra_defaults(d):
    raw_hours  = parse_list(d.get('mw_hours_of_day', ''))
    raw_weeks  = parse_list(d.get('mw_weeks_of_month', ''))
    return {**d,
        'cloud_exadata_infrastructure_id': d.get('cloud_exadata_infrastructure_id') or 'my-exadb-infra',
        'display_name':       d.get('display_name') or 'my-exadb-infra',
        'gcp_oracle_zone':    d.get('gcp_oracle_zone') or '',
        'shape':              d.get('shape') or shapes.default_shape('gcp'),
        'compute_count':      int(d.get('compute_count') or 2),
        'storage_count':      int(d.get('storage_count') or 3),
        'total_storage_size_gb': int(d.get('total_storage_size_gb') or 0),
        'customer_contacts':  d.get('customer_contacts', []),
        'mw_preference':      d.get('mw_preference', 'NO_PREFERENCE'),
        'mw_patching_mode':   d.get('mw_patching_mode', 'ROLLING'),
        'mw_is_custom_action_timeout_enabled': tf_bool(d.get('mw_is_custom_action_timeout_enabled', False)),
        'mw_custom_action_timeout_mins': int(d.get('mw_custom_action_timeout_mins', 15) or 15),
        'mw_lead_time_week':  d.get('mw_lead_time_week', ''),
        'mw_months':          parse_list(d.get('mw_months', '')),
        'mw_weeks_of_month':  [int(x) for x in raw_weeks if x.strip().lstrip('-').isdigit()],
        'mw_days_of_week':    parse_list(d.get('mw_days_of_week', '')),
        'mw_hours_of_day':    [int(x) for x in raw_hours if x.strip().lstrip('-').isdigit()],
        'deletion_protection': d.get('deletion_protection', True),
        'labels':             d.get('labels', {}),
    }


def _gcp_cluster_defaults(d, first_net=None, first_infra=None):
    first_net   = first_net or {}
    first_infra = first_infra or {}
    return {**d,
        'cloud_vm_cluster_id':    d.get('cloud_vm_cluster_id') or d.get('exadb_vm_cluster_id') or 'my-vm-cluster',
        'display_name':           d.get('display_name') or 'my-vm-cluster',
        'gi_version':             d.get('gi_version') or '23.0.0.0',
        'hostname_prefix':        d.get('hostname_prefix') or 'vm',
        'cpu_core_count':         int(d.get('cpu_core_count') or 16),
        'memory_size_gb':         int(d.get('memory_size_gb') or 60),
        'db_node_storage_size_gb': int(d.get('db_node_storage_size_gb') or 120),
        'data_storage_size_tb':   float(d.get('data_storage_size_tb') or 4.0),
        'local_backup_enabled':   d.get('local_backup_enabled', False),
        'sparse_diskgroup_enabled': d.get('sparse_diskgroup_enabled', False),
        'license_type':           d.get('license_type') or 'LICENSE_INCLUDED',
        'ssh_public_keys':        d.get('ssh_public_keys') or [],
        'deletion_protection':    d.get('deletion_protection', True),
        'network_ref':  d.get('network_ref') or first_net.get('module_name') or 'gcp-odb-network',
        'infra_ref':    d.get('infra_ref')   or first_infra.get('module_name') or 'gcp-exadata-infra',
        'labels':       d.get('labels', {}),
        # Optional attributes — the root module and gcp-vm-cluster module already
        # accept all of these, so they must reach terraform.auto.tfvars or the
        # form values silently fall back to the optional() defaults.
        'location':               d.get('location') or '',
        'project':                d.get('project') or '',
        'cluster_name':           d.get('cluster_name') or '',
        'time_zone':              d.get('time_zone') or '',
        'scan_listener_port_tcp': tf_num(d.get('scan_listener_port_tcp')),
        'dco_diagnostics':        bool(d.get('dco_diagnostics', True)),
        'dco_health':             bool(d.get('dco_health', True)),
        'dco_incident_logs':      bool(d.get('dco_incident_logs', True)),
    }


def _gcp_adb_defaults(d, first_net=None):
    """Autonomous AI Database Serverless.

    No infra_ref: Serverless runs on Oracle's fleet, not on an Exadata
    Infrastructure you provision. It still takes a network_ref, because the
    private endpoint lands in that ODB Network's *client* subnet — ADB never
    uses the backup subnet.

    Also no gcp_oracle_zone: ADB is a regional resource.
    """
    first_net = first_net or {}
    adb_id = d.get('autonomous_database_id') or 'my-adb'
    # The id allows hyphens; `database` is the Oracle DB name and takes at most
    # 30 *alphanumeric* characters, so the separators are stripped rather than
    # substituted — an underscore would be rejected just as a hyphen is.
    return {**d,
        'module_name':            d.get('module_name') or 'gcp_adb',
        'autonomous_database_id': adb_id,
        'database':               d.get('database') or ''.join(c for c in adb_id if c.isalnum())[:30],
        'display_name':           d.get('display_name') or '',
        'network_ref':            d.get('network_ref') or first_net.get('module_name') or 'gcp_network',
        'location':               d.get('location') or '',
        'project':                d.get('project') or '',
        'db_workload':            d.get('db_workload') or 'OLTP',
        'license_type':           d.get('license_type') or 'LICENSE_INCLUDED',
        'db_edition':             d.get('db_edition') or 'ENTERPRISE_EDITION',
        'db_version':             d.get('db_version') or '23ai',
        # Fractional ECPU is legal, but a whole number should read as one in
        # tfvars — 2.0 where the console shows 2 invites a "did that round?".
        'compute_count':          _num(d.get('compute_count'), 2),
        'data_storage_size_gb':   int(d.get('data_storage_size_gb') or 120),
        'is_auto_scaling_enabled':         bool(d.get('is_auto_scaling_enabled', True)),
        'is_storage_auto_scaling_enabled': bool(d.get('is_storage_auto_scaling_enabled', False)),
        'backup_retention_period_days':    int(d.get('backup_retention_period_days') or 60),
        'maintenance_schedule_type':       d.get('maintenance_schedule_type') or 'REGULAR',
        'character_set':          d.get('character_set') or 'AL32UTF8',
        'n_character_set':        d.get('n_character_set') or 'AL16UTF16',
        'operations_insights_state': d.get('operations_insights_state') or 'NOT_ENABLED',
        'mtls_connection_required': bool(d.get('mtls_connection_required', True)),
        'private_endpoint_label': d.get('private_endpoint_label') or '',
        'private_endpoint_ip':    d.get('private_endpoint_ip') or '',
        'customer_contacts':      _as_list(d.get('customer_contacts')),
        'deletion_protection':    d.get('deletion_protection', True),
        'labels':                 d.get('labels', {}),
    }


def _gcp_xs_vault_defaults(d):
    """Exascale Database Storage Vault: database storage several clusters share."""
    flash = d.get('additional_flash_cache_percent')
    return {
        'module_name':                    d.get('module_name') or 'gcp_xs_vault',
        'exascale_db_storage_vault_id':   d.get('exascale_db_storage_vault_id') or 'my-exascale-vault',
        'display_name':                   d.get('display_name') or '',
        'location':                       d.get('location') or '',
        'project':                        d.get('project') or '',
        'gcp_oracle_zone':                d.get('gcp_oracle_zone') or '',
        'total_size_gbs':                 int(d.get('total_size_gbs') or 300),
        'additional_flash_cache_percent': int(flash) if flash not in (None, '') else None,
        'time_zone':                      d.get('time_zone') or '',
        'deletion_protection':            d.get('deletion_protection', True),
        'labels':                         d.get('labels') or {},
    }


#: Oracle publishes no API for the Grid Infrastructure image OCID. The
#: placeholder passes the module's ocid1.dbpatch. check so the configuration
#: validates, and fails at apply until it is replaced.
_GCP_XS_GRID_PLACEHOLDER = 'ocid1.dbpatch.oc1..CHANGEME'


def _gcp_xs_cluster_defaults(d, std_net_names, vault_names):
    """Exascale VM Cluster. No Exadata Infrastructure under it and no zone input.

    It needs a client *and* backup subnet, so network_ref names a standard ODB
    Network, never an ADB-S-only one. The vault is a card here (vault_ref) or an
    existing one by full resource name (existing_vault). Dangling refs fall
    back to the first card, as a missing map key fails at apply.
    """
    shape = d.get('shape_attribute') if d.get('shape_attribute') in ('SMART_STORAGE', 'BLOCK_STORAGE') else 'SMART_STORAGE'
    existing_vault = (d.get('existing_vault') or '').strip()
    vault_ref = d.get('vault_ref') or ''
    if vault_ref not in vault_names:
        vault_ref = '' if existing_vault or not vault_names else vault_names[0]
    net_ref = d.get('network_ref') or ''
    if std_net_names and net_ref not in std_net_names:
        net_ref = std_net_names[0]
    extra = d.get('additional_ecpu_count_per_node')
    return {
        'module_name':                    d.get('module_name') or 'gcp_xs_cluster',
        'exadb_vm_cluster_id':            d.get('exadb_vm_cluster_id') or 'my-exascale-cluster',
        'display_name':                   d.get('display_name') or '',
        'location':                       d.get('location') or '',
        'project':                        d.get('project') or '',
        'network_ref':                    net_ref,
        'vault_ref':                      vault_ref,
        'existing_vault':                 '' if vault_ref else existing_vault,
        'grid_image_id':                  (d.get('grid_image_id') or '').strip() or _GCP_XS_GRID_PLACEHOLDER,
        'shape_attribute':                shape,
        'node_count':                     int(d.get('node_count') or 2),
        'enabled_ecpu_count_per_node':    int(d.get('enabled_ecpu_count_per_node') or 8),
        'additional_ecpu_count_per_node': int(extra) if extra not in (None, '') else None,
        # The minimum depends on the storage type: 220 GB smart, 260 GB block.
        'vm_file_system_size_gbs_per_node': int(d.get('vm_file_system_size_gbs_per_node')
                                                or (220 if shape == 'SMART_STORAGE' else 260)),
        'hostname_prefix':                d.get('hostname_prefix') or 'vm',
        'cluster_name':                   d.get('cluster_name') or '',
        'license_model':                  d.get('license_model') or 'LICENSE_INCLUDED',
        'ssh_public_keys':                _as_list(d.get('ssh_public_keys')),
        'scan_listener_port_tcp':         tf_num(d.get('scan_listener_port_tcp')),
        'time_zone':                      d.get('time_zone') or '',
        'dco_diagnostics':                bool(d.get('dco_diagnostics', True)),
        'dco_health':                     bool(d.get('dco_health', True)),
        'dco_incident_logs':              bool(d.get('dco_incident_logs', True)),
        'deletion_protection':            d.get('deletion_protection', True),
        'labels':                         d.get('labels') or {},
    }


def _hcl(v):
    """A JSON string literal is a valid HCL string literal."""
    return json.dumps(v) if isinstance(v, str) else ('true' if v is True else 'false' if v is False else str(v))


def _tf_entries(name, entries):
    """`name = { "key" = { ... } }` with each entry's keys aligned as fmt does.

    Built here because which optional keys an entry sets varies, and fmt pads
    each run of single-line attributes to its own longest key.
    """
    lines = [f'{name} = {{']
    for i, (key, attrs) in enumerate(entries):
        if i:
            lines.append('')
        lines.append(f'  {json.dumps(key)} = {{')
        w = max(len(k) for k, _ in attrs)
        lines += [f'    {k.ljust(w)} = {v}' for k, v in attrs]
        lines.append('  }')
    lines.append('}')
    return '\n'.join(lines)


def _labels_hcl(labels):
    return '{ ' + ', '.join(f'{json.dumps(k)} = {json.dumps(v)}' for k, v in labels.items()) + ' }' if labels else '{}'


def _gcp_xs_tfvars(vaults, clusters):
    if not vaults and not clusters:
        return ''
    v_entries = []
    for v in vaults:
        attrs = [('exascale_db_storage_vault_id', _hcl(v['exascale_db_storage_vault_id']))]
        for k in ('display_name', 'location', 'project', 'gcp_oracle_zone'):
            if v[k]:
                attrs.append((k, _hcl(v[k])))
        attrs.append(('total_size_gbs', _hcl(v['total_size_gbs'])))
        if v['additional_flash_cache_percent'] is not None:
            attrs.append(('additional_flash_cache_percent', _hcl(v['additional_flash_cache_percent'])))
        if v['time_zone']:
            attrs.append(('time_zone', _hcl(v['time_zone'])))
        attrs += [('deletion_protection', _hcl(bool(v['deletion_protection']))),
                  ('labels', _labels_hcl(v['labels']))]
        v_entries.append((v['module_name'], attrs))
    c_entries = []
    for c in clusters:
        attrs = [('network_key', _hcl(c['network_ref']))]
        attrs.append(('vault_key', _hcl(c['vault_ref'])) if c['vault_ref']
                     else ('existing_vault', _hcl(c['existing_vault'])))
        attrs.append(('exadb_vm_cluster_id', _hcl(c['exadb_vm_cluster_id'])))
        for k in ('display_name', 'location', 'project'):
            if c[k]:
                attrs.append((k, _hcl(c[k])))
        attrs += [('grid_image_id', _hcl(c['grid_image_id'])),
                  ('shape_attribute', _hcl(c['shape_attribute'])),
                  ('node_count', _hcl(c['node_count'])),
                  ('enabled_ecpu_count_per_node', _hcl(c['enabled_ecpu_count_per_node']))]
        if c['additional_ecpu_count_per_node'] is not None:
            attrs.append(('additional_ecpu_count_per_node', _hcl(c['additional_ecpu_count_per_node'])))
        attrs += [('vm_file_system_size_gbs_per_node', _hcl(c['vm_file_system_size_gbs_per_node'])),
                  ('hostname_prefix', _hcl(c['hostname_prefix']))]
        if c['cluster_name']:
            attrs.append(('cluster_name', _hcl(c['cluster_name'])))
        attrs += [('license_model', _hcl(c['license_model'])),
                  ('ssh_public_keys', '[' + ', '.join(json.dumps(k) for k in c['ssh_public_keys']) + ']')]
        if c['scan_listener_port_tcp'] is not None:
            attrs.append(('scan_listener_port_tcp', _hcl(c['scan_listener_port_tcp'])))
        if c['time_zone']:
            attrs.append(('time_zone', _hcl(c['time_zone'])))
        attrs += [('dco_diagnostics', _hcl(c['dco_diagnostics'])),
                  ('dco_health', _hcl(c['dco_health'])),
                  ('dco_incident_logs', _hcl(c['dco_incident_logs'])),
                  ('deletion_protection', _hcl(bool(c['deletion_protection']))),
                  ('labels', _labels_hcl(c['labels']))]
        c_entries.append((c['module_name'], attrs))
    out = ['# Exascale: storage vaults and the VM clusters on them. No Exadata Infrastructure.',
           '# vault_key names a vault below; existing_vault is the full resource name of one',
           '# built elsewhere. grid_image_id has no API: read it in the OCI Console.']
    out.append(_tf_entries('gcp_exascale_vaults', v_entries) if v_entries else 'gcp_exascale_vaults = {}')
    out += ['', _tf_entries('gcp_exascale_vm_clusters', c_entries) if c_entries else 'gcp_exascale_vm_clusters = {}']
    return '\n'.join(out)


#: Root of the customer-managed-key output, beside the main configuration.
_GCP_KMS_DIR = 'kms'
_PLACEHOLDER = 'CHANGEME'


def _gcp_kms_defaults(d, clusters, networks):
    """A Cloud KMS customer-managed TDE key for one ExaDB-D VM cluster.

    Generates two standalone roots rather than a module of the main root:
    the OCI half authenticates differently (a federated session token) and in
    two regions; both run only after the VM cluster exists, since the service
    agent email and connector OCID come from its Identity Connector; and the
    crypto key's prevent_destroy would otherwise block destroying the main root.

    Project, location and the paired OCI multicloud region default from the
    chosen cluster - the region catalogue already pairs GCP locations with OCI
    regions. What only exists after provisioning stays CHANGEME.
    """
    name = (d.get('module_name') or 'exadb_kms').strip()
    cluster = next((c for c in clusters if c['module_name'] == d.get('cluster_ref')),
                   clusters[0] if clusters else {})
    net = next((n for n in networks if n.get('location')), networks[0] if networks else {})
    location = ((d.get('gcp_kms_location') or '').strip() or cluster.get('location')
                or net.get('location') or 'us-east4')
    project = ((d.get('gcp_project_id') or '').strip() or cluster.get('project')
               or net.get('project') or _PLACEHOLDER)
    key_ring = (d.get('gcp_key_ring_name') or '').strip() or 'exadb-tde'
    # The custom role is project-wide: two key rings in one project sharing a
    # role ID would collide on create, so the default carries the card's name.
    role_id = ((d.get('oracle_kms_role_id') or '').strip()
               or ('oracleExadbKms_' + re.sub(r'[^A-Za-z0-9_]', '_', name))[:64])
    level = (d.get('key_protection_level') or 'HSM').upper()
    return {**d,
        'module_name': name,
        'cluster_ref': cluster.get('module_name', ''),
        'gcp_project_id': project,
        'gcp_kms_location': location,
        'gcp_key_ring_name': key_ring,
        'gcp_crypto_key_name': (d.get('gcp_crypto_key_name') or '').strip() or 'exadb-tde-mek',
        'key_protection_level': level if level in ('HSM', 'SOFTWARE') else 'HSM',
        'oracle_kms_role_id': role_id,
        'oracle_workload_resource_service_agent':
            (d.get('oracle_workload_resource_service_agent') or '').strip() or _PLACEHOLDER,
        'oci_auth': d.get('oci_auth') or 'SecurityToken',
        'oci_config_profile': (d.get('oci_config_profile') or '').strip() or 'FEDERATED_TF',
        'oci_multicloud_region': (d.get('oci_multicloud_region') or '').strip() or _oci_region_for(location),
        'oci_home_region': (d.get('oci_home_region') or '').strip() or _PLACEHOLDER,
        'oci_compartment_ocid': (d.get('oci_compartment_ocid') or '').strip() or _PLACEHOLDER,
        'oci_gcp_identity_connector_ocid': (d.get('oci_gcp_identity_connector_ocid') or '').strip() or _PLACEHOLDER,
        'oci_gcp_key_ring_display_name': (d.get('oci_gcp_key_ring_display_name') or '').strip() or key_ring,
        'create_cluster_gcp_key_policy': bool(d.get('create_cluster_gcp_key_policy', False)),
        'oci_gcp_key_policy_name': (d.get('oci_gcp_key_policy_name') or '').strip() or 'exadb-read-gcp-kms-keys',
        # Known before anything is applied, so the OCI root needs no hand-off.
        'gcp_key_ring_id': f'projects/{project}/locations/{location}/keyRings/{key_ring}',
    }


def _gcp_kms_files(k, iac_tool):
    base = f'{_GCP_KMS_DIR}/{k["module_name"]}'
    files = {f'{base}/README.md': render_tf('gcp_kms/README.md.j2', k=k)}
    for side in ('gcp', 'oci'):
        for f in ('versions.tf', 'variables.tf', 'main.tf', 'outputs.tf'):
            files[f'{base}/{side}/{f}'] = render_tf(f'gcp_kms/{side}/{f}.j2', iac_tool=iac_tool)
        files[f'{base}/{side}/terraform.tfvars'] = render_tf(f'gcp_kms/{side}/terraform.tfvars.j2', k=k)
    return files


def _as_list(v):
    """Form values arrive as a list or as 'a, b' — templates need a list."""
    if isinstance(v, list):
        return v
    return parse_list(v or '')


def _num(v, default):
    """Float, narrowed to int when it is whole, for tidier HCL."""
    n = float(v if v not in (None, '') else default)
    return int(n) if n == int(n) else n


# ── GCP Terraform generator ───────────────────────────────────────────────────

def generate_gcp_tf(data: dict) -> dict:
    raw_nets     = data.get('gcp_networks', [])
    raw_infras   = data.get('gcp_infras', [])
    raw_clusters = data.get('gcp_clusters', [])
    raw_adbs     = data.get('gcp_autonomous_dbs', [])
    raw_oci_dbs  = data.get('gcp_oci_databases', [])

    # Legacy single-resource payload support
    if not raw_nets:
        raw_nets = [{
            **data.get('gcp_module_0', {}),
            'module_name': data.get('gcp_module_names', {}).get('0', 'gcp-odb-network'),
            'client_subnet_id':  data.get('gcp_module_1', {}).get('odb_subnet_id', 'client-subnet'),
            'client_cidr':       data.get('gcp_module_1', {}).get('cidr_range', '10.0.1.0/24'),
            'backup_subnet_id':  data.get('gcp_module_2', {}).get('odb_subnet_id', 'backup-subnet'),
            'backup_cidr':       data.get('gcp_module_2', {}).get('cidr_range', '10.0.2.0/24'),
        }]
    # An empty infra/cluster payload still materialises one instance, so that a
    # half-filled form generates something to look at. That is wrong for an
    # ADB-S-only configuration, which has no Exadata layer at all — inventing a
    # phantom infra and cluster there would emit modules the deployment must not
    # have. Keyed off the network flag, so every other config is unaffected.
    raw_xs_vaults   = data.get('gcp_exascale_vaults') or []
    raw_xs_clusters = data.get('gcp_exascale_clusters') or []
    # Exascale has no Exadata Infrastructure either: a config with Exascale
    # and no infra or cluster of its own gets no Exadata modules. With Exascale
    # present an empty list is a choice, not a half-filled form, so no phantom
    # infra or cluster is invented for it either.
    has_xs = bool(raw_xs_clusters or raw_xs_vaults)
    wants_dedicated = _wants_dedicated(raw_nets, raw_infras, raw_clusters) and \
        not (has_xs and not raw_infras and not raw_clusters)
    if not raw_infras and wants_dedicated and not has_xs:
        raw_infras = [{**data.get('gcp_module_3', {}), 'module_name': data.get('gcp_module_names', {}).get('3', 'gcp-exadata-infra')}]
    if not raw_clusters and wants_dedicated and not has_xs:
        raw_clusters = [{**data.get('gcp_module_4', {}), 'module_name': data.get('gcp_module_names', {}).get('4', 'gcp-vm-cluster')}]

    networks  = [_gcp_net_defaults(n) for n in raw_nets]
    infras    = [_gcp_infra_defaults(i) for i in raw_infras]
    clusters  = [_gcp_cluster_defaults(c, networks[0] if networks else None, infras[0] if infras else None)
                 for c in raw_clusters]
    dedicated_nets, adbs_nets = _split_networks(networks)

    # A network_ref naming a network this config does not build would fail at
    # apply on a missing map key, so retarget it to the first network. Unlike
    # Azure's ADB, the reference cannot simply be blanked: odb_network and
    # odb_subnet are how a GCP ADB reaches a private endpoint at all.
    net_names = [n['module_name'] for n in networks]
    adbs = []
    for a in raw_adbs:
        adb = _gcp_adb_defaults(a, networks[0] if networks else None)
        if net_names and adb['network_ref'] not in net_names:
            adb['network_ref'] = net_names[0]
        adbs.append(adb)

    first_cl_name = clusters[0]['module_name'] if clusters else ''
    oci_dbs = [_oci_db_defaults(db, first_cl_name) for db in raw_oci_dbs if _ocidb_filled(db)]

    gcp_region = 'us-east4'
    for n in networks:
        if n.get('location'): gcp_region = n['location']; break
    oci_region = _oci_region_for(gcp_region)

    iac_tool = data.get('iac_tool', 'terraform')

    customer_name = data.get('customer_name', '')
    # has_std_nets: emit the standard (client + backup) ODB Network module.
    # True unless every network in the config is ADB-S-only. An empty payload
    # keeps it, so a half-filled form still generates something to look at.
    xs_vaults = [_gcp_xs_vault_defaults(v) for v in raw_xs_vaults]
    xs_clusters = [_gcp_xs_cluster_defaults(c, [n['module_name'] for n in dedicated_nets],
                                            [v['module_name'] for v in xs_vaults])
                   for c in raw_xs_clusters]
    ctx = dict(dedicated_nets=dedicated_nets, adbs_nets=adbs_nets,
               wants_dedicated=wants_dedicated,
               has_std_nets=bool(dedicated_nets) or not networks,
               xs_vaults=xs_vaults, xs_clusters=xs_clusters)
    files = {
        'main.tf':               gcp_build_root_main(networks, infras, clusters, oci_dbs, oci_region, iac_tool, adbs, **ctx),
        'variables.tf':          gcp_build_root_vars(networks, infras, clusters, oci_dbs, oci_region, adbs, **ctx),
        'terraform.auto.tfvars': gcp_build_root_tfvars(networks, infras, clusters, adbs, **ctx),
        'README.md':             gcp_build_readme(networks, infras, clusters, iac_tool, customer_name, adbs, **ctx),
    }

    # Only the module directories this configuration actually deploys. The ODB
    # Network module comes in two shapes (with and without a backup subnet); the
    # Exadata pair is left out entirely by an ADB-S-only config.
    if dedicated_nets or not networks:
        files.update({
            f'modules/{_GCP_MOD_NET}/main.tf':      render_tf('gcp_odb_network/main.tf.j2'),
            f'modules/{_GCP_MOD_NET}/variables.tf': render_tf('gcp_odb_network/variables.tf.j2'),
            f'modules/{_GCP_MOD_NET}/outputs.tf':   render_tf('gcp_odb_network/outputs.tf.j2'),
        })
    if adbs_nets:
        files.update(_gcp_adbs_net_module_files())
    if wants_dedicated:
        files.update(_gcp_exadata_module_files())
    if adbs:
        files.update(_gcp_adb_module_files())
    if xs_vaults or xs_clusters:
        files.update(_gcp_exascale_module_files())

    # OCI DB Home / CDB / PDB modules — still per-instance (named)
    for db in oci_dbs:
        base = db['module_name']
        vcr  = db.get('vmcluster_ref', first_cl_name)
        mn_h = _mn_dbhome(base); mn_c = _mn_cdb(base); mn_p = _mn_pdb(base)
        files[f'modules/{mn_h}/main.tf']          = oci_dbhome_main(mn_h, db, vcr)
        files[f'modules/{mn_h}/variables.tf']     = oci_dbhome_vars(mn_h, db, vcr)
        files[f'modules/{mn_h}/outputs.tf']       = oci_dbhome_outputs(mn_h)
        files[f'modules/{mn_h}/terraform.tfvars'] = oci_dbhome_tfvars(mn_h, db, vcr)
        files[f'modules/{mn_c}/main.tf']          = oci_cdb_main(mn_c, db, mn_h)
        files[f'modules/{mn_c}/variables.tf']     = oci_cdb_vars(mn_c, db, mn_h)
        files[f'modules/{mn_c}/outputs.tf']       = oci_cdb_outputs(mn_c)
        files[f'modules/{mn_c}/terraform.tfvars'] = oci_cdb_tfvars(mn_c, db, mn_h)
        if db.get('create_pdb') and db.get('pdb_name'):
            files[f'modules/{mn_p}/main.tf']          = oci_pdb_main(mn_p, db, mn_c)
            files[f'modules/{mn_p}/variables.tf']     = oci_pdb_vars(mn_p, db, mn_c)
            files[f'modules/{mn_p}/outputs.tf']       = oci_pdb_outputs(mn_p)
            files[f'modules/{mn_p}/terraform.tfvars'] = oci_pdb_tfvars(mn_p, db, mn_c)

    # Customer-managed TDE keys: standalone roots under kms/, one per card.
    kms = [_gcp_kms_defaults(k, clusters, networks) for k in (data.get('gcp_kms_keys') or [])]
    for k in kms:
        files.update(_gcp_kms_files(k, iac_tool))
    if kms:
        files['README.md'] += '\n\n' + render_tf('gcp_root/README_kms.md.j2', kms=kms)

    files.update(generate_oci_dg_tf({
        'dg_multi_az':     data.get('gcp_dg_multi_az', []),
        'dg_cross_region': data.get('gcp_dg_cross_region', []),
    }))

    return files
