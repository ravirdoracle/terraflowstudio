"""Region / zone catalogues loaded from config/<cloud>_regions.json."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import regions
from regions import RegionConfigError
from clouds.aws.generator import _oci_region_for as aws_oci_region
from clouds.gcp.generator import _oci_region_for as gcp_oci_region
from app import app

CLOUDS = ('aws', 'azure', 'gcp')


class TestCataloguesLoad(unittest.TestCase):
    """Shape rules that hold for every cloud."""

    def test_all_catalogues_non_empty(self):
        for cloud in CLOUDS:
            self.assertGreater(len(regions.regions(cloud)), 0, cloud)

    def test_every_entry_has_required_fields(self):
        for cloud in CLOUDS:
            for r in regions.regions(cloud):
                for field in ('region', 'label', 'zones', 'status'):
                    self.assertIn(field, r, f'{cloud}/{r.get("region")} missing {field}')

    def test_region_codes_unique(self):
        for cloud in CLOUDS:
            codes = [r['region'] for r in regions.regions(cloud)]
            self.assertEqual(len(codes), len(set(codes)), cloud)

    def test_status_values_valid(self):
        for cloud in CLOUDS:
            for r in regions.regions(cloud):
                self.assertIn(r['status'], ('live', 'planned'), f'{cloud}/{r["region"]}')

    def test_planned_regions_have_no_zones(self):
        # A planned region is not selectable, so offering zones for it would be
        # a dropdown that leads nowhere.
        for cloud in CLOUDS:
            for r in regions.regions(cloud):
                if r['status'] == 'planned':
                    self.assertEqual(r['zones'], [],
                                     f'{cloud}/{r["region"]} is planned but lists zones')

    def test_zones_are_lists(self):
        for cloud in CLOUDS:
            for r in regions.regions(cloud):
                self.assertIsInstance(r['zones'], list, f'{cloud}/{r["region"]}')


class TestGloballyUniqueZones(unittest.TestCase):
    """AWS AZ IDs and GCP zones are globally unique; Azure numbers are not."""

    def test_zones_unique_for_aws_and_gcp(self):
        for cloud in ('aws', 'gcp'):
            zs = [z for r in regions.regions(cloud) for z in r['zones']]
            self.assertEqual(len(zs), len(set(zs)), cloud)

    def test_zone_to_region_round_trips(self):
        for cloud in ('aws', 'gcp'):
            zmap, z2r = regions.zone_map(cloud), regions.zone_to_region(cloud)
            for code, zs in zmap.items():
                for z in zs:
                    self.assertEqual(z2r[z], code, f'{cloud}/{z}')

    def test_azure_reuses_zone_numbers_across_regions(self):
        # Not a defect: '1' in eastus is unrelated to '1' in uksouth. This is why
        # the catalogue sets zones_are_region_scoped and skips the uniqueness check.
        zs = [z for r in regions.regions('azure') for z in r['zones']]
        self.assertGreater(len(zs), len(set(zs)))

    def test_azure_zone_map_keeps_regions_separate(self):
        zmap = regions.zone_map('azure')
        self.assertEqual(zmap['eastus'], ['1', '3'])
        self.assertEqual(zmap['uksouth'], ['1', '2'])


class TestOciRegionMapping(unittest.TestCase):
    """The catalogues replaced hardcoded dicts; behaviour must be unchanged."""

    OLD_AWS = {
        'us-east-1': 'us-ashburn-1',        'us-east-2': 'us-chicago-1',
        'us-west-1': 'us-sanjose-1',        'us-west-2': 'us-portland-1',
        'eu-west-1': 'eu-frankfurt-1',      'eu-central-1': 'eu-frankfurt-1',
        'ap-southeast-1': 'ap-singapore-1', 'ap-northeast-1': 'ap-tokyo-1',
    }
    OLD_GCP = {
        'us-east4': 'us-ashburn-1',                  'us-central1': 'us-desmoines-1',
        'us-west3': 'us-saltlake-2',                 'northamerica-northeast1': 'ca-montreal-1',
        'northamerica-northeast2': 'ca-toronto-1',   'europe-west3': 'eu-frankfurt-1',
        'europe-west2': 'uk-london-1',               'europe-west8': 'eu-milan-1',
        'asia-south2': 'ap-delhi-1',                 'australia-southeast2': 'ap-melbourne-1',
        'asia-south1': 'ap-mumbai-1',                'asia-northeast2': 'ap-osaka-1',
        'australia-southeast1': 'ap-sydney-1',       'asia-northeast1': 'ap-tokyo-1',
        'southamerica-east1': 'sa-saopaulo-1',
    }

    def test_aws_matches_previous_hardcoded_mapping(self):
        for r in regions.regions('aws'):
            code = r['region']
            self.assertEqual(aws_oci_region(code),
                             self.OLD_AWS.get(code, 'us-ashburn-1'), code)

    def test_gcp_matches_previous_hardcoded_mapping(self):
        for r in regions.regions('gcp'):
            code = r['region']
            self.assertEqual(gcp_oci_region(code),
                             self.OLD_GCP.get(code, 'us-ashburn-1'), code)

    def test_unknown_region_falls_back_to_default(self):
        self.assertEqual(aws_oci_region('no-such-region-1'), regions.default_oci_region('aws'))
        self.assertEqual(gcp_oci_region('no-such-region-1'), regions.default_oci_region('gcp'))

    def test_gcp_live_regions_all_mapped(self):
        # Unlike AWS, GCP's mapping is complete - a null here means a live region
        # would silently generate an OCI provider pointing at Ashburn.
        for r in regions.regions('gcp'):
            if r['status'] == 'live':
                self.assertTrue(r['oci_region'], f'{r["region"]} is live but unmapped')

    def test_mapped_and_unmapped_partition_the_catalogue(self):
        for cloud in ('aws', 'gcp'):
            mapped = set(regions.to_oci_region(cloud))
            unmapped = set(regions.unmapped_oci_regions(cloud))
            self.assertEqual(mapped & unmapped, set(), cloud)
            self.assertEqual(len(mapped) + len(unmapped), len(regions.regions(cloud)), cloud)


class TestValidationRejectsBadConfig(unittest.TestCase):
    """Malformed config fails at load, rather than rendering an empty dropdown."""

    def _load(self, doc):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'bad_regions.json').write_text(json.dumps(doc), encoding='utf-8')
            orig, regions.CONFIG_DIR = regions.CONFIG_DIR, Path(td)
            try:
                return regions.load('bad', refresh=True)
            finally:
                regions.CONFIG_DIR = orig
                regions._cache.pop('bad', None)

    def test_missing_regions_key(self):
        with self.assertRaises(RegionConfigError):
            self._load({'nope': []})

    def test_empty_regions(self):
        with self.assertRaises(RegionConfigError):
            self._load({'regions': []})

    def test_duplicate_region_code(self):
        e = {'region': 'us-east-1', 'label': 'x', 'zones': [], 'status': 'live'}
        with self.assertRaises(RegionConfigError):
            self._load({'regions': [e, dict(e)]})

    def test_duplicate_zone_across_regions(self):
        with self.assertRaises(RegionConfigError):
            self._load({'regions': [
                {'region': 'a', 'label': 'A', 'zones': ['z1'], 'status': 'live'},
                {'region': 'b', 'label': 'B', 'zones': ['z1'], 'status': 'live'},
            ]})

    def test_duplicate_zone_allowed_when_region_scoped(self):
        doc = self._load({
            'zones_are_region_scoped': True,
            'regions': [
                {'region': 'a', 'label': 'A', 'zones': ['1'], 'status': 'live'},
                {'region': 'b', 'label': 'B', 'zones': ['1'], 'status': 'live'},
            ]})
        self.assertEqual(len(doc['regions']), 2)

    def test_bad_status(self):
        with self.assertRaises(RegionConfigError):
            self._load({'regions': [
                {'region': 'a', 'label': 'A', 'zones': [], 'status': 'maybe'}]})

    def test_zones_not_a_list(self):
        with self.assertRaises(RegionConfigError):
            self._load({'regions': [
                {'region': 'a', 'label': 'A', 'zones': 'one', 'status': 'live'}]})

    def test_missing_field(self):
        with self.assertRaises(RegionConfigError):
            self._load({'regions': [{'region': 'a', 'label': 'A', 'zones': []}]})

    def test_missing_file(self):
        with self.assertRaises(RegionConfigError):
            regions.load('does-not-exist', refresh=True)


class TestPagesRenderCatalogue(unittest.TestCase):

    PAGES = (('/aws', 'ODB_REGIONS', 'aws'),
             ('/azure', 'AZURE_REGIONS', 'azure'),
             ('/gcp', 'GCP_REGIONS', 'gcp'))

    def setUp(self):
        self.client = app.test_client()

    def test_pages_embed_their_catalogue(self):
        for path, const, _ in self.PAGES:
            html = self.client.get(path).get_data(as_text=True)
            self.assertIn(f'const {const} = [', html, path)

    def test_no_unrendered_jinja_left(self):
        for path, _, cloud in self.PAGES:
            html = self.client.get(path).get_data(as_text=True)
            self.assertNotIn(f'{cloud}_regions_json', html, path)

    def test_every_region_reaches_the_page(self):
        for path, _, cloud in self.PAGES:
            html = self.client.get(path).get_data(as_text=True)
            for r in regions.regions(cloud):
                self.assertIn(f'"{r["region"]}"', html, f'{path} {r["region"]}')

    def test_every_zone_reaches_the_page(self):
        for path, _, cloud in self.PAGES:
            html = self.client.get(path).get_data(as_text=True)
            for r in regions.regions(cloud):
                for z in r['zones']:
                    self.assertIn(f'"{z}"', html, f'{path} {z}')

    def test_azure_groups_survive(self):
        # The location dropdown builds its optgroups from this field.
        html = self.client.get('/azure').get_data(as_text=True)
        for group in {r['group'] for r in regions.regions('azure')}:
            self.assertIn(group, html)


# ==============================================================================
#  CATALOGUE EDITOR - /regions and /api/regions/<cloud>
#  Writes land on the same files every dropdown and the OCI provider region read
#  from, so a bad save would empty every dropdown in the app at the next load.
#  Everything here runs against a temp CONFIG_DIR: the real catalogues are never
#  touched by the suite.
# ==============================================================================

class RegionEditorBase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_dir = regions.CONFIG_DIR
        # Copy the real catalogues so the tests exercise real shapes.
        tmp = Path(self._tmp.name)
        for cloud in regions.CLOUDS:
            src = self._orig_dir / f'{cloud}_regions.json'
            (tmp / f'{cloud}_regions.json').write_text(
                src.read_text(encoding='utf-8'), encoding='utf-8')
        regions.CONFIG_DIR = tmp
        regions._cache.clear()
        self.tmp = tmp

    def tearDown(self):
        regions.CONFIG_DIR = self._orig_dir
        regions._cache.clear()
        self._tmp.cleanup()

    def read(self, cloud):
        return json.loads((self.tmp / f'{cloud}_regions.json').read_text(encoding='utf-8'))

    def raw(self, cloud):
        return (self.tmp / f'{cloud}_regions.json').read_text(encoding='utf-8')


class TestCatalogueWriter(RegionEditorBase):

    def test_entries_stay_one_line_each(self):
        # json.dumps(indent=2) would put every field on its own line and turn a
        # one-word edit into a 250-line diff. These files get read by people.
        for cloud in regions.CLOUDS:
            doc = regions.load(cloud)
            body = regions.dumps(cloud, doc)
            entry_lines = [l for l in body.split('\n') if l.strip().startswith('{ "')]
            self.assertEqual(len(entry_lines), len(doc['regions']), cloud)

    def test_writing_is_idempotent(self):
        for cloud in regions.CLOUDS:
            regions.save(cloud, regions.load(cloud))
            once = self.raw(cloud)
            regions.save(cloud, regions.load(cloud))
            self.assertEqual(once, self.raw(cloud), f'{cloud}: second save differs')

    def test_field_order_follows_the_existing_file(self):
        # Azure lists `group` before `status`; AWS/GCP put the oci_* pair last.
        # Reordering would rewrite every line for no reason.
        for cloud in regions.CLOUDS:
            before = list(regions.load(cloud)['regions'][0].keys())
            regions.save(cloud, regions.load(cloud))
            regions._cache.clear()
            self.assertEqual(list(self.read(cloud)['regions'][0].keys()), before, cloud)

    def test_top_level_keys_survive_a_save(self):
        # _comment carries the field documentation, and the other keys change
        # behaviour: default_oci_region feeds the generator, and losing
        # zones_are_region_scoped would make Azure fail its own duplicate check.
        regions.save('aws', regions.load('aws'))
        after = self.read('aws')
        self.assertIn('_comment', after)
        self.assertGreater(len(after['_comment']), 5)
        self.assertEqual(after['default_oci_region'], 'us-ashburn-1')

        regions.save('azure', regions.load('azure'))
        azure = self.read('azure')
        self.assertTrue(azure['zones_are_region_scoped'])
        self.assertIn('default_zones', azure)

    def test_a_rejected_save_leaves_the_file_alone(self):
        before = self.raw('aws')
        doc = regions.load('aws')
        doc['regions'][1]['region'] = doc['regions'][0]['region']   # duplicate
        with self.assertRaises(RegionConfigError):
            regions.save('aws', doc)
        self.assertEqual(before, self.raw('aws'))

    def test_saving_refreshes_the_cache(self):
        # No restart: the cloud pages embed the catalogue at render time.
        doc = regions.load('gcp')
        doc['regions'].append({'region': 'test-region-9', 'label': 'Test',
                               'zones': ['test-zone-9'], 'status': 'live'})
        regions.save('gcp', doc)
        self.assertIn('test-region-9', [r['region'] for r in regions.regions('gcp')])


class TestRegionApi(RegionEditorBase):

    def setUp(self):
        super().setUp()
        self.client = app.test_client()

    def test_get_returns_the_doc_and_a_field_spec(self):
        for cloud in regions.CLOUDS:
            d = self.client.get(f'/api/regions/{cloud}').get_json()
            self.assertEqual(d['cloud'], cloud)
            self.assertTrue(d['doc']['regions'])
            self.assertEqual(d['spec']['core'], ['region', 'label', 'zones', 'status'])

    def test_the_spec_names_the_optional_fields_each_cloud_uses(self):
        get = lambda c: self.client.get(f'/api/regions/{c}').get_json()['spec']
        self.assertEqual(get('aws')['optional'], ['oci_label', 'oci_region'])
        self.assertEqual(get('gcp')['optional'], ['oci_label', 'oci_region'])
        self.assertEqual(get('azure')['optional'], ['group'])
        # Azure numbers zones per region, so the duplicate check is off there.
        self.assertTrue(get('azure')['zones_are_region_scoped'])
        self.assertFalse(get('aws')['zones_are_region_scoped'])

    def test_unknown_cloud_is_a_404(self):
        self.assertEqual(self.client.get('/api/regions/oracle').status_code, 404)
        self.assertEqual(self.client.post('/api/regions/oracle', json={'doc': {}}).status_code, 404)

    def test_adding_a_region_round_trips(self):
        doc = self.client.get('/api/regions/aws').get_json()['doc']
        doc['regions'].append({'region': 'me-central-1', 'label': 'Middle East (UAE)',
                               'zones': ['mec1-az1'], 'status': 'live',
                               'oci_label': 'UAE Central (Abu Dhabi)', 'oci_region': None})
        res = self.client.post('/api/regions/aws', json={'doc': doc})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['n_regions'], len(doc['regions']))
        self.assertIn('me-central-1', [r['region'] for r in self.read('aws')['regions']])
        # An unmapped oci_region stays null rather than becoming "".
        added = [r for r in self.read('aws')['regions'] if r['region'] == 'me-central-1'][0]
        self.assertIsNone(added['oci_region'])

    def test_removing_a_region_round_trips(self):
        doc = self.client.get('/api/regions/gcp').get_json()['doc']
        gone = doc['regions'].pop(0)['region']
        self.client.post('/api/regions/gcp', json={'doc': doc})
        self.assertNotIn(gone, [r['region'] for r in self.read('gcp')['regions']])

    def test_a_duplicate_zone_is_rejected_with_the_loaders_message(self):
        doc = self.client.get('/api/regions/aws').get_json()['doc']
        doc['regions'][1]['zones'] = list(doc['regions'][0]['zones'])
        before = self.raw('aws')
        res = self.client.post('/api/regions/aws', json={'doc': doc})
        self.assertEqual(res.status_code, 400)
        self.assertIn('already listed under', res.get_json()['error'])
        self.assertEqual(before, self.raw('aws'), 'file changed despite rejection')

    def test_azure_may_repeat_zone_numbers_across_regions(self):
        # The same check that rejects AWS duplicates must not fire here.
        doc = self.client.get('/api/regions/azure').get_json()['doc']
        for r in doc['regions'][:3]:
            r['zones'] = ['1', '2']
        self.assertEqual(self.client.post('/api/regions/azure', json={'doc': doc}).status_code, 200)

    def test_a_bad_status_is_rejected(self):
        doc = self.client.get('/api/regions/aws').get_json()['doc']
        doc['regions'][0]['status'] = 'coming-soon'
        res = self.client.post('/api/regions/aws', json={'doc': doc})
        self.assertEqual(res.status_code, 400)
        self.assertIn('status must be', res.get_json()['error'])

    def test_an_empty_catalogue_is_rejected(self):
        res = self.client.post('/api/regions/aws', json={'doc': {'regions': []}})
        self.assertEqual(res.status_code, 400)
        self.assertIn('empty', res.get_json()['error'])

    def test_a_malformed_body_is_rejected(self):
        self.assertEqual(self.client.post('/api/regions/aws', json={'nope': 1}).status_code, 400)

    def test_the_comment_block_survives_an_edit_from_the_browser(self):
        # The browser only sends what it edits; everything else comes off disk.
        doc = self.client.get('/api/regions/aws').get_json()['doc']
        self.client.post('/api/regions/aws', json={'doc': {'regions': doc['regions']}})
        self.assertIn('_comment', self.read('aws'))
        self.assertEqual(self.read('aws')['default_oci_region'], 'us-ashburn-1')

    def test_a_saved_region_reaches_the_cloud_page(self):
        # The point of the editor: no restart, and the dropdown picks it up.
        doc = self.client.get('/api/regions/gcp').get_json()['doc']
        doc['regions'].append({'region': 'test-region-7', 'label': 'Test Seven',
                               'zones': ['test-zone-7'], 'status': 'live'})
        self.client.post('/api/regions/gcp', json={'doc': doc})
        html = self.client.get('/gcp').get_data(as_text=True)
        self.assertIn('test-region-7', html)
        self.assertIn('test-zone-7', html)


class TestRegionEditorPage(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_the_page_renders_with_a_tab_per_cloud(self):
        html = self.client.get('/regions').get_data(as_text=True)
        for cloud in regions.CLOUDS:
            self.assertIn(f'data-cloud="{cloud}"', html)

    def test_the_page_is_not_cacheable(self):
        # Same rule as the product pages: a stale catalogue editor would show
        # regions that are no longer there.
        res = self.client.get('/regions')
        self.assertIn('no-store', res.headers.get('Cache-Control', ''))

    def test_home_links_to_it(self):
        self.assertIn('href="/regions"', self.client.get('/').get_data(as_text=True))


class TestEditsReachEveryWorker(RegionEditorBase):
    """Gunicorn runs four workers, each with its own cache. A save lands in one
    of them; the rest must still see it, so the cache follows the file."""

    def test_a_write_from_another_process_is_picked_up(self):
        self.assertNotIn('euw3-az9', regions.zone_map('aws')['eu-west-3'])
        doc = self.read('aws')
        next(r for r in doc['regions'] if r['region'] == 'eu-west-3')['zones'].append('euw3-az9')
        path = self.tmp / 'aws_regions.json'
        path.write_text(json.dumps(doc), encoding='utf-8')
        # Force a distinct mtime: some filesystems tick coarsely.
        st = os.stat(path)
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        self.assertIn('euw3-az9', regions.zone_map('aws')['eu-west-3'])


class TestGeneratedZonesFollowTheRegion(RegionEditorBase):
    """A blank AZ used to become the literal use1-az6 whatever the region."""

    def _tfvars(self, **kw):
        from clouds.aws.generator import generate_aws_tf
        net = {'module_name': 'n', 'client_subnet_cidr': '10.0.0.0/24',
               'backup_subnet_cidr': '10.0.1.0/24', **kw}
        return generate_aws_tf({'aws_networks': [net],
                                'aws_infras': [{'module_name': 'i', **kw}]})['terraform.auto.tfvars']

    def test_blank_az_takes_the_regions_first_zone(self):
        out = self._tfvars(region='eu-west-2')
        self.assertIn('"euw2-az1"', out)
        self.assertNotIn('use1-az6', out)

    def test_blank_az_follows_an_edited_catalogue(self):
        doc = self.read('aws')
        next(r for r in doc['regions'] if r['region'] == 'eu-west-2')['zones'] = ['euw2-az3']
        regions.save('aws', doc)
        self.assertIn('"euw2-az3"', self._tfvars(region='eu-west-2'))

    def test_no_region_keeps_the_old_default(self):
        self.assertIn('"use1-az6"', self._tfvars())

    def test_an_explicit_az_is_never_replaced(self):
        out = self._tfvars(region='eu-west-2', availability_zone_id='euw2-az3')
        self.assertIn('"euw2-az3"', out)
        self.assertNotIn('euw2-az1', out)

    def test_tfvars_region_is_the_networks_not_the_infras(self):
        from clouds.aws.generator import generate_aws_tf
        files = generate_aws_tf({
            'aws_networks': [{'module_name': 'n', 'region': 'us-east-1'}],
            'aws_infras':   [{'module_name': 'i', 'region': 'eu-west-2'}]})
        self.assertIn('aws_region = "us-east-1"', files['terraform.auto.tfvars'])


class TestAzMustBelongToRegion(unittest.TestCase):

    def _zone_errors(self, az, region):
        net = {'module_name': 'n', 'display_name': 'x', 'region': region,
               'availability_zone_id': az, 'client_subnet_cidr': '10.0.0.0/24',
               'backup_subnet_cidr': '10.0.1.0/24'}
        r = app.test_client().post('/api/validate',
                                   json={'cloud': 'aws', 'tab': 0, 'aws_networks': [net]})
        return json.dumps(r.get_json())

    def test_az_from_another_region_is_rejected(self):
        self.assertIn('use1-az6 is in us-east-1', self._zone_errors('use1-az6', 'eu-west-2'))

    def test_az_in_its_own_region_passes(self):
        self.assertNotIn('availability_zone_id', self._zone_errors('euw2-az1', 'eu-west-2'))

    def test_az_not_in_the_catalogue_is_allowed_as_custom(self):
        self.assertNotIn('availability_zone_id', self._zone_errors('euw2-az9', 'eu-west-2'))


if __name__ == '__main__':
    unittest.main()
