"""
rag.py — RAG layer for Terraflow Studio.

Backends (auto-selected at runtime):
  ChromaDB + embeddings — when `chromadb` is installed AND EMBEDDING_PROVIDER is set
  BM25 (pure Python)    — fallback, no extra dependencies required

Embedding environment variables:
  EMBEDDING_PROVIDER   ollama | openai | gemini
  EMBEDDING_MODEL      nomic-embed-text | text-embedding-3-small | text-embedding-004
  EMBEDDING_BASE_URL   http://localhost:11434  (Ollama only, default shown)
  LLM_API_KEY          used for openai / gemini embeddings (same key as LLM)
"""
import json, math, re, os, pathlib, urllib.request
from collections import Counter

BASE_DIR    = pathlib.Path(__file__).resolve().parent
DOCS_DIR    = BASE_DIR / 'rag_docs'
_DATA_DIR   = pathlib.Path(os.environ.get('ODB_DATA_DIR', '')).resolve() if os.environ.get('ODB_DATA_DIR') else BASE_DIR / 'data'
INDEX_PATH  = _DATA_DIR / 'rag_index.json'
CHROMA_PATH = _DATA_DIR / 'chroma'

CHUNK_WORDS     = 350
OVERLAP_WORDS   = 60
BM25_K1         = 1.5
BM25_B          = 0.75
TITLE_BOOST     = 3.0  # multiplier when a query term appears in the section heading
CHUNKER_VERSION = 3    # bump when chunking logic changes to force auto-rebuild
COLLECTION    = 'odb_terraform'


# ── shared: chunking ──────────────────────────────────────────────────────────

_STOP = frozenset({
    'a','an','the','and','or','but','in','on','at','to','for','of','with',
    'by','from','is','are','was','were','be','been','has','have','had',
    'do','does','did','will','would','could','should','may','might','shall',
    'not','no','so','if','as','it','its','this','that','these','those',
    'how','what','when','where','why','which','who',
    'use','used','uses','using','get','set','add','can','let','make',
    'need','needs','must','also','all','any','each','per','via',
    'enable','enabled','disable','disabled','create','delete','update',
})

def _tokenize(text):
    toks = re.findall(r'\b[a-z0-9_]+\b', text.lower())
    # Remove stop words only from queries (short inputs); keep all tokens for indexing
    return toks

def _tokenize_query(text):
    toks = re.findall(r'\b[a-z0-9_]+\b', text.lower())
    filtered = [t for t in toks if t not in _STOP and len(t) > 1]
    return filtered if filtered else toks  # fall back to unfiltered if everything stripped

def _chunk_file(path):
    """Chunk by markdown section (## heading or --- divider).
    Falls back to fixed-word chunking only when a section exceeds CHUNK_WORDS."""
    text = path.read_text(encoding='utf-8')
    stem = path.stem
    default_title = stem.replace('_', ' ').title()

    # Split on lines that start a new heading (any level) or are a --- divider
    sections = re.split(r'(?m)^(?=#{1,6}\s)', text)

    chunks, seq = [], 0
    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Extract heading as the title for this section
        first_line = section.split('\n', 1)[0]
        if re.match(r'^#{1,6}\s', first_line):
            title = re.sub(r'^#+\s*', '', first_line).strip()
        else:
            title = default_title

        words = section.split()
        if not words:
            continue

        if len(words) <= CHUNK_WORDS:
            chunks.append({
                'id':     f'{stem}_{seq}',
                'source': path.name,
                'title':  title,
                'text':   section,
            })
            seq += 1
        else:
            # Section too long — sub-chunk with overlap, keep title prefix
            i = 0
            while i < len(words):
                chunks.append({
                    'id':     f'{stem}_{seq}',
                    'source': path.name,
                    'title':  title,
                    'text':   ' '.join(words[i : i + CHUNK_WORDS]),
                })
                seq += 1
                i += CHUNK_WORDS - OVERLAP_WORDS
    return chunks

def _all_chunks():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    chunks = []
    for p in sorted(DOCS_DIR.glob('*.md')) + sorted(DOCS_DIR.glob('*.txt')):
        chunks.extend(_chunk_file(p))
    return chunks


# ── embedding ─────────────────────────────────────────────────────────────────

def _emb_provider():
    return os.environ.get('EMBEDDING_PROVIDER', '').lower().strip()

