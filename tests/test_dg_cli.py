"""CLI generation and execution checks using local stubs; never contacts OCI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app import app, generate_all
from oci.validator import validate

CARD = {'module_name':'cli', 'oci_region':'us-ashburn-1',
        'database_id':'ocid1.database.oc1.iad.primary',
        'peer_vm_cluster_id':'ocid1.cloudvmcluster.oc1.phx.target', 'output_format':'cli'}
BASE = 'dg_association_cli/cli/'


def generate(**changes):
    return generate_all({'cloud':'dg','dg_associations':[{**CARD,**changes}]})


class TestCli(unittest.TestCase):
    def test_only_cli_and_both_preserve_terraform(self):
        only=generate()
        self.assertEqual(set(only),{BASE+'run.sh',BASE+'request.json',BASE+'README.md'})
        terraform=generate(output_format='terraform')
        both=generate(output_format='both')
        self.assertEqual(both,{**terraform,**only})
        for mode in ('create','existing'):
            for creation in ('ExistingVmCluster','ExistingDbSystem'):
                script=generate(mode=mode,creation_type=creation)[BASE+'run.sh']
                check=subprocess.run(['bash','-n'],input=script,text=True,capture_output=True)
                self.assertEqual(check.returncode,0,check.stderr)

    def test_creation_request_and_password_transport(self):
        for creation,field in [('ExistingVmCluster','peerVmClusterId'),('ExistingDbSystem','peerDbSystemId')]:
            files=generate(creation_type=creation,peer_db_system_id='ocid1.dbsystem.oc1.phx.target',
                           database_admin_password='MUST_NOT_EXPORT',peer_db_home_id='ocid1.dbhome.oc1.phx.home')
            self.assertNotIn('MUST_NOT_EXPORT','\n'.join(files.values()))
            request=json.loads(files[BASE+'request.json'])
            self.assertIn(field,request)
            self.assertNotIn('databaseAdminPassword',request)
            self.assertTrue(request['isActiveDataGuardEnabled'])
            self.assertEqual(request['peerDbHomeId'],'ocid1.dbhome.oc1.phx.home')
            script=files[BASE+'run.sh'].split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
            with tempfile.TemporaryDirectory() as directory:
                source=Path(directory)/'request.json';source.write_text(json.dumps(request))
                captured=[]
                def call(command,**kwargs):
                    captured.append((command,kwargs))
                    return subprocess.CompletedProcess(command,0)
                with patch.object(sys,'argv',['-',str(source),'us-ashburn-1','']), \
                     patch('shutil.which',return_value='/stub/oci'), \
                     patch('getpass.getpass',return_value='RUNTIME_SECRET'), \
                     patch('subprocess.run',side_effect=call), self.assertRaises(SystemExit) as exit:
                    exec(compile(script,'generated_cli','exec'),{})
                self.assertEqual(exit.exception.code,0)
                command,options=captured[0]
                self.assertNotIn('RUNTIME_SECRET',' '.join(command))
                self.assertIn('file:///dev/stdin',command)
                self.assertEqual(json.loads(options['input'])['databaseAdminPassword'],'RUNTIME_SECRET')
                self.assertEqual(json.loads(source.read_text()),request)

    def test_existing_pair_script_filters_result_and_reports_missing(self):
        peer="ocid1.database.peer'; touch SHOULD_NOT_EXIST; #"
        files=generate(mode='existing',peer_database_id=peer)
        with tempfile.TemporaryDirectory(prefix='dg cli ') as directory:
            root=Path(directory)
            for path,content in files.items():
                (root/Path(path).name).write_text(content)
            stub=root/'oci'
            stub.write_text('#!'+sys.executable+'\nimport json,os,sys\nrequest=json.load(sys.stdin)\nassert request["databaseId"]\nassert "list" in sys.argv and "--all" in sys.argv\nprint(os.environ["STUB_RESPONSE"])\n')
            stub.chmod(0o700)
            env={**os.environ,'PATH':str(root)+os.pathsep+os.environ['PATH'],
                 'STUB_RESPONSE':json.dumps({'data':[{'peer-database-id':peer,'state':'AVAILABLE'},
                                                    {'peer-database-id':'other'}]})}
            result=subprocess.run(['bash',str(root/'run.sh')],env=env,cwd=root,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['peer-database-id'],peer)
            self.assertFalse((root/'SHOULD_NOT_EXIST').exists())
            env['STUB_RESPONSE']='{"data":[]}'
            result=subprocess.run(['bash',str(root/'run.sh')],env=env,cwd=root,text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('No unique association',result.stderr)

    def test_optional_args_absent_and_active_false(self):
        request=json.loads(generate(is_active_data_guard_enabled=False)[BASE+'request.json'])
        self.assertFalse(request['isActiveDataGuardEnabled'])
        self.assertNotIn('peerDbHomeId',request)
        self.assertNotIn('peerDbSystemId',request)
        self.assertNotIn('creationType',request)

    def test_validate_and_preview(self):
        errors={}
        validate({'dg_associations':[{**CARD,'output_format':'invalid'}]},errors)
        self.assertIn('output_format',errors['cli'])
        with self.assertRaises(ValueError):generate(output_format='invalid')
        client=app.test_client()
        response=client.post('/api/generate',json={'cloud':'dg','dg_associations':[CARD],
                                                 'file_key':BASE+'run.sh'})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.get_json()['content'].startswith('#!/usr/bin/env bash'))
