"""
GCP Oracle Database tests — for_each / shared-module architecture.
Run with:  python -m unittest tests/test_gcp.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, generate_all
from clouds.gcp.generator import (
    _gcp_net_defaults, _gcp_infra_defaults, _gcp_cluster_defaults,
    _gcp_adb_defaults, _gcp_shared_module_files, _gcp_adb_module_files,
    _gcp_adbs_net_module_files, _wants_dedicated, _split_networks,
    gcp_build_root_main, gcp_build_root_vars, gcp_build_root_tfvars,
    generate_gcp_tf,
    _GCP_MOD_NET, _GCP_MOD_NET_ADBS, _GCP_MOD_INFRA, _GCP_MOD_CLUSTER, _GCP_MOD_ADB,
)
from tf_validator import validate_terraform, summarise


# ══════════════════════════════════════════════════════════════════════════════
#  FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

def gcp_net(module_name='gcp-odb-network', **kw):
    return {
        'module_name':   module_name,
        'odb_network_id': 'my-odb-net',
        'location':       'us-east4',
        'network':        'projects/my-proj/global/networks/default',
        'project':        'my-proj',
        'gcp_oracle_zone': 'us-east4-b-r1',
        'deletion_protection': True,
        'client_subnet_id':   'client-subnet',
        'client_cidr':        '10.0.1.0/24',
        'backup_subnet_id':   'backup-subnet',
        'backup_cidr':        '10.0.2.0/24',
        'labels': {'env': 'test'},
        **kw,
    }

def gcp_infra(module_name='gcp-exadata-infra', **kw):
    return {
        'module_name':    module_name,
        'cloud_exadata_infrastructure_id': 'my-infra',
        'display_name':   'My Infra',
        'location':       'us-east4',
        'gcp_oracle_zone': 'us-east4-b-r1',
        'project':        'my-proj',
        'shape':          'Exadata.X9M',
        'compute_count':  2,
        'storage_count':  3,
        'mw_preference':  'NO_PREFERENCE',
        'mw_patching_mode': 'ROLLING',
        **kw,
    }

def gcp_cluster(module_name='gcp-vm-cluster', net_module='gcp-odb-network', infra_module='gcp-exadata-infra', **kw):
    return {
        'module_name':       module_name,
        'cloud_vm_cluster_id': 'my-cluster',
        'display_name':      'My Cluster',
        'location':          'us-east4',
        'project':           'my-proj',
        'hostname_prefix':   'vm',
        'cpu_core_count':    16,
        'memory_size_gb':    60,
        'db_node_storage_size_gb': 120,
        'data_storage_size_tb':    4.0,
        'gi_version':        '23.0.0.0',
        'license_type':      'LICENSE_INCLUDED',
        'ssh_public_keys':   ['ssh-rsa AAAAB3Nz test@host'],
        'network_ref':       net_module,
        'infra_ref':         infra_module,
        **kw,
    }

def gcp_adb(module_name='gcp_adb', net_module='gcp-odb-network', **kw):
    return {
        'module_name':            module_name,
        'autonomous_database_id': 'my-adb',
        'database':               'myadb',
        'display_name':           'My ADB',
        'location':               'us-east4',
        'network_ref':            net_module,
        'db_workload':            'OLTP',
        'compute_count':          2,
        'data_storage_size_gb':   120,
        **kw,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Shared module files
# ══════════════════════════════════════════════════════════════════════════════

class TestGcpSharedModules(unittest.TestCase):

    def setUp(self):
        self.files = _gcp_shared_module_files()

    def test_exactly_nine_module_files(self):
        self.assertEqual(len(self.files), 9)

    def test_odb_network_main_has_resource(self):
        self.assertIn('google_oracle_database_odb_network',
                      self.files[f'modules/{_GCP_MOD_NET}/main.tf'])

    def test_odb_network_main_has_client_subnet(self):
        self.assertIn('google_oracle_database_odb_subnet',
                      self.files[f'modules/{_GCP_MOD_NET}/main.tf'])

    def test_odb_network_variables_has_odb_network_id(self):
        self.assertIn('odb_network_id', self.files[f'modules/{_GCP_MOD_NET}/variables.tf'])

    def test_odb_network_variables_has_cidr_range_vars(self):
        v = self.files[f'modules/{_GCP_MOD_NET}/variables.tf']
        self.assertIn('client_cidr_range', v)
        self.assertIn('backup_cidr_range', v)

    def test_odb_network_outputs_has_network_name(self):
        self.assertIn('odb_network_name', self.files[f'modules/{_GCP_MOD_NET}/outputs.tf'])

    def test_odb_network_outputs_has_subnet_names(self):
        o = self.files[f'modules/{_GCP_MOD_NET}/outputs.tf']
        self.assertIn('client_subnet_name', o)
        self.assertIn('backup_subnet_name', o)

    def test_exadata_infra_main_has_resource(self):
        self.assertIn('google_oracle_database_cloud_exadata_infrastructure',
                      self.files[f'modules/{_GCP_MOD_INFRA}/main.tf'])

    def test_exadata_infra_main_has_lifecycle(self):
        self.assertIn('ignore_changes', self.files[f'modules/{_GCP_MOD_INFRA}/main.tf'])

    def test_exadata_infra_variables_has_shape(self):
        self.assertIn('shape', self.files[f'modules/{_GCP_MOD_INFRA}/variables.tf'])

    def test_exadata_infra_outputs_has_infra_name(self):
        self.assertIn('infra_name', self.files[f'modules/{_GCP_MOD_INFRA}/outputs.tf'])

    def test_exadata_infra_outputs_has_self_link(self):
        self.assertIn('infra_self_link', self.files[f'modules/{_GCP_MOD_INFRA}/outputs.tf'])

    def test_vm_cluster_main_has_resource(self):
        self.assertIn('google_oracle_database_cloud_vm_cluster',
                      self.files[f'modules/{_GCP_MOD_CLUSTER}/main.tf'])

    def test_vm_cluster_main_has_memory_size_gb(self):
        self.assertIn('memory_size_gb', self.files[f'modules/{_GCP_MOD_CLUSTER}/main.tf'])

    def test_vm_cluster_main_has_data_storage_tb(self):
        self.assertIn('data_storage_size_tb', self.files[f'modules/{_GCP_MOD_CLUSTER}/main.tf'])

    def test_vm_cluster_main_has_timeouts(self):
        self.assertIn('timeouts', self.files[f'modules/{_GCP_MOD_CLUSTER}/main.tf'])

    def test_vm_cluster_main_has_lifecycle(self):
        self.assertIn('ignore_changes', self.files[f'modules/{_GCP_MOD_CLUSTER}/main.tf'])

    def test_vm_cluster_variables_has_all_storage_vars(self):
        v = self.files[f'modules/{_GCP_MOD_CLUSTER}/variables.tf']
        for var in ['memory_size_gb', 'db_node_storage_size_gb', 'data_storage_size_tb']:
            self.assertIn(var, v, msg=f'Missing {var} in vm-cluster variables.tf')

    def test_vm_cluster_outputs_has_cluster_name(self):
        self.assertIn('vm_cluster_name', self.files[f'modules/{_GCP_MOD_CLUSTER}/outputs.tf'])

    def test_all_module_files_non_empty(self):
        for path, content in self.files.items():
            self.assertGreater(len(content.strip()), 0, f'{path} is empty')


# ══════════════════════════════════════════════════════════════════════════════
#  Root templates
# ══════════════════════════════════════════════════════════════════════════════

class TestGcpRoot(unittest.TestCase):

    def _build(self, net_count=1, infra_count=1, cluster_count=1):
        nets     = [_gcp_net_defaults(gcp_net(f'gnet-{i}')) for i in range(net_count)]
        infras   = [_gcp_infra_defaults(gcp_infra(f'ginf-{i}')) for i in range(infra_count)]
        clusters = [_gcp_cluster_defaults(
            gcp_cluster(f'gcl-{i}', 'gnet-0', 'ginf-0'), nets[0], infras[0])
            for i in range(cluster_count)]
        return nets, infras, clusters

    def test_root_main_has_provider(self):
        ns, inf, cls = self._build()
        self.assertIn('hashicorp/google', gcp_build_root_main(ns, inf, cls))

    def test_root_main_uses_for_each_networks(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('for_each = var.gcp_odb_networks', out)

    def test_root_main_uses_for_each_infras(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('for_each = var.gcp_exadata_infras', out)

    def test_root_main_uses_for_each_clusters(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('for_each = var.gcp_vm_clusters', out)

    def test_root_main_has_db_servers_data_source(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('google_oracle_database_db_servers', out)

    def test_root_main_references_infra_key(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('each.value.infra_key', out)

    def test_root_main_references_network_key(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('each.value.network_key', out)

    def test_root_main_passes_memory_size_gb(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('memory_size_gb', out)

    def test_root_main_passes_data_storage_size_tb(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('data_storage_size_tb', out)

    def test_root_vars_has_map_object_networks(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_vars(ns, inf, cls)
        self.assertIn('gcp_odb_networks', out)
        self.assertIn('map(object', out)

    def test_root_vars_has_map_object_infras(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_vars(ns, inf, cls)
        self.assertIn('gcp_exadata_infras', out)

    def test_root_vars_has_map_object_clusters(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_vars(ns, inf, cls)
        self.assertIn('gcp_vm_clusters', out)

    def test_root_vars_cluster_has_infra_key_field(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_vars(ns, inf, cls)
        self.assertIn('infra_key', out)

    def test_root_vars_cluster_has_network_key_field(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_vars(ns, inf, cls)
        self.assertIn('network_key', out)

    def test_root_tfvars_has_gcp_odb_networks_map(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_tfvars(ns, inf, cls)
        self.assertIn('gcp_odb_networks', out)

    def test_root_tfvars_has_gcp_exadata_infras_map(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_tfvars(ns, inf, cls)
        self.assertIn('gcp_exadata_infras', out)

    def test_root_tfvars_has_gcp_vm_clusters_map(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_tfvars(ns, inf, cls)
        self.assertIn('gcp_vm_clusters', out)

    def test_root_tfvars_cluster_entry_has_infra_key(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_tfvars(ns, inf, cls)
        self.assertIn('infra_key', out)

    def test_root_tfvars_cluster_entry_has_network_key(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_tfvars(ns, inf, cls)
        self.assertIn('network_key', out)

    def test_root_tfvars_has_memory_size_gb(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_tfvars(ns, inf, cls)
        self.assertIn('memory_size_gb', out)


# ══════════════════════════════════════════════════════════════════════════════
#  generate_gcp_tf — file count and structure
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateGcpTf(unittest.TestCase):

    def _base(self, net_count=1, infra_count=1, cluster_count=1):
        nets     = [gcp_net(f'gn-{i}')   for i in range(net_count)]
        infras   = [gcp_infra(f'gi-{i}') for i in range(infra_count)]
        clusters = [gcp_cluster(f'gc-{i}', 'gn-0', 'gi-0') for i in range(cluster_count)]
        return {'cloud': 'gcp', 'gcp_networks': nets, 'gcp_infras': infras, 'gcp_clusters': clusters}

    # 3 root files + 9 shared module files (3 modules × 3 files) + a generated
    # README = 13. The count is fixed: instances live in terraform.auto.tfvars,
    # so adding them grows that file rather than the file list.
    EXPECTED_FILES = 13

    def test_always_fixed_file_count_one_of_each(self):
        self.assertEqual(len(generate_gcp_tf(self._base())), self.EXPECTED_FILES)

    def test_always_fixed_file_count_two_networks(self):
        self.assertEqual(len(generate_gcp_tf(self._base(net_count=2))), self.EXPECTED_FILES)

    def test_always_fixed_file_count_two_clusters(self):
        self.assertEqual(len(generate_gcp_tf(self._base(cluster_count=2))), self.EXPECTED_FILES)

    def test_always_fixed_file_count_two_of_everything(self):
        self.assertEqual(len(generate_gcp_tf(self._base(2, 2, 2))), self.EXPECTED_FILES)

    def test_readme_is_generated(self):
        self.assertIn('README.md', generate_gcp_tf(self._base()))

    def test_has_root_main(self):
        self.assertIn('main.tf', generate_gcp_tf(self._base()))

    def test_has_root_variables(self):
        self.assertIn('variables.tf', generate_gcp_tf(self._base()))

    def test_has_root_tfvars(self):
        self.assertIn('terraform.auto.tfvars', generate_gcp_tf(self._base()))

    def test_has_shared_odb_network_module(self):
        files = generate_gcp_tf(self._base())
        for f in ['main.tf', 'variables.tf', 'outputs.tf']:
            self.assertIn(f'modules/{_GCP_MOD_NET}/{f}', files)

    def test_has_shared_exadata_infra_module(self):
        files = generate_gcp_tf(self._base())
        for f in ['main.tf', 'variables.tf', 'outputs.tf']:
            self.assertIn(f'modules/{_GCP_MOD_INFRA}/{f}', files)

    def test_has_shared_vm_cluster_module(self):
        files = generate_gcp_tf(self._base())
        for f in ['main.tf', 'variables.tf', 'outputs.tf']:
            self.assertIn(f'modules/{_GCP_MOD_CLUSTER}/{f}', files)

    def test_no_per_instance_module_dirs(self):
        files = generate_gcp_tf(self._base())
        # Old style: modules/gn-0/main.tf — should NOT exist
        self.assertNotIn('modules/gn-0/main.tf', files)
        self.assertNotIn('modules/gi-0/main.tf', files)

    def test_multiple_networks_appear_in_tfvars(self):
        files = generate_gcp_tf(self._base(net_count=2))
        tfv = files['terraform.auto.tfvars']
        self.assertIn('gn-0', tfv)
        self.assertIn('gn-1', tfv)

    def test_multiple_clusters_appear_in_tfvars(self):
        files = generate_gcp_tf(self._base(cluster_count=2))
        tfv = files['terraform.auto.tfvars']
        self.assertIn('gc-0', tfv)
        self.assertIn('gc-1', tfv)

    def test_root_main_google_provider(self):
        self.assertIn('hashicorp/google', generate_gcp_tf(self._base())['main.tf'])

    def test_all_files_non_empty(self):
        for path, content in generate_gcp_tf(self._base()).items():
            self.assertGreater(len(content.strip()), 0, f'{path} is empty')


# ══════════════════════════════════════════════════════════════════════════════
#  generate_all — GCP integration
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateAllGcp(unittest.TestCase):

    def _base(self):
        return {
            'cloud': 'gcp',
            'gcp_networks':  [gcp_net('gn-1')],
            'gcp_infras':    [gcp_infra('gi-1')],
            'gcp_clusters':  [gcp_cluster('gc-1', 'gn-1', 'gi-1')],
        }

    def test_returns_root_main(self):
        self.assertIn('main.tf', generate_all(self._base()))

    def test_returns_root_tfvars(self):
        self.assertIn('terraform.auto.tfvars', generate_all(self._base()))

    def test_returns_root_variables(self):
        self.assertIn('variables.tf', generate_all(self._base()))

    def test_shared_module_files_present(self):
        files = generate_all(self._base())
        for mod in [_GCP_MOD_NET, _GCP_MOD_INFRA, _GCP_MOD_CLUSTER]:
            for f in ['main.tf', 'variables.tf', 'outputs.tf']:
                self.assertIn(f'modules/{mod}/{f}', files)

    def test_no_aws_provider_in_gcp_output(self):
        files = generate_all(self._base())
        self.assertNotIn('hashicorp/aws', files['main.tf'])
        self.assertNotIn('hashicorp/azurerm', files['main.tf'])


# ══════════════════════════════════════════════════════════════════════════════
#  Autonomous AI Database (Serverless)
# ══════════════════════════════════════════════════════════════════════════════

class TestGcpAutonomousDb(unittest.TestCase):

    def _payload(self, adbs=None, **kw):
        return {'cloud': 'gcp',
                'gcp_networks': [gcp_net('gn-0')],
                'gcp_infras':   [gcp_infra('gi-0')],
                'gcp_clusters': [gcp_cluster('gc-0', 'gn-0', 'gi-0')],
                'gcp_autonomous_dbs': adbs if adbs is not None else [gcp_adb(net_module='gn-0')],
                **kw}

    # ── Emitted only when used ────────────────────────────────────────────────

    def test_no_adb_module_dir_without_an_adb(self):
        files = generate_gcp_tf(self._payload(adbs=[]))
        self.assertFalse([k for k in files if _GCP_MOD_ADB in k])

    def test_adb_module_dir_emitted_when_used(self):
        files = generate_gcp_tf(self._payload())
        for f in ('main.tf', 'variables.tf', 'outputs.tf'):
            self.assertIn(f'modules/{_GCP_MOD_ADB}/{f}', files)

    def test_no_adb_leaves_root_untouched(self):
        """A config without an ADB generates what it did before ADB support."""
        files = generate_gcp_tf(self._payload(adbs=[]))
        self.assertNotIn('gcp_autonomous_dbs', files['main.tf'])
        self.assertNotIn('gcp_autonomous_dbs', files['variables.tf'])
        self.assertNotIn('gcp_autonomous_dbs', files['terraform.auto.tfvars'])


    # ── Provider constraint ───────────────────────────────────────────────────

    def test_provider_floor_is_7_5_with_or_without_adb(self):
        """The blueprints' CI bisected published releases: these modules do not
        validate below google 7.5.0 (7.0.0 undercut). ADB's odb_network /
        odb_subnet arrived in 7.0, so one floor now covers both cases."""
        for adbs in (None, []):
            with self.subTest(adbs=adbs):
                payload = self._payload() if adbs is None else self._payload(adbs=adbs)
                main = generate_gcp_tf(payload)['main.tf']
                google = main[main.index('google = {'):main.index('}', main.index('google = {'))]
                self.assertIn('version = ">= 7.5.0"', google)

    # ── for_each wiring ───────────────────────────────────────────────────────

    def test_root_uses_for_each(self):
        self.assertIn('for_each = var.gcp_autonomous_dbs',
                      generate_gcp_tf(self._payload())['main.tf'])

    def test_file_count_fixed_regardless_of_adb_count(self):
        one = generate_gcp_tf(self._payload())
        two = generate_gcp_tf(self._payload(
            adbs=[gcp_adb('gcp_adb', net_module='gn-0'),
                  gcp_adb('gcp_adb_2', net_module='gn-0', autonomous_database_id='adb-2')]))
        self.assertEqual(len(one), len(two))

    def test_both_instances_reach_tfvars(self):
        tfvars = generate_gcp_tf(self._payload(
            adbs=[gcp_adb('gcp_adb', net_module='gn-0'),
                  gcp_adb('gcp_adb_2', net_module='gn-0')]))['terraform.auto.tfvars']
        self.assertIn('"gcp_adb"', tfvars)
        self.assertIn('"gcp_adb_2"', tfvars)

    # ── Networking: client subnet, never backup ───────────────────────────────

    def test_wired_to_odb_network_and_client_subnet(self):
        main = generate_gcp_tf(self._payload())['main.tf']
        block = main[main.index('module "gcp_autonomous_db"'):]
        block = block[:block.index('\n}\n')]
        self.assertIn('odb_network = module.gcp_odb_network[each.value.network_key].odb_network_name', block)
        self.assertIn('odb_subnet  = module.gcp_odb_network[each.value.network_key].client_subnet_name', block)

    def test_never_uses_the_backup_subnet(self):
        """ADB uses the client subnet only — the backup subnet is for VM Clusters."""
        main = generate_gcp_tf(self._payload())['main.tf']
        block = main[main.index('module "gcp_autonomous_db"'):]
        block = block[:block.index('\n}\n')]
        self.assertNotIn('backup_odb_subnet', block)
        self.assertNotIn('backup_subnet_name', block)

    def test_takes_no_infra_reference(self):
        """Serverless runs on Oracle's fleet — there is no Exadata Infra under it."""
        main = generate_gcp_tf(self._payload())['main.tf']
        block = main[main.index('module "gcp_autonomous_db"'):]
        block = block[:block.index('\n}\n')]
        self.assertNotIn('gcp_exadata_infra', block)
        self.assertNotIn('infra_key', block)

    def test_unknown_network_ref_is_retargeted(self):
        """A dangling key would fail at apply on a missing map key."""
        tfvars = generate_gcp_tf(self._payload(
            adbs=[gcp_adb(net_module='no-such-network')]))['terraform.auto.tfvars']
        self.assertIn('network_key                     = "gn-0"', tfvars)

    # ── Secrets ───────────────────────────────────────────────────────────────

    def test_admin_password_never_written_to_any_file(self):
        files = generate_gcp_tf(self._payload(
            adbs=[gcp_adb(net_module='gn-0', admin_password='S3cretPassw0rd')]))
        for path, content in files.items():
            self.assertNotIn('S3cretPassw0rd', content, f'password leaked into {path}')

    def test_password_variable_is_sensitive_and_has_no_default(self):
        variables = generate_gcp_tf(self._payload())['variables.tf']
        block = variables[variables.index('variable "gcp_adb_admin_passwords"'):]
        block = block[:block.index('\n}')]
        self.assertIn('sensitive   = true', block)
        self.assertNotIn('default', block)

    def test_password_map_not_assigned_in_tfvars(self):
        tfvars = generate_gcp_tf(self._payload())['terraform.auto.tfvars']
        assigned = [ln for ln in tfvars.splitlines()
                    if ln.lstrip().startswith('gcp_adb_admin_passwords')]
        self.assertEqual(assigned, [])

    def test_module_declares_admin_password_sensitive(self):
        variables = _gcp_adb_module_files()[f'modules/{_GCP_MOD_ADB}/variables.tf']
        block = variables[variables.index('variable "admin_password"'):]
        block = block[:block.index('\n}')]
        self.assertIn('sensitive   = true', block)
        self.assertNotIn('default', block)

    # ── Resource shape ────────────────────────────────────────────────────────

    def test_module_emits_the_autonomous_database_resource(self):
        main = _gcp_adb_module_files()[f'modules/{_GCP_MOD_ADB}/main.tf']
        self.assertIn('resource "google_oracle_database_autonomous_database" "this"', main)

    def test_module_has_no_gcp_oracle_zone(self):
        """ADB is regional, unlike the infra, VM clusters and subnets."""
        files = _gcp_adb_module_files()
        for path, content in files.items():
            # The word may appear in a comment saying exactly this; what must
            # not exist is an argument or a variable of that name.
            code = '\n'.join(ln for ln in content.splitlines()
                             if not ln.lstrip().startswith('#'))
            self.assertNotIn('gcp_oracle_zone', code, path)

    def test_scaling_fields_are_guarded_against_drift(self):
        main = _gcp_adb_module_files()[f'modules/{_GCP_MOD_ADB}/main.tf']
        block = main[main.index('ignore_changes'):]
        for field in ('compute_count', 'data_storage_size_gb', 'db_version'):
            self.assertIn(f'properties[0].{field}', block)

    def test_customer_contacts_render_as_a_dynamic_block(self):
        main = _gcp_adb_module_files()[f'modules/{_GCP_MOD_ADB}/main.tf']
        self.assertIn('dynamic "customer_contacts"', main)

    def test_root_exposes_adb_output(self):
        self.assertIn('output "autonomous_databases"',
                      generate_gcp_tf(self._payload())['main.tf'])

    # ── Defaults ──────────────────────────────────────────────────────────────

    def test_database_name_derived_from_id_when_absent(self):
        """`database` is alphanumeric only — hyphens are dropped, not swapped."""
        adb = _gcp_adb_defaults({'autonomous_database_id': 'my-prod-adb'})
        self.assertEqual(adb['database'], 'myprodadb')

    def test_derived_database_name_is_capped_at_30_chars(self):
        adb = _gcp_adb_defaults({'autonomous_database_id': 'a' * 63})
        self.assertEqual(len(adb['database']), 30)

    def test_whole_ecpu_count_renders_as_an_int(self):
        self.assertEqual(_gcp_adb_defaults({'compute_count': 2.0})['compute_count'], 2)

    def test_fractional_ecpu_count_is_preserved(self):
        self.assertEqual(_gcp_adb_defaults({'compute_count': 2.5})['compute_count'], 2.5)

    def test_contacts_accept_a_comma_separated_string(self):
        adb = _gcp_adb_defaults({'customer_contacts': 'a@b.com, c@d.com'})
        self.assertEqual(adb['customer_contacts'], ['a@b.com', 'c@d.com'])

    def test_network_ref_falls_back_to_the_first_network(self):
        adb = _gcp_adb_defaults({}, {'module_name': 'gn-0'})
        self.assertEqual(adb['network_ref'], 'gn-0')

    # ── Validation ────────────────────────────────────────────────────────────

    def _errors(self, adb):
        import clouds.gcp.validator as v
        errors = {}
        v.validate({'tab': 15, 'gcp_autonomous_dbs': [adb]}, errors)
        return errors.get(adb.get('module_name', 'gcp_adb'), {})

    def test_valid_adb_passes(self):
        self.assertEqual(self._errors(gcp_adb()), {})

    def test_missing_database_id_is_an_error(self):
        self.assertIn('autonomous_database_id',
                      self._errors(gcp_adb(autonomous_database_id='')))

    def test_missing_network_ref_is_an_error(self):
        self.assertIn('network_ref', self._errors(gcp_adb(net_module='')))

    def test_one_ecpu_is_rejected(self):
        self.assertIn('compute_count', self._errors(gcp_adb(compute_count=1)))

    def test_bad_workload_is_rejected(self):
        self.assertIn('db_workload', self._errors(gcp_adb(db_workload='OLAP')))

    def test_backup_retention_over_60_days_is_rejected(self):
        self.assertIn('backup_retention_period_days',
                      self._errors(gcp_adb(backup_retention_period_days=90)))


