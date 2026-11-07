"""AWS (ODB@AWS) and CloudFormation generators."""
import re
import json
import datetime
import regions
import shapes
import os

from core.helpers import make_renderer
from core.helpers import is_ref, parse_list, tf_bool, tf_num

# This package renders only its own templates. Reaching for another cloud's
# raises TemplateNotFound rather than quietly working.
render_tf = make_renderer(os.path.join(os.path.dirname(__file__), 'templates'))
from oci import generate_oci_dg_tf
from oci import (
    _avmc_filled, _ocidb_filled, _oci_db_defaults,
    _mn_dbhome, _mn_cdb, _mn_pdb,
    oci_dbhome_main, oci_dbhome_vars, oci_dbhome_outputs, oci_dbhome_tfvars,
    oci_cdb_main, oci_cdb_vars, oci_cdb_outputs, oci_cdb_tfvars,
    oci_pdb_main, oci_pdb_vars, oci_pdb_outputs, oci_pdb_tfvars,
)

# Sourced from config/aws_regions.json — edit that file, not this module.
# Regions with no oci_region set are absent here and fall back to the default,
# which is what the hand-maintained dict this replaced did implicitly.
def _oci_region_for(aws_region):
    return regions.to_oci_region('aws').get(aws_region, regions.default_oci_region('aws'))


def _default_az(region, fallback='use1-az6'):
    """AZ ID for a card whose availability_zone_id was left blank.

    The first zone the catalogue lists for the card's own region. A literal
    'use1-az6' here put a Virginia AZ into an eu-west-2 network - and picking a
    region on the card clears its AZ dropdown, so that was the common path.
    With no region set at all the old literal stands, so an empty payload still
    generates what it always did.
    """
    zones = regions.zone_map('aws').get(region or '') or []
    return zones[0] if zones else fallback


# ── AWS MODULE 0 — aws_odb_network ────────────────────────────────────────────

def mod0_main(mn, d):
    return render_tf('aws_odb_network/main.tf.j2',
        module_name=mn,
        custom_domain_name=d.get('custom_domain_name', ''),
        default_dns_prefix=d.get('default_dns_prefix', ''),
    )


def _s3_val(v):
    if isinstance(v, str):
        return v if v in ('ENABLED', 'DISABLED') else ('ENABLED' if v else 'DISABLED')
    return 'ENABLED' if v else 'DISABLED'


def _opt_access(v):
    """Tri-state for sts_access / kms_access: unset, ENABLED or DISABLED.

    Unlike s3_access and zero_etl_access, which the provider marks Required,
    these two are Optional + Computed. An omitted value adopts whatever the
    service assigned and does not diff, so "not set" has to stay distinct from
    an explicit DISABLED rather than collapsing to a bool.
    """
    v = (v or '').strip().upper() if isinstance(v, str) else ('ENABLED' if v else '')
    return v if v in ('ENABLED', 'DISABLED') else ''


def mod0_vars(mn, d):
    return render_tf('aws_odb_network/variables.tf.j2',
        module_name=mn,
        display_name=d.get('display_name', ''),
        availability_zone_id=d.get('availability_zone_id', ''),
        client_subnet_cidr=d.get('client_subnet_cidr', ''),
        backup_subnet_cidr=d.get('backup_subnet_cidr', ''),
        s3_access=_s3_val(d.get('s3_access')),
        zero_etl_access=_s3_val(d.get('zero_etl_access')),
        sts_access=_opt_access(d.get('sts_access')),
        kms_access=_opt_access(d.get('kms_access')),
        s3_policy_document=(d.get('s3_policy_document') or '').strip(),
        sts_policy_document=(d.get('sts_policy_document') or '').strip(),
        kms_policy_document=(d.get('kms_policy_document') or '').strip(),
        cross_region_s3_restore_sources_access=_strs(
            d.get('cross_region_s3_restore_sources_access')),
        availability_zone=d.get('availability_zone', ''),
        region=d.get('region', ''),
        default_dns_prefix=d.get('default_dns_prefix', ''),
        custom_domain_name=d.get('custom_domain_name', ''),
        delete_associated_resources=tf_bool(d.get('delete_associated_resources', False)),
        tags=d.get('tags', {}),
    )


def mod0_outputs(mn):
    return render_tf('aws_odb_network/outputs.tf.j2', module_name=mn)


def mod0_tfvars(mn, d):
    return render_tf('aws_odb_network/terraform.tfvars.j2',
        module_name=mn,
        display_name=d.get('display_name', '') or 'odb-my-net',
        availability_zone_id=d.get('availability_zone_id', '') or _default_az(d.get('region')),
        client_subnet_cidr=d.get('client_subnet_cidr', '') or '10.2.0.0/24',
        backup_subnet_cidr=d.get('backup_subnet_cidr', '') or '10.2.1.0/24',
        s3_access=_s3_val(d.get('s3_access')),
        zero_etl_access=_s3_val(d.get('zero_etl_access')),
        sts_access=_opt_access(d.get('sts_access')),
        kms_access=_opt_access(d.get('kms_access')),
        s3_policy_document=(d.get('s3_policy_document') or '').strip(),
        sts_policy_document=(d.get('sts_policy_document') or '').strip(),
        kms_policy_document=(d.get('kms_policy_document') or '').strip(),
        cross_region_s3_restore_sources_access=_strs(
            d.get('cross_region_s3_restore_sources_access')),
        availability_zone=d.get('availability_zone', ''),
        region=d.get('region', ''),
        default_dns_prefix=d.get('default_dns_prefix', ''),
        custom_domain_name=d.get('custom_domain_name', ''),
        delete_associated_resources=tf_bool(d.get('delete_associated_resources', False)),
        tags=d.get('tags', {}),
    )


# ── AWS MODULE 1 — aws_odb_cloud_exadata_infrastructure ──────────────────────

def _mod1_ctx(d, defaults=False):
    raw_hours  = parse_list(d.get('mw_hours_of_day', ''))
    raw_weeks  = parse_list(d.get('mw_weeks_of_month', ''))
    hours_ints = [int(x) for x in raw_hours  if x.strip().lstrip('-').isdigit()]
    weeks_ints = [int(x) for x in raw_weeks  if x.strip().lstrip('-').isdigit()]
    days  = parse_list(d.get('mw_days_of_week', ''))
    months = parse_list(d.get('mw_months', ''))
    return dict(
        display_name=d.get('display_name', '') or ('exadb-inf-demo' if defaults else ''),
        shape=d.get('shape') or shapes.default_shape('aws'),
        compute_count=int(d.get('compute_count', 2) or 2),
        storage_count=int(d.get('storage_count', 3) or 3),
        availability_zone_id=d.get('availability_zone_id', '') or (_default_az(d.get('region'), 'usw2-az3') if defaults else ''),
        availability_zone=d.get('availability_zone', ''),
        region=d.get('region', ''),
        database_server_type=d.get('database_server_type', ''),
        storage_server_type=d.get('storage_server_type', ''),
        customer_contacts=d.get('customer_contacts', []),
        mw_preference=d.get('mw_preference', 'NO_PREFERENCE'),
        mw_patching_mode=d.get('mw_patching_mode', 'ROLLING'),
        mw_is_custom_action_timeout_enabled=tf_bool(d.get('mw_is_custom_action_timeout_enabled', False)),
        mw_custom_action_timeout_in_mins=int(d.get('mw_custom_action_timeout_in_mins', 15) or 15),
        is_custom_mw=(d.get('mw_preference', '') == 'CUSTOM_PREFERENCE'),
        mw_lead_time_in_weeks=d.get('mw_lead_time_in_weeks', ''),
        mw_hours_of_day=hours_ints,
        mw_weeks_of_month=weeks_ints,
        mw_days_of_week=days,
        mw_months=months,
        tags=d.get('tags', {}),
    )


