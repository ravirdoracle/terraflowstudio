"""Opt-in Oracle Database@AWS transit VPC generation."""
import ipaddress
import json
import re

FIELDS = {
    'network_ref': 'string', 'region': 'string', 'vpc_mode': 'string',
    'vpc_cidr': 'string', 'subnet_cidr': 'string', 'vpc_id': 'string',
    'subnet_id': 'string', 'transit_gateway_id': 'string',
    'transit_gateway_route_table_id': 'string',
    'attachment_mode': 'string', 'attachment_id': 'string',
    'peering_mode': 'string', 'peering_id': 'string',
    'odb_cidrs': 'list(string)', 'client_cidrs': 'list(string)',
    'application_route_table_ids': 'list(string)',
    'manage_vpc_routes': 'bool', 'manage_tgw_routes': 'bool',
    'register_peer_cidrs': 'bool',
}


def transit_payload(data):
    """A transit-only setup must not deploy the page's untouched sample cards."""
    if not data.get('aws_transit_vpcs'):
        return data
    return {
        **data,
        'aws_infras': [card for card in data.get('aws_infras', [])
                       if card.get('is_existing') or card.get('display_name')],
        'aws_peerings': [card for card in data.get('aws_peerings', [])
                        if card.get('display_name') or card.get('peer_network_id') or card.get('peer_network_cidrs')],
    }


def _list(value):
    if isinstance(value, str):
        value = re.split(r'[,\s]+', value)
    return list(dict.fromkeys(str(item).strip() for item in (value or []) if str(item).strip()))


def defaults(card, networks):
    names = [n['module_name'] for n in networks]
    ref = card.get('network_ref') or (names[0] if names else '')
    net = next((n for n in networks if n['module_name'] == ref), {})
    cidrs = _list(card.get('odb_cidrs'))
    if not cidrs and not net.get('is_existing'):
        cidrs = _list([net.get('client_subnet_cidr', ''), net.get('backup_subnet_cidr', '')])
    return {
        'module_name': card.get('module_name') or 'transit_vpc',
        'network_ref': ref, 'region': card.get('region') or net.get('region') or '',
        'vpc_mode': card.get('vpc_mode', 'existing'),
        'vpc_cidr': (card.get('vpc_cidr') or '').strip(),
        'subnet_cidr': (card.get('subnet_cidr') or '').strip(),
        'vpc_id': (card.get('vpc_id') or '').strip(),
        'subnet_id': (card.get('subnet_id') or '').strip(),
        'transit_gateway_id': (card.get('transit_gateway_id') or '').strip(),
        'transit_gateway_route_table_id': (card.get('transit_gateway_route_table_id') or '').strip(),
        'attachment_mode': card.get('attachment_mode', 'create'),
        'attachment_id': (card.get('attachment_id') or '').strip(),
        'peering_mode': card.get('peering_mode', 'create'),
        'peering_id': (card.get('peering_id') or '').strip(),
        'odb_cidrs': cidrs, 'client_cidrs': _list(card.get('client_cidrs')),
        'application_route_table_ids': _list(card.get('application_route_table_ids')),
        'manage_vpc_routes': card.get('manage_vpc_routes', True),
        'manage_tgw_routes': card.get('manage_tgw_routes', True),
        'register_peer_cidrs': card.get('register_peer_cidrs', False),
    }


