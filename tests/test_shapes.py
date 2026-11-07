"""Exadata shape catalogue — config/<cloud>_shapes.json.

Mirrors tests/test_regions.py: the shape catalogue is the same kind of object as
the region catalogue, and both go through catalogue.py.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import shapes
from shapes import ShapeConfigError
from app import app


# ══════════════════════════════════════════════════════════════════════════════
#  Loading
# ══════════════════════════════════════════════════════════════════════════════

class TestCataloguesLoad(unittest.TestCase):

    def test_every_cloud_has_a_catalogue(self):
        for cloud in shapes.CLOUDS:
            self.assertTrue(shapes.path_for(cloud).exists(), cloud)

    def test_every_catalogue_parses(self):
        for cloud in shapes.CLOUDS:
            self.assertTrue(shapes.shapes(cloud), cloud)

    def test_shape_values_are_unique_per_cloud(self):
        for cloud in shapes.CLOUDS:
            names = shapes.names(cloud)
            self.assertEqual(len(names), len(set(names)), cloud)

    def test_every_entry_has_the_core_fields(self):
        for cloud in shapes.CLOUDS:
            for entry in shapes.shapes(cloud):
                for field in shapes.CORE_FIELDS:
                    self.assertIn(field, entry, f'{cloud}: {entry}')

    def test_default_shape_is_one_of_the_listed_shapes(self):
        for cloud in shapes.CLOUDS:
            self.assertIn(shapes.default_shape(cloud), shapes.names(cloud), cloud)

    def test_unknown_cloud_raises(self):
        with self.assertRaises(ShapeConfigError):
            shapes.load('nope')

    # The three pages used to carry three hand-maintained <option> lists that had
    # drifted: AWS and GCP offered X10M, Azure did not. One catalogue per cloud
    # does not force them to agree, but it does make a difference visible.
    def test_x10m_is_now_present_for_every_cloud(self):
        for cloud in shapes.CLOUDS:
            self.assertIn('Exadata.X10M', shapes.names(cloud), cloud)


# ══════════════════════════════════════════════════════════════════════════════
#  Server types
# ══════════════════════════════════════════════════════════════════════════════

class TestServerTypes(unittest.TestCase):

    def test_aws_offers_server_models_for_every_shape(self):
        for shape, models in shapes.db_server_types('aws').items():
            self.assertTrue(models, shape)
        for shape, models in shapes.storage_server_types('aws').items():
            self.assertTrue(models, shape)

    def test_azure_offers_server_models_for_every_shape(self):
        for shape, models in shapes.db_server_types('azure').items():
            self.assertTrue(models, shape)

    def test_gcp_carries_no_server_models(self):
        """google_oracle_database_cloud_exadata_infrastructure has no such input —
        it reports db_server_version / storage_server_version as computed only."""
        for models in shapes.db_server_types('gcp').values():
            self.assertEqual(models, [])
        for models in shapes.storage_server_types('gcp').values():
            self.assertEqual(models, [])

    def test_gcp_spec_offers_no_server_type_columns(self):
        self.assertEqual(shapes.field_spec('gcp')['list_fields'], [])

    def test_x11m_requires_server_types_on_aws_and_azure(self):
        """A constraint of the X11M generation, not of one cloud's provider."""
        for cloud in ('aws', 'azure'):
            self.assertIn('Exadata.X11M', shapes.requires_server_types(cloud), cloud)

    def test_older_shapes_do_not_require_server_types(self):
        for cloud in ('aws', 'azure'):
            self.assertNotIn('Exadata.X9M', shapes.requires_server_types(cloud), cloud)

    def test_storage_models_cover_high_capacity_and_extreme_flash(self):
        for shape, models in shapes.storage_server_types('aws').items():
            self.assertTrue(any(m.endswith('-HC') for m in models), shape)


# ══════════════════════════════════════════════════════════════════════════════
#  Validation
# ══════════════════════════════════════════════════════════════════════════════

