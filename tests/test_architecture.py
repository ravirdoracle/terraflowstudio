"""Dependency rules between packages.

The point of the split is that a change to one cloud cannot reach another. These
tests fail if that stops being true, which is cheaper than discovering it when an
AWS edit breaks GCP output.

    core            <- no dependencies on oci or any cloud
      ^
    oci             <- depends on core only
      ^
    clouds/*        <- each cloud depends on core + oci, never on another cloud
"""
import ast
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT))

CLOUDS = ('aws', 'gcp', 'azure')


def _imports(path):
    """Top-level module names imported by a file, from real AST rather than grep."""
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:                     # relative import: same package
                names.add('.' * node.level + (node.module or ''))
            elif node.module:
                names.add(node.module.split('.')[0])
    return names


def _py_files(*parts):
    return sorted(p for p in (ROOT.joinpath(*parts)).rglob('*.py')
                  if '__pycache__' not in p.parts)


class TestCoreIsIndependent(unittest.TestCase):

    def test_core_imports_no_oci(self):
        for f in _py_files('core'):
            self.assertNotIn('oci', _imports(f), f'{f.name} imports oci')

    def test_core_imports_no_cloud(self):
        for f in _py_files('core'):
            imported = _imports(f)
            for cloud in CLOUDS:
                self.assertNotIn(f'clouds.{cloud}', imported, f'{f.name} imports {cloud}')

    def test_core_does_not_import_app(self):
        for f in _py_files('core'):
            self.assertNotIn('app', _imports(f), f'{f.name} imports app')


class TestOciIsIndependentOfClouds(unittest.TestCase):
    """OCI sits below the clouds: shared by all three, coupled to none."""

    def test_oci_imports_no_cloud_module(self):
        for f in _py_files('oci'):
            src = f.read_text(encoding='utf-8')
            for cloud in CLOUDS:
                self.assertNotIn(f'clouds.{cloud}', src, f'{f.name} imports clouds.{cloud}')

    def test_oci_renders_no_cloud_named_template(self):
        # The Data Guard templates were once called aws_dg_* despite containing
        # only oci_core_* resources. Renaming them is only durable if nothing
        # reintroduces a cloud-prefixed template path.
        #
        # Deliberately narrow: this checks render_tf() targets, not every string.
        # The <cloud>_oci_databases and <cloud>_dg_* payload keys are accepted
        # back-compat aliases and must not trip this.
        for f in _py_files('oci'):
            tree = ast.parse(f.read_text(encoding='utf-8'), filename=str(f))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and getattr(node.func, 'id', None) == 'render_tf'
                        and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    tmpl = node.args[0].value
                    for cloud in CLOUDS:
                        self.assertFalse(
                            tmpl.startswith(f'{cloud}_'),
                            f'{f.name} renders {cloud}-named template {tmpl!r}')

    def test_oci_templates_exist_under_oci_prefix(self):
        tf = ROOT / 'oci' / 'templates'
        for d in ('oci_dg_multi_az', 'oci_dg_cross_region'):
            self.assertTrue((tf / d).is_dir(), f'missing oci/templates/{d}')
        for cloud in CLOUDS:
            for d in (f'{cloud}_dg_multi_az', f'{cloud}_dg_cross_region'):
                self.assertFalse((tf / d).exists(), f'{d} should have been renamed')

    def test_dg_templates_declare_only_the_oci_provider(self):
        tf = ROOT / 'oci' / 'templates'
        for d in ('oci_dg_multi_az', 'oci_dg_cross_region'):
            main = tf / d / 'main.tf.j2'
            if not main.exists():
                continue
            src = main.read_text(encoding='utf-8')
            self.assertIn('oracle/oci', src, d)
            self.assertNotIn('hashicorp/aws', src, d)
            self.assertNotIn('hashicorp/google', src, d)
            self.assertNotIn('hashicorp/azurerm', src, d)


