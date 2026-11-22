"""Existing Network Anchor cards must reuse IDs without provisioning a subnet."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app, generate_all
from clouds.azure.selftest import collect_cidrs
from clouds.azure.validator import validate
from tests.test_azure_network_anchor import BASE, NA, _gen
from tf_validator import validate_terraform

ANCHOR_ID = '/subscriptions/s/resourceGroups/rg/providers/Oracle.Database/networkAnchors/existing'
EXISTING = {'module_name': 'reuse_anchor', 'anchor_mode': 'existing',
            'existing_network_anchor_id': ANCHOR_ID}


class TestExistingNetworkAnchor(unittest.TestCase):
    def test_existing_card_only_passes_ids_and_does_not_require_create_fields(self):
        data = {'cloud': 'azure', 'azure_network_anchors': [EXISTING]}
        errors = {}
        validate({**data, 'tab': 25}, errors)
        self.assertEqual(errors, {})
        files = generate_all(data)
        self.assertNotIn('azure/azapi', files['main.tf'])
        self.assertNotIn('azurerm_subnet', '\n'.join(files.values()))
        self.assertFalse(re.search(r'\bresource\s+"', files['modules/reuse_anchor/main.tf']))
        self.assertIn('value       = var.network_anchor_id', files['modules/reuse_anchor/outputs.tf'])
        self.assertIn(ANCHOR_ID, files['terraform.auto.tfvars'])
        self.assertNotIn('subnet_address_prefix', files['terraform.auto.tfvars'])
        self.assertNotIn('output "reuse_anchor_oci_vcn_id"', files['main.tf'])
        self.assertIn('output "reuse_anchor_network_anchor_id"', files['main.tf'])
        self.assertEqual([r.name for r in validate_terraform(files, 'azure') if r.status == 'fail'], [])

    def test_create_and_existing_cards_work_together_and_wire_to_clusters(self):
        data = {**BASE, 'azure_network_anchors': [NA, EXISTING],
                'azure_clusters': [{'module_name': 'cluster', 'name': 'cluster', 'use_network_anchor': True,
                                    'network_anchor_ref': 'reuse_anchor'}]}
        files = generate_all(data)
        self.assertIn('Oracle.Database/networkAnchors@', files['modules/azure_netanchor/main.tf'])
        self.assertIn('network_anchor_id               = module.reuse_anchor.network_anchor_id', files['main.tf'])
        self.assertIn('resource_anchor_id              = module.reuse_anchor.resource_anchor_id', files['main.tf'])
        self.assertIn('azapi_resource', files['modules/cluster/main.tf'])
        self.assertIn('output "azure_netanchor_oci_vcn_id"', files['main.tf'])
        self.assertNotIn('output "reuse_anchor_oci_vcn_id"', files['main.tf'])
        self.assertEqual([r.name for r in validate_terraform(files, 'azure') if r.status == 'fail'], [])

    @unittest.skipUnless(shutil.which('terraform'), 'Terraform not installed')
    def test_existing_module_and_generated_root_outputs_validate_without_providers(self):
        # Validate the real generated module calls and outputs with Terraform.
        # These ID-only modules need no cloud providers, credentials or network.
        files = generate_all({'cloud': 'azure', 'azure_network_anchors': [EXISTING]})
        calls = re.findall(r'^module "reuse_anchor" \{.*?^\}', files['main.tf'], re.M | re.S)
        outputs = re.findall(r'^output "reuse_anchor_[^\n]+', files['main.tf'], re.M)
        self.assertEqual(len(calls), 1)
        self.assertTrue(outputs)
        with tempfile.TemporaryDirectory() as directory:
            selected = {path: content for path, content in files.items()
                        if path.startswith('modules/reuse_anchor/') or path == 'variables.tf'}
            selected['main.tf'] = '\n'.join(calls + outputs)
            for name, content in selected.items():
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            for command in (['terraform', 'init', '-backend=false', '-input=false', '-no-color'],
                            ['terraform', 'validate', '-no-color']):
                result = subprocess.run(command, cwd=directory, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_retained_create_settings_are_ignored_in_existing_mode(self):
        stale = {**NA, **EXISTING, 'subnet_address_prefix': 'not-a-cidr', 'name': ''}
        errors = {}
        validate({**BASE, 'tab': 25, 'azure_network_anchors': [stale]}, errors)
        self.assertEqual(errors, {})
        self.assertFalse(any('reuse_anchor' in label for label, _ in collect_cidrs(
            {**BASE, 'azure_network_anchors': [stale]})))
        files = _gen(stale)
        root = files['main.tf'].split('module "reuse_anchor" {')[1].split('}')[0]
        self.assertNotIn('module.azure_resource_anchor', root)
        self.assertNotIn('module.azure_vnet', root)

    def test_missing_and_invalid_ids_are_rejected(self):
        for anchor_id in ('', 'ocid1.anchor', '/providers/Oracle.Database/networkAnchors/short'):
            with self.subTest(anchor_id=anchor_id):
                errors = {}
                validate({'tab': 25, 'azure_network_anchors': [{**EXISTING,
                         'existing_network_anchor_id': anchor_id}]}, errors)
                self.assertIn('existing_network_anchor_id', errors['reuse_anchor'])

    @patch.dict(os.environ, APP_AUTH_USER='', APP_AUTH_PASSWORD='')
    def test_app_selftest_accepts_existing_cards(self):
        result = app.test_client().post('/api/test', json={
            'cloud': 'azure', 'azure_network_anchors': [EXISTING]}).get_json()
        self.assertEqual(result['failed'], 0, [r for r in result['results'] if r['status'] == 'fail'])

    @unittest.skipUnless(shutil.which('terraform'), 'Terraform not installed')
    def test_generated_existing_configuration_is_formatted(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, content in generate_all({'cloud': 'azure', 'azure_network_anchors': [EXISTING]}).items():
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            result = subprocess.run(['terraform', 'fmt', '-check', '-recursive', '-diff', directory],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
