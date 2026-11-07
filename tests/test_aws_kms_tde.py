"""
TDE master keys in AWS KMS (tab 8) — a customer-managed KMS key per card, an IAM
role + KmsTde association per VM cluster it serves, and the key registered in
OCI, wired from this configuration's own VM clusters.
Run with:  python -m unittest tests/test_aws_kms_tde.py
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import generate_all

ROOT = Path(__file__).parent.parent
BLUEPRINTS = Path(os.environ.get('TERRAFLOW_BLUEPRINTS') or ROOT.parent / 'odb-terraform-blueprints')

OIDC_ARN = 'arn:aws:iam::111122223333:oidc-provider/idcs-abc.identity.oraclecloud.com'
MODULES = ('aws-kms-key', 'aws-kms-cluster-access', 'aws-kms-oci-key')


class TestKmsTdeGeneration(unittest.TestCase):

    NET = {'module_name': 'net1', 'display_name': 'n', 'sts_access': 'ENABLED', 'kms_access': 'ENABLED'}
    INF = {'module_name': 'exa1', 'display_name': 'e'}
    CLUSTERS = [{'module_name': c, 'display_name': c, 'gi_version': '23.0.0.0', 'hostname_prefix': c,
                 'infra_ref': 'exa1', 'network_ref': 'net1'} for c in ('vmc1', 'vmc2')]
    SETTINGS = {'oidc_mode': 'existing', 'oidc_provider_arn': OIDC_ARN}

    def _gen(self, *keys, settings=None, **extra):
        return generate_all({'cloud': 'aws', 'aws_networks': [self.NET], 'aws_infras': [self.INF],
                             'aws_clusters': self.CLUSTERS, 'aws_kms_keys': list(keys),
                             'aws_kms_tde': settings or self.SETTINGS, **extra})

    def test_absent_without_keys(self):
        files = generate_all({'cloud': 'aws', 'aws_networks': [self.NET], 'aws_clusters': self.CLUSTERS,
                              'aws_kms_tde': self.SETTINGS})
        for mod in MODULES:
            self.assertNotIn(f'modules/{mod}/main.tf', files)
        for f in ('main.tf', 'variables.tf', 'terraform.auto.tfvars', 'README.md'):
            self.assertNotIn('aws_kms', files[f])
        self.assertNotIn('oracle/oci', files['main.tf'])
        self.assertIn('version = ">= 6.42.0"', files['main.tf'])

    def test_modules_and_wiring(self):
        files = self._gen({'module_name': 'prod', 'cluster_refs': ['vmc1', 'vmc2']})
        for mod in MODULES:
            for f in ('main.tf', 'variables.tf', 'outputs.tf'):
                self.assertIn(f'modules/{mod}/{f}', files)
        main = files['main.tf']
        self.assertIn('for_each = local.kms_cluster_keys', main)
        self.assertIn('vm_cluster_arn          = module.aws_vm_cluster[each.key].vm_cluster_arn', main)
        self.assertIn('vm_cluster_ocid         = module.aws_vm_cluster[each.key].ocid', main)
        self.assertIn('depends_on = [module.aws_kms_cluster_access]', main)
        self.assertIn('provider "oci"', main)
        self.assertIn('output "aws_kms_keys"', main)

    def test_version_floors(self):
        main = self._gen({'module_name': 'prod', 'cluster_refs': ['vmc1']})['main.tf']
        self.assertIn('version = ">= 6.61.0"', main)    # aws_odb_iam_role_association
        self.assertIn('version = ">= 7.27.0"', main)    # oci_dbmulticloud_oracle_db_aws_key
        # An Autonomous Database's higher aws floor wins.
        with_adb = self._gen({'module_name': 'prod', 'cluster_refs': ['vmc1']},
                             aws_autonomous_dbs=[{'module_name': 'adb1', 'display_name': 'a',
                                                  'network_ref': 'net1'}])['main.tf']
        self.assertIn('version = ">= 6.68.0"', with_adb)

    def test_tfvars_entry(self):
        tfvars = self._gen({'module_name': 'prod', 'cluster_refs': ['vmc1', 'gone'],
                            'enable_key_rotation': True, 'deletion_window_in_days': 14,
                            'register_via': 'vmc2'})['terraform.auto.tfvars']
        # A cluster this config does not have is dropped, never retargeted, and
        # register_via must be one of the key's own clusters.
        self.assertIn('cluster_refs            = ["vmc1"]', tfvars)
        self.assertIn('alias                   = "alias/oracle-tde-prod"', tfvars)
        self.assertIn('deletion_window_in_days = 14', tfvars)
        self.assertIn('enable_key_rotation     = true', tfvars)
        self.assertNotIn('register_via', tfvars)
        self.assertNotIn('multi_region', tfvars)
        self.assertIn(f'aws_kms_oidc_provider_arn = "{OIDC_ARN}"', tfvars)

    def test_adopted_key_has_no_alias(self):
        tfvars = self._gen({'module_name': 'old', 'cluster_refs': ['vmc1'],
                            'existing_arn': 'arn:aws:kms:us-east-1:111122223333:key/abc'})['terraform.auto.tfvars']
        self.assertIn('existing_arn = "arn:aws:kms:us-east-1:111122223333:key/abc"', tfvars)
        self.assertNotIn('alias', tfvars)

    def test_create_mode_settings(self):
        tfvars = self._gen({'module_name': 'prod', 'cluster_refs': ['vmc1']}, settings={
            'oidc_mode': 'create', 'oidc_provider_arn': OIDC_ARN,
            'oidc_provider_url': 'https://idcs-abc.identity.oraclecloud.com/', 'oidc_audience': 'DBMC',
            'isolate_role_to_cluster': False, 'oci_policy_compartment_id': 'ocid1.tenancy.oc1..t',
        })['terraform.auto.tfvars']
        self.assertIn('aws_kms_oidc_provider_url         = "https://idcs-abc.identity.oraclecloud.com"', tfvars)
        self.assertNotIn('aws_kms_oidc_provider_arn', tfvars)   # the other mode's value is not carried
        self.assertIn('aws_kms_oidc_audience             = "DBMC"', tfvars)
        self.assertIn('aws_kms_isolate_role_to_cluster   = false', tfvars)
        self.assertIn('aws_kms_oci_policy_compartment_id = "ocid1.tenancy.oc1..t"', tfvars)

    def test_modules_match_the_blueprint(self):
        # The app's templates are copies of odb-terraform-blueprints/aws-kms-tde/modules.
        src = BLUEPRINTS / 'aws-kms-tde' / 'modules'
        if not src.is_dir():
            self.skipTest('odb-terraform-blueprints/aws-kms-tde not checked out')
        files = self._gen({'module_name': 'prod', 'cluster_refs': ['vmc1']})
        for mod, bp in zip(MODULES, ('kms-key', 'cluster-access', 'oci-key')):
            for f in ('main.tf', 'variables.tf', 'outputs.tf'):
                with self.subTest(module=mod, file=f):
                    self.assertEqual(files[f'modules/{mod}/{f}'].rstrip('\n'),
                                     (src / bp / f).read_text(encoding='utf-8').rstrip('\n'))

    def test_formatted(self):
        import shutil, subprocess, tempfile
        tf = shutil.which('terraform') or shutil.which('tofu')
        if not tf:
            self.skipTest('terraform/tofu not found in PATH')
        cases = [
            ([{'module_name': 'prod', 'cluster_refs': ['vmc1']}], self.SETTINGS),
            ([{'module_name': 'prod', 'cluster_refs': ['vmc1'], 'multi_region': True,
               'deletion_window_in_days': 7, 'oci_compartment_id': 'ocid1.compartment.oc1..c'},
              {'module_name': 'old', 'cluster_refs': ['vmc2'], 'register_via': 'vmc2',
               'existing_arn': 'arn:aws:kms:us-east-1:111122223333:key/abc'}],
             {'oidc_mode': 'create', 'oidc_provider_url': 'https://idcs-abc.identity.oraclecloud.com',
              'oidc_audience': 'DBMC', 'isolate_role_to_cluster': False}),
        ]
        for keys, settings in cases:
            files = self._gen(*keys, settings=settings)
            with tempfile.TemporaryDirectory() as tmp, self.subTest(n=len(keys)):
                for rel, content in files.items():
                    if rel.endswith(('.tf', '.tfvars')):
                        q = Path(tmp) / rel
                        q.parent.mkdir(parents=True, exist_ok=True)
                        q.write_text(content + '\n', encoding='utf-8')
                r = subprocess.run([tf, 'fmt', '-check', '-recursive', '-diff', tmp],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestKmsTdeValidation(unittest.TestCase):

    NETS = [{'module_name': 'net1', 'sts_access': 'ENABLED', 'kms_access': 'ENABLED'},
            {'module_name': 'net2'},
            {'module_name': 'netx', 'is_existing': True, 'existing_id': 'odbnet_x'}]
    CLUSTERS = [{'module_name': 'vmc1', 'network_ref': 'net1'},
                {'module_name': 'vmc2', 'network_ref': 'net1'},
                {'module_name': 'vmc3', 'network_ref': 'net2'},
                {'module_name': 'vmcx', 'network_ref': 'netx'}]

    def _errs(self, keys=None, settings=None, **kw):
        import clouds.aws.validator as v
        key = {'module_name': 'k1', 'cluster_refs': ['vmc1'], **kw}
        errors = {}
        v.validate({'tab': 8, 'aws_networks': self.NETS, 'aws_clusters': self.CLUSTERS,
                    'aws_kms_tde': settings if settings is not None else {'oidc_provider_arn': OIDC_ARN},
                    'aws_kms_keys': keys if keys is not None else [key]}, errors)
        return errors

    def test_a_plain_key_is_valid(self):
        self.assertEqual(self._errs(), {})

    def test_needs_a_cluster_that_exists(self):
        self.assertIn('cluster_refs', self._errs(cluster_refs=[])['k1'])
        self.assertIn('cluster_refs', self._errs(cluster_refs=['gone'])['k1'])

    def test_a_cluster_takes_one_key(self):
        errs = self._errs(keys=[{'module_name': 'k1', 'cluster_refs': ['vmc1']},
                                {'module_name': 'k2', 'cluster_refs': ['vmc1', 'vmc2']}])
        self.assertNotIn('k1', errs)
        self.assertIn('already takes key "k1"', errs['k2']['cluster_refs'])

    def test_network_needs_sts_and_kms(self):
        msg = self._errs(cluster_refs=['vmc3'])['k1']['cluster_refs']
        self.assertIn('sts_access and kms_access', msg)
        # An externally provisioned network cannot be checked, so it is not flagged.
        self.assertEqual(self._errs(cluster_refs=['vmcx']), {})

    def test_existing_arn_is_a_key_arn(self):
        self.assertIn('existing_arn', self._errs(existing_arn='alias/prod')['k1'])
        self.assertNotIn('k1', self._errs(existing_arn='arn:aws:kms:us-east-1:111122223333:key/1a2b-3c'))

    def test_alias_and_window(self):
        self.assertIn('alias', self._errs(alias='alias/aws/rds')['k1'])
        self.assertIn('alias', self._errs(alias='prod')['k1'])
        self.assertIn('deletion_window_in_days', self._errs(deletion_window_in_days=45)['k1'])

    def test_register_via_is_one_of_the_keys_clusters(self):
        self.assertIn('register_via', self._errs(register_via='vmc2')['k1'])

    def test_settings(self):
        errs = self._errs(settings={'oidc_provider_arn': 'arn:aws:iam::111122223333:role/x'})
        self.assertIn('oidc_provider_arn', errs['aws_kms_tde'])
        errs = self._errs(settings={'oidc_mode': 'create', 'oidc_provider_url': 'idcs-abc'})
        self.assertIn('oidc_provider_url', errs['aws_kms_tde'])
        self.assertIn('oidc_audience', errs['aws_kms_tde'])     # create needs the audience
        errs = self._errs(settings={'oidc_provider_arn': OIDC_ARN, 'oidc_audience': '*'})
        self.assertIn('oidc_audience', errs['aws_kms_tde'])
        errs = self._errs(settings={'oidc_provider_arn': OIDC_ARN, 'oci_policy_compartment_id': 'abc'})
        self.assertIn('oci_policy_compartment_id', errs['aws_kms_tde'])

    def test_settings_unchecked_without_keys(self):
        self.assertEqual(self._errs(keys=[], settings={}), {})


class TestKmsTdePage(unittest.TestCase):

    def test_tab_and_page(self):
        html = (ROOT / 'clouds' / 'aws' / 'pages' / 'aws.html').read_text(encoding='utf-8')
        self.assertIn('switchTab(8,false)', html)
        self.assertIn('id="aws-page-8"', html)
        for key in ('aws_kms_keys:', 'aws_kms_tde:'):
            self.assertIn(key, html)     # sent by buildPayload


if __name__ == '__main__':
    unittest.main()