class TestCloudsDoNotImportEachOther(unittest.TestCase):

    def test_no_cross_cloud_imports(self):
        for cloud in CLOUDS:
            for f in _py_files('clouds', cloud):
                src = f.read_text(encoding='utf-8')
                for other in CLOUDS:
                    if other == cloud:
                        continue
                    self.assertNotIn(f'clouds.{other}', src,
                                     f'clouds/{cloud}/{f.name} imports {other}')

    def test_clouds_reach_oci_through_the_package(self):
        # Importing oci.database / oci.dataguard directly bypasses the declared
        # surface in oci/__init__.py, which is what keeps the contract visible.
        for cloud in CLOUDS:
            src = (ROOT / 'clouds' / cloud / 'generator.py').read_text(encoding='utf-8')
            self.assertNotIn('from oci.database import', src, cloud)
            self.assertNotIn('from oci.dataguard import', src, cloud)


class TestCloudPackagesAreIsolated(unittest.TestCase):
    """clouds/<cloud>/ owns that cloud's validation rules and provider schema."""

    def test_package_exists_per_cloud(self):
        for cloud in CLOUDS:
            pkg = ROOT / 'clouds' / cloud
            for f in ('validator.py', 'schema.py', 'generator.py', 'selftest.py',
                      'routes.py'):
                self.assertTrue((pkg / f).is_file(), f'{cloud}/{f}')
            self.assertTrue((pkg / 'templates').is_dir(), f'{cloud}/templates')

    def test_no_cross_cloud_imports(self):
        for cloud in CLOUDS:
            for f in _py_files('clouds', cloud):
                src = f.read_text(encoding='utf-8')
                for other in CLOUDS:
                    if other == cloud:
                        continue
                    self.assertNotIn(f'clouds.{other}', src,
                                     f'clouds/{cloud}/{f.name} reaches into {other}')

    def test_cloud_packages_do_not_import_app(self):
        # Validation used to live in app.py. Importing back into it would
        # reintroduce the coupling this move removed, and create a cycle.
        for cloud in CLOUDS:
            for f in _py_files('clouds', cloud):
                self.assertNotIn('app', _imports(f), f'clouds/{cloud}/{f.name} imports app')

    def test_validators_expose_a_uniform_entry_point(self):
        import importlib
        for cloud in CLOUDS:
            mod = importlib.import_module(f'clouds.{cloud}.validator')
            self.assertTrue(callable(getattr(mod, 'validate', None)),
                            f'clouds/{cloud}/validator.py has no validate()')

    def test_validate_reports_errors_by_module(self):
        # Contract the /api/validate route depends on: errors is populated as
        # {module_name: {field: message}} and nothing is returned.
        import importlib
        for cloud in CLOUDS:
            mod = importlib.import_module(f'clouds.{cloud}.validator')
            errors = {}
            self.assertIsNone(mod.validate({'tab': -1}, errors), cloud)
            self.assertEqual(errors, {}, f'{cloud} invented errors for an unknown tab')

    def test_schemas_do_not_collide_across_clouds(self):
        # tf_validator merges these into one flat dict, which is only
        # unambiguous while the resource-type names stay disjoint.
        from clouds.aws.schema import AWS_SCHEMAS
        from clouds.gcp.schema import GCP_SCHEMAS
        from clouds.azure.schema import AZURE_SCHEMAS
        from oci.schema import OCI_SCHEMAS
        pairs = (('aws', AWS_SCHEMAS), ('gcp', GCP_SCHEMAS), ('azure', AZURE_SCHEMAS),
                 ('oci', OCI_SCHEMAS))
        for i, (a, sa) in enumerate(pairs):
            for b, sb in pairs[i + 1:]:
                self.assertEqual(set(sa) & set(sb), set(),
                                 f'{a} and {b} declare the same resource type')


