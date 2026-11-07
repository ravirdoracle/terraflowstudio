"""Region / availability-zone catalogue, loaded from config/*.json.

One source of truth for data that used to be duplicated: a JavaScript literal in
the page template (region and AZ dropdowns) and a Python dict in the generator
(the OCI provider region). Keeping both by hand meant they drifted - the Python
side covered 8 of the 22 regions the dropdown offered, and everything else fell
back to us-ashburn-1 without saying so.

Edit config/aws_regions.json to add a region or AZ; no code change is needed.
"""
import json
from pathlib import Path

import catalogue

CONFIG_DIR = catalogue.CONFIG_DIR

#: Clouds that have a catalogue, in the order the editor shows them.
CLOUDS = ('aws', 'azure', 'gcp')

#: Fields every entry carries, plus the optional ones each cloud actually uses.
#: The region editor renders from this, so adding a cloud means adding a
#: catalogue file and a line here - no UI change.
CORE_FIELDS = ('region', 'label', 'zones', 'status')
OPTIONAL_FIELDS = {
    'aws':   ('oci_label', 'oci_region'),
    'gcp':   ('oci_label', 'oci_region'),
    'azure': ('group',),
}

_cache = {}


#: The generic catalogue error, re-exported under the name callers already use.
#: `shapes.py` raises the same class, so a route can catch one type for both.
RegionConfigError = catalogue.CatalogueError


def _validate(cloud, doc):
    """Fail loudly at load time rather than silently rendering an empty dropdown."""
    if not isinstance(doc, dict) or not isinstance(doc.get('regions'), list):
        raise RegionConfigError(f'{cloud}: expected an object with a "regions" list')
    if not doc['regions']:
        raise RegionConfigError(f'{cloud}: "regions" is empty')

    seen, seen_zones = set(), {}
    for i, entry in enumerate(doc['regions']):
        where = f'{cloud}: regions[{i}]'
        for field in ('region', 'label', 'zones', 'status'):
            if field not in entry:
                raise RegionConfigError(f'{where} is missing "{field}"')
        code = entry['region']
        if code in seen:
            raise RegionConfigError(f'{where}: duplicate region "{code}"')
        seen.add(code)
        if entry['status'] not in ('live', 'planned'):
            raise RegionConfigError(
                f'{where}: status must be "live" or "planned", got "{entry["status"]}"')
        if not isinstance(entry['zones'], list):
            raise RegionConfigError(f'{where}: "zones" must be a list')
        # AWS AZ IDs and GCP zones are globally unique, so a duplicate means a
        # typo that would make the zone -> region reverse lookup silently pick
        # one. Azure reuses bare numbers ('1', '2') across every region, so the
        # check would fire on correct data and is skipped there.
        if not doc.get('zones_are_region_scoped'):
            for z in entry['zones']:
                if z in seen_zones:
                    raise RegionConfigError(
                        f'{where}: zone "{z}" already listed under "{seen_zones[z]}"')
                seen_zones[z] = code
    return doc


def load(cloud='aws', refresh=False):
    """Return the parsed catalogue for a cloud. Cached after first read."""
    return catalogue.load(path_for(cloud), cloud, _validate, _cache, 'regions',
                          refresh=refresh)


def path_for(cloud):
    return CONFIG_DIR / f'{cloud}_regions.json'


def validate(cloud, doc):
    """Public entry point for the same rules load() enforces.

    The editor calls this before writing, so a catalogue can never be saved in a
    state that would raise RegionConfigError on the next load and leave every
    dropdown in the app empty.
    """
    return _validate(cloud, doc)


def field_spec(cloud):
    """What the editor should render for this cloud."""
    return {
        'cloud': cloud,
        'core': list(CORE_FIELDS),
        'optional': list(OPTIONAL_FIELDS.get(cloud, ())),
        # Azure numbers its zones per region, so '1' in eastus is unrelated to
        # '1' in uksouth and the editor must not warn about the repetition.
        'zones_are_region_scoped': bool(load(cloud).get('zones_are_region_scoped')),
    }


def _field_order(cloud, entries):
    """Field order for written entries — Azure lists `group` before `status`;
    AWS and GCP put the oci_* pair last."""
    return catalogue.field_order(
        entries, tuple(CORE_FIELDS) + tuple(OPTIONAL_FIELDS.get(cloud, ())))


def dumps(cloud, doc, order=None):
    """Serialise a catalogue the way the files are written by hand."""
    order = order or _field_order(cloud, doc.get('regions', []))
    return catalogue.dumps(doc, 'regions', order)


def save(cloud, doc):
    """Validate, then replace the catalogue file atomically and drop the cache.

    Atomic because a half-written file is not merely a bad save: every cloud page
    reads its catalogue at render time, so truncated JSON takes the whole app
    down until someone fixes it by hand.
    """
    validate(cloud, doc)
    try:
        order = _field_order(cloud, load(cloud)['regions'])
    except RegionConfigError:
        order = None
    catalogue.write_atomic(path_for(cloud), dumps(cloud, doc, order),
                           prefix=f'.{cloud}_regions.')
    return load(cloud, refresh=True)


def regions(cloud='aws'):
    """Region entries in file order, without the leading _comment block."""
    return load(cloud)['regions']


def regions_json(cloud='aws'):
    """Compact JSON for embedding directly in a <script> block."""
    return json.dumps(regions(cloud), separators=(',', ':'))


def zone_map(cloud='aws'):
    """region code -> list of zones (AWS AZ IDs, Azure zone numbers, GCP zones)."""
    return {r['region']: r['zones'] for r in regions(cloud)}


def zone_to_region(cloud='aws'):
    """zone -> region code. Only meaningful where zones are globally unique.

    Azure numbers its zones per region, so this collapses there and the caller
    should use zone_map() instead.
    """
    return {z: r['region'] for r in regions(cloud) for z in r['zones']}


def default_oci_region(cloud='aws'):
    return load(cloud).get('default_oci_region', 'us-ashburn-1')


def to_oci_region(cloud='aws'):
    """AWS region -> OCI region identifier, for regions that have one mapped.

    Entries with a null oci_region are omitted, so callers keep using .get()
    with the default and behave exactly as before for unmapped regions.
    """
    return {r['region']: r['oci_region'] for r in regions(cloud) if r.get('oci_region')}


def unmapped_oci_regions(cloud='aws'):
    """Region codes with no OCI region set - these silently take the default."""
    return [r['region'] for r in regions(cloud) if not r.get('oci_region')]
