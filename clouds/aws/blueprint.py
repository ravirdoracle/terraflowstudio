"""Which of this cloud's modules are also published as the standalone blueprints.

The app's templates are the master copy: scripts/sync_blueprints.py renders these
modules through the real generator and writes them into the
odb-terraform-blueprints repo, so the blueprints get exactly what an app user
downloads. Only modules are shared - each side keeps its own hand-written root.
"""

#: Blueprint directory inside the odb-terraform-blueprints repo.
BLUEPRINT_DIR = 'db-at-aws'

#: app module directory -> (blueprint module directory, template directory)
MODULES = {
    'aws-odb-network':   ('odb-network',           'aws_odb_network'),
    'aws-exadata-infra': ('exadata-infra',         'aws_exadata_infra'),
    'aws-peering':       ('peering',               'aws_peering'),
    'aws-vm-cluster':    ('vm-cluster',            'aws_vm_cluster'),
    'aws-avmcluster':    ('autonomous-vm-cluster', 'aws_avmcluster'),
}

#: A payload that makes the generator emit every module above. Module files do
#: not depend on instance values - a test holds that true - so any such payload
#: renders the same modules.
PAYLOAD = {
    'cloud': 'aws',
    'aws_networks': [{'module_name': 'net'}],
    'aws_infras': [{'module_name': 'infra'}],
    'aws_peerings': [{'module_name': 'peer'}],
    'aws_clusters': [{'module_name': 'cluster'}],
    'aws_avmclusters': [{'module_name': 'avmc', 'display_name': 'avmc'}],
}