class TestRoutesAreOwnedByTheirCloud(unittest.TestCase):
    """Page routes live in the cloud package, registered as blueprints."""

    PAGES = {'/aws': 'aws.page', '/gcp': 'gcp.page', '/azure': 'azure.page',
             '/oci': 'oci_pages.db_page', '/dg': 'oci_pages.dg_page'}

    def test_pages_are_served_by_blueprints(self):
        from app import app
        rules = {str(r): r.endpoint for r in app.url_map.iter_rules()}
        for path, endpoint in self.PAGES.items():
            self.assertEqual(rules.get(path), endpoint, path)

    def test_app_defines_no_cloud_page_route(self):
        # A route added back into app.py would work, but puts cloud knowledge
        # back where this refactor removed it.
        src = (ROOT / 'app.py').read_text(encoding='utf-8')
        for path in self.PAGES:
            self.assertNotIn(f"@app.route('{path}')", src,
                             f'{path} is defined in app.py again')

    def test_all_pages_render(self):
        from app import app
        client = app.test_client()
        for path in self.PAGES:
            self.assertEqual(client.get(path).status_code, 200, path)

    def test_pages_are_not_cacheable(self):
        # These embed generated state; a cached copy shows a config the server
        # would no longer produce.
        from app import app
        client = app.test_client()
        for path in self.PAGES:
            headers = client.get(path).headers
            self.assertIn('no-store', headers.get('Cache-Control', ''), path)

    def test_route_modules_are_not_imported_by_package_init(self):
        # Importing a cloud for its validator must not drag in Flask. Checked via
        # AST rather than a substring, so the docstring saying so does not count.
        for pkg in ('clouds/aws', 'clouds/gcp', 'clouds/azure', 'oci'):
            init = ROOT / pkg / '__init__.py'
            tree = ast.parse(init.read_text(encoding='utf-8'), filename=str(init))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, 'routes',
                                        f'{pkg}/__init__.py imports routes')
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertNotIn('routes', a.name.split('.'),
                                         f'{pkg}/__init__.py imports routes')


class TestCloudRegistry(unittest.TestCase):
    """One table replaces the if/elif chains that used to select a cloud."""

    def test_every_cloud_has_a_generator_and_zip_name(self):
        from clouds.registry import REGISTRY
        for name, spec in REGISTRY.items():
            self.assertTrue(callable(spec.generate), name)
            self.assertTrue(spec.zip_name, name)
            self.assertEqual(spec.name, name)

    def test_hyperscalers_and_dg_have_validators_and_oci_does_not(self):
        # dg gained server rules with its hub-and-spoke VCN pairs: their names are
        # for_each keys and their CIDRs must not collide.
        from clouds.registry import REGISTRY
        for name in CLOUDS + ('dg',):
            self.assertIsNotNone(REGISTRY[name].validate, name)
        self.assertIsNone(REGISTRY['oci'].validate, 'oci is validated client-side only')

    def test_unknown_cloud_falls_back_to_aws(self):
        from clouds import registry
        self.assertEqual(registry.get('no-such-cloud').name, 'aws')
        self.assertEqual(registry.get(None).name, 'aws')

    def test_zip_names_are_unique(self):
        from clouds.registry import REGISTRY
        names = [s.zip_name for s in REGISTRY.values()]
        self.assertEqual(len(names), len(set(names)))

    def test_no_cloud_package_imports_the_registry(self):
        # The registry imports the clouds. The reverse would be a cycle, and
        # would let one cloud reach another through it.
        for cloud in CLOUDS:
            for f in _py_files('clouds', cloud):
                self.assertNotIn('registry', f.read_text(encoding='utf-8'),
                                 f'clouds/{cloud}/{f.name} imports the registry')

    def test_generation_and_download_use_the_registry(self):
        # These two were if/elif chains over every cloud. Other branches remain
        # in api_test, api_llm_ask, api_ai_security_review and _collect_cidrs -
        # those are scenario and prompt building rather than cloud dispatch, and
        # are a later stage. This test pins the two that are done so they cannot
        # quietly regrow.
        src = (ROOT / 'app.py').read_text(encoding='utf-8')
        gen = src[src.index('def generate_all('):src.index('#  ROUTES')]
        self.assertIn('cloud_registry.get', gen)
        for cloud in CLOUDS + ('dg', 'oci'):
            self.assertNotIn(f"cloud == '{cloud}'", gen,
                             f'generate_all still branches on {cloud}')

        dl = src[src.index('def api_download('):]
        dl = dl[:dl.index('\n@app.route')]
        self.assertIn('cloud_registry.get(cloud).zip_name', dl)
        self.assertNotIn('terraflow-studio-', dl,
                         'api_download still hardcodes zip names')


