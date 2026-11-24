"""ODB transit hubs: routing, reuse, same-AZ constraints, and staged peering updates."""
import copy
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
from clouds.aws.generator import generate_cfn
from clouds.aws.transit import defaults, validate_transits
from tf_validator import validate_terraform

NETWORK = {'module_name': 'net', 'display_name': 'network', 'availability_zone_id': 'use1-az6',
           'client_subnet_cidr': '10.10.0.0/24', 'backup_subnet_cidr': '10.10.1.0/24'}
HUB = {'module_name': 'hub', 'network_ref': 'net', 'vpc_mode': 'create',
       'vpc_cidr': '10.90.0.0/16', 'subnet_cidr': '10.90.0.0/28',
       'transit_gateway_id': 'tgw-0123456789abcdef0',
       'transit_gateway_route_table_id': 'tgw-rtb-0123456789abcdef0',
       'client_cidrs': ['10.20.0.0/16']}


def payload(**changes):
    return {'cloud': 'aws', 'aws_networks': [copy.deepcopy(NETWORK)], 'aws_infras': [],
            'aws_peerings': [], 'aws_clusters': [],
            'aws_transit_vpcs': [{**copy.deepcopy(HUB), **changes}]}


class TestTransitGeneration(unittest.TestCase):
    def test_opt_in_and_cloudformation_cannot_silently_drop_transit(self):
        plain = generate_all({'cloud': 'aws'})
        self.assertFalse([p for p in plain if 'transit' in p.lower()])
        with self.assertRaisesRegex(ValueError, 'Terraform and OpenTofu'):
            generate_cfn(payload())

    def test_new_vpc_one_az_attachment_and_correct_route_targets(self):
        files = generate_all(payload())
        module = files['modules/aws-transit-vpc/main.tf']
        self.assertIn('availability_zone_id    = data.aws_odb_network.selected.availability_zone_id', module)
        self.assertRegex(module, r'subnet_ids\s*=\s*\[local.subnet_id\]')
        self.assertIn('odb_network_arn        = data.aws_odb_network.selected.arn', module)
        self.assertNotIn('vpc_peering_connection_id', module)
        self.assertIn('transit_gateway_attachment_id  = local.attachment_id', module)
        self.assertIn('register_peer_cidrs ? var.config.client_cidrs : null', module)
        self.assertIn('module "aws_transit_vpc"', files['main.tf'])
        self.assertIn('TRANSIT_VPC.md', files)
        self.assertIn('module.aws_transit_vpc["<KEY>"]', files['IMPORT.md'])
        self.assertEqual([r.name for r in validate_terraform(files, 'aws') if r.status == 'fail'], [])

    def test_existing_vpc_peering_and_attachment_are_reused(self):
        data = payload(vpc_mode='existing', vpc_id='vpc-0123456789abcdef0',
                       subnet_id='subnet-0123456789abcdef0', attachment_mode='existing',
                       attachment_id='tgw-attach-0123456789abcdef0', peering_mode='existing',
                       peering_id='odbpcx-1234567890abcdef', manage_tgw_routes=False)
        files = generate_all(data)
        values = files['terraform.auto.tfvars']
        self.assertIn('tgw-attach-0123456789abcdef0', values)
        self.assertIn('odbpcx-1234567890abcdef', values)
        self.assertIn('reused attachments', files['TRANSIT_VPC.md'])
        self.assertIn('var.config.attachment_mode == "existing" ? 1 : 0', files['modules/aws-transit-vpc/main.tf'])

    def test_external_odb_network_requires_explicit_cidrs_and_keeps_reference(self):
        data = payload()
        data['aws_networks'][0].update(is_existing=True, existing_id='odbnet-1234567890abcdef')
        with self.assertRaisesRegex(ValueError, 'odb_cidrs'):
            generate_all(data)
        data['aws_transit_vpcs'][0]['odb_cidrs'] = ['10.10.0.0/24', '10.10.1.0/24']
        files = generate_all(data)
        self.assertIn('odb_network_id = local.odb_network_ids[each.value.network_ref]', files['main.tf'])

    def test_multiple_hubs_and_opentofu(self):
        data = payload()
        data['iac_tool'] = 'opentofu'
        data['aws_transit_vpcs'].append({**HUB, 'module_name': 'hub2', 'vpc_cidr': '10.91.0.0/16', 'subnet_cidr': '10.91.0.0/28'})
        files = generate_all(data)
        self.assertIn('"hub2" = {', files['terraform.auto.tfvars'])
        self.assertIn('tofu init -upgrade', files['TRANSIT_VPC.md'])

    def test_advertised_supernets_and_default_routes_are_supported(self):
        data = payload(client_cidrs=['10.0.0.0/8', '0.0.0.0/0'])
        files = generate_all(data)
        self.assertIn('["10.0.0.0/8", "0.0.0.0/0"]', files['terraform.auto.tfvars'])

    def test_transit_only_setup_omits_untouched_infrastructure_and_peering_samples(self):
        data = payload()
        data['aws_infras'] = [{'module_name': 'sample_infra', 'display_name': '', 'shape': 'Exadata.X11M'}]
        data['aws_peerings'] = [{'module_name': 'sample_peer', 'display_name': '', 'peer_network_id': ''}]
        files = generate_all(data)
        self.assertNotIn('sample_infra', files['terraform.auto.tfvars'])
        self.assertNotIn('sample_peer', files['terraform.auto.tfvars'])
        self.assertNotIn('vpc-CHANGEME', files['terraform.auto.tfvars'])

    def test_unconfigured_odb_network_cannot_be_activated_as_a_sample(self):
        data = payload()
        data['aws_networks'] = [{'module_name': 'net', 'display_name': '', 'availability_zone_id': ''}]
        with self.assertRaisesRegex(ValueError, 'network_ref'):
            generate_all(data)

    def test_validation_rejects_bad_inputs_before_export(self):
        cases = [({'network_ref': 'deleted'}, 'network_ref'),
                 ({'vpc_cidr': '10.10.0.0/16', 'subnet_cidr': '10.10.2.0/28'}, 'vpc_cidr'),
                 ({'subnet_cidr': '10.91.0.0/28'}, 'subnet_cidr'),
                 ({'transit_gateway_id': ''}, 'transit_gateway_id'),
                 ({'client_cidrs': []}, 'client_cidrs'),
                 ({'manage_tgw_routes': 'false'}, 'manage_tgw_routes'),
                 ({'attachment_mode': 'existing'}, 'attachment_mode'),
                 ({'application_route_table_ids': ['tgw-rtb-123']}, 'application_route_table_ids')]
        for changes, field in cases:
            with self.subTest(field=field):
                errors = {}
                validate_transits(payload(**changes),
                                 lambda name, key, message: errors.setdefault(name, {}).update({key: message}))
                self.assertIn(field, errors['hub'])
                with self.assertRaises(ValueError):
                    generate_all(payload(**changes))

    @patch.dict(os.environ, APP_AUTH_USER='', APP_AUTH_PASSWORD='')
    def test_validation_preview_download_and_functional_endpoints(self):
        client = app.test_client()
        data = payload()
        result = client.post('/api/validate', json={**data, 'tab': 9}).get_json()
        self.assertFalse(result.get('errors'), result)
        files = client.post('/api/files', json=data).get_json()['files']
        self.assertIn('TRANSIT_VPC.md', files)
        result = client.post('/api/test', json=data).get_json()
        self.assertEqual(result['failed'], 0, [r for r in result['results'] if r['status'] == 'fail'])
        result = client.post('/api/download', json=payload(transit_gateway_id=''))
        self.assertEqual(result.status_code, 400)
        self.assertIn('transit_gateway_id', result.get_json()['error'])
        result = client.post('/api/download', json={**data, 'iac_tool': 'cloudformation'})
        self.assertEqual(result.status_code, 400)
        self.assertIn('Terraform and OpenTofu', result.get_json()['error'])

    @unittest.skipUnless(shutil.which('terraform'), 'Terraform not installed')
    def test_generated_hcl_is_formatted(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, content in generate_all(payload()).items():
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            result = subprocess.run(['terraform', 'fmt', '-recursive', '-check', '-diff', directory],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node not installed')
    def test_ui_modes_and_saved_config_roundtrip(self):
        text = (Path(__file__).parent.parent / 'clouds/aws/pages/aws.html').read_text()
        self.assertIn('id="aws-page-9"', text)
        self.assertIn('aws_transit_vpcs:  awsTransitVpcs', text)
        functions = []
        for name in ('defAwsTransit', 'readAwsTransit', 'awsTransitCardHTML'):
            start = text.index('function ' + name + '(')
            functions.append(text[start:text.index('\n}', start) + 2])
        setup = '''
const assert=require('assert');
const awsNets=[{module_name:'net',client_subnet_cidr:'10.10.0.0/24',backup_subnet_cidr:'10.10.1.0/24'}];
let awsTransitVpcs=[],elements={};
const document={getElementById:key=>elements[key]||null};
const fv=key=>elements[key]?.value||'',fcb=key=>!!elements[key]?.checked,esc=s=>String(s);
'''
        checks = '''
awsTransitVpcs.push(defAwsTransit(0));
let html=awsTransitCardHTML(awsTransitVpcs[0],0);
assert(html.includes('id="tv0_vpc_id"'));assert(!html.includes('id="tv0_vpc_cidr"'));
elements={tv0_vpc_mode:{value:'create'},tv0_vpc_id:{value:'vpc-abc'}};
readAwsTransit(0);html=awsTransitCardHTML(awsTransitVpcs[0],0);
assert(html.includes('id="tv0_vpc_cidr"'));assert(!html.includes('id="tv0_vpc_id"'));
const saved=JSON.parse(JSON.stringify(awsTransitVpcs));
awsTransitVpcs=saved.map((d,i)=>({...defAwsTransit(i),...d}));
assert.equal(awsTransitVpcs[0].vpc_id,'vpc-abc');
assert.equal(awsTransitVpcs[0].attachment_mode,'create');
'''
        result = subprocess.run(['node'], input=setup + '\n'.join(functions) + checks,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(os.environ.get('RUN_TRANSIT_PROVIDER_TESTS') == '1' and shutil.which('terraform'),
                         'Set RUN_TRANSIT_PROVIDER_TESTS=1 to run provider-backed mocked plans')
    def test_mocked_provider_plans_reuse_and_same_az_guards(self):
        files = generate_all(payload())
        fixture = Path(__file__).parent / 'fixtures/aws_transit.tftest.hcl'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('main.tf', 'variables.tf', 'outputs.tf'):
                (root / name).write_text(files['modules/aws-transit-vpc/' + name])
            (root / 'transit.tftest.hcl').write_text(fixture.read_text())
            for command in (['terraform', 'init', '-backend=false', '-input=false', '-no-color'],
                            ['terraform', 'validate', '-no-color'],
                            ['terraform', 'test', '-no-color']):
                result = subprocess.run(command, cwd=directory, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
