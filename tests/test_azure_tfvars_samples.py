"""Sample tfvars stay comments, and reloading does not restore blank cards."""
import shutil
import subprocess
import unittest
from pathlib import Path

from app import generate_all
from clouds.azure.tfvars import comment_tfvars_samples


class TestTfvarsSamples(unittest.TestCase):
    def test_unconfigured_resource_examples_and_blank_root_fields_are_commented(self):
        data = {'cloud': 'azure',
                'azure_vnets': [{'module_name': 'azure_vnet', 'vnet_name': '',
                                 'address_space': '10.0.0.0/16', 'subnet_address_prefix': '10.0.1.0/24'}],
                'azure_infras': [{'module_name': 'azure_exainfra'}],
                'azure_clusters': [{'module_name': 'azure_vmcluster'}]}
        text = generate_all(data)['terraform.auto.tfvars']
        self.assertNotIn('azure_vnet_address_space', text)
        self.assertNotIn('azure_exainfra_shape', text)
        self.assertNotIn('azure_vmcluster_cpu_core_count', text)
        self.assertIn('# subscription_id', text)
        self.assertFalse([line for line in text.splitlines() if line.strip() and not line.startswith('#')])

    def test_real_values_stay_active_even_when_they_match_form_defaults(self):
        data = {'cloud': 'azure', 'location': 'eastus',
                'azure_vnets': [{'module_name': 'net', 'vnet_name': 'prod', 'subnet_name': 'client',
                                 'address_space': '10.0.0.0/16'}],
                'azure_infras': [{'module_name': 'infra', 'infra_mode': 'existing',
                                  'existing_infrastructure_id': '/subscriptions/s/resourceGroups/rg/providers/Oracle.Database/cloudExadataInfrastructures/prod'}]}
        text = generate_all(data)['terraform.auto.tfvars']
        active = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))
        self.assertIn('net_vnet_name', active)
        self.assertIn('net_address_space', active)
        self.assertIn('infra_existing_infrastructure_id', active)
        self.assertIn('location = "eastus"', active)

    def test_multiline_sample_objects_are_completely_commented_and_prefixes_are_distinct(self):
        data = {'azure_network_anchors': [{'module_name': 'db'}],
                'azure_clusters': [{'module_name': 'db_prod', 'name': 'prod'}]}
        content = 'db = {\n  name = ""\n  rules = [\n    { value = "sample" },\n  ]\n}\ndb_prod_count = 0\ndb_prod_enabled = false'
        text = comment_tfvars_samples(content, data)
        active = [line for line in text.splitlines() if not line.startswith('#')]
        self.assertEqual(active, ['db_prod_count   = 0', 'db_prod_enabled = false'])

    @unittest.skipUnless(shutil.which('node'), 'Node not installed')
    def test_loading_empty_lists_does_not_add_sample_cards(self):
        page = (Path(__file__).parent.parent / 'clouds/azure/pages/azure.html').read_text()
        functions = []
        for name in ('applyConfig', 'buildPayload'):
            start = page.index('function ' + name + '(')
            functions.append(page[start:page.index('\n}', start) + 2])
        script = '''
const assert=require('assert');
let azureVnets=[{vnet_name:'sample'}],azureInfras=[{}],azureClusters=[{}],azureAdbs=[{}];
let azureResourceAnchors=[],azureNetworkAnchors=[];
const cloud='azure',iacTool='terraform',getCustName=()=>'';
const renderAll=()=>{},refresh=()=>{},updateTestBtn=()=>{};
const defAzureVnet=()=>({}),defAzureInfra=()=>({}),defAzureCluster=()=>({}),defAzureAdb=()=>({});
const defAzureResourceAnchor=()=>({}),defAzureNetworkAnchor=()=>({});
'''
        checks = '''
applyConfig({azure_vnets:[],azure_infras:[],azure_clusters:[],azure_autonomous_dbs:[]});
assert.equal(azureVnets.length,0);assert.equal(azureInfras.length,0);
assert.equal(azureClusters.length,0);assert.equal(azureAdbs.length,0);
applyConfig({azure_infras:[{infra_mode:'existing',existing_infrastructure_id:'real-id'}],azure_vnets:[]});
assert.equal(azureInfras[0].existing_infrastructure_id,'real-id');
const saved=JSON.parse(JSON.stringify(buildPayload()));
azureVnets.push({vnet_name:'sample'});
applyConfig(saved);
assert.equal(azureVnets.length,0);
assert.equal(azureInfras[0].existing_infrastructure_id,'real-id');
'''
        result = subprocess.run(['node'], input=script + '\n'.join(functions) + checks,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