class TestTemplatesAreOwnedByTheirPackage(unittest.TestCase):
    """Each package renders only its own templates, via its own Jinja loader.

    A single shared search path would let one cloud render another's template and
    let the two drift into each other. Separate loaders make that a
    TemplateNotFound at the first attempt.
    """

    OWNERS = {'clouds/aws': 'aws_', 'clouds/gcp': 'gcp_',
              'clouds/azure': 'azure_', 'oci': 'oci_'}

    def test_every_package_has_its_own_template_dir(self):
        for pkg in self.OWNERS:
            self.assertTrue((ROOT / pkg / 'templates').is_dir(), pkg)

    def test_template_dirs_carry_their_owner_prefix(self):
        for pkg, prefix in self.OWNERS.items():
            for d in (ROOT / pkg / 'templates').iterdir():
                if d.is_dir():
                    self.assertTrue(d.name.startswith(prefix),
                                    f'{pkg}/templates/{d.name} is not {prefix}*')

    def test_shared_template_tree_is_gone(self):
        # Everything moved into a package; a file left behind would be rendered
        # by nobody and silently rot.
        self.assertFalse((ROOT / 'templates' / 'tf').exists(),
                         'templates/tf still exists')

    def test_a_package_cannot_render_another_packages_template(self):
        from clouds.aws.generator import render_tf as aws_render
        from clouds.gcp.generator import render_tf as gcp_render
        from jinja2 import TemplateNotFound
        with self.assertRaises(TemplateNotFound):
            aws_render('gcp_root/main.tf.j2')
        with self.assertRaises(TemplateNotFound):
            gcp_render('aws_root/main.tf.j2')

    def test_every_rendered_template_exists_in_the_owning_package(self):
        # Catches a render_tf() call naming a template that moved elsewhere -
        # which would otherwise only surface when that code path runs.
        import re
        for pkg, prefix in self.OWNERS.items():
            root = ROOT / pkg / 'templates'
            for f in _py_files(*pkg.split('/')):
                for tmpl in re.findall(r"render_tf\(\s*'([^']+)'", f.read_text(encoding='utf-8')):
                    self.assertTrue((root / tmpl).is_file(),
                                    f'{f.name} renders {tmpl}, missing from {pkg}/templates')


class TestSecurityReviewIsPerCloud(unittest.TestCase):
    """CIDR collection and the prompt's provider line come from the cloud package.

    Both used to branch aws/else, so Azure was handed the GCP collector - which
    looks for gcp_networks an Azure payload does not have - and the AWS prompt
    line, which names a field azurerm has no equivalent of. Azure configs got no
    overlap findings at all, in a review whose whole point is that those findings
    are deterministic rather than guessed at.
    """

    AZURE = {
        'cloud': 'azure',
        'azure_vnets': [{'module_name': 'v1', 'address_space': '10.0.0.0/16',
                         'subnet_address_prefix': '10.0.1.0/24'}],
        'azure_clusters': [{'module_name': 'c1',
                            'backup_subnet_cidr': '192.168.252.0/22'}],
    }

    def test_every_cloud_supplies_a_collector(self):
        from clouds.registry import REGISTRY
        for name, spec in REGISTRY.items():
            self.assertIsInstance(spec.collect_cidrs({}), list, name)

    def test_azure_collects_its_cidrs(self):
        from app import _collect_cidrs
        labels = dict(_collect_cidrs(self.AZURE))
        self.assertIn('v1.subnet_address_prefix', labels)
        self.assertIn('c1.backup_subnet_cidr', labels)

    def test_valid_azure_config_reports_nothing(self):
        # address_space is excluded on purpose: subnets belong inside it, so
        # including it would flag every correct config as a high-severity overlap.
        from app import _check_cidr_overlaps
        self.assertEqual(_check_cidr_overlaps(self.AZURE), [])

    def test_azure_backup_range_clashing_with_the_subnet_is_caught(self):
        from app import _check_cidr_overlaps
        clash = {**self.AZURE,
                 'azure_clusters': [{'module_name': 'c1',
                                     'backup_subnet_cidr': '10.0.1.128/25'}]}
        found = _check_cidr_overlaps(clash)
        self.assertTrue(found)
        self.assertEqual(found[0]['severity'], 'high')

    def test_two_azure_clusters_sharing_a_backup_range_is_caught(self):
        from app import _check_cidr_overlaps
        shared = {**self.AZURE, 'azure_clusters': [
            {'module_name': 'c1', 'backup_subnet_cidr': '192.168.252.0/22'},
            {'module_name': 'c2', 'backup_subnet_cidr': '192.168.252.0/22'},
        ]}
        self.assertTrue(_check_cidr_overlaps(shared))

    def test_aws_and_gcp_collection_is_unchanged(self):
        from app import _collect_cidrs
        aws = {'cloud': 'aws', 'aws_networks': [
            {'module_name': 'n1', 'client_subnet_cidr': '10.2.0.0/24',
             'backup_subnet_cidr': '10.2.1.0/24'}]}
        self.assertEqual(_collect_cidrs(aws),
                         [('n1.client_subnet_cidr', '10.2.0.0/24'),
                          ('n1.backup_subnet_cidr', '10.2.1.0/24')])
        gcp = {'cloud': 'gcp', 'gcp_networks': [
            {'module_name': 'g1', 'subnets': [
                {'cidr_range': '10.3.0.0/24', 'purpose': 'CLIENT_SUBNET'}]}]}
        self.assertEqual(_collect_cidrs(gcp),
                         [('g1.subnet[0](CLIENT_SUBNET).cidr_range', '10.3.0.0/24')])

    def test_each_cloud_has_its_own_prompt_line(self):
        from clouds.registry import REGISTRY
        lines = {c: REGISTRY[c].security_prompt_line for c in CLOUDS}
        self.assertEqual(len(set(lines.values())), len(CLOUDS),
                         'two clouds share a security-review prompt line')
        for cloud, line in lines.items():
            self.assertTrue(line.endswith('\n'), f'{cloud} line must end with a newline')
        # The specific mix-up that prompted this: Azure naming an AWS-only field.
        self.assertNotIn('delete_associated_resources', lines['azure'])

    def test_oci_products_collect_nothing(self):
        from clouds.registry import REGISTRY
        for name in ('oci', 'dg'):
            self.assertEqual(REGISTRY[name].collect_cidrs({'cloud': name}), [])
            self.assertEqual(REGISTRY[name].security_prompt_line, '')