# ══════════════════════════════════════════════════════════════════════════════
#  ODB Network purpose flag — dedicated / adbs / both
# ══════════════════════════════════════════════════════════════════════════════

class TestGcpNetworkPurpose(unittest.TestCase):
    """The flag on the ODB Network decides the shape of the whole config.

    ADB Serverless needs no Exadata Infrastructure, no VM Cluster and no backup
    subnet, so a config whose networks are all ADB-S-only must not emit them.
    """

    def _mods(self, payload):
        return sorted({k.split('/')[1] for k in generate_gcp_tf(payload)
                       if k.startswith('modules/')})

    def _adbs_only(self):
        return {'cloud': 'gcp',
                'gcp_networks': [gcp_net('gn', purpose='adbs')],
                'gcp_infras': [], 'gcp_clusters': [],
                'gcp_autonomous_dbs': [gcp_adb(net_module='gn')]}

    # ── Defaults and parsing ──────────────────────────────────────────────────

    def test_purpose_defaults_to_both(self):
        """Configs saved before the flag existed must keep their old shape."""
        self.assertEqual(_gcp_net_defaults({})['purpose'], 'both')

    def test_unknown_purpose_falls_back_to_both(self):
        self.assertEqual(_gcp_net_defaults({'purpose': 'nonsense'})['purpose'], 'both')

    def test_purpose_is_preserved(self):
        for p in ('dedicated', 'adbs', 'both'):
            self.assertEqual(_gcp_net_defaults({'purpose': p})['purpose'], p)

    def test_split_networks_separates_adbs_only(self):
        ded, adbs = _split_networks([{'module_name': 'a', 'purpose': 'both'},
                                     {'module_name': 'b', 'purpose': 'adbs'},
                                     {'module_name': 'c', 'purpose': 'dedicated'}])
        self.assertEqual([n['module_name'] for n in ded], ['a', 'c'])
        self.assertEqual([n['module_name'] for n in adbs], ['b'])

    # ── Which modules get emitted ─────────────────────────────────────────────

    def test_adbs_only_emits_no_exadata_modules(self):
        mods = self._mods(self._adbs_only())
        self.assertNotIn(_GCP_MOD_INFRA, mods)
        self.assertNotIn(_GCP_MOD_CLUSTER, mods)

    def test_adbs_only_uses_the_no_backup_network_module(self):
        mods = self._mods(self._adbs_only())
        self.assertIn(_GCP_MOD_NET_ADBS, mods)
        self.assertNotIn(_GCP_MOD_NET, mods)

    def test_adbs_only_emits_exactly_two_module_dirs(self):
        self.assertEqual(self._mods(self._adbs_only()),
                         [_GCP_MOD_ADB, _GCP_MOD_NET_ADBS])

    def test_dedicated_only_is_unchanged(self):
        mods = self._mods({'cloud': 'gcp',
                           'gcp_networks': [gcp_net('gn', purpose='dedicated')],
                           'gcp_infras': [gcp_infra('gi')],
                           'gcp_clusters': [gcp_cluster('gc', 'gn', 'gi')]})
        self.assertEqual(mods, [_GCP_MOD_INFRA, _GCP_MOD_NET, _GCP_MOD_CLUSTER])

    def test_mixed_config_emits_both_network_modules(self):
        mods = self._mods({'cloud': 'gcp',
                           'gcp_networks': [gcp_net('gn', purpose='both'),
                                            gcp_net('gn2', purpose='adbs')],
                           'gcp_infras': [gcp_infra('gi')],
                           'gcp_clusters': [gcp_cluster('gc', 'gn', 'gi')],
                           'gcp_autonomous_dbs': [gcp_adb(net_module='gn2')]})
        self.assertIn(_GCP_MOD_NET, mods)
        self.assertIn(_GCP_MOD_NET_ADBS, mods)

    def test_explicit_infra_survives_an_adbs_only_network(self):
        """The flag suppresses the phantom instance, never a real one."""
        payload = dict(self._adbs_only(), gcp_infras=[gcp_infra('gi')])
        self.assertIn(_GCP_MOD_INFRA, self._mods(payload))

    def test_wants_dedicated_false_only_when_everything_is_adbs(self):
        self.assertFalse(_wants_dedicated([{'purpose': 'adbs'}]))
        self.assertTrue(_wants_dedicated([{'purpose': 'adbs'}, {'purpose': 'both'}]))
        self.assertTrue(_wants_dedicated([{'purpose': 'adbs'}], infras=[{'x': 1}]))
        self.assertTrue(_wants_dedicated([]))          # legacy/empty payload

    # ── No phantom instances ──────────────────────────────────────────────────

    def test_adbs_only_invents_no_infra_or_cluster_in_tfvars(self):
        tfvars = generate_gcp_tf(self._adbs_only())['terraform.auto.tfvars']
        self.assertNotIn('gcp_exadata_infras', tfvars)
        self.assertNotIn('gcp_vm_clusters', tfvars)

    def test_adbs_only_root_has_no_exadata_wiring(self):
        main = generate_gcp_tf(self._adbs_only())['main.tf']
        for token in ('gcp_exadata_infra', 'gcp_vm_cluster',
                      'google_oracle_database_db_servers'):
            self.assertNotIn(token, main)

    # ── No backup subnet ──────────────────────────────────────────────────────

    def test_adbs_network_module_creates_no_backup_subnet(self):
        main = _gcp_adbs_net_module_files()[f'modules/{_GCP_MOD_NET_ADBS}/main.tf']
        self.assertIn('CLIENT_SUBNET', main)
        self.assertNotIn('BACKUP_SUBNET', main)

    def test_adbs_network_module_takes_no_backup_variables(self):
        variables = _gcp_adbs_net_module_files()[f'modules/{_GCP_MOD_NET_ADBS}/variables.tf']
        self.assertNotIn('variable "backup_subnet_id"', variables)
        self.assertNotIn('variable "backup_cidr_range"', variables)

    def test_adbs_only_tfvars_carries_no_backup_cidr(self):
        tfvars = generate_gcp_tf(self._adbs_only())['terraform.auto.tfvars']
        self.assertNotIn('backup_cidr_range', tfvars)
        self.assertNotIn('backup_subnet_id', tfvars)

    def test_standard_network_still_has_its_backup_subnet(self):
        """The original module is untouched — no state move for existing users."""
        main = _gcp_shared_module_files()[f'modules/{_GCP_MOD_NET}/main.tf']
        self.assertIn('BACKUP_SUBNET', main)
        self.assertIn('resource "google_oracle_database_odb_subnet" "backup"', main)
        self.assertNotIn('count', main)

    # ── ADB wiring across both network kinds ──────────────────────────────────

    def test_adb_resolves_through_locals_when_an_adbs_network_exists(self):
        main = generate_gcp_tf(self._adbs_only())['main.tf']
        self.assertIn('local.adb_odb_networks[each.value.network_key]', main)

    def test_adb_uses_the_direct_reference_when_no_adbs_network_exists(self):
        """No locals block unless it is actually needed."""
        main = generate_gcp_tf({'cloud': 'gcp',
                                'gcp_networks': [gcp_net('gn', purpose='both')],
                                'gcp_infras': [], 'gcp_clusters': [],
                                'gcp_autonomous_dbs': [gcp_adb(net_module='gn')]})['main.tf']
        self.assertIn('module.gcp_odb_network[each.value.network_key]', main)
        self.assertNotIn('adb_odb_networks', main)

    def test_mixed_locals_merge_covers_both_network_modules(self):
        main = generate_gcp_tf({'cloud': 'gcp',
                                'gcp_networks': [gcp_net('gn', purpose='both'),
                                                 gcp_net('gn2', purpose='adbs')],
                                'gcp_infras': [], 'gcp_clusters': [],
                                'gcp_autonomous_dbs': [gcp_adb(net_module='gn2')]})['main.tf']
        block = main[main.index('adb_odb_networks = merge('):]
        block = block[:block.index('\n}')]
        self.assertIn('module.gcp_odb_network :', block)
        self.assertIn('module.gcp_odb_network_adbs :', block)

    # ── Validation ────────────────────────────────────────────────────────────

    def _errors(self, tab, payload, module_name):
        import clouds.gcp.validator as v
        errors = {}
        v.validate({**payload, 'tab': tab}, errors)
        return errors.get(module_name, {})

    def test_adbs_network_does_not_require_a_backup_cidr(self):
        net = gcp_net('gn', purpose='adbs')
        net.pop('backup_cidr'); net.pop('backup_subnet_id')
        self.assertEqual(self._errors(10, {'gcp_networks': [net]}, 'gn'), {})

    def test_dedicated_network_still_requires_a_backup_cidr(self):
        net = gcp_net('gn', purpose='dedicated')
        net.pop('backup_cidr')
        self.assertIn('backup_cidr', self._errors(10, {'gcp_networks': [net]}, 'gn'))

    def test_bad_purpose_value_is_rejected(self):
        self.assertIn('purpose',
                      self._errors(10, {'gcp_networks': [gcp_net('gn', purpose='wat')]}, 'gn'))

    def test_cluster_may_not_use_an_adbs_only_network(self):
        errs = self._errors(13, {'gcp_networks': [gcp_net('gn', purpose='adbs')],
                                 'gcp_clusters': [gcp_cluster('gc', 'gn', 'gi')]}, 'gc')
        self.assertIn('network_ref', errs)

    def test_adb_may_not_use_a_dedicated_only_network(self):
        errs = self._errors(15, {'gcp_networks': [gcp_net('gn', purpose='dedicated')],
                                 'gcp_autonomous_dbs': [gcp_adb(net_module='gn')]}, 'gcp_adb')
        self.assertIn('network_ref', errs)

    def test_both_network_serves_cluster_and_adb(self):
        payload = {'gcp_networks': [gcp_net('gn', purpose='both')],
                   'gcp_clusters': [gcp_cluster('gc', 'gn', 'gi')],
                   'gcp_autonomous_dbs': [gcp_adb(net_module='gn')]}
        self.assertNotIn('network_ref', self._errors(13, payload, 'gc'))
        self.assertNotIn('network_ref', self._errors(15, payload, 'gcp_adb'))


