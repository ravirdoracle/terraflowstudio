"""Active Data Guard: create a standby or inspect an existing pair safely."""
import io
from pathlib import Path
import shutil
import subprocess
import unittest
import zipfile

from app import app, generate_all
from oci.validator import validate
from tf_validator import tf_roots

CARD = {'module_name': 'payroll', 'oci_region': 'us-ashburn-1',
        'database_id': 'ocid1.database.oc1.iad.primary',
        'peer_vm_cluster_id': 'ocid1.cloudvmcluster.oc1.phx.standby'}
BASE = 'dg_association_payroll/'


def payload(**changes):
    return {'cloud': 'dg', 'dg_associations': [{**CARD, **changes}]}


class TestAssociation(unittest.TestCase):
    def test_create_defaults_and_secret_exclusion(self):
        files = generate_all(payload(database_admin_password='DO_NOT_EXPORT_THIS'))
        main = files[BASE+'main.tf']
        self.assertIn('"ExistingVmCluster"', main)
        self.assertIn('peer_vm_cluster_id', main)
        self.assertNotIn('peer_db_system_id', main)
        self.assertIn('prevent_destroy = true', main)
        self.assertIn('delete_standby_db_home_on_delete   = true', main)
        self.assertIn('is_active_data_guard_enabled = true', files[BASE+'terraform.tfvars'])
        self.assertIn('sensitive   = true', files[BASE+'variables.tf'])
        self.assertNotIn('DO_NOT_EXPORT_THIS', '\n'.join(files.values()))
        self.assertEqual(len(files), 5)
        self.assertEqual(tf_roots(files), ['dg_association_payroll'])

    def test_existing_db_system_omits_vm_cluster(self):
        files = generate_all(payload(creation_type='ExistingDbSystem',
                                    peer_db_system_id='ocid1.dbsystem.oc1.phx.target'))
        self.assertIn('peer_db_system_id', files[BASE+'main.tf'])
        self.assertNotIn('peer_vm_cluster_id', '\n'.join(files.values()))

    def test_existing_pair_is_read_only_and_fails_if_missing(self):
        files = generate_all(payload(mode='existing', peer_database_id='ocid1.database.oc1.phx.peer'))
        main = files[BASE+'main.tf']
        self.assertIn('data "oci_database_data_guard_associations"', main)
        self.assertNotIn('resource "', main)
        self.assertNotIn('database_admin_password', '\n'.join(files.values()))
        self.assertIn('association.peer_database_id == var.peer_database_id', main)
        self.assertIn('length(local.matching_associations) == 1', files[BASE+'outputs.tf'])

    def test_tfvars_escape_terraform_interpolation(self):
        files = generate_all(payload(peer_db_unique_name='${file("secret")}\n%{if true}'))
        self.assertIn('$${file(\\"secret\\")}', files[BASE+'terraform.tfvars'])
        self.assertIn('%%{if true}', files[BASE+'terraform.tfvars'])

    def test_no_associations_preserves_networking(self):
        data = {'cloud': 'dg', 'dg_multi_az': [{'module_name':'net', 'oci_region':'us-ashburn-1'}]}
        self.assertEqual(generate_all(data), generate_all({**data, 'dg_associations':[]}))
        combined = generate_all({**data, **payload(), 'dg_multi_az':data['dg_multi_az']})
        for path, text in generate_all(data).items():
            self.assertEqual(combined[path], text)

    def test_invalid_names_and_duplicates_rejected_during_generation(self):
        for name in ('../escape', 'a/b', 'bad:name'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                generate_all(payload(module_name=name))
        data = payload()
        data['dg_associations'] *= 2
        with self.assertRaises(ValueError):
            generate_all(data)

    def test_validation_both_modes_and_missing_ids(self):
        for changes in ({}, {'mode':'existing','peer_database_id':'ocid1.database.oc1.phx.peer'},
                        {'creation_type':'ExistingDbSystem','peer_db_system_id':'ocid1.dbsystem.oc1.phx.target'}):
            errors = {}
            validate(payload(**changes), errors)
            self.assertEqual(errors, {})
        for changes, field in [({'database_id':''},'database_id'),
                               ({'peer_vm_cluster_id':''},'peer_vm_cluster_id'),
                               ({'mode':'existing','peer_database_id':CARD['database_id']},'peer_database_id'),
                               ({'creation_type':'NewDbSystem'},'creation_type'),
                               ({'mode':'unknown'},'mode'),
                               ({'is_active_data_guard_enabled':'false'},'is_active_data_guard_enabled')]:
            with self.subTest(changes=changes):
                errors = {}
                validate(payload(**changes), errors)
                self.assertIn(field, errors['payroll'])

    def test_preview_validation_and_zip(self):
        client = app.test_client()
        data = payload()
        self.assertTrue(client.post('/api/validate',json=data).get_json()['valid'])
        response = client.post('/api/generate', json={**data,'file_key':BASE+'main.tf'})
        self.assertIn('oci_database_data_guard_association',response.get_json()['content'])
        response = client.post('/api/download',json=data)
        self.assertEqual(response.status_code,200)
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            names=archive.namelist()
            self.assertTrue(any(n.endswith(BASE+'main.tf') for n in names),names)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for UI state checks')
    def test_page_state_roundtrip_and_legacy_reset(self):
        result = subprocess.run(['node', 'tests/dg_association_ui.js'],
                                cwd=Path(__file__).resolve().parent.parent,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mock_validator_covers_generated_outputs(self):
        from tf_validator import validate_terraform
        for mode in ('create', 'existing'):
            results = validate_terraform(generate_all(payload(mode=mode)), 'dg')
            self.assertFalse([r for r in results if r.status != 'pass'])

    def test_page_has_both_modes_and_roundtrip_wiring(self):
        page=app.test_client().get('/dg').get_data(as_text=True)
        for text in ('dg-page-2', 'Create standby and associate', 'Check existing database pair',
                     'dg_associations:', 'doc.dg_associations', 'dg_assoc:', 'readDgAssociation'):
            self.assertIn(text,page)


if __name__ == '__main__':
    unittest.main()