class TestPagesAreOwnedByTheirPackage(unittest.TestCase):
    """Each product page lives with the route that serves it.

    Two Jinja trees per package, kept apart because they render different
    languages for different consumers:

        <pkg>/templates/  Terraform, via core.helpers.make_renderer
        <pkg>/pages/      HTML, via Flask's blueprint template_folder
    """

    OWNERS = {'clouds/aws': ['aws.html'], 'clouds/gcp': ['gcp.html'],
              'clouds/azure': ['azure.html'],
              'oci': ['oci_db.html', 'dg.html']}
    #: Pages that belong to no cloud - the chooser, tools and settings.
    SHARED = ('home.html', 'cidr.html', 'config.html', 'hub.html', 'rag.html')

    def test_each_package_holds_its_own_pages(self):
        for pkg, pages in self.OWNERS.items():
            for page in pages:
                self.assertTrue((ROOT / pkg / 'pages' / page).is_file(),
                                f'{pkg}/pages/{page}')

    def test_cloud_pages_are_gone_from_the_shared_tree(self):
        for pages in self.OWNERS.values():
            for page in pages:
                self.assertFalse((ROOT / 'templates' / page).exists(),
                                 f'templates/{page} should have moved')

    def test_shared_pages_stay_shared(self):
        # These serve no single cloud; moving them into one would be wrong.
        for page in self.SHARED:
            self.assertTrue((ROOT / 'templates' / page).is_file(), page)

    def test_pages_and_terraform_templates_stay_separate(self):
        # A .html under templates/ would be rendered as Terraform; a .j2 under
        # pages/ would be served as a page. Both are silent mistakes.
        for pkg in self.OWNERS:
            tf = ROOT / pkg / 'templates'
            if tf.is_dir():
                self.assertEqual([p.name for p in tf.rglob('*.html')], [], f'{pkg}/templates')
            pages = ROOT / pkg / 'pages'
            self.assertEqual([p.name for p in pages.rglob('*.j2')], [], f'{pkg}/pages')

    def test_blueprints_declare_their_template_folder(self):
        # Without template_folder the page is only found if it is still in the
        # shared tree, so this is what makes the move work.
        import importlib
        for mod_name in ('clouds.aws.routes', 'clouds.gcp.routes',
                         'clouds.azure.routes', 'oci.routes'):
            mod = importlib.import_module(mod_name)
            self.assertEqual(mod.bp.template_folder, 'pages', mod_name)

    def test_every_page_renders(self):
        from app import app
        client = app.test_client()
        for path in ('/', '/aws', '/gcp', '/azure', '/oci', '/dg',
                     '/cidr', '/hub', '/rag', '/config'):
            self.assertEqual(client.get(path).status_code, 200, path)

    def test_pages_are_standalone(self):
        # None of them extends or includes another, which is why they could be
        # split across packages at all. If that changes, the shared parent has to
        # stay reachable from every blueprint.
        import re
        for pkg, pages in self.OWNERS.items():
            for page in pages:
                src = (ROOT / pkg / 'pages' / page).read_text(encoding='utf-8')
                self.assertIsNone(re.search(r'\{%\s*(extends|include)\s', src),
                                  f'{pkg}/pages/{page} now depends on another template')

    def test_panel_resizer_is_shared(self):
        # Each page used to carry its own copy of the form/output divider. The
        # Data Guard and OCI DB copies stored "NaN" on a plain click, which broke
        # the grid on every page (output dropped below the form). One copy now,
        # in static/panel-resizer.js; no page may grow its own again.
        checked = 0
        for pkg, pages in self.OWNERS.items():
            for page in pages:
                src = (ROOT / pkg / 'pages' / page).read_text(encoding='utf-8')
                if 'id="panel-resizer"' not in src:
                    continue
                checked += 1
                with self.subTest(page=f'{pkg}/pages/{page}'):
                    self.assertIn("filename='panel-resizer.js'", src)
                    self.assertNotIn('tf-rhs-width', src, 'page has its own resizer copy again')
        # aws, gcp, azure, oci_db, dg — fail rather than pass by checking nothing.
        self.assertGreaterEqual(checked, 5)