class TestValidationRejectsBadConfig(unittest.TestCase):

    def _err(self, doc):
        with self.assertRaises(ShapeConfigError) as ctx:
            shapes.validate('aws', doc)
        return str(ctx.exception)

    def _ok_entry(self, **kw):
        return {'shape': 'Exadata.X9M', 'label': 'X9M', 'status': 'live', **kw}

    def test_missing_shapes_list(self):
        self.assertIn('shapes', self._err({}))

    def test_empty_shapes_list(self):
        self.assertIn('empty', self._err({'shapes': []}))

    def test_missing_core_field(self):
        self.assertIn('label', self._err({'shapes': [{'shape': 'X', 'status': 'live'}]}))

    def test_duplicate_shape(self):
        doc = {'shapes': [self._ok_entry(), self._ok_entry()]}
        self.assertIn('duplicate', self._err(doc))

    def test_bad_status(self):
        doc = {'shapes': [self._ok_entry(status='maybe')]}
        self.assertIn('status', self._err(doc))

    def test_server_types_must_be_a_list(self):
        doc = {'shapes': [self._ok_entry(database_server_types='X9M')]}
        self.assertIn('must be a list', self._err(doc))

    def test_required_without_any_models_is_rejected(self):
        """A required dropdown with nothing in it is a dead end on the form."""
        doc = {'shapes': [self._ok_entry(server_types_required=True,
                                         database_server_types=[],
                                         storage_server_types=[])]}
        self.assertIn('server_types_required', self._err(doc))

    def test_default_shape_must_exist(self):
        doc = {'default_shape': 'Exadata.X99M', 'shapes': [self._ok_entry()]}
        self.assertIn('default_shape', self._err(doc))

    def test_a_valid_document_passes(self):
        doc = {'default_shape': 'Exadata.X9M',
               'shapes': [self._ok_entry(database_server_types=['X9M'],
                                         storage_server_types=['X9M-HC'],
                                         server_types_required=True)]}
        self.assertEqual(shapes.validate('aws', doc), doc)


# ══════════════════════════════════════════════════════════════════════════════
#  Writer
# ══════════════════════════════════════════════════════════════════════════════

class ShapeEditorBase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_dir = shapes.CONFIG_DIR
        tmp = Path(self._tmp.name)
        for cloud in shapes.CLOUDS:
            src = self._orig_dir / f'{cloud}_shapes.json'
            (tmp / f'{cloud}_shapes.json').write_text(
                src.read_text(encoding='utf-8'), encoding='utf-8')
        shapes.CONFIG_DIR = tmp
        shapes._cache.clear()
        self.tmp = tmp

    def tearDown(self):
        shapes.CONFIG_DIR = self._orig_dir
        shapes._cache.clear()
        self._tmp.cleanup()

    def read(self, cloud):
        return json.loads((self.tmp / f'{cloud}_shapes.json').read_text(encoding='utf-8'))

    def raw(self, cloud):
        return (self.tmp / f'{cloud}_shapes.json').read_text(encoding='utf-8')


class TestCatalogueWriter(ShapeEditorBase):

    def test_entries_stay_one_line_each(self):
        for cloud in shapes.CLOUDS:
            doc = shapes.load(cloud)
            body = shapes.dumps(cloud, doc)
            entry_lines = [l for l in body.split('\n') if l.strip().startswith('{ "')]
            self.assertEqual(len(entry_lines), len(doc['shapes']), cloud)

    def test_writing_is_idempotent(self):
        for cloud in shapes.CLOUDS:
            shapes.save(cloud, shapes.load(cloud))
            once = self.raw(cloud)
            shapes.save(cloud, shapes.load(cloud))
            self.assertEqual(once, self.raw(cloud), f'{cloud}: second save differs')

    def test_the_hand_written_file_is_already_in_canonical_form(self):
        """A first save from the UI should be a no-op, not a reformat."""
        for cloud in shapes.CLOUDS:
            before = self.raw(cloud)
            shapes.save(cloud, shapes.load(cloud))
            self.assertEqual(before, self.raw(cloud), cloud)

    def test_top_level_keys_survive_a_save(self):
        shapes.save('aws', shapes.load('aws'))
        after = self.read('aws')
        self.assertIn('_comment', after)
        self.assertEqual(after['default_shape'], 'Exadata.X11M')

    def test_a_rejected_save_leaves_the_file_untouched(self):
        before = self.raw('aws')
        doc = shapes.load('aws')
        doc['shapes'][0]['status'] = 'sometimes'
        with self.assertRaises(ShapeConfigError):
            shapes.save('aws', doc)
        self.assertEqual(before, self.raw('aws'))

    def test_saving_refreshes_the_cache(self):
        doc = shapes.load('gcp')
        doc['shapes'].append({'shape': 'Exadata.X12M', 'label': 'X12M', 'status': 'planned'})
        shapes.save('gcp', doc)
        self.assertIn('Exadata.X12M', shapes.names('gcp'))