# ══════════════════════════════════════════════════════════════════════════════
#  Default normalisers
# ══════════════════════════════════════════════════════════════════════════════

class TestGcpDefaultNormalisers(unittest.TestCase):

    def test_net_defaults_odb_network_id_fallback(self):
        self.assertEqual(_gcp_net_defaults({})['odb_network_id'], 'my-odb-network')

    def test_net_defaults_client_cidr_fallback(self):
        self.assertEqual(_gcp_net_defaults({})['client_cidr'], '10.0.1.0/24')

    def test_net_defaults_backup_cidr_fallback(self):
        self.assertEqual(_gcp_net_defaults({})['backup_cidr'], '10.0.2.0/24')

    def test_net_defaults_preserves_location(self):
        self.assertEqual(_gcp_net_defaults({'location': 'europe-west3'})['location'], 'europe-west3')

    def test_infra_defaults_shape_fallback(self):
        self.assertEqual(_gcp_infra_defaults({})['shape'], 'Exadata.X9M')

    def test_infra_defaults_compute_count_int(self):
        d = _gcp_infra_defaults({'compute_count': '4', 'storage_count': '6'})
        self.assertEqual(d['compute_count'], 4)
        self.assertEqual(d['storage_count'], 6)

    def test_infra_defaults_fallback_counts(self):
        d = _gcp_infra_defaults({})
        self.assertEqual(d['compute_count'], 2)
        self.assertEqual(d['storage_count'], 3)

    def test_cluster_defaults_network_ref_fallback(self):
        first_net = _gcp_net_defaults({'module_name': 'net-prod'})
        d = _gcp_cluster_defaults({}, first_net=first_net)
        self.assertEqual(d['network_ref'], 'net-prod')

    def test_cluster_defaults_infra_ref_fallback(self):
        first_infra = _gcp_infra_defaults({'module_name': 'infra-prod'})
        d = _gcp_cluster_defaults({}, first_infra=first_infra)
        self.assertEqual(d['infra_ref'], 'infra-prod')

    def test_cluster_defaults_memory_size_gb_int(self):
        d = _gcp_cluster_defaults({'memory_size_gb': '120'})
        self.assertEqual(d['memory_size_gb'], 120)

    def test_cluster_defaults_data_storage_float(self):
        d = _gcp_cluster_defaults({'data_storage_size_tb': '8'})
        self.assertEqual(d['data_storage_size_tb'], 8.0)

    def test_cluster_defaults_cpu_core_count_int(self):
        d = _gcp_cluster_defaults({'cpu_core_count': '32'})
        self.assertEqual(d['cpu_core_count'], 32)


