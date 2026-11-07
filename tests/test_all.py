"""
Terraflow Studio — Comprehensive Test Suite
Covers: helpers, AWS modules, GCP modules, generate_all, all API routes, store backends.
Run with:  python -m pytest tests/ -v
"""

import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# ── Make app importable from tests/ directory ─────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
import app as app_module
from app import (
    app, generate_all, is_ref, parse_list, tf_bool,
    mod0_main, mod0_vars, mod0_outputs, mod0_tfvars,
    mod1_main, mod1_vars, mod1_outputs, mod1_tfvars,
    mod2_main, mod2_vars, mod2_outputs, mod2_tfvars,
    mod3_main, mod3_vars, mod3_outputs, mod3_tfvars,
    build_root_main, build_root_tfvars,
    _aws_net_defaults, _aws_infra_defaults, _aws_peer_defaults, _aws_cluster_defaults,
    azure_vnet_main, azure_vnet_vars, azure_vnet_outputs, azure_vnet_tfvars,
    azure_infra_main, azure_infra_vars, azure_infra_outputs, azure_infra_tfvars,
    azure_cluster_main, azure_cluster_vars, azure_cluster_outputs, azure_cluster_tfvars,
    azure_build_root_main, azure_build_root_vars, azure_build_root_tfvars,
    _azure_vnet_defaults, _azure_infra_defaults, _azure_cluster_defaults,
    generate_azure_tf,
)
from clouds.gcp.generator import (
    gcp_build_root_main, gcp_build_root_vars, gcp_build_root_tfvars,
    _gcp_net_defaults, _gcp_infra_defaults, _gcp_cluster_defaults,
    _gcp_shared_module_files, generate_gcp_tf,
    _GCP_MOD_NET, _GCP_MOD_INFRA, _GCP_MOD_CLUSTER,
)
from store import FileStore, _slug
from tf_validator import validate_terraform, summarise


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

def gcp_net(module_name='gcp_network', **kw):
    return {
        'module_name': module_name,
        'odb_network_id': 'my-odb-net',
        'location': 'us-east4',
        'network': 'projects/my-proj/global/networks/default',
        'project': 'my-proj',
        'gcp_oracle_zone': 'us-east4-b-r1',
        'deletion_protection': True,
        'client_subnet_id': 'client-subnet',
        'client_cidr': '10.0.1.0/24',
        'backup_subnet_id': 'backup-subnet',
        'backup_cidr': '10.0.2.0/24',
        'labels': {'env': 'test'},
        **kw,
    }

def gcp_infra(module_name='gcp_infra', **kw):
    return {
        'module_name': module_name,
        'cloud_exadata_infrastructure_id': 'my-infra',
        'display_name': 'My Infra',
        'location': 'us-east4',
        'gcp_oracle_zone': 'us-east4-b-r1',
        'project': 'my-proj',
        'shape': 'Exadata.X9M',
        'compute_count': 2,
        'storage_count': 3,
        'mw_preference': 'NO_PREFERENCE',
        'mw_patching_mode': 'ROLLING',
        **kw,
    }

