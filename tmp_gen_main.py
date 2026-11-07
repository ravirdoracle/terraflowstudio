import sys
sys.path.insert(0, r'c:\terraflow_studio\odb_terraform_app')
from app import generate_all

data = {
    'cloud': 'aws',
    'aws_networks':  [{'module_name': 'n1', 'display_name': 'test-net', 'availability_zone_id': 'use1-az6', 'client_subnet_cidr': '10.2.0.0/24', 'backup_subnet_cidr': '10.2.1.0/24'}],
    'aws_infras':    [{'module_name': 'i1', 'display_name': 'test-infra', 'availability_zone_id': 'use1-az6'}],
    'aws_peerings':  [{'module_name': 'p1', 'display_name': 'test-peer', 'network_ref': 'n1', 'peer_network_id': 'vpc-123'}],
    'aws_clusters':  [{'module_name': 'c1', 'display_name': 'test-cluster', 'infra_ref': 'i1', 'network_ref': 'n1', 'gi_version': '23.0.0.0', 'hostname_prefix': 'vm', 'ssh_public_keys': ['ssh-rsa AAAA']}],
}

files = generate_all(data)
with open(r'C:\Users\ravin\AppData\Local\Temp\aws_main.tf', 'w', encoding='utf-8') as f:
    f.write(files['main.tf'])
print("Wrote", len(files['main.tf']), "chars to aws_main.tf")
