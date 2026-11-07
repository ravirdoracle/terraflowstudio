"""Exascale on AI Database@Google Cloud: storage vaults and Exascale VM clusters.

google_oracle_database_exascale_db_storage_vault + google_oracle_database_exadb_vm_cluster
(hashicorp/google >= 7.20.0). No Exadata Infrastructure, no zone input on the cluster,
and a client *and* backup subnet. Limits are Oracle's "Create an Exascale VM Cluster".
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, generate_all
from clouds.gcp import validator
from clouds.gcp.generator import _GCP_EXASCALE_FLOOR, _gcp_xs_cluster_defaults
from tf_validator import validate_terraform

ROOT = Path(__file__).parent.parent
PAGE = ROOT / 'clouds' / 'gcp' / 'pages' / 'gcp.html'

NET = {'module_name': 'net1', 'project': 'my-proj', 'location': 'us-east4', 'odb_network_id': 'net-1',
       'client_cidr': '10.0.1.0/24', 'backup_cidr': '10.0.2.0/24'}
VAULT = {'module_name': 'vault1', 'exascale_db_storage_vault_id': 'vault-1', 'gcp_oracle_zone': 'us-east4-a-r1',
         'total_size_gbs': 500, 'additional_flash_cache_percent': 50}
CLUSTER = {'module_name': 'xs1', 'exadb_vm_cluster_id': 'xs-1', 'network_ref': 'net1', 'vault_ref': 'vault1',
           'grid_image_id': 'ocid1.dbpatch.oc1.iad.abc', 'node_count': 2, 'enabled_ecpu_count_per_node': 16,
           'vm_file_system_size_gbs_per_node': 220, 'hostname_prefix': 'vm', 'ssh_public_keys': ['ssh-rsa AAAA x@y']}
EXISTING = 'projects/my-proj/locations/us-east4/exascaleDbStorageVaults/v0'


def _gcp(**extra):
    return {'cloud': 'gcp', 'gcp_networks': [NET], 'gcp_infras': [], 'gcp_clusters': [],
            'gcp_exascale_vaults': [VAULT], 'gcp_exascale_clusters': [CLUSTER], **extra}


def _errors(tab, **extra):
    errors = {}
    validator.validate({**_gcp(**extra), 'tab': tab}, errors)
    return errors


class TestWithoutExascale(unittest.TestCase):

    def test_nothing_exascale_is_emitted(self):
        for path, content in generate_all({'cloud': 'gcp', 'gcp_networks': [NET]}).items():
            self.assertNotIn('exascale', content.lower(), path)

    def test_the_provider_floor_stays(self):
        self.assertIn('version = ">= 7.5.0"', generate_all({'cloud': 'gcp'})['main.tf'])


class TestExascaleOnly(unittest.TestCase):

    def setUp(self):
        self.files = generate_all(_gcp())

    def test_no_exadata_infrastructure_and_no_phantom(self):
        mods = {p.split('/')[1] for p in self.files if p.startswith('modules/')}
        self.assertEqual(mods, {'gcp-odb-network', 'gcp-exascale-vault', 'gcp-exascale-vm-cluster'})
        self.assertNotIn('gcp_exadata_infras', self.files['main.tf'])

    def test_the_network_keeps_its_backup_subnet(self):
        main = self.files['main.tf']
        self.assertIn('backup_odb_subnet   = module.gcp_odb_network[each.value.network_key].backup_subnet_name', main)
        self.assertNotIn('Serverless only', main)
        self.assertIn('Exascale only', main)

    def test_the_floor_moves_with_exascale(self):
        self.assertEqual(_GCP_EXASCALE_FLOOR, '7.20.0')
        self.assertIn('version = ">= 7.20.0"', self.files['main.tf'])
        self.assertIn('version = ">= 7.20.0"', self.files['modules/gcp-exascale-vm-cluster/main.tf'])

    def test_vault_wiring(self):
        self.assertIn('module.gcp_exascale_vault[each.value.vault_key].vault_id : each.value.existing_vault',
                      self.files['main.tf'])

    def test_cluster_module(self):
        mod = self.files['modules/gcp-exascale-vm-cluster/main.tf']
        self.assertIn('resource "google_oracle_database_exadb_vm_cluster" "this"', mod)
        self.assertNotIn('gcp_oracle_zone', mod.split('resource')[1].split('properties')[0])
        self.assertIn('properties[0].ssh_public_keys', mod)
        # Scaling is not ignored: a resize in tfvars must plan.
        self.assertNotIn('properties[0].enabled_ecpu_count_per_node', mod)

    def test_grid_image_must_be_a_dbpatch_ocid(self):
        self.assertIn('startswith(var.grid_image_id, "ocid1.dbpatch.")',
                      self.files['modules/gcp-exascale-vm-cluster/variables.tf'])

    def test_tfvars(self):
        tv = self.files['terraform.auto.tfvars']
        self.assertIn('gcp_exascale_vaults = {\n  "vault1" = {', tv)
        self.assertIn('    additional_flash_cache_percent = 50', tv)
        self.assertIn('    vault_key                        = "vault1"', tv)
        self.assertNotIn('existing_vault', tv.split('gcp_exascale_vm_clusters')[1])

    def test_readme(self):
        readme = self.files['README.md']
        self.assertIn('### Exascale VM Clusters', readme)
        self.assertIn('gcp-exascale-vm-cluster/', readme)
        self.assertNotIn('Autonomous Serverless only', readme)


class TestDefaults(unittest.TestCase):

    def test_existing_vault(self):
        c = _gcp_xs_cluster_defaults({**CLUSTER, 'vault_ref': '', 'existing_vault': EXISTING}, ['net1'], ['vault1'])
        self.assertEqual((c['vault_ref'], c['existing_vault']), ('', EXISTING))

    def test_dangling_refs_fall_back(self):
        c = _gcp_xs_cluster_defaults({**CLUSTER, 'vault_ref': 'gone', 'network_ref': 'gone'}, ['net1'], ['vault1'])
        self.assertEqual((c['vault_ref'], c['network_ref']), ('vault1', 'net1'))

    def test_block_storage_file_system_minimum(self):
        c = _gcp_xs_cluster_defaults({'shape_attribute': 'BLOCK_STORAGE'}, ['n'], [])
        self.assertEqual(c['vm_file_system_size_gbs_per_node'], 260)

    def test_grid_placeholder(self):
        self.assertEqual(_gcp_xs_cluster_defaults({}, ['n'], [])['grid_image_id'], 'ocid1.dbpatch.oc1..CHANGEME')

    def test_vault_alone_generates(self):
        files = generate_all(_gcp(gcp_exascale_clusters=[]))
        self.assertIn('modules/gcp-exascale-vault/main.tf', files)
        self.assertIn('gcp_exascale_vm_clusters = {}', files['terraform.auto.tfvars'])


class TestMixed(unittest.TestCase):

    def test_exadata_and_exascale_side_by_side(self):
        files = generate_all(_gcp(gcp_infras=[{'module_name': 'inf'}],
                                  gcp_clusters=[{'module_name': 'cl', 'ssh_public_keys': ['k']}]))
        mods = {p.split('/')[1] for p in files if p.startswith('modules/')}
        self.assertTrue({'gcp-exadata-infra', 'gcp-vm-cluster', 'gcp-exascale-vm-cluster'} <= mods)

    def test_an_infra_kept_for_later_gets_no_phantom_cluster(self):
        tv = generate_all(_gcp(gcp_infras=[{'module_name': 'inf'}]))['terraform.auto.tfvars']
        self.assertNotIn('cloud_vm_cluster_id', tv)


class TestValidation(unittest.TestCase):

    def test_good_payload(self):
        self.assertEqual(_errors(17), {})
        self.assertEqual(_errors(18), {})

    def test_vault_limits(self):
        e = _errors(17, gcp_exascale_vaults=[{**VAULT, 'total_size_gbs': 200, 'additional_flash_cache_percent': 20,
                                               'exascale_db_storage_vault_id': 'Bad_ID'}])['vault1']
        for f in ('total_size_gbs', 'additional_flash_cache_percent', 'exascale_db_storage_vault_id'):
            self.assertIn(f, e)

    def test_cluster_limits(self):
        bad = {**CLUSTER, 'node_count': 11, 'enabled_ecpu_count_per_node': 10, 'additional_ecpu_count_per_node': 6,
               'vm_file_system_size_gbs_per_node': 230, 'shape_attribute': 'BLOCK_STORAGE', 'cluster_name': 'waytoolongname'}
        e = _errors(18, gcp_exascale_clusters=[bad])['xs1']
        for f in ('node_count', 'enabled_ecpu_count_per_node', 'additional_ecpu_count_per_node',
                  'vm_file_system_size_gbs_per_node', 'cluster_name'):
            self.assertIn(f, e)
        self.assertIn('260 to 1100', e['vm_file_system_size_gbs_per_node'])

    def test_needs_a_backup_subnet(self):
        e = _errors(18, gcp_networks=[{**NET, 'purpose': 'adbs'}])['xs1']
        self.assertIn('ADB-S only', e['network_ref'])

    def test_grid_image(self):
        self.assertIn('grid_image_id', _errors(18, gcp_exascale_clusters=[{**CLUSTER, 'grid_image_id': ''}])['xs1'])
        self.assertIn('ocid1.dbpatch.', _errors(18, gcp_exascale_clusters=[{**CLUSTER, 'grid_image_id': 'ocid1.x'}])['xs1']['grid_image_id'])

    def test_vault_reference(self):
        e = _errors(18, gcp_exascale_vaults=[], gcp_exascale_clusters=[{**CLUSTER, 'vault_ref': ''}])['xs1']
        self.assertIn('vault_ref', e)
        e = _errors(18, gcp_exascale_clusters=[{**CLUSTER, 'vault_ref': '', 'existing_vault': 'v0'}])['xs1']
        self.assertIn('existing_vault', e)
        self.assertEqual(_errors(18, gcp_exascale_clusters=[{**CLUSTER, 'vault_ref': '', 'existing_vault': EXISTING}]), {})


class TestSelftestAndMock(unittest.TestCase):

    def test_functional_test_passes_without_exadata(self):
        d = app.test_client().post('/api/test', json=_gcp()).get_json()
        self.assertEqual([r['name'] for r in d['results'] if r['status'] == 'fail'], [])
        self.assertIn('modules/gcp-exascale-vm-cluster/main.tf generated', {r['name'] for r in d['results']})

    def test_mock_validator_knows_both_resources(self):
        bad = [r for r in validate_terraform(generate_all(_gcp()), 'gcp')
               if r.status != 'pass' and 'exascale' in (r.file or '') + r.name]
        self.assertEqual([r.name for r in bad], [])


class TestPage(unittest.TestCase):

    def setUp(self):
        self.html = PAGE.read_text(encoding='utf-8')

    def test_tabs(self):
        for i, v in ((6, 17), (7, 18)):
            self.assertIn(f'onclick="switchTab({i},true)"', self.html)
            self.assertIn(f'id="gcp-page-{i}"', self.html)
            self.assertIn(f'vgen({v},true)', self.html)

    def test_payload_and_restore(self):
        self.assertIn('gcp_exascale_clusters: gcpXsClusters,', self.html)
        self.assertIn("gcpXsClusters = (doc.gcp_exascale_clusters || [])", self.html)

    def test_exadata_cards_can_be_removed_for_an_exascale_only_config(self):
        self.assertIn('${gcpInfras.length>0', self.html)
        self.assertIn('${gcpClusters.length>0', self.html)


@unittest.skipUnless(shutil.which('terraform'), 'terraform not installed')
class TestTerraformFmt(unittest.TestCase):

    CASES = {
        'exascale_only': _gcp(),
        'existing_block': _gcp(gcp_exascale_vaults=[], gcp_exascale_clusters=[
            {**CLUSTER, 'vault_ref': '', 'existing_vault': EXISTING, 'shape_attribute': 'BLOCK_STORAGE',
             'vm_file_system_size_gbs_per_node': 260, 'additional_ecpu_count_per_node': 8, 'cluster_name': 'exacl',
             'time_zone': 'UTC', 'scan_listener_port_tcp': 1521}]),
        'mixed': _gcp(gcp_infras=[{'module_name': 'inf'}], gcp_clusters=[{'module_name': 'cl', 'ssh_public_keys': ['k']}],
                      gcp_autonomous_dbs=[{'module_name': 'adb'}]),
    }

    def test_fmt_clean(self):
        for name, payload in self.CASES.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                for path, content in generate_all(payload).items():
                    full = os.path.join(tmp, path)
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    with open(full, 'w', encoding='utf-8', newline='\n') as fh:
                        fh.write(content)
                r = subprocess.run(['terraform', 'fmt', '-check', '-recursive', '.'],
                                   cwd=tmp, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