# ══════════════════════════════════════════════════════════════════════════════
#  API Routes — GCP
# ══════════════════════════════════════════════════════════════════════════════

class TestApiRoutesGcp(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.base = {
            'cloud': 'gcp',
            'gcp_networks':  [gcp_net('gn1')],
            'gcp_infras':    [gcp_infra('gi1')],
            'gcp_clusters':  [gcp_cluster('gc1', 'gn1', 'gi1')],
        }

    def test_generate_shared_net_module_variables(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': f'modules/{_GCP_MOD_NET}/variables.tf'},
            content_type='application/json')
        self.assertIn('variable', r.get_json()['content'])

    def test_generate_shared_infra_module_variables(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': f'modules/{_GCP_MOD_INFRA}/variables.tf'},
            content_type='application/json')
        self.assertIn('variable', r.get_json()['content'])

    def test_generate_shared_cluster_module_variables(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': f'modules/{_GCP_MOD_CLUSTER}/variables.tf'},
            content_type='application/json')
        self.assertIn('variable', r.get_json()['content'])

    def test_generate_root_variables(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': 'variables.tf'},
            content_type='application/json')
        self.assertIn('gcp_odb_networks', r.get_json()['content'])

    def test_download_gcp_filename_contains_gcp(self):
        r = self.client.post('/api/download', json=self.base, content_type='application/json')
        self.assertIn('gcp', r.headers.get('Content-Disposition', ''))

    def test_download_gcp_zip_magic_bytes(self):
        r = self.client.post('/api/download', json=self.base, content_type='application/json')
        self.assertEqual(r.data[:4], b'PK\x03\x04')

    def test_download_gcp_zip_contains_main_tf(self):
        import io, zipfile as zf_mod
        r = self.client.post('/api/download', json=self.base, content_type='application/json')
        z = zf_mod.ZipFile(io.BytesIO(r.data))
        self.assertTrue(any('main.tf' in n for n in z.namelist()))

    def test_download_gcp_main_tf_has_google_provider(self):
        import io, zipfile as zf_mod
        r = self.client.post('/api/download', json=self.base, content_type='application/json')
        z = zf_mod.ZipFile(io.BytesIO(r.data))
        main = next(n for n in z.namelist() if n.endswith('main.tf') and 'modules' not in n)
        self.assertIn('hashicorp/google', z.read(main).decode())

    def test_tf_validate_gcp_returns_200(self):
        r = self.client.post('/api/tf-validate', json=self.base, content_type='application/json')
        self.assertEqual(r.status_code, 200)

    def test_tf_validate_gcp_cloud_field(self):
        r = self.client.post('/api/tf-validate', json=self.base, content_type='application/json')
        self.assertEqual(r.get_json()['cloud'], 'gcp')

    def test_validate_gcp_tab13_pass(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'gcp', 'tab': 13,
            'gcp_clusters': [{'module_name': 'gc', 'cloud_vm_cluster_id': 'cl',
                               'display_name': 'My Cluster',
                               'location': 'us-east4', 'hostname_prefix': 'vm',
                               'cpu_core_count': 16,
                               'ssh_public_keys': ['ssh-rsa AAA']}],
        })
        self.assertTrue(r.get_json()['valid'])

    def test_validate_gcp_tab13_missing_hostname(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'gcp', 'tab': 13,
            'gcp_clusters': [{'module_name': 'gc', 'cloud_vm_cluster_id': 'cl',
                               'location': 'us-east4',
                               'cpu_core_count': 16,
                               'ssh_public_keys': ['ssh-rsa AAA']}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('hostname_prefix', d['errors'])

    def test_validate_gcp_tab13_no_ssh_key(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'gcp', 'tab': 13,
            'gcp_clusters': [{'module_name': 'gc', 'cloud_vm_cluster_id': 'cl',
                               'location': 'us-east4', 'hostname_prefix': 'vm',
                               'cpu_core_count': 16,
                               'ssh_public_keys': []}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('ssh_public_keys', d['errors'])


# ══════════════════════════════════════════════════════════════════════════════
#  tf_validator — GCP
# ══════════════════════════════════════════════════════════════════════════════

class TestTfValidateGcp(unittest.TestCase):

    def _gen(self, net_count=1, infra_count=1, cluster_count=1):
        nets     = [gcp_net(f'tn-{i}')   for i in range(net_count)]
        infras   = [gcp_infra(f'ti-{i}') for i in range(infra_count)]
        clusters = [gcp_cluster(f'tc-{i}', 'tn-0', 'ti-0') for i in range(cluster_count)]
        return generate_gcp_tf({'cloud': 'gcp',
                                 'gcp_networks': nets,
                                 'gcp_infras':   infras,
                                 'gcp_clusters': clusters})

    def _fails(self, files):
        return [r for r in validate_terraform(files, 'gcp') if r.status == 'fail']

    def test_valid_gcp_has_no_failures(self):
        fails = self._fails(self._gen())
        self.assertEqual(fails, [],
            msg='\n'.join(f'{f.group} / {f.name}: {f.error}' for f in fails))

    def test_valid_gcp_passes_provider_check(self):
        results = validate_terraform(self._gen(), 'gcp')
        ok = [r for r in results if r.group == 'Provider' and 'google' in r.name and r.status == 'pass']
        self.assertTrue(len(ok) > 0)

    def test_valid_gcp_passes_file_structure(self):
        results = validate_terraform(self._gen(), 'gcp')
        fails = [r for r in results if r.group == 'File Structure' and r.status == 'fail']
        self.assertEqual(fails, [])

    def test_valid_gcp_passes_hcl_syntax(self):
        results = validate_terraform(self._gen(), 'gcp')
        fails = [r for r in results if r.group == 'HCL Syntax' and r.status == 'fail']
        self.assertEqual(fails, [])

    def test_missing_root_main_detected(self):
        files = self._gen()
        del files['main.tf']
        self.assertTrue(any('main.tf' in f.name for f in self._fails(files)))

    def test_missing_module_file_detected(self):
        files = self._gen()
        del files[f'modules/{_GCP_MOD_NET}/main.tf']
        self.assertTrue(any(_GCP_MOD_NET in f.name for f in self._fails(files)))

    def test_wrong_provider_detected(self):
        files = self._gen()
        files['main.tf'] = files['main.tf'].replace('hashicorp/google', 'hashicorp/aws')
        self.assertTrue(any('google' in f.name for f in self._fails(files)))

    def test_odb_network_resource_in_module(self):
        files = self._gen()
        self.assertIn('google_oracle_database_odb_network',
                      files[f'modules/{_GCP_MOD_NET}/main.tf'])

    def test_exadata_infra_resource_in_module(self):
        files = self._gen()
        self.assertIn('google_oracle_database_cloud_exadata_infrastructure',
                      files[f'modules/{_GCP_MOD_INFRA}/main.tf'])

    def test_vm_cluster_resource_in_module(self):
        files = self._gen()
        self.assertIn('google_oracle_database_cloud_vm_cluster',
                      files[f'modules/{_GCP_MOD_CLUSTER}/main.tf'])

    def test_multi_resource_keeps_fixed_file_count(self):
        files = self._gen(net_count=2, infra_count=2, cluster_count=2)
        self.assertEqual(len(files), 13)

    def test_summary_structure_complete(self):
        s = summarise(validate_terraform(self._gen(), 'gcp'))
        for key in ('passed', 'failed', 'warned', 'total', 'results'):
            self.assertIn(key, s)

    def test_summary_passed_greater_than_zero(self):
        s = summarise(validate_terraform(self._gen(), 'gcp'))
        self.assertGreater(s['passed'], 0)


# ══════════════════════════════════════════════════════════════════════════════
#  Customer-managed TDE key in Google Cloud KMS (gcp_kms_keys)
#  Two standalone roots under kms/<name>/ - gcp/ and oci/ - applied after the
#  VM cluster exists. Built from the reference exadb-d-gcp-kms project.
# ══════════════════════════════════════════════════════════════════════════════

def _kms_payload(*keys, iac_tool='terraform'):
    return {'cloud': 'gcp', 'iac_tool': iac_tool,
            'gcp_networks': [{'module_name': 'n1', 'location': 'europe-west3', 'project': 'acme-prod'}],
            'gcp_clusters': [{'module_name': 'vmc1'}],
            'gcp_kms_keys': list(keys)}


class TestGcpKmsGeneration(unittest.TestCase):

    def test_no_card_generates_nothing_new(self):
        files = generate_gcp_tf(_kms_payload())
        self.assertFalse([k for k in files if k.startswith('kms/')])
        self.assertNotIn('Customer-managed TDE keys', files['README.md'])

    def test_two_standalone_roots_and_a_readme(self):
        files = generate_gcp_tf(_kms_payload({'module_name': 'tde'}))
        for side in ('gcp', 'oci'):
            for f in ('versions.tf', 'variables.tf', 'main.tf', 'outputs.tf', 'terraform.tfvars'):
                self.assertIn(f'kms/tde/{side}/{f}', files)
        self.assertIn('kms/tde/README.md', files)
        # Not a module of the main root: the crypto key's prevent_destroy must
        # not be able to block destroying the environment.
        self.assertNotIn('google_kms', files['main.tf'])
        self.assertIn('prevent_destroy = true', files['kms/tde/gcp/main.tf'])

    def test_defaults_come_from_the_cluster_and_the_region_catalogue(self):
        files = generate_gcp_tf(_kms_payload({'module_name': 'tde'}))
        gcp, oci = files['kms/tde/gcp/terraform.tfvars'], files['kms/tde/oci/terraform.tfvars']
        self.assertIn('gcp_project_id       = "acme-prod"', gcp)
        self.assertIn('gcp_kms_location     = "europe-west3"', gcp)
        self.assertIn('oci_multicloud_region = "eu-frankfurt-1"', oci)   # catalogue pairing
        # Known before anything is applied - no hand-off from the GCP output.
        self.assertIn('gcp_key_ring_id  = "projects/acme-prod/locations/europe-west3/keyRings/exadb-tde"', oci)

    def test_values_only_known_after_provisioning_are_placeholders(self):
        files = generate_gcp_tf(_kms_payload({'module_name': 'tde'}))
        self.assertIn('oracle_workload_resource_service_agent = "CHANGEME"', files['kms/tde/gcp/terraform.tfvars'])
        oci = files['kms/tde/oci/terraform.tfvars']
        for key in ('oci_gcp_identity_connector_ocid', 'oci_compartment_ocid'):
            self.assertRegex(oci, rf'{key}\s*=\s*"CHANGEME"')

    def test_role_ids_are_unique_per_card(self):
        # The custom role is project-wide; two cards sharing an ID collide on create.
        files = generate_gcp_tf(_kms_payload({'module_name': 'a'}, {'module_name': 'b'}))
        self.assertIn('oracle_kms_role_id   = "oracleExadbKms_a"', files['kms/a/gcp/terraform.tfvars'])
        self.assertIn('oracle_kms_role_id   = "oracleExadbKms_b"', files['kms/b/gcp/terraform.tfvars'])

    def test_oci_root_adds_the_rest_prefix_and_uses_the_home_region_for_iam(self):
        files = generate_gcp_tf(_kms_payload({'module_name': 'tde'}))
        main, versions = files['kms/tde/oci/main.tf'], files['kms/tde/oci/versions.tf']
        self.assertIn('gcp_key_ring_id = "https://cloudkms.googleapis.com/v1/${var.gcp_key_ring_id}"', main)
        self.assertIn('provider = oci.home', main)
        self.assertIn('alias               = "home"', versions)

    def test_provider_floors(self):
        # oracle/oci 7.17.0 added oci_dbmulticloud_oracle_db_gcp_key_ring
        # (7.16.0 fails validate with "Invalid resource type").
        files = generate_gcp_tf(_kms_payload({'module_name': 'tde'}))
        self.assertIn('version = ">= 7.17.0"', files['kms/tde/oci/versions.tf'])
        self.assertIn('version = ">= 7.5.0"', files['kms/tde/gcp/versions.tf'])

    def test_the_policy_is_optional(self):
        off = generate_gcp_tf(_kms_payload({'module_name': 'tde'}))['kms/tde/oci/terraform.tfvars']
        on = generate_gcp_tf(_kms_payload({'module_name': 'tde', 'create_cluster_gcp_key_policy': True}))['kms/tde/oci/terraform.tfvars']
        self.assertIn('create_cluster_gcp_key_policy = false', off)
        self.assertIn('create_cluster_gcp_key_policy = true', on)

    def test_formatted(self):
        import shutil, subprocess, tempfile
        tf = shutil.which('terraform') or shutil.which('tofu')
        if not tf:
            self.skipTest('terraform/tofu not found in PATH')
        for tool in ('terraform', 'opentofu'):
            files = generate_gcp_tf(_kms_payload({'module_name': 'tde'},
                                                 {'module_name': 'tde2', 'create_cluster_gcp_key_policy': True,
                                                  'key_protection_level': 'SOFTWARE'}, iac_tool=tool))
            with tempfile.TemporaryDirectory() as tmp, self.subTest(tool=tool):
                for rel, content in files.items():
                    if rel.startswith('kms/') and rel.endswith(('.tf', '.tfvars')):
                        q = Path(tmp) / rel
                        q.parent.mkdir(parents=True, exist_ok=True)
                        q.write_text(content + '\n', encoding='utf-8')
                r = subprocess.run([tf, 'fmt', '-check', '-recursive', '-diff', tmp], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestGcpKmsValidation(unittest.TestCase):

    GOOD = {'module_name': 'tde', 'cluster_ref': 'c1',
            'oracle_workload_resource_service_agent': 'service-1@gcp-sa-oracle.iam.gserviceaccount.com',
            'oci_gcp_identity_connector_ocid': 'ocid1.oracledbgcpidentityconnector.oc1..aaaa',
            'oci_compartment_ocid': 'ocid1.compartment.oc1..aaaa', 'oci_home_region': 'us-ashburn-1'}

    def _errs(self, **kw):
        import clouds.gcp.validator as v
        errors = {}
        v.validate({'tab': 16, 'gcp_clusters': [{'module_name': 'c1', 'project': 'acme-prod'}],
                    'gcp_kms_keys': [{**self.GOOD, **kw}]}, errors)
        return errors.get('tde', {})

    def test_a_complete_card_is_valid(self):
        self.assertEqual(self._errs(gcp_project_id='acme-prod'), {})

    def test_connector_must_not_be_a_compartment(self):
        # The reference guide's most common failure.
        errs = self._errs(oci_gcp_identity_connector_ocid='ocid1.compartment.oc1..aaaa')
        self.assertIn('compartment', errs['oci_gcp_identity_connector_ocid'])

    def test_values_from_the_identity_connector_are_required(self):
        for field in ('oracle_workload_resource_service_agent', 'oci_gcp_identity_connector_ocid',
                      'oci_compartment_ocid', 'oci_home_region'):
            for blank in ('', 'CHANGEME'):
                with self.subTest(field=field, value=blank):
                    self.assertIn(field, self._errs(**{field: blank}))

    def test_formats(self):
        self.assertIn('oracle_workload_resource_service_agent', self._errs(oracle_workload_resource_service_agent='me@gmail.com'))
        self.assertIn('gcp_project_id', self._errs(gcp_project_id='Bad_Project'))
        self.assertIn('gcp_key_ring_name', self._errs(gcp_key_ring_name='has space'))
        self.assertIn('oracle_kms_role_id', self._errs(oracle_kms_role_id='x'))
        self.assertIn('oci_home_region', self._errs(oci_home_region='ashburn'))
        self.assertIn('oci_compartment_ocid', self._errs(oci_compartment_ocid='ocid1.vcn.oc1..x'))

    def test_project_required_unless_derivable(self):
        import clouds.gcp.validator as v
        def errs(clusters, nets, **kw):
            e = {}
            v.validate({'tab': 16, 'gcp_clusters': clusters, 'gcp_networks': nets,
                        'gcp_kms_keys': [{**self.GOOD, **kw}]}, e)
            return e.get('tde', {})
        self.assertIn('gcp_project_id', errs([{'module_name': 'c1'}], []))
        self.assertNotIn('gcp_project_id', errs([{'module_name': 'c1', 'project': 'acme-prod'}], []))
        self.assertNotIn('gcp_project_id', errs([{'module_name': 'c1'}], [{'module_name': 'n', 'project': 'acme-prod'}]))
        self.assertNotIn('gcp_project_id', errs([{'module_name': 'c1'}], [], gcp_project_id='acme-prod'))

    def test_cluster_must_exist(self):
        self.assertIn('cluster_ref', self._errs(cluster_ref='gone'))


if __name__ == '__main__':
    unittest.main()