def validate_transits(data, err):
    networks = data.get('aws_networks') or []
    if not networks and data.get('module_0'):
        networks = [{**data['module_0'], 'module_name': data.get('module_names', {}).get('0', 'odb_network')}]
    seen = set()
    peers = set()
    attachments = set()
    for raw in data.get('aws_transit_vpcs') or []:
        card = defaults(raw, networks)
        name = card['module_name']
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', name) or name in seen:
            err(name, 'module_name', 'Use a unique Terraform identifier')
        seen.add(name)
        if card['network_ref'] not in {n.get('module_name') for n in networks}:
            err(name, 'network_ref', 'Select an ODB network from this configuration')
        for field, values in (('vpc_mode', ('create', 'existing')),
                              ('attachment_mode', ('create', 'existing')),
                              ('peering_mode', ('create', 'existing'))):
            if card[field] not in values:
                err(name, field, 'Choose Create new or Use existing')
        for field in ('manage_vpc_routes', 'manage_tgw_routes', 'register_peer_cidrs'):
            if not isinstance(card[field], bool):
                err(name, field, 'Must be true or false')
        ids = [('transit_gateway_id', r'tgw-[0-9a-f]+')]
        if card['manage_tgw_routes']:
            ids.append(('transit_gateway_route_table_id', r'tgw-rtb-[0-9a-f]+'))
        if card['vpc_mode'] == 'existing':
            ids += [('vpc_id', r'vpc-[0-9a-f]+'), ('subnet_id', r'subnet-[0-9a-f]+')]
        if card['attachment_mode'] == 'existing':
            ids.append(('attachment_id', r'tgw-attach-[0-9a-f]+'))
            if card['vpc_mode'] == 'create':
                err(name, 'attachment_mode', 'A new VPC needs a new TGW attachment')
        if card['peering_mode'] == 'existing':
            ids.append(('peering_id', r'odbpcx[-_][A-Za-z0-9]+'))
            if card['vpc_mode'] == 'create':
                err(name, 'peering_mode', 'A new VPC needs a new ODB peering')
            if card['register_peer_cidrs']:
                err(name, 'register_peer_cidrs', 'Use the documented CLI update for a peering managed elsewhere')
        if card['vpc_mode'] == 'existing' and card['vpc_id']:
            peer_key = (card['network_ref'], card['vpc_id'])
            if peer_key in peers:
                err(name, 'vpc_id', 'Only one hub may manage this ODB network / transit VPC pair')
            peers.add(peer_key)
            attachment_key = (card['vpc_id'], card['transit_gateway_id'])
            if card['attachment_mode'] == 'create':
                if attachment_key in attachments:
                    err(name, 'attachment_mode', 'Create one attachment per VPC/TGW pair; reuse it for other hubs')
                attachments.add(attachment_key)
        for field, pattern in ids:
            if not re.fullmatch(pattern, card[field]):
                err(name, field, 'Enter a valid AWS resource ID')
        parsed = {}
        fields = ['odb_cidrs', 'client_cidrs']
        if card['vpc_mode'] == 'create':
            fields += ['vpc_cidr', 'subnet_cidr']
        for field in fields:
            values = card[field] if isinstance(card[field], list) else [card[field]]
            if not values:
                err(name, field, 'Enter at least one IPv4 CIDR')
            for value in values:
                try:
                    net = ipaddress.ip_network(value, strict=True)
                    if net.version != 4:
                        raise ValueError()
                    parsed.setdefault(field, []).append(net)
                except ValueError:
                    err(name, field, 'Use canonical IPv4 CIDRs')
        if parsed.get('vpc_cidr') and parsed.get('subnet_cidr'):
            vpc, subnet = parsed['vpc_cidr'][0], parsed['subnet_cidr'][0]
            if not 16 <= vpc.prefixlen <= 28 or not 16 <= subnet.prefixlen <= 28 or not subnet.subnet_of(vpc):
                err(name, 'subnet_cidr', 'Use a /16–/28 subnet inside the VPC CIDR')
            # Advertised client prefixes may intentionally be supernets/default
            # routes. They are not necessarily the physical application CIDRs.
            if any(vpc.overlaps(n) for n in parsed.get('odb_cidrs', [])):
                err(name, 'vpc_cidr', 'Transit VPC must not overlap the ODB network')
        for route_table in card['application_route_table_ids']:
            if not re.fullmatch(r'rtb-[0-9a-f]+', route_table):
                err(name, 'application_route_table_ids', 'Use VPC route table IDs (rtb-...)')
        selected = next((n for n in networks if n.get('module_name') == card['network_ref']), {})
        if selected:
            if selected.get('is_existing'):
                if not selected.get('existing_id'):
                    err(name, 'network_ref', 'Enter the existing ODB network ID on its network card')
            elif not all(selected.get(key) for key in ('display_name', 'availability_zone_id',
                                                       'client_subnet_cidr', 'backup_subnet_cidr')):
                err(name, 'network_ref', 'Complete the selected ODB network card or select an existing network')
        if card['region'] and not re.fullmatch(r'[a-z]{2}(?:-[a-z0-9]+)+-\d+', card['region']):
            err(name, 'region', 'Enter an AWS region such as us-east-1')
        if card['region'] and selected.get('region') and card['region'] != selected['region']:
            err(name, 'region', 'Transit VPC must use the selected ODB network region')


def add_transit_files(files, data, networks, network_id_expr, render):
    raw = data.get('aws_transit_vpcs') or []
    if not raw:
        return
    errors = {}
    validate_transits(data,
                     lambda name, field, message: errors.setdefault(name, {}).update({field: message}))
    if errors:
        raise ValueError('Transit VPC configuration: ' + json.dumps(errors, sort_keys=True))
    cards = [defaults(card, networks) for card in raw]
    fields = '\n'.join(f'    {key.ljust(max(map(len, FIELDS)))} = {kind}' for key, kind in FIELDS.items())
    files['main.tf'] += '\n\n' + render('aws_transit_vpc/root.tf.j2', network_id_expr=network_id_expr)
    files['variables.tf'] += '\n\n' + render('aws_transit_vpc/root_variables.tf.j2', fields=fields)
    entries = []
    width = max(map(len, FIELDS))
    for card in cards:
        entries += [f'  {json.dumps(card["module_name"])} = {{']
        entries += [f'    {key.ljust(width)} = {json.dumps(card[key]).replace("${", "$${").replace("%{", "%%{")}'
                    for key in FIELDS]
        entries.append('  }')
    files['terraform.auto.tfvars'] += '\n\naws_transit_vpcs = {\n' + '\n'.join(entries) + '\n}'
    for name in ('main.tf', 'variables.tf', 'outputs.tf'):
        files['modules/aws-transit-vpc/' + name] = render('aws_transit_vpc/' + name + '.j2', fields=fields)
    files['TRANSIT_VPC.md'] = render('aws_transit_vpc/README.md.j2',
                                   cli='tofu' if data.get('iac_tool') == 'opentofu' else 'terraform')
    files['README.md'] += '\n\n## Transit VPC\n\nSee [TRANSIT_VPC.md](TRANSIT_VPC.md) for routing, staged CIDR registration, DNS, and ownership requirements.\n'