def _emb_model():
    defaults = {
        'ollama': 'nomic-embed-text',
        'openai': 'text-embedding-3-small',
        'gemini': 'text-embedding-004',
    }
    return os.environ.get('EMBEDDING_MODEL', defaults.get(_emb_provider(), ''))

def _embed_batch(texts):
    """Embed a list of strings. Returns list of float vectors."""
    provider = _emb_provider()

    if provider == 'ollama':
        base  = os.environ.get('EMBEDDING_BASE_URL', 'http://localhost:11434').rstrip('/')
        model = _emb_model()
        vecs  = []
        for text in texts:
            body = json.dumps({'model': model, 'input': text}).encode()
            req  = urllib.request.Request(
                f'{base}/api/embed', data=body,
                headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                vecs.append(json.loads(r.read())['embeddings'][0])
        return vecs

    if provider == 'openai':
        import openai
        client = openai.OpenAI(api_key=os.environ.get('LLM_API_KEY'))
        resp   = client.embeddings.create(model=_emb_model(), input=texts)
        return [d.embedding for d in resp.data]

    if provider == 'gemini':
        import google.generativeai as genai
        genai.configure(api_key=os.environ.get('LLM_API_KEY'))
        m = f'models/{_emb_model()}'
        return [genai.embed_content(model=m, content=t)['embedding'] for t in texts]

    raise RuntimeError(f'Unknown EMBEDDING_PROVIDER: {provider!r}')

def _embed_one(text):
    return _embed_batch([text])[0]


# ── backend selector ──────────────────────────────────────────────────────────

def _use_chroma():
    """True when chromadb is importable AND an embedding provider is configured."""
    if not _emb_provider():
        return False
    try:
        import chromadb  # noqa: F401
        return True
    except ImportError:
        return False


# ── ChromaDB backend ──────────────────────────────────────────────────────────

_chroma_client = None

def _get_client():
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _chroma_client

def _chroma_rebuild(chunks):
    client = _get_client()
    # get_or_create avoids a delete+create race in the Rust backend;
    # then we clear all existing documents before re-adding.
    col = client.get_or_create_collection(COLLECTION, metadata={'hnsw:space': 'cosine'})
    existing_ids = col.get(include=[])['ids']
    if existing_ids:
        col.delete(ids=existing_ids)
    if not chunks:
        return 0
    BATCH = 100
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        vecs  = _embed_batch([c['text'] for c in batch])
        col.add(
            ids        = [c['id']     for c in batch],
            documents  = [c['text']   for c in batch],
            embeddings = vecs,
            metadatas  = [{'source': c['source']} for c in batch],
        )
    return len(chunks)

def _chroma_retrieve(query, k):
    client = _get_client()
    try:
        col = client.get_collection(COLLECTION)
    except Exception:
        return []
    n = col.count()
    if n == 0:
        return []
    res = col.query(query_embeddings=[_embed_one(query)], n_results=min(k, n))
    return [
        {'id': doc_id, 'source': meta['source'], 'text': doc}
        for doc_id, doc, meta in zip(
            res['ids'][0], res['documents'][0], res['metadatas'][0]
        )
    ]

def _chroma_stats():
    client = _get_client()
    try:
        col    = client.get_collection(COLLECTION)
        n      = col.count()
        metas  = col.get(include=['metadatas'])['metadatas'] or []
        n_docs = len({m['source'] for m in metas})
    except Exception:
        n, n_docs = 0, 0
    return {
        'backend':    'chroma',
        'n_chunks':   n,
        'n_docs':     n_docs,
        'n_terms':    0,
        'index_path': str(CHROMA_PATH),
        'docs_dir':   str(DOCS_DIR),
    }


# ── BM25 backend ──────────────────────────────────────────────────────────────

_index_cache = None

def _invalidate_bm25():
    global _index_cache
    _index_cache = None

def _bm25_rebuild(chunks):
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not chunks:
        INDEX_PATH.write_text(json.dumps({'chunks': [], 'idf': {}, 'avg_len': 1, 'n_docs': 0}))
        _invalidate_bm25()
        return 0
    token_sets = []
    for c in chunks:
        toks           = _tokenize(c['text'])
        c['tf']        = dict(Counter(toks))
        c['length']    = len(toks)
        c['title_toks']= list(set(_tokenize(c.get('title', ''))))
        token_sets.append(set(toks))
    N       = len(chunks)
    idf     = {}
    for term in {t for ts in token_sets for t in ts}:
        df        = sum(1 for ts in token_sets if term in ts)
        idf[term] = math.log((N - df + 0.5) / (df + 0.5) + 1)
    avg_len = sum(c['length'] for c in chunks) / N
    INDEX_PATH.write_text(json.dumps(
        {'chunks': chunks, 'idf': idf, 'avg_len': avg_len, 'n_docs': N,
         'chunker_version': CHUNKER_VERSION},
        indent=2,
    ))
    _invalidate_bm25()
    return N

def _load_bm25():
    global _index_cache
    if _index_cache is None:
        needs_rebuild = (
            not INDEX_PATH.exists() or
            json.loads(INDEX_PATH.read_text(encoding='utf-8')).get('chunker_version', 0) != CHUNKER_VERSION
        )
        if needs_rebuild:
            _bm25_rebuild(_all_chunks())
        _index_cache = json.loads(INDEX_PATH.read_text(encoding='utf-8'))
    return _index_cache

def _bm25_retrieve(query, k):
    idx    = _load_bm25()
    chunks = idx.get('chunks', [])
    if not chunks:
        return []
    idf     = idx.get('idf', {})
    avg_len = idx.get('avg_len', 1) or 1
    q_toks  = _tokenize_query(query)
    scores  = []
    for chunk in chunks:
        tf          = chunk.get('tf', {})
        doc_len     = chunk.get('length', 1) or 1
        title_toks  = set(chunk.get('title_toks', []))
        score = sum(
            idf[t]
            * (tf.get(t, 0) * (BM25_K1 + 1))
            / (tf.get(t, 0) + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / avg_len))
            * (TITLE_BOOST if t in title_toks else 1.0)
            for t in q_toks if t in idf
        )
        scores.append((score, chunk))
    scores.sort(key=lambda x: x[0], reverse=True)
    return [c for s, c in scores[:k] if s > 0]