def mod1_main(mn):
    return render_tf('aws_exadata_infra/main.tf.j2', module_name=mn)


def mod1_vars(mn, d):
    return render_tf('aws_exadata_infra/variables.tf.j2', module_name=mn, **_mod1_ctx(d))


def mod1_outputs(mn):
    return render_tf('aws_exadata_infra/outputs.tf.j2', module_name=mn)


def mod1_tfvars(mn, d):
    return render_tf('aws_exadata_infra/terraform.tfvars.j2', module_name=mn, **_mod1_ctx(d, defaults=True))


# ── AWS MODULE 2 — aws_odb_network_peering_connection ────────────────────────

def _mod2_ctx(d, mn0, defaults=False):
    odb  = d.get('odb_network_id', '') or (f'module.{mn0}.network_id' if mn0 else '')
    peer = d.get('peer_network_id', '')
    return dict(
        display_name=d.get('display_name', '') or ('odb-peering-conn' if defaults else ''),
        odb_network_id=odb,
        odb_network_id_is_ref=is_ref(odb),
        peer_network_id=peer,
        peer_network_id_is_ref=is_ref(peer),
        mn0=mn0,
        region=d.get('region', ''),
        cidrs=d.get('peer_network_cidrs', []),
        tags=d.get('tags', {}),
    )


def mod2_main(mn):
    return render_tf('aws_peering/main.tf.j2', module_name=mn)


def mod2_vars(mn, d, mn0):
    return render_tf('aws_peering/variables.tf.j2', module_name=mn, **_mod2_ctx(d, mn0))


def mod2_outputs(mn):
    return render_tf('aws_peering/outputs.tf.j2', module_name=mn)


def mod2_tfvars(mn, d, mn0):
    return render_tf('aws_peering/terraform.tfvars.j2', module_name=mn, **_mod2_ctx(d, mn0, defaults=True))


# ── AWS MODULE 3 — aws_odb_cloud_vm_cluster ───────────────────────────────────

def _mod3_ctx(d, mn0='', mn1='', defaults=False):
    infraid = d.get('cloud_exadata_infrastructure_id', '')
    netid   = d.get('odb_network_id', '')
    ds      = d.get('data_storage_size_in_tbs', '')  or 'null'
    dng     = d.get('db_node_storage_size_in_gbs', '') or 'null'
    mem     = d.get('memory_size_in_gbs', '')          or 'null'
    sc      = d.get('scan_listener_port_tcp', '')      or 'null'
    infraid = infraid or (f'module.{mn1}.infra_id' if mn1 else '')
    netid   = netid   or (f'module.{mn0}.network_id' if mn0 else '')
    infra_val = infraid if not is_ref(infraid) else infraid
    net_val   = netid   if not is_ref(netid)   else netid
    return dict(
        display_name=d.get('display_name', '') or ('tf-vmc-demo' if defaults else ''),
        cpu_core_count=int(d.get('cpu_core_count', 16) or 16),
        gi_version=d.get('gi_version', ''),
        hostname_prefix=d.get('hostname_prefix', ''),
        license_model=d.get('license_model', 'LICENSE_INCLUDED'),
        cloud_exadata_infrastructure_id=infraid,
        odb_network_id=netid,
        infra_id=infra_val,
        net_id=net_val,
        mn0=mn0, mn1=mn1,
        ssh_public_keys=d.get('ssh_public_keys', []),
        db_servers=d.get('db_servers', []),
        db_servers_mode=d.get('db_servers_mode', 'auto'),
        dco_is_diagnostics_events_enabled=tf_bool(d.get('dco_is_diagnostics_events_enabled', True)),
        dco_is_health_monitoring_enabled=tf_bool(d.get('dco_is_health_monitoring_enabled', True)),
        dco_is_incident_logs_enabled=tf_bool(d.get('dco_is_incident_logs_enabled', True)),
        cluster_name=d.get('cluster_name', ''),
        timezone=d.get('timezone', ''),
        data_storage_size_in_tbs=ds,
        db_node_storage_size_in_gbs=dng,
        memory_size_in_gbs=mem,
        scan_listener_port_tcp=sc,
        is_local_backup_enabled=tf_bool(d.get('is_local_backup_enabled', False)),
        is_sparse_diskgroup_enabled=tf_bool(d.get('is_sparse_diskgroup_enabled', False)),
        tags=d.get('tags', {}),
    )


def mod3_main(mn, d=None, mn0='', mn1=''):
    ctx = _mod3_ctx(d, mn0, mn1) if d else {'db_servers_mode': 'auto', 'db_servers': [], 'vm_mode': 'arn'}
    return render_tf('aws_vm_cluster/main.tf.j2', module_name=mn, **ctx)


def mod3_vars(mn, d, mn0='', mn1=''):
    return render_tf('aws_vm_cluster/variables.tf.j2', module_name=mn, **_mod3_ctx(d, mn0, mn1))


def mod3_outputs(mn):
    return render_tf('aws_vm_cluster/outputs.tf.j2', module_name=mn)


def mod3_tfvars(mn, d, mn0, mn1):
    return render_tf('aws_vm_cluster/terraform.tfvars.j2', module_name=mn, **_mod3_ctx(d, mn0, mn1, defaults=True))


# ── AWS MODULE 4 — aws_odb_cloud_autonomous_vm_cluster ───────────────────────

# One shared module per pair mode, exactly as modules 0-3: instance values live
# in aws_avmclusters / aws_avmclusters_arn in terraform.auto.tfvars, so adding an
# AVMC never touches main.tf. Two directories rather than one conditional
# argument because the provider accepts the id pair OR the arn pair and rejects a
# config carrying both — a null attribute still counts as present ("either
# odb_network_id & cloud_exadata_infrastructure_id combination or odb_network_arn
# & cloud_exadata_infrastructure_arn combination").
_MOD4      = 'aws-avmcluster'
_MOD4_ARN  = 'aws-avmcluster-arn'


def mod4_main(mn=_MOD4, use_arn_pair=False):
    return render_tf('aws_avmcluster/main.tf.j2', module_name=mn, use_arn_pair=use_arn_pair)


def mod4_vars(mn=_MOD4, use_arn_pair=False):
    return render_tf('aws_avmcluster/variables.tf.j2', module_name=mn, use_arn_pair=use_arn_pair)


def mod4_outputs(mn=_MOD4):
    return render_tf('aws_avmcluster/outputs.tf.j2', module_name=mn)


# ── AWS MODULE 5 — aws_odb_autonomous_database (Serverless) ──────────────────
# ── AWS MODULE 6 — aws_odb_autonomous_database_secrets_manager_integration ───

# Both arrived in hashicorp/aws 6.68.0. The root raises its constraint to that
# only when a config uses one, so every other config generates what it did.
_MOD5 = 'aws-autonomous-db'
_MOD6 = 'aws-adb-secrets-integration'
_AWS_PROVIDER_MIN     = '>= 6.42.0'
_AWS_PROVIDER_MIN_ADB = '>= 6.68.0'

_ADB_WORKLOADS        = ('OLTP', 'LH', 'AJD', 'APEX')
_ADB_PASSWORD_SOURCES = ('write_only', 'secrets_manager')
_ADB_EXTERNAL_ID_TYPES = ('database_ocid', 'compartment_ocid', 'tenant_ocid')


# ── AWS MODULE 7 — aws_ram_resource_share ───────────────────────────────────
# Shares this configuration's own ODB Networks and Exadata Infrastructures. The
# account that applies this root owns what it builds, so the share belongs here.
_MOD7 = 'aws-ram-share'


