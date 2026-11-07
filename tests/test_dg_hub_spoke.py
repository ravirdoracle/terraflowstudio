"""Cross-region Data Guard: more VCN pairs on one hub VCN, DRG and RPC per region.

The card's own VCNs stay the first pair at the addresses they always had, so an
applied configuration plans no change; extra pairs are additive, with paired
routing — each cluster VCN reaches only its own peer.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, generate_all
from oci import validator

ROOT = Path(__file__).parent.parent
PAGE = ROOT / 'oci' / 'pages' / 'dg.html'

CARD = {'module_name': 'cr1', 'primary_oci_region': 'us-ashburn-1', 'standby_oci_region': 'us-phoenix-1'}
PAIRS = [{'name': 'app2', 'primary_vcn_id': 'ocid1.vcn.oc1..p2', 'primary_nsg_id': 'ocid1.nsg.oc1..p2',
          'primary_client_cidr': '10.11.1.0/24', 'standby_vcn_id': 'ocid1.vcn.oc1..s2',
          'standby_nsg_id': 'ocid1.nsg.oc1..s2', 'standby_client_cidr': '10.31.1.0/24'},
         {'name': 'erp', 'primary_client_cidr': '10.12.1.0/24', 'standby_client_cidr': '10.32.1.0/24'}]
BASE = 'dg_cross_region_cr1'


def _gen(**card):
    return generate_all({'cloud': 'dg', 'dg_cross_region': [{**CARD, **card}]})


def _errors(**card):
    errors = {}
    validator.validate({'dg_cross_region': [{**CARD, **card}]}, errors)
    return errors.get('cr1', {})


class TestWithoutPairs(unittest.TestCase):

    def test_nothing_pair_related_is_emitted(self):
        for path, content in _gen().items():
            for word in ('extra_spokes', 'additional_pairs', '_extra'):
                self.assertNotIn(word, content, path)

    def test_an_empty_list_is_the_same_as_none(self):
        self.assertEqual(_gen(additional_pairs=[]), _gen())


class TestTheFoundationIsBuiltOnce(unittest.TestCase):

    def setUp(self):
        self.files = _gen(additional_pairs=PAIRS)
        self.region = self.files[f'{BASE}/modules/oci-dg-primary/main.tf']

    def test_one_hub_vcn_drg_and_rpc_pair(self):
        self.assertEqual(self.region.count('resource "oci_core_vcn"'), 1)
        self.assertEqual(self.region.count('resource "oci_core_drg"'), 1)
        self.assertEqual(self.region.count('resource "oci_core_drg_attachment"'), 1)
        peering = self.files[f'{BASE}/modules/oci-dg-peering/main.tf']
        self.assertEqual(peering.count('resource "oci_core_remote_peering_connection"'), 2)

    def test_the_first_pair_keeps_its_addresses(self):
        # Unchanged resource blocks mean unchanged state addresses: no move, no destroy.
        plain = _gen()[f'{BASE}/modules/oci-dg-primary/main.tf']
        for block in re.findall(r'resource "[^"]+" "[^"]+"', plain):
            self.assertIn(block, self.region)

    def test_extra_pairs_get_their_own_lpg_pair_on_the_shared_hub(self):
        self.assertIn('resource "oci_core_local_peering_gateway" "hub_lpg_extra"', self.region)
        self.assertIn('resource "oci_core_local_peering_gateway" "cluster_lpg_extra"', self.region)
        self.assertIn('vcn_id         = oci_core_vcn.hub.id', self.region)
        self.assertIn('vcn_id         = each.value.cluster_vcn_id', self.region)

    def test_hub_route_tables_gain_a_rule_per_pair(self):
        self.assertEqual(self.region.count('dynamic "route_rules"'), 2)
        self.assertIn('network_entity_id = oci_core_local_peering_gateway.hub_lpg_extra[route_rules.key].id', self.region)
        self.assertIn('destination       = route_rules.value.remote_client_cidr', self.region)

    def test_paired_routing_and_nsg(self):
        # Each pair's NSG admits only its own peer's CIDR.
        self.assertIn('source                    = each.value.remote_client_cidr', self.region)
        root = self.files[f'{BASE}/main.tf']
        self.assertIn('local_client_cidr      = p.primary_client_cidr\n      remote_client_cidr     = p.dr_client_cidr', root)
        self.assertIn('local_client_cidr      = p.dr_client_cidr\n      remote_client_cidr     = p.primary_client_cidr', root)

    def test_tfvars_carry_the_pairs(self):
        tfvars = self.files[f'{BASE}/terraform.tfvars']
        self.assertIn('additional_pairs = {\n  "app2" = {', tfvars)
        self.assertIn('    dr_client_cidr      = "10.31.1.0/24"', tfvars)
        self.assertIn('    primary_vcn_id      = "<erp-primary-vcn-ocid>"', tfvars)
        self.assertNotIn('route_table_id', tfvars.split('additional_pairs')[1])

    def test_readme_lists_the_pairs(self):
        readme = self.files[f'{BASE}/README.md']
        self.assertIn('### Additional VCN pairs on the same hub', readme)
        self.assertIn('| `app2` | `10.11.1.0/24` | `10.31.1.0/24` |', readme)


class TestManagedRouteTables(unittest.TestCase):

    def setUp(self):
        self.files = _gen(additional_pairs=PAIRS, manage_route_table=True)

    def test_existing_rules_are_kept_through_tfvars(self):
        # One for_each resource serves every pair, so pre-existing rules cannot
        # be pasted into the module as they are for the first pair.
        region = self.files[f'{BASE}/modules/oci-dg-primary/main.tf']
        self.assertIn('for_each = each.value.existing_route_rules', region)
        self.assertIn("terraform import 'module.primary.oci_core_default_route_table.cluster_rt_extra[\"app2\"]'", region)
        tfvars = self.files[f'{BASE}/terraform.tfvars']
        self.assertIn('primary_route_table_id = "<app2-primary-default-rt-ocid>"', tfvars)
        self.assertIn('# primary_existing_route_rules = [', tfvars)

    def test_readme_warns_about_removed_routes(self):
        self.assertIn('every other route in it is removed', self.files[f'{BASE}/README.md'])


class TestValidation(unittest.TestCase):

    def test_good_pairs_pass(self):
        self.assertEqual(_errors(additional_pairs=PAIRS), {})

    def test_no_pairs_no_rules(self):
        self.assertEqual(_errors(), {})

    def test_duplicate_names(self):
        e = _errors(additional_pairs=[PAIRS[0], {**PAIRS[1], 'name': 'APP2'}])
        self.assertIn('used twice', e['additional_pairs'])

    def test_name_format(self):
        self.assertIn('a letter', _errors(additional_pairs=[{**PAIRS[0], 'name': '2bad'}])['additional_pairs'])

    def test_a_cidr_shared_on_one_side(self):
        e = _errors(additional_pairs=[{**PAIRS[0], 'primary_client_cidr': '10.10.1.0/25'}])
        self.assertIn('overlaps the primary CIDR of first pair', e['additional_pairs'])

    def test_a_cidr_on_both_sides(self):
        e = _errors(additional_pairs=[{**PAIRS[0], 'standby_client_cidr': '10.11.1.0/24'}])
        self.assertIn('overlaps the standby CIDR', e['additional_pairs'])

    def test_lpg_limit(self):
        pairs = [{'name': f'p{n}', 'primary_client_cidr': f'10.11.{n}.0/24',
                  'standby_client_cidr': f'10.31.{n}.0/24'} for n in range(10)]
        self.assertIn('OCI allows 10', _errors(additional_pairs=pairs)['additional_pairs'])
        self.assertEqual(_errors(additional_pairs=pairs[:9]), {})

    def test_api_uses_it(self):
        d = app.test_client().post('/api/validate', json={
            'cloud': 'dg', 'tab': 1,
            'dg_cross_region': [{**CARD, 'additional_pairs': [{**PAIRS[0], 'name': '2bad'}]}]}).get_json()
        self.assertFalse(d['valid'])
        self.assertIn('cr1', d['errors_by_module'])


class TestPage(unittest.TestCase):

    def setUp(self):
        self.html = PAGE.read_text(encoding='utf-8')

    def test_pairs_ui(self):
        for fn in ('function addDgCrPair(', 'function removeDgCrPair(', 'function _dgCrPairsHTML('):
            self.assertIn(fn, self.html)
        self.assertIn('additional_pairs:       (dgCrs[i].additional_pairs || []).map(', self.html)

    def test_default_names_are_never_reused(self):
        self.assertIn("while (pairs.some(pr => pr.name === `pair${n}`)) n++;", self.html)

    def test_validation_errors_are_shown(self):
        # /api/validate returns an object; the page called .join on it.
        self.assertNotIn("(d.errors||[]).join", self.html)
        self.assertIn('d.errors_by_module', self.html)


@unittest.skipUnless(shutil.which('terraform'), 'terraform not installed')
class TestTerraformFmt(unittest.TestCase):
    """Everything the pairs add is fmt-clean. The root main.tf outputs block is
    not, and never was — downloads run terraform fmt over it (app._fmt_files)."""

    def test_pair_output_is_fmt_clean(self):
        for manage in (False, True):
            with self.subTest(manage=manage), tempfile.TemporaryDirectory() as tmp:
                for path, content in _gen(additional_pairs=PAIRS, manage_route_table=manage,
                                          add_ssh=manage).items():
                    full = os.path.join(tmp, path)
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    with open(full, 'w', encoding='utf-8', newline='\n') as fh:
                        fh.write(content)
                r = subprocess.run(['terraform', 'fmt', '-check', '-recursive', '.'],
                                   cwd=tmp, capture_output=True, text=True)
                unformatted = [l for l in r.stdout.split() if l.strip()]
                self.assertEqual([l for l in unformatted if not l.replace('\\', '/').endswith(f'{BASE}/main.tf')],
                                 [], r.stdout)


if __name__ == '__main__':
    unittest.main()