def _bm25_stats():
    idx = _load_bm25()
    return {
        'backend':    'bm25',
        'n_chunks':   len(idx.get('chunks', [])),
        'n_docs':     idx.get('n_docs', 0),
        'n_terms':    len(idx.get('idf', {})),
        'index_path': str(INDEX_PATH),
        'docs_dir':   str(DOCS_DIR),
    }


# ── source URL registry (update when new docs are crawled) ───────────────────

_AWS_BASE  = 'https://docs.oracle.com/en-us/iaas/Content/database-at-aws/oaaws.htm'
_AZ_BASE   = 'https://docs.oracle.com/en-us/iaas/Content/database-at-azure/oaa.htm'
_GCP_BASE  = 'https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/home.htm'

SOURCE_URLS = {
    # AWS
    'aws_odb_network.md':         _AWS_BASE,
    'aws_exadata_infra.md':       _AWS_BASE,
    'aws_vm_cluster.md':          _AWS_BASE,
    'aws_peering_avmcluster.md':  _AWS_BASE,
    'aws_autonomous_database.md': _AWS_BASE,
    'aws_networking_dns.md':      _AWS_BASE,
    'aws_networking_advanced.md': _AWS_BASE,
    'aws_gotchas.md':             _AWS_BASE,
    'aws_cloudformation.md':      _AWS_BASE,
    'aws_onboarding.md':               'https://docs.oracle.com/en-us/iaas/Content/database-at-aws/oaaws-onboard.htm',
    'aws_subscription_sharing.md':    'https://docs.oracle.com/en-us/iaas/Content/database-at-aws/onboard-multi.htm',
    'aws_hadr.md':                     'https://docs.oracle.com/en-us/iaas/Content/database-at-aws-exadata-awsbc/awsbc-business-continuity-hadr.html',
    'azure_onboarding.md':            'https://docs.oracle.com/en-us/iaas/Content/database-at-azure/oaaonboard.htm',
    'azure_hadr.md':                  'https://docs.oracle.com/en-us/iaas/Content/database-at-azure/azubc-business-continuity-hadr.html',
    'gcp_kms_tde.md':                 'https://docs.oracle.com/en-us/iaas/exadatacloud/doc/gcp-kms-integration-for-oracle-database-at-google-cloud.html',
    'gcp_exascale.md':                'https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/gcpcr-create-exascale-vm-cluster.html',
    'gcp_onboarding.md':              'https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/onboard.htm',
    'gcp_hadr.md':                    'https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/gcpbc-business-continuity-hadr.html',
    # Azure
    'azure_resources.md':         _AZ_BASE,
    'azure_network_anchor.md':    'https://docs.oracle.com/en-us/iaas/Content/database-at-azure/azucr-create-network-anchor.html',
    'azure_network_design.md':    'https://docs.oracle.com/en-us/iaas/Content/database-at-azure/network-anchor-design.htm',
    # GCP
    'gcp_resources.md':           _GCP_BASE,
    'gcp_networking_dns.md':      _GCP_BASE,
    'gcp_networking_advanced.md': _GCP_BASE,
    'gcp_gotchas.md':             _GCP_BASE,
    # MAA / multicloud
    'maa_multicloud.md':          'https://docs.oracle.com/en/database/oracle/oracle-database/19/haovw/multicloud1.html',
    'multicloud_hub.md':          'https://docs.oracle.com/en-us/iaas/Content/multicloud-hub/home.htm',
    # OCI
    'oci_database.md':            'https://docs.oracle.com/en-us/iaas/Content/Database/Concepts/databaseoverview.htm',
}