def _ram_share_module_files() -> dict:
    return {
        f'modules/{_MOD7}/main.tf':      render_tf('aws_ram_resource_share/main.tf.j2'),
        f'modules/{_MOD7}/variables.tf': render_tf('aws_ram_resource_share/variables.tf.j2'),
        f'modules/{_MOD7}/outputs.tf':   render_tf('aws_ram_resource_share/outputs.tf.j2'),
    }


# ── AWS MODULE 8 — TDE master keys in AWS KMS ────────────────────────────────
# Three shared modules, the same files as odb-terraform-blueprints/aws-kms-tde:
# the key, a per-cluster IAM role + KmsTde association, and the key's
# registration in OCI. Emitted only when a config has a KMS key.
_MOD8        = 'aws-kms-key'
_MOD8_ACCESS = 'aws-kms-cluster-access'
_MOD8_OCI    = 'aws-kms-oci-key'
_AWS_PROVIDER_MIN_KMS = '>= 6.61.0'   # aws_odb_iam_role_association
_OCI_PROVIDER_MIN     = '>= 6.0.0'
_OCI_PROVIDER_MIN_KMS = '>= 7.27.0'   # oci_dbmulticloud_oracle_db_aws_key


def _kms_module_files() -> dict:
    files = {}
    for mod, tpl in ((_MOD8, 'aws_kms_key'), (_MOD8_ACCESS, 'aws_kms_cluster_access'),
                     (_MOD8_OCI, 'aws_kms_oci_key')):
        for f in ('main.tf', 'variables.tf', 'outputs.tf'):
            files[f'modules/{mod}/{f}'] = render_tf(f'{tpl}/{f}.j2')
    return files


def _adb_module_files() -> dict:
    return {
        f'modules/{_MOD5}/main.tf':      render_tf('aws_autonomous_db/main.tf.j2'),
        f'modules/{_MOD5}/variables.tf': render_tf('aws_autonomous_db/variables.tf.j2'),
        f'modules/{_MOD5}/outputs.tf':   render_tf('aws_autonomous_db/outputs.tf.j2'),
    }


def _adb_integration_module_files() -> dict:
    return {
        f'modules/{_MOD6}/main.tf':      render_tf('aws_adb_secrets_integration/main.tf.j2'),
        f'modules/{_MOD6}/variables.tf': render_tf('aws_adb_secrets_integration/variables.tf.j2'),
        f'modules/{_MOD6}/outputs.tf':   render_tf('aws_adb_secrets_integration/outputs.tf.j2'),
    }


# ── AWS ROOT ──────────────────────────────────────────────────────────────────

def _infra_id_expr(external_infras, key='each.value.infra_ref'):
    return (f'local.infra_ids[{key}]' if external_infras
            else f'module.aws_exadata_infra[{key}].infra_id')


def _network_id_expr(external_networks, key='each.value.network_ref'):
    return (f'local.odb_network_ids[{key}]' if external_networks
            else f'module.aws_odb_network[{key}].network_id')


def _version_ctx(adbs, adb_integration, iac_tool, kms_keys=()):
    """Provider and core version constraints for the root module.

    Raised only when the config needs them, so a config with no Autonomous
    Database generates byte-identical output. An ADB needs the 6.68.0 provider,
    and its ADMIN password goes through an ephemeral variable into a write-only
    argument: Terraform 1.11 and OpenTofu 1.11 are the first to support both.
    A TDE key needs aws 6.61.0 (the role association) and oci 7.27.0 (the key
    registration); an ADB's higher aws floor wins when both are present.
    """
    if adbs:
        core = '>= 1.11.0'
    else:
        core = '>= 1.6.0' if iac_tool == 'opentofu' else '>= 1.5.0'
    if adbs or adb_integration:
        aws = _AWS_PROVIDER_MIN_ADB
    elif kms_keys:
        aws = _AWS_PROVIDER_MIN_KMS
    else:
        aws = _AWS_PROVIDER_MIN
    return dict(
        aws_provider_version=aws,
        oci_provider_version=_OCI_PROVIDER_MIN_KMS if kms_keys else _OCI_PROVIDER_MIN,
        core_version=core,
    )


def build_root_main(networks, infras, peerings, clusters, avmclusters=None, oci_databases=None, iac_tool='terraform',
                    external_networks=None, external_infras=None, avmclusters_arn=None,
                    adbs=None, adb_integration=False, ram_shares=None, kms_keys=None, kms=None):
    aws_region = 'us-east-1'
    for n in (networks or []):
        if n.get('region'): aws_region = n['region']; break
    oci_region = _oci_region_for(aws_region)
    external_networks = external_networks or []
    external_infras   = external_infras or []
    return render_tf('aws_root/main.tf.j2',
        networks=networks, infras=infras, peerings=peerings,
        clusters=clusters, avmclusters=avmclusters or [],
        avmclusters_arn=avmclusters_arn or [],
        oci_databases=oci_databases or [],
        oci_region=oci_region,
        external_networks=external_networks, external_infras=external_infras,
        infra_id_expr=_infra_id_expr(external_infras),
        network_id_expr=_network_id_expr(external_networks),
        adbs=adbs or [], adb_integration=adb_integration, ram_shares=ram_shares or [],
        kms_keys=kms_keys or [], kms=kms or {},
        iac_tool=iac_tool, **_version_ctx(adbs, adb_integration, iac_tool, kms_keys))


def build_root_vars(networks, infras, peerings, clusters, avmclusters=None, oci_databases=None,
                    external_networks=None, external_infras=None, avmclusters_arn=None,
                    adbs=None, ram_shares=None, kms_keys=None):
    aws_region = 'us-east-1'
    for n in (networks or []):
        if n.get('region'): aws_region = n['region']; break
    oci_region = _oci_region_for(aws_region)
    return render_tf('aws_root/variables.tf.j2', kms_keys=kms_keys or [],
        aws_region=aws_region, oci_region=oci_region,
        networks=networks, infras=infras, peerings=peerings,
        clusters=clusters, avmclusters=avmclusters or [],
        avmclusters_arn=avmclusters_arn or [],
        external_networks=external_networks or [], external_infras=external_infras or [],
        oci_databases=oci_databases or [], adbs=adbs or [], ram_shares=ram_shares or [])


def build_readme(networks, infras, peerings, clusters, avmclusters=None, oci_databases=None, iac_tool='terraform',
                 customer_name='', avmclusters_arn=None, adbs=None, adb_integration=False,
                 ram_shares=None, kms_keys=None, kms=None):
    avmclusters = avmclusters or []
    aws_region = 'us-east-1'
    oci_region = 'us-ashburn-1'
    for n in (networks or []):
        if n.get('region'): aws_region = n['region']; break
    oci_region = _oci_region_for(aws_region)
    return render_tf('aws_root/README.md.j2',
        aws_region=aws_region, oci_region=oci_region,
        networks=networks, infras=infras, peerings=peerings,
        clusters=clusters, avmclusters=avmclusters,
        avmclusters_arn=avmclusters_arn or [],
        oci_databases=oci_databases or [],
        iac_tool=iac_tool,
        customer_name=customer_name,
        adbs=adbs or [], adb_integration=adb_integration, ram_shares=ram_shares or [],
        kms_keys=kms_keys or [], kms=kms or {},
        **_version_ctx(adbs, adb_integration, iac_tool, kms_keys),
        generated_date=datetime.date.today().isoformat())


