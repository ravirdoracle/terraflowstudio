"""Terraform testing for products that emit more than one root — Data Guard first.

Every Data Guard card is its own root (dg_multi_az_<name>/, dg_cross_region_<name>/)
with no top-level main.tf at all; a GCP KMS key adds kms/<name>/gcp/ and
kms/<name>/oci/. `terraform init` / `validate` only look at the directory they run
in, so a test that ran them at the top level reported a pass for code it never
checked, and the mock validator failed DG outright for lacking a root main.tf.
"""
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import app as app_module
from app import app, generate_all
from tf_validator import validate_terraform, summarise, tf_roots, _extract_var_refs

ROOT = Path(__file__).parent.parent
DG_PAGE = ROOT / 'oci' / 'pages' / 'dg.html'

DG = {
    'cloud': 'dg',
    'dg_multi_az': [{'module_name': 'maz1', 'oci_region': 'us-ashburn-1'}],
    'dg_cross_region': [{'module_name': 'cr1', 'primary_oci_region': 'us-ashburn-1',
                         'standby_oci_region': 'us-phoenix-1'}],
}


class TestTfRoots(unittest.TestCase):

    def test_data_guard_has_one_root_per_card_and_no_top_level(self):
        self.assertEqual(tf_roots(generate_all(DG)), ['dg_cross_region_cr1', 'dg_multi_az_maz1'])

    def test_module_directories_are_not_roots(self):
        roots = tf_roots(generate_all(DG))
        self.assertFalse([r for r in roots if 'modules' in r.split('/')])

    def test_a_cloud_root_is_the_top_level(self):
        self.assertEqual(tf_roots({'main.tf': '', 'modules/x/main.tf': '', 'README.md': ''}), [''])

    def test_gcp_kms_roots_are_found_beside_the_main_root(self):
        files = generate_all({'cloud': 'gcp', 'gcp_kms_keys': [{'module_name': 'k1'}]})
        roots = tf_roots(files)
        self.assertIn('', roots)
        self.assertIn('kms/k1/gcp', roots)
        self.assertIn('kms/k1/oci', roots)


class TestMockValidatorOnDataGuard(unittest.TestCase):

    def setUp(self):
        self.results = validate_terraform(generate_all(DG), 'dg')

    def test_no_failures(self):
        self.assertEqual([(r.group, r.name, r.error) for r in self.results if r.status == 'fail'], [])

    def test_no_spurious_top_level_checks(self):
        names = {r.name for r in self.results}
        self.assertNotIn('Root terraform.auto.tfvars exists', names)
        self.assertNotIn('Root declares hashicorp/google provider', names)

    def test_each_root_reports_under_its_directory(self):
        groups = {r.group for r in self.results}
        for root in ('dg_multi_az_maz1/', 'dg_cross_region_cr1/'):
            self.assertIn(f'{root} · File Structure', groups)
            self.assertIn(f'{root} · Provider', groups)
            self.assertIn(f'{root} · Resource Schema', groups)
        self.assertTrue(all(r.file and r.file.startswith(('dg_multi_az_maz1/', 'dg_cross_region_cr1/'))
                            for r in self.results))

    def test_the_oci_provider_is_what_is_checked(self):
        self.assertIn('Root declares oracle/oci provider', {r.name for r in self.results})

    def test_oci_resource_types_are_known(self):
        unknown = [r.name for r in self.results if 'is known' in r.name and r.status != 'pass']
        self.assertEqual(unknown, [])

    def test_multi_az_root_resources_are_schema_checked(self):
        # Multi-AZ declares its resources in the root — there are no modules.
        self.assertTrue(any(r.group == 'dg_multi_az_maz1/ · Resource Schema' and 'root "oci_core_' in r.name
                            for r in self.results))

    def test_a_missing_required_argument_fails(self):
        files = generate_all(DG)
        path = 'dg_multi_az_maz1/main.tf'
        files[path] = re.sub(r'\n\s*vcn_id\s*=.*', '\n', files[path], count=1)
        failed = [r for r in validate_terraform(files, 'dg') if r.status == 'fail']
        self.assertTrue(any('"vcn_id"' in r.name and r.file == path for r in failed),
                        [r.name for r in failed])

    def test_every_named_block_is_checked_not_just_the_first_of_its_type(self):
        files = generate_all(DG)
        path = 'dg_multi_az_maz1/main.tf'
        blocks = re.findall(r'resource "oci_core_local_peering_gateway" "(\w+)"', files[path])
        self.assertGreater(len(blocks), 1)
        # Break only the second one.
        head, sep, tail = files[path].partition(f'resource "oci_core_local_peering_gateway" "{blocks[1]}"')
        files[path] = head + sep + re.sub(r'\n\s*vcn_id\s*=.*', '\n', tail, count=1)
        failed = [r for r in validate_terraform(files, 'dg') if r.status == 'fail']
        self.assertTrue(any('"vcn_id"' in r.name for r in failed))


class TestVarRefsInInterpolations(unittest.TestCase):

    def test_interpolated_var_counts_as_used(self):
        self.assertEqual(_extract_var_refs('x = "${var.prefix}-lpg"'), {'prefix'})

    def test_plain_string_is_not_a_reference(self):
        self.assertEqual(_extract_var_refs('x = "var.prefix"'), set())