DOC_LABELS = {
    'https://docs.oracle.com/en-us/iaas/Content/database-at-aws/oaaws-onboard.htm':                      'Oracle AI DB@AWS Onboarding',
    'https://docs.oracle.com/en-us/iaas/Content/database-at-aws/onboard-multi.htm':                     'Oracle AI DB@AWS Subscription Sharing',
    'https://docs.oracle.com/en-us/iaas/Content/database-at-aws-exadata-awsbc/awsbc-business-continuity-hadr.html': 'Oracle AI DB@AWS HADR',
    'https://docs.oracle.com/en-us/iaas/Content/database-at-azure/oaaonboard.htm':                      'Oracle AI DB@Azure Onboarding',
    'https://docs.oracle.com/en-us/iaas/Content/database-at-azure/azubc-business-continuity-hadr.html': 'Oracle AI DB@Azure HADR',
    'https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/onboard.htm':                           'Oracle AI DB@GCP Onboarding',
    'https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/gcpbc-business-continuity-hadr.html':   'Oracle AI DB@GCP HADR',
    _AWS_BASE:  'Oracle AI DB@AWS Docs',
    _AZ_BASE:   'Oracle AI DB@Azure Docs',
    'https://docs.oracle.com/en-us/iaas/Content/database-at-azure/network-anchor-design.htm': 'Azure Network Anchor Design',
    _GCP_BASE:  'Oracle AI DB@GCP Docs',
    'https://docs.oracle.com/en/database/oracle/oracle-database/19/haovw/multicloud1.html': 'Oracle MAA for Multicloud',
    'https://docs.oracle.com/en-us/iaas/Content/multicloud-hub/home.htm': 'Oracle Multicloud Hub',
    'https://docs.oracle.com/en-us/iaas/Content/Database/Concepts/databaseoverview.htm': 'OCI Database Docs',
}


def source_links(chunks):
    """Return deduplicated list of {url, label} for the given chunk list."""
    seen, links = set(), []
    for c in chunks:
        url = SOURCE_URLS.get(c.get('source', ''))
        if url and url not in seen:
            seen.add(url)
            links.append({'url': url, 'label': DOC_LABELS.get(url, 'Oracle Docs')})
    return links


# ── public API ────────────────────────────────────────────────────────────────

def rebuild():
    """Index all docs in DOCS_DIR. Returns chunk count."""
    chunks = _all_chunks()
    if _use_chroma():
        return _chroma_rebuild(chunks)
    return _bm25_rebuild(chunks)

def retrieve(query, k=5):
    """Return top-k chunks by relevance for query."""
    if _use_chroma():
        return _chroma_retrieve(query, k)
    return _bm25_retrieve(query, k)

