"""
store.py — Pluggable storage backend for Terraflow Studio configs.

Auto-selects backend at startup:
  • If COUCHDB_URL is set AND the server responds  → CouchDBStore
  • Otherwise                                      → FileStore (data/ directory)

FileStore layout:
  data/
    {customer_slug}/
      aws.json
      gcp.json

CouchDB layout:
  database: terraflow_studio_configs
  document: { _id: "{slug}_{cloud}", customer: str, cloud: str, updated: ISO8601,
               module_names: {}, module_0..3: {}, gcp_module_names: {}, gcp_module_0..2: {} }
"""

import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path(os.environ.get('ODB_DATA_DIR', '') or Path(__file__).parent / 'data')

# Every product page that saves a config. Not only the three clouds: the Data Guard
# and OCI Database pages save under 'dg' / 'oci', and a list that left them out hid
# every such save from the customer dropdown. Kept in step with clouds/registry.py
# by tests/test_all.py.
PRODUCTS = ('aws', 'gcp', 'azure', 'oci', 'dg')
COUCHDB_URL = os.environ.get('COUCHDB_URL', '').rstrip('/')
COUCHDB_DB  = os.environ.get('COUCHDB_DB', 'terraflow_studio_configs')


def _slug(customer: str) -> str:
    """Convert customer name to a safe slug."""
    return re.sub(r'[^a-z0-9_-]', '-', customer.strip().lower())[:64].strip('-') or 'unnamed'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────
#  FILE STORE
# ─────────────────────────────────────────────

class FileStore:
    def save(self, customer: str, cloud: str, payload: dict) -> dict:
        slug = _slug(customer)
        d = DATA_DIR / slug
        d.mkdir(parents=True, exist_ok=True)
        doc = {
            'customer': customer,
            'cloud': cloud,
            'updated': _now(),
            **{k: v for k, v in payload.items() if k != 'cloud'},
        }
        (d / f'{cloud}.json').write_text(json.dumps(doc, indent=2))
        return {'ok': True, 'id': f'{slug}/{cloud}'}

    def load(self, customer: str, cloud: str) -> dict | None:
        slug = _slug(customer)
        p = DATA_DIR / slug / f'{cloud}.json'
        if not p.exists():
            return None
        return json.loads(p.read_text())

    def list_customers(self) -> list[dict]:
        if not DATA_DIR.exists():
            return []
        result = []
        for d in sorted(DATA_DIR.iterdir()):
            if not d.is_dir():
                continue
            clouds = [p.stem for p in sorted(d.glob('*.json'))
                      if p.stem in PRODUCTS]
            if not clouds:
                continue
            # Read customer name from first file
            name = d.name
            for p in d.glob('*.json'):
                try:
                    doc = json.loads(p.read_text(encoding='utf-8'))
                    name = doc.get('customer', d.name)
                    break
                except Exception:
                    pass
            result.append({'customer': name, 'slug': d.name, 'clouds': clouds})
        return result

    def delete(self, customer: str, cloud: str) -> bool:
        slug = _slug(customer)
        p = DATA_DIR / slug / f'{cloud}.json'
        if p.exists():
            p.unlink()
            # Remove empty customer dir
            try:
                (DATA_DIR / slug).rmdir()
            except OSError:
                pass
            return True
        return False

    @property
    def backend_name(self):
        return f'file:{DATA_DIR}'


# ─────────────────────────────────────────────
#  COUCHDB STORE (pure urllib — no extra deps)
# ─────────────────────────────────────────────

class CouchDBStore:
    def __init__(self, url: str, db: str):
        self.base = f'{url}/{db}'
        self._ensure_db(url, db)

    def _ensure_db(self, url, db):
        try:
            req = urllib.request.Request(f'{url}/{db}', method='PUT')
            urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            if e.code != 412:  # 412 = already exists
                raise

    def _doc_id(self, customer: str, cloud: str) -> str:
        return f'{_slug(customer)}_{cloud}'

    def _get(self, doc_id: str) -> dict | None:
        try:
            with urllib.request.urlopen(f'{self.base}/{doc_id}', timeout=5) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def _put(self, doc_id: str, doc: dict) -> dict:
        data = json.dumps(doc).encode()
        req = urllib.request.Request(
            f'{self.base}/{doc_id}', data=data, method='PUT',
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def save(self, customer: str, cloud: str, payload: dict) -> dict:
        doc_id = self._doc_id(customer, cloud)
        existing = self._get(doc_id)
        doc = {
            '_id': doc_id,
            'customer': customer,
            'cloud': cloud,
            'updated': _now(),
            **{k: v for k, v in payload.items() if k != 'cloud'},
        }
        if existing:
            doc['_rev'] = existing['_rev']
        resp = self._put(doc_id, doc)
        return {'ok': True, 'id': doc_id, 'rev': resp.get('rev')}

    def load(self, customer: str, cloud: str) -> dict | None:
        return self._get(self._doc_id(customer, cloud))

    def list_customers(self) -> list[dict]:
        # Use _all_docs with include_docs
        url = f'{self.base}/_all_docs?include_docs=true'
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                data = json.loads(r.read())
        except Exception:
            return []
        # Aggregate by slug
        by_slug = {}
        for row in data.get('rows', []):
            doc = row.get('doc', {})
            if doc.get('_id', '').startswith('_design'):
                continue
            slug = _slug(doc.get('customer', ''))
            if slug not in by_slug:
                by_slug[slug] = {'customer': doc.get('customer', slug), 'slug': slug, 'clouds': []}
            by_slug[slug]['clouds'].append(doc.get('cloud', ''))
        return sorted(by_slug.values(), key=lambda x: x['customer'].lower())

    def delete(self, customer: str, cloud: str) -> bool:
        doc_id = self._doc_id(customer, cloud)
        existing = self._get(doc_id)
        if not existing:
            return False
        url = f'{self.base}/{doc_id}?rev={existing["_rev"]}'
        req = urllib.request.Request(url, method='DELETE')
        try:
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            return False

    @property
    def backend_name(self):
        return f'couchdb:{self.base}'


# ─────────────────────────────────────────────
#  AUTO-SELECT BACKEND
# ─────────────────────────────────────────────

def _make_backend():
    if COUCHDB_URL:
        try:
            with urllib.request.urlopen(COUCHDB_URL, timeout=3) as r:
                info = json.loads(r.read())
                if 'couchdb' in info:
                    store = CouchDBStore(COUCHDB_URL, COUCHDB_DB)
                    print(f'[store] CouchDB backend: {store.base}')
                    return store
        except Exception as e:
            print(f'[store] CouchDB unreachable ({e}), falling back to file store')
    store = FileStore()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f'[store] File backend: {DATA_DIR.resolve()}')
    return store


# Singleton — imported by app.py
storage = _make_backend()