def build_root_tfvars(networks, infras, peerings, clusters, avmclusters=None, iac_tool='terraform',
                      external_networks=None, external_infras=None, avmclusters_arn=None,
                      adbs=None, ram_shares=None, kms_keys=None, kms=None):
    avmclusters = avmclusters or []
    adbs = adbs or []
    avmclusters_arn = avmclusters_arn or []
    all_tags = {}
    for items in [networks, infras, peerings, clusters, avmclusters, avmclusters_arn, adbs]:
        for item in items:
            all_tags.update(item.get('tags', {}))
    # Networks first, then infras - and stop at the first hit. The inner
    # `break` used to leave the outer loop running, so an infra's region
    # overwrote the network's and tfvars disagreed with main.tf and the README.
    region = next((i['region'] for i in [*networks, *infras] if i.get('region')),
                  'us-east-1')
    return render_tf('aws_root/terraform.tfvars.j2',
        aws_region=region,
        networks=networks, infras=infras, peerings=peerings,
        clusters=clusters, avmclusters=avmclusters,
        avmclusters_arn=avmclusters_arn, adbs=adbs, ram_shares=ram_shares or [],
        kms_keys=kms_keys or [], kms_lines=_kms_settings_tfvars(kms) if kms_keys else [],
        external_networks=external_networks or [], external_infras=external_infras or [],
        tags=all_tags if all_tags else {'ManagedBy': 'Terraform'},
    )


# ── Default normalizers ───────────────────────────────────────────────────────

def _is_external(d) -> bool:
    """True when the user flagged this network/infra as provisioned elsewhere.

    External entries are dropped from the aws_networks / aws_infras maps (so
    Terraform creates nothing) and surface as existing_*_ids instead, keyed by
    the same module name the clusters and peerings already reference."""
    return bool(d.get('is_existing'))


#: Optional ODB-network attributes that share one alignment run in tfvars.
#: terraform fmt pads a run to its own longest key, so the width depends on
#: which of these the config actually sets - hence computing it here rather
#: than hardcoding a column in the template.
_NET_OPT_KEYS = ('sts_access', 'kms_access', 's3_policy_document',
                 'sts_policy_document', 'kms_policy_document')


def _aws_net_defaults(d):
    cdn = d.get('custom_domain_name', '')
    out = {**d,
        'is_existing': bool(d.get('is_existing', False)),
        'existing_id': d.get('existing_id') or ('CHANGEME' if d.get('is_existing') else ''),
        'existing_arn': d.get('existing_arn', ''),
        'display_name': d.get('display_name') or 'odb-network',
        'availability_zone_id': d.get('availability_zone_id') or _default_az(d.get('region')),
        'client_subnet_cidr': d.get('client_subnet_cidr') or '10.2.0.0/24',
        'backup_subnet_cidr': d.get('backup_subnet_cidr') or '10.2.1.0/24',
        's3_access': 'ENABLED' if d.get('s3_access') else 'DISABLED',
        'zero_etl_access': 'ENABLED' if d.get('zero_etl_access') else 'DISABLED',
        # Optional + Computed in the provider, so each is emitted only when set.
        'sts_access': _opt_access(d.get('sts_access')),
        'kms_access': _opt_access(d.get('kms_access')),
        # Endpoint policies: JSON documents, emitted as heredocs when present.
        's3_policy_document': (d.get('s3_policy_document') or '').strip(),
        'sts_policy_document': (d.get('sts_policy_document') or '').strip(),
        'kms_policy_document': (d.get('kms_policy_document') or '').strip(),
        'cross_region_s3_restore_sources_access':
            _strs(d.get('cross_region_s3_restore_sources_access')),
        'region': d.get('region', ''),
        'availability_zone': d.get('availability_zone', ''),
        'custom_domain_name': cdn,
        'default_dns_prefix': '' if cdn else d.get('default_dns_prefix', ''),
        'delete_associated_resources': bool(d.get('delete_associated_resources', False)),
    }
    # Width of the optional-attribute run, so the tfvars it renders is already
    # what `terraform fmt` would produce.
    out['opt_pad'] = max((len(k) for k in _NET_OPT_KEYS if out.get(k)), default=0)
    return out


def _aws_infra_defaults(d):
    return {**d,
        'is_existing': bool(d.get('is_existing', False)),
        'existing_id': d.get('existing_id') or ('CHANGEME' if d.get('is_existing') else ''),
        'existing_arn': d.get('existing_arn', ''),
        'display_name': d.get('display_name') or 'odb-exadata-infra',
        'shape': d.get('shape') or shapes.default_shape('aws'),
        'compute_count': int(d.get('compute_count') or 2),
        'storage_count': int(d.get('storage_count') or 3),
        'availability_zone_id': d.get('availability_zone_id') or _default_az(d.get('region')),
        'region': d.get('region', ''),
        'availability_zone': d.get('availability_zone', ''),
        'mw_preference': d.get('mw_preference') or 'NO_PREFERENCE',
        'mw_patching_mode': d.get('mw_patching_mode') or 'ROLLING',
    }


def _aws_peer_defaults(d, first_network_name=''):
    return {**d,
        'display_name': d.get('display_name') or 'odb-peering',
        'peer_network_id': d.get('peer_network_id') or 'vpc-CHANGEME',
        'network_ref': d.get('network_ref') or first_network_name,
        'region': d.get('region', ''),
    }


def _aws_cluster_defaults(d, first_network_name='', first_infra_name=''):
    return {**d,
        'display_name': d.get('display_name') or 'odb-vm-cluster',
        'cpu_core_count': int(d.get('cpu_core_count') or 16),
        'gi_version': d.get('gi_version') or '23.0.0.0',
        'hostname_prefix': d.get('hostname_prefix') or 'vm',
        'license_model': d.get('license_model') or 'LICENSE_INCLUDED',
        'ssh_public_keys': d.get('ssh_public_keys') or [],
        'db_servers': d.get('db_servers') or [],
        'db_servers_mode': d.get('db_servers_mode') or 'auto',
        'vm_mode': d.get('vm_mode') or 'arn',
        'network_ref': d.get('network_ref') or first_network_name,
        'infra_ref': d.get('infra_ref') or first_infra_name,
        # Optional attributes — the root module and aws-vm-cluster module already
        # accept all of these, so they must reach terraform.auto.tfvars or the
        # form values silently fall back to the optional() defaults.
        'dco_is_diagnostics_events_enabled': bool(d.get('dco_is_diagnostics_events_enabled', True)),
        'dco_is_health_monitoring_enabled': bool(d.get('dco_is_health_monitoring_enabled', True)),
        'dco_is_incident_logs_enabled': bool(d.get('dco_is_incident_logs_enabled', True)),
        'cluster_name': d.get('cluster_name') or '',
        'timezone': d.get('timezone') or '',
        'data_storage_size_in_tbs': tf_num(d.get('data_storage_size_in_tbs')),
        'db_node_storage_size_in_gbs': tf_num(d.get('db_node_storage_size_in_gbs')),
        'memory_size_in_gbs': tf_num(d.get('memory_size_in_gbs')),
        'scan_listener_port_tcp': tf_num(d.get('scan_listener_port_tcp')),
        'is_local_backup_enabled': bool(d.get('is_local_backup_enabled', False)),
        'is_sparse_diskgroup_enabled': bool(d.get('is_sparse_diskgroup_enabled', False)),
    }


def _ints(v):
    """Form values arrive as '4, 16' or a list; keep only what HCL can take as a number."""
    raw = v if isinstance(v, list) else parse_list(v or '')
    return [int(x) for x in raw if str(x).strip().lstrip('-').isdigit()]


def _strs(v):
    return v if isinstance(v, list) else parse_list(v or '')