class TestOciPublicSurface(unittest.TestCase):
    """oci/__init__ is the contract the clouds are allowed to depend on."""

    def test_entry_points_exported(self):
        import oci
        for name in ('generate_oci_db_tf', 'generate_oci_dg_tf'):
            self.assertTrue(hasattr(oci, name), name)

    def test_everything_in_all_is_importable(self):
        import oci
        for name in oci.__all__:
            self.assertTrue(hasattr(oci, name), f'__all__ lists missing {name}')

    def test_clouds_only_use_exported_names(self):
        import oci
        exported = set(oci.__all__)
        for cloud in CLOUDS:
            src = (ROOT / 'clouds' / cloud / 'generator.py').read_text(encoding='utf-8')
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == 'oci':
                    for alias in node.names:
                        self.assertIn(alias.name, exported,
                                      f'{cloud}_gen imports oci.{alias.name}, '
                                      'which is not in oci.__all__')


class TestDataGuardKeyAliases(unittest.TestCase):
    """Canonical payload keys, with the old cloud-prefixed ones still accepted."""

    def _entry(self):
        # oci_region is what _dg_maz_filled() checks; without it the generator
        # returns {} and an alias comparison would pass by comparing nothing.
        return {'module_name': 'dg1', 'display_name': 'dg',
                'oci_region': 'us-ashburn-1'}

    def test_canonical_key_accepted(self):
        from oci import generate_oci_dg_tf
        files = generate_oci_dg_tf({'dg_multi_az': [self._entry()]})
        self.assertGreater(len(files), 0)

    def test_cloud_prefixed_aliases_still_accepted(self):
        from oci import generate_oci_dg_tf
        canonical = generate_oci_dg_tf({'dg_multi_az': [self._entry()]})
        self.assertGreater(len(canonical), 0, 'fixture produced no files')
        for prefix in ('aws_', 'gcp_', 'azure_'):
            aliased = generate_oci_dg_tf({f'{prefix}dg_multi_az': [self._entry()]})
            self.assertEqual(aliased, canonical, prefix)

    def test_canonical_key_wins_over_alias(self):
        from oci import generate_oci_dg_tf
        both = generate_oci_dg_tf({
            'dg_multi_az':     [dict(self._entry(), module_name='canonical')],
            'aws_dg_multi_az': [dict(self._entry(), module_name='legacy')],
        })
        self.assertTrue(any('canonical' in k for k in both))
        self.assertFalse(any('legacy' in k for k in both))

    def test_empty_payload_produces_nothing(self):
        from oci import generate_oci_dg_tf
        self.assertEqual(generate_oci_dg_tf({}), {})


if __name__ == '__main__':
    unittest.main()
