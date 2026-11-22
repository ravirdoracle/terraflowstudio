"""Normalize the Azure form's deployment inputs without activating empty cards."""
import re


_IDENTITIES = {
    'azure_vnets': ('vnet_name', 'subnet_name', 'resource_group_name'),
    'azure_infras': ('name', 'display_name', 'resource_group_name'),
    'azure_clusters': ('name', 'display_name', 'hostname', 'resource_group_name'),
    'azure_autonomous_dbs': ('name', 'display_name', 'resource_group_name'),
    'azure_resource_anchors': ('name',),
    'azure_network_anchors': ('name',),
}


def configured_payload(data):
    result = dict(data)
    for key, identities in _IDENTITIES.items():
        result[key] = [card for card in data.get(key, [])
                       if card.get('vnet_mode') == 'existing'
                       or card.get('infra_mode') == 'existing'
                       or card.get('anchor_mode') == 'existing'
                       or any(str(card.get(field) or '').strip() for field in identities)]
    return result


def deployment_defaults(data):
    """Explicit root settings win; otherwise use unambiguous entered settings.

    Resource groups/regions come from creation cards, not linked resources that
    may live in another group. A single subscription can come from existing IDs.
    """
    result = dict(data)
    creation_cards = [card for key in ('azure_vnets', 'azure_infras', 'azure_clusters', 'azure_autonomous_dbs')
                      for card in data.get(key, []) if card.get('infra_mode') != 'existing' and card.get('vnet_mode') != 'existing']
    for field in ('resource_group_name', 'location'):
        values = {str(card[field]).strip() for card in creation_cards if card.get(field)}
        if not result.get(field) and len(values) == 1:
            result[field] = values.pop()
    subscriptions = set()
    for key in _IDENTITIES:
        for card in data.get(key, []):
            for value in card.values():
                if isinstance(value, str):
                    match = re.match(r'(?i)^/subscriptions/([^/]+)/', value)
                    if match:
                        subscriptions.add(match.group(1))
    if not result.get('subscription_id') and len(subscriptions) == 1:
        result['subscription_id'] = subscriptions.pop()
    return result
