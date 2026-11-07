"""Oracle Network Anchor on Azure (Oracle.Database/networkAnchors via azapi), and the
Resource Anchor card it depends on.

A Network Anchor is the network bridge between Azure and OCI. It is not tied to one
database service and takes a delegated subnet of its own. azurerm has no resource
for it, so the module uses azapi against API version 2025-09-01.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, generate_all
from clouds.azure import validator
from clouds.azure.generator import (AZAPI_FLOOR, NETWORK_ANCHOR_API_VERSION,
                                    _azure_na_defaults, _azure_na_tfvars_entry)
from clouds.azure.selftest import collect_cidrs
from tf_validator import validate_terraform

ROOT = Path(__file__).parent.parent
PAGE = ROOT / 'clouds' / 'azure' / 'pages' / 'azure.html'

VNET = {'module_name': 'azure_vnet', 'resource_group_name': 'rg', 'vnet_name': 'ora-vnet',
        'address_space': '10.0.0.0/16', 'subnet_name': 'ora-sub', 'subnet_address_prefix': '10.0.1.0/24'}
BASE = {'cloud': 'azure', 'resource_group_name': 'rg', 'location': 'eastus',
        'subscription_id': '00000000-0000-0000-0000-000000000000',
        'azure_vnets': [VNET],
        'azure_resource_anchors': [{'module_name': 'azure_resource_anchor', 'name': 'ra1'}]}
NA = {'module_name': 'azure_netanchor', 'name': 'na-east-1', 'resource_anchor_ref': 'azure_resource_anchor',
      'vnet_ref': 'azure_vnet', 'subnet_address_prefix': '10.0.2.0/24'}
EXISTING_RA = '/subscriptions/x/resourceGroups/rg/providers/Oracle.Database/resourceAnchors/ra0'


def _gen(*nas, **extra):
    return generate_all({**BASE, 'azure_network_anchors': list(nas), **extra})


def _errors(*nas, **extra):
    errors = {}
    validator.validate({**BASE, 'tab': 25, 'azure_network_anchors': list(nas), **extra}, errors)
    return errors


class TestWithoutANetworkAnchor(unittest.TestCase):

    def test_no_azapi_anywhere(self):
        files = generate_all(BASE)
        self.assertFalse([p for p, c in files.items() if 'azapi' in c])

    def test_root_is_what_it_was(self):
        # The provider block and required_providers gain azapi only with an anchor.
        main = generate_all(BASE)['main.tf']
        self.assertNotIn('provider "azapi"', main)
        self.assertNotIn('Network Anchor', main)


class TestModule(unittest.TestCase):

    def setUp(self):
        self.files = _gen(NA)
        self.main = self.files['modules/azure_netanchor/main.tf']

    def test_module_files(self):
        for f in ('main.tf', 'variables.tf', 'outputs.tf'):
            self.assertIn(f'modules/azure_netanchor/{f}', self.files)

    def test_azapi_resource_at_the_ga_api_version(self):
        self.assertEqual(NETWORK_ANCHOR_API_VERSION, '2025-09-01')
        self.assertIn('type      = "Oracle.Database/networkAnchors@2025-09-01"', self.main)

    def test_its_own_delegated_subnet(self):
        self.assertIn('resource "azurerm_subnet" "network_anchor"', self.main)
        self.assertIn('name = "Oracle.Database/networkAttachments"', self.main)
        self.assertIn('subnetId                             = azurerm_subnet.network_anchor.id', self.main)

    def test_unset_optionals_stay_out_of_the_request(self):
        self.assertIn('ignore_null_property = true', self.main)

    def test_comma_separated_api_fields_are_joined(self):
        self.assertIn('join(",", var.dns_listening_allowed_cidrs)', self.main)
        self.assertIn('domainNames         = join(",", r.domain_names)', self.main)

    def test_floor_is_the_first_azapi_with_the_type(self):
        # Bisected: 2.5.0-2.7.0 reject the type, 2.4.0 has no ignore_null_property.
        self.assertEqual(AZAPI_FLOOR, '2.8.0')
        self.assertIn(f'version = ">= {AZAPI_FLOOR}"', self.main)

    def test_outputs_read_the_exported_response(self):
        out = self.files['modules/azure_netanchor/outputs.tf']
        self.assertIn('azapi_resource.this.output.properties.ociVcnId', out)
        for path in ('ociVcnId', 'ociSubnetId', 'dnsListeningEndpointIpAddress',
                     'dnsForwardingEndpointIpAddress'):
            self.assertIn(f'"properties.{path}"', self.main)

    def test_name_rule_is_enforced_in_the_module_too(self):
        self.assertIn('^[A-Za-z0-9-]{3,24}$', self.files['modules/azure_netanchor/variables.tf'])


class TestRoot(unittest.TestCase):

    def test_azapi_provider_declared_with_the_floor(self):
        main = _gen(NA)['main.tf']
        self.assertIn('source  = "azure/azapi"', main)
        self.assertIn(f'version = ">= {AZAPI_FLOOR}"', main)
        self.assertIn('provider "azapi" {\n  subscription_id = var.subscription_id\n}', main)

    def test_wired_to_this_configs_anchor_and_vnet(self):
        main = _gen(NA)['main.tf']
        self.assertIn('resource_anchor_id              = module.azure_resource_anchor.resource_anchor_id', main)
        self.assertIn('virtual_network_name            = module.azure_vnet.vnet_name', main)

    def test_existing_anchor_and_vnet_come_from_tfvars(self):
        na = {**NA, 'resource_anchor_ref': '', 'existing_resource_anchor_id': EXISTING_RA,
              'vnet_ref': '', 'existing_vnet_name': 'legacy-vnet'}
        files = _gen(na)
        self.assertIn('resource_anchor_id              = var.azure_netanchor.resource_anchor_id', files['main.tf'])
        self.assertIn('virtual_network_name            = var.azure_netanchor.virtual_network_name', files['main.tf'])
        tfvars = files['terraform.auto.tfvars']
        self.assertIn(f'resource_anchor_id    = "{EXISTING_RA}"', tfvars)
        self.assertIn('virtual_network_name  = "legacy-vnet"', tfvars)

    def test_one_object_variable_per_anchor(self):
        vars_tf = _gen(NA)['variables.tf']
        self.assertIn('variable "azure_netanchor" {', vars_tf)
        self.assertIn('dns_listening_allowed_cidrs     = optional(list(string), [])', vars_tf)

    def test_outputs(self):
        main = _gen(NA)['main.tf']
        self.assertIn('output "azure_netanchor_network_anchor_id"', main)
        self.assertIn('output "azure_netanchor_oci_vcn_id"', main)


class TestDefaults(unittest.TestCase):

    def test_dangling_refs_fall_back_to_the_first_card(self):
        d = _azure_na_defaults({'resource_anchor_ref': 'gone', 'vnet_ref': 'gone'}, ['ra'], ['v'])
        self.assertEqual((d['resource_anchor_ref'], d['vnet_ref']), ('ra', 'v'))

    def test_an_existing_id_wins_over_a_fallback(self):
        d = _azure_na_defaults({'resource_anchor_ref': '', 'existing_resource_anchor_id': EXISTING_RA}, ['ra'], [])
        self.assertEqual(d['resource_anchor_ref'], '')
        self.assertEqual(d['existing_resource_anchor_id'], EXISTING_RA)

    def test_an_existing_id_is_dropped_when_a_card_is_used(self):
        d = _azure_na_defaults({'resource_anchor_ref': 'ra', 'existing_resource_anchor_id': EXISTING_RA}, ['ra'], [])
        self.assertEqual(d['existing_resource_anchor_id'], '')

    def test_subnet_name_defaults_from_the_module(self):
        self.assertEqual(_azure_na_defaults({'module_name': 'na1'}, [], [])['subnet_name'], 'na1-subnet')


class TestTfvarsEntry(unittest.TestCase):

    def _entry(self, **kw):
        return _azure_na_tfvars_entry(_azure_na_defaults({**NA, **kw}, ['azure_resource_anchor'], ['azure_vnet']))

    def test_unset_optionals_are_omitted(self):
        e = self._entry()
        for key in ('zone', 'oci_vcn_dns_label', 'oci_backup_cidr_block', 'dns_', 'resource_anchor_id'):
            self.assertNotIn(key, e)

    def test_column_follows_the_longest_key_present(self):
        self.assertIn('  subnet_address_prefix = "10.0.2.0/24"', self._entry())
        e = self._entry(dns_forwarding_endpoint_enabled=True)
        self.assertIn('  subnet_address_prefix           = "10.0.2.0/24"', e)

    def test_forwarding_rules_sit_after_a_blank_line(self):
        e = self._entry(dns_forwarding_endpoint_enabled=True,
                        dns_forwarding_rules=[{'domain_names': 'a.com, b.com', 'forwarding_ip_address': '10.0.3.4'}])
        self.assertIn('\n\n  dns_forwarding_rules = [\n    {\n      domain_names          = ["a.com", "b.com"]', e)

    def test_values_are_escaped(self):
        self.assertIn(r'name                  = "a\"b"', self._entry(name='a"b'))


class TestValidation(unittest.TestCase):

    def test_a_good_anchor_passes(self):
        self.assertEqual(_errors(NA), {})

    def test_name_format(self):
        self.assertIn('name', _errors({**NA, 'name': 'bad_name'})['azure_netanchor'])
        self.assertIn('name', _errors({**NA, 'name': 'ab'})['azure_netanchor'])

    def test_needs_a_resource_anchor(self):
        e = _errors({**NA, 'resource_anchor_ref': ''})['azure_netanchor']
        self.assertIn('resource_anchor_ref', e)
        e = _errors({**NA, 'resource_anchor_ref': '', 'existing_resource_anchor_id': '/subscriptions/x/rg'})
        self.assertIn('existing_resource_anchor_id', e['azure_netanchor'])
        self.assertEqual(_errors({**NA, 'resource_anchor_ref': '', 'existing_resource_anchor_id': EXISTING_RA}), {})

    def test_needs_a_vnet(self):
        self.assertIn('vnet_ref', _errors({**NA, 'vnet_ref': ''})['azure_netanchor'])
        self.assertEqual(_errors({**NA, 'vnet_ref': '', 'existing_vnet_name': 'legacy'}), {})

    def test_its_subnet_is_its_own(self):
        e = _errors({**NA, 'subnet_address_prefix': '10.0.1.0/25'})['azure_netanchor']
        self.assertIn('delegated subnet', e['subnet_address_prefix'])

    def test_its_subnet_is_inside_the_vnet(self):
        e = _errors({**NA, 'subnet_address_prefix': '10.9.0.0/24'})['azure_netanchor']
        self.assertIn('address space', e['subnet_address_prefix'])

    def test_two_anchors_cannot_share_a_range(self):
        e = _errors(NA, {**NA, 'module_name': 'na2', 'name': 'na-2', 'subnet_address_prefix': '10.0.2.128/25'})
        self.assertIn('azure_netanchor', e['na2']['subnet_address_prefix'])

    def test_zone_sync_and_listening_endpoint_overlap(self):
        e = _errors({**NA, 'dns_zone_sync_enabled': True, 'dns_listening_endpoint_enabled': True})
        self.assertIn('dns_listening_endpoint_enabled', e['azure_netanchor'])

    def test_dns_details_need_their_endpoint(self):
        e = _errors({**NA, 'dns_listening_allowed_cidrs': '10.0.0.0/16',
                     'dns_forwarding_rules': [{'domain_names': ['a.com'], 'forwarding_ip_address': '10.0.3.4'}]})
        self.assertIn('dns_listening_allowed_cidrs', e['azure_netanchor'])
        self.assertIn('dns_forwarding_rules', e['azure_netanchor'])

    def test_forwarding_rule_needs_a_real_ip(self):
        e = _errors({**NA, 'dns_forwarding_endpoint_enabled': True,
                     'dns_forwarding_rules': [{'domain_names': ['a.com'], 'forwarding_ip_address': 'nope'}]})
        self.assertIn('dns_forwarding_rules', e['azure_netanchor'])

    def test_optional_formats(self):
        e = _errors({**NA, 'zone': '4', 'oci_vcn_dns_label': '1bad', 'oci_backup_cidr_block': 'x',
                     'subnet_name': '-bad'})['azure_netanchor']
        for f in ('zone', 'oci_vcn_dns_label', 'oci_backup_cidr_block', 'subnet_name'):
            self.assertIn(f, e)

    def test_resource_anchor_tab_requires_a_name(self):
        errors = {}
        validator.validate({'tab': 24, 'azure_resource_anchors': [{'module_name': 'ra', 'name': ''}]}, errors)
        self.assertIn('name', errors['ra'])


class TestSelftestAndReview(unittest.TestCase):

    def test_functional_test_checks_the_anchor(self):
        client = app.test_client()
        d = client.post('/api/test', json={**BASE, 'azure_network_anchors': [NA]}).get_json()
        self.assertEqual(d['failed'], 0, [r for r in d['results'] if r['status'] == 'fail'])
        names = {r['name'] for r in d['results']}
        self.assertIn('Network Anchor "azure_netanchor": its own delegated subnet', names)
        self.assertIn('modules/azure_netanchor/main.tf generated', names)

    def test_security_review_sees_the_anchor_subnet(self):
        cidrs = dict(collect_cidrs({**BASE, 'azure_network_anchors': [NA]}))
        self.assertEqual(cidrs['azure_netanchor.subnet_address_prefix'], '10.0.2.0/24')

    def test_mock_validator_knows_both_anchor_types(self):
        results = validate_terraform(_gen(NA), 'azure')
        self.assertEqual([r.name for r in results if r.status != 'pass'], [])


class TestPage(unittest.TestCase):

    def setUp(self):
        self.html = PAGE.read_text(encoding='utf-8')

    def test_tabs_and_pages(self):
        for i in (4, 5):
            self.assertIn(f'onclick="switchTab({i},true)"', self.html)
            self.assertIn(f'id="azure-page-{i}"', self.html)
        self.assertIn('vgen(24)', self.html)
        self.assertIn('vgen(25)', self.html)

    def test_payload_carries_both_kinds(self):
        self.assertIn('azure_resource_anchors: azureResourceAnchors,', self.html)
        self.assertIn('azure_network_anchors:  azureNetworkAnchors,', self.html)

    def test_saved_configs_restore_them(self):
        self.assertIn("azureNetworkAnchors  = (doc.azure_network_anchors  || [])", self.html)


@unittest.skipUnless(shutil.which('terraform'), 'terraform not installed')
class TestTerraformFmt(unittest.TestCase):
    """fmt pads each run of attributes to its own longest key, so the generated
    tfvars entry is checked for every shape of entry, not one."""

    CASES = [
        NA,
        {**NA, 'zone': '1', 'oci_vcn_dns_label': 'navcn', 'dns_listening_endpoint_enabled': True,
         'dns_listening_allowed_cidrs': '10.0.0.0/16', 'dns_forwarding_endpoint_enabled': True,
         'dns_forwarding_rules': [{'domain_names': 'a.com, b.com', 'forwarding_ip_address': '10.0.3.4'},
                                  {'domain_names': 'c.com', 'forwarding_ip_address': '10.0.3.5'}]},
        {**NA, 'resource_anchor_ref': '', 'existing_resource_anchor_id': EXISTING_RA,
         'vnet_ref': '', 'existing_vnet_name': 'legacy-vnet'},
    ]

    def test_generated_files_are_fmt_clean(self):
        for case in self.CASES:
            with self.subTest(case=json.dumps(case)[:80]), tempfile.TemporaryDirectory() as tmp:
                for path, content in _gen(case).items():
                    full = os.path.join(tmp, path)
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    with open(full, 'w', encoding='utf-8', newline='\n') as fh:
                        fh.write(content)
                r = subprocess.run(['terraform', 'fmt', '-check', '-recursive', '-diff', '.'],
                                   cwd=tmp, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
