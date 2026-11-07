"""
Azure AI DB@Azure tests — self-contained, no AWS or GCP dependencies.
Run with:  python -m unittest tests/test_azure.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import (
    app, generate_all,
    azure_vnet_main, azure_vnet_vars, azure_vnet_outputs, azure_vnet_tfvars,
    azure_infra_main, azure_infra_vars, azure_infra_outputs, azure_infra_tfvars,
    azure_cluster_main, azure_cluster_vars, azure_cluster_outputs, azure_cluster_tfvars,
    azure_build_root_main, azure_build_root_vars, azure_build_root_tfvars,
    _azure_vnet_defaults, _azure_infra_defaults, _azure_cluster_defaults,
    generate_azure_tf,
)
from tf_validator import validate_terraform, summarise


# ══════════════════════════════════════════════════════════════════════════════
#  FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

def azure_vnet(module_name='azure_vnet', **kw):
    return {
        'module_name':           module_name,
        'resource_group_name':   'my-rg',
        'location':              'eastus',
        'vnet_name':             'my-vnet',
        'address_space':         '10.0.0.0/16',
        'subnet_name':           'oracle-delegated',
        'subnet_address_prefix': '10.0.1.0/24',
        'tags': {'env': 'test'},
        **kw,
    }

def azure_infra(module_name='azure_exainfra', **kw):
    return {
        'module_name':           module_name,
        'resource_group_name':   'my-rg',
        'location':              'eastus',
        'name':                  'my-exainfra',
        'display_name':          'My Exadata',
        'shape':                 'Exadata.X11M',
        'compute_count':         2,
        'storage_count':         3,
        'zone':                  '1',
        'mw_preference':         'NoPreference',
        'mw_patching_mode':      'Rolling',
        'mw_lead_time_in_weeks': 0,
        'mw_days_of_week':       '',
        'mw_hours_of_day':       '',
        'mw_weeks_of_month':     '',
        'mw_months':             '',
        'customer_contacts':     [],
        'tags': {},
        **kw,
    }

def azure_cluster(module_name='azure_vmcluster', vnet_ref='azure_vnet', infra_ref='azure_exainfra', **kw):
    return {
        'module_name':                    module_name,
        'resource_group_name':            'my-rg',
        'location':                       'eastus',
        'name':                           'my-vmcluster',
        'display_name':                   'My VM Cluster',
        'cloud_exadata_infrastructure_id': '',
        'subnet_id':                      '',
        'vnet_id':                        '',
        'hostname':                       'myhost',
        'cpu_core_count':                 4,
        'data_storage_size_in_tbs':       2.0,
        'db_node_storage_size_in_gbs':    120,
        'memory_size_in_gbs':             60,
        'ssh_public_keys':                ['ssh-rsa AAAAB3Nz test@host'],
        'gi_version':                     '19.0.0.0',
        'license_model':                  'LicenseIncluded',
        'cluster_name':                   '',
        'domain':                         '',
        'backup_subnet_cidr':             '',
        'data_storage_percentage':        100,
        'local_backup_enabled':           False,
        'sparse_diskgroup_enabled':       False,
        'time_zone':                      'UTC',
        'db_servers':                     [],
        'scan_listener_port_tcp':         1521,
        'dco_diagnostics_events_enabled': True,
        'dco_health_monitoring_enabled':  True,
        'dco_incident_logs_enabled':      True,
        'infra_ref':                      infra_ref,
        'vnet_ref':                       vnet_ref,
        'tags': {},
        **kw,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  VNet Module
# ══════════════════════════════════════════════════════════════════════════════

class TestAzureVnetModule(unittest.TestCase):

    def setUp(self):
        self.mn = 'azure_vnet'
        self.d  = _azure_vnet_defaults(azure_vnet(self.mn))

    def test_main_contains_vnet_resource(self):
        out = azure_vnet_main(self.mn, self.d)
        self.assertIn('azurerm_virtual_network', out)

    def test_main_contains_subnet_resource(self):
        out = azure_vnet_main(self.mn, self.d)
        self.assertIn('azurerm_subnet', out)

    def test_main_contains_oracle_delegation(self):
        out = azure_vnet_main(self.mn, self.d)
        self.assertIn('Oracle.Database/networkAttachments', out)

    def test_main_uses_var_vnet_name(self):
        out = azure_vnet_main(self.mn, self.d)
        self.assertIn('var.vnet_name', out)

    def test_main_uses_var_address_space(self):
        out = azure_vnet_main(self.mn, self.d)
        self.assertIn('var.address_space', out)

    def test_vars_contains_location(self):
        out = azure_vnet_vars(self.mn, self.d)
        self.assertIn('location', out)

    def test_vars_contains_subnet_prefix(self):
        out = azure_vnet_vars(self.mn, self.d)
        self.assertIn('subnet_address_prefix', out)

    def test_outputs_contains_vnet_id(self):
        out = azure_vnet_outputs(self.mn)
        self.assertIn('vnet_id', out)

    def test_outputs_contains_subnet_id(self):
        out = azure_vnet_outputs(self.mn)
        self.assertIn('subnet_id', out)

    def test_tfvars_contains_vnet_name_value(self):
        out = azure_vnet_tfvars(self.mn, self.d)
        self.assertIn('my-vnet', out)

    def test_tfvars_contains_address_space_value(self):
        out = azure_vnet_tfvars(self.mn, self.d)
        self.assertIn('10.0.0.0/16', out)

    def test_tfvars_contains_subnet_prefix_value(self):
        out = azure_vnet_tfvars(self.mn, self.d)
        self.assertIn('10.0.1.0/24', out)

    def test_main_has_azurerm_provider(self):
        out = azure_vnet_main(self.mn, self.d)
        self.assertIn('hashicorp/azurerm', out)


# ══════════════════════════════════════════════════════════════════════════════
#  Exadata Infrastructure Module
# ══════════════════════════════════════════════════════════════════════════════

class TestAzureInfraModule(unittest.TestCase):

    def setUp(self):
        self.mn = 'azure_exainfra'
        self.d  = _azure_infra_defaults(azure_infra(self.mn))

    def test_main_contains_correct_resource_type(self):
        out = azure_infra_main(self.mn, self.d)
        self.assertIn('azurerm_oracle_exadata_infrastructure', out)

    def test_main_does_not_contain_old_resource_type(self):
        out = azure_infra_main(self.mn, self.d)
        self.assertNotIn('azurerm_oracle_cloud_exadata_infrastructure', out)

    def test_main_uses_var_shape(self):
        out = azure_infra_main(self.mn, self.d)
        self.assertIn('var.shape', out)

    def test_main_uses_var_compute_count(self):
        out = azure_infra_main(self.mn, self.d)
        self.assertIn('var.compute_count', out)

    def test_main_uses_var_storage_count(self):
        out = azure_infra_main(self.mn, self.d)
        self.assertIn('var.storage_count', out)

    def test_main_contains_maintenance_window(self):
        out = azure_infra_main(self.mn, self.d)
        self.assertIn('maintenance_window', out)

    def test_vars_contains_shape(self):
        out = azure_infra_vars(self.mn, self.d)
        self.assertIn('shape', out)

    def test_vars_contains_zone(self):
        out = azure_infra_vars(self.mn, self.d)
        self.assertIn('zone', out)

    def test_outputs_contains_infra_id(self):
        out = azure_infra_outputs(self.mn)
        self.assertIn('infra_id', out)

    def test_outputs_references_correct_resource(self):
        out = azure_infra_outputs(self.mn)
        self.assertIn('azurerm_oracle_exadata_infrastructure.this', out)

    def test_tfvars_contains_shape_value(self):
        out = azure_infra_tfvars(self.mn, self.d)
        self.assertIn('Exadata.X11M', out)

    def test_tfvars_contains_name_value(self):
        out = azure_infra_tfvars(self.mn, self.d)
        self.assertIn('my-exainfra', out)

    def test_main_has_azurerm_provider(self):
        out = azure_infra_main(self.mn, self.d)
        self.assertIn('hashicorp/azurerm', out)


# ══════════════════════════════════════════════════════════════════════════════
#  VM Cluster Module
# ══════════════════════════════════════════════════════════════════════════════

class TestAzureVmClusterModule(unittest.TestCase):

    def setUp(self):
        self.mn = 'azure_vmcluster'
        self.d  = _azure_cluster_defaults(azure_cluster(self.mn), 'azure_vnet', 'azure_exainfra')

    def test_main_contains_vm_cluster_resource(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('azurerm_oracle_cloud_vm_cluster', out)

    def test_main_uses_var_hostname(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('var.hostname', out)

    def test_main_uses_var_cpu_core_count(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('var.cpu_core_count', out)

    def test_main_uses_var_gi_version(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('var.gi_version', out)

    def test_main_uses_var_ssh_public_keys(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('var.ssh_public_keys', out)

    def test_main_uses_var_subnet_id(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('var.subnet_id', out)

    def test_main_uses_var_virtual_network_id(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('var.virtual_network_id', out)

    def test_main_uses_var_infra_id(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('var.cloud_exadata_infrastructure_id', out)

    def test_main_contains_data_collection_options(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('data_collection_options', out)

    def test_vars_contains_license_model(self):
        out = azure_cluster_vars(self.mn, self.d)
        self.assertIn('license_model', out)

    def test_vars_contains_data_storage_size(self):
        out = azure_cluster_vars(self.mn, self.d)
        self.assertIn('data_storage_size_in_tbs', out)

    def test_outputs_contains_cluster_id(self):
        out = azure_cluster_outputs(self.mn)
        self.assertIn('cluster_id', out)

    def test_outputs_contains_ocid(self):
        out = azure_cluster_outputs(self.mn)
        self.assertIn('ocid', out)

    def test_tfvars_contains_gi_version_value(self):
        out = azure_cluster_tfvars(self.mn, self.d)
        self.assertIn('19.0.0.0', out)

    def test_tfvars_contains_license_model_value(self):
        out = azure_cluster_tfvars(self.mn, self.d)
        self.assertIn('LicenseIncluded', out)

    def test_main_has_azurerm_provider(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('hashicorp/azurerm', out)

    # backup_subnet_cidr is Optional + ForceNew but not Computed. If the config
    # leaves it empty the service writes its own default into state and every
    # later plan proposes replacing the cluster, so it must always be explicit.

    def test_blank_backup_subnet_cidr_gets_service_default(self):
        d = _azure_cluster_defaults(azure_cluster(self.mn, backup_subnet_cidr=''))
        self.assertEqual(d['backup_subnet_cidr'], '192.168.252.0/22')

    def test_explicit_backup_subnet_cidr_preserved(self):
        d = _azure_cluster_defaults(azure_cluster(self.mn, backup_subnet_cidr='10.9.0.0/22'))
        self.assertEqual(d['backup_subnet_cidr'], '10.9.0.0/22')

    def test_main_never_nulls_backup_subnet_cidr(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('backup_subnet_cidr         = var.backup_subnet_cidr', out)
        self.assertNotIn('var.backup_subnet_cidr != ""', out)

    def test_vars_backup_subnet_cidr_default_never_empty(self):
        out = azure_cluster_vars(self.mn, self.d)
        self.assertNotIn('variable "backup_subnet_cidr" {\n  type        = string\n  default     = ""', out)
        self.assertIn('192.168.252.0/22', out)

    def test_tfvars_always_emits_backup_subnet_cidr(self):
        out = azure_cluster_tfvars(self.mn, self.d)
        self.assertIn('backup_subnet_cidr        = "192.168.252.0/22"', out)

    # The provider's Read writes whatever the API reports into state, and the
    # attribute is ForceNew, so an API-side normalisation would otherwise plan a
    # replacement of the cluster on every run.

    def test_lifecycle_guard_always_emitted(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn('lifecycle {', out)
        self.assertIn('ignore_changes = [', out)

    # Only the optional arguments that are ForceNew *without* being Computed can
    # diff against an empty config. The Computed ones adopt the state value when
    # config omits them, so guarding them would cost drift detection for nothing.

    def test_guards_the_three_non_computed_forcenew_args(self):
        out = azure_cluster_main(self.mn, self.d)
        for arg in ('backup_subnet_cidr', 'gi_version',
                    'scan_listener_port_tcp_ssl'):
            self.assertRegex(out, rf'\n      {arg},')

    def test_computed_args_are_not_guarded(self):
        out = azure_cluster_main(self.mn, self.d)
        for arg in ('cluster_name', 'domain', 'time_zone', 'zone_id'):
            self.assertNotRegex(out, rf'\n      {arg},')

    def test_ssl_port_guard_dropped_when_port_is_explicit(self):
        d = _azure_cluster_defaults(
            azure_cluster(self.mn, scan_listener_port_tcp_ssl=2484))
        out = azure_cluster_main(self.mn, d)
        self.assertNotRegex(out, r'\n      scan_listener_port_tcp_ssl,')
        self.assertRegex(out, r'\n      gi_version,')

    def test_operator_drift_candidates_emitted_commented(self):
        out = azure_cluster_main(self.mn, self.d)
        for arg in ('system_version', 'cpu_core_count', 'ssh_public_keys',
                    'data_storage_size_in_tbs', 'memory_size_in_gbs',
                    'db_node_storage_size_in_gbs'):
            self.assertIn(f'# {arg},', out)

    def test_no_ui_toggle_keys_leak_into_context(self):
        d = _azure_cluster_defaults({'module_name': self.mn})
        self.assertNotIn('ignore_backup_subnet_cidr_drift', d)
        self.assertNotIn('ignore_gi_version_drift', d)

    def test_lifecycle_guard_names_replace_command(self):
        out = azure_cluster_main(self.mn, self.d)
        self.assertIn(
            f'-replace=module.{self.mn}.azurerm_oracle_cloud_vm_cluster.this', out)



# ══════════════════════════════════════════════════════════════════════════════
#  Azure Root
# ══════════════════════════════════════════════════════════════════════════════

class TestAzureRoot(unittest.TestCase):

    def _build(self, vnet_count=1, infra_count=1, cluster_count=1):
        vnets    = [_azure_vnet_defaults(azure_vnet(f'avnet_{i}'))    for i in range(vnet_count)]
        infras   = [_azure_infra_defaults(azure_infra(f'ainf_{i}'))   for i in range(infra_count)]
        clusters = [_azure_cluster_defaults(
                        azure_cluster(f'acl_{i}', 'avnet_0', 'ainf_0'),
                        'avnet_0', 'ainf_0')
                    for i in range(cluster_count)]
        return vnets, infras, clusters

    def test_root_main_contains_azurerm_provider(self):
        vs, ins, cls = self._build()
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('hashicorp/azurerm', out)

    def test_root_main_does_not_contain_other_providers(self):
        vs, ins, cls = self._build()
        out = azure_build_root_main(vs, ins, cls)
        self.assertNotIn('hashicorp/google', out)
        self.assertNotIn('hashicorp/aws', out)

    def test_root_main_has_vnet_module(self):
        vs, ins, cls = self._build()
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('module "avnet_0"', out)

    def test_root_main_has_infra_module(self):
        vs, ins, cls = self._build()
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('module "ainf_0"', out)

    def test_root_main_has_cluster_module(self):
        vs, ins, cls = self._build()
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('module "acl_0"', out)

    def test_root_main_cluster_wired_to_infra(self):
        vs, ins, cls = self._build()
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('module.ainf_0.infra_id', out)

    def test_root_main_cluster_wired_to_subnet(self):
        vs, ins, cls = self._build()
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('module.avnet_0.subnet_id', out)

    def test_root_main_cluster_wired_to_vnet(self):
        vs, ins, cls = self._build()
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('module.avnet_0.vnet_id', out)

    def test_root_main_cluster_has_depends_on(self):
        vs, ins, cls = self._build()
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('depends_on', out)

    def test_root_main_multi_vnet(self):
        vs, ins, cls = self._build(vnet_count=2)
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('module "avnet_0"', out)
        self.assertIn('module "avnet_1"', out)

    def test_root_main_multi_infra(self):
        vs, ins, cls = self._build(infra_count=2)
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('module "ainf_0"', out)
        self.assertIn('module "ainf_1"', out)

    def test_root_main_multi_cluster(self):
        vs, ins, cls = self._build(cluster_count=2)
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('module "acl_0"', out)
        self.assertIn('module "acl_1"', out)

    def test_root_tfvars_contains_subscription_id(self):
        vs, ins, cls = self._build()
        out = azure_build_root_tfvars(vs, ins, cls, subscription_id='sub-123')
        self.assertIn('sub-123', out)

    def test_root_vars_contains_subscription_id_var(self):
        vs, ins, cls = self._build()
        out = azure_build_root_vars(vs, ins, cls)
        self.assertIn('subscription_id', out)

    def test_root_main_outputs_vnet_id(self):
        vs, ins, cls = self._build()
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('vnet_id', out)

    def test_root_main_outputs_infra_id(self):
        vs, ins, cls = self._build()
        out = azure_build_root_main(vs, ins, cls)
        self.assertIn('infra_id', out)


# ══════════════════════════════════════════════════════════════════════════════
#  generate_all — Azure
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateAllAzure(unittest.TestCase):

    def _base(self, vnet_count=1, infra_count=1, cluster_count=1):
        return {
            'cloud': 'azure',
            'azure_vnets':    [azure_vnet(f'av{i}')    for i in range(vnet_count)],
            'azure_infras':   [azure_infra(f'ai{i}')   for i in range(infra_count)],
            'azure_clusters': [azure_cluster(f'ac{i}', 'av0', 'ai0') for i in range(cluster_count)],
        }

    def test_returns_root_main(self):
        self.assertIn('main.tf', generate_all(self._base()))

    def test_returns_root_tfvars(self):
        self.assertIn('terraform.auto.tfvars', generate_all(self._base()))

    def test_returns_root_variables(self):
        self.assertIn('variables.tf', generate_all(self._base()))

    def test_vnet_module_files_generated(self):
        files = generate_all(self._base())
        for f in ['main.tf', 'variables.tf', 'outputs.tf']:
            self.assertIn(f'modules/av0/{f}', files)

    def test_infra_module_files_generated(self):
        files = generate_all(self._base())
        for f in ['main.tf', 'variables.tf', 'outputs.tf']:
            self.assertIn(f'modules/ai0/{f}', files)

    def test_cluster_module_files_generated(self):
        files = generate_all(self._base())
        for f in ['main.tf', 'variables.tf', 'outputs.tf']:
            self.assertIn(f'modules/ac0/{f}', files)

    def test_file_count_one_of_each(self):
        # 3 modules × 3 files + 3 root files = 12
        self.assertEqual(len(generate_all(self._base())), 12)

    def test_file_count_two_vnets(self):
        # 4 modules × 3 files + 3 root = 15
        self.assertEqual(len(generate_all(self._base(vnet_count=2))), 15)

    def test_file_count_two_clusters(self):
        # 4 modules × 3 files + 3 root = 15
        self.assertEqual(len(generate_all(self._base(cluster_count=2))), 15)

    def test_root_main_has_azurerm_provider(self):
        files = generate_all(self._base())
        self.assertIn('hashicorp/azurerm', files['main.tf'])

    def test_root_main_has_no_other_provider(self):
        files = generate_all(self._base())
        self.assertNotIn('hashicorp/google', files['main.tf'])
        self.assertNotIn('hashicorp/aws', files['main.tf'])

    def test_infra_module_uses_correct_resource_type(self):
        files = generate_all(self._base())
        self.assertIn('azurerm_oracle_exadata_infrastructure', files['modules/ai0/main.tf'])
        self.assertNotIn('azurerm_oracle_cloud_exadata_infrastructure', files['modules/ai0/main.tf'])

    def test_cluster_module_uses_correct_resource_type(self):
        files = generate_all(self._base())
        self.assertIn('azurerm_oracle_cloud_vm_cluster', files['modules/ac0/main.tf'])

    def test_vnet_module_has_oracle_delegation(self):
        files = generate_all(self._base())
        self.assertIn('Oracle.Database/networkAttachments', files['modules/av0/main.tf'])

    def test_cluster_cross_wired_to_correct_infra(self):
        files = generate_all({
            'cloud': 'azure',
            'azure_vnets':    [azure_vnet('vnet_a'), azure_vnet('vnet_b')],
            'azure_infras':   [azure_infra('inf_prod'), azure_infra('inf_dev')],
            'azure_clusters': [
                azure_cluster('cl_prod', vnet_ref='vnet_a', infra_ref='inf_prod'),
                azure_cluster('cl_dev',  vnet_ref='vnet_b', infra_ref='inf_dev'),
            ],
        })
        root = files['main.tf']
        self.assertIn('module.inf_prod.infra_id', root)
        self.assertIn('module.inf_dev.infra_id', root)
        self.assertIn('module.vnet_b.subnet_id', root)

    def test_all_files_non_empty(self):
        files = generate_all(self._base())
        for path, content in files.items():
            self.assertGreater(len(content.strip()), 0, f'{path} is empty')

    def test_all_tf_files_have_braces(self):
        files = generate_all(self._base())
        for path, content in files.items():
            if path.endswith('.tf'):
                self.assertIn('{', content, f'{path} missing opening brace')


# ══════════════════════════════════════════════════════════════════════════════
#  Azure Default Normalisers
# ══════════════════════════════════════════════════════════════════════════════

class TestAzureDefaultNormalisers(unittest.TestCase):

    def test_vnet_defaults_location_fallback(self):
        self.assertEqual(_azure_vnet_defaults({})['location'], 'eastus')

    def test_vnet_defaults_address_space_fallback(self):
        self.assertEqual(_azure_vnet_defaults({})['address_space'], '10.0.0.0/16')

    def test_vnet_defaults_preserves_location(self):
        d = _azure_vnet_defaults({'location': 'westeurope'})
        self.assertEqual(d['location'], 'westeurope')

    def test_infra_defaults_shape_fallback(self):
        self.assertEqual(_azure_infra_defaults({})['shape'], 'Exadata.X11M')

    def test_infra_defaults_compute_count_int(self):
        d = _azure_infra_defaults({'compute_count': '4', 'storage_count': '5'})
        self.assertEqual(d['compute_count'], 4)
        self.assertEqual(d['storage_count'], 5)

    def test_infra_defaults_fallback_counts(self):
        d = _azure_infra_defaults({})
        self.assertEqual(d['compute_count'], 2)
        self.assertEqual(d['storage_count'], 3)

    def test_cluster_defaults_infra_ref_fallback(self):
        d = _azure_cluster_defaults({}, first_vnet_name='vnet_a', first_infra_name='inf_a')
        self.assertEqual(d['infra_ref'], 'inf_a')
        self.assertEqual(d['vnet_ref'],  'vnet_a')

    def test_cluster_defaults_cpu_int(self):
        d = _azure_cluster_defaults({'cpu_core_count': '8'})
        self.assertEqual(d['cpu_core_count'], 8)

    def test_cluster_defaults_storage_float(self):
        d = _azure_cluster_defaults({'data_storage_size_in_tbs': '4'})
        self.assertAlmostEqual(d['data_storage_size_in_tbs'], 4.0)

    def test_cluster_defaults_ssh_keys_list(self):
        d = _azure_cluster_defaults({'ssh_public_keys': ['ssh-rsa AAA']})
        self.assertEqual(d['ssh_public_keys'], ['ssh-rsa AAA'])


# ══════════════════════════════════════════════════════════════════════════════
#  API Routes — Azure
# ══════════════════════════════════════════════════════════════════════════════

class TestApiRoutesAzure(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.base = {
            'cloud': 'azure',
            'azure_vnets':    [azure_vnet('av1')],
            'azure_infras':   [azure_infra('ai1')],
            'azure_clusters': [azure_cluster('ac1', 'av1', 'ai1')],
        }

    def test_azure_page_returns_200(self):
        r = self.client.get('/azure')
        self.assertEqual(r.status_code, 200)

    def test_azure_page_contains_azurerm(self):
        r = self.client.get('/azure')
        self.assertIn(b'azurerm', r.data)

    def test_azure_page_no_cache_header(self):
        r = self.client.get('/azure')
        self.assertIn('no-cache', r.headers.get('Cache-Control', ''))

    def test_generate_azure_root_main_has_provider(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': 'main.tf'},
            content_type='application/json')
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertIn('hashicorp/azurerm', d['content'])

    def test_generate_azure_root_tfvars(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': 'terraform.auto.tfvars'},
            content_type='application/json')
        self.assertIn('content', r.get_json())

    def test_generate_azure_vnet_module_main(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': 'modules/av1/main.tf'},
            content_type='application/json')
        self.assertIn('azurerm_virtual_network', r.get_json()['content'])

    def test_generate_azure_infra_module_main(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': 'modules/ai1/main.tf'},
            content_type='application/json')
        content = r.get_json()['content']
        self.assertIn('azurerm_oracle_exadata_infrastructure', content)
        self.assertNotIn('azurerm_oracle_cloud_exadata_infrastructure', content)

    def test_generate_azure_cluster_module_main(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': 'modules/ac1/main.tf'},
            content_type='application/json')
        self.assertIn('azurerm_oracle_cloud_vm_cluster', r.get_json()['content'])

    def test_generate_azure_module_variables(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': 'modules/av1/variables.tf'},
            content_type='application/json')
        self.assertIn('variable', r.get_json()['content'])

    def test_generate_azure_module_outputs(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': 'modules/av1/outputs.tf'},
            content_type='application/json')
        self.assertIn('output', r.get_json()['content'])

    def test_download_azure_returns_zip(self):
        r = self.client.post('/api/download', json=self.base, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('zip', r.content_type)
        self.assertEqual(r.data[:4], b'PK\x03\x04')

    def test_download_azure_filename_contains_azure(self):
        r = self.client.post('/api/download', json=self.base, content_type='application/json')
        self.assertIn('azure', r.headers.get('Content-Disposition', ''))

    def test_download_azure_zip_contains_main_tf(self):
        import io, zipfile as zf_mod
        r = self.client.post('/api/download', json=self.base, content_type='application/json')
        z = zf_mod.ZipFile(io.BytesIO(r.data))
        self.assertTrue(any('main.tf' in n for n in z.namelist()))

    def test_download_azure_main_tf_has_azurerm(self):
        import io, zipfile as zf_mod
        r = self.client.post('/api/download', json=self.base, content_type='application/json')
        z = zf_mod.ZipFile(io.BytesIO(r.data))
        main = next(n for n in z.namelist() if n.endswith('main.tf') and 'modules' not in n)
        self.assertIn('hashicorp/azurerm', z.read(main).decode())

    def test_validate_azure_tab20_pass(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 20,
            'azure_vnets': [{'module_name': 'av', 'resource_group_name': 'rg',
                              'location': 'eastus', 'vnet_name': 'v',
                              'address_space': '10.0.0.0/16',
                              'subnet_address_prefix': '10.0.1.0/24'}],
        })
        self.assertTrue(r.get_json()['valid'])

    def test_validate_azure_tab20_missing_rg(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 20,
            'azure_vnets': [{'module_name': 'av', 'location': 'eastus',
                              'vnet_name': 'v', 'address_space': '10.0.0.0/16',
                              'subnet_address_prefix': '10.0.1.0/24'}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('resource_group_name', d['errors'])

    def test_validate_azure_tab20_bad_address_cidr(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 20,
            'azure_vnets': [{'module_name': 'av', 'resource_group_name': 'rg',
                              'location': 'eastus', 'vnet_name': 'v',
                              'address_space': 'not-a-cidr',
                              'subnet_address_prefix': '10.0.1.0/24'}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('address_space', d['errors'])

    def test_validate_azure_tab20_bad_subnet_cidr(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 20,
            'azure_vnets': [{'module_name': 'av', 'resource_group_name': 'rg',
                              'location': 'eastus', 'vnet_name': 'v',
                              'address_space': '10.0.0.0/16',
                              'subnet_address_prefix': 'bad'}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('subnet_address_prefix', d['errors'])

    def test_validate_azure_tab21_pass(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 21,
            'azure_infras': [{'module_name': 'ai', 'resource_group_name': 'rg',
                               'location': 'eastus', 'name': 'n', 'display_name': 'n',
                               'shape': 'Exadata.X11M', 'compute_count': 2, 'storage_count': 3,
                               # X11M sets server_types_required on Azure too.
                               'database_server_type': 'X11M',
                               'storage_server_type': 'X11M-HC'}],
        })
        self.assertTrue(r.get_json()['valid'])

    def test_validate_azure_tab21_missing_name(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 21,
            'azure_infras': [{'module_name': 'ai', 'resource_group_name': 'rg',
                               'location': 'eastus', 'display_name': 'x',
                               'shape': 'Exadata.X11M', 'compute_count': 2, 'storage_count': 3}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('name', d['errors'])

    def test_validate_azure_tab21_low_compute(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 21,
            'azure_infras': [{'module_name': 'ai', 'resource_group_name': 'rg',
                               'location': 'eastus', 'name': 'n', 'display_name': 'n',
                               'shape': 'Exadata.X11M', 'compute_count': 1, 'storage_count': 3}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('compute_count', d['errors'])

    def test_validate_azure_tab21_low_storage(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 21,
            'azure_infras': [{'module_name': 'ai', 'resource_group_name': 'rg',
                               'location': 'eastus', 'name': 'n', 'display_name': 'n',
                               'shape': 'Exadata.X11M', 'compute_count': 2, 'storage_count': 2}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('storage_count', d['errors'])

    def test_validate_azure_tab22_pass(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 22,
            'azure_clusters': [{'module_name': 'ac', 'resource_group_name': 'rg',
                                 'location': 'eastus', 'name': 'n', 'display_name': 'n',
                                 'hostname': 'h', 'gi_version': '19.0.0.0',
                                 'cpu_core_count': 4, 'data_storage_size_in_tbs': 2.0,
                                 'ssh_public_keys': ['ssh-rsa AAA']}],
        })
        self.assertTrue(r.get_json()['valid'])

    def test_validate_azure_tab22_missing_hostname(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 22,
            'azure_clusters': [{'module_name': 'ac', 'resource_group_name': 'rg',
                                 'location': 'eastus', 'name': 'n', 'display_name': 'n',
                                 'gi_version': '19.0.0.0', 'cpu_core_count': 4,
                                 'data_storage_size_in_tbs': 2.0, 'ssh_public_keys': ['k']}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('hostname', d['errors'])

    def test_validate_azure_tab22_no_ssh_key(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 22,
            'azure_clusters': [{'module_name': 'ac', 'resource_group_name': 'rg',
                                 'location': 'eastus', 'name': 'n', 'display_name': 'n',
                                 'hostname': 'h', 'gi_version': '19.0.0.0',
                                 'cpu_core_count': 4, 'data_storage_size_in_tbs': 2.0,
                                 'ssh_public_keys': []}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('ssh_public_keys', d['errors'])

    def test_validate_azure_tab22_low_cpu(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 22,
            'azure_clusters': [{'module_name': 'ac', 'resource_group_name': 'rg',
                                 'location': 'eastus', 'name': 'n', 'display_name': 'n',
                                 'hostname': 'h', 'gi_version': '19.0.0.0',
                                 'cpu_core_count': 1, 'data_storage_size_in_tbs': 2.0,
                                 'ssh_public_keys': ['k']}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('cpu_core_count', d['errors'])

    def test_validate_azure_unrecognised_tab_passes(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 0,
            'azure_vnets': [{'module_name': 'av'}],
        })
        self.assertTrue(r.get_json()['valid'])

    def test_tf_validate_azure_returns_200(self):
        r = self.client.post('/api/tf-validate', json=self.base, content_type='application/json')
        self.assertEqual(r.status_code, 200)

    def test_tf_validate_azure_has_no_failures(self):
        r = self.client.post('/api/tf-validate', json=self.base, content_type='application/json')
        d = r.get_json()
        failures = [x for x in d.get('results', []) if x['status'] == 'fail']
        self.assertEqual(failures, [],
            msg='Failures:\n' + '\n'.join(f['name'] + ': ' + str(f['error']) for f in failures))

    def test_tf_validate_azure_provider_check_passes(self):
        r = self.client.post('/api/tf-validate', json=self.base, content_type='application/json')
        d = r.get_json()
        row = next((x for x in d['results']
                    if 'azurerm' in x['name'] and x['group'] == 'Provider'), None)
        self.assertIsNotNone(row)
        self.assertEqual(row['status'], 'pass')

    def test_tf_validate_azure_cloud_field(self):
        r = self.client.post('/api/tf-validate', json=self.base, content_type='application/json')
        self.assertEqual(r.get_json()['cloud'], 'azure')


# ══════════════════════════════════════════════════════════════════════════════
#  Mock tf_validator — Azure
# ══════════════════════════════════════════════════════════════════════════════

class TestTfValidateAzure(unittest.TestCase):
    """Direct unit tests for validate_terraform() against Azure-generated files."""

    def _gen(self, vnet_count=1, infra_count=1, cluster_count=1):
        return generate_azure_tf({
            'cloud': 'azure',
            'azure_vnets':    [azure_vnet(f'tv{i}')    for i in range(vnet_count)],
            'azure_infras':   [azure_infra(f'ti{i}')   for i in range(infra_count)],
            'azure_clusters': [azure_cluster(f'tc{i}', 'tv0', 'ti0') for i in range(cluster_count)],
        })

    def _fails(self, files):
        return [r for r in validate_terraform(files, 'azure') if r.status == 'fail']

    def test_valid_azure_has_no_failures(self):
        fails = self._fails(self._gen())
        self.assertEqual(fails, [],
            msg='\n'.join(f'{f.group} / {f.name}: {f.error}' for f in fails))

    def test_valid_azure_passes_provider_check(self):
        results = validate_terraform(self._gen(), 'azure')
        ok = [r for r in results if r.group == 'Provider' and 'azurerm' in r.name and r.status == 'pass']
        self.assertTrue(len(ok) > 0)

    def test_valid_azure_passes_file_structure(self):
        results = validate_terraform(self._gen(), 'azure')
        fails = [r for r in results if r.group == 'File Structure' and r.status == 'fail']
        self.assertEqual(fails, [])

    def test_valid_azure_passes_hcl_syntax(self):
        results = validate_terraform(self._gen(), 'azure')
        fails = [r for r in results if r.group == 'HCL Syntax' and r.status == 'fail']
        self.assertEqual(fails, [])

    def test_valid_azure_passes_variable_resolution(self):
        results = validate_terraform(self._gen(), 'azure')
        fails = [r for r in results if r.group == 'Variable Resolution' and r.status == 'fail']
        self.assertEqual(fails, [],
            msg='\n'.join(f'{f.name}: {f.error}' for f in fails))

    def test_valid_azure_passes_module_crossrefs(self):
        results = validate_terraform(self._gen(), 'azure')
        fails = [r for r in results if r.group == 'Module Cross-References' and r.status == 'fail']
        self.assertEqual(fails, [],
            msg='\n'.join(f'{f.name}: {f.error}' for f in fails))

    def test_missing_root_main_detected(self):
        files = self._gen()
        del files['main.tf']
        self.assertTrue(any('main.tf' in f.name for f in self._fails(files)))

    def test_missing_module_file_detected(self):
        files = self._gen()
        del files['modules/tv0/main.tf']
        self.assertTrue(any('tv0' in f.name for f in self._fails(files)))

    def test_wrong_provider_detected(self):
        files = self._gen()
        files['main.tf'] = files['main.tf'].replace('hashicorp/azurerm', 'hashicorp/google')
        self.assertTrue(any('azurerm' in f.name for f in self._fails(files)))

    def test_infra_resource_type_recognised_by_schema(self):
        results = validate_terraform(self._gen(), 'azure')
        ok = [r for r in results
              if 'azurerm_oracle_exadata_infrastructure' in r.name and r.status == 'pass']
        self.assertTrue(len(ok) > 0,
            msg='azurerm_oracle_exadata_infrastructure not recognised in mock validator schema')

    def test_old_infra_resource_type_would_be_unknown(self):
        files = self._gen()
        files['modules/ti0/main.tf'] = files['modules/ti0/main.tf'].replace(
            'azurerm_oracle_exadata_infrastructure',
            'azurerm_oracle_cloud_exadata_infrastructure')
        results = validate_terraform(files, 'azure')
        warns = [r for r in results
                 if 'azurerm_oracle_cloud_exadata_infrastructure' in r.name
                 and r.status == 'warn']
        self.assertTrue(len(warns) > 0,
            msg='Expected validator to warn about unknown old resource type')

    def test_multi_resource_has_no_failures(self):
        fails = self._fails(self._gen(vnet_count=2, infra_count=2, cluster_count=2))
        self.assertEqual(fails, [],
            msg='\n'.join(f'{f.group} / {f.name}: {f.error}' for f in fails))

    def test_summary_structure_complete(self):
        s = summarise(validate_terraform(self._gen(), 'azure'))
        for key in ('passed', 'failed', 'warned', 'total', 'results'):
            self.assertIn(key, s)

    def test_summary_failed_zero_for_valid_input(self):
        s = summarise(validate_terraform(self._gen(), 'azure'))
        self.assertEqual(s['failed'], 0)

    def test_summary_passed_greater_than_zero(self):
        s = summarise(validate_terraform(self._gen(), 'azure'))
        self.assertGreater(s['passed'], 0)


if __name__ == '__main__':
    unittest.main()