def _aws_avmc_defaults(d, first_network_name='', first_infra_name=''):
    # Both arns present means the instance is served by the arn-pair module; the
    # provider rejects a config that carries the id pair as well.
    infra_arn = d.get('cloud_exadata_infrastructure_arn') or ''
    net_arn   = d.get('odb_network_arn') or ''
    return {**d,
        'display_name': d.get('display_name') or 'odb-avmc',
        'autonomous_data_storage_size_in_tbs': float(d.get('autonomous_data_storage_size_in_tbs') or 5),
        'cpu_core_count_per_node': int(d.get('cpu_core_count_per_node') or 40),
        'memory_per_oracle_compute_unit_in_gbs': int(d.get('memory_per_oracle_compute_unit_in_gbs') or 2),
        'total_container_databases': int(d.get('total_container_databases') or 2),
        'scan_listener_port_non_tls': int(d.get('scan_listener_port_non_tls') or 1521),
        'scan_listener_port_tls': int(d.get('scan_listener_port_tls') or 2484),
        'license_model': d.get('license_model') or 'LICENSE_INCLUDED',
        'is_mtls_enabled_vm_cluster': bool(d.get('is_mtls_enabled_vm_cluster', False)),
        'db_servers': d.get('db_servers') or [],
        'db_servers_mode': d.get('db_servers_mode') or 'auto',
        'network_ref': d.get('network_ref') or first_network_name,
        'infra_ref': d.get('infra_ref') or first_infra_name,
        'cloud_exadata_infrastructure_arn': infra_arn,
        'odb_network_arn': net_arn,
        'use_arn_pair': bool(infra_arn and net_arn),
        'description': d.get('description') or '',
        'time_zone': d.get('time_zone') or '',
        'mw_preference': d.get('mw_preference') or 'NO_PREFERENCE',
        'mw_patching_mode': d.get('mw_patching_mode') or 'ROLLING',
        'mw_is_custom_action_timeout_enabled': bool(d.get('mw_is_custom_action_timeout_enabled', False)),
        'mw_custom_action_timeout_mins': int(d.get('mw_custom_action_timeout_mins') or 15),
        # Schedule fields reach terraform.auto.tfvars now — before the split they
        # were read for a has-schedule flag and then dropped on the floor.
        'mw_lead_time_in_weeks': int(d.get('mw_lead_time_in_weeks') or 0),
        'mw_days_of_week': _strs(d.get('mw_days_of_week')),
        'mw_months': _strs(d.get('mw_months')),
        'mw_hours_of_day': _ints(d.get('mw_hours_of_day')),
        'mw_weeks_of_month': _ints(d.get('mw_weeks_of_month')),
    }


def _aws_ram_share_defaults(d, net_names=(), infra_names=()):
    """One RAM share: which of this config's networks / infras, shared with whom.

    A ref naming a network or infra this config does not have is dropped rather
    than retargeted — silently sharing a *different* resource with another
    account is worse than sharing one fewer.
    """
    mn = d.get('module_name') or 'odb_ram_share'
    return {**d,
        'module_name': mn,
        'name': (d.get('name') or '').strip() or mn.replace('_', '-'),
        'network_refs': [r for r in _strs(d.get('network_refs')) if r in net_names],
        'infra_refs': [r for r in _strs(d.get('infra_refs')) if r in infra_names],
        'resource_arns': _strs(d.get('resource_arns')),
        'principals': _strs(d.get('principals')),
        'allow_external_principals': bool(d.get('allow_external_principals', False)),
    }


def _ram_share_tfvars(r):
    run = [('name', r['name']), ('principals', r['principals'])]
    run += [(k, r[k]) for k in ('network_refs', 'infra_refs', 'resource_arns') if r[k]]
    if r['allow_external_principals']:
        run.append(('allow_external_principals', True))
    return _tfvars_runs([run])


def _aws_kms_key_defaults(d, cluster_names=()):
    """One TDE key: created (or adopted by ARN) and given to these clusters.

    Like a RAM share, a cluster_ref naming a cluster this config does not have
    is dropped, not retargeted - handing a key to a different cluster than the
    one picked is worse than one fewer. register_via must be one of the key's
    own clusters; anything else falls back to blank, which the root resolves
    to the first.
    """
    mn = d.get('module_name') or 'tde_key'
    refs = [r for r in _strs(d.get('cluster_refs')) if r in cluster_names]
    via = (d.get('register_via') or '').strip()
    try:
        window = int(d.get('deletion_window_in_days') or 30)
    except (TypeError, ValueError):
        window = 30
    return {**d,
        'module_name': mn,
        'alias': (d.get('alias') or '').strip() or 'alias/oracle-tde-' + mn.replace('_', '-'),
        'existing_arn': (d.get('existing_arn') or '').strip(),
        'cluster_refs': refs,
        'multi_region': bool(d.get('multi_region', False)),
        'enable_key_rotation': bool(d.get('enable_key_rotation', False)),
        'deletion_window_in_days': window,
        'oci_compartment_id': (d.get('oci_compartment_id') or '').strip(),
        'register_via': via if via in refs else '',
    }


def _kms_key_tfvars(k):
    run = [('cluster_refs', k['cluster_refs'])]
    if k['existing_arn']:
        run.append(('existing_arn', k['existing_arn']))
    else:
        run.append(('alias', k['alias']))
        if k['deletion_window_in_days'] != 30:
            run.append(('deletion_window_in_days', k['deletion_window_in_days']))
        if k['multi_region']:
            run.append(('multi_region', True))
        if k['enable_key_rotation']:
            run.append(('enable_key_rotation', True))
    opt = [(f, k[f]) for f in ('oci_compartment_id', 'register_via') if k[f]]
    return _tfvars_runs([run, opt])


def _aws_kms_settings(d):
    """Page-level settings shared by every TDE key: the OIDC provider the
    cluster roles trust (reused by ARN, or created from the identity domain
    URL), the token audience, role isolation, and the compartment the OCI
    key-read policy goes in (blank: not created)."""
    d = d or {}
    mode = d.get('oidc_mode') if d.get('oidc_mode') in ('existing', 'create') else 'existing'
    return {
        'oidc_mode': mode,
        'oidc_provider_arn': (d.get('oidc_provider_arn') or '').strip() if mode == 'existing' else '',
        'oidc_provider_url': (d.get('oidc_provider_url') or '').strip().rstrip('/') if mode == 'create' else '',
        'oidc_audience': (d.get('oidc_audience') or '').strip(),
        'isolate_role_to_cluster': d.get('isolate_role_to_cluster', True) is not False,
        'oci_policy_compartment_id': (d.get('oci_policy_compartment_id') or '').strip(),
    }


def _kms_settings_tfvars(kms):
    if kms['oidc_mode'] == 'existing':
        run = [('aws_kms_oidc_provider_arn', kms['oidc_provider_arn'])]
    else:
        run = [('aws_kms_oidc_provider_url', kms['oidc_provider_url'])]
    if kms['oidc_audience']:
        run.append(('aws_kms_oidc_audience', kms['oidc_audience']))
    if not kms['isolate_role_to_cluster']:
        run.append(('aws_kms_isolate_role_to_cluster', False))
    if kms['oci_policy_compartment_id']:
        run.append(('aws_kms_oci_policy_compartment_id', kms['oci_policy_compartment_id']))
    return _tfvars_runs([run])


def _tristate(v):
    """True / False / None for an Optional + Computed bool.

    None is "not set", which leaves the value to the service. The card sends
    '' for that, so it must not collapse to False the way bool('') would.
    """
    if v in (None, ''):
        return None
    if isinstance(v, str):
        return {'true': True, 'false': False}.get(v.strip().lower())
    return bool(v)


def _adb_db_name(display_name):
    """An Oracle DB name from the display name: a letter first, alphanumeric, max 30."""
    s = ''.join(c for c in display_name if c.isalnum())
    s = s.lstrip('0123456789')
    return (s or 'ADB')[:30].upper()


