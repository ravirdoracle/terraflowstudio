"""Check import instructions against generated module instances and state roots."""
import io
import os
import unittest
import zipfile
from unittest.mock import patch

from core.import_guidance import add_import_guidance


class TestImportGuidance(unittest.TestCase):
    def test_walks_called_modules_and_keeps_nested_instance_addresses(self):
        files = {
            'main.tf': '''module "networks" {
  source = "./modules/network"
  for_each = var.networks
}
data "aws_vpc" "lookup" { id = var.vpc_id }
''',
            'modules/network/main.tf': '''module "child" {
  source = "../child"
  count = var.enabled ? 1 : 0
}
resource "aws_vpc" "this" {
  tags = { comment = "a } brace // and # text" }
  dynamic "example" {
    for_each = var.rules
    content { value = example.value }
  }
}
''',
            'modules/child/extra.tf': '''resource "aws_subnet" "this" {
  for_each = var.subnets
}
''',
            'modules/unused/main.tf': 'resource "aws_vpc" "unused" {}',
        }
        guide = add_import_guidance(files)['IMPORT.md']
        self.assertIn('module.networks["<KEY>"].module.child[<INDEX>].aws_subnet.this["<KEY>"]', guide)
        self.assertIn("terraform import 'module.networks[\"<KEY>\"].aws_vpc.this' '<IMPORT_ID>'", guide)
        self.assertNotIn('aws_vpc.this[', guide)  # dynamic blocks do not index the resource
        self.assertNotIn('aws_vpc.unused', guide)
        self.assertNotIn('aws_vpc.lookup', guide)
        self.assertNotIn('IMPORT.md', files)

    def test_separates_state_roots_and_uses_selected_cli(self):
        files = {
            'main.tf': 'resource "aws_vpc" "vpc" {}',
            'kms/key/oci/main.tf': 'resource "oci_kms_key" "key" {}',
            'dg/main.tf': 'resource "oci_core_vcn" "hub" {}',
        }
        guide = add_import_guidance(files, 'opentofu')['IMPORT.md']
        self.assertIn('## Root: `.`', guide)
        self.assertIn('## Root: `kms/key/oci`', guide)
        self.assertIn('cd kms/key/oci', guide)
        self.assertIn("tofu import 'oci_kms_key.key'", guide)
        self.assertNotIn('terraform import ', guide)
        self.assertIn('tofu state pull', guide)
        self.assertIn('tofu plan', guide)

    def test_comments_strings_and_heredocs_do_not_create_resources(self):
        files = {'main.tf': '''# resource "aws_vpc" "comment" {}
/* resource "aws_vpc" "block_comment" {} */
locals {
  text = <<-TEXT
resource "aws_vpc" "example" { }
TEXT
}
resource "aws_vpc" "real" { tags = { label = "}" } }
'''}
        guide = add_import_guidance(files)['IMPORT.md']
        self.assertIn("import 'aws_vpc.real'", guide)
        for name in ('comment', 'block_comment', 'example'):
            self.assertNotIn(f'aws_vpc.{name}', guide)

    def test_no_guidance_without_a_terraform_root(self):
        self.assertEqual(add_import_guidance({}), {})


class TestGeneratedImportGuidance(unittest.TestCase):
    def test_all_products_get_guidance(self):
        from app import generate_all
        for cloud, extra in (
            ('aws', {'aws_networks': [{'module_name': 'prod'}]}),
            ('gcp', {'gcp_networks': [{'module_name': 'prod'}]}),
            ('azure', {'azure_vnets': [{'module_name': 'prod'}]}),
            ('oci', {'oci_databases': [{'module_name': 'prod', 'db_name': 'PROD'}]}),
            ('dg', {'dg_multi_az': [{'module_name': 'prod', 'oci_region': 'us-ashburn-1'}]}),
        ):
            with self.subTest(cloud=cloud):
                files = generate_all({'cloud': cloud, **extra})
                self.assertIn('IMPORT.md', files)
                self.assertIn('terraform plan', files['IMPORT.md'])
                self.assertNotIn('terraform.tfstate', files)

    def test_aws_uses_actual_module_call_address(self):
        from app import generate_all
        files = generate_all({'cloud': 'aws', 'aws_networks': [{'module_name': 'prod'}]})
        self.assertIn('module.aws_odb_network["<KEY>"].aws_odb_network.this', files['IMPORT.md'])

    @patch.dict(os.environ, APP_AUTH_USER="", APP_AUTH_PASSWORD="")
    def test_preview_file_list_and_zip_include_guide(self):
        from app import app
        client = app.test_client()
        payload = {'cloud': 'azure', 'azure_vnets': [{'module_name': 'prod', 'vnet_name': 'prod'}]}
        preview = client.post('/api/generate', json={**payload, 'file_key': 'IMPORT.md'}).get_json()
        self.assertIn('module.prod.azurerm_virtual_network', preview['content'])
        listing = client.post('/api/files', json=payload).get_json()
        self.assertIn('IMPORT.md', listing['files'])
        with patch('app._fmt_files', side_effect=lambda files, *args: files):
            download = client.post('/api/download', json=payload)
        self.assertEqual(download.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
            guide = archive.read('terraflow-studio-azure/IMPORT.md').decode()
        self.assertEqual(guide, preview['content'])

    def test_cloudformation_remains_a_single_output(self):
        from app import generate_all
        self.assertEqual(set(generate_all({'cloud': 'aws', 'iac_tool': 'cloudformation'})), {'cfn'})


if __name__ == '__main__':
    unittest.main()