# ══════════════════════════════════════════════════════════════════════════════
#  API
# ══════════════════════════════════════════════════════════════════════════════

class TestShapeApi(ShapeEditorBase):

    def setUp(self):
        super().setUp()
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_get_returns_doc_and_spec(self):
        for cloud in shapes.CLOUDS:
            d = self.client.get(f'/api/shapes/{cloud}').get_json()
            self.assertIn('shapes', d['doc'])
            self.assertEqual(d['spec']['core'], list(shapes.CORE_FIELDS))

    def test_get_unknown_cloud_is_404(self):
        self.assertEqual(self.client.get('/api/shapes/nope').status_code, 404)

    def test_post_round_trips(self):
        doc = self.client.get('/api/shapes/aws').get_json()['doc']
        # Relative to what the catalogue currently ships: adding a shape to
        # config/aws_shapes.json is a catalogue edit, not a reason for this to fail.
        before = len(doc['shapes'])
        doc['shapes'].append({'shape': 'Exadata.X12M', 'label': 'X12M', 'status': 'planned',
                              'database_server_types': ['X12M'],
                              'storage_server_types': ['X12M-HC'],
                              'server_types_required': False})
        res = self.client.post('/api/shapes/aws', json={'doc': doc})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['n_shapes'], before + 1)
        self.assertIn('Exadata.X12M',
                      [s['shape'] for s in self.client.get('/api/shapes/aws').get_json()['doc']['shapes']])

    def test_post_rejects_a_bad_document_without_writing(self):
        before = self.raw('aws')
        doc = self.client.get('/api/shapes/aws').get_json()['doc']
        doc['shapes'][0]['status'] = 'sometimes'
        res = self.client.post('/api/shapes/aws', json={'doc': doc})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(before, self.raw('aws'))

    def test_post_preserves_the_comment_block(self):
        doc = self.client.get('/api/shapes/aws').get_json()['doc']
        self.client.post('/api/shapes/aws', json={'doc': {'shapes': doc['shapes']}})
        self.assertIn('_comment', self.read('aws'))


# ══════════════════════════════════════════════════════════════════════════════
#  Pages render from the catalogue
# ══════════════════════════════════════════════════════════════════════════════

class TestPagesRenderCatalogue(unittest.TestCase):

    PAGES = {'aws': ('/aws', 'AWS_SHAPES'),
             'azure': ('/azure', 'AZURE_SHAPES'),
             'gcp': ('/gcp', 'GCP_SHAPES')}

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def _html(self, url):
        return self.client.get(url).data.decode('utf-8')

    def test_each_page_injects_its_catalogue(self):
        for cloud, (url, const) in self.PAGES.items():
            self.assertIn(f'const {const} = [', self._html(url), cloud)

    def test_each_page_injects_its_default_shape(self):
        for cloud, (url, const) in self.PAGES.items():
            html = self._html(url)
            self.assertIn(f'"{shapes.default_shape(cloud)}"', html, cloud)

    def test_every_catalogue_shape_reaches_the_page(self):
        for cloud, (url, _) in self.PAGES.items():
            html = self._html(url)
            for name in shapes.names(cloud):
                self.assertIn(name, html, f'{cloud}: {name}')

    def test_no_page_hardcodes_a_shape_option_list(self):
        """The whole point: the <option> lists are gone, not merely in sync."""
        for cloud, (url, _) in self.PAGES.items():
            html = self._html(url)
            self.assertNotIn('<option value="Exadata.', html, cloud)

    def test_pages_load_the_shared_dropdown_helper(self):
        for cloud, (url, _) in self.PAGES.items():
            self.assertIn('shape-select.js', self._html(url), cloud)