def retrieve_hybrid(query, k=5):
    """Merge ChromaDB semantic + BM25 keyword results.
    Interleaves both ranked lists (deduped by chunk id) so acronym/keyword
    queries (strong in BM25) and semantic queries (strong in ChromaDB) both surface.
    Falls back to single-backend retrieve when only one is available.
    """
    if not _use_chroma():
        return _bm25_retrieve(query, k)

    chroma = _chroma_retrieve(query, k)
    bm25   = _bm25_retrieve(query, k)

    # BM25 top result leads (strong for keyword/acronym queries),
    # then interleave chroma and bm25 tails for semantic coverage.
    seen, merged = set(), []
    for chunk in (bm25[:1] + [c for pair in zip(chroma, bm25[1:]) for c in pair] + chroma + bm25):
        if chunk['id'] not in seen:
            seen.add(chunk['id'])
            merged.append(chunk)
    return merged[:k]

def build_context(query, k=5):
    """Return a formatted context block for LLM system prompt injection."""
    chunks = retrieve(query, k)
    if not chunks:
        return ''
    return '\n\n---\n\n'.join(f'[{c["source"]}]\n{c["text"]}' for c in chunks)

def index_stats():
    if _use_chroma():
        return _chroma_stats()
    return _bm25_stats()

def pdf_to_markdown(file_bytes: bytes, filename: str) -> str:
    """Extract text from a PDF and return it as markdown. Requires pypdf."""
    try:
        from pypdf import PdfReader
        import io
    except ImportError:
        raise RuntimeError('pypdf is not installed. Run: pip install pypdf')

    reader = PdfReader(io.BytesIO(file_bytes))
    stem  = pathlib.Path(filename).stem
    lines = [f'# {stem}', '']

    for idx, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or '').strip()
        if not text:
            continue
        lines.append(f'## Page {idx}')
        lines.append('')
        for line in text.splitlines():
            line = line.strip()
            if line:
                lines.append(line)
        lines.append('')

    if len(lines) <= 2:
        raise RuntimeError(
            'No text could be extracted from this PDF. '
            'Scanned/image-only PDFs are not supported.'
        )
    return '\n'.join(lines)


def docx_to_markdown(file_bytes: bytes, filename: str) -> str:
    """Extract text from a .docx file and return it as markdown. Requires python-docx."""
    try:
        from docx import Document
        from docx.oxml.ns import qn
        import io
    except ImportError:
        raise RuntimeError('python-docx is not installed. Run: pip install python-docx')

    doc   = Document(io.BytesIO(file_bytes))
    stem  = pathlib.Path(filename).stem
    lines = [f'# {stem}', '']

    for para in doc.paragraphs:
        text  = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else ''
        if 'Heading 1' in style:
            lines.append(f'# {text}')
        elif 'Heading 2' in style:
            lines.append(f'## {text}')
        elif 'Heading 3' in style:
            lines.append(f'### {text}')
        elif 'Heading' in style:
            lines.append(f'## {text}')
        else:
            lines.append(text)
        lines.append('')

    return '\n'.join(lines)


def pptx_to_markdown(file_bytes: bytes, filename: str) -> str:
    """Extract text from a .pptx file and return it as a markdown string.
    Each slide becomes a ## section. Requires python-pptx."""
    try:
        from pptx import Presentation
        from pptx.util import Pt
        import io
    except ImportError:
        raise RuntimeError(
            'python-pptx is not installed. '
            'Run: pip install python-pptx'
        )

    prs  = Presentation(io.BytesIO(file_bytes))
    stem = pathlib.Path(filename).stem
    lines = [f'# {stem}', '']

    for idx, slide in enumerate(prs.slides, 1):
        title_text = ''
        body_parts = []

        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            text = shape.text_frame.text.strip()
            if not text:
                continue
            # Treat the first non-empty shape (usually the title placeholder) as the heading
            if not title_text and shape.shape_type in (13, 14, 15, 19) or (
                hasattr(shape, 'placeholder_format') and
                shape.placeholder_format is not None and
                shape.placeholder_format.idx == 0
            ):
                title_text = text
            else:
                body_parts.append(text)

        heading = title_text or f'Slide {idx}'
        lines.append(f'## {heading}')
        lines.append('')
        for part in body_parts:
            for line in part.splitlines():
                line = line.strip()
                if line:
                    lines.append(line)
        lines.append('')

    return '\n'.join(lines)

def invalidate_cache():
    global _chroma_client
    _chroma_client = None
    _invalidate_bm25()