def _hcl_value(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return '[' + ', '.join(_hcl_value(x) for x in v) + ']'
    return json.dumps(str(v))


def _tfvars_runs(runs):
    """Lines for one tfvars entry, already in `terraform fmt` form.

    fmt pads each run of arguments to that run's own longest key, and a blank
    line ends a run. Which optional keys an ADB sets varies, so the width is
    computed per run here — the same reason _aws_net_defaults computes opt_pad.
    Empty runs are dropped, so no stray blank lines appear.
    """
    lines = []
    for run in (r for r in runs if r):
        if lines:
            lines.append('')
        pad = max(len(k) for k, _ in run)
        lines.extend(f'{k.ljust(pad)} = {_hcl_value(v)}' for k, v in run)
    return lines


def _aws_adb_defaults(d, first_network_name=''):
    """Autonomous Database Serverless.

    No infra_ref: Oracle runs the Exadata fleet, so the only thing an ADB-S
    needs from this configuration is the ODB Network. Optional + Computed
    arguments stay None when unset and are left out of tfvars entirely, so the
    service's own value is adopted rather than overwritten by a guess.
    """
    display_name = d.get('display_name') or 'odb-adb'
    source = d.get('admin_password_source') or 'write_only'
    out = {**d,
        'display_name': display_name,
        'db_name': d.get('db_name') or _adb_db_name(display_name),
        'network_ref': d.get('network_ref') or first_network_name,
        'db_workload': d.get('db_workload') or 'OLTP',
        'license_model': d.get('license_model') or 'LICENSE_INCLUDED',
        'compute_count': tf_num(d.get('compute_count')) or 2,
        'data_storage_size_in_tbs': tf_num(d.get('data_storage_size_in_tbs')) or 1,
        'admin_password_source': source,
        'admin_password_wo_version': tf_num(d.get('admin_password_wo_version')) or 1,
        'secret_arn': (d.get('secret_arn') or '').strip(),
        'secret_iam_role_arn': (d.get('secret_iam_role_arn') or '').strip(),
        'secret_external_id_type': d.get('secret_external_id_type') or 'compartment_ocid',
        # Optional + Computed — None means "leave it to the service".
        'database_edition': d.get('database_edition') or None,
        'db_version': (d.get('db_version') or '').strip() or None,
        'is_auto_scaling_enabled': _tristate(d.get('is_auto_scaling_enabled')),
        'is_auto_scaling_for_storage_enabled': _tristate(d.get('is_auto_scaling_for_storage_enabled')),
        'backup_retention_period_in_days': tf_num(d.get('backup_retention_period_in_days')),
        'autonomous_maintenance_schedule_type': d.get('autonomous_maintenance_schedule_type') or None,
        'is_mtls_connection_required': _tristate(d.get('is_mtls_connection_required')),
        'private_endpoint_label': (d.get('private_endpoint_label') or '').strip() or None,
        'private_endpoint_ip': (d.get('private_endpoint_ip') or '').strip() or None,
        'allowlisted_ips': _strs(d.get('allowlisted_ips')),
        'character_set': (d.get('character_set') or '').strip() or None,
        'ncharacter_set': (d.get('ncharacter_set') or '').strip() or None,
        'encryption_key_provider': d.get('encryption_key_provider') or None,
        'kms_key_id': (d.get('kms_key_id') or '').strip() or None,
        'customer_contacts': _strs(d.get('customer_contacts')),
    }
    base = [(k, out[k]) for k in ('display_name', 'db_name', 'network_ref', 'db_workload',
                                  'license_model', 'compute_count', 'data_storage_size_in_tbs')]
    optional = [(k, out[k]) for k in (
        'database_edition', 'db_version', 'is_auto_scaling_enabled',
        'is_auto_scaling_for_storage_enabled', 'backup_retention_period_in_days',
        'autonomous_maintenance_schedule_type', 'is_mtls_connection_required',
        'private_endpoint_label', 'private_endpoint_ip', 'allowlisted_ips',
        'character_set', 'ncharacter_set', 'encryption_key_provider', 'kms_key_id',
        'customer_contacts') if out[k] not in (None, [])]
    password = [('admin_password_source', source)]
    if source == 'secrets_manager':
        password += [('secret_arn', out['secret_arn'] or 'CHANGEME'),
                     ('secret_iam_role_arn', out['secret_iam_role_arn'] or 'CHANGEME'),
                     ('secret_external_id_type', out['secret_external_id_type'])]
    else:
        password += [('admin_password_wo_version', out['admin_password_wo_version'])]
    out['tfvars_lines'] = _tfvars_runs([base, optional, password])
    return out


# ── CloudFormation generator ──────────────────────────────────────────────────

def _pascal(s: str) -> str:
    return ''.join(p.capitalize() for p in re.split(r'[_\-\s]+', s) if p)


def _cfn_str(v) -> str:
    s = str(v)
    if any(c in s for c in ':{}[]|>&*!,#?@`"\'\n') or s in ('true', 'false', 'null', '~') or s == '':
        return "'" + s.replace("'", "''") + "'"
    return s


def generate_cfn(data: dict) -> str:
    raw_nets     = data.get('aws_networks', [])
    raw_infras   = data.get('aws_infras', [])
    raw_peerings = data.get('aws_peerings', [])
    raw_clusters = data.get('aws_clusters', [])
    raw_avmc     = data.get('aws_avmclusters', [])

    if not raw_nets:
        mn0 = data.get('module_names', {}).get('0', 'odb_network')
        raw_nets = [{**data.get('module_0', {}), 'module_name': mn0}]
    if not raw_infras:
        mn1 = data.get('module_names', {}).get('1', 'odb_exadata_infra')
        raw_infras = [{**data.get('module_1', {}), 'module_name': mn1}]
    if not raw_peerings:
        mn2 = data.get('module_names', {}).get('2', 'odb_peering')
        raw_peerings = [{**data.get('module_2', {}), 'module_name': mn2}]
    if not raw_clusters and data.get('module_3'):
        mn3 = data.get('module_names', {}).get('3', 'odb_vm_cluster')
        raw_clusters = [{**data['module_3'], 'module_name': mn3}]

    first_net_name = raw_nets[0].get('module_name', 'odb_network') if raw_nets else 'odb_network'
    first_inf_name = raw_infras[0].get('module_name', 'odb_exadata_infra') if raw_infras else 'odb_exadata_infra'

    networks    = [_aws_net_defaults(n) for n in raw_nets]
    infras      = [_aws_infra_defaults(i) for i in raw_infras]
    peerings    = [_aws_peer_defaults(p, first_net_name) for p in raw_peerings]
    clusters    = [_aws_cluster_defaults(c, first_net_name, first_inf_name) for c in raw_clusters]
    avmclusters = [_aws_avmc_defaults(a, first_net_name, first_inf_name) for a in raw_avmc if _avmc_filled(a)]

    L = []
    out = []

    def line(s=''):
        L.append(s)

    line("AWSTemplateFormatVersion: '2010-09-09'")
    line("Description: 'ODB@AWS stack generated by Terraflow Studio'")
    line()
    line("Resources:")

    for net in networks:
        lid = _pascal(net['module_name'])
        line()
        line(f"  # ODB Network: {net['module_name']}")
        line(f"  {lid}:")
        line(f"    Type: AWS::ODB::OdbNetwork")
        line(f"    Properties:")
        line(f"      DisplayName: {_cfn_str(net['display_name'])}")
        if net.get('availability_zone_id'):
            line(f"      AvailabilityZoneId: {_cfn_str(net['availability_zone_id'])}")
        line(f"      ClientSubnetCidr: {_cfn_str(net['client_subnet_cidr'])}")
        line(f"      BackupSubnetCidr: {_cfn_str(net['backup_subnet_cidr'])}")
        line(f"      S3Access: {net['s3_access']}")
        line(f"      ZeroEtlAccess: {net['zero_etl_access']}")
        if net.get('default_dns_prefix'):
            line(f"      DefaultDnsPrefix: {_cfn_str(net['default_dns_prefix'])}")
        if net.get('custom_domain_name'):
            line(f"      CustomDomainName: {_cfn_str(net['custom_domain_name'])}")
        line(f"      DeleteAssociatedResources: true")
        out.append((f"{lid}OdbNetworkId", lid, "OdbNetworkId"))

    for inf in infras:
        lid = _pascal(inf['module_name'])
        line()
        line(f"  # Exadata Infrastructure: {inf['module_name']}")
        line(f"  {lid}:")
        line(f"    Type: AWS::ODB::CloudExadataInfrastructure")
        line(f"    Properties:")
        line(f"      DisplayName: {_cfn_str(inf['display_name'])}")
        if inf.get('availability_zone_id'):
            line(f"      AvailabilityZoneId: {_cfn_str(inf['availability_zone_id'])}")
        line(f"      Shape: {_cfn_str(inf['shape'])}")
        line(f"      ComputeCount: {inf['compute_count']}")
        line(f"      StorageCount: {inf['storage_count']}")
        out.append((f"{lid}InfraId", lid, "CloudExadataInfrastructureId"))

    for peer in peerings:
        lid     = _pascal(peer['module_name'])
        net_lid = _pascal(peer.get('network_ref', first_net_name))
        line()
        line(f"  # ODB Peering Connection: {peer['module_name']}")
        line(f"  {lid}:")
        line(f"    Type: AWS::ODB::OdbPeeringConnection")
        line(f"    DependsOn: {net_lid}")
        line(f"    Properties:")
        line(f"      DisplayName: {_cfn_str(peer['display_name'])}")
        line(f"      OdbNetworkId: !GetAtt {net_lid}.OdbNetworkId")
        line(f"      PeerNetworkId: {_cfn_str(peer['peer_network_id'])}")
        out.append((f"{lid}PeeringId", lid, "OdbPeeringConnectionId"))

    for cl in clusters:
        lid     = _pascal(cl['module_name'])
        net_lid = _pascal(cl.get('network_ref', first_net_name))
        inf_lid = _pascal(cl.get('infra_ref', first_inf_name))
        line()
        line(f"  # VM Cluster: {cl['module_name']}")
        line(f"  {lid}:")
        line(f"    Type: AWS::ODB::CloudVmCluster")
        line(f"    DependsOn:")
        line(f"      - {net_lid}")
        line(f"      - {inf_lid}")
        line(f"    Properties:")
        line(f"      DisplayName: {_cfn_str(cl['display_name'])}")
        line(f"      OdbNetworkId: !GetAtt {net_lid}.OdbNetworkId")
        line(f"      CloudExadataInfrastructureId: !GetAtt {inf_lid}.CloudExadataInfrastructureId")
        if cl.get('hostname_prefix'):
            line(f"      Hostname: {_cfn_str(cl['hostname_prefix'])}")
        line(f"      GiVersion: {_cfn_str(cl.get('gi_version', '23.0.0.0'))}")
        line(f"      CpuCoreCount: {cl['cpu_core_count']}")
        mem = cl.get('memory_size_in_gbs') or ''
        if mem and str(mem) not in ('null', '0', ''):
            line(f"      MemorySizeInGBs: {mem}")
        ds = cl.get('data_storage_size_in_tbs') or ''
        if ds and str(ds) not in ('null', '0', ''):
            line(f"      DataStorageSizeInTBs: {ds}")
        dng = cl.get('db_node_storage_size_in_gbs') or ''
        if dng and str(dng) not in ('null', '0', ''):
            line(f"      DbNodeStorageSizeInGBs: {dng}")
        line(f"      LicenseModel: {cl['license_model']}")
        keys = cl.get('ssh_public_keys') or []
        if keys:
            line(f"      SshPublicKeys:")
            for k in keys:
                line(f"        - {_cfn_str(k)}")
        db_servers = cl.get('db_servers') or []
        if db_servers and cl.get('db_servers_mode') != 'auto':
            line(f"      DbServers:")
            for s in db_servers:
                line(f"        - {_cfn_str(s)}")
        out.append((f"{lid}VmClusterId", lid, "CloudVmClusterId"))

    for av in avmclusters:
        lid     = _pascal(av['module_name'])
        net_lid = _pascal(av.get('network_ref', first_net_name))
        inf_lid = _pascal(av.get('infra_ref', first_inf_name))
        line()
        line(f"  # Autonomous VM Cluster: {av['module_name']}")
        line(f"  {lid}:")
        line(f"    Type: AWS::ODB::CloudAutonomousVmCluster")
        line(f"    DependsOn:")
        line(f"      - {net_lid}")
        line(f"      - {inf_lid}")
        line(f"    Properties:")
        line(f"      DisplayName: {_cfn_str(av['display_name'])}")
        line(f"      OdbNetworkId: !GetAtt {net_lid}.OdbNetworkId")
        line(f"      CloudExadataInfrastructureId: !GetAtt {inf_lid}.CloudExadataInfrastructureId")
        line(f"      AutonomousDataStorageSizeInTBs: {av['autonomous_data_storage_size_in_tbs']}")
        line(f"      CpuCoreCountPerNode: {av['cpu_core_count_per_node']}")
        line(f"      MemoryPerOracleComputeUnitInGBs: {av['memory_per_oracle_compute_unit_in_gbs']}")
        line(f"      TotalContainerDatabases: {av['total_container_databases']}")
        line(f"      LicenseModel: {av['license_model']}")
        line(f"      IsMtlsEnabledVmCluster: {'true' if av['is_mtls_enabled_vm_cluster'] else 'false'}")
        if av.get('time_zone'):
            line(f"      TimeZone: {_cfn_str(av['time_zone'])}")
        if av.get('description'):
            line(f"      Description: {_cfn_str(av['description'])}")
        out.append((f"{lid}AvmClusterId", lid, "CloudAutonomousVmClusterId"))

    if out:
        line()
        line("Outputs:")
        for (out_key, lid, attr) in out:
            line()
            line(f"  {out_key}:")
            line(f"    Value: !GetAtt {lid}.{attr}")
            line(f"    Export:")
            line(f"      Name: !Sub '${{AWS::StackName}}-{out_key}'")

    return '\n'.join(L) + '\n'


# ── AWS Terraform generator ───────────────────────────────────────────────────

def generate_aws_tf(data: dict) -> dict:
    raw_nets     = data.get('aws_networks', [])
    raw_infras   = data.get('aws_infras', [])
    raw_peerings = data.get('aws_peerings', [])
    raw_clusters = data.get('aws_clusters', [])
    raw_avmc     = data.get('aws_avmclusters', [])

    if not raw_nets:
        d0 = data.get('module_0', {})
        mn0 = data.get('module_names', {}).get('0', 'odb_network')
        raw_nets = [{**d0, 'module_name': mn0}]
    # An infra or peering is invented only when the payload predates the list
    # keys (absent, or a legacy module_N config). An explicit empty list is a
    # choice: a Serverless-only deployment has no Exadata Infrastructure, and
    # inventing one generated an X11M — and a peering to vpc-CHANGEME — beside
    # the database, which a plain `terraform apply` would have created.
    if not raw_infras and ('aws_infras' not in data or data.get('module_1')):
        d1 = data.get('module_1', {})
        mn1 = data.get('module_names', {}).get('1', 'odb_exadata_infra')
        raw_infras = [{**d1, 'module_name': mn1}]
    if not raw_peerings and ('aws_peerings' not in data or data.get('module_2')):
        d2 = data.get('module_2', {})
        mn2 = data.get('module_names', {}).get('2', 'odb_peering')
        raw_peerings = [{**d2, 'module_name': mn2}]
    # Only the legacy single-instance shim, never an invention: a payload with no
    # clusters means no clusters. The shim fires solely for configs saved before
    # the UI supported multiple instances, which stored one per module_N key.
    if not raw_clusters and data.get('module_3'):
        d3 = data['module_3']
        mn3 = data.get('module_names', {}).get('3', 'odb_vm_cluster')
        raw_clusters = [{**d3, 'module_name': mn3}]

    first_net_name  = raw_nets[0].get('module_name', 'odb_network')
    first_inf_name  = raw_infras[0].get('module_name', 'odb_exadata_infra') if raw_infras else ''
    all_networks = [_aws_net_defaults(n) for n in raw_nets]
    all_infras   = [_aws_infra_defaults(i) for i in raw_infras]
    # Externally provisioned entries create nothing; they only contribute an ID
    # under their module name. Refs (infra_ref / network_ref) are unaffected.
    external_networks = [n for n in all_networks if _is_external(n)]
    external_infras   = [i for i in all_infras   if _is_external(i)]
    networks    = [n for n in all_networks if not _is_external(n)]
    infras      = [i for i in all_infras   if not _is_external(i)]
    peerings    = [_aws_peer_defaults(p, first_net_name) for p in raw_peerings]
    clusters    = [_aws_cluster_defaults(c, first_net_name, first_inf_name) for c in raw_clusters]
    all_avmc    = [_aws_avmc_defaults(a, first_net_name, first_inf_name) for a in raw_avmc if _avmc_filled(a)]
    # Two maps, two modules: an instance naming its infra and network by ARN
    # cannot also carry the id pair, so it is served separately.
    avmclusters     = [a for a in all_avmc if not a['use_arn_pair']]
    avmclusters_arn = [a for a in all_avmc if a['use_arn_pair']]

    raw_oci_dbs   = [db for db in data.get('aws_oci_databases', []) if _ocidb_filled(db)]
    first_cl_name = clusters[0]['module_name'] if clusters else (all_avmc[0]['module_name'] if all_avmc else '')
    oci_dbs = [_oci_db_defaults(db, first_cl_name) for db in raw_oci_dbs]

    # An ADB-S resolves its network through the same keyspace as the clusters,
    # managed or external. A network_ref naming neither fails at apply on a
    # missing map key, so it is retargeted to the first network instead.
    net_names = [n['module_name'] for n in all_networks]
    adbs = []
    for a in data.get('aws_autonomous_dbs') or []:
        adb = _aws_adb_defaults(a, first_net_name)
        if adb['network_ref'] not in net_names:
            adb = _aws_adb_defaults({**a, 'network_ref': first_net_name}, first_net_name)
        adbs.append(adb)
    adb_integration = bool(data.get('aws_adb_secrets_integration'))

    # A share names networks / infras by the same keys the clusters use, managed
    # or external — an external one is shareable only if its ARN was given.
    infra_names = [i['module_name'] for i in all_infras]
    ram_shares = [_aws_ram_share_defaults(r, net_names, infra_names)
                  for r in data.get('aws_ram_shares') or []]
    for r in ram_shares:
        r['tfvars_lines'] = _ram_share_tfvars(r)

    # TDE keys hand this config's own VM clusters a KMS key; the cluster ARN and
    # OCID come from module.aws_vm_cluster, so nothing is pasted after apply.
    cluster_names = [c['module_name'] for c in clusters]
    kms_keys = [_aws_kms_key_defaults(k, cluster_names) for k in data.get('aws_kms_keys') or []]
    for k in kms_keys:
        k['tfvars_lines'] = _kms_key_tfvars(k)
    kms = _aws_kms_settings(data.get('aws_kms_tde'))

    iac_tool = data.get('iac_tool', 'terraform')

    customer_name = data.get('customer_name', '')
    adb_ctx = dict(adbs=adbs, adb_integration=adb_integration, ram_shares=ram_shares,
                   kms_keys=kms_keys, kms=kms)
    files = {
        'main.tf':          build_root_main(networks, infras, peerings, clusters, avmclusters, oci_dbs, iac_tool,
                                              external_networks, external_infras, avmclusters_arn, **adb_ctx),
        'variables.tf':     build_root_vars(networks, infras, peerings, clusters, avmclusters, oci_dbs,
                                            external_networks, external_infras, avmclusters_arn, adbs=adbs,
                                            ram_shares=ram_shares, kms_keys=kms_keys),
        'terraform.auto.tfvars': build_root_tfvars(networks, infras, peerings, clusters, avmclusters, iac_tool,
                                                   external_networks, external_infras, avmclusters_arn, adbs=adbs,
                                                   ram_shares=ram_shares, kms_keys=kms_keys, kms=kms),
        'README.md':        build_readme(networks, infras, peerings, clusters, avmclusters, oci_dbs, iac_tool,
                                         customer_name, avmclusters_arn, **adb_ctx),
    }
    # Shared static modules — one directory per resource type regardless of instance count
    files['modules/aws-odb-network/main.tf']      = mod0_main('aws-odb-network', {})
    files['modules/aws-odb-network/variables.tf'] = mod0_vars('aws-odb-network', {})
    files['modules/aws-odb-network/outputs.tf']   = mod0_outputs('aws-odb-network')
    files['modules/aws-exadata-infra/main.tf']      = mod1_main('aws-exadata-infra')
    files['modules/aws-exadata-infra/variables.tf'] = mod1_vars('aws-exadata-infra', {})
    files['modules/aws-exadata-infra/outputs.tf']   = mod1_outputs('aws-exadata-infra')
    files['modules/aws-peering/main.tf']      = mod2_main('aws-peering')
    files['modules/aws-peering/variables.tf'] = mod2_vars('aws-peering', {}, '')
    files['modules/aws-peering/outputs.tf']   = mod2_outputs('aws-peering')
    files['modules/aws-vm-cluster/main.tf']      = mod3_main('aws-vm-cluster')
    files['modules/aws-vm-cluster/variables.tf'] = mod3_vars('aws-vm-cluster', {}, '', '')
    files['modules/aws-vm-cluster/outputs.tf']   = mod3_outputs('aws-vm-cluster')
    # One shared directory per pair mode, emitted only when something uses it.
    if avmclusters:
        files[f'modules/{_MOD4}/main.tf']      = mod4_main(_MOD4)
        files[f'modules/{_MOD4}/variables.tf'] = mod4_vars(_MOD4)
        files[f'modules/{_MOD4}/outputs.tf']   = mod4_outputs(_MOD4)
    if avmclusters_arn:
        files[f'modules/{_MOD4_ARN}/main.tf']      = mod4_main(_MOD4_ARN, use_arn_pair=True)
        files[f'modules/{_MOD4_ARN}/variables.tf'] = mod4_vars(_MOD4_ARN, use_arn_pair=True)
        files[f'modules/{_MOD4_ARN}/outputs.tf']   = mod4_outputs(_MOD4_ARN)
    if adbs:
        files.update(_adb_module_files())
    if adb_integration:
        files.update(_adb_integration_module_files())
    if ram_shares:
        files.update(_ram_share_module_files())
    if kms_keys:
        files.update(_kms_module_files())
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
    files.update(generate_oci_dg_tf(data))
    return files