class TestCloudRootsUnchanged(unittest.TestCase):
    """The top-level cloud root keeps its group names and its required files."""

    def test_aws_top_level_groups_are_unprefixed(self):
        results = validate_terraform(generate_all({'cloud': 'aws'}), 'aws')
        groups = {r.group for r in results}
        self.assertIn('File Structure', groups)
        self.assertIn('Root terraform.auto.tfvars exists', {r.name for r in results})

    def test_an_empty_file_set_still_fails_for_the_missing_root(self):
        failed = {r.name for r in validate_terraform({}, 'aws') if r.status == 'fail'}
        self.assertIn('Root main.tf exists', failed)

    def test_dg_roots_appended_to_a_cloud_config_are_validated_on_their_own(self):
        files = generate_all({**DG, 'cloud': 'aws'})
        groups = {r.group for r in validate_terraform(files, 'aws')}
        self.assertIn('Provider', groups)
        self.assertIn('dg_multi_az_maz1/ · Provider', groups)


class TestDataGuardEndpoints(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_tf_validate_endpoint(self):
        d = self.client.post('/api/tf-validate', json=DG).get_json()
        self.assertEqual(d['failed'], 0, [r for r in d['results'] if r['status'] == 'fail'])
        self.assertGreater(d['passed'], 50)

    def test_functional_test_no_longer_asks_dg_for_a_top_level_main_tf(self):
        d = self.client.post('/api/test', json=DG).get_json()
        self.assertEqual(d['failed'], 0, [r for r in d['results'] if r['status'] == 'fail'])
        names = {r['name'] for r in d['results']}
        self.assertIn('dg_multi_az_maz1/main.tf generated', names)
        self.assertIn('dg_cross_region_cr1/main.tf generated', names)

    def test_tf_cli_runs_init_and_validate_in_every_root(self):
        calls = []

        def fake_run(cmd, cwd=None, **kw):
            calls.append((cmd[1], Path(cwd or '.')))
            out = '{"valid": true, "diagnostics": []}' if cmd[1] == 'validate' else '{}'
            return mock.Mock(returncode=0, stdout=out, stderr='')

        with mock.patch.object(app_module, '_find_tf_bin', return_value='terraform'), \
             mock.patch.object(app_module.subprocess, 'run', side_effect=fake_run):
            d = self.client.post('/api/tf-cli', json=DG).get_json()

        for step in ('init', 'validate'):
            dirs = sorted(p.name for c, p in calls if c == step)
            self.assertEqual(dirs, ['dg_cross_region_cr1', 'dg_multi_az_maz1'], step)
        groups = {r['group'] for r in d['results']}
        self.assertIn('terraform validate · dg_multi_az_maz1/', groups)
        self.assertIn('terraform validate · dg_cross_region_cr1/', groups)
        self.assertEqual(d['failed'], 0)

    def test_tf_cli_reports_a_failing_root_by_its_directory(self):
        def fake_run(cmd, cwd=None, **kw):
            if cmd[1] == 'validate' and (cwd or '').endswith('dg_multi_az_maz1'):
                out = ('{"valid": false, "diagnostics": [{"severity": "error", "summary": "Bad",'
                       ' "detail": "x", "range": {"filename": "main.tf"}}]}')
            else:
                out = '{"valid": true, "diagnostics": []}' if cmd[1] == 'validate' else '{}'
            return mock.Mock(returncode=0, stdout=out, stderr='')

        with mock.patch.object(app_module, '_find_tf_bin', return_value='terraform'), \
             mock.patch.object(app_module.subprocess, 'run', side_effect=fake_run):
            d = self.client.post('/api/tf-cli', json=DG).get_json()
        bad = [r for r in d['results'] if r['status'] == 'fail']
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]['file'], 'dg_multi_az_maz1/main.tf')

    def test_tf_cli_with_nothing_generated_fails_rather_than_passing(self):
        with mock.patch.object(app_module, '_find_tf_bin', return_value='terraform'), \
             mock.patch.object(app_module.subprocess, 'run',
                               return_value=mock.Mock(returncode=0, stdout='', stderr='')):
            d = self.client.post('/api/tf-cli', json={'cloud': 'dg'}).get_json()
        self.assertGreater(d['failed'], 0)


class TestDataGuardPageTabs(unittest.TestCase):

    def setUp(self):
        self.html = DG_PAGE.read_text(encoding='utf-8')

    def test_three_test_tabs(self):
        for tab in ('functional', 'tfvalidate', 'tfcli'):
            self.assertIn(f"switchTestTab('{tab}')", self.html)
            self.assertIn(f'id="ttab-{tab}"', self.html)

    def test_each_tab_posts_to_its_endpoint(self):
        self.assertIn("functional: '/api/test', tfvalidate: '/api/tf-validate', tfcli: '/api/tf-cli'", self.html)

    def test_results_are_read_by_status(self):
        # /api/test rows carry status, never `passed` — reading t.passed showed every check as failed.
        self.assertNotIn('t.passed', self.html)
        self.assertIn("r.status === 'pass'", self.html)

    def test_summary_tiles_are_styled(self):
        # dg.html carries its own stylesheet rather than linking app.css.
        for rule in ('.test-summary{', '.test-stat.warn', '.test-warn-row'):
            self.assertIn(rule, self.html)



class TestDataGuardCardsCanBeRemoved(unittest.TestCase):
    """The page starts with no cards, so a `length>1` guard on Remove meant the
    first card added could never be removed."""

    def setUp(self):
        self.html = DG_PAGE.read_text(encoding='utf-8')

    def test_remove_is_not_guarded_by_a_count(self):
        for arr in ('dgMazs', 'dgCrs'):
            self.assertNotIn(f'{arr}.length>1?`<button class="inst-rm"', self.html)
            self.assertIn(f'removeInst({arr},${{i}},', self.html)

    def test_loading_a_config_replaces_the_cards_outright(self):
        self.assertIn('dgMazs = mazs.map(', self.html)
        self.assertNotIn('if (mazs.length) dgMazs', self.html)


if __name__ == '__main__':
    unittest.main()
