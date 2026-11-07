"""
AWS ODB tests — self-contained, no GCP or Azure dependencies.
Run with:  python -m unittest tests/test_aws.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import (
    app, generate_all,
    mod0_main, mod0_vars, mod0_outputs, mod0_tfvars,
    mod1_main, mod1_vars, mod1_outputs, mod1_tfvars,
    mod2_main, mod2_vars, mod2_outputs, mod2_tfvars,
    mod3_main, mod3_vars, mod3_outputs, mod3_tfvars,
    build_root_main, build_root_tfvars,
    _aws_net_defaults, _aws_infra_defaults, _aws_peer_defaults, _aws_cluster_defaults,
)
# Imported from the owning package rather than re-exported through app: the
# validator is this cloud's, and app.py has no business in the path.
import clouds.aws.validator as aws_validator


# ══════════════════════════════════════════════════════════════════════════════
#  FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

def aws_net(module_name='odb_network', **kw):
    return {
        'module_name': module_name,
        'display_name': 'test-net',
        'availability_zone_id': 'use1-az6',
        'client_subnet_cidr': '10.2.0.0/24',
        'backup_subnet_cidr': '10.2.1.0/24',
        's3_access': True,
        'zero_etl_access': False,
        'tags': {'Env': 'test'},
        **kw,
    }

def aws_infra(module_name='odb_infra', **kw):
    return {
        'module_name': module_name,
        'display_name': 'test-infra',
        'shape': 'Exadata.X11M',
        'availability_zone_id': 'use1-az6',
        'compute_count': 2,
        'storage_count': 3,
        'mw_preference': 'NO_PREFERENCE',
        'mw_patching_mode': 'ROLLING',
        'tags': {},
        **kw,
    }

def aws_peer(module_name='odb_peering', **kw):
    return {
        'module_name': module_name,
        'display_name': 'test-peer',
        'peer_network_id': 'vpc-abc123',
        'network_ref': 'odb_network',
        'tags': {},
        **kw,
    }

def aws_cluster(module_name='odb_cluster', **kw):
    return {
        'module_name': module_name,
        'display_name': 'test-cluster',
        'cpu_core_count': 16,
        'gi_version': '23.0.0.0',
        'hostname_prefix': 'vm',
        'license_model': 'LICENSE_INCLUDED',
        'vm_mode': 'id',
        'infra_ref': 'odb_infra',
        'network_ref': 'odb_network',
        'ssh_public_keys': ['ssh-rsa AAAAB3Nz test@host'],
        'db_servers': [],
        'dco_is_diagnostics_events_enabled': True,
        'dco_is_health_monitoring_enabled': True,
        'dco_is_incident_logs_enabled': True,
        'tags': {},
        **kw,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  ODB Network
# ══════════════════════════════════════════════════════════════════════════════

class TestAwsOdbNetwork(unittest.TestCase):

    def setUp(self):
        self.mn = 'odb_network'
        self.d  = _aws_net_defaults(aws_net(self.mn))

    def test_main_contains_resource(self):
        out = mod0_main(self.mn, self.d)
        self.assertIn('aws_odb_network', out)
        self.assertIn(self.mn, out)

    def test_vars_contains_module_name(self):
        out = mod0_vars(self.mn, self.d)
        self.assertIn('variable', out)
        self.assertIn('display_name', out)

    def test_vars_contains_cidr_variables(self):
        out = mod0_vars(self.mn, self.d)
        self.assertIn('client_subnet_cidr', out)
        self.assertIn('backup_subnet_cidr', out)

    def test_outputs_contains_network_id(self):
        out = mod0_outputs(self.mn)
        self.assertIn('network_id', out)

    def test_tfvars_contains_display_name(self):
        out = mod0_tfvars(self.mn, self.d)
        self.assertIn('test-net', out)

    def test_tfvars_contains_cidr_values(self):
        out = mod0_tfvars(self.mn, self.d)
        self.assertIn('10.2.0.0/24', out)
        self.assertIn('10.2.1.0/24', out)

    def test_tfvars_s3_access_enabled(self):
        out = mod0_tfvars(self.mn, self.d)
        self.assertIn('ENABLED', out)

    def test_tfvars_zero_etl_disabled(self):
        out = mod0_tfvars(self.mn, self.d)
        self.assertIn('DISABLED', out)

    def test_custom_module_name(self):
        mn = 'prod_odb_network'
        d = _aws_net_defaults(aws_net(mn))
        out = mod0_main(mn, d)
        self.assertIn(mn, out)

    def test_tags_rendered_in_vars(self):
        out = mod0_vars(self.mn, self.d)
        self.assertIn('tags', out)


# ══════════════════════════════════════════════════════════════════════════════
#  Exadata Infrastructure
# ══════════════════════════════════════════════════════════════════════════════

class TestAwsExadataInfra(unittest.TestCase):

    def setUp(self):
        self.mn = 'odb_infra'
        self.d  = _aws_infra_defaults(aws_infra(self.mn))

    def test_main_contains_resource(self):
        out = mod1_main(self.mn)
        self.assertIn('aws_odb_cloud_exadata_infrastructure', out)

    def test_vars_contains_shape(self):
        out = mod1_vars(self.mn, self.d)
        self.assertIn('shape', out)

    def test_vars_contains_compute_storage(self):
        out = mod1_vars(self.mn, self.d)
        self.assertIn('compute_count', out)
        self.assertIn('storage_count', out)

    def test_vars_contains_maintenance_window(self):
        out = mod1_vars(self.mn, self.d)
        self.assertIn('maintenance_window', out)

    def test_outputs_contains_infra_id(self):
        out = mod1_outputs(self.mn)
        self.assertIn('infra_id', out)

    def test_tfvars_contains_shape_value(self):
        out = mod1_tfvars(self.mn, self.d)
        self.assertIn('Exadata.X11M', out)

    def test_tfvars_compute_count(self):
        out = mod1_tfvars(self.mn, self.d)
        self.assertIn('2', out)

    def test_custom_preference_no_preference(self):
        d = _aws_infra_defaults(aws_infra(self.mn, mw_preference='NO_PREFERENCE'))
        out = mod1_tfvars(self.mn, d)
        self.assertIn('NO_PREFERENCE', out)

    def test_custom_preference_custom(self):
        d = _aws_infra_defaults(aws_infra(self.mn,
            mw_preference='CUSTOM_PREFERENCE',
            mw_hours_of_day='4,8',
            mw_weeks_of_month='1,3',
        ))
        out = mod1_tfvars(self.mn, d)
        self.assertIn('CUSTOM_PREFERENCE', out)


# ══════════════════════════════════════════════════════════════════════════════
#  Network Peering
# ══════════════════════════════════════════════════════════════════════════════

class TestAwsPeering(unittest.TestCase):

    def setUp(self):
        self.mn  = 'odb_peering'
        self.mn0 = 'odb_network'
        self.d   = _aws_peer_defaults(aws_peer(self.mn), self.mn0)

    def test_main_contains_resource(self):
        out = mod2_main(self.mn)
        self.assertIn('aws_odb_network_peering_connection', out)

    def test_vars_contains_fields(self):
        out = mod2_vars(self.mn, self.d, self.mn0)
        self.assertIn('peer_network_id', out)

    def test_outputs_contains_peering_id(self):
        out = mod2_outputs(self.mn)
        self.assertIn('peering_connection_id', out)

    def test_tfvars_contains_peer_vpc(self):
        out = mod2_tfvars(self.mn, self.d, self.mn0)
        self.assertIn('vpc-abc123', out)

    def test_network_ref_in_root_main(self):
        nets     = [_aws_net_defaults(aws_net(self.mn0))]
        infras   = [_aws_infra_defaults(aws_infra())]
        peerings = [_aws_peer_defaults(aws_peer(self.mn, network_ref=self.mn0), self.mn0)]
        clusters = [_aws_cluster_defaults(aws_cluster())]
        out = build_root_main(nets, infras, peerings, clusters)
        # Refs resolve through the for_each key now, not a per-instance module name.
        self.assertIn('module.aws_odb_network[each.value.network_ref].network_id', out)


# ══════════════════════════════════════════════════════════════════════════════
#  VM Cluster
# ══════════════════════════════════════════════════════════════════════════════

class TestAwsVmCluster(unittest.TestCase):

    def setUp(self):
        self.mn  = 'odb_cluster'
        self.mn0 = 'odb_network'
        self.mn1 = 'odb_infra'
        self.d   = _aws_cluster_defaults(aws_cluster(self.mn), self.mn0, self.mn1)

    def test_main_contains_resource(self):
        out = mod3_main(self.mn)
        self.assertIn('aws_odb_cloud_vm_cluster', out)

    def test_vars_contains_gi_version(self):
        out = mod3_vars(self.mn, self.d, self.mn0, self.mn1)
        self.assertIn('gi_version', out)

    def test_vars_contains_ssh_keys(self):
        out = mod3_vars(self.mn, self.d, self.mn0, self.mn1)
        self.assertIn('ssh_public_keys', out)

    def test_outputs_contains_cluster_id(self):
        out = mod3_outputs(self.mn)
        self.assertIn('vm_cluster_id', out)

    def test_tfvars_contains_cpu_count(self):
        out = mod3_tfvars(self.mn, self.d, self.mn0, self.mn1)
        self.assertIn('16', out)

    def test_tfvars_contains_gi_version(self):
        out = mod3_tfvars(self.mn, self.d, self.mn0, self.mn1)
        self.assertIn('23.0.0.0', out)

    def test_infra_ref_wired_in_root(self):
        nets     = [_aws_net_defaults(aws_net(self.mn0))]
        infras   = [_aws_infra_defaults(aws_infra(self.mn1))]
        peerings = [_aws_peer_defaults(aws_peer())]
        clusters = [_aws_cluster_defaults(aws_cluster(self.mn, infra_ref=self.mn1, network_ref=self.mn0), self.mn0, self.mn1)]
        out = build_root_main(nets, infras, peerings, clusters)
        self.assertIn('module.aws_exadata_infra[each.value.infra_ref].infra_id', out)
        self.assertIn('module.aws_odb_network[each.value.network_ref].network_id', out)

    def test_license_included(self):
        out = mod3_tfvars(self.mn, self.d, self.mn0, self.mn1)
        self.assertIn('LICENSE_INCLUDED', out)

    def test_byol(self):
        d = _aws_cluster_defaults(aws_cluster(self.mn, license_model='BRING_YOUR_OWN_LICENSE'), self.mn0, self.mn1)
        out = mod3_tfvars(self.mn, d, self.mn0, self.mn1)
        self.assertIn('BRING_YOUR_OWN_LICENSE', out)


# ══════════════════════════════════════════════════════════════════════════════
#  AWS Root
# ══════════════════════════════════════════════════════════════════════════════

class TestAwsRoot(unittest.TestCase):

    def _build(self, nets=1, infras=1, peerings=1, clusters=1):
        ns  = [_aws_net_defaults(aws_net(f'net_{i}'))     for i in range(nets)]
        inf = [_aws_infra_defaults(aws_infra(f'inf_{i}')) for i in range(infras)]
        prs = [_aws_peer_defaults(aws_peer(f'peer_{i}', network_ref='net_0'), 'net_0')  for i in range(peerings)]
        cls = [_aws_cluster_defaults(aws_cluster(f'cl_{i}', infra_ref='inf_0', network_ref='net_0'), 'net_0', 'inf_0') for i in range(clusters)]
        return ns, inf, prs, cls

    def test_root_main_contains_provider(self):
        ns, inf, prs, cls = self._build()
        out = build_root_main(ns, inf, prs, cls)
        self.assertIn('hashicorp/aws', out)
        self.assertIn('required_version', out)

    # The root used to emit one module block per instance (module "net_0",
    # "net_1", ...). It now emits one for_each block per resource type, driven by
    # the maps in terraform.auto.tfvars, so instance names live in tfvars and the
    # module names are fixed.

    def test_root_main_has_all_modules(self):
        ns, inf, prs, cls = self._build()
        out = build_root_main(ns, inf, prs, cls)
        for mod in ('aws_odb_network', 'aws_exadata_infra',
                    'aws_peering', 'aws_vm_cluster'):
            self.assertIn(f'module "{mod}"', out)

    def test_root_main_modules_are_for_each_driven(self):
        ns, inf, prs, cls = self._build()
        out = build_root_main(ns, inf, prs, cls)
        for var in ('var.aws_networks', 'var.aws_infras',
                    'var.aws_peerings', 'var.aws_clusters'):
            self.assertIn(f'for_each = {var}', out)

    def test_root_main_shape_is_independent_of_instance_count(self):
        # Adding instances must not change main.tf - that is the whole point of
        # the for_each rewrite. Only terraform.auto.tfvars grows.
        one  = build_root_main(*self._build())
        many = build_root_main(*self._build(nets=3, infras=3, peerings=3, clusters=3))
        self.assertEqual(one, many)

    def test_root_main_emits_each_module_once(self):
        ns, inf, prs, cls = self._build(nets=3, peerings=3, clusters=3)
        out = build_root_main(ns, inf, prs, cls)
        for mod in ('aws_odb_network', 'aws_peering', 'aws_vm_cluster'):
            self.assertEqual(out.count(f'module "{mod}"'), 1, mod)

    def test_root_main_cluster_module_present(self):
        ns, inf, prs, cls = self._build(clusters=3)
        out = build_root_main(ns, inf, prs, cls)
        self.assertIn('module "aws_vm_cluster"', out)
        self.assertIn('for_each = var.aws_clusters', out)

    def test_root_main_outputs(self):
        ns, inf, prs, cls = self._build()
        out = build_root_main(ns, inf, prs, cls)
        self.assertIn('output', out)
        self.assertIn('network_id', out)
        self.assertIn('infra_id', out)

    def test_root_tfvars_contains_region(self):
        ns, inf, prs, cls = self._build()
        out = build_root_tfvars(ns, inf, prs, cls)
        self.assertIn('aws_region', out)

    def test_cluster_depends_on_infra_and_network(self):
        ns, inf, prs, cls = self._build()
        out = build_root_main(ns, inf, prs, cls)
        self.assertIn('depends_on', out)


# ══════════════════════════════════════════════════════════════════════════════
#  ODB network service access — sts / kms / endpoint policies / cross-region
# ══════════════════════════════════════════════════════════════════════════════

_POLICY = '{"Version": "2012-10-17", "Statement": []}'


class TestOdbNetworkServiceAccess(unittest.TestCase):
    """sts_access and friends.

    These six are Optional in the provider, so the governing property is that a
    config which sets none of them emits none of them - a saved config from
    before they existed must keep generating the tfvars entry it always did.
    """

    def _tfvars(self, **kw):
        net = _aws_net_defaults(aws_net('odb_network', **kw))
        return build_root_tfvars([net], [], [], [])

    def _entry(self, **kw):
        """The aws_networks block of the root tfvars."""
        out = self._tfvars(**kw)
        start = out.index('aws_networks = {')
        return out[start:out.index('\n}', start)]

    # ── the quiet case ───────────────────────────────────────────────────────
    def test_unset_emits_nothing(self):
        entry = self._entry()
        for key in ('sts_access', 'kms_access', 's3_policy_document',
                    'sts_policy_document', 'kms_policy_document',
                    'cross_region_s3_restore_sources_access'):
            self.assertNotIn(key, entry, f'{key} leaked into an unset config')

    def test_unset_entry_keys_are_unchanged(self):
        """The pre-existing keys, and only those, at their original alignment."""
        entry = self._entry()
        self.assertIn('    delete_associated_resources = false', entry)
        self.assertIn('    s3_access                   = "ENABLED"', entry)

    # ── access flags ─────────────────────────────────────────────────────────
    def test_sts_access_emitted_when_set(self):
        self.assertIn('sts_access', self._entry(sts_access='ENABLED'))

    def test_kms_access_emitted_when_set(self):
        self.assertIn('kms_access', self._entry(kms_access='DISABLED'))

    def test_access_flag_accepts_only_the_two_statuses(self):
        from clouds.aws.generator import _opt_access
        self.assertEqual(_opt_access('ENABLED'), 'ENABLED')
        self.assertEqual(_opt_access('disabled'), 'DISABLED')
        self.assertEqual(_opt_access('MAYBE'), '')
        self.assertEqual(_opt_access(''), '')
        self.assertEqual(_opt_access(None), '')

    def test_module_sends_null_not_empty_string(self):
        """"" is not a valid status, so an unset flag must become null."""
        out = mod0_main('odb_network', _aws_net_defaults(aws_net()))
        self.assertIn('var.sts_access != "" ? var.sts_access : null', out)
        self.assertIn('var.kms_access != "" ? var.kms_access : null', out)

    def test_access_flags_are_not_lifecycle_guarded(self):
        """Optional + Computed adopts the state value; guarding it would be wrong."""
        out = mod0_main('odb_network', _aws_net_defaults(aws_net()))
        self.assertNotIn('ignore_changes', out)

    # ── endpoint policies ────────────────────────────────────────────────────
    def test_policy_document_is_emitted_as_a_heredoc(self):
        entry = self._entry(sts_policy_document=_POLICY)
        self.assertIn('<<-EOT', entry)
        self.assertIn('"Version": "2012-10-17"', entry)

    def test_each_policy_has_its_own_variable(self):
        out = mod0_vars('odb_network', _aws_net_defaults(aws_net()))
        for v in ('s3_policy_document', 'sts_policy_document', 'kms_policy_document'):
            self.assertIn(f'variable "{v}"', out)

    # ── cross-region restore sources ─────────────────────────────────────────
    def test_cross_region_list_is_emitted(self):
        entry = self._entry(
            cross_region_s3_restore_sources_access=['us-east-1', 'eu-west-1'])
        self.assertIn('cross_region_s3_restore_sources_access = ["us-east-1", "eu-west-1"]',
                      entry)

    def test_cross_region_accepts_a_comma_string(self):
        entry = self._entry(
            cross_region_s3_restore_sources_access='us-east-1, eu-west-1')
        self.assertIn('"us-east-1", "eu-west-1"', entry)

    # ── alignment ────────────────────────────────────────────────────────────
    def test_lone_optional_is_single_spaced(self):
        """terraform fmt collapses a one-line run, so the template must too."""
        entry = self._entry(sts_access='ENABLED')
        self.assertIn('    sts_access = "ENABLED"', entry)

    def test_optional_run_pads_to_its_own_longest_key(self):
        entry = self._entry(sts_access='ENABLED', kms_policy_document=_POLICY)
        self.assertIn('    sts_access          = "ENABLED"', entry)
        self.assertIn('    kms_policy_document = <<-EOT', entry)


class TestOdbNetworkServiceAccessValidation(unittest.TestCase):

    def _errors(self, **kw):
        errors = {}
        aws_validator.validate(
            {'tab': 0, 'aws_networks': [aws_net('n1', **kw)]}, errors)
        return errors.get('n1', {})

    def test_nothing_set_is_valid(self):
        self.assertEqual(self._errors(), {})

    def test_valid_pair_passes(self):
        self.assertEqual(
            self._errors(sts_access='ENABLED', sts_policy_document=_POLICY), {})

    def test_bad_status_rejected(self):
        self.assertIn('sts_access', self._errors(sts_access='MAYBE'))

    def test_malformed_policy_json_rejected(self):
        self.assertIn('sts_policy_document',
                      self._errors(sts_policy_document='{not json'))

    def test_policy_must_be_an_object(self):
        self.assertIn('kms_policy_document',
                      self._errors(kms_policy_document='[1, 2]'))

    def test_policy_against_disabled_access_rejected(self):
        errs = self._errors(kms_access='DISABLED', kms_policy_document=_POLICY)
        self.assertIn('kms_policy_document', errs)
        self.assertIn('no effect', errs['kms_policy_document'])

    def test_policy_against_unset_access_allowed(self):
        """Unset may still come up enabled, so the policy is not necessarily inert."""
        self.assertEqual(self._errors(sts_policy_document=_POLICY), {})

    def test_bad_region_name_rejected(self):
        self.assertIn('cross_region_s3_restore_sources_access',
                      self._errors(cross_region_s3_restore_sources_access=['nope']))

    def test_cross_region_needs_s3_access(self):
        errs = self._errors(s3_access=False,
                            cross_region_s3_restore_sources_access=['us-east-1'])
        self.assertIn('cross_region_s3_restore_sources_access', errs)


# ══════════════════════════════════════════════════════════════════════════════
#  AUTONOMOUS DATABASE SERVERLESS + SECRETS MANAGER INTEGRATION
#  aws_odb_autonomous_database / aws_odb_autonomous_database_secrets_manager_
#  integration, both new in hashicorp/aws 6.68.0. An ADB-S needs an ODB Network
#  and nothing else; its ADMIN password must never reach a file, plan or state.
# ══════════════════════════════════════════════════════════════════════════════

def aws_adb(module_name='odb_adb', **kw):
    return {'module_name': module_name, 'display_name': 'sales-adb', **kw}


def _adb_payload(*adbs, integration=False, networks=None, iac_tool='terraform'):
    return {
        'cloud': 'aws', 'iac_tool': iac_tool,
        'aws_networks': networks or [aws_net('n1')],
        'aws_infras': [aws_infra('i1')],
        'aws_autonomous_dbs': list(adbs),
        'aws_adb_secrets_integration': integration,
    }


def _tfvars_entry(tfvars, key):
    """The body of one aws_autonomous_dbs entry."""
    start = tfvars.index(f'  "{key}" = {{')
    return tfvars[start:tfvars.index('\n  }', start)]


class TestAwsAutonomousDbGeneration(unittest.TestCase):

    def test_no_adb_emits_nothing_new(self):
        files = generate_all(_adb_payload())
        self.assertFalse([k for k in files if 'aws-autonomous-db' in k or 'aws-adb-secrets' in k])
        self.assertIn('version = ">= 6.42.0"', files['main.tf'])
        self.assertIn('required_version = ">= 1.5.0"', files['main.tf'])
        self.assertNotIn('aws_autonomous_dbs', files['variables.tf'])
        self.assertNotIn('aws_adb_admin_passwords', files['variables.tf'])

    def test_adb_emits_its_module_and_for_each(self):
        files = generate_all(_adb_payload(aws_adb('a1'), aws_adb('a2', display_name='hr')))
        for f in ('main.tf', 'variables.tf', 'outputs.tf'):
            self.assertIn(f'modules/aws-autonomous-db/{f}', files)
        self.assertIn('for_each = var.aws_autonomous_dbs', files['main.tf'])
        self.assertIn('output "autonomous_databases"', files['main.tf'])
        for k in ('"a1"', '"a2"'):
            self.assertIn(k, files['terraform.auto.tfvars'])

    def test_adb_raises_provider_and_core_versions(self):
        for tool in ('terraform', 'opentofu'):
            with self.subTest(tool=tool):
                files = generate_all(_adb_payload(aws_adb(), iac_tool=tool))
                self.assertIn('version = ">= 6.68.0"', files['main.tf'])
                # Ephemeral variables and write-only arguments: 1.11 on both.
                self.assertIn('required_version = ">= 1.11.0"', files['main.tf'])
                self.assertIn('">= 6.68.0"', files['modules/aws-autonomous-db/main.tf'])

    def test_integration_alone_raises_only_the_provider(self):
        files = generate_all(_adb_payload(integration=True))
        self.assertIn('version = ">= 6.68.0"', files['main.tf'])
        self.assertIn('required_version = ">= 1.5.0"', files['main.tf'])
        self.assertIn('modules/aws-adb-secrets-integration/main.tf', files)
        self.assertNotIn('modules/aws-autonomous-db/main.tf', files)
        self.assertIn('output "adb_secrets_manager_service_role_arn"', files['main.tf'])

    def test_integration_is_protected_from_destroy(self):
        # Destroying it disables Secrets Manager passwords account- and Region-wide.
        files = generate_all(_adb_payload(integration=True))
        self.assertIn('prevent_destroy = true', files['modules/aws-adb-secrets-integration/main.tf'])

    def test_adb_depends_on_integration_only_when_managed(self):
        with_int = generate_all(_adb_payload(aws_adb(), integration=True))['main.tf']
        without  = generate_all(_adb_payload(aws_adb()))['main.tf']
        self.assertIn('module.aws_adb_secrets_integration]', with_int)
        self.assertNotIn('aws_adb_secrets_integration', without)

    def test_adb_module_has_no_infra_reference(self):
        main = generate_all(_adb_payload(aws_adb()))['modules/aws-autonomous-db/main.tf']
        self.assertNotIn('cloud_exadata_infrastructure', main)
        self.assertIn('odb_network_id = var.odb_network_id', main)


class TestAwsAutonomousDbPassword(unittest.TestCase):

    SECRET = 'Sup3rSecret-Value#99'

    def test_password_never_lands_in_a_generated_file(self):
        files = generate_all(_adb_payload(aws_adb(admin_password=self.SECRET,
                                                  admin_password_wo=self.SECRET)))
        for path, content in files.items():
            self.assertNotIn(self.SECRET, content, path)

    def test_password_variable_is_ephemeral_sensitive_and_unset(self):
        files = generate_all(_adb_payload(aws_adb()))
        var = files['variables.tf']
        block = var[var.index('variable "aws_adb_admin_passwords"'):]
        block = block[:block.index('\n}')]
        self.assertIn('ephemeral   = true', block)
        self.assertIn('sensitive   = true', block)
        # No assignment — the comment lines show how to set it, and must stay comments.
        import re
        self.assertIsNone(re.search(r'(?m)^\s*aws_adb_admin_passwords\s*=', files['terraform.auto.tfvars']))
        self.assertIn('TF_VAR_aws_adb_admin_passwords', files['terraform.auto.tfvars'])
        mod = files['modules/aws-autonomous-db/variables.tf']
        self.assertIn('ephemeral   = true', mod[mod.index('variable "admin_password_wo"'):])

    def test_a_single_password_variable_needs_no_hcl_quoting(self):
        # TF_VAR_aws_adb_admin_passwords is an HCL map, and a bare password in it
        # fails with "Variables not allowed" — what a user typed. The singular
        # variable takes the password as-is and covers every write_only database.
        files = generate_all(_adb_payload(aws_adb('a1')))
        var = files['variables.tf']
        block = var[var.index('variable "aws_adb_admin_password" {'):]
        block = block[:block.index('\n}')]
        self.assertIn('type        = string', block)
        self.assertIn('ephemeral   = true', block)
        self.assertIn('sensitive   = true', block)
        self.assertIn('lookup(var.aws_adb_admin_passwords, each.key, var.aws_adb_admin_password)',
                      files['main.tf'])

    def test_password_instructions_cover_macos_and_powershell(self):
        files = generate_all(_adb_payload(aws_adb('a1')))
        for path in ('README.md', 'terraform.auto.tfvars', 'modules/aws-autonomous-db/main.tf'):
            with self.subTest(path=path):
                self.assertIn("export TF_VAR_aws_adb_admin_password='", files[path])
                self.assertIn("$env:TF_VAR_aws_adb_admin_password = '", files[path])

    def test_a_missing_password_stops_the_plan_with_instructions(self):
        main = generate_all(_adb_payload(aws_adb('a1')))['modules/aws-autonomous-db/main.tf']
        self.assertIn('precondition {', main)
        self.assertIn('var.admin_password_source != "write_only" || var.admin_password_wo != null', main)

    def test_write_only_entry_carries_version_not_secret_fields(self):
        entry = _tfvars_entry(generate_all(_adb_payload(aws_adb('a1')))['terraform.auto.tfvars'], 'a1')
        self.assertIn('admin_password_source     = "write_only"', entry)
        self.assertIn('admin_password_wo_version = 1', entry)
        self.assertNotIn('secret_arn', entry)

    def test_secrets_manager_entry_carries_the_secret_and_role(self):
        tfvars = generate_all(_adb_payload(aws_adb(
            'a1', admin_password_source='secrets_manager',
            secret_arn='arn:aws:secretsmanager:us-east-1:111122223333:secret:x',
            secret_iam_role_arn='arn:aws:iam::111122223333:role/r')))['terraform.auto.tfvars']
        entry = _tfvars_entry(tfvars, 'a1')
        self.assertIn('secret_arn              = "arn:aws:secretsmanager:us-east-1:111122223333:secret:x"', entry)
        self.assertIn('secret_external_id_type = "compartment_ocid"', entry)
        self.assertNotIn('admin_password_wo_version', entry)
        # No write-only entry, so no export hint either.
        self.assertNotIn('TF_VAR_aws_adb_admin_passwords', tfvars)

    def test_export_hint_names_only_write_only_entries(self):
        tfvars = generate_all(_adb_payload(
            aws_adb('a1'),
            aws_adb('a2', admin_password_source='secrets_manager', secret_arn='arn:aws:x:::y',
                    secret_iam_role_arn='arn:aws:iam:::z')))['terraform.auto.tfvars']
        # The per-database map example names only the write_only databases.
        hint = next(l for l in tfvars.splitlines() if 'HCL map such as' in l)
        self.assertIn('a1 = "..."', hint)
        self.assertNotIn('a2', hint)


class TestAwsAutonomousDbTfvars(unittest.TestCase):

    def _entry(self, **kw):
        return _tfvars_entry(generate_all(_adb_payload(aws_adb('a1', **kw)))['terraform.auto.tfvars'], 'a1')

    def test_optional_computed_fields_are_omitted_when_unset(self):
        # Left out, each adopts the service's value and produces no diff.
        entry = self._entry()
        for k in ('db_version', 'is_auto_scaling_enabled', 'backup_retention_period_in_days',
                  'is_mtls_connection_required', 'allowlisted_ips', 'character_set',
                  'encryption_key_provider', 'database_edition'):
            self.assertNotIn(k, entry)

    def test_explicit_false_is_kept_distinct_from_unset(self):
        entry = self._entry(is_mtls_connection_required='false', is_auto_scaling_enabled='')
        self.assertIn('is_mtls_connection_required = false', entry)
        self.assertNotIn('is_auto_scaling_enabled', entry)

    def test_set_optionals_are_emitted_with_hcl_types(self):
        entry = self._entry(db_version='23ai', backup_retention_period_in_days='30',
                            allowlisted_ips='10.0.0.0/24, 10.1.0.0/24', compute_count='2.5')
        self.assertIn('db_version                      = "23ai"', entry)
        self.assertIn('backup_retention_period_in_days = 30', entry)
        self.assertIn('allowlisted_ips                 = ["10.0.0.0/24", "10.1.0.0/24"]', entry)
        self.assertIn('compute_count            = 2.5', entry)

    def test_db_name_derives_from_display_name(self):
        self.assertIn('db_name                  = "HRADB"', self._entry(display_name='2hr-adb'))
        self.assertIn('db_name                  = "ADB"', self._entry(display_name='---'))
        self.assertIn('db_name                  = "Mine1"', self._entry(db_name='Mine1'))


class TestAwsAutonomousDbNetwork(unittest.TestCase):

    def test_dangling_network_ref_is_retargeted_to_the_first_network(self):
        tfvars = generate_all(_adb_payload(aws_adb('a1', network_ref='gone')))['terraform.auto.tfvars']
        self.assertIn('network_ref              = "n1"', _tfvars_entry(tfvars, 'a1'))

    def test_external_network_resolves_through_the_merged_locals(self):
        files = generate_all(_adb_payload(
            aws_adb('a1', network_ref='nx'),
            networks=[aws_net('n1'), aws_net('nx', is_existing=True, existing_id='odbnet-abc')]))
        self.assertIn('network_ref              = "nx"', _tfvars_entry(files['terraform.auto.tfvars'], 'a1'))
        main = files['main.tf']
        block = main[main.index('module "aws_autonomous_db"'):]
        self.assertIn('odb_network_id           = local.odb_network_ids[each.value.network_ref]', block)


class TestAwsAutonomousDbValidation(unittest.TestCase):

    def _errs(self, networks=None, **kw):
        errors = {}
        aws_validator.validate({'tab': 5, 'aws_networks': networks or [aws_net('n1')],
                                'aws_autonomous_dbs': [aws_adb('a1', **{'network_ref': 'n1', **kw})]}, errors)
        return errors.get('a1', {})

    def test_a_plain_config_is_valid(self):
        self.assertEqual(self._errs(), {})

    def test_display_name_required(self):
        self.assertIn('display_name', self._errs(display_name=''))

    def test_db_name_rules(self):
        self.assertIn('db_name', self._errs(db_name='1abc'))
        self.assertIn('db_name', self._errs(db_name='has-hyphen'))
        self.assertIn('db_name', self._errs(db_name='A' * 31))
        self.assertNotIn('db_name', self._errs(db_name='Sales1'))

    def test_storage_must_be_a_whole_number_of_tb(self):
        # The provider's ValidateConfig rejects a fractional TB value outright.
        self.assertIn('data_storage_size_in_tbs', self._errs(data_storage_size_in_tbs='1.5'))
        self.assertIn('data_storage_size_in_tbs', self._errs(data_storage_size_in_tbs='385'))
        self.assertNotIn('data_storage_size_in_tbs', self._errs(data_storage_size_in_tbs='384'))

    def test_compute_count_range(self):
        self.assertIn('compute_count', self._errs(compute_count='0'))
        self.assertIn('compute_count', self._errs(compute_count='513'))
        self.assertNotIn('compute_count', self._errs(compute_count='0.5'))

    def test_network_must_exist(self):
        self.assertIn('network_ref', self._errs(network_ref='nope'))
        errors = {}
        aws_validator.validate({'tab': 5, 'aws_networks': [],
                                'aws_autonomous_dbs': [aws_adb('a1')]}, errors)
        self.assertIn('network_ref', errors['a1'])

    def test_secrets_manager_needs_both_arns(self):
        errs = self._errs(admin_password_source='secrets_manager')
        self.assertIn('secret_arn', errs)
        self.assertIn('secret_iam_role_arn', errs)
        errs = self._errs(admin_password_source='secrets_manager', secret_arn='not-an-arn',
                          secret_iam_role_arn='arn:aws:iam::111122223333:role/r')
        self.assertEqual(set(errs), {'secret_arn'})

    def test_kms_key_and_provider_go_together(self):
        self.assertIn('kms_key_id', self._errs(encryption_key_provider='AWS_KMS'))
        self.assertIn('kms_key_id', self._errs(kms_key_id='arn:aws:kms:us-east-1:1:key/x'))
        self.assertEqual(self._errs(encryption_key_provider='AWS_KMS',
                                    kms_key_id='arn:aws:kms:us-east-1:1:key/x'), {})

    def test_edition_only_with_byol(self):
        self.assertIn('database_edition', self._errs(database_edition='STANDARD_EDITION'))
        self.assertNotIn('database_edition', self._errs(database_edition='STANDARD_EDITION',
                                                        license_model='BRING_YOUR_OWN_LICENSE'))

    def test_allowlisted_ips_must_be_ipv4(self):
        self.assertIn('allowlisted_ips', self._errs(allowlisted_ips=['10.0.0.0/24', 'example.com']))
        self.assertNotIn('allowlisted_ips', self._errs(allowlisted_ips='10.0.0.1, 10.0.0.0/24'))

    def test_a_password_in_the_payload_is_rejected(self):
        # Saving the config would otherwise write it under data/.
        self.assertIn('admin_password', self._errs(admin_password='Welcome12345#'))


class TestAwsAutonomousDbFmt(unittest.TestCase):
    """Optional keys vary per entry, so the tfvars alignment is computed — prove fmt agrees."""

    @classmethod
    def setUpClass(cls):
        import shutil
        cls.tf_bin = shutil.which('terraform') or shutil.which('tofu')

    def _assert_fmt_clean(self, files):
        if not self.tf_bin:
            self.skipTest('terraform/tofu not found in PATH')
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for rel, content in files.items():
                if rel.endswith(('.tf', '.tfvars')):
                    full = Path(tmp) / rel
                    full.parent.mkdir(parents=True, exist_ok=True)
                    full.write_text(content + '\n', encoding='utf-8')
            r = subprocess.run([self.tf_bin, 'fmt', '-check', '-recursive', '-diff', tmp],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_combinations_are_formatted(self):
        everything = dict(
            db_version='23ai', database_edition='ENTERPRISE_EDITION',
            license_model='BRING_YOUR_OWN_LICENSE', is_auto_scaling_enabled='true',
            is_auto_scaling_for_storage_enabled='false', backup_retention_period_in_days='30',
            autonomous_maintenance_schedule_type='EARLY', is_mtls_connection_required='true',
            private_endpoint_label='sales', private_endpoint_ip='10.2.0.10',
            allowlisted_ips=['10.0.0.0/16'], character_set='AL32UTF8', ncharacter_set='AL16UTF16',
            encryption_key_provider='AWS_KMS', kms_key_id='arn:aws:kms:us-east-1:1:key/x',
            customer_contacts=['dba@example.com'])
        cases = {
            'minimal': [aws_adb('a1')],
            'one optional': [aws_adb('a1', db_version='19c')],
            'everything': [aws_adb('a1', **everything)],
            'secrets manager': [aws_adb('a1', admin_password_source='secrets_manager',
                                        secret_arn='arn:aws:x:::y', secret_iam_role_arn='arn:aws:iam:::z')],
            'mixed': [aws_adb('a1'), aws_adb('a2', **everything)],
        }
        for name, adbs in cases.items():
            for integration in (False, True):
                with self.subTest(case=name, integration=integration):
                    self._assert_fmt_clean(generate_all(_adb_payload(*adbs, integration=integration)))

    def test_with_avmc_and_without(self):
        payload = _adb_payload(aws_adb('a1'))
        payload['aws_avmclusters'] = [{'module_name': 'av1', 'display_name': 'av',
                                       'infra_ref': 'i1', 'network_ref': 'n1'}]
        self._assert_fmt_clean(generate_all(payload))


if __name__ == '__main__':
    unittest.main()