def gcp_cluster(module_name='gcp_cluster', net_module='gcp_network', infra_module='gcp_infra', **kw):
    return {
        'module_name': module_name,
        'cloud_vm_cluster_id': 'my-cluster',
        'display_name': 'My Cluster',
        'location': 'us-east4',
        'gcp_oracle_zone': 'us-east4-b-r1',
        'project': 'my-proj',
        'gi_version': '23.0.0.0',
        'hostname_prefix': 'vm',
        'license_type': 'LICENSE_INCLUDED',
        'cpu_core_count': 16,
        'memory_size_gb': 60,
        'db_node_storage_size_gb': 120,
        'data_storage_size_tb': 4.0,
        'local_backup_enabled': False,
        'sparse_diskgroup_enabled': False,
        'ssh_public_keys': ['ssh-rsa AAAAB3Nz test@host'],
        'network_ref': net_module,
        'infra_ref': infra_module,
        **kw,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  1. HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

class TestHelpers(unittest.TestCase):

    # is_ref
    def test_is_ref_valid_module_ref(self):
        self.assertTrue(is_ref('module.odb_network.network_id'))

    def test_is_ref_valid_data_ref(self):
        self.assertTrue(is_ref('data.aws_odb_db_servers.this.db_servers'))

    def test_is_ref_bare_string(self):
        self.assertFalse(is_ref('vpc-0abc123'))

    def test_is_ref_empty(self):
        self.assertFalse(is_ref(''))

    def test_is_ref_none(self):
        self.assertFalse(is_ref(None))

    def test_is_ref_arn(self):
        self.assertFalse(is_ref('arn:aws:odb:us-east-1:123:network/abc'))

    # parse_list
    def test_parse_list_comma_separated(self):
        self.assertEqual(parse_list('a, b, c'), ['a', 'b', 'c'])

    def test_parse_list_empty_string(self):
        self.assertEqual(parse_list(''), [])

    def test_parse_list_none(self):
        self.assertEqual(parse_list(None), [])

    def test_parse_list_single(self):
        self.assertEqual(parse_list('only'), ['only'])

    def test_parse_list_trims_whitespace(self):
        self.assertEqual(parse_list('  x , y  '), ['x', 'y'])

    # tf_bool
    def test_tf_bool_true(self):
        self.assertEqual(tf_bool(True), 'true')

    def test_tf_bool_false(self):
        self.assertEqual(tf_bool(False), 'false')

    def test_tf_bool_truthy(self):
        self.assertEqual(tf_bool(1), 'true')

    def test_tf_bool_falsy(self):
        self.assertEqual(tf_bool(0), 'false')


# ══════════════════════════════════════════════════════════════════════════════
#  2. AWS MODULE 0 — aws_odb_network
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
#  3. AWS MODULE 1 — aws_odb_cloud_exadata_infrastructure
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
#  4. AWS MODULE 2 — aws_odb_network_peering_connection
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
        self.assertIn('module.aws_odb_network', out)
        self.assertIn('network_id', out)


# ══════════════════════════════════════════════════════════════════════════════
#  5. AWS MODULE 3 — aws_odb_cloud_vm_cluster
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
        self.assertIn('module.aws_exadata_infra', out)
        self.assertIn('infra_id', out)
        self.assertIn('module.aws_odb_network', out)
        self.assertIn('network_id', out)

    def test_license_included(self):
        out = mod3_tfvars(self.mn, self.d, self.mn0, self.mn1)
        self.assertIn('LICENSE_INCLUDED', out)

    def test_byol(self):
        d = _aws_cluster_defaults(aws_cluster(self.mn, license_model='BRING_YOUR_OWN_LICENSE'), self.mn0, self.mn1)
        out = mod3_tfvars(self.mn, d, self.mn0, self.mn1)
        self.assertIn('BRING_YOUR_OWN_LICENSE', out)


# ══════════════════════════════════════════════════════════════════════════════
#  6. AWS ROOT
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

    def test_root_main_has_all_modules(self):
        ns, inf, prs, cls = self._build()
        out = build_root_main(ns, inf, prs, cls)
        self.assertIn('module "aws_odb_network"', out)
        self.assertIn('module "aws_exadata_infra"', out)
        self.assertIn('module "aws_peering"', out)
        self.assertIn('module "aws_vm_cluster"', out)

    def test_root_main_multi_network(self):
        # With for_each, extra networks are entries in terraform.auto.tfvars — root main.tf stays the same
        ns, inf, prs, cls = self._build(nets=3)
        out = build_root_main(ns, inf, prs, cls)
        self.assertIn('for_each = var.aws_networks', out)

    def test_root_main_multi_peering(self):
        # With for_each, extra peerings are entries in terraform.auto.tfvars — root main.tf stays the same
        ns, inf, prs, cls = self._build(peerings=3)
        out = build_root_main(ns, inf, prs, cls)
        self.assertIn('for_each = var.aws_peerings', out)

    def test_root_main_multi_cluster(self):
        # With for_each, extra clusters are entries in terraform.auto.tfvars — root main.tf stays the same
        ns, inf, prs, cls = self._build(clusters=3)
        out = build_root_main(ns, inf, prs, cls)
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
#  7. GCP MODULE 0 — google_oracle_database_odb_network
# ══════════════════════════════════════════════════════════════════════════════

class TestGcpOdbNetwork(unittest.TestCase):

    def setUp(self):
        self.d     = _gcp_net_defaults(gcp_net('gcp_network'))
        self.files = _gcp_shared_module_files()

    def test_main_contains_resource(self):
        out = self.files[f'modules/{_GCP_MOD_NET}/main.tf']
        self.assertIn('google_oracle_database_odb_network', out)

    def test_vars_contains_odb_network_id(self):
        out = self.files[f'modules/{_GCP_MOD_NET}/variables.tf']
        self.assertIn('odb_network_id', out)

    def test_vars_contains_location(self):
        out = self.files[f'modules/{_GCP_MOD_NET}/variables.tf']
        self.assertIn('location', out)

    def test_outputs_contains_odb_network_name(self):
        out = self.files[f'modules/{_GCP_MOD_NET}/outputs.tf']
        self.assertIn('odb_network_name', out)

    def test_tfvars_contains_network_id_value(self):
        out = gcp_build_root_tfvars([self.d], [], [])
        self.assertIn('my-odb-net', out)

    def test_tfvars_contains_location_value(self):
        out = gcp_build_root_tfvars([self.d], [], [])
        self.assertIn('us-east4', out)

    def test_deletion_protection_true(self):
        out = self.files[f'modules/{_GCP_MOD_NET}/variables.tf']
        self.assertIn('deletion_protection', out)


# ══════════════════════════════════════════════════════════════════════════════
#  8. GCP ODB Subnet
# ══════════════════════════════════════════════════════════════════════════════

class TestGcpOdbSubnet(unittest.TestCase):

    def setUp(self):
        self.files = _gcp_shared_module_files()
        self.net   = _gcp_net_defaults(gcp_net('gcp_network'))

    def test_main_contains_resource(self):
        out = self.files[f'modules/{_GCP_MOD_NET}/main.tf']
        self.assertIn('google_oracle_database_odb_subnet', out)

    def test_vars_contains_cidr(self):
        out = self.files[f'modules/{_GCP_MOD_NET}/variables.tf']
        self.assertIn('client_cidr_range', out)

    def test_vars_contains_purpose(self):
        # Purpose is hardcoded in the module (CLIENT_SUBNET / BACKUP_SUBNET)
        out = self.files[f'modules/{_GCP_MOD_NET}/main.tf']
        self.assertIn('CLIENT_SUBNET', out)

    def test_outputs_contains_subnet_name(self):
        out = self.files[f'modules/{_GCP_MOD_NET}/outputs.tf']
        self.assertIn('client_subnet_name', out)

    def test_tfvars_contains_cidr_value(self):
        out = gcp_build_root_tfvars([self.net], [], [])
        self.assertIn('10.0.1.0/24', out)

    def test_backup_subnet_purpose(self):
        out = self.files[f'modules/{_GCP_MOD_NET}/main.tf']
        self.assertIn('BACKUP_SUBNET', out)


# ══════════════════════════════════════════════════════════════════════════════
#  9. GCP MODULE 2 — google_oracle_database_cloud_exadata_infrastructure
# ══════════════════════════════════════════════════════════════════════════════

class TestGcpExadataInfra(unittest.TestCase):

    def setUp(self):
        self.d     = _gcp_infra_defaults(gcp_infra('gcp_infra'))
        self.files = _gcp_shared_module_files()

    def test_main_contains_resource(self):
        out = self.files[f'modules/{_GCP_MOD_INFRA}/main.tf']
        self.assertIn('google_oracle_database_cloud_exadata_infrastructure', out)

    def test_vars_contains_shape(self):
        out = self.files[f'modules/{_GCP_MOD_INFRA}/variables.tf']
        self.assertIn('shape', out)

    def test_vars_contains_counts(self):
        out = self.files[f'modules/{_GCP_MOD_INFRA}/variables.tf']
        self.assertIn('compute_count', out)
        self.assertIn('storage_count', out)

    def test_outputs_contains_infra_name(self):
        out = self.files[f'modules/{_GCP_MOD_INFRA}/outputs.tf']
        self.assertIn('infra_name', out)

    def test_tfvars_contains_infra_id(self):
        out = gcp_build_root_tfvars([], [self.d], [])
        self.assertIn('my-infra', out)

    def test_tfvars_contains_shape_value(self):
        out = gcp_build_root_tfvars([], [self.d], [])
        self.assertIn('Exadata.X9M', out)


# ══════════════════════════════════════════════════════════════════════════════
#  10. GCP MODULE 1 — google_oracle_database_cloud_vm_cluster
# ══════════════════════════════════════════════════════════════════════════════

class TestGcpVmCluster(unittest.TestCase):

    def setUp(self):
        self.net   = _gcp_net_defaults(gcp_net('gcp_network'))
        self.infra = _gcp_infra_defaults(gcp_infra('gcp_infra'))
        self.d     = _gcp_cluster_defaults(gcp_cluster('gcp_cluster', 'gcp_network', 'gcp_infra'), self.net)
        self.files = _gcp_shared_module_files()

    def test_main_contains_resource(self):
        out = self.files[f'modules/{_GCP_MOD_CLUSTER}/main.tf']
        self.assertIn('google_oracle_database_cloud_vm_cluster', out)

    def test_root_contains_data_source(self):
        out = gcp_build_root_main([self.net], [self.infra], [self.d])
        self.assertIn('google_oracle_database_db_servers', out)

    def test_main_contains_lifecycle(self):
        out = self.files[f'modules/{_GCP_MOD_CLUSTER}/main.tf']
        self.assertIn('ignore_changes', out)

    def test_vars_contains_gi_version(self):
        out = self.files[f'modules/{_GCP_MOD_CLUSTER}/variables.tf']
        self.assertIn('gi_version', out)

    def test_vars_contains_cpu_core_count(self):
        out = self.files[f'modules/{_GCP_MOD_CLUSTER}/variables.tf']
        self.assertIn('cpu_core_count', out)

    def test_vars_contains_exadata_infrastructure(self):
        out = self.files[f'modules/{_GCP_MOD_CLUSTER}/variables.tf']
        self.assertIn('exadata_infrastructure', out)

    def test_outputs_contains_cluster_name(self):
        out = self.files[f'modules/{_GCP_MOD_CLUSTER}/outputs.tf']
        self.assertIn('vm_cluster_name', out)

    def test_outputs_contains_ocid(self):
        out = self.files[f'modules/{_GCP_MOD_CLUSTER}/outputs.tf']
        self.assertIn('ocid', out)

    def test_tfvars_contains_cluster_id(self):
        out = gcp_build_root_tfvars([], [], [self.d])
        self.assertIn('my-cluster', out)

    def test_tfvars_contains_gi_version(self):
        out = gcp_build_root_tfvars([], [], [self.d])
        self.assertIn('gi_version', out)


# ══════════════════════════════════════════════════════════════════════════════
#  11. GCP ROOT
# ══════════════════════════════════════════════════════════════════════════════

class TestGcpRoot(unittest.TestCase):

    def _build(self, net_count=1, infra_count=1, cluster_count=1):
        nets     = [_gcp_net_defaults(gcp_net(f'gnet_{i}')) for i in range(net_count)]
        infras   = [_gcp_infra_defaults(gcp_infra(f'ginf_{i}')) for i in range(infra_count)]
        clusters = [_gcp_cluster_defaults(gcp_cluster(f'gcl_{i}', 'gnet_0', 'ginf_0'), nets[0]) for i in range(cluster_count)]
        return nets, infras, clusters

    def test_root_main_contains_provider(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('hashicorp/google', out)

    def test_root_main_has_network_module(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('module "gcp_odb_network"', out)
        self.assertIn('for_each = var.gcp_odb_networks', out)

    def test_root_main_has_subnet_outputs(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('client_subnet_name', out)
        self.assertIn('backup_subnet_name', out)

    def test_root_main_has_infra_module(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('module "gcp_exadata_infra"', out)
        self.assertIn('for_each = var.gcp_exadata_infras', out)

    def test_root_main_has_cluster_module(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('module "gcp_vm_cluster"', out)
        self.assertIn('for_each = var.gcp_vm_clusters', out)

    def test_root_main_cluster_references_subnet(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_main(ns, inf, cls)
        self.assertIn('client_subnet_name', out)

    def test_root_main_multi_network(self):
        # With for_each, extra networks are added as tfvars entries — root main.tf stays the same
        ns, inf, cls = self._build(net_count=2)
        out = gcp_build_root_tfvars(ns, inf, cls)
        self.assertIn('"gnet_0"', out)
        self.assertIn('"gnet_1"', out)

    def test_root_main_multi_cluster(self):
        # With for_each, extra clusters are added as tfvars entries — root main.tf stays the same
        ns, inf, cls = self._build(cluster_count=2)
        out = gcp_build_root_tfvars(ns, inf, cls)
        self.assertIn('"gcl_0"', out)
        self.assertIn('"gcl_1"', out)

    def test_root_tfvars_contains_project(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_tfvars(ns, inf, cls)
        self.assertIn('gcp_project', out)

    def test_root_tfvars_contains_region(self):
        ns, inf, cls = self._build()
        out = gcp_build_root_tfvars(ns, inf, cls)
        self.assertIn('gcp_region', out)


# ══════════════════════════════════════════════════════════════════════════════
#  12. generate_all — multi-instance
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateAll(unittest.TestCase):

    # ── AWS single-instance backward-compat ──────────────────────────────────
    def test_aws_single_backward_compat(self):
        files = generate_all({
            'cloud': 'aws',
            'module_names': {'0': 'net', '1': 'inf', '2': 'peer', '3': 'cl'},
            'module_0': aws_net('net'),
            'module_1': aws_infra('inf'),
            'module_2': aws_peer('peer'),
            'module_3': {**aws_cluster('cl'), 'vm_mode': 'id',
                         'cloud_exadata_infrastructure_id': '',
                         'odb_network_id': ''},
        })
        # 4 shared modules × 3 files + 3 root + README.md = 16
        self.assertEqual(len(files), 16)
        self.assertIn('main.tf', files)
        self.assertIn('variables.tf', files)
        self.assertIn('modules/aws-odb-network/main.tf', files)

    # ── AWS multi-instance ────────────────────────────────────────────────────
    def test_aws_multi_two_networks(self):
        files = generate_all({
            'cloud': 'aws',
            'aws_networks':  [aws_net('n1'), aws_net('n2')],
            'aws_infras':    [aws_infra('i1')],
            'aws_peerings':  [aws_peer('p1', network_ref='n1')],
            'aws_clusters':  [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        })
        # 4 shared modules × 3 files + 3 root + README.md = 16, regardless of instance count
        self.assertEqual(len(files), 16)
        self.assertIn('modules/aws-odb-network/main.tf', files)
        self.assertIn('"n1"', files['terraform.auto.tfvars'])
        self.assertIn('"n2"', files['terraform.auto.tfvars'])

    def test_aws_multi_two_infras(self):
        files = generate_all({
            'cloud': 'aws',
            'aws_networks':  [aws_net('n1')],
            'aws_infras':    [aws_infra('i1'), aws_infra('i2')],
            'aws_peerings':  [aws_peer('p1', network_ref='n1')],
            'aws_clusters':  [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        })
        self.assertIn('modules/aws-exadata-infra/main.tf', files)
        self.assertIn('"i1"', files['terraform.auto.tfvars'])
        self.assertIn('"i2"', files['terraform.auto.tfvars'])

    def test_aws_multi_two_peerings(self):
        files = generate_all({
            'cloud': 'aws',
            'aws_networks':  [aws_net('n1'), aws_net('n2')],
            'aws_infras':    [aws_infra('i1')],
            'aws_peerings':  [aws_peer('p1', network_ref='n1'), aws_peer('p2', network_ref='n2')],
            'aws_clusters':  [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        })
        # With for_each, extra peerings are map entries in tfvars — root main.tf stays the same
        tfvars = files['terraform.auto.tfvars']
        self.assertIn('"p1"', tfvars)
        self.assertIn('"p2"', tfvars)
        self.assertIn('for_each = var.aws_peerings', files['main.tf'])

    def test_aws_multi_two_clusters(self):
        files = generate_all({
            'cloud': 'aws',
            'aws_networks':  [aws_net('n1')],
            'aws_infras':    [aws_infra('i1')],
            'aws_peerings':  [aws_peer('p1', network_ref='n1')],
            'aws_clusters':  [
                aws_cluster('c1', infra_ref='i1', network_ref='n1'),
                aws_cluster('c2', infra_ref='i1', network_ref='n1'),
            ],
        })
        # With for_each, extra clusters are map entries in tfvars — root main.tf stays the same
        tfvars = files['terraform.auto.tfvars']
        self.assertIn('"c1"', tfvars)
        self.assertIn('"c2"', tfvars)

    def test_aws_cluster_cross_wired_to_correct_infra(self):
        files = generate_all({
            'cloud': 'aws',
            'aws_networks':  [aws_net('n1'), aws_net('n2')],
            'aws_infras':    [aws_infra('i_prod'), aws_infra('i_dev')],
            'aws_peerings':  [aws_peer('p1', network_ref='n1')],
            'aws_clusters':  [
                aws_cluster('c_prod', infra_ref='i_prod', network_ref='n1'),
                aws_cluster('c_dev',  infra_ref='i_dev',  network_ref='n2'),
            ],
        })
        # Cross-wiring is expressed as infra_ref/network_ref values in the tfvars map entries
        tfvars = files['terraform.auto.tfvars']
        self.assertIn('"i_prod"', tfvars)
        self.assertIn('"i_dev"', tfvars)
        self.assertIn('"n2"', tfvars)

    # ── GCP single-instance backward-compat ──────────────────────────────────
    def test_gcp_single_backward_compat(self):
        files = generate_all({
            'cloud': 'gcp',
            'gcp_module_names': {'0': 'gnet', '1': 'csub', '2': 'bsub', '3': 'ginf', '4': 'gcl'},
            'gcp_module_0': gcp_net('gnet'),
            'gcp_module_1': {'odb_subnet_id': 'csub', 'location': 'us-east4', 'cidr_range': '10.0.1.0/24', 'purpose': 'CLIENT_SUBNET'},
            'gcp_module_2': {'odb_subnet_id': 'bsub', 'location': 'us-east4', 'cidr_range': '10.0.2.0/24', 'purpose': 'BACKUP_SUBNET'},
            'gcp_module_3': gcp_infra('ginf'),
            'gcp_module_4': {**gcp_cluster('gcl', 'gnet', 'ginf'), 'odb_network': '', 'odb_subnet': '', 'backup_odb_subnet': '', 'exadata_infrastructure': ''},
        })
        # subnets inline in network module, no per-module tfvars: 1 net + 1 infra + 1 cluster = 3 modules × 3 + 3 root + README.md = 13
        self.assertEqual(len(files), 13)
        self.assertIn('main.tf', files)
        self.assertIn('variables.tf', files)

    # ── GCP multi-instance ────────────────────────────────────────────────────
    def test_gcp_multi_two_networks(self):
        n1 = gcp_net('gnet1')
        n2 = gcp_net('gnet2')
        files = generate_all({
            'cloud': 'gcp',
            'gcp_networks': [n1, n2],
            'gcp_infras':   [gcp_infra('ginf1')],
            'gcp_clusters': [gcp_cluster('gcl1', 'gnet1', 'ginf1')],
        })
        # 3 shared modules (9 files) + 3 root files + README.md = 13, regardless of instance count
        self.assertEqual(len(files), 13)
        self.assertIn(f'modules/{_GCP_MOD_NET}/main.tf', files)
        self.assertIn(f'modules/{_GCP_MOD_INFRA}/main.tf', files)

    def test_gcp_multi_cluster_cross_wired(self):
        n1 = _gcp_net_defaults(gcp_net('gnet1'))
        n2 = _gcp_net_defaults(gcp_net('gnet2'))
        files = generate_all({
            'cloud': 'gcp',
            'gcp_networks': [n1, n2],
            'gcp_infras':   [gcp_infra('ginf1')],
            'gcp_clusters': [
                gcp_cluster('gcl_prod', 'gnet1', 'ginf1'),
                gcp_cluster('gcl_dev',  'gnet2', 'ginf1'),
            ],
        })
        # Cross-wiring is expressed as network_key in the tfvars map entries
        tfvars = files['terraform.auto.tfvars']
        self.assertIn('gnet1', tfvars)
        self.assertIn('gnet2', tfvars)
        self.assertIn('for_each = var.gcp_odb_networks', files['main.tf'])

    # ── File content quality checks ───────────────────────────────────────────
    def test_all_files_are_non_empty(self):
        files = generate_all({
            'cloud': 'aws',
            'aws_networks':  [aws_net('n1')],
            'aws_infras':    [aws_infra('i1')],
            'aws_peerings':  [aws_peer('p1', network_ref='n1')],
            'aws_clusters':  [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        })
        for path, content in files.items():
            self.assertGreater(len(content.strip()), 0, f'{path} is empty')

    def test_all_tf_files_have_valid_structure(self):
        files = generate_all({
            'cloud': 'aws',
            'aws_networks':  [aws_net('n1')],
            'aws_infras':    [aws_infra('i1')],
            'aws_peerings':  [aws_peer('p1', network_ref='n1')],
            'aws_clusters':  [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        })
        for path, content in files.items():
            if path.endswith('.tf'):
                self.assertIn('{', content, f'{path} missing opening brace')


# ══════════════════════════════════════════════════════════════════════════════
#  13. DEFAULT NORMALISER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

class TestDefaultNormalisers(unittest.TestCase):

    def test_aws_net_defaults_s3_enabled(self):
        d = _aws_net_defaults({'s3_access': True})
        self.assertEqual(d['s3_access'], 'ENABLED')

    def test_aws_net_defaults_s3_disabled(self):
        d = _aws_net_defaults({'s3_access': False})
        self.assertEqual(d['s3_access'], 'DISABLED')

    def test_aws_infra_defaults_compute_int(self):
        d = _aws_infra_defaults({'compute_count': '4', 'storage_count': '5'})
        self.assertEqual(d['compute_count'], 4)
        self.assertEqual(d['storage_count'], 5)

    def test_aws_infra_defaults_fallback(self):
        d = _aws_infra_defaults({})
        self.assertEqual(d['compute_count'], 2)
        self.assertEqual(d['storage_count'], 3)

    def test_aws_peer_defaults_network_ref(self):
        d = _aws_peer_defaults({}, 'my_network')
        self.assertEqual(d['network_ref'], 'my_network')

    def test_aws_cluster_defaults_refs(self):
        d = _aws_cluster_defaults({}, 'my_net', 'my_inf')
        self.assertEqual(d['network_ref'], 'my_net')
        self.assertEqual(d['infra_ref'], 'my_inf')

    def test_gcp_net_defaults_subnet_id_fallback(self):
        d = _gcp_net_defaults({})
        self.assertEqual(d['client_subnet_id'], 'client-subnet')
        self.assertEqual(d['backup_subnet_id'], 'backup-subnet')

    def test_gcp_infra_defaults_shape_fallback(self):
        d = _gcp_infra_defaults({})
        self.assertEqual(d['shape'], 'Exadata.X9M')

    def test_gcp_cluster_defaults_auto_subnet_refs(self):
        first_net = _gcp_net_defaults({'module_name': 'net1'})
        d = _gcp_cluster_defaults({}, first_net=first_net)
        self.assertEqual(d['network_ref'], 'net1')


# ══════════════════════════════════════════════════════════════════════════════
#  14. API ROUTES
# ══════════════════════════════════════════════════════════════════════════════

class TestApiRoutes(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.base_aws = {
            'cloud': 'aws',
            'aws_networks':  [aws_net('n1')],
            'aws_infras':    [aws_infra('i1')],
            'aws_peerings':  [aws_peer('p1', network_ref='n1')],
            'aws_clusters':  [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        }
        self.base_gcp = {
            'cloud': 'gcp',
            'gcp_networks':  [gcp_net('gnet1')],
            'gcp_infras':    [gcp_infra('ginf1')],
            'gcp_clusters':  [gcp_cluster('gcl1', 'gnet1', 'ginf1')],
        }

    # GET / (home page)
    def test_index_returns_200(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)

    def test_index_contains_html(self):
        r = self.client.get('/')
        self.assertIn(b'Terraflow', r.data)

    def test_index_no_cache_header(self):
        r = self.client.get('/')
        self.assertIn('no-cache', r.headers.get('Cache-Control', ''))

    def test_index_contains_version(self):
        r = self.client.get('/')
        self.assertIn(b'v5', r.data)

    # GET /aws
    def test_aws_page_returns_200(self):
        r = self.client.get('/aws')
        self.assertEqual(r.status_code, 200)

    def test_aws_page_contains_html(self):
        r = self.client.get('/aws')
        self.assertIn(b'ODB@AWS', r.data)

    def test_aws_page_no_cache_header(self):
        r = self.client.get('/aws')
        self.assertIn('no-cache', r.headers.get('Cache-Control', ''))

    # GET /gcp
    def test_gcp_page_returns_200(self):
        r = self.client.get('/gcp')
        self.assertEqual(r.status_code, 200)

    def test_gcp_page_contains_html(self):
        r = self.client.get('/gcp')
        self.assertIn(b'AI DB@GCP', r.data)

    def test_gcp_page_no_cache_header(self):
        r = self.client.get('/gcp')
        self.assertIn('no-cache', r.headers.get('Cache-Control', ''))

    # POST /api/generate — AWS
    def test_generate_aws_root_main(self):
        r = self.client.post('/api/generate',
            json={**self.base_aws, 'file_key': 'main.tf'},
            content_type='application/json')
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertIn('content', d)
        self.assertIn('for_each = var.aws_networks', d['content'])

    def test_generate_aws_root_tfvars(self):
        r = self.client.post('/api/generate',
            json={**self.base_aws, 'file_key': 'terraform.auto.tfvars'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('content', d)
        self.assertIn('aws_region', d['content'])

    def test_generate_aws_module_main(self):
        r = self.client.post('/api/generate',
            json={**self.base_aws, 'file_key': 'modules/aws-odb-network/main.tf'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('content', d)
        self.assertIn('aws_odb_network', d['content'])

    def test_generate_aws_module_variables(self):
        r = self.client.post('/api/generate',
            json={**self.base_aws, 'file_key': 'modules/aws-odb-network/variables.tf'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('variable', d['content'])

    def test_generate_aws_module_outputs(self):
        r = self.client.post('/api/generate',
            json={**self.base_aws, 'file_key': 'modules/aws-odb-network/outputs.tf'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('output', d['content'])

    def test_generate_aws_infra_module(self):
        r = self.client.post('/api/generate',
            json={**self.base_aws, 'file_key': 'modules/aws-exadata-infra/main.tf'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('aws_odb_cloud_exadata_infrastructure', d['content'])

    def test_generate_aws_peering_module(self):
        r = self.client.post('/api/generate',
            json={**self.base_aws, 'file_key': 'modules/aws-peering/main.tf'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('aws_odb_network_peering_connection', d['content'])

    def test_generate_aws_cluster_module(self):
        r = self.client.post('/api/generate',
            json={**self.base_aws, 'file_key': 'modules/aws-vm-cluster/main.tf'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('aws_odb_cloud_vm_cluster', d['content'])

    def test_generate_unknown_file_key_returns_error(self):
        r = self.client.post('/api/generate',
            json={**self.base_aws, 'file_key': 'modules/nonexistent/main.tf'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('error', d)

    # POST /api/files — the file tree is built from this list, so every path it
    # returns must be a file_key /api/generate can actually resolve.
    def test_files_lists_aws_paths(self):
        r = self.client.post('/api/files', json=self.base_aws,
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        files = r.get_json()['files']
        self.assertIn('main.tf', files)
        self.assertIn('terraform.auto.tfvars', files)
        self.assertTrue(any(f.startswith('modules/') for f in files))

    def test_every_listed_aws_file_is_generatable(self):
        files = self.client.post('/api/files', json=self.base_aws,
                                 content_type='application/json').get_json()['files']
        self.assertTrue(files)
        for key in files:
            d = self.client.post('/api/generate',
                json={**self.base_aws, 'file_key': key},
                content_type='application/json').get_json()
            self.assertIn('content', d, f'{key} listed by /api/files but not generatable')

    def test_every_listed_gcp_file_is_generatable(self):
        files = self.client.post('/api/files', json=self.base_gcp,
                                 content_type='application/json').get_json()['files']
        self.assertTrue(files)
        for key in files:
            d = self.client.post('/api/generate',
                json={**self.base_gcp, 'file_key': key},
                content_type='application/json').get_json()
            self.assertIn('content', d, f'{key} listed by /api/files but not generatable')

    # POST /api/generate — GCP
    def test_generate_gcp_root_main(self):
        r = self.client.post('/api/generate',
            json={**self.base_gcp, 'file_key': 'main.tf'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('content', d)
        self.assertIn('module "gcp_odb_network"', d['content'])

    def test_generate_gcp_network_module(self):
        r = self.client.post('/api/generate',
            json={**self.base_gcp, 'file_key': f'modules/{_GCP_MOD_NET}/main.tf'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('google_oracle_database_odb_network', d['content'])

    def test_generate_gcp_infra_module(self):
        r = self.client.post('/api/generate',
            json={**self.base_gcp, 'file_key': f'modules/{_GCP_MOD_INFRA}/main.tf'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('google_oracle_database_cloud_exadata_infrastructure', d['content'])

    def test_generate_gcp_cluster_module(self):
        r = self.client.post('/api/generate',
            json={**self.base_gcp, 'file_key': f'modules/{_GCP_MOD_CLUSTER}/main.tf'},
            content_type='application/json')
        d = r.get_json()
        self.assertIn('google_oracle_database_cloud_vm_cluster', d['content'])

    # POST /api/download
    def test_download_aws_returns_zip(self):
        r = self.client.post('/api/download',
            json=self.base_aws,
            content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('zip', r.content_type)
        self.assertTrue(r.data[:4] == b'PK\x03\x04')  # ZIP magic bytes

    def test_download_gcp_returns_zip(self):
        r = self.client.post('/api/download',
            json=self.base_gcp,
            content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data[:4] == b'PK\x03\x04')

    # POST /api/validate — AWS passing
    def test_validate_aws_tab0_pass(self):
        r = self.client.post('/api/validate', json={
            'tab': 0,
            'module_0': {
                'display_name': 'my-net',
                'availability_zone_id': 'use1-az6',
                'client_subnet_cidr': '10.0.0.0/24',
                'backup_subnet_cidr': '10.0.1.0/24',
            },
        })
        d = r.get_json()
        self.assertTrue(d['valid'])

    def test_validate_aws_tab0_missing_fields(self):
        r = self.client.post('/api/validate', json={'tab': 0, 'module_0': {}})
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('display_name', d['errors'])
        self.assertIn('availability_zone_id', d['errors'])

    def test_validate_aws_tab0_bad_cidr(self):
        r = self.client.post('/api/validate', json={
            'tab': 0,
            'module_0': {
                'display_name': 'n', 'availability_zone_id': 'use1-az6',
                'client_subnet_cidr': 'not-a-cidr',
                'backup_subnet_cidr': '10.0.0.0/24',
            },
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('client_subnet_cidr', d['errors'])

    def test_validate_aws_tab1_pass(self):
        r = self.client.post('/api/validate', json={
            'tab': 1,
            'module_1': {
                'display_name': 'inf', 'shape': 'Exadata.X11M',
                'availability_zone_id': 'use1-az6',
                'compute_count': 2, 'storage_count': 3,
                # X11M sets server_types_required, so a pass case must name both.
                'database_server_type': 'X11M', 'storage_server_type': 'X11M-HC',
            },
        })
        d = r.get_json()
        self.assertTrue(d['valid'])

    def test_validate_aws_tab1_low_compute(self):
        r = self.client.post('/api/validate', json={
            'tab': 1,
            'module_1': {
                'display_name': 'i', 'shape': 'Exadata.X11M',
                'availability_zone_id': 'use1-az6',
                'compute_count': 1, 'storage_count': 3,
            },
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('compute_count', d['errors'])

    def test_validate_aws_tab2_pass(self):
        r = self.client.post('/api/validate', json={
            'tab': 2,
            'module_2': {
                'display_name': 'p', 'odb_network_id': 'mod.n.id',
                'peer_network_id': 'vpc-abc',
            },
        })
        d = r.get_json()
        self.assertTrue(d['valid'])

    def test_validate_aws_tab3_pass(self):
        r = self.client.post('/api/validate', json={
            'tab': 3,
            'module_3': {
                'display_name': 'c', 'cpu_core_count': 16,
                'gi_version': '23.0.0.0', 'hostname_prefix': 'vm',
                'vm_mode': 'id',
                'cloud_exadata_infrastructure_id': 'mod.i.id',
                'odb_network_id': 'mod.n.id',
                'ssh_public_keys': ['ssh-rsa AAA'],
            },
        })
        d = r.get_json()
        self.assertTrue(d['valid'])

    def test_validate_aws_tab3_no_ssh_key(self):
        r = self.client.post('/api/validate', json={
            'tab': 3,
            'module_3': {
                'display_name': 'c', 'cpu_core_count': 16,
                'gi_version': '23.0.0.0', 'hostname_prefix': 'vm',
                'vm_mode': 'id',
                'cloud_exadata_infrastructure_id': 'x', 'odb_network_id': 'y',
                'ssh_public_keys': [],
            },
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('ssh_public_keys', d['errors'])

    # POST /api/validate — GCP
    def test_validate_gcp_tab10_pass(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'gcp', 'tab': 10,
            'gcp_networks': [{
                'module_name': 'gcp_network', 'odb_network_id': 'my-net',
                'location': 'us-east4', 'network': 'projects/p/global/networks/n',
                'client_cidr': '10.0.1.0/24', 'backup_cidr': '10.0.2.0/24',
            }],
        })
        d = r.get_json()
        self.assertTrue(d['valid'])

    def test_validate_gcp_tab10_missing(self):
        r = self.client.post('/api/validate', json={'cloud': 'gcp', 'tab': 10, 'gcp_networks': [{'module_name':'gnet'}]})
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('odb_network_id', d['errors'])
        self.assertIn('location', d['errors'])
        self.assertNotIn('network', d['errors'])

    def test_validate_gcp_tab12_pass(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'gcp', 'tab': 12,
            'gcp_module_3': {
                'cloud_exadata_infrastructure_id': 'inf', 'location': 'us-east4',
                'shape': 'Exadata.X9M', 'compute_count': 2, 'storage_count': 3,
            },
        })
        d = r.get_json()
        self.assertTrue(d['valid'])

    def test_validate_gcp_tab12_low_storage(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'gcp', 'tab': 12,
            'gcp_module_3': {
                'cloud_exadata_infrastructure_id': 'i', 'location': 'us-east4',
                'shape': 'Exadata.X9M', 'compute_count': 2, 'storage_count': 2,
            },
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('storage_count', d['errors'])

    # GET /api/config/backend
    def test_config_backend(self):
        r = self.client.get('/api/config/backend')
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertIn('backend', d)

    # GET /api/config/list
    def test_config_list(self):
        r = self.client.get('/api/config/list')
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.get_json(), list)


# ══════════════════════════════════════════════════════════════════════════════
#  15. FILESTORE (mocked filesystem)
# ══════════════════════════════════════════════════════════════════════════════

class TestFileStore(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = FileStore()
        # Patch DATA_DIR to use temp dir
        import store as store_mod
        self._orig_data_dir = store_mod.DATA_DIR
        store_mod.DATA_DIR = Path(self.tmpdir)
        self.store_mod = store_mod

    def tearDown(self):
        self.store_mod.DATA_DIR = self._orig_data_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_slug_alphanumeric(self):
        self.assertEqual(_slug('MyCustomer'), 'mycustomer')

    def test_slug_spaces_become_dashes(self):
        self.assertEqual(_slug('Acme Corp'), 'acme-corp')

    def test_slug_special_chars_removed(self):
        self.assertEqual(_slug('test@company.com'), 'test-company-com')

    def test_slug_empty_fallback(self):
        self.assertEqual(_slug(''), 'unnamed')

    def test_save_creates_file(self):
        self.store_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        result = self.store.save('Acme', 'aws', {'cloud': 'aws', 'aws_networks': []})
        self.assertTrue(result['ok'])
        p = Path(self.tmpdir) / 'acme' / 'aws.json'
        self.assertTrue(p.exists())

    def test_save_and_load_roundtrip(self):
        self.store_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {'cloud': 'aws', 'aws_networks': [{'module_name': 'n1'}]}
        self.store.save('TestCo', 'aws', payload)
        doc = self.store.load('TestCo', 'aws')
        self.assertIsNotNone(doc)
        self.assertEqual(doc['customer'], 'TestCo')
        self.assertEqual(doc['cloud'], 'aws')

    def test_load_nonexistent_returns_none(self):
        result = self.store.load('NonExistent', 'aws')
        self.assertIsNone(result)

    def test_list_customers_empty(self):
        result = self.store.list_customers()
        self.assertIsInstance(result, list)

    def test_list_customers_after_save(self):
        self.store_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.store.save('Acme', 'aws', {'cloud': 'aws'})
        self.store.save('Beta', 'gcp', {'cloud': 'gcp'})
        result = self.store.list_customers()
        slugs = [r['slug'] for r in result]
        self.assertIn('acme', slugs)
        self.assertIn('beta', slugs)

    def test_list_customers_includes_data_guard_and_oci_saves(self):
        # The list used to admit only aws/gcp/azure, so a DG or OCI DB save was
        # written to disk and then never appeared in that page's dropdown.
        self.store_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.store.save('DgCo', 'dg', {'cloud': 'dg'})
        self.store.save('OciCo', 'oci', {'cloud': 'oci'})
        by_slug = {r['slug']: r['clouds'] for r in self.store.list_customers()}
        self.assertEqual(by_slug.get('dgco'), ['dg'])
        self.assertEqual(by_slug.get('ocico'), ['oci'])

    def test_every_registered_product_is_listable(self):
        from clouds.registry import REGISTRY
        self.assertEqual(set(self.store_mod.PRODUCTS), set(REGISTRY))

    def test_delete_removes_file(self):
        self.store_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.store.save('DelCo', 'aws', {'cloud': 'aws'})
        deleted = self.store.delete('DelCo', 'aws')
        self.assertTrue(deleted)
        self.assertIsNone(self.store.load('DelCo', 'aws'))

    def test_delete_nonexistent_returns_false(self):
        result = self.store.delete('Nobody', 'aws')
        self.assertFalse(result)

    def test_save_overwrites_existing(self):
        self.store_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.store.save('Acme', 'aws', {'cloud': 'aws', 'version': 1})
        self.store.save('Acme', 'aws', {'cloud': 'aws', 'version': 2})
        doc = self.store.load('Acme', 'aws')
        self.assertEqual(doc.get('version'), 2)

    def test_backend_name(self):
        self.assertIn('file:', self.store.backend_name)

    def test_multiple_clouds_same_customer(self):
        self.store_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.store.save('Multi', 'aws', {'cloud': 'aws'})
        self.store.save('Multi', 'gcp', {'cloud': 'gcp'})
        customers = self.store.list_customers()
        multi = next((c for c in customers if c['slug'] == 'multi'), None)
        self.assertIsNotNone(multi)
        self.assertIn('aws', multi['clouds'])
        self.assertIn('gcp', multi['clouds'])


# ══════════════════════════════════════════════════════════════════════════════
#  16. CONFIG API ROUTES (mocked store)
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigApiRoutes(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        # Create a mock storage backend
        self.mock_store = MagicMock()
        self.mock_store.backend_name = 'file:mock'
        self.patcher = patch.object(app_module, 'storage', self.mock_store)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_config_save_success(self):
        self.mock_store.save.return_value = {'ok': True, 'id': 'acme/aws'}
        r = self.client.post('/api/config/save', json={
            'customer': 'Acme', 'cloud': 'aws',
            'aws_networks': [{'module_name': 'n1'}],
        })
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d.get('ok'))
        self.mock_store.save.assert_called_once()

    def test_config_save_missing_customer(self):
        r = self.client.post('/api/config/save', json={'cloud': 'aws'})
        self.assertEqual(r.status_code, 400)

    def test_config_save_missing_cloud_defaults_to_aws(self):
        self.mock_store.save.return_value = {'ok': True, 'id': 'acme/aws'}
        r = self.client.post('/api/config/save', json={'customer': 'Acme'})
        self.assertEqual(r.status_code, 200)
        # cloud defaults to 'aws' if not provided
        call_args = self.mock_store.save.call_args
        self.assertEqual(call_args[0][1], 'aws')

    def test_config_load_found(self):
        self.mock_store.load.return_value = {
            'customer': 'Acme', 'cloud': 'aws', 'aws_networks': []
        }
        r = self.client.get('/api/config/load/acme/aws')
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d['customer'], 'Acme')

    def test_config_load_not_found(self):
        self.mock_store.load.return_value = None
        r = self.client.get('/api/config/load/nobody/aws')
        self.assertEqual(r.status_code, 404)

    def test_config_list_success(self):
        self.mock_store.list_customers.return_value = [
            {'customer': 'Acme', 'slug': 'acme', 'clouds': ['aws']},
            {'customer': 'Beta', 'slug': 'beta', 'clouds': ['gcp']},
        ]
        r = self.client.get('/api/config/list')
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(len(d), 2)

    def test_config_delete_success(self):
        self.mock_store.delete.return_value = True
        r = self.client.delete('/api/config/delete/acme/aws')
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d.get('ok'))

    def test_config_delete_not_found(self):
        self.mock_store.delete.return_value = False
        r = self.client.delete('/api/config/delete/nobody/aws')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()['ok'])

    def test_config_backend_endpoint(self):
        r = self.client.get('/api/config/backend')
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertIn('backend', d)


# ══════════════════════════════════════════════════════════════════════════════
#  17. COUCHDB STORE (fully mocked urllib)
# ══════════════════════════════════════════════════════════════════════════════

class TestCouchDBStore(unittest.TestCase):

    def _make_mock_response(self, data: dict, status: int = 200):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(data).encode()
        mock_resp.status = status
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_save_new_document(self):
        from store import CouchDBStore
        store = CouchDBStore.__new__(CouchDBStore)
        store.base = 'http://localhost:5984/testdb'
        # Mock _get (returns None = new doc) and _put
        store._get = MagicMock(return_value=None)
        store._put = MagicMock(return_value={'ok': True, 'rev': '1-abc'})
        result = store.save('Acme', 'aws', {'cloud': 'aws', 'data': 1})
        self.assertTrue(result['ok'])
        store._put.assert_called_once()

    def test_save_existing_document_includes_rev(self):
        from store import CouchDBStore
        store = CouchDBStore.__new__(CouchDBStore)
        store.base = 'http://localhost:5984/testdb'
        store._get = MagicMock(return_value={'_id': 'acme_aws', '_rev': '2-xyz'})
        store._put = MagicMock(return_value={'ok': True, 'rev': '3-new'})
        result = store.save('Acme', 'aws', {'cloud': 'aws'})
        self.assertTrue(result['ok'])
        # _rev must be included in the PUT body
        put_doc = store._put.call_args[0][1]
        self.assertEqual(put_doc['_rev'], '2-xyz')

    @patch('store.urllib.request.urlopen')
    def test_load_existing(self, mock_urlopen):
        from store import CouchDBStore
        doc = {'_id': 'acme_aws', 'customer': 'Acme', 'cloud': 'aws'}
        mock_urlopen.return_value = self._make_mock_response(doc)
        store = CouchDBStore.__new__(CouchDBStore)
        store.base = 'http://localhost:5984/testdb'
        result = store._get('acme_aws')
        self.assertEqual(result['customer'], 'Acme')

    @patch('store.urllib.request.urlopen')
    def test_load_not_found(self, mock_urlopen):
        from store import CouchDBStore
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError('url', 404, 'not found', {}, None)
        store = CouchDBStore.__new__(CouchDBStore)
        store.base = 'http://localhost:5984/testdb'
        result = store._get('nobody_aws')
        self.assertIsNone(result)

    @patch('store.urllib.request.urlopen')
    def test_list_customers(self, mock_urlopen):
        from store import CouchDBStore
        data = {
            'rows': [
                {'doc': {'_id': 'acme_aws', 'customer': 'Acme', 'cloud': 'aws'}},
                {'doc': {'_id': 'beta_gcp', 'customer': 'Beta', 'cloud': 'gcp'}},
            ]
        }
        mock_urlopen.return_value = self._make_mock_response(data)
        store = CouchDBStore.__new__(CouchDBStore)
        store.base = 'http://localhost:5984/testdb'
        result = store.list_customers()
        self.assertEqual(len(result), 2)

    @patch('store.urllib.request.urlopen')
    def test_delete_success(self, mock_urlopen):
        from store import CouchDBStore
        import urllib.error
        existing = {'_id': 'acme_aws', '_rev': '1-abc'}
        mock_urlopen.side_effect = [
            self._make_mock_response(existing),  # _get
            self._make_mock_response({'ok': True}),  # DELETE
        ]
        store = CouchDBStore.__new__(CouchDBStore)
        store.base = 'http://localhost:5984/testdb'
        result = store.delete('Acme', 'aws')
        self.assertTrue(result)

    def test_backend_name(self):
        from store import CouchDBStore
        store = CouchDBStore.__new__(CouchDBStore)
        store.base = 'http://localhost:5984/testdb'
        self.assertIn('couchdb', store.backend_name)


if __name__ == '__main__':
    unittest.main(verbosity=2)


# ══════════════════════════════════════════════════════════════════════════════
#  18. /api/test ROUTE
# ══════════════════════════════════════════════════════════════════════════════

class TestApiTestRoute(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.good_aws = {
            'cloud': 'aws',
            'aws_networks': [aws_net('n1')],
            'aws_infras':   [aws_infra('i1')],
            'aws_peerings': [aws_peer('p1', network_ref='n1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        }
        self.good_gcp = {
            'cloud': 'gcp',
            'gcp_networks':  [gcp_net('gnet1')],
            'gcp_infras':    [gcp_infra('ginf1')],
            'gcp_clusters':  [gcp_cluster('gcl1', 'gnet1', 'ginf1')],
        }

    def test_returns_200(self):
        r = self.client.post('/api/test', json=self.good_aws)
        self.assertEqual(r.status_code, 200)

    def test_response_has_required_fields(self):
        r = self.client.post('/api/test', json=self.good_aws)
        d = r.get_json()
        for field in ('passed', 'failed', 'total', 'results', 'cloud'):
            self.assertIn(field, d)

    def test_all_pass_on_valid_aws_payload(self):
        r = self.client.post('/api/test', json=self.good_aws)
        d = r.get_json()
        self.assertEqual(d['failed'], 0)
        self.assertGreater(d['passed'], 0)

    def test_all_pass_on_valid_gcp_payload(self):
        r = self.client.post('/api/test', json=self.good_gcp)
        d = r.get_json()
        self.assertEqual(d['failed'], 0)
        self.assertGreater(d['passed'], 0)

    def test_catches_missing_availability_zone_id(self):
        payload = {**self.good_aws,
                   'aws_networks': [{**aws_net('n1'), 'availability_zone_id': ''}]}
        r = self.client.post('/api/test', json=payload)
        d = r.get_json()
        self.assertGreater(d['failed'], 0)
        names = [row['name'] for row in d['results'] if row['status'] == 'fail']
        self.assertTrue(any('availability_zone_id' in n for n in names))

    def test_catches_invalid_cidr(self):
        payload = {**self.good_aws,
                   'aws_networks': [{**aws_net('n1'), 'client_subnet_cidr': 'not-a-cidr'}]}
        r = self.client.post('/api/test', json=payload)
        d = r.get_json()
        self.assertGreater(d['failed'], 0)

    def test_catches_low_compute_count(self):
        payload = {**self.good_aws,
                   'aws_infras': [{**aws_infra('i1'), 'compute_count': 1}]}
        r = self.client.post('/api/test', json=payload)
        d = r.get_json()
        self.assertGreater(d['failed'], 0)

    def test_catches_missing_ssh_key(self):
        payload = {**self.good_aws,
                   'aws_clusters': [{**aws_cluster('c1'), 'ssh_public_keys': []}]}
        r = self.client.post('/api/test', json=payload)
        d = r.get_json()
        self.assertGreater(d['failed'], 0)

    def test_catches_duplicate_module_names(self):
        payload = {**self.good_aws,
                   'aws_networks': [aws_net('same'), aws_net('same')]}
        r = self.client.post('/api/test', json=payload)
        d = r.get_json()
        self.assertGreater(d['failed'], 0)

    def test_results_grouped_by_category(self):
        r = self.client.post('/api/test', json=self.good_aws)
        d = r.get_json()
        groups = {row['group'] for row in d['results']}
        self.assertIn('Input Validation', groups)
        self.assertIn('Module Generation', groups)
        self.assertIn('Content Checks', groups)
        self.assertIn('Uniqueness', groups)

    def test_verifies_infra_wiring_in_root(self):
        r = self.client.post('/api/test', json=self.good_aws)
        d = r.get_json()
        wiring_tests = [row for row in d['results'] if 'wired to infra' in row['name']]
        self.assertTrue(len(wiring_tests) > 0)
        self.assertTrue(all(t['status'] == 'pass' for t in wiring_tests))

    def test_gcp_checks_provider(self):
        r = self.client.post('/api/test', json=self.good_gcp)
        d = r.get_json()
        provider_check = next((row for row in d['results'] if 'GCP provider' in row['name']), None)
        self.assertIsNotNone(provider_check)
        self.assertEqual(provider_check['status'], 'pass')

    def test_loads_saved_config_by_customer_name(self):
        mock_store = MagicMock()
        mock_store.load.return_value = {**self.good_aws, 'customer': 'AcmeCorp', 'cloud': 'aws'}
        import app as app_mod
        with patch.object(app_mod, 'storage', mock_store):
            r = self.client.post('/api/test',
                json={'customer': 'AcmeCorp', 'cloud': 'aws'},
                content_type='application/json')
        self.assertEqual(r.status_code, 200)
        mock_store.load.assert_called_once_with('AcmeCorp', 'aws')

    def test_uses_posted_payload_when_no_saved_config(self):
        mock_store = MagicMock()
        mock_store.load.return_value = None  # not saved
        import app as app_mod
        with patch.object(app_mod, 'storage', mock_store):
            r = self.client.post('/api/test', json=self.good_aws)
        d = r.get_json()
        self.assertEqual(d['failed'], 0)

    def test_multi_network_all_checked(self):
        payload = {
            'cloud': 'aws',
            'aws_networks': [aws_net('n1'), aws_net('n2'), aws_net('n3')],
            'aws_infras':   [aws_infra('i1')],
            'aws_peerings': [aws_peer('p1', network_ref='n1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        }
        r = self.client.post('/api/test', json=payload)
        d = r.get_json()
        # Should check all 3 networks
        net_checks = [row for row in d['results'] if '"n1"' in row['name'] or '"n2"' in row['name'] or '"n3"' in row['name']]
        self.assertGreaterEqual(len(net_checks), 3)


# ══════════════════════════════════════════════════════════════════════════════
#  19. MOCK TERRAFORM VALIDATOR  (tf_validator.py)
# ══════════════════════════════════════════════════════════════════════════════

class TestTFValidator(unittest.TestCase):

    def _validate(self, files, cloud):
        from tf_validator import validate_terraform, summarise
        return summarise(validate_terraform(files, cloud))['results']

    def _gen_aws(self, **kw):
        base = {
            'cloud': 'aws',
            'aws_networks':  [aws_net('odb_network')],
            'aws_infras':    [aws_infra('odb_infra')],
            'aws_peerings':  [aws_peer('odb_peering', network_ref='odb_network')],
            'aws_clusters':  [aws_cluster('odb_cluster', infra_ref='odb_infra',
                                          network_ref='odb_network')],
        }
        base.update(kw)
        return generate_all(base)

    def _gen_gcp(self):
        n = gcp_net('gcp_network')
        return generate_all({
            'cloud': 'gcp',
            'gcp_networks':  [n],
            'gcp_infras':    [gcp_infra('gcp_infra')],
            'gcp_clusters':  [gcp_cluster('gcp_cluster', 'gcp_network', 'gcp_infra')],
        })

    # ── File structure ─────────────────────────────────────────────────────
    def test_aws_all_files_present(self):
        files = self._gen_aws()
        results = self._validate(files, 'aws')
        struct = [r for r in results if r['group'] == 'File Structure' and r['status'] == 'fail']
        self.assertEqual(struct, [], f'File structure failures: {struct}')

    def test_gcp_all_files_present(self):
        files = self._gen_gcp()
        results = self._validate(files, 'gcp')
        struct = [r for r in results if r['group'] == 'File Structure' and r['status'] == 'fail']
        self.assertEqual(struct, [], f'File structure failures: {struct}')

    # ── HCL syntax ─────────────────────────────────────────────────────────
    def test_valid_hcl_no_syntax_errors(self):
        files = self._gen_aws()
        results = self._validate(files, 'aws')
        syntax_fails = [r for r in results if r['group'] == 'HCL Syntax' and r['status'] == 'fail']
        self.assertEqual(syntax_fails, [], f'HCL syntax failures: {syntax_fails}')

    def test_broken_hcl_detected(self):
        from tf_validator import _check_balanced
        bad = 'resource "aws_odb_network" "this" { display_name = var.display_name'
        result = _check_balanced(bad, 'test.tf')
        self.assertIsNotNone(result)
        self.assertEqual(result.status, 'fail')

    def test_balanced_hcl_passes(self):
        from tf_validator import _check_balanced
        good = 'resource "aws_odb_network" "this" { display_name = var.display_name }'
        result = _check_balanced(good, 'test.tf')
        self.assertIsNone(result)

    def test_comments_not_counted_in_balance(self):
        from tf_validator import _check_balanced
        with_comment = '# This { has braces\nresource "x" "y" { a = 1 }'
        result = _check_balanced(with_comment, 'test.tf')
        self.assertIsNone(result)

    # ── Provider checks ────────────────────────────────────────────────────
    def test_aws_provider_declared(self):
        files = self._gen_aws()
        results = self._validate(files, 'aws')
        prov = [r for r in results if r['group'] == 'Provider' and r['status'] == 'fail']
        self.assertEqual(prov, [])

    def test_gcp_provider_declared(self):
        files = self._gen_gcp()
        results = self._validate(files, 'gcp')
        prov = [r for r in results if r['group'] == 'Provider' and r['status'] == 'fail']
        self.assertEqual(prov, [])

    # ── Resource schema ────────────────────────────────────────────────────
    def test_aws_resource_types_known(self):
        files = self._gen_aws()
        results = self._validate(files, 'aws')
        schema_fails = [r for r in results if r['group'] == 'Resource Schema' and r['status'] == 'fail']
        self.assertEqual(schema_fails, [], f'Schema failures: {schema_fails}')

    def test_gcp_resource_types_known(self):
        files = self._gen_gcp()
        results = self._validate(files, 'gcp')
        schema_fails = [r for r in results if r['group'] == 'Resource Schema' and r['status'] == 'fail']
        self.assertEqual(schema_fails, [], f'Schema failures: {schema_fails}')

    # ── Variable resolution ────────────────────────────────────────────────
    def test_no_unresolved_var_refs(self):
        files = self._gen_aws()
        results = self._validate(files, 'aws')
        var_fails = [r for r in results
                     if r['group'] == 'Variable Resolution' and r['status'] == 'fail']
        self.assertEqual(var_fails, [], f'Unresolved vars: {var_fails}')

    def test_unresolved_var_detected(self):
        files = self._gen_aws()
        # Inject a broken main.tf with an undefined variable
        files['modules/aws-odb-network/main.tf'] += '\n  undefined_arg = var.does_not_exist\n'
        results = self._validate(files, 'aws')
        var_fails = [r for r in results
                     if r['group'] == 'Variable Resolution' and r['status'] == 'fail'
                     and 'does_not_exist' in (r.get('error') or '')]
        self.assertGreater(len(var_fails), 0, 'Should detect unresolved var.does_not_exist')

    # ── Module cross-references ────────────────────────────────────────────
    def test_module_source_paths_correct(self):
        files = self._gen_aws()
        results = self._validate(files, 'aws')
        xref_fails = [r for r in results
                      if r['group'] == 'Module Cross-References' and r['status'] == 'fail']
        self.assertEqual(xref_fails, [], f'Cross-ref failures: {xref_fails}')

    def test_broken_source_path_detected(self):
        import re as _re
        files = self._gen_aws()
        # Break the source path for one module so its directory no longer exists
        files['main.tf'] = _re.sub(
            r'source\s*=\s*"./modules/aws-odb-network"',
            'source = "./modules/wrong_path"',
            files['main.tf'])
        results = self._validate(files, 'aws')
        # The validator should detect that modules/wrong_path/ does not exist
        src_fails = [r for r in results
                     if r['group'] == 'Module Cross-References' and r['status'] == 'fail']
        self.assertGreater(len(src_fails), 0, 'Should detect wrong source path')

    # ── Overall: no failures on valid config ──────────────────────────────
    def test_valid_aws_config_zero_failures(self):
        files = self._gen_aws()
        results = self._validate(files, 'aws')
        failures = [r for r in results if r['status'] == 'fail']
        self.assertEqual(failures, [], f'Unexpected failures: {failures}')

    def test_valid_gcp_config_zero_failures(self):
        files = self._gen_gcp()
        results = self._validate(files, 'gcp')
        failures = [r for r in results if r['status'] == 'fail']
        self.assertEqual(failures, [], f'Unexpected failures: {failures}')

    def test_multi_module_aws_zero_failures(self):
        files = generate_all({
            'cloud': 'aws',
            'aws_networks': [aws_net('net1'), aws_net('net2')],
            'aws_infras':   [aws_infra('inf1'), aws_infra('inf2')],
            'aws_peerings': [aws_peer('peer1', network_ref='net1'),
                             aws_peer('peer2', network_ref='net2')],
            'aws_clusters': [aws_cluster('cl1', infra_ref='inf1', network_ref='net1'),
                             aws_cluster('cl2', infra_ref='inf2', network_ref='net2')],
        })
        results = self._validate(files, 'aws')
        failures = [r for r in results if r['status'] == 'fail']
        self.assertEqual(failures, [], f'Multi-module failures: {failures}')

    # ── /api/tf-validate endpoint ─────────────────────────────────────────
    def test_api_tf_validate_returns_200(self):
        c = app.test_client()
        r = c.post('/api/tf-validate', json={
            'cloud': 'aws',
            'aws_networks': [aws_net('odb_network')],
            'aws_infras':   [aws_infra('odb_infra')],
            'aws_peerings': [aws_peer('odb_peering', network_ref='odb_network')],
            'aws_clusters': [aws_cluster('odb_cluster', infra_ref='odb_infra', network_ref='odb_network')],
        })
        self.assertEqual(r.status_code, 200)

    def test_api_tf_validate_response_fields(self):
        c = app.test_client()
        r = c.post('/api/tf-validate', json={
            'cloud': 'aws',
            'aws_networks': [aws_net('odb_network')],
            'aws_infras':   [aws_infra('odb_infra')],
            'aws_peerings': [aws_peer('odb_peering', network_ref='odb_network')],
            'aws_clusters': [aws_cluster('odb_cluster', infra_ref='odb_infra', network_ref='odb_network')],
        })
        d = r.get_json()
        for field in ('passed', 'failed', 'warned', 'total', 'results', 'files_generated'):
            self.assertIn(field, d)

    def test_api_tf_validate_zero_failures_valid_config(self):
        c = app.test_client()
        r = c.post('/api/tf-validate', json={
            'cloud': 'aws',
            'aws_networks': [aws_net('odb_network')],
            'aws_infras':   [aws_infra('odb_infra')],
            'aws_peerings': [aws_peer('odb_peering', network_ref='odb_network')],
            'aws_clusters': [aws_cluster('odb_cluster', infra_ref='odb_infra', network_ref='odb_network')],
        })
        d = r.get_json()
        self.assertEqual(d['failed'], 0, f"Unexpected failures: {[x for x in d['results'] if x['status']=='fail']}")


# ══════════════════════════════════════════════════════════════════════════════
#  18b. INLINE EVENT HANDLERS MUST EXIST
#  Every onclick/onchange/oninput in the markup has to name a function the page
#  actually defines. A missing one is a silent ReferenceError: the button does
#  nothing and no error reaches the user.
# ══════════════════════════════════════════════════════════════════════════════

class TestInlineHandlersAreDefined(unittest.TestCase):

    PAGES = ('/aws', '/gcp', '/azure', '/dg', '/oci', '/')

    # Browser globals and JS keywords that can legitimately precede a "(".
    _ALLOWED = {
        'document', 'window', 'event', 'console', 'Number', 'String', 'Boolean',
        'parseInt', 'parseFloat', 'JSON', 'Array', 'Object', 'Math', 'Date',
        'setTimeout', 'clearTimeout', 'setInterval', 'alert', 'confirm', 'prompt',
        'fetch', 'encodeURIComponent', 'decodeURIComponent', 'isNaN', 'RegExp',
        'Set', 'Map', 'if', 'for', 'while', 'switch', 'catch', 'return',
        'typeof', 'function',
    }

    _SCRIPT_RE = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.S)
    # Pages also pull shared helpers from static/ — chrome that is not specific
    # to one cloud, such as the Deploy Guide exporters.
    _SRC_RE = re.compile(r'<script[^>]*\bsrc="([^"]*static/[^"]+)"')
    _HANDLER_RE = re.compile(
        r'\bon(?:click|change|input|submit|keydown|keyup|load)\s*=\s*"([^"]*)"')
    # Leading identifier of a call, skipping method calls such as x.foo().
    _CALL_RE = re.compile(r'(?<![\w.$])([A-Za-z_$][\w$]*)\s*\(')

    ROOT = Path(__file__).resolve().parent.parent

    @staticmethod
    def _is_defined(js, name):
        return any(pat in js for pat in (
            'function %s(' % name, 'function %s (' % name,
            'const %s=' % name, 'const %s =' % name,
            'let %s=' % name, 'let %s =' % name,
            'var %s=' % name, 'var %s =' % name,
            # Exposed from inside an IIFE.
            'window.%s =' % name, 'window.%s=' % name,
        ))

    def _external_js(self, html):
        """Source of every static script the page loads, so handlers can resolve
        into a shared file instead of forcing it to be inlined three times."""
        out = []
        for src in self._SRC_RE.findall(html):
            path = self.ROOT / 'static' / src.split('static/', 1)[1].lstrip('/')
            self.assertTrue(path.is_file(), 'page loads %s, which does not exist' % src)
            out.append(path.read_text(encoding='utf-8'))
        return out

    def setUp(self):
        self.client = app.test_client()

    def test_every_inline_handler_resolves(self):
        for route in self.PAGES:
            with self.subTest(route=route):
                html = self.client.get(route).get_data(as_text=True)
                js = '\n'.join(self._SCRIPT_RE.findall(html) + self._external_js(html))
                called = set()
                for handler in self._HANDLER_RE.findall(html):
                    called.update(self._CALL_RE.findall(handler))
                missing = sorted(n for n in called
                                 if n not in self._ALLOWED and not self._is_defined(js, n))
                self.assertEqual(
                    missing, [],
                    '%s: handlers referenced in markup but never defined: %s' % (route, missing))


# ══════════════════════════════════════════════════════════════════════════════
#  18b-2. DEPLOY GUIDE EXPORT
#  The guide is built in the browser from the current form, so it existed only
#  on screen. Both exporters read the rendered panel, which is the one place the
#  Terraform and CloudFormation variants of the guide meet.
# ══════════════════════════════════════════════════════════════════════════════

class TestDeployGuideExport(unittest.TestCase):

    GUIDE_PAGES = ('/aws', '/gcp', '/azure')
    ROOT = Path(__file__).resolve().parent.parent

    def setUp(self):
        self.client = app.test_client()

    def test_the_exporter_ships_and_exposes_both_entry_points(self):
        src = (self.ROOT / 'static' / 'guide-export.js').read_text(encoding='utf-8')
        self.assertIn('window.exportGuidePdf = exportGuidePdf', src)
        self.assertIn('window.exportGuideMarkdown = exportGuideMarkdown', src)

    def test_every_guide_page_loads_it_and_offers_both_buttons(self):
        for route in self.GUIDE_PAGES:
            with self.subTest(route=route):
                html = self.client.get(route).get_data(as_text=True)
                self.assertIn('guide-export.js', html)
                self.assertIn('onclick="exportGuidePdf()"', html)
                self.assertIn('onclick="exportGuideMarkdown()"', html)

    def test_the_buttons_sit_in_the_guide_panel(self):
        # Not in the toolbar: exporting is meaningless until the panel is open,
        # and both exporters read #guide-body.
        for route in self.GUIDE_PAGES:
            with self.subTest(route=route):
                html = self.client.get(route).get_data(as_text=True)
                panel = html.split('id="guide-panel"', 1)[1].split('id="guide-body"', 1)[0]
                self.assertIn('exportGuidePdf()', panel)
                self.assertIn('exportGuideMarkdown()', panel)

    def test_the_static_file_is_served(self):
        res = self.client.get('/static/guide-export.js')
        try:
            self.assertEqual(200, res.status_code)
            self.assertIn(b'exportGuidePdf', res.get_data())
        finally:
            res.close()   # send_from_directory hands back an open file wrapper

    def _aws_branch(self):
        """buildDeployGuide()'s AWS arm — the page carries a GCP arm too."""
        src = (self.ROOT / 'clouds' / 'aws' / 'pages' / 'aws.html').read_text(encoding='utf-8')
        body = src.split("if(cloud==='aws'){", 1)[1]
        return body.split('} else { // GCP', 1)[0]

    def test_the_guide_follows_the_provisioning_order(self):
        # Exadata Infrastructure -> ODB Network -> ODB Peering -> clusters.
        # The infra depends on nothing, so it goes first; peering needs its
        # network; clusters need both.
        branch = self._aws_branch()
        order = [branch.index('`Deploy Exadata Infrastructure$'),
                 branch.index('`Deploy ODB Network$'),
                 branch.index('`Deploy ODB Peering$'),
                 branch.index('`Deploy VM Cluster$')]
        self.assertEqual(order, sorted(order),
                         'deploy guide steps are out of provisioning order')

    def test_nothing_in_the_guide_tells_you_to_run_applies_in_parallel(self):
        branch = self._aws_branch()
        self.assertNotIn('parallel', branch.lower())
        self.assertNotIn('simultaneously', branch.lower())
        self.assertNotIn('two terminals', branch.lower())

    def test_multi_instance_steps_say_one_at_a_time(self):
        branch = self._aws_branch()
        for res in ('Exadata Infrastructure', 'ODB Network', 'ODB Peering', 'VM Cluster'):
            title = branch.split('`Deploy %s$' % res, 1)[1].split('`,', 1)[0]
            self.assertIn('one at a time', title,
                          '%s step does not say one at a time when there are several' % res)

    def test_targets_name_the_for_each_module_addresses(self):
        # An instruction to run these in order is worthless if the address does
        # not resolve — every resource type is one for_each module now.
        branch = self._aws_branch()
        for mod in ('aws_exadata_infra', 'aws_odb_network', 'aws_peering',
                    'aws_vm_cluster', 'aws_avmcluster'):
            self.assertIn("-target='module.%s[\"${" % mod, branch,
                          '%s step does not target the for_each address' % mod)
        # The pre-for_each form, one per resource kind. Not a blanket ban on
        # "-target=module.${": the OCI DB Home/CDB/PDB modules really are one
        # module per instance, so their flat targets are correct.
        for var in ('n', 'i', 'pp', 'c', 'a'):
            self.assertNotIn('-target=module.${%s.module_name}' % var, branch)


# ══════════════════════════════════════════════════════════════════════════════
#  18c. VALIDATION FIELD -> FORM INPUT MAP
#  /api/validate reports Terraform field names (display_name, availability_zone_id)
#  while the form inputs use short ids (dn, az). VALIDATION_FIELD_INPUT bridges
#  the two; if it drifts, validation still reports the error but no field is
#  highlighted, which reads to the user as "validation is broken".
# ══════════════════════════════════════════════════════════════════════════════

class TestValidationFieldMap(unittest.TestCase):

    # page -> {validator tab: card id prefix}
    PAGES = {
        'aws.html':   {0: 'an', 1: 'ai', 2: 'ap', 3: 'ac', 4: 'av', 5: 'ad', 7: 'rs', 8: 'kk'},
        'gcp.html':   {10: 'gn', 12: 'gi', 13: 'gc', 15: 'ga', 16: 'gk', 17: 'gv', 18: 'gx'},
        'azure.html': {20: 'av', 21: 'ai', 22: 'ac', 23: 'ad', 24: 'ar', 25: 'na'},
    }
    # page -> (cloud package, validator function). Validation moved out of
    # app.py into clouds/<cloud>/validator.py so each cloud owns its own rules.
    VALIDATORS = {
        'aws.html':   ('aws', '_validate_aws'),
        'gcp.html':   ('gcp', '_validate_gcp'),
        'azure.html': ('azure', '_validate_azure'),
    }
    # page -> {card id prefix: card-rendering function}
    CARDS = {
        'aws.html': {'an': 'awsNetCardHTML', 'ai': 'awsInfraCardHTML', 'ap': 'awsPeeringCardHTML',
                     'ac': 'awsClusterCardHTML', 'av': 'awsAvmcCardHTML', 'ad': 'awsAdbCardHTML',
                     'rs': 'awsRamShareCardHTML', 'kk': 'awsKmsKeyCardHTML'},
        'gcp.html': {'gn': 'gcpNetCardHTML', 'gi': 'gcpInfraCardHTML', 'gc': 'gcpClusterCardHTML',
                     'ga': 'gcpAdbCardHTML', 'gk': 'gcpKmsCardHTML',
                     'gv': 'gcpXsVaultCardHTML', 'gx': 'gcpXsClusterCardHTML'},
        'azure.html': {'av': 'azureVnetCardHTML', 'ai': 'azureInfraCardHTML',
                       'ac': 'azureClusterCardHTML', 'ad': 'azureAdbCardHTML',
                       'ar': 'azureResourceAnchorCardHTML', 'na': 'azureNetworkAnchorCardHTML'},
    }

    ROOT = Path(__file__).resolve().parent.parent

    # Cloud pages moved from templates/ into their package, next to the blueprint
    # that serves them. Shared pages (home, cidr, config, hub, rag) stayed put.
    PAGE_DIRS = {
        'aws.html':   'clouds/aws/pages',
        'gcp.html':   'clouds/gcp/pages',
        'azure.html': 'clouds/azure/pages',
        'oci_db.html': 'oci/pages',
        'dg.html':     'oci/pages',
    }

    def _page(self, page):
        folder = self.PAGE_DIRS.get(page, 'templates')
        return (self.ROOT / folder / page).read_text(encoding='utf-8')

    def _field_map(self, page):
        """Parse VALIDATION_FIELD_INPUT out of the page."""
        src = self._page(page)
        start = src.find('const VALIDATION_FIELD_INPUT = {')
        self.assertGreater(start, 0, '%s: VALIDATION_FIELD_INPUT is missing' % page)
        body = src[start:src.find('\n};', start)]
        return {
            prefix: dict(re.findall(r"([a-z_0-9]+)\s*:\s*'([A-Za-z0-9_]+)'", inner))
            for prefix, inner in re.findall(r'(\w+):\s*\{(.*?)\}', body, re.S)
        }

    def _validator_fields(self, spec):
        """{tab: {field names the validator can report}} from the cloud package."""
        cloud, fn_name = spec
        path = self.ROOT / 'clouds' / cloud / 'validator.py'
        src = path.read_text(encoding='utf-8')
        start = src.find('def %s(' % fn_name)
        self.assertGreater(start, 0, '%s not found in %s' % (fn_name, path))

        # Top-level function bodies, so a tab that delegates to a helper
        # (`_check_adb(adb, mn, ...)`) is credited with the helper's fields
        # rather than with whatever function happens to follow it in the file.
        defs = {m.group(1): m.start() for m in re.finditer(r'(?m)^def (\w+)\(', src)}
        ends = sorted(defs.values()) + [len(src)]
        bodies = {name: src[pos:ends[ends.index(pos) + 1]] for name, pos in defs.items()}
        lit = lambda text: set(re.findall(r"_err\(mn, '([a-z_]+)'", text))

        out, tab = {}, None
        for line in bodies[fn_name].split('\n'):
            m = re.search(r'\b(?:el)?if tab == (\d+)', line)
            if m:
                tab = int(m.group(1))
                out.setdefault(tab, set())
            if tab is not None:
                out[tab].update(lit(line))
                for helper in re.findall(r'\b(_check_\w+)\(', line):
                    out[tab].update(lit(bodies.get(helper, '')))
        return out

    def _card_input_ids(self, page, card_fn):
        src = self._page(page)
        start = src.find('function %s(' % card_fn)
        self.assertGreater(start, 0, '%s: %s not found' % (page, card_fn))
        body = src[start:src.find('\nfunction ', start + 10)]
        return set(re.findall(r'\$\{p\}([A-Za-z0-9_]+)', body))

    def test_every_mapped_input_exists_on_the_card(self):
        for page, cards in self.CARDS.items():
            field_map = self._field_map(page)
            for prefix, fields in field_map.items():
                ids = self._card_input_ids(page, cards[prefix])
                for field, suffix in fields.items():
                    with self.subTest(page=page, prefix=prefix, field=field):
                        self.assertIn(
                            suffix, ids,
                            '%s %s.%s maps to id suffix %r, which no input on the card uses'
                            % (page, prefix, field, suffix))

    def test_every_validator_field_is_mapped(self):
        for page, tabs in self.PAGES.items():
            field_map = self._field_map(page)
            by_tab = self._validator_fields(self.VALIDATORS[page])
            for tab, prefix in tabs.items():
                expected = by_tab.get(tab, set())
                self.assertTrue(expected, '%s tab %d: validator reports nothing' % (page, tab))
                unmapped = sorted(expected - set(field_map.get(prefix, {})))
                with self.subTest(page=page, tab=tab):
                    self.assertEqual(
                        unmapped, [],
                        '%s tab %d (%s): validator can report %s but the map has no entry, '
                        'so those fields never get highlighted' % (page, tab, prefix, unmapped))


# ══════════════════════════════════════════════════════════════════════════════
#  19. EXTERNALLY PROVISIONED NETWORKS / INFRAS
#  An entry flagged is_existing must create nothing and instead surface as an
#  existing_*_ids entry keyed by the same module name the refs already use.
# ══════════════════════════════════════════════════════════════════════════════

class TestExternalAwsResources(unittest.TestCase):

    def _gen(self, infra_external=False, net_external=False):
        net = aws_net('n1')
        inf = aws_infra('i1')
        if net_external:
            net = {**net, 'is_existing': True, 'existing_id': 'odb-net-abc'}
        if infra_external:
            inf = {**inf, 'is_existing': True, 'existing_id': 'odb-exa-abc'}
        return generate_all({
            'cloud': 'aws',
            'aws_networks': [net],
            'aws_infras':   [inf],
            'aws_peerings': [aws_peer('p1', network_ref='n1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        })

    def test_managed_output_is_unchanged(self):
        files = self._gen()
        # The brownfield locals specifically — main.tf always carries a locals
        # block now for DB server discovery, so 'locals {' no longer isolates it.
        self.assertNotIn('infra_ids = merge(', files['main.tf'])
        self.assertNotIn('odb_network_ids = merge(', files['main.tf'])
        self.assertNotIn('existing_infra_ids', files['variables.tf'])
        self.assertNotIn('existing_infra_ids', files['terraform.auto.tfvars'])
        self.assertIn('module.aws_exadata_infra[each.value.infra_ref].infra_id', files['main.tf'])

    def test_external_infra_is_not_created(self):
        files = self._gen(infra_external=True)
        self.assertIn('aws_infras = {}', files['terraform.auto.tfvars'])
        self.assertIn('"i1" = "odb-exa-abc"', files['terraform.auto.tfvars'])
        self.assertIn('existing_infra_ids', files['terraform.auto.tfvars'])

    def test_external_infra_rewires_every_reference(self):
        main = self._gen(infra_external=True)['main.tf']
        self.assertIn('infra_ids = merge(', main)
        self.assertNotIn('module.aws_exadata_infra[each.value.infra_ref].infra_id', main)
        # both the data source and the VM cluster module go through the map
        self.assertEqual(main.count('local.infra_ids[each.value.infra_ref]'), 2)
        # the network is still managed, so its wiring is untouched
        self.assertIn('module.aws_odb_network[each.value.network_ref].network_id', main)

    def test_external_network_rewires_cluster_and_peering(self):
        main = self._gen(net_external=True)['main.tf']
        self.assertNotIn('module.aws_odb_network[each.value.network_ref].network_id', main)
        self.assertEqual(main.count('local.odb_network_ids[each.value.network_ref]'), 2)

    def test_external_declares_its_root_variable(self):
        variables = self._gen(infra_external=True, net_external=True)['variables.tf']
        self.assertIn('variable "existing_infra_ids"', variables)
        self.assertIn('variable "existing_odb_network_ids"', variables)
        self.assertIn('type        = map(string)', variables)

    def test_missing_id_becomes_a_visible_placeholder(self):
        files = generate_all({
            'cloud': 'aws',
            'aws_networks': [aws_net('n1')],
            'aws_infras':   [{**aws_infra('i1'), 'is_existing': True}],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        })
        self.assertIn('"i1" = "CHANGEME"', files['terraform.auto.tfvars'])


class TestExternalAwsValidation(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def _validate(self, tab, key, row):
        return self.client.post('/api/validate',
            json={'cloud': 'aws', 'tab': tab, key: [row]},
            content_type='application/json').get_json()

    def test_external_infra_skips_creation_fields(self):
        d = self._validate(1, 'aws_infras',
                           {'module_name': 'i1', 'is_existing': True, 'existing_id': 'odb-exa-abc'})
        self.assertTrue(d['valid'], d['errors'])

    def test_external_infra_requires_an_id(self):
        d = self._validate(1, 'aws_infras', {'module_name': 'i1', 'is_existing': True})
        self.assertFalse(d['valid'])
        self.assertIn('existing_id', d['errors'])

    def test_external_network_skips_creation_fields(self):
        d = self._validate(0, 'aws_networks',
                           {'module_name': 'n1', 'is_existing': True, 'existing_id': 'odb-net-abc'})
        self.assertTrue(d['valid'], d['errors'])

    def test_managed_infra_still_validated(self):
        d = self._validate(1, 'aws_infras', {'module_name': 'i1'})
        self.assertFalse(d['valid'])
        self.assertIn('display_name', d['errors'])


# ══════════════════════════════════════════════════════════════════════════════
#  19a. SPREADSHEET IMPORT
#  The parsed doc is merged straight into the form's state arrays, so any
#  comma-separated column has to come back as a real list.
# ══════════════════════════════════════════════════════════════════════════════

class TestSpreadsheetImport(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def _round_trip(self, cloud):
        tpl = self.client.get(f'/api/import/template/{cloud}')
        self.assertEqual(tpl.status_code, 200, f'{cloud} template download failed')
        r = self.client.post(
            '/api/import/spreadsheet',
            data={'file': (io.BytesIO(tpl.data), 't.xlsx'), 'cloud': cloud},
            content_type='multipart/form-data')
        doc = r.get_json()
        self.assertNotIn('error', doc, f'{cloud} import returned an error')
        return doc

    def test_template_round_trips_for_every_cloud(self):
        for cloud in ('aws', 'gcp', 'azure'):
            with self.subTest(cloud=cloud):
                doc = self._round_trip(cloud)
                self.assertTrue(doc.get('_import_summary'))

    def test_comma_separated_columns_parse_as_lists(self):
        doc = self._round_trip('aws')
        LIST_FIELDS = ('ssh_public_keys', 'customer_contacts',
                       'peer_network_cidrs', 'db_servers', 'db_server_ocids')
        seen = 0
        for rows in doc.values():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for field in LIST_FIELDS:
                    if field in row:
                        seen += 1
                        self.assertIsInstance(
                            row[field], list,
                            f'{field} must be a list, got {row[field]!r}')
        self.assertTrue(seen, 'no list-valued column present to check')

    def test_ssh_public_keys_splits_on_commas(self):
        from spreadsheet_importer import _coerce
        self.assertEqual(_coerce('ssh-rsa AAA, ssh-rsa BBB', 'ssh_public_keys'),
                         ['ssh-rsa AAA', 'ssh-rsa BBB'])
        self.assertEqual(_coerce('a@x.com,,b@x.com ', 'customer_contacts'),
                         ['a@x.com', 'b@x.com'])


# ══════════════════════════════════════════════════════════════════════════════
#  19b. VM CLUSTER OPTIONAL ATTRIBUTES REACH terraform.auto.tfvars
#  The root variables/module blocks accept these, so dropping them from tfvars
#  silently reverts the user's form input to the optional() defaults.
# ══════════════════════════════════════════════════════════════════════════════

class TestVmClusterOptionalsInTfvars(unittest.TestCase):

    def _aws_tfvars(self, **cluster_kw):
        return generate_all({
            'cloud': 'aws',
            'aws_networks': [aws_net('odb_network')],
            'aws_infras':   [aws_infra('odb_infra')],
            'aws_clusters': [aws_cluster('odb_cluster', **cluster_kw)],
        })['terraform.auto.tfvars']

    def test_aws_optional_strings_and_numbers_are_emitted(self):
        tfvars = self._aws_tfvars(
            cluster_name='gic-prod', timezone='UTC',
            data_storage_size_in_tbs='8.5', db_node_storage_size_in_gbs='120',
            memory_size_in_gbs='60', scan_listener_port_tcp='1522',
        )
        self.assertIn('cluster_name                      = "gic-prod"', tfvars)
        self.assertIn('timezone                          = "UTC"', tfvars)
        self.assertIn('data_storage_size_in_tbs          = 8.5', tfvars)
        self.assertIn('db_node_storage_size_in_gbs       = 120', tfvars)
        self.assertIn('memory_size_in_gbs                = 60', tfvars)
        self.assertIn('scan_listener_port_tcp            = 1522', tfvars)

    def test_aws_blank_optionals_are_omitted_not_quoted_empty(self):
        tfvars = self._aws_tfvars(
            cluster_name='', timezone='', data_storage_size_in_tbs='',
            memory_size_in_gbs='', scan_listener_port_tcp='',
        )
        self.assertNotIn('cluster_name', tfvars)
        self.assertNotIn('data_storage_size_in_tbs', tfvars)
        self.assertNotIn('scan_listener_port_tcp', tfvars)

    def test_aws_optional_booleans_are_always_emitted(self):
        tfvars = self._aws_tfvars(
            dco_is_diagnostics_events_enabled=False,
            dco_is_health_monitoring_enabled=False,
            dco_is_incident_logs_enabled=True,
            is_local_backup_enabled=True,
            is_sparse_diskgroup_enabled=True,
        )
        self.assertIn('dco_is_diagnostics_events_enabled = false', tfvars)
        self.assertIn('dco_is_health_monitoring_enabled  = false', tfvars)
        self.assertIn('dco_is_incident_logs_enabled      = true', tfvars)
        self.assertIn('is_local_backup_enabled           = true', tfvars)
        self.assertIn('is_sparse_diskgroup_enabled       = true', tfvars)

    def _gcp_tfvars(self, **cluster_kw):
        return generate_all({
            'cloud': 'gcp',
            'gcp_networks': [gcp_net('gcp_network')],
            'gcp_infras':   [gcp_infra('gcp_infra')],
            'gcp_clusters': [gcp_cluster('gcp_cluster', **cluster_kw)],
        })['terraform.auto.tfvars']

    def test_gcp_optionals_are_emitted(self):
        tfvars = self._gcp_tfvars(
            location='us-east4', project='my-proj', cluster_name='gic',
            time_zone='America/New_York', scan_listener_port_tcp='1522',
            dco_diagnostics=False, dco_health=True, dco_incident_logs=False,
        )
        self.assertIn('location                 = "us-east4"', tfvars)
        self.assertIn('project                  = "my-proj"', tfvars)
        self.assertIn('cluster_name             = "gic"', tfvars)
        self.assertIn('time_zone                = "America/New_York"', tfvars)
        self.assertIn('scan_listener_port_tcp   = 1522', tfvars)
        self.assertIn('dco_diagnostics          = false', tfvars)
        self.assertIn('dco_incident_logs        = false', tfvars)

    def test_gcp_blank_optionals_are_omitted(self):
        tfvars = self._gcp_tfvars(cluster_name='', time_zone='', scan_listener_port_tcp='')
        self.assertNotIn('cluster_name', tfvars)
        self.assertNotIn('scan_listener_port_tcp', tfvars)


# ══════════════════════════════════════════════════════════════════════════════
#  19b-1. NO VM CLUSTER UNLESS ONE WAS ASKED FOR
#  The page used to seed a VM Cluster card on load, and the generator invented
#  one from the legacy module_3 defaults whenever aws_clusters was empty — so a
#  cluster nobody configured reached terraform.auto.tfvars.
# ══════════════════════════════════════════════════════════════════════════════

class TestNoDefaultVmCluster(unittest.TestCase):

    BASE = {
        'cloud': 'aws',
        'aws_networks': [aws_net('n1')],
        'aws_infras':   [aws_infra('i1')],
        'aws_peerings': [],
    }

    def test_empty_cluster_list_generates_no_cluster(self):
        files = generate_all({**self.BASE, 'aws_clusters': []})
        self.assertIn('aws_clusters = {\n}', files['terraform.auto.tfvars'])
        self.assertNotIn('odb_vm_cluster', files['terraform.auto.tfvars'])

    def test_the_shared_module_is_still_emitted(self):
        # for_each means an entry can be appended to tfvars later without
        # regenerating, so the module directory and its variable stay.
        files = generate_all({**self.BASE, 'aws_clusters': []})
        self.assertIn('modules/aws-vm-cluster/main.tf', files)
        self.assertIn('for_each = var.aws_clusters', files['main.tf'])
        self.assertIn('variable "aws_clusters"', files['variables.tf'])

    def test_legacy_single_instance_configs_still_get_their_cluster(self):
        # module_3 is the pre-multi-instance save format; only its presence
        # revives the one-cluster shim.
        files = generate_all({**self.BASE, 'module_names': {'3': 'cl'},
                              'module_3': aws_cluster('cl')})
        self.assertIn('"cl" = {', files['terraform.auto.tfvars'])

    def test_the_page_seeds_no_cluster_card(self):
        page = (Path(__file__).resolve().parent.parent
                / 'clouds' / 'aws' / 'pages' / 'aws.html').read_text(encoding='utf-8')
        self.assertNotIn('awsClusters.push(defAwsCluster(0))', page)
        # The resources that do seed one are unaffected.
        self.assertIn('awsNets.push(defAwsNet(0))', page)
        self.assertIn('awsInfras.push(defAwsInfra(0))', page)

    def test_the_only_cluster_card_can_be_removed(self):
        # Zero is a valid state for both cluster kinds, so the guard that kept
        # the last card undeletable made "+ Add" a one-way door.
        page = (Path(__file__).resolve().parent.parent
                / 'clouds' / 'aws' / 'pages' / 'aws.html').read_text(encoding='utf-8')
        self.assertIn('${awsClusters.length>0?`<button class="inst-rm"', page)
        self.assertIn('${awsAvmcs.length>0?`<button class="inst-rm"', page)

    def test_seeded_resources_keep_their_last_card(self):
        # Networks are still seeded and the generator still materialises one
        # from an empty payload — deleting the last card would put it back.
        page = (Path(__file__).resolve().parent.parent
                / 'clouds' / 'aws' / 'pages' / 'aws.html').read_text(encoding='utf-8')
        self.assertIn('${awsNets.length>1?`<button class="inst-rm"', page)

    def test_last_infra_and_peering_can_be_removed(self):
        # A Serverless-only deployment has no Exadata Infrastructure, and may
        # have no peering. Keeping the last card generated an X11M and a peering
        # to vpc-CHANGEME beside the database.
        page = (Path(__file__).resolve().parent.parent
                / 'clouds' / 'aws' / 'pages' / 'aws.html').read_text(encoding='utf-8')
        for arr in ('awsInfras', 'awsPeerings'):
            self.assertIn('${%s.length>0?`<button class="inst-rm"' % arr, page)

    def test_an_explicit_empty_list_generates_none(self):
        files = generate_all({'cloud': 'aws', 'aws_networks': [aws_net('n1')],
                              'aws_infras': [], 'aws_peerings': []})
        tfvars = files['terraform.auto.tfvars']
        self.assertIn('aws_infras = {}', tfvars)
        self.assertIn('aws_peerings = {\n}', tfvars)
        self.assertNotIn('vpc-CHANGEME', tfvars)

    def test_a_payload_without_the_keys_still_gets_the_seeded_instances(self):
        # Legacy and half-filled payloads keep the old behaviour.
        tfvars = generate_all({'cloud': 'aws'})['terraform.auto.tfvars']
        self.assertIn('"odb_exadata_infra" = {', tfvars)
        self.assertIn('"odb_peering" = {', tfvars)


# ══════════════════════════════════════════════════════════════════════════════
#  19b-2. db_servers_mode — WHICH SERVERS A CLUSTER IS PLACED ON
#  A DB server hosts one VM per cluster and reports allocated-vs-total capacity,
#  and vm_cluster_ids is a list — so a server another cluster sits on is still a
#  valid target. "auto" must therefore offer every server; excluding allocated
#  ones is a separate, opt-in mode.
# ══════════════════════════════════════════════════════════════════════════════

class TestDbServersMode(unittest.TestCase):

    ALLOCATION_FILTER = 'length(s.vm_cluster_ids) == 0 && length(s.autonomous_vm_cluster_ids) == 0'

    def _main(self, mode, avmc_mode=None):
        return generate_all({
            'cloud': 'aws',
            'aws_networks': [aws_net('n1')],
            'aws_infras':   [aws_infra('i1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1',
                                         db_servers_mode=mode, db_servers=['db-1'])],
            'aws_avmclusters': ([aws_avmc('av1', db_servers_mode=avmc_mode, db_servers=['db-1'])]
                                if avmc_mode else []),
        })['main.tf']

    def test_auto_offers_every_server_on_the_infrastructure(self):
        main = self._main('auto')
        self.assertIn('d.db_servers[*].id', main)
        # The filter is reachable only through the "unallocated" branch.
        self.assertIn('var.aws_clusters[k].db_servers_mode == "unallocated"', main)

    def test_discovery_covers_every_non_manual_mode(self):
        # for_each on == "auto" would leave "unallocated" clusters without a
        # data source entry, and the lookup would fall back to their empty list.
        self.assertIn('if v.db_servers_mode != "manual"', self._main('unallocated'))

    def test_manual_falls_back_to_the_supplied_list(self):
        main = self._main('manual')
        self.assertIn('lookup(local.discovered_db_servers, k, v.db_servers)', main)
        self.assertIn('db_servers                        = local.cluster_db_servers[each.key]', main)

    def test_unallocated_gets_a_plan_time_warning(self):
        main = self._main('unallocated')
        self.assertIn('check "unallocated_db_servers_available"', main)
        self.assertIn(self.ALLOCATION_FILTER, main)

    def test_avmclusters_get_the_same_three_modes(self):
        main = self._main('auto', avmc_mode='unallocated')
        self.assertIn('var.aws_avmclusters[k].db_servers_mode == "unallocated"', main)
        self.assertIn('db_servers = local.avmc_db_servers[each.key]', main)
        self.assertIn('check "unallocated_avmc_db_servers_available"', main)

    def test_mode_is_validated_in_terraform_not_just_the_form(self):
        # A hand-edited tfvars is the one path the browser cannot police.
        variables = generate_all({
            'cloud': 'aws',
            'aws_networks': [aws_net('n1')],
            'aws_infras':   [aws_infra('i1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
            'aws_avmclusters': [aws_avmc('av1')],
        })['variables.tf']
        self.assertEqual(2, variables.count(
            'contains(["auto", "unallocated", "manual"], c.db_servers_mode)'))

    def test_the_page_offers_all_three(self):
        page = (Path(__file__).resolve().parent.parent
                / 'clouds' / 'aws' / 'pages' / 'aws.html').read_text(encoding='utf-8')
        for mode in ('auto', 'unallocated', 'manual'):
            # One radio per mode on the VM cluster card and on the AVMC card.
            self.assertEqual(2, page.count('value="%s" ${' % mode),
                             'db_servers_mode radio for %r is missing from a card' % mode)


# ══════════════════════════════════════════════════════════════════════════════
#  19c. AUTONOMOUS VM CLUSTERS ARE for_each MODULES
#  Every other AWS resource type is one module driven by a map in
#  terraform.auto.tfvars; the AVMC used to be one module directory and six
#  flat root variables per instance, so adding one rewrote main.tf.
# ══════════════════════════════════════════════════════════════════════════════

def aws_avmc(module_name='odb_avmcluster', **kw):
    return {
        'module_name': module_name,
        'display_name': 'test-avmc',
        'infra_ref': 'i1',
        'network_ref': 'n1',
        'autonomous_data_storage_size_in_tbs': 5,
        **kw,
    }


class TestAvmClustersAreModular(unittest.TestCase):

    def _files(self, avmcs):
        return generate_all({
            'cloud': 'aws',
            'aws_networks': [aws_net('n1')],
            'aws_infras':   [aws_infra('i1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
            'aws_avmclusters': avmcs,
        })

    def test_instances_live_in_the_tfvars_map(self):
        tfvars = self._files([aws_avmc('av1'), aws_avmc('av2', cpu_core_count_per_node=80)])['terraform.auto.tfvars']
        self.assertIn('aws_avmclusters = {', tfvars)
        self.assertIn('"av1" = {', tfvars)
        self.assertIn('"av2" = {', tfvars)
        self.assertIn('cpu_core_count_per_node               = 80', tfvars)

    def test_one_shared_module_serves_every_instance(self):
        files = self._files([aws_avmc('av1'), aws_avmc('av2')])
        avmc_files = sorted(p for p in files if 'avmcluster' in p)
        self.assertEqual(avmc_files, [
            'modules/aws-avmcluster/main.tf',
            'modules/aws-avmcluster/outputs.tf',
            'modules/aws-avmcluster/variables.tf',
        ])
        self.assertIn('for_each = var.aws_avmclusters', files['main.tf'])

    def test_adding_an_instance_leaves_main_tf_untouched(self):
        one = self._files([aws_avmc('av1')])['main.tf']
        two = self._files([aws_avmc('av1'), aws_avmc('av2')])['main.tf']
        self.assertEqual(one, two)

    def test_maintenance_schedule_reaches_tfvars(self):
        # Read only for a has-schedule flag before, then dropped — the generated
        # module took its window from a variable default no tfvars entry set.
        tfvars = self._files([aws_avmc('av1', mw_preference='CUSTOM_PREFERENCE',
                                       mw_days_of_week='MONDAY, TUESDAY',
                                       mw_hours_of_day='4, 16',
                                       mw_lead_time_in_weeks='2')])['terraform.auto.tfvars']
        self.assertIn('mw_preference                         = "CUSTOM_PREFERENCE"', tfvars)
        self.assertIn('mw_days_of_week                       = ["MONDAY", "TUESDAY"]', tfvars)
        self.assertIn('mw_hours_of_day                       = [4, 16]', tfvars)
        self.assertIn('mw_lead_time_in_weeks                 = 2', tfvars)

    def test_a_config_without_avmcs_carries_nothing(self):
        files = self._files([])
        self.assertEqual([p for p in files if 'avmcluster' in p], [])
        self.assertNotIn('aws_avmclusters', files['main.tf'])
        self.assertNotIn('aws_avmclusters', files['variables.tf'])
        self.assertNotIn('aws_avmclusters', files['terraform.auto.tfvars'])

    def test_arn_pair_instances_get_their_own_map_and_module(self):
        # The provider takes the id pair or the arn pair and rejects both, and a
        # null attribute still counts as present — so the two cannot share one
        # module with a conditional argument.
        files = self._files([
            aws_avmc('av1'),
            aws_avmc('avarn', infra_ref='', network_ref='', db_servers=['db-1'],
                     cloud_exadata_infrastructure_arn='arn:aws:odb:us-east-1:1:cloud-exadata-infrastructure/x',
                     odb_network_arn='arn:aws:odb:us-east-1:1:odb-network/y'),
        ])
        tfvars = files['terraform.auto.tfvars']
        self.assertIn('aws_avmclusters_arn = {', tfvars)
        self.assertIn('"avarn" = {', tfvars)
        # ...and stays out of the id-pair map.
        id_map = tfvars.split('aws_avmclusters = {')[1].split('\n}')[0]
        self.assertNotIn('avarn', id_map)

        self.assertIn('modules/aws-avmcluster-arn/main.tf', files)
        arn_mod = files['modules/aws-avmcluster-arn/main.tf']
        self.assertIn('cloud_exadata_infrastructure_arn = var.cloud_exadata_infrastructure_arn', arn_mod)
        self.assertNotIn('cloud_exadata_infrastructure_id', arn_mod)
        self.assertNotIn('odb_network_id', arn_mod)


# ══════════════════════════════════════════════════════════════════════════════
#  19d. AZURE BACKUP SUBNET CIDR
#  Several VM clusters legitimately share one delegated subnet, but Oracle carves
#  the backup range inside the VNet per cluster — so those ranges must not
#  collide with each other or with the delegated subnet itself.
# ══════════════════════════════════════════════════════════════════════════════

class TestAzureBackupSubnetValidation(unittest.TestCase):

    VNETS = [
        {'module_name': 'av1', 'subnet_address_prefix': '10.0.1.0/24'},
        {'module_name': 'av2', 'subnet_address_prefix': '10.1.1.0/24'},
    ]

    def setUp(self):
        self.client = app.test_client()

    @staticmethod
    def _cluster(mn, vnet='av1', **kw):
        return {
            'module_name': mn, 'resource_group_name': 'rg', 'location': 'eastus',
            'name': mn, 'display_name': mn, 'hostname': 'h', 'gi_version': '19.0.0.0',
            'cpu_core_count': 4, 'data_storage_size_in_tbs': 2,
            'ssh_public_keys': ['ssh-rsa AAAA'], 'vnet_ref': vnet, **kw,
        }

    def _validate(self, clusters):
        return self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 22,
            'azure_vnets': self.VNETS, 'azure_clusters': clusters,
        }, content_type='application/json').get_json()

    def _backup_errors(self, clusters):
        d = self._validate(clusters)
        return {mn: errs['backup_subnet_cidr']
                for mn, errs in d['errors_by_module'].items() if 'backup_subnet_cidr' in errs}

    def test_single_cluster_may_omit_the_backup_cidr(self):
        # Nothing to collide with — Oracle can pick the default range.
        self.assertTrue(self._validate([self._cluster('ac1')])['valid'])

    def test_clusters_sharing_a_subnet_must_each_declare_one(self):
        errs = self._backup_errors([self._cluster('ac1'), self._cluster('ac2')])
        self.assertEqual(sorted(errs), ['ac1', 'ac2'])
        self.assertIn('share a delegated subnet', errs['ac1'])

    def test_sharing_a_subnet_with_distinct_ranges_is_valid(self):
        d = self._validate([
            self._cluster('ac1', backup_subnet_cidr='10.0.10.0/24'),
            self._cluster('ac2', backup_subnet_cidr='10.0.11.0/24'),
        ])
        self.assertTrue(d['valid'], d['errors'])

    def test_identical_backup_ranges_rejected(self):
        errs = self._backup_errors([
            self._cluster('ac1', backup_subnet_cidr='10.0.10.0/24'),
            self._cluster('ac2', backup_subnet_cidr='10.0.10.0/24'),
        ])
        self.assertIn('Overlaps the backup subnet of ac1', errs.get('ac2', ''))

    def test_partially_overlapping_backup_ranges_rejected(self):
        # /22 supernet swallows the /24 — not caught by an equality check.
        errs = self._backup_errors([
            self._cluster('ac1', backup_subnet_cidr='10.0.8.0/22'),
            self._cluster('ac2', backup_subnet_cidr='10.0.10.0/24'),
        ])
        self.assertIn('Overlaps the backup subnet of ac1', errs.get('ac2', ''))

    def test_backup_range_may_not_overlap_the_delegated_subnet(self):
        errs = self._backup_errors([self._cluster('ac1', backup_subnet_cidr='10.0.1.128/25')])
        self.assertIn('Overlaps the delegated subnet 10.0.1.0/24', errs.get('ac1', ''))

    def test_same_range_on_a_different_vnet_is_fine(self):
        # Separate VNets are separate address spaces.
        d = self._validate([
            self._cluster('ac1', 'av1', backup_subnet_cidr='10.0.10.0/24'),
            self._cluster('ac2', 'av2', backup_subnet_cidr='10.0.10.0/24'),
        ])
        self.assertTrue(d['valid'], d['errors'])

    def test_malformed_cidr_rejected(self):
        for bad in ('10.0.10.0', 'not-a-cidr', '10.0.10.0/', ''):
            with self.subTest(value=bad):
                errs = self._backup_errors([
                    self._cluster('ac1', backup_subnet_cidr=bad),
                    self._cluster('ac2', backup_subnet_cidr='10.0.11.0/24'),
                ])
                self.assertIn('ac1', errs, '%r should not be accepted' % bad)


# ══════════════════════════════════════════════════════════════════════════════
#  20. TERRAFORM FMT
#  Requires terraform or tofu in PATH; skipped automatically when absent.
# ══════════════════════════════════════════════════════════════════════════════

class TestTerraformFmt(unittest.TestCase):
    """Generated .tf files must pass `terraform fmt -check`."""

    @classmethod
    def setUpClass(cls):
        import shutil
        cls.tf_bin = shutil.which('terraform') or shutil.which('tofu')

    def _assert_fmt_clean(self, files):
        if not self.__class__.tf_bin:
            self.skipTest('terraform/tofu not found in PATH')
        import subprocess
        with tempfile.TemporaryDirectory() as tmpdir:
            for rel_path, content in files.items():
                # .tfvars counts: terraform fmt formats it, and the live preview
                # shows it unformatted, so drift there is user-visible.
                if not rel_path.endswith(('.tf', '.tfvars')):
                    continue
                full = Path(tmpdir) / rel_path
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content, encoding='utf-8')
            result = subprocess.run(
                [self.__class__.tf_bin, 'fmt', '-check', '-recursive', tmpdir],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                bad = [l.strip() for l in result.stdout.splitlines() if l.strip()]
                self.fail(
                    f'terraform fmt -check found {len(bad)} file(s) needing formatting:\n'
                    + '\n'.join(bad)
                )

    def test_aws_tf_files_are_formatted(self):
        self._assert_fmt_clean(generate_all({
            'cloud': 'aws',
            'aws_networks':  [aws_net('n1')],
            'aws_infras':    [aws_infra('i1')],
            'aws_peerings':  [aws_peer('p1', network_ref='n1')],
            'aws_clusters':  [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        }))

    def test_aws_avmcluster_files_are_formatted(self):
        self._assert_fmt_clean(generate_all({
            'cloud': 'aws',
            'aws_networks': [aws_net('n1')],
            'aws_infras':   [aws_infra('i1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
            'aws_avmclusters': [{
                'module_name': 'av1', 'display_name': 'av',
                'infra_ref': 'i1', 'network_ref': 'n1',
                'autonomous_data_storage_size_in_tbs': 5,
            }],
        }))

    def test_aws_avmcluster_with_schedule_is_formatted(self):
        self._assert_fmt_clean(generate_all({
            'cloud': 'aws',
            'aws_networks': [aws_net('n1')],
            'aws_infras':   [aws_infra('i1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
            'aws_avmclusters': [{
                'module_name': 'av1', 'display_name': 'av',
                'infra_ref': 'i1', 'network_ref': 'n1',
                'autonomous_data_storage_size_in_tbs': 5,
                'mw_preference': 'CUSTOM_PREFERENCE',
                'mw_days_of_week': 'MONDAY', 'mw_hours_of_day': '4',
            }],
        }))

    def test_aws_avmcluster_arn_pair_is_formatted(self):
        self._assert_fmt_clean(generate_all({
            'cloud': 'aws',
            'aws_networks': [aws_net('n1')],
            'aws_infras':   [aws_infra('i1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
            'aws_avmclusters': [{
                'module_name': 'avarn', 'display_name': 'av',
                'autonomous_data_storage_size_in_tbs': 5,
                'db_servers': ['db-1'],
                'cloud_exadata_infrastructure_arn': 'arn:aws:odb:us-east-1:111122223333:cloud-exadata-infrastructure/x',
                'odb_network_arn': 'arn:aws:odb:us-east-1:111122223333:odb-network/y',
            }],
        }))

    def test_aws_external_resources_are_formatted(self):
        self._assert_fmt_clean(generate_all({
            'cloud': 'aws',
            'aws_networks': [{**aws_net('n1'), 'is_existing': True, 'existing_id': 'odb-net-a'}],
            'aws_infras':   [{**aws_infra('i1'), 'is_existing': True, 'existing_id': 'odb-exa-a'}],
            'aws_peerings': [aws_peer('p1', network_ref='n1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        }))

    def test_azure_tf_files_are_formatted(self):
        self._assert_fmt_clean(generate_all({
            'cloud': 'azure',
            'azure_vnets':    [{'module_name': 'av1'}],
            'azure_infras':   [{'module_name': 'ai1'}],
            'azure_clusters': [{'module_name': 'ac1', 'infra_ref': 'ai1', 'vnet_ref': 'av1'}],
        }))

    def test_azure_autonomous_database_files_are_formatted(self):
        self._assert_fmt_clean(generate_all({
            'cloud': 'azure',
            'azure_vnets': [{'module_name': 'av1'}],
            'azure_autonomous_dbs': [
                {'module_name': 'adb1', 'name': 'adb-one', 'display_name': 'One',
                 'vnet_ref': 'av1', 'customer_contacts': ['dba@example.com']},
                # Public endpoint: no VNet, an allowed_ips ACL instead.
                {'module_name': 'adb2', 'name': 'adb-two', 'display_name': 'Two',
                 'vnet_ref': '', 'allowed_ips': ['203.0.113.0/24'], 'db_workload': 'DW'},
            ],
        }))

    def test_gcp_tf_files_are_formatted(self):
        self._assert_fmt_clean(generate_all({
            'cloud': 'gcp',
            'gcp_networks':  [gcp_net('gnet1')],
            'gcp_infras':    [gcp_infra('ginf1')],
            'gcp_clusters':  [gcp_cluster('gcl1', 'gnet1', 'ginf1')],
        }))


# ══════════════════════════════════════════════════════════════════════════════
#  21. TERRAFORM VALIDATE
#  Requires terraform or tofu in PATH; skipped automatically when absent.
#  Downloads providers on first run (~400 MB); subsequent runs use the cache.
# ══════════════════════════════════════════════════════════════════════════════

class TestTerraformValidate(unittest.TestCase):
    """Generated Terraform must pass `terraform validate` after `terraform init`."""

    @classmethod
    def setUpClass(cls):
        import shutil
        cls.tf_bin = shutil.which('terraform') or shutil.which('tofu')

    # Provider plugin crashes on Windows ("Plugin did not respond") are outside
    # our control — skip rather than fail so the suite stays green on all platforms.
    _PLUGIN_SKIP_PHRASES = (
        'Plugin did not respond',
        'Could not load the schema',
        'plugin crashed',
        'rpc error',
    )

    def _validate_files(self, files):
        if not self.__class__.tf_bin:
            self.skipTest('terraform/tofu not found in PATH')
        import subprocess
        import json as _json

        # Windows keeps a handle on the downloaded provider .exe after init, so
        # cleanup can raise PermissionError long after the assertions passed.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            for rel_path, content in files.items():
                full = Path(tmpdir) / rel_path
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content, encoding='utf-8')

            init = subprocess.run(
                [self.__class__.tf_bin, 'init', '-no-color', '-backend=false'],
                capture_output=True, text=True, cwd=tmpdir,
                timeout=300,
            )
            if init.returncode != 0:
                combined = (init.stderr or '') + (init.stdout or '')
                if any(p in combined for p in self._PLUGIN_SKIP_PHRASES):
                    self.skipTest(f'terraform init: provider plugin error (skipped on this platform)')
                self.fail(f'terraform init failed:\n{init.stderr or init.stdout}')

            val = subprocess.run(
                [self.__class__.tf_bin, 'validate', '-no-color', '-json'],
                capture_output=True, text=True, cwd=tmpdir,
                timeout=60,
            )
            if val.returncode != 0:
                combined = (val.stderr or '') + (val.stdout or '')
                if any(p in combined for p in self._PLUGIN_SKIP_PHRASES):
                    self.skipTest(f'terraform validate: provider plugin error (skipped on this platform)')
                try:
                    diags = _json.loads(val.stdout).get('diagnostics', [])
                    msgs = '\n'.join(
                        f"[{d['severity']}] {d['summary']}: {d.get('detail', '')}"
                        for d in diags
                    )
                except Exception:
                    msgs = val.stdout or val.stderr
                self.fail(f'terraform validate failed:\n{msgs}')

    def test_aws_config_validates(self):
        self._validate_files(generate_all({
            'cloud': 'aws',
            'aws_networks':  [aws_net('n1')],
            'aws_infras':    [aws_infra('i1')],
            'aws_peerings':  [aws_peer('p1', network_ref='n1')],
            'aws_clusters':  [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
        }))

    def test_aws_avmcluster_and_external_resources_validate(self):
        """Covers three regressions at once, in one init:

        - AVMC maintenance_window carried patching_mode /
          is_custom_action_timeout_enabled / custom_action_timeout_in_mins,
          which the provider only accepts on the Exadata Infrastructure.
        - The AVMC sent both the id pair and the arn pair; the provider rejects
          that, and a null-valued attribute still counts as present.
        - db_servers is a required argument and was omitted for a manual,
          still-empty server list.
        """
        self._validate_files(generate_all({
            'cloud': 'aws',
            'aws_networks': [{**aws_net('n1'), 'is_existing': True, 'existing_id': 'odb-net-a'}],
            'aws_infras':   [{**aws_infra('i1'), 'is_existing': True, 'existing_id': 'odb-exa-a'}],
            'aws_peerings': [aws_peer('p1', network_ref='n1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
            'aws_avmclusters': [{
                'module_name': 'av1', 'display_name': 'av',
                'infra_ref': 'i1', 'network_ref': 'n1',
                'autonomous_data_storage_size_in_tbs': 5,
                'db_servers_mode': 'manual', 'db_servers': [],
            }],
        }))

    def test_aws_db_servers_modes_validate(self):
        """The three db_servers_mode branches, the locals that resolve them and
        the check blocks that guard "unallocated", in one init."""
        self._validate_files(generate_all({
            'cloud': 'aws',
            'aws_networks': [aws_net('n1')],
            'aws_infras':   [aws_infra('i1')],
            'aws_clusters': [
                aws_cluster('c1', infra_ref='i1', network_ref='n1', db_servers_mode='auto'),
                aws_cluster('c2', infra_ref='i1', network_ref='n1', db_servers_mode='unallocated'),
                aws_cluster('c3', infra_ref='i1', network_ref='n1',
                            db_servers_mode='manual', db_servers=['db-1']),
            ],
            'aws_avmclusters': [{
                'module_name': 'av1', 'display_name': 'av',
                'infra_ref': 'i1', 'network_ref': 'n1',
                'autonomous_data_storage_size_in_tbs': 5,
                'db_servers_mode': 'unallocated',
            }],
        }))

    def test_aws_avmcluster_arn_pair_validates(self):
        """The arn-pair AVMC is a second module for the same provider constraint:
        the id pair must be absent from the configuration, not set to null."""
        self._validate_files(generate_all({
            'cloud': 'aws',
            'aws_networks': [aws_net('n1')],
            'aws_infras':   [aws_infra('i1')],
            'aws_clusters': [aws_cluster('c1', infra_ref='i1', network_ref='n1')],
            'aws_avmclusters': [{
                'module_name': 'avarn', 'display_name': 'av',
                'autonomous_data_storage_size_in_tbs': 5,
                'db_servers': ['db-1'],
                'cloud_exadata_infrastructure_arn': 'arn:aws:odb:us-east-1:111122223333:cloud-exadata-infrastructure/x',
                'odb_network_arn': 'arn:aws:odb:us-east-1:111122223333:odb-network/y',
            }],
        }))

    def test_azure_autonomous_database_validates(self):
        """First real terraform validate on the Azure side. admin_password has no
        default on purpose, which validate tolerates — it is only required at
        plan time, from TF_VAR_<module>_admin_password."""
        self._validate_files(generate_all({
            'cloud': 'azure',
            'resource_group_name': 'my-rg',
            'azure_vnets': [azure_vnet('av1')],
            'azure_autonomous_dbs': [
                azure_adb('adb1', vnet_ref='av1'),
                azure_adb('adb2', vnet_ref='', allowed_ips=['203.0.113.0/24'],
                          db_workload='DW', db_version='23ai',
                          mtls_connection_required=False),
            ],
        }))

    def test_gcp_config_validates(self):
        self._validate_files(generate_all({
            'cloud': 'gcp',
            'gcp_networks':  [gcp_net('gnet1')],
            'gcp_infras':    [gcp_infra('ginf1')],
            'gcp_clusters':  [gcp_cluster('gcl1', 'gnet1', 'ginf1')],
        }))


# ══════════════════════════════════════════════════════════════════════════════
#  RAG — BM25 retrieval engine
# ══════════════════════════════════════════════════════════════════════════════

import rag as rag_module


class TestRagEngine(unittest.TestCase):
    """Unit tests for rag.py — BM25 index building and retrieval."""

    def setUp(self):
        # Point RAG at a fresh temp directory so tests don't pollute data/
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self._tmpdir.name)
        self._orig_docs     = rag_module.DOCS_DIR
        self._orig_index    = rag_module.INDEX_PATH
        self._orig_chroma   = rag_module.CHROMA_PATH
        self._orig_provider = os.environ.pop('EMBEDDING_PROVIDER', '')
        rag_module.DOCS_DIR    = tmp / 'rag_docs'
        rag_module.INDEX_PATH  = tmp / 'rag_index.json'
        rag_module.CHROMA_PATH = tmp / 'chroma'
        rag_module.DOCS_DIR.mkdir()
        rag_module.invalidate_cache()

        # Write two tiny knowledge docs
        (rag_module.DOCS_DIR / 'aws_network.md').write_text(
            'ODB Network resource aws_odb_network. '
            'Required fields: display_name client_subnet_cidr backup_subnet_cidr. '
            'Outputs: network_id network_name.',
            encoding='utf-8',
        )
        (rag_module.DOCS_DIR / 'vm_cluster.md').write_text(
            'VM Cluster resource aws_odb_cloud_vm_cluster. '
            'Required: cpu_core_count gi_version hostname_prefix license_model. '
            'gi_version valid values: 23.0.0.0.0 21.0.0.0.0 19.0.0.0.0.',
            encoding='utf-8',
        )

    def tearDown(self):
        rag_module.DOCS_DIR    = self._orig_docs
        rag_module.INDEX_PATH  = self._orig_index
        rag_module.CHROMA_PATH = self._orig_chroma
        if self._orig_provider:
            os.environ['EMBEDDING_PROVIDER'] = self._orig_provider
        rag_module.invalidate_cache()
        self._tmpdir.cleanup()

    # ── rebuild ───────────────────────────────────────────────────────────────

    def test_rebuild_returns_positive_chunk_count(self):
        n = rag_module.rebuild()
        self.assertGreater(n, 0)

    def test_rebuild_creates_index_file(self):
        rag_module.rebuild()
        self.assertTrue(rag_module.INDEX_PATH.exists())

    def test_rebuild_index_has_expected_keys(self):
        rag_module.rebuild()
        idx = json.loads(rag_module.INDEX_PATH.read_text(encoding='utf-8'))
        for key in ('chunks', 'idf', 'avg_len', 'n_docs'):
            self.assertIn(key, idx)

    def test_rebuild_indexes_both_docs(self):
        rag_module.rebuild()
        idx = json.loads(rag_module.INDEX_PATH.read_text(encoding='utf-8'))
        sources = {c['source'] for c in idx['chunks']}
        self.assertIn('aws_network.md', sources)
        self.assertIn('vm_cluster.md', sources)

    def test_rebuild_empty_docs_returns_zero(self):
        for f in rag_module.DOCS_DIR.iterdir():
            f.unlink()
        n = rag_module.rebuild()
        self.assertEqual(n, 0)

    # ── retrieve ──────────────────────────────────────────────────────────────

    def test_retrieve_returns_list(self):
        rag_module.rebuild()
        results = rag_module.retrieve('cpu_core_count', k=5)
        self.assertIsInstance(results, list)

    def test_retrieve_relevant_chunk_for_network_query(self):
        rag_module.rebuild()
        results = rag_module.retrieve('odb network display name subnet cidr', k=5)
        self.assertTrue(len(results) > 0)
        sources = [c['source'] for c in results]
        self.assertIn('aws_network.md', sources)

    def test_retrieve_relevant_chunk_for_vmcluster_query(self):
        rag_module.rebuild()
        results = rag_module.retrieve('vm cluster gi_version cpu_core_count', k=5)
        self.assertTrue(len(results) > 0)
        sources = [c['source'] for c in results]
        self.assertIn('vm_cluster.md', sources)

    def test_retrieve_nonsense_query_returns_empty(self):
        rag_module.rebuild()
        results = rag_module.retrieve('xyzzy foobar qux quux', k=5)
        self.assertEqual(results, [])

    def test_retrieve_respects_k(self):
        rag_module.rebuild()
        results = rag_module.retrieve('network cluster', k=1)
        self.assertLessEqual(len(results), 1)

    def test_retrieve_chunk_has_required_keys(self):
        rag_module.rebuild()
        results = rag_module.retrieve('network', k=3)
        for chunk in results:
            for key in ('id', 'source', 'text'):
                self.assertIn(key, chunk)

    # ── build_context ─────────────────────────────────────────────────────────

    def test_build_context_returns_string(self):
        rag_module.rebuild()
        ctx = rag_module.build_context('odb network subnet')
        self.assertIsInstance(ctx, str)

    def test_build_context_nonempty_for_known_query(self):
        rag_module.rebuild()
        ctx = rag_module.build_context('odb network subnet')
        self.assertTrue(len(ctx) > 0)

    def test_build_context_contains_source_header(self):
        rag_module.rebuild()
        ctx = rag_module.build_context('odb network subnet')
        self.assertIn('[aws_network.md]', ctx)

    def test_build_context_empty_for_nonsense(self):
        rag_module.rebuild()
        ctx = rag_module.build_context('xyzzy foobar qux')
        self.assertEqual(ctx, '')

    # ── index_stats ───────────────────────────────────────────────────────────

    def test_index_stats_returns_dict(self):
        rag_module.rebuild()
        stats = rag_module.index_stats()
        self.assertIsInstance(stats, dict)

    def test_index_stats_has_required_keys(self):
        rag_module.rebuild()
        stats = rag_module.index_stats()
        for key in ('n_chunks', 'n_docs', 'n_terms', 'index_path', 'docs_dir'):
            self.assertIn(key, stats)

    def test_index_stats_n_chunks_positive(self):
        rag_module.rebuild()
        stats = rag_module.index_stats()
        self.assertGreater(stats['n_chunks'], 0)

    def test_index_stats_n_terms_positive(self):
        rag_module.rebuild()
        stats = rag_module.index_stats()
        self.assertGreater(stats['n_terms'], 0)


class TestRagApiRoutes(unittest.TestCase):
    """Integration tests for /api/rag/* Flask routes."""

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        # Force BM25 so tests don't require Ollama to be running
        self._orig_provider = os.environ.pop('EMBEDDING_PROVIDER', '')
        rag_module.invalidate_cache()
        rag_module.rebuild()

    def tearDown(self):
        if self._orig_provider:
            os.environ['EMBEDDING_PROVIDER'] = self._orig_provider
        rag_module.invalidate_cache()

    # ── /api/rag/stats ────────────────────────────────────────────────────────

    def test_rag_stats_returns_200(self):
        r = self.client.get('/api/rag/stats')
        self.assertEqual(r.status_code, 200)

    def test_rag_stats_has_n_chunks(self):
        r = self.client.get('/api/rag/stats')
        data = r.get_json()
        self.assertIn('n_chunks', data)
        self.assertGreater(data['n_chunks'], 0)

    def test_rag_stats_has_n_docs(self):
        r = self.client.get('/api/rag/stats')
        data = r.get_json()
        self.assertIn('n_docs', data)

    # ── /api/rag/rebuild ──────────────────────────────────────────────────────

    def test_rag_rebuild_returns_200(self):
        r = self.client.post('/api/rag/rebuild')
        self.assertEqual(r.status_code, 200)

    def test_rag_rebuild_ok_true(self):
        r = self.client.post('/api/rag/rebuild')
        data = r.get_json()
        self.assertTrue(data.get('ok'))

    def test_rag_rebuild_has_chunks_indexed(self):
        r = self.client.post('/api/rag/rebuild')
        data = r.get_json()
        self.assertIn('chunks_indexed', data)
        self.assertGreater(data['chunks_indexed'], 0)

    # ── /api/rag/search ───────────────────────────────────────────────────────

    def test_rag_search_returns_200(self):
        r = self.client.post('/api/rag/search',
                             json={'query': 'vm cluster cpu_core_count'})
        self.assertEqual(r.status_code, 200)

    def test_rag_search_has_results_key(self):
        r = self.client.post('/api/rag/search',
                             json={'query': 'vm cluster cpu_core_count'})
        data = r.get_json()
        self.assertIn('results', data)

    def test_rag_search_results_are_list(self):
        r = self.client.post('/api/rag/search',
                             json={'query': 'vm cluster cpu_core_count'})
        data = r.get_json()
        self.assertIsInstance(data['results'], list)

    def test_rag_search_result_has_fields(self):
        r = self.client.post('/api/rag/search',
                             json={'query': 'odb network display_name'})
        data = r.get_json()
        if data['results']:
            hit = data['results'][0]
            for key in ('id', 'source', 'text'):
                self.assertIn(key, hit)

    def test_rag_search_missing_query_returns_400(self):
        r = self.client.post('/api/rag/search', json={})
        self.assertEqual(r.status_code, 400)

    def test_rag_search_empty_query_returns_400(self):
        r = self.client.post('/api/rag/search', json={'query': '   '})
        self.assertEqual(r.status_code, 400)

    def test_rag_search_respects_k_param(self):
        r = self.client.post('/api/rag/search',
                             json={'query': 'network cluster infra', 'k': 2})
        data = r.get_json()
        self.assertLessEqual(len(data['results']), 2)


# ══════════════════════════════════════════════════════════════════════════════
#  AZURE FIXTURES
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
        'data_storage_percentage':        80,
        'local_backup_enabled':           False,
        'sparse_diskgroup_enabled':       False,
        'time_zone':                      'UTC',
        'db_servers':                     [],
        'scan_listener_port_tcp':         1521,
        'scan_listener_port_tcp_ssl':     None,
        'system_version':                 '',
        'zone_id':                        '',
        'file_system_configuration':      [],
        'dco_diagnostics_events_enabled': True,
        'dco_health_monitoring_enabled':  True,
        'dco_incident_logs_enabled':      True,
        'infra_ref':                      infra_ref,
        'vnet_ref':                       vnet_ref,
        'tags': {},
        **kw,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  19. AZURE MODULE — azure_vnet (VNet + Oracle-delegated subnet)
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
#  20. AZURE MODULE — azure_exadata_infra
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
#  21. AZURE MODULE — azure_vm_cluster
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


# ══════════════════════════════════════════════════════════════════════════════
#  22. AZURE ROOT
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
#  23. generate_all — Azure
# ══════════════════════════════════════════════════════════════════════════════

def azure_adb(module_name='azure_adbs', vnet_ref='azure_vnet', **kw):
    return {
        'module_name':                      module_name,
        'resource_group_name':              'my-rg',
        'location':                         'eastus',
        'name':                             'adb-prod',
        'display_name':                     'ADB Prod',
        'db_workload':                      'OLTP',
        'db_version':                       '19c',
        'license_model':                    'LicenseIncluded',
        'compute_model':                    'ECPU',
        'compute_count':                    2,
        'data_storage_size_in_tbs':         1,
        'auto_scaling_enabled':             True,
        'auto_scaling_for_storage_enabled': False,
        'backup_retention_period_in_days':  60,
        'vnet_ref':                         vnet_ref,
        **kw,
    }


# ==============================================================================
#  AZURE MODULE - azurerm_oracle_autonomous_database (ADB Serverless)
#  Serverless has no Exadata Infrastructure or VM Cluster under it, so it takes
#  a vnet_ref but no infra_ref. admin_password is Required by the provider and
#  must never reach a generated file.
# ==============================================================================

class TestAzureAutonomousDatabase(unittest.TestCase):

    def _gen(self, adbs=None, **kw):
        return generate_all({
            'cloud': 'azure',
            'resource_group_name': 'my-rg',
            'azure_vnets':          [azure_vnet('azure_vnet')],
            'azure_autonomous_dbs': adbs if adbs is not None else [azure_adb()],
            **kw,
        })

    def test_module_files_are_generated(self):
        files = self._gen()
        for f in ('main.tf', 'variables.tf', 'outputs.tf'):
            self.assertIn(f'modules/azure_adbs/{f}', files)

    def test_the_resource_is_the_serverless_one(self):
        main = self._gen()['modules/azure_adbs/main.tf']
        self.assertIn('resource "azurerm_oracle_autonomous_database" "this"', main)
        # Not the Dedicated stack: no infrastructure, no VM cluster.
        self.assertNotIn('cloud_exadata_infrastructure_id', main)

    def test_admin_password_never_reaches_a_generated_file(self):
        files = self._gen([azure_adb(admin_password='hunter2NotInFiles')])
        for path, content in files.items():
            with self.subTest(path=path):
                self.assertNotIn('hunter2NotInFiles', content)
        # It is declared, sensitive, and has no default anywhere.
        self.assertIn('sensitive   = true', files['modules/azure_adbs/variables.tf'])
        self.assertIn('sensitive = true', files['variables.tf'])
        self.assertIn('var.azure_adbs_admin_password', files['main.tf'])
        tfvars = files['terraform.auto.tfvars']
        assigns = [l for l in tfvars.splitlines()
                   if 'admin_password' in l and not l.lstrip().startswith('#')]
        self.assertEqual(assigns, [], 'admin_password is assigned in tfvars')

    def test_private_endpoint_wires_the_delegated_subnet(self):
        main = self._gen()['main.tf']
        self.assertIn('subnet_id                        = module.azure_vnet.subnet_id', main)
        self.assertIn('virtual_network_id               = module.azure_vnet.vnet_id', main)
        self.assertIn('depends_on = [module.azure_vnet]', main)

    def test_public_endpoint_omits_the_network_wiring(self):
        # No vnet_ref and no VNet to fall back on: the module keeps its empty
        # defaults, which main.tf turns into null rather than "".
        files = generate_all({
            'cloud': 'azure', 'resource_group_name': 'my-rg',
            'azure_autonomous_dbs': [azure_adb(vnet_ref='', allowed_ips=['203.0.113.0/24'])],
        })
        self.assertNotIn('module.azure_vnet', files['main.tf'])
        self.assertNotIn('subnet_id  ', files['main.tf'])
        self.assertIn('allowed_ips', files['terraform.auto.tfvars'])
        module_main = files['modules/azure_adbs/main.tf']
        self.assertIn('var.subnet_id != "" ? var.subnet_id : null', module_main)

    def test_values_reach_the_root_tfvars(self):
        tfvars = self._gen([azure_adb(compute_count=8, data_storage_size_in_tbs=4,
                                      db_workload='DW', db_version='23ai',
                                      mtls_connection_required=False)])['terraform.auto.tfvars']
        self.assertIn('azure_adbs_compute_count                    = 8', tfvars)
        self.assertIn('azure_adbs_data_storage_size_in_tbs         = 4', tfvars)
        self.assertIn('azure_adbs_db_workload                      = "DW"', tfvars)
        self.assertIn('azure_adbs_db_version                       = "23ai"', tfvars)
        self.assertIn('azure_adbs_mtls_connection_required         = false', tfvars)

    def test_a_config_without_one_carries_nothing(self):
        files = generate_all({
            'cloud': 'azure', 'resource_group_name': 'my-rg',
            'azure_vnets': [azure_vnet('azure_vnet')],
        })
        self.assertEqual([p for p in files if 'adb' in p], [])
        self.assertNotIn('autonomous', files['main.tf'].lower())

    def test_several_instances_get_their_own_module(self):
        files = self._gen([azure_adb('adb_one'), azure_adb('adb_two')])
        self.assertIn('modules/adb_one/main.tf', files)
        self.assertIn('modules/adb_two/main.tf', files)
        self.assertIn('module "adb_one"', files['main.tf'])
        self.assertIn('module "adb_two"', files['main.tf'])

    def test_validator_rejects_the_obvious_mistakes(self):
        from clouds.azure.validator import validate
        errors = {}
        validate({'tab': 23, 'azure_autonomous_dbs': [
            {'module_name': 'bad', 'compute_count': 0, 'data_storage_size_in_tbs': 0,
             'backup_retention_period_in_days': 90, 'db_workload': 'NOPE'}]}, errors)
        self.assertEqual(sorted(errors['bad']), [
            'backup_retention_period_in_days', 'compute_count',
            'data_storage_size_in_tbs', 'db_workload', 'display_name',
            'location', 'name', 'resource_group_name'])

    def test_a_valid_payload_reports_nothing(self):
        from clouds.azure.validator import validate
        errors = {}
        validate({'tab': 23, 'azure_autonomous_dbs': [azure_adb()]}, errors)
        self.assertEqual(errors, {})


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
#  24. AZURE DEFAULT NORMALISERS
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
#  25. API ROUTES — Azure
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

    # /api/validate tab 20 — VNet
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

    # /api/validate tab 21 — Infra
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

    # /api/validate tab 22 — VM Cluster
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
        # Tab 0 with cloud=azure hits _validate_azure → no matching elif → no errors
        r = self.client.post('/api/validate', json={
            'cloud': 'azure', 'tab': 0,
            'azure_vnets': [{'module_name': 'av'}],
        })
        self.assertTrue(r.get_json()['valid'])

    # /api/tf-validate — Azure
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
#  26. MOCK tf_validator — Azure
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


# ══════════════════════════════════════════════════════════════════════════════
#  27. generate_all — GCP
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateAllGcp(unittest.TestCase):

    def _base(self, net_count=1, infra_count=1, cluster_count=1):
        nets    = [gcp_net(f'gn{i}')    for i in range(net_count)]
        infras  = [gcp_infra(f'gi{i}')  for i in range(infra_count)]
        clusters = [gcp_cluster(f'gc{i}', f'gn0', f'gi0') for i in range(cluster_count)]
        return {'cloud': 'gcp', 'gcp_networks': nets, 'gcp_infras': infras, 'gcp_clusters': clusters}

    def test_returns_root_main(self):
        self.assertIn('main.tf', generate_all(self._base()))

    def test_returns_root_tfvars(self):
        self.assertIn('terraform.auto.tfvars', generate_all(self._base()))

    def test_returns_root_variables(self):
        self.assertIn('variables.tf', generate_all(self._base()))

    def test_net_module_files_generated(self):
        files = generate_all(self._base())
        for f in ['main.tf', 'variables.tf', 'outputs.tf']:
            self.assertIn(f'modules/{_GCP_MOD_NET}/{f}', files)

    def test_client_subnet_in_network_module(self):
        files = generate_all(self._base())
        self.assertIn('CLIENT_SUBNET', files[f'modules/{_GCP_MOD_NET}/main.tf'])
        self.assertIn('BACKUP_SUBNET', files[f'modules/{_GCP_MOD_NET}/main.tf'])
        self.assertIn('client_subnet_name', files[f'modules/{_GCP_MOD_NET}/outputs.tf'])

    def test_infra_module_files_generated(self):
        files = generate_all(self._base())
        for f in ['main.tf', 'variables.tf', 'outputs.tf']:
            self.assertIn(f'modules/{_GCP_MOD_INFRA}/{f}', files)

    def test_cluster_module_files_generated(self):
        files = generate_all(self._base())
        for f in ['main.tf', 'variables.tf', 'outputs.tf']:
            self.assertIn(f'modules/{_GCP_MOD_CLUSTER}/{f}', files)

    def test_file_count_one_of_each(self):
        # 3 shared modules (9 files) + 3 root files + README.md = 13, regardless of instance count
        self.assertEqual(len(generate_all(self._base())), 13)

    def test_file_count_two_networks(self):
        # with for_each: additional networks are tfvars entries, not extra module files → still 13
        self.assertEqual(len(generate_all(self._base(net_count=2))), 13)

    def test_file_count_two_clusters(self):
        # with for_each: additional clusters are tfvars entries, not extra module files → still 13
        self.assertEqual(len(generate_all(self._base(cluster_count=2))), 13)

    def test_root_main_has_google_provider(self):
        files = generate_all(self._base())
        self.assertIn('hashicorp/google', files['main.tf'])

    def test_root_main_has_no_aws_provider(self):
        files = generate_all(self._base())
        self.assertNotIn('hashicorp/aws', files['main.tf'])
        self.assertNotIn('hashicorp/azurerm', files['main.tf'])

    def test_net_module_has_odb_network_resource(self):
        files = generate_all(self._base())
        self.assertIn('google_oracle_database_odb_network', files[f'modules/{_GCP_MOD_NET}/main.tf'])

    def test_infra_module_has_exadata_resource(self):
        files = generate_all(self._base())
        self.assertIn('google_oracle_database_cloud_exadata_infrastructure',
                      files[f'modules/{_GCP_MOD_INFRA}/main.tf'])

    def test_cluster_module_has_vm_cluster_resource(self):
        files = generate_all(self._base())
        self.assertIn('google_oracle_database_cloud_vm_cluster',
                      files[f'modules/{_GCP_MOD_CLUSTER}/main.tf'])

    def test_cluster_cross_wired_to_correct_infra(self):
        n1 = gcp_net('net_a')
        n2 = gcp_net('net_b')
        files = generate_all({
            'cloud': 'gcp',
            'gcp_networks':  [n1, n2],
            'gcp_infras':    [gcp_infra('inf_prod'), gcp_infra('inf_dev')],
            'gcp_clusters':  [
                gcp_cluster('cl_prod', 'net_a', 'inf_prod'),
                gcp_cluster('cl_dev',  'net_b', 'inf_dev'),
            ],
        })
        # Cross-wiring expressed as network_key / infra_key in tfvars map entries
        tfvars = files['terraform.auto.tfvars']
        self.assertIn('net_a', tfvars)
        self.assertIn('net_b', tfvars)
        self.assertIn('inf_prod', tfvars)
        self.assertIn('inf_dev', tfvars)
        self.assertIn('for_each = var.gcp_vm_clusters', files['main.tf'])

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
#  28. GCP DEFAULT NORMALISERS
# ══════════════════════════════════════════════════════════════════════════════

class TestGcpDefaultNormalisers(unittest.TestCase):

    def test_net_defaults_odb_network_id_fallback(self):
        d = _gcp_net_defaults({})
        self.assertEqual(d['odb_network_id'], 'my-odb-network')

    def test_net_defaults_client_subnet_id_fallback(self):
        d = _gcp_net_defaults({})
        self.assertEqual(d['client_subnet_id'], 'client-subnet')

    def test_net_defaults_backup_subnet_id_fallback(self):
        d = _gcp_net_defaults({})
        self.assertEqual(d['backup_subnet_id'], 'backup-subnet')

    def test_net_defaults_preserves_location(self):
        d = _gcp_net_defaults({'location': 'europe-west4'})
        self.assertEqual(d['location'], 'europe-west4')

    def test_net_defaults_client_cidr_fallback(self):
        self.assertEqual(_gcp_net_defaults({})['client_cidr'], '10.0.1.0/24')

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
        first_net = _gcp_net_defaults({'module_name': 'net1'})
        d = _gcp_cluster_defaults({}, first_net=first_net)
        self.assertEqual(d['network_ref'], 'net1')

    def test_cluster_defaults_network_ref(self):
        first_net = _gcp_net_defaults({'module_name': 'net1'})
        d = _gcp_cluster_defaults({}, first_net=first_net)
        self.assertEqual(d['network_ref'], 'net1')

    def test_cluster_defaults_cpu_core_count_int(self):
        d = _gcp_cluster_defaults({'cpu_core_count': '32'})
        self.assertEqual(d['cpu_core_count'], 32)

    def test_cluster_defaults_memory_size_gb_int(self):
        d = _gcp_cluster_defaults({'memory_size_gb': '120'})
        self.assertEqual(d['memory_size_gb'], 120)


# ══════════════════════════════════════════════════════════════════════════════
#  29. API ROUTES — GCP (dedicated)
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

    # /api/generate — shared module variables and outputs
    def test_generate_gcp_net_variables(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': f'modules/{_GCP_MOD_NET}/variables.tf'},
            content_type='application/json')
        self.assertIn('variable', r.get_json()['content'])

    def test_generate_gcp_net_outputs(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': f'modules/{_GCP_MOD_NET}/outputs.tf'},
            content_type='application/json')
        self.assertIn('output', r.get_json()['content'])

    def test_generate_gcp_infra_variables(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': f'modules/{_GCP_MOD_INFRA}/variables.tf'},
            content_type='application/json')
        self.assertIn('variable', r.get_json()['content'])

    def test_generate_gcp_cluster_variables(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': f'modules/{_GCP_MOD_CLUSTER}/variables.tf'},
            content_type='application/json')
        self.assertIn('variable', r.get_json()['content'])

    def test_generate_gcp_root_variables(self):
        r = self.client.post('/api/generate',
            json={**self.base, 'file_key': 'variables.tf'},
            content_type='application/json')
        self.assertIn('variable', r.get_json()['content'])

    # /api/download — GCP-specific assertions
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

    # /api/validate tab 13 — GCP VM Cluster
    def test_validate_gcp_tab13_pass(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'gcp', 'tab': 13,
            'gcp_clusters': [{'module_name': 'gc', 'cloud_vm_cluster_id': 'cl',
                               'location': 'us-east4', 'hostname_prefix': 'vm',
                               'gi_version': '23.0.0.0', 'cpu_core_count': 16,
                               'ssh_public_keys': ['ssh-rsa AAA']}],
        })
        self.assertTrue(r.get_json()['valid'])

    def test_validate_gcp_tab13_missing_hostname(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'gcp', 'tab': 13,
            'gcp_clusters': [{'module_name': 'gc', 'cloud_vm_cluster_id': 'cl',
                               'location': 'us-east4', 'gi_version': '23.0.0.0',
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
                               'gi_version': '23.0.0.0', 'cpu_core_count': 16,
                               'ssh_public_keys': []}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('ssh_public_keys', d['errors'])

    def test_validate_gcp_tab13_missing_cluster_id(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'gcp', 'tab': 13,
            'gcp_clusters': [{'module_name': 'gc',
                               'location': 'us-east4', 'hostname_prefix': 'vm',
                               'gi_version': '23.0.0.0', 'cpu_core_count': 16,
                               'ssh_public_keys': ['ssh-rsa AAA']}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('cloud_vm_cluster_id', d['errors'])

    # /api/validate tab 14 — GCP OCI DB
    def test_validate_gcp_tab14_pass(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'gcp', 'tab': 14,
            'gcp_oci_databases': [{'module_name': 'ocidb', 'vmcluster_ref': 'gc1',
                                    'db_version': '19.0.0.0', 'db_name': 'mydb'}],
        })
        self.assertTrue(r.get_json()['valid'])

    def test_validate_gcp_tab14_missing_vmcluster_ref(self):
        r = self.client.post('/api/validate', json={
            'cloud': 'gcp', 'tab': 14,
            'gcp_oci_databases': [{'module_name': 'ocidb'}],
        })
        d = r.get_json()
        self.assertFalse(d['valid'])
        self.assertIn('vmcluster_ref', d['errors'])

    # /api/tf-validate — GCP
    def test_tf_validate_gcp_returns_200(self):
        r = self.client.post('/api/tf-validate', json=self.base, content_type='application/json')
        self.assertEqual(r.status_code, 200)

    def test_tf_validate_gcp_has_no_failures(self):
        r = self.client.post('/api/tf-validate', json=self.base, content_type='application/json')
        d = r.get_json()
        failures = [x for x in d.get('results', []) if x['status'] == 'fail']
        self.assertEqual(failures, [],
            msg='Failures:\n' + '\n'.join(f['name'] + ': ' + str(f['error']) for f in failures))

    def test_tf_validate_gcp_provider_check_passes(self):
        r = self.client.post('/api/tf-validate', json=self.base, content_type='application/json')
        d = r.get_json()
        row = next((x for x in d['results']
                    if 'google' in x['name'] and x['group'] == 'Provider'), None)
        self.assertIsNotNone(row)
        self.assertEqual(row['status'], 'pass')

    def test_tf_validate_gcp_cloud_field(self):
        r = self.client.post('/api/tf-validate', json=self.base, content_type='application/json')
        self.assertEqual(r.get_json()['cloud'], 'gcp')


# ══════════════════════════════════════════════════════════════════════════════
#  30. MOCK tf_validator — GCP
# ══════════════════════════════════════════════════════════════════════════════

class TestTfValidateGcp(unittest.TestCase):
    """Direct unit tests for validate_terraform() against GCP-generated files."""

    def _gen(self, net_count=1, infra_count=1, cluster_count=1):
        nets    = [gcp_net(f'tn{i}')    for i in range(net_count)]
        infras  = [gcp_infra(f'ti{i}')  for i in range(infra_count)]
        clusters = [gcp_cluster(f'tc{i}', 'tn0', 'ti0') for i in range(cluster_count)]
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

    def test_valid_gcp_passes_variable_resolution(self):
        results = validate_terraform(self._gen(), 'gcp')
        fails = [r for r in results if r.group == 'Variable Resolution' and r.status == 'fail']
        self.assertEqual(fails, [],
            msg='\n'.join(f'{f.name}: {f.error}' for f in fails))

    def test_valid_gcp_passes_module_crossrefs(self):
        results = validate_terraform(self._gen(), 'gcp')
        fails = [r for r in results if r.group == 'Module Cross-References' and r.status == 'fail']
        self.assertEqual(fails, [],
            msg='\n'.join(f'{f.name}: {f.error}' for f in fails))

    def test_missing_root_main_detected(self):
        files = self._gen()
        del files['main.tf']
        self.assertTrue(any('main.tf' in f.name for f in self._fails(files)))

    def test_missing_module_file_detected(self):
        files = self._gen()
        del files[f'modules/{_GCP_MOD_NET}/main.tf']
        self.assertTrue(any(_GCP_MOD_NET in f.name or 'main.tf' in f.name
                            for f in self._fails(files)))

    def test_wrong_provider_detected(self):
        files = self._gen()
        files['main.tf'] = files['main.tf'].replace('hashicorp/google', 'hashicorp/aws')
        self.assertTrue(any('google' in f.name for f in self._fails(files)))

    def test_net_resource_recognised_by_schema(self):
        results = validate_terraform(self._gen(), 'gcp')
        ok = [r for r in results
              if 'google_oracle_database_odb_network' in r.name and r.status == 'pass']
        self.assertTrue(len(ok) > 0,
            msg='google_oracle_database_odb_network not recognised in mock validator schema')

    def test_infra_resource_recognised_by_schema(self):
        results = validate_terraform(self._gen(), 'gcp')
        ok = [r for r in results
              if 'google_oracle_database_cloud_exadata_infrastructure' in r.name and r.status == 'pass']
        self.assertTrue(len(ok) > 0,
            msg='google_oracle_database_cloud_exadata_infrastructure not recognised in schema')

    def test_cluster_resource_recognised_by_schema(self):
        results = validate_terraform(self._gen(), 'gcp')
        ok = [r for r in results
              if 'google_oracle_database_cloud_vm_cluster' in r.name and r.status == 'pass']
        self.assertTrue(len(ok) > 0,
            msg='google_oracle_database_cloud_vm_cluster not recognised in schema')

    def test_multi_resource_has_no_failures(self):
        fails = self._fails(self._gen(net_count=2, infra_count=2, cluster_count=2))
        self.assertEqual(fails, [],
            msg='\n'.join(f'{f.group} / {f.name}: {f.error}' for f in fails))

    def test_summary_structure_complete(self):
        s = summarise(validate_terraform(self._gen(), 'gcp'))
        for key in ('passed', 'failed', 'warned', 'total', 'results'):
            self.assertIn(key, s)

    def test_summary_failed_zero_for_valid_input(self):
        s = summarise(validate_terraform(self._gen(), 'gcp'))
        self.assertEqual(s['failed'], 0)

    def test_summary_passed_greater_than_zero(self):
        s = summarise(validate_terraform(self._gen(), 'gcp'))
        self.assertGreater(s['passed'], 0)
