"""Reuse the client subnet without creating placeholder network resources."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app, generate_all
from clouds.azure.configuration import deployment_defaults
from clouds.azure.selftest import collect_cidrs
from clouds.azure.validator import validate

VNET_ID = '/subscriptions/sub/resourceGroups/network-rg/providers/Microsoft.Network/virtualNetworks/prod'
SUBNET_ID = VNET_ID + '/subnets/client'
EXISTING = {'module_name': 'net', 'vnet_mode': 'existing', 'existing_subnet_id': SUBNET_ID}


class TestExistingVnet(unittest.TestCase):
    def test_existing_mode_only_needs_subnet_id_and_ignores_creation_defaults(self):
        card = {**EXISTING, 'vnet_name': '', 'resource_group_name': '',
                'address_space': 'invalid', 'subnet_address_prefix': 'invalid'}
        data = {'cloud': 'azure', 'azure_vnets': [card]}
        errors = {}
        validate({**data, 'tab': 20}, errors)
        self.assertEqual(errors, {})
        self.assertEqual(collect_cidrs(data), [])
        files = generate_all(data)
        self.assertNotIn('resource "', files['modules/net/main.tf'])
        self.assertIn('subnet_id = var.net_existing_subnet_id', files['main.tf'])
        self.assertNotIn('net_address_space', files['terraform.auto.tfvars'])
        self.assertIn(SUBNET_ID, files['terraform.auto.tfvars'])

    def test_blank_cards_are_omitted_and_cluster_group_and_region_are_preserved(self):
        data = {'cloud': 'azure', 'azure_vnets': [
                    {'module_name': 'blank', 'vnet_name': '', 'resource_group_name': ''}, EXISTING],
                'azure_clusters': [{'module_name': 'cluster', 'name': 'prod', 'vnet_ref': 'net',
                                    'resource_group_name': 'database-rg', 'location': 'uksouth'}]}
        files = generate_all(data)
        self.assertNotIn('module "blank"', files['main.tf'])
        self.assertFalse(any(path.startswith('modules/blank/') for path in files))
        self.assertIn('resource_group_name             = var.cluster_resource_group_name', files['main.tf'])
        self.assertIn('location                        = var.cluster_location', files['main.tf'])
        self.assertIn('cluster_resource_group_name = "database-rg"', files['terraform.auto.tfvars'])
        self.assertIn('cluster_location = "uksouth"', files['terraform.auto.tfvars'])
        self.assertIn('subnet_id                       = module.net.subnet_id', files['main.tf'])

    def test_invalid_subnet_ids_are_rejected(self):
        for value in ('', VNET_ID, '/subnets/client'):
            errors = {}
            validate({'tab': 20, 'azure_vnets': [{**EXISTING, 'existing_subnet_id': value}]}, errors)
            self.assertIn('existing_subnet_id', errors['net'])

    def test_explicit_settings_win_and_ambiguous_subscriptions_are_not_inferred(self):
        result = deployment_defaults({'subscription_id': 'explicit', 'azure_vnets': [EXISTING]})
        self.assertEqual(result['subscription_id'], 'explicit')
        result = deployment_defaults({'azure_vnets': [EXISTING, {**EXISTING,
                                      'existing_subnet_id': SUBNET_ID.replace('/sub/', '/other/')} ]})
        self.assertNotIn('subscription_id', result)

    @patch.dict(os.environ, APP_AUTH_USER='', APP_AUTH_PASSWORD='')
    def test_functional_checks_accept_existing_networking(self):
        result = app.test_client().post('/api/test', json={
            'cloud': 'azure', 'azure_vnets': [EXISTING]}).get_json()
        self.assertEqual(result['failed'], 0, [r for r in result['results'] if r['status'] == 'fail'])

    @unittest.skipUnless(shutil.which('terraform'), 'Terraform not installed')
    def test_terraform_derives_parent_id_without_cloud_resources(self):
        files = generate_all({'cloud': 'azure', 'azure_vnets': [EXISTING]})
        calls = re.findall(r'^module "net" \{.*?^\}', files['main.tf'], re.M | re.S)
        outputs = re.findall(r'^output "net_[^\n]+', files['main.tf'], re.M)
        with tempfile.TemporaryDirectory() as directory:
            selected = {name: content for name, content in files.items()
                        if name.startswith('modules/net/') or name in ('variables.tf', 'terraform.auto.tfvars')}
            selected['main.tf'] = '\n'.join(calls + outputs)
            for name, content in selected.items():
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            for command in (['terraform', 'fmt', '-check', '-recursive'],
                            ['terraform', 'init', '-backend=false', '-input=false', '-no-color'],
                            ['terraform', 'plan', '-input=false', '-lock=false', '-out=test.plan', '-no-color']):
                result = subprocess.run(command, cwd=directory, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(['terraform', 'show', '-json', 'test.plan'], cwd=directory,
                                    capture_output=True, text=True, check=True)
            plan = json.loads(result.stdout)
            self.assertEqual(plan['planned_values']['outputs']['net_vnet_id']['value'], VNET_ID)
            self.assertEqual(plan['planned_values']['outputs']['net_subnet_id']['value'], SUBNET_ID)
            self.assertFalse(plan.get('resource_changes'))

    @unittest.skipUnless(shutil.which('node'), 'Node not installed')
    def test_form_existing_mode_hides_create_fields_and_retains_entered_values(self):
        page = (Path(__file__).parent.parent / 'clouds/azure/pages/azure.html').read_text()
        functions = []
        for name in ('defAzureVnet', 'readAzureVnet', 'azureVnetCardHTML'):
            start = page.index('function ' + name + '(')
            functions.append(page[start:page.index('\n}', start) + 2])
        setup = '''
const assert=require('assert');
let azureVnets=[],_cardOpen={};
const elements={},document={getElementById:key=>elements[key]||null};
const fv=key=>elements[key]?.value||'',esc=s=>String(s),azureRegionSelectHTML=()=>'';
'''
        checks = '''
azureVnets.push(defAzureVnet(0));
assert(azureVnetCardHTML(azureVnets[0],0).includes('Use existing VNet / subnet'));
Object.assign(elements,{av0_mode:{value:'existing'},av0_vn:{value:'saved-vnet'},
  av0_as:{value:'10.0.0.0/16'},av0_sp:{value:'10.0.1.0/24'}});
readAzureVnet(0);
let html=azureVnetCardHTML(azureVnets[0],0);
assert(html.includes('id="av0_existing_id"'));
for(const suffix of ['vn','rg','as','sn','sp']) assert(!html.includes('id="av0_'+suffix+'"'));
for(const key of Object.keys(elements)) delete elements[key];
Object.assign(elements,{av0_mode:{value:'create'},av0_existing_id:{value:'saved-subnet-id'}});
readAzureVnet(0);
assert.equal(azureVnets[0].vnet_name,'saved-vnet');
assert.equal(azureVnets[0].existing_subnet_id,'saved-subnet-id');
assert(azureVnetCardHTML(azureVnets[0],0).includes('id="av0_vn"'));
'''
        result = subprocess.run(['node'], input=setup + '\n'.join(functions) + checks,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
