"""
The standalone blueprints' shared modules are rendered from this app's templates
(scripts/sync_blueprints.py). These tests keep that true.
Run with:  python -m unittest tests/test_blueprint_sync.py
"""
import importlib
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from app import generate_all
import sync_blueprints

CLOUDS = sync_blueprints.CLOUDS

#: Deliberately different from each blueprint.PAYLOAD: more instances, other
#: names and values, the other toolchain.
OTHER = {
    'aws': {'cloud': 'aws', 'iac_tool': 'opentofu',
            'aws_networks': [{'module_name': 'a', 'display_name': 'x', 'sts_access': 'ENABLED'},
                             {'module_name': 'b', 'display_name': 'y', 'region': 'eu-west-2'}],
            'aws_infras': [{'module_name': 'i', 'display_name': 'z', 'compute_count': 4}],
            'aws_peerings': [{'module_name': 'p', 'network_ref': 'b'}],
            'aws_clusters': [{'module_name': 'c', 'cpu_core_count': 32}, {'module_name': 'd'}],
            'aws_avmclusters': [{'module_name': 'v', 'display_name': 'v', 'total_container_databases': 4}]},
    'gcp': {'cloud': 'gcp', 'iac_tool': 'opentofu',
            'gcp_networks': [{'module_name': 'x'}, {'module_name': 'y', 'purpose': 'adbs'}, {'module_name': 'z'}],
            'gcp_infras': [{'module_name': 'i'}, {'module_name': 'j'}],
            'gcp_clusters': [{'module_name': 'c', 'network_ref': 'z'}],
            'gcp_autonomous_dbs': [{'module_name': 'q', 'network_ref': 'y', 'compute_count': 8}]},
}


def blueprint(cloud):
    return importlib.import_module(f'clouds.{cloud}.blueprint')


class TestSharedModulesArePayloadIndependent(unittest.TestCase):
    """The sync renders each module once, from one payload. That is only right if
    a module's files never depend on the instances a config declares."""

    def test_same_module_files_for_any_payload(self):
        for cloud in CLOUDS:
            bp = blueprint(cloud)
            a, b = generate_all(bp.PAYLOAD), generate_all(OTHER[cloud])
            for app_dir in bp.MODULES:
                for f in sync_blueprints.FILES:
                    key = f'modules/{app_dir}/{f}'
                    with self.subTest(cloud=cloud, file=key):
                        self.assertIn(key, a)
                        self.assertEqual(a[key], b.get(key), f'{key} depends on the payload')


class TestBlueprintMapping(unittest.TestCase):

    def test_every_template_dir_exists(self):
        for cloud in CLOUDS:
            for app_dir, (_, template) in blueprint(cloud).MODULES.items():
                with self.subTest(cloud=cloud, module=app_dir):
                    self.assertTrue((ROOT / 'clouds' / cloud / 'templates' / template).is_dir(), template)

    def test_azure_is_not_shared(self):
        # The app emits one Azure module per instance; the blueprint, for_each.
        self.assertNotIn('azure', CLOUDS)


@unittest.skipUnless(os.path.isdir(os.path.join(sync_blueprints.blueprints_repo(), '.git')),
                     'odb-terraform-blueprints is not checked out next to this repo')
class TestBlueprintsAreInSync(unittest.TestCase):

    def test_every_blueprint_module_dir_exists(self):
        repo = Path(sync_blueprints.blueprints_repo())
        for cloud in CLOUDS:
            bp = blueprint(cloud)
            for bp_dir, _ in bp.MODULES.values():
                with self.subTest(cloud=cloud, module=bp_dir):
                    self.assertTrue((repo / bp.BLUEPRINT_DIR / 'modules' / bp_dir).is_dir())

    def test_blueprint_modules_match_the_render(self):
        to_write, blocked = sync_blueprints.plan(sync_blueprints.blueprints_repo())
        self.assertEqual(
            sorted(set(to_write) | set(blocked)), [],
            'The blueprints repo is out of date with the app templates. Run:\n'
            '    python scripts/sync_blueprints.py\n'
            '(committing in this repo does it automatically once the hook is installed: '
            'git config core.hooksPath .githooks)')


if __name__ == '__main__':
    unittest.main()
