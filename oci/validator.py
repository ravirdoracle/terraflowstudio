"""Data Guard payload validation for /api/validate.

Until the hub-and-spoke pairs arrived, Data Guard was checked in the browser only.
The pairs need the server: their names become Terraform for_each keys, and with
paired routing a CIDR that two VCNs on one side share would send one pair's Data
Guard traffic to the other.
"""
import ipaddress
import re

#: Each pair puts one LPG on each hub VCN; OCI allows 10 per VCN by default.
MAX_PAIRS = 10

_NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,31}$')


def _net(value):
    try:
        return ipaddress.ip_network((value or '').strip(), strict=False)
    except ValueError:
        return None


def validate(data, errors):
    """Populate `errors` as {module_name: {field: message}}. Returns nothing."""
    def _err(mn, f, m): errors.setdefault(mn, {}).setdefault(f, m)

    for cr in data.get('dg_cross_region') or []:
        mn = cr.get('module_name') or 'dg'
        _check_pairs(cr, mn, _err)


def _check_pairs(cr, mn, _err):
    pairs = cr.get('additional_pairs') or []
    if not pairs:
        return
    if len(pairs) + 1 > MAX_PAIRS:
        _err(mn, 'additional_pairs',
             f'{len(pairs) + 1} VCN pairs need {len(pairs) + 1} LPGs on each hub VCN; '
             f'OCI allows {MAX_PAIRS} by default - raise the limit first')

    seen = set()
    # Every client CIDR on a side, the card's own first: paired routing sends
    # traffic by destination, so two VCNs on one side must not share a range.
    sides = {'primary': [('first pair', _net(cr.get('primary_client_cidr') or '10.10.1.0/24'))],
             'standby': [('first pair', _net(cr.get('standby_client_cidr') or '10.30.1.0/24'))]}
    for n, pr in enumerate(pairs):
        name = (pr.get('name') or '').strip() or f'pair{n + 2}'
        if not _NAME.match(name):
            _err(mn, 'additional_pairs', f'Pair name "{name}": a letter, then letters, digits, _ or -')
        elif name.lower() in seen:
            _err(mn, 'additional_pairs', f'Pair name "{name}" is used twice')
        seen.add(name.lower())
        for side in ('primary', 'standby'):
            raw = (pr.get(f'{side}_client_cidr') or '').strip()
            net = _net(raw)
            if not net:
                _err(mn, 'additional_pairs', f'Pair "{name}": {side}_client_cidr is not a valid CIDR')
                continue
            clash = next((other for other, o in sides[side] if o and o.overlaps(net)), None)
            if clash:
                _err(mn, 'additional_pairs',
                     f'Pair "{name}": {side}_client_cidr {raw} overlaps the {side} CIDR of {clash}')
            sides[side].append((f'pair "{name}"', net))

    # A range that is local on one side and remote on the other is routed both
    # ways at once.
    for label, net in sides['primary']:
        clash = next((other for other, o in sides['standby'] if o and net and o.overlaps(net)), None)
        if clash:
            _err(mn, 'additional_pairs', f'The primary CIDR of {label} overlaps the standby CIDR of {clash}')
            break
