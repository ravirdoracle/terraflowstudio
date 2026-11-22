"""Existing infrastructure is referenced by ID, without a managed resource."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app, generate_all
from clouds.azure.validator import validate
from tests.test_azure_network_anchor import BASE, NA
from tf_validator import validate_terraform

INFRA_ID = '/subscriptions/s/resourceGroups/rg/providers/Oracle.Database/cloudExadataInfrastructures/existing'
EXISTING = {'module_name': 'reuse_infra', 'infra_mode': 'existing',
            'existing_infrastructure_id': INFRA_ID}


class TestExistingInfrastructure(unittest.TestCase):
    def test_only_id_is_required_and_no_infrastructure_resource_is_created(self):
        data = {'cloud': 'azure', 'azure_infras': [EXISTING]}
        errors = {}
        validate({**data, 'tab': 21}, errors)
        self.assertEqual(errors, {})
        files = generate_all(data)
        module = '\n'.join(content for path, content in files.items()
                           if path.startswith('modules/reuse_infra/'))
        self.assertNotRegex(module, r'\bresource\s+"')
        self.assertIn('value       = var.infrastructure_id', module)
        self.assertIn('infra_name', module)
        self.assertIn(INFRA_ID, files['terraform.auto.tfvars'])
        self.assertNotIn('reuse_infra_shape', files['variables.tf'])
        self.assertNotIn('reuse_infra_compute_count', files['terraform.auto.tfvars'])
        self.assertNotIn('azurerm_oracle_exadata_infrastructure', files['IMPORT.md'])
        self.assertEqual([r.name for r in validate_terraform(files, 'azure') if r.status == 'fail'], [])

    def test_existing_infrastructure_wires_to_both_cluster_paths(self):
        for anchor_enabled in (False, True):
            with self.subTest(anchor_enabled=anchor_enabled):
                data = {**BASE, 'azure_infras': [EXISTING],
                        'azure_network_anchors': [NA] if anchor_enabled else [],
                        'azure_clusters': [{'module_name': 'cluster', 'name': 'cluster', 'infra_ref': 'reuse_infra',
                                            'vnet_ref': 'azure_vnet', 'use_network_anchor': anchor_enabled,
                                            'network_anchor_ref': NA['module_name'] if anchor_enabled else ''}]}
                files = generate_all(data)
                self.assertIn('cloud_exadata_infrastructure_id = module.reuse_infra.infra_id', files['main.tf'])
                self.assertEqual([r.name for r in validate_terraform(files, 'azure') if r.status == 'fail'], [])

    def test_create_and_reuse_can_coexist_and_old_payloads_still_create(self):
        data = {'cloud': 'azure', 'azure_infras': [EXISTING,
                {'module_name': 'new_infra', 'name': 'new', 'shape': 'Exadata.X9M'}]}
        files = generate_all(data)
        self.assertIn('resource "azurerm_oracle_exadata_infrastructure"', files['modules/new_infra/main.tf'])
        self.assertNotRegex(files['modules/reuse_infra/main.tf'], r'\bresource\s+"')
        self.assertIn('new_infra_shape', files['variables.tf'])

    def test_missing_or_wrong_resource_ids_and_unknown_mode_are_rejected(self):
        for value in ('', 'ocid1.exadata', INFRA_ID.replace('cloudExadataInfrastructures', 'networkAnchors')):
            with self.subTest(value=value):
                errors = {}
                validate({'tab': 21, 'azure_infras': [{**EXISTING, 'existing_infrastructure_id': value}]}, errors)
                self.assertIn('existing_infrastructure_id', errors['reuse_infra'])
        errors = {}
        validate({'tab': 21, 'azure_infras': [{**EXISTING, 'infra_mode': 'invalid'}]}, errors)
        self.assertIn('infra_mode', errors['reuse_infra'])

    @patch.dict(os.environ, APP_AUTH_USER='', APP_AUTH_PASSWORD='')
    def test_selftest_and_preview_support_existing_infrastructure(self):
        client = app.test_client()
        data = {'cloud': 'azure', 'azure_infras': [EXISTING]}
        result = client.post('/api/test', json=data).get_json()
        self.assertEqual(result['failed'], 0, [r for r in result['results'] if r['status'] == 'fail'])
        content = client.post('/api/generate', json={**data, 'file_key': 'main.tf'}).get_json()['content']
        self.assertIn('infrastructure_id = var.reuse_infra_existing_infrastructure_id', content)

    @unittest.skipUnless(shutil.which('node'), 'Node not installed')
    def test_ui_hides_create_fields_and_preserves_values_when_switching_modes(self):
        page = (Path(__file__).parent.parent / 'clouds/azure/pages/azure.html').read_text()
        functions = []
        for name in ('defAzureInfra', 'readAzureInfra', 'azureInfraCardHTML'):
            start = page.index('function ' + name + '(')
            end = page.index('\n}', start) + 2
            functions.append(page[start:end])
        setup = '''
const assert = require('assert');
const azureInfras = [], AZURE_DEFAULT_SHAPE='Exadata.X11M', AZURE_SHAPES=[], _cardOpen={};
const elements={};
const document={getElementById:key=>elements[key]||null};
const fv=key=>elements[key]?.value||'';
const esc=s=>String(s).replace(/"/g,'&quot;');
const soleServerType=()=>'', shapeRequiresServerTypes=()=>false, normaliseServerTypes=()=>{};
const shapeSelectHTML=()=>'', serverTypeSelectHTML=()=>'', azureRegionSelectHTML=()=>'', azureZoneOptions=()=>'';
'''
        checks = '''
azureInfras.push(defAzureInfra(0));
let html=azureInfraCardHTML(azureInfras[0],0);
assert(html.includes('Use existing Exadata Infrastructure'));
assert(html.includes('id="ai0_cc"'));
Object.assign(elements, {ai0_mode:{value:'existing'}, ai0_name:{value:'saved-name'},
  ai0_cc:{value:'4'},ai0_sc:{value:'6'},ai0_mn:{value:'azure_exainfra'}});
readAzureInfra(0);
html=azureInfraCardHTML(azureInfras[0],0);
assert(html.includes('id="ai0_existing_id"'));
for(const id of ['name','loc','shape','cc','sc','zone','mwp','contactin'])
  assert(!html.includes('id="ai0_'+id+'"'), id+' should be hidden');
for(const key of Object.keys(elements)) delete elements[key];
Object.assign(elements,{ai0_mode:{value:'create'},ai0_existing_id:{value:'existing-resource-id'}});
readAzureInfra(0);
assert.equal(azureInfras[0].name,'saved-name');
assert.equal(azureInfras[0].compute_count,4);
assert.equal(azureInfras[0].storage_count,6);
assert.equal(azureInfras[0].existing_infrastructure_id,'existing-resource-id');
assert(azureInfraCardHTML(azureInfras[0],0).includes('id="ai0_cc"'));
'''
        result = subprocess.run(['node'], input=setup + '\n'.join(functions) + checks,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('terraform'), 'Terraform not installed')
    def test_existing_and_mixed_generated_files_are_formatted(self):
        for infras in ([EXISTING], [EXISTING, {'module_name': 'new_infra'}]):
            with tempfile.TemporaryDirectory() as directory:
                for name, content in generate_all({'cloud': 'azure', 'azure_infras': infras}).items():
                    path = Path(directory) / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content)
                result = subprocess.run(['terraform', 'fmt', '-check', '-recursive', '-diff', directory],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
