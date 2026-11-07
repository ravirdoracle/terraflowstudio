"""Which of this cloud's modules are also published as the standalone blueprints.

The app's templates are the master copy: scripts/sync_blueprints.py renders these
modules through the real generator and writes them into the
odb-terraform-blueprints repo, so the blueprints get exactly what an app user
downloads. Only modules are shared - each side keeps its own hand-written root.
"""

#: Blueprint directory inside the odb-terraform-blueprints repo.
BLUEPRINT_DIR = 'db-at-gcp'

#: app module directory -> (blueprint module directory, template directory)
MODULES = {
    'gcp-odb-network':      ('odb-network',      'gcp_odb_network'),
    'gcp-odb-network-adbs': ('odb-network-adbs', 'gcp_odb_network_adbs'),
    'gcp-exadata-infra':    ('exadata-infra',    'gcp_exadb_infra'),
    'gcp-vm-cluster':       ('vm-cluster',       'gcp_exadb_vm_cluster'),
    'gcp-autonomous-db':    ('autonomous-db',    'gcp_autonomous_db'),
}

#: A payload that makes the generator emit every module above: a dedicated
#: network and an ADB-S-only one, an infra, a cluster and an Autonomous Database.
PAYLOAD = {
    'cloud': 'gcp',
    'gcp_networks': [{'module_name': 'net'}, {'module_name': 'net_adbs', 'purpose': 'adbs'}],
    'gcp_infras': [{'module_name': 'infra'}],
    'gcp_clusters': [{'module_name': 'cluster'}],
    'gcp_autonomous_dbs': [{'module_name': 'adb', 'network_ref': 'net_adbs'}],
}
