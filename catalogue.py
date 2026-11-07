"""Generic machinery behind the config/*.json catalogues.

`regions.py` and `shapes.py` are the same shape of thing: a per-cloud JSON file,
read by the browser and the generators, edited from /regions, and validated
before it is written. Everything in here is what those two have in common - the
cache, the atomic write, and the hand-written serialisation format.

What is *not* here is what each catalogue means: its fields, its rules, and its
accessors stay in the module that owns it. This file knows about "a list of
entries under some key", nothing more.
"""
import json
import os
import tempfile
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent / 'config'


class CatalogueError(RuntimeError):
    """A catalogue file is missing, malformed, or internally inconsistent."""


def load(path, cloud, validate_fn, cache, key, refresh=False):
    """Parse and validate a catalogue file, caching the result.

    The cache is keyed on the file's path and mtime, not just the cloud. Under
    gunicorn every worker holds its own cache, and a save from /regions only
    refreshes the worker that handled it - the others went on serving the old
    zones to the product pages until a restart. One stat() per call is the
    price of every worker seeing an edit on its next request.
    """
    if refresh:
        cache.pop(cloud, None)
    try:
        stamp = (str(path), os.stat(path).st_mtime_ns)
    except FileNotFoundError:
        raise CatalogueError(f'{cloud}: catalogue not found at {path}')
    hit = cache.get(cloud)
    if hit is None or hit[0] != stamp:
        try:
            with open(path, encoding='utf-8') as fh:
                doc = json.load(fh)
        except FileNotFoundError:
            raise CatalogueError(f'{cloud}: catalogue not found at {path}')
        except json.JSONDecodeError as exc:
            raise CatalogueError(f'{cloud}: invalid JSON in {path} - {exc}')
        cache[cloud] = (stamp, validate_fn(cloud, doc))
    return cache[cloud][1]


def field_order(entries, preferred):
    """Field order for written entries, taken from what the file already uses.

    Following the existing file keeps a save from reordering every line, so the
    diff shows what actually changed. Fields the file has never carried are
    appended in `preferred` order.
    """
    order = []
    for entry in entries:
        for k in entry:
            if k not in order:
                order.append(k)
    for k in preferred:
        if k not in order:
            order.append(k)
    return order


def dumps(doc, key, order):
    """Serialise a catalogue the way these files are written by hand.

    json.dumps(indent=2) would put every field of every entry on its own line
    and turn a one-word edit into a 250-line diff. These files are read and
    reviewed by people, so entries stay on one line, column-aligned.
    """
    entries = doc.get(key, [])

    cells = []
    for entry in entries:
        row = {}
        for k in order:
            if k in entry:
                row[k] = f'"{k}": {json.dumps(entry[k], ensure_ascii=False)}'
        cells.append(row)
    width = {k: max((len(r[k]) for r in cells if k in r), default=0) for k in order}

    lines = ['{']
    for k, value in doc.items():
        if k == key:
            continue
        if k == '_comment' and isinstance(value, list):
            lines.append('  "_comment": [')
            for i, note in enumerate(value):
                tail = '' if i == len(value) - 1 else ','
                lines.append(f'    {json.dumps(note, ensure_ascii=False)}{tail}')
            lines.append('  ],')
        else:
            lines.append(f'  {json.dumps(k)}: {json.dumps(value, ensure_ascii=False)},')

    lines.append(f'  "{key}": [')
    for i, row in enumerate(cells):
        present = [k for k in order if k in row]
        parts = []
        for j, k in enumerate(present):
            if j == len(present) - 1:
                parts.append(row[k])        # last column: no comma, no padding
            else:
                # The comma belongs to the value and the padding follows it —
                # pad first and the commas end up in a ragged second column.
                parts.append((row[k] + ', ').ljust(width[k] + 2))
        tail = '' if i == len(cells) - 1 else ','
        lines.append('    { ' + ''.join(parts).rstrip() + ' }' + tail)
    lines.append('  ]')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def write_atomic(path, body, prefix):
    """Replace a catalogue file atomically.

    Atomic because a half-written file is not merely a bad save: every cloud page
    reads its catalogues at render time, so truncated JSON takes the whole app
    down until someone fixes it by hand.
    """
    fd, tmp = tempfile.mkstemp(dir=str(Path(path).parent), prefix=prefix, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(body)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
