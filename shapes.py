"""Exadata shape catalogue, loaded from config/<cloud>_shapes.json.

The same idea as regions.py, for the other set of values that used to be
hardcoded in three places: the shape dropdown was a literal <option> list in each
of the three product pages, the default shape was a string literal in each
generator, and the database/storage server types were free-text boxes on the AWS
page with a placeholder for documentation. The three pages had already drifted -
AWS and GCP offered X9M/X10M/X11M, Azure offered X9M/X11M.

Edit config/<cloud>_shapes.json, or use /regions, to add a shape or a server
type; no code change is needed.

What a shape carries:
  shape                  provider value, e.g. "Exadata.X11M". Unique; the key
                         everything joins on.
  label                  human name shown in the dropdown.
  status                 "live" or "planned" - planned shapes are shown greyed.
  database_server_types  models offered for this shape, e.g. ["X11M"].
  storage_server_types   models offered for this shape, e.g. ["X11M-HC"].
  server_types_required  the provider rejects the infra without them. AWS
                         documents this for Exadata.X11M.

GCP carries no server-type lists: google_oracle_database_cloud_exadata_infrastructure
has no such input, only computed db_server_version / storage_server_version.
"""
import json

import catalogue

CONFIG_DIR = catalogue.CONFIG_DIR

#: Clouds that have a shape catalogue, in the order the editor shows them.
CLOUDS = ('aws', 'azure', 'gcp')

#: Fields every entry carries, plus the optional ones each cloud actually uses.
#: The editor renders from this, so a new cloud needs a catalogue file and a
#: line here - no UI change.
CORE_FIELDS = ('shape', 'label', 'status')
OPTIONAL_FIELDS = {
    'aws':   ('database_server_types', 'storage_server_types', 'server_types_required'),
    'azure': ('database_server_types', 'storage_server_types', 'server_types_required'),
    'gcp':   (),
}

#: Entry fields the editor should render as a list of chips rather than a text box.
LIST_FIELDS = ('database_server_types', 'storage_server_types')

#: Entry fields the editor should render as a checkbox.
BOOL_FIELDS = ('server_types_required',)

ShapeConfigError = catalogue.CatalogueError

_cache = {}


def _validate(cloud, doc):
    """Fail loudly at load time rather than silently rendering an empty dropdown."""
    if not isinstance(doc, dict) or not isinstance(doc.get('shapes'), list):
        raise ShapeConfigError(f'{cloud}: expected an object with a "shapes" list')
    if not doc['shapes']:
        raise ShapeConfigError(f'{cloud}: "shapes" is empty')

    seen = set()
    for i, entry in enumerate(doc['shapes']):
        where = f'{cloud}: shapes[{i}]'
        for field in CORE_FIELDS:
            if field not in entry:
                raise ShapeConfigError(f'{where} is missing "{field}"')
        name = entry['shape']
        if name in seen:
            raise ShapeConfigError(f'{where}: duplicate shape "{name}"')
        seen.add(name)
        if entry['status'] not in ('live', 'planned'):
            raise ShapeConfigError(
                f'{where}: status must be "live" or "planned", got "{entry["status"]}"')
        for field in LIST_FIELDS:
            if field in entry and not isinstance(entry[field], list):
                raise ShapeConfigError(f'{where}: "{field}" must be a list')
        # A shape that demands server types but offers none to choose from would
        # leave the form with a required dropdown and nothing in it.
        if entry.get('server_types_required') and not (
                entry.get('database_server_types') and entry.get('storage_server_types')):
            raise ShapeConfigError(
                f'{where}: server_types_required is set but the type lists are empty')

    # A default naming a shape that is not in the list would silently leave every
    # new card with a blank dropdown.
    default = doc.get('default_shape')
    if default is not None and default not in seen:
        raise ShapeConfigError(
            f'{cloud}: default_shape "{default}" is not one of the listed shapes')
    return doc


def load(cloud='aws', refresh=False):
    """Return the parsed catalogue for a cloud. Cached after first read."""
    return catalogue.load(path_for(cloud), cloud, _validate, _cache, 'shapes',
                          refresh=refresh)


def path_for(cloud):
    return CONFIG_DIR / f'{cloud}_shapes.json'


def validate(cloud, doc):
    """Public entry point for the same rules load() enforces.

    The editor calls this before writing, so a catalogue can never be saved in a
    state that would raise on the next load and leave every dropdown empty.
    """
    return _validate(cloud, doc)


def field_spec(cloud):
    """What the editor should render for this cloud."""
    return {
        'cloud': cloud,
        'core': list(CORE_FIELDS),
        'optional': list(OPTIONAL_FIELDS.get(cloud, ())),
        'list_fields': [f for f in LIST_FIELDS if f in OPTIONAL_FIELDS.get(cloud, ())],
        'bool_fields': [f for f in BOOL_FIELDS if f in OPTIONAL_FIELDS.get(cloud, ())],
        'default_shape': default_shape(cloud),
    }


def _field_order(cloud, entries):
    return catalogue.field_order(
        entries, tuple(CORE_FIELDS) + tuple(OPTIONAL_FIELDS.get(cloud, ())))


def dumps(cloud, doc, order=None):
    """Serialise a catalogue the way the files are written by hand."""
    order = order or _field_order(cloud, doc.get('shapes', []))
    return catalogue.dumps(doc, 'shapes', order)


def save(cloud, doc):
    """Validate, then replace the catalogue file atomically and drop the cache."""
    validate(cloud, doc)
    try:
        order = _field_order(cloud, load(cloud)['shapes'])
    except ShapeConfigError:
        order = None
    catalogue.write_atomic(path_for(cloud), dumps(cloud, doc, order),
                           prefix=f'.{cloud}_shapes.')
    return load(cloud, refresh=True)


# ── Accessors ─────────────────────────────────────────────────────────────────

def shapes(cloud='aws'):
    """Shape entries in file order, without the leading _comment block."""
    return load(cloud)['shapes']


def shapes_json(cloud='aws'):
    """Compact JSON for embedding directly in a <script> block."""
    return json.dumps(shapes(cloud), separators=(',', ':'))


def names(cloud='aws'):
    """Shape values in file order."""
    return [s['shape'] for s in shapes(cloud)]


def default_shape(cloud='aws'):
    """The shape a new card starts on.

    Falls back to the first live entry, then the first entry, so a catalogue that
    omits default_shape still produces a sensible card rather than a blank one.
    """
    doc = load(cloud)
    if doc.get('default_shape'):
        return doc['default_shape']
    entries = doc['shapes']
    for entry in entries:
        if entry.get('status') == 'live':
            return entry['shape']
    return entries[0]['shape']


def db_server_types(cloud='aws'):
    """shape -> list of database server models."""
    return {s['shape']: list(s.get('database_server_types', [])) for s in shapes(cloud)}


def storage_server_types(cloud='aws'):
    """shape -> list of storage server models."""
    return {s['shape']: list(s.get('storage_server_types', [])) for s in shapes(cloud)}


def requires_server_types(cloud='aws'):
    """Shapes the provider will not accept without database/storage server types."""
    return [s['shape'] for s in shapes(cloud) if s.get('server_types_required')]
