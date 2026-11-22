"""Keep examples and empty form values out of active generated assignments."""
import re


_ASSIGNMENT = re.compile(r'^([A-Za-z_][\w-]*)\s*=')
_EMPTY = re.compile(r'^\s*[\w-]+\s*=\s*(?:""|\[\]|\{\}|null)\s*$')


def comment_tfvars_samples(content, data):
    """Preserve entered settings; comment unconfigured cards and unset fields.

    Values selected on a named resource (counts, shape, region, etc.) are its
    configuration, even when they equal the form defaults. A card without a
    resource name or existing resource ID is still an example.
    """
    cards = {}
    for key, name, identity in (
        ('azure_vnets', 'azure_vnet', 'vnet_name'),
        ('azure_infras', 'azure_exainfra', 'name'),
        ('azure_clusters', 'azure_vmcluster', 'name'),
        ('azure_autonomous_dbs', 'azure_adbs', 'name'),
        ('azure_resource_anchors', 'azure_resource_anchor', 'name'),
        ('azure_network_anchors', 'azure_netanchor', 'name'),
    ):
        for card in data.get(key, []):
            existing = ''
            if key == 'azure_vnets' and card.get('vnet_mode') == 'existing':
                existing = card.get('existing_subnet_id') or ''
            elif key == 'azure_infras' and card.get('infra_mode') == 'existing':
                existing = card.get('existing_infrastructure_id') or ''
            elif key == 'azure_network_anchors' and card.get('anchor_mode') == 'existing':
                existing = card.get('existing_network_anchor_id') or ''
            cards[card.get('module_name') or name] = not bool(
                str(card.get(identity) or '').strip() or str(existing).strip())
    # Resolve longest names first so a sample `db` does not mask configured `db_prod`.
    names = sorted(cards, key=len, reverse=True)
    result = [
        '# Blank values and examples for unconfigured cards are commented out.',
        '# Enter real values before uncommenting; review variables.tf defaults before planning.',
    ]
    sample = False
    for line in content.splitlines():
        assignment = _ASSIGNMENT.match(line)
        if assignment:
            key = assignment.group(1)
            owner = next((name for name in names if key == name or key.startswith(name + '_')), None)
            sample = cards.get(owner, False)
            if key == 'location' and not data.get('location'):
                sample = True
        if line.strip() and not line.lstrip().startswith('#') and (sample or _EMPTY.match(line)):
            if sample:
                line = '# ' + line
            else:
                indent = line[:len(line) - len(line.lstrip())]
                line = indent + '# ' + line.lstrip()
        result.append(line)
    # Commenting a member changes the alignment of the remaining assignments.
    # Match Terraform's alignment of consecutive single-line assignments.
    aligned = []
    pending = []
    def flush():
        if pending:
            width = max(len(key) for _, key, _ in pending)
            aligned.extend(f'{indent}{key.ljust(width)} = {value}'
                           for indent, key, value in pending)
            pending.clear()
    for line in result:
        match = re.match(r'^(\s*)([\w-]+)\s*=\s*(.+)$', line)
        if not match or (pending and match.group(1) != pending[0][0]):
            flush()
        if match:
            pending.append(match.groups())
        else:
            aligned.append(line)
    flush()
    return '\n'.join(aligned)