class TestCatalogueEditorPage(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_editor_offers_both_catalogues(self):
        html = self.client.get('/regions').data.decode('utf-8')
        self.assertIn('data-cat="regions"', html)
        self.assertIn('data-cat="shapes"', html)

    def test_editor_is_still_served_at_regions(self):
        """The URL people have bookmarked keeps working."""
        self.assertEqual(self.client.get('/regions').status_code, 200)


# ══════════════════════════════════════════════════════════════════════════════
#  Generators take their default from the catalogue
# ══════════════════════════════════════════════════════════════════════════════

class TestGeneratorDefaults(unittest.TestCase):

    def test_aws_infra_defaults_to_the_catalogue_shape(self):
        from clouds.aws.generator import _aws_infra_defaults
        self.assertEqual(_aws_infra_defaults({})['shape'], shapes.default_shape('aws'))

    def test_gcp_infra_defaults_to_the_catalogue_shape(self):
        from clouds.gcp.generator import _gcp_infra_defaults
        self.assertEqual(_gcp_infra_defaults({})['shape'], shapes.default_shape('gcp'))

    def test_azure_infra_defaults_to_the_catalogue_shape(self):
        from clouds.azure.generator import _azure_infra_defaults
        self.assertEqual(_azure_infra_defaults({})['shape'], shapes.default_shape('azure'))


class TestAzureServerTypes(unittest.TestCase):
    """Azure gained the two fields with this change — azurerm supports both."""

    def _gen(self, **kw):
        from clouds.azure.generator import generate_azure_tf
        infra = {'module_name': 'ai', 'name': 'infra', 'display_name': 'Infra',
                 'resource_group_name': 'rg', 'location': 'eastus',
                 'shape': 'Exadata.X11M', **kw}
        return generate_azure_tf({'cloud': 'azure', 'azure_infras': [infra]})

    def test_module_declares_both_variables(self):
        v = self._gen()['modules/ai/variables.tf']
        self.assertIn('variable "database_server_type"', v)
        self.assertIn('variable "storage_server_type"', v)

    def test_empty_values_send_null_not_empty_string(self):
        m = self._gen()['modules/ai/main.tf']
        self.assertIn('var.database_server_type != "" ? var.database_server_type : null', m)

    def test_values_reach_the_root_and_tfvars(self):
        f = self._gen(database_server_type='X11M', storage_server_type='X11M-HC')
        self.assertIn('ai_database_server_type = "X11M"', f['terraform.auto.tfvars'])
        self.assertIn('database_server_type = var.ai_database_server_type', f['main.tf'])

    def test_absent_values_add_nothing_to_the_root(self):
        f = self._gen()
        self.assertNotIn('ai_database_server_type', f['terraform.auto.tfvars'])
        self.assertNotIn('ai_database_server_type', f['main.tf'])

    def test_the_module_block_stays_terraform_fmt_aligned(self):
        """The longer key widens the column, but only when it is emitted."""
        with_types = self._gen(database_server_type='X11M', storage_server_type='X11M-HC')['main.tf']
        self.assertIn('  source               = "./modules/ai"', with_types)
        self.assertIn('  database_server_type = var.ai_database_server_type', with_types)
        without = self._gen()['main.tf']
        self.assertIn('  source              = "./modules/ai"', without)


class TestServerTypesAreRequired(unittest.TestCase):
    """Both server types are required for a shape the catalogue flags.

    Which shapes those are comes from config/<cloud>_shapes.json, so turning the
    rule on or off for a shape is a checkbox in the editor, not a code change.
    """

    CASES = {'aws': (1, 'aws_infras'), 'azure': (21, 'azure_infras')}

    def _errors(self, cloud, **infra):
        import importlib
        mod = importlib.import_module(f'clouds.{cloud}.validator')
        tab, key = self.CASES[cloud]
        base = {'module_name': 'i1', 'display_name': 'd', 'availability_zone_id': 'z',
                'resource_group_name': 'rg', 'location': 'eastus', 'name': 'n',
                'compute_count': 2, 'storage_count': 3}
        errors = {}
        mod.validate({'tab': tab, key: [{**base, **infra}]}, errors)
        return errors.get('i1', {})

    def test_blank_pair_is_rejected_on_a_required_shape(self):
        for cloud in self.CASES:
            errs = self._errors(cloud, shape='Exadata.X11M',
                                database_server_type='', storage_server_type='')
            self.assertIn('database_server_type', errs, cloud)
            self.assertIn('storage_server_type', errs, cloud)

    def test_the_error_names_the_shape(self):
        errs = self._errors('aws', shape='Exadata.X11M',
                            database_server_type='', storage_server_type='')
        self.assertIn('Exadata.X11M', errs['database_server_type'])

    def test_either_one_missing_is_rejected(self):
        for cloud in self.CASES:
            only_db = self._errors(cloud, shape='Exadata.X11M',
                                   database_server_type='X11M', storage_server_type='')
            self.assertNotIn('database_server_type', only_db, cloud)
            self.assertIn('storage_server_type', only_db, cloud)

    def test_a_complete_pair_passes(self):
        for cloud in self.CASES:
            errs = self._errors(cloud, shape='Exadata.X11M',
                                database_server_type='X11M', storage_server_type='X11M-HC')
            self.assertNotIn('database_server_type', errs, cloud)
            self.assertNotIn('storage_server_type', errs, cloud)

    def test_a_shape_that_does_not_require_them_stays_optional(self):
        for cloud in self.CASES:
            errs = self._errors(cloud, shape='Exadata.X9M',
                                database_server_type='', storage_server_type='')
            self.assertNotIn('database_server_type', errs, cloud)
            self.assertNotIn('storage_server_type', errs, cloud)

    def test_an_externally_provisioned_aws_infra_is_exempt(self):
        """Nothing is created, so the creation fields are not validated."""
        errs = self._errors('aws', shape='Exadata.X11M', is_existing=True,
                            existing_id='ocid1.x', database_server_type='',
                            storage_server_type='')
        self.assertNotIn('database_server_type', errs)

    def test_the_rule_survives_an_unreadable_catalogue(self):
        """A broken shapes file must not take payload validation down with it."""
        import clouds.aws.validator as av
        orig = shapes.CONFIG_DIR
        shapes.CONFIG_DIR = Path(tempfile.mkdtemp())
        shapes._cache.clear()
        try:
            errs = self._errors('aws', shape='Exadata.X11M',
                                database_server_type='', storage_server_type='')
            self.assertNotIn('database_server_type', errs)
        finally:
            shapes.CONFIG_DIR = orig
            shapes._cache.clear()

    def test_the_saved_configs_that_this_now_flags(self):
        """8 of the 11 stored AWS infras name X11M with both fields blank.

        They were generating Terraform that AWS documents as invalid. This test
        pins the count so the number moving is a deliberate act, not a surprise.
        """
        import glob, json as _json
        flagged = 0
        for path in glob.glob('data/*/aws.json'):
            with open(path, encoding='utf-8') as fh:
                doc = _json.load(fh)
            for inf in doc.get('aws_infras', []):
                if inf.get('shape') in shapes.requires_server_types('aws') and not (
                        inf.get('database_server_type') and inf.get('storage_server_type')):
                    flagged += 1
        self.assertEqual(flagged, 8)


if __name__ == '__main__':
    unittest.main()
