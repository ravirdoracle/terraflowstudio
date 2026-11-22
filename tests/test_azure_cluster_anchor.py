"""Network Anchor VM clusters: new API path, existing IDs and legacy safety."""
import copy
import tempfile
import shutil
import subprocess
import unittest
from pathlib import Path

from app import app, generate_all
from clouds.azure.validator import validate
from spreadsheet_importer import _coerce
from test_azure import azure_cluster, azure_infra, azure_vnet
from test_azure_network_anchor import NA, BASE
from tf_validator import validate_terraform

ANCHOR_ID = '/subscriptions/s/resourceGroups/rg/providers/Oracle.Database/networkAnchors/na1'
RESOURCE_ANCHOR_ID = '/subscriptions/s/resourceGroups/rg/providers/Oracle.Database/resourceAnchors/ra1'


def payload(**cluster):
    return {**BASE, 'azure_vnets': [azure_vnet()],
            'azure_infras': [azure_infra(shape='Exadata.X9M')],
            'azure_network_anchors': [copy.deepcopy(NA)],
            'azure_clusters': [azure_cluster(use_network_anchor=True,
                                            network_anchor_ref=NA['module_name'], **cluster)]}


class TestClusterAnchor(unittest.TestCase):
    def test_module_reference_wiring_and_client_subnet_stay_separate(self):
        files = generate_all(payload())
        root = files['main.tf']
        self.assertIn('network_anchor_id               = module.azure_netanchor.network_anchor_id', root)
        self.assertIn('depends_on = [module.azure_netanchor]', root)
        self.assertIn('resource_anchor_id              = module.azure_netanchor.resource_anchor_id', root)
        self.assertIn('subnet_id                       = module.azure_vnet.subnet_id', root)
        self.assertNotIn('subnet_id                       = module.azure_netanchor.subnet_id', root)
        main = files['modules/azure_vmcluster/main.tf']
        self.assertIn('Oracle.Database/cloudVmClusters@2026-06-01', main)
        self.assertIn('networkAnchorId', main)
        self.assertIn('prevent_destroy = true', main)
        self.assertIn('>= 2.14.0', main)
        self.assertNotIn('schema_validation_enabled = false', main)
        self.assertIn('azapi_resource.this.output.properties.ocid', files['modules/azure_vmcluster/outputs.tf'])

    def test_existing_anchor_and_manual_infrastructure_network_ids(self):
        data = payload()
        data.update(azure_network_anchors=[], azure_resource_anchors=[], azure_vnets=[], azure_infras=[])
        data['azure_clusters'][0].update(network_anchor_ref='', network_anchor_id=ANCHOR_ID,
            resource_anchor_id=RESOURCE_ANCHOR_ID, infra_ref='', vnet_ref='',
            cloud_exadata_infrastructure_id='/subscriptions/s/resourceGroups/rg/providers/Oracle.Database/cloudExadataInfrastructures/i',
            subnet_id='/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/v/subnets/client',
            vnet_id='/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/v')
        files = generate_all(data)
        self.assertIn('provider "azapi"', files['main.tf'])
        self.assertNotIn('module.azure_exainfra', files['main.tf'])
        self.assertNotIn('module.azure_vnet', files['main.tf'])
        self.assertNotIn('depends_on = [module.', files['main.tf'])
        self.assertIn(ANCHOR_ID, files['terraform.auto.tfvars'])
        self.assertIn(RESOURCE_ANCHOR_ID, files['terraform.auto.tfvars'])
        errors = {}; validate({**data, 'tab': 22}, errors)
        self.assertEqual(errors, {})
        result = app.test_client().post('/api/test', json=data).get_json()
        self.assertEqual(result['failed'], 0, [r for r in result['results'] if r['status'] == 'fail'])
        self.assertEqual([r.name for r in validate_terraform(files, 'azure') if r.status != 'pass'], [])

    def test_missing_and_deleted_anchor_are_rejected(self):
        for changes, field in [({'network_anchor_ref': 'deleted'}, 'network_anchor_ref'),
                               ({'network_anchor_ref': '', 'network_anchor_id': ''}, 'network_anchor_id'),
                               ({'network_anchor_ref': '', 'network_anchor_id': 'ocid1.not-an-azure-id'}, 'network_anchor_id'),
                               ({'resource_anchor_id': 'invalid'}, 'resource_anchor_id')]:
            with self.subTest(changes=changes):
                data = payload(); data['azure_clusters'][0].update(changes)
                errors = {}; validate({**data, 'tab': 22}, errors)
                self.assertIn(field, errors['azure_vmcluster'])

    def test_existing_configs_and_explicit_opt_out_keep_azurerm(self):
        for extra in ({}, {'network_anchor_ref': NA['module_name'], 'use_network_anchor': False}):
            data = payload(); data['azure_clusters'] = [azure_cluster(**extra)]
            data['azure_network_anchors'] = []
            files = generate_all(data)
            self.assertIn('resource "azurerm_oracle_cloud_vm_cluster"', files['modules/azure_vmcluster/main.tf'])
            self.assertIn('azurerm_oracle_cloud_vm_cluster.this.ocid', files['modules/azure_vmcluster/outputs.tf'])
            self.assertNotIn('azure/azapi', files['main.tf'])

    def test_multiple_clusters_can_choose_different_paths(self):
        data = payload(); legacy = azure_cluster(module_name='legacy')
        data['azure_clusters'].append(legacy)
        files = generate_all(data)
        self.assertIn('azapi_resource', files['modules/azure_vmcluster/main.tf'])
        self.assertIn('azurerm_oracle_cloud_vm_cluster', files['modules/legacy/main.tf'])
        results = validate_terraform(files, 'azure')
        self.assertEqual([r.name for r in results if r.status != 'pass'], [])

    def test_functional_checks_accept_the_new_resource(self):
        result = app.test_client().post('/api/test', json=payload()).get_json()
        self.assertEqual(result['failed'], 0, [r for r in result['results'] if r['status'] == 'fail'])
        self.assertTrue(any('Network Anchor API provisioning' in r['name'] for r in result['results']))

    def test_spreadsheet_boolean_opt_out_is_not_truthy_string(self):
        self.assertIs(_coerce('false', 'use_network_anchor'), False)
        self.assertIs(_coerce('true', 'use_network_anchor'), True)

    @unittest.skipUnless(shutil.which('terraform'), 'Terraform not installed')
    def test_fmt_for_module_and_existing_anchor_paths(self):
        existing = payload(); existing['azure_clusters'][0].update(network_anchor_ref='', network_anchor_id=ANCHOR_ID)
        for data in (payload(), existing):
            with self.subTest(), tempfile.TemporaryDirectory() as directory:
                for name, content in generate_all(data).items():
                    p = Path(directory)/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)
                result = subprocess.run(['terraform', 'fmt', '-check', '-recursive', '-diff', directory], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
