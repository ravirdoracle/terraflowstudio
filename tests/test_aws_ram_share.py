"""
AWS RAM resource shares (aws_ram_resource_share) — sharing this configuration's
own ODB Networks and Exadata Infrastructures with other accounts in the AWS
Organization, ARNs wired from the module outputs.
Run with:  python -m unittest tests/test_aws_ram_share.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import generate_all


class TestRamResourceShareInMainRoot(unittest.TestCase):
    """aws_ram_resource_share over this configuration's own networks and infras,
    in the main root, with ARNs wired from the module outputs."""

    NET = {'module_name': 'net1', 'display_name': 'n'}
    EXT = {'module_name': 'netx', 'is_existing': True, 'existing_id': 'odbnet_x',
           'existing_arn': 'arn:aws:odb:us-east-1:111111111111:odb-network/odbnet_x'}
    INF = {'module_name': 'exa1', 'display_name': 'e'}

    def _gen(self, *shares, networks=None):
        return generate_all({'cloud': 'aws', 'aws_networks': networks or [self.NET],
                             'aws_infras': [self.INF], 'aws_ram_shares': list(shares)})

    def test_absent_without_shares(self):
        files = generate_all({'cloud': 'aws', 'aws_networks': [self.NET]})
        self.assertNotIn('modules/aws-ram-share/main.tf', files)
        for f in ('main.tf', 'variables.tf', 'terraform.auto.tfvars'):
            self.assertNotIn('aws_ram_share', files[f])

    def test_module_and_wiring(self):
        files = self._gen({'module_name': 's1', 'infra_refs': ['exa1'], 'network_refs': ['net1'],
                           'principals': ['333333333333']})
        for f in ('main.tf', 'variables.tf', 'outputs.tf'):
            self.assertIn(f'modules/aws-ram-share/{f}', files)
        main = files['main.tf']
        self.assertIn('for_each = var.aws_ram_shares', main)
        self.assertIn('{ for k, m in module.aws_exadata_infra : k => m.infra_arn }', main)
        self.assertIn('{ for k, m in module.aws_odb_network : k => m.network_arn }', main)
        self.assertIn('output "ram_resource_shares"', main)

    def test_associations_are_keyed_by_name_not_arn(self):
        # ARNs of resources created in the same apply are unknown at plan time,
        # and for_each keys must be known then.
        files = self._gen({'module_name': 's1', 'infra_refs': ['exa1'], 'principals': ['333333333333']})
        self.assertIn('for_each = var.resource_arns', files['modules/aws-ram-share/main.tf'])
        self.assertIn('type        = map(string)', files['modules/aws-ram-share/variables.tf'])
        self.assertIn('"exadata-infrastructure/${r}" => local.ram_infra_arns[r]', files['main.tf'])

    def test_tfvars_entry(self):
        tfvars = self._gen({'module_name': 's1', 'name': 'prod-share', 'infra_refs': ['exa1'],
                            'principals': '333333333333, 444444444444'})['terraform.auto.tfvars']
        self.assertIn('name       = "prod-share"', tfvars)
        self.assertIn('principals = ["333333333333", "444444444444"]', tfvars)
        self.assertIn('infra_refs = ["exa1"]', tfvars)
        self.assertNotIn('allow_external_principals', tfvars)

    def test_dangling_refs_are_dropped_not_retargeted(self):
        # Sharing a *different* resource with another account is worse than one fewer.
        tfvars = self._gen({'module_name': 's1', 'infra_refs': ['gone', 'exa1'],
                            'network_refs': ['gone'], 'principals': ['333333333333']})['terraform.auto.tfvars']
        self.assertIn('infra_refs = ["exa1"]', tfvars)
        self.assertNotIn('network_refs', tfvars)

    def test_external_network_is_shared_by_its_arn(self):
        files = self._gen({'module_name': 's1', 'network_refs': ['netx'], 'principals': ['333333333333']},
                          networks=[self.NET, self.EXT])
        self.assertIn('"netx" = "arn:aws:odb:us-east-1:111111111111:odb-network/odbnet_x"',
                      files['terraform.auto.tfvars'])
        self.assertIn('var.existing_odb_network_arns', files['main.tf'])

    def test_formatted(self):
        import shutil, subprocess, tempfile
        tf = shutil.which('terraform') or shutil.which('tofu')
        if not tf:
            self.skipTest('terraform/tofu not found in PATH')
        cases = [
            [{'module_name': 's1', 'infra_refs': ['exa1'], 'principals': ['333333333333']}],
            [{'module_name': 's1', 'infra_refs': ['exa1'], 'network_refs': ['net1', 'netx'],
              'resource_arns': ['arn:aws:odb:us-east-1:111111111111:odb-network/other'],
              'principals': ['333333333333'], 'allow_external_principals': True},
             {'module_name': 's2', 'network_refs': ['net1'], 'principals': ['444444444444']}],
        ]
        for shares in cases:
            files = self._gen(*shares, networks=[self.NET, self.EXT])
            with tempfile.TemporaryDirectory() as tmp, self.subTest(n=len(shares)):
                for rel, content in files.items():
                    if rel.endswith(('.tf', '.tfvars')):
                        q = Path(tmp) / rel
                        q.parent.mkdir(parents=True, exist_ok=True)
                        q.write_text(content + '\n', encoding='utf-8')
                r = subprocess.run([tf, 'fmt', '-check', '-recursive', '-diff', tmp],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestRamResourceShareValidation(unittest.TestCase):

    def _errs(self, networks=None, **kw):
        import clouds.aws.validator as v
        share = {'module_name': 's1', 'infra_refs': ['exa1'], 'principals': ['333333333333'], **kw}
        errors = {}
        v.validate({'tab': 7, 'aws_networks': networks or [{'module_name': 'net1'}],
                    'aws_infras': [{'module_name': 'exa1'}], 'aws_ram_shares': [share]}, errors)
        return errors.get('s1', {})

    def test_a_plain_share_is_valid(self):
        self.assertEqual(self._errs(), {})

    def test_principals(self):
        self.assertIn('principals', self._errs(principals=[]))
        self.assertIn('principals', self._errs(principals=['44444']))

    def test_needs_a_resource(self):
        self.assertIn('network_refs', self._errs(infra_refs=[]))

    def test_refs_must_exist(self):
        self.assertIn('infra_refs', self._errs(infra_refs=['gone']))

    def test_external_ref_needs_its_arn(self):
        ext = [{'module_name': 'netx', 'is_existing': True, 'existing_id': 'odbnet_x'}]
        self.assertIn('network_refs', self._errs(networks=ext, network_refs=['netx']))

    def test_other_arns_must_be_odb_network_or_infra(self):
        self.assertIn('resource_arns', self._errs(resource_arns=['arn:aws:rds:us-east-1:111111111111:db:x']))
        self.assertNotIn('resource_arns', self._errs(
            resource_arns=['arn:aws:odb:us-east-1:111111111111:odb-network/n']))

    def test_external_principals_are_rejected(self):
        self.assertIn('allow_external_principals', self._errs(allow_external_principals=True))


if __name__ == '__main__':
    unittest.main()
