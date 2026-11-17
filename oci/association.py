"""Standalone Data Guard creation or read-only inspection of an existing pair."""
import json
import os
import re
import shlex

from core.helpers import make_renderer

render_tf = make_renderer(os.path.join(os.path.dirname(__file__), 'templates'))


def association_files(data):
    files = {}
    seen = set()
    for raw in data.get('dg_associations') or []:
        name = raw.get('module_name') or 'primary'
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}', name):
            raise ValueError('Data Guard association module name must start with a letter and contain only letters, digits, _ or - (max 32)')
        if name.lower() in seen:
            raise ValueError(f'Duplicate Data Guard association module name: {name}')
        seen.add(name.lower())
        mode = raw.get('mode', 'create')
        output_format = raw.get('output_format', 'terraform')
        if output_format not in ('terraform', 'cli', 'both'):
            raise ValueError('Association output format must be terraform, cli or both')
        creation = raw.get('creation_type', 'ExistingVmCluster')
        if mode not in ('create', 'existing'):
            raise ValueError('Data Guard association mode must be create or existing')
        if mode == 'create' and creation not in ('ExistingVmCluster', 'ExistingDbSystem'):
            raise ValueError('Choose an existing VM cluster or DB system for standby creation')
        # Whitelist fields: credentials and unknown input never reach output files.
        values = {k: (raw.get(k) or '').strip() for k in (
            'oci_region', 'database_id', 'peer_database_id', 'peer_vm_cluster_id',
            'peer_db_system_id', 'peer_db_home_id', 'peer_db_unique_name', 'peer_sid_prefix')}
        values['oci_region'] = values['oci_region'] or 'us-ashburn-1'
        keys = ['oci_region', 'database_id']
        if mode == 'existing':
            keys += ['peer_database_id']
        else:
            keys += ['peer_vm_cluster_id' if creation == 'ExistingVmCluster' else 'peer_db_system_id',
                     'peer_db_home_id', 'peer_db_unique_name', 'peer_sid_prefix']
        tfvars = '\n'.join(f'{k} = {json.dumps(values[k]).replace("${", "$${").replace("%{", "%%{")}' for k in keys)
        if mode == 'create':
            tfvars += '\nis_active_data_guard_enabled = ' + ('false' if raw.get('is_active_data_guard_enabled') is False else 'true')
            tfvars += '\n# Supply database_admin_password interactively at terraform plan/apply; never commit it.'
        ctx = dict(mode=mode, creation_type=creation, keys=keys, tfvars=tfvars)
        base = f'dg_association_{name}'
        if output_format != 'cli':
            for filename in ('main.tf', 'variables.tf', 'outputs.tf', 'terraform.tfvars', 'README.md'):
                files[f'{base}/{filename}'] = render_tf(f'oci_dg_association/{filename}.j2', **ctx)
        if output_format != 'terraform':
            request = {'databaseId': values['database_id']}
            if mode == 'create':
                request.update(protectionMode='MAXIMUM_PERFORMANCE', transportType='ASYNC',
                               isActiveDataGuardEnabled=raw.get('is_active_data_guard_enabled') is not False)
                if creation == 'ExistingDbSystem':
                    request['creationType'] = creation
                for key in keys:
                    if key not in ('oci_region', 'database_id') and (values[key] or key.endswith('_cluster_id') or key.endswith('_system_id')):
                        camel = key.split('_')[0] + ''.join(part.title() for part in key.split('_')[1:])
                        request[camel] = values[key]
            files[f'{base}/cli/request.json'] = json.dumps(request, indent=2)
            files[f'{base}/cli/run.sh'] = render_tf('oci_dg_association/run.sh.j2',
                **ctx, region=shlex.quote(values['oci_region']),
                peer_database_id=shlex.quote(values['peer_database_id']))
            files[f'{base}/cli/README.md'] = render_tf('oci_dg_association/CLI_README.md.j2', **ctx)
    return files
