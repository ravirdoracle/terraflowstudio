"""
Terraflow Studio — Flask Application
Generates modular Terraform code for Oracle AI Database@AWS and AI DB@GCP.
All HCL output is rendered from Jinja2 templates in templates/tf/.
"""

# Load .env FIRST — before any module reads os.environ at import time
try:
    from dotenv import load_dotenv
    import pathlib as _pl
    _env_path = _pl.Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=_env_path, override=True)
except ImportError:
    import pathlib as _pl, os as _os
    _env_path = _pl.Path(__file__).parent / '.env'
    if _env_path.exists():
        for _line in _env_path.read_text(encoding='utf-8').splitlines():
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                _k = _k.strip(); _v = _v.strip().strip('"').strip("'")
                if _k: _os.environ[_k] = _v

import io
import hmac
import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from flask import Flask, render_template, request, jsonify, send_file, make_response
from store import storage
import llm as llm_module
import github as github_module
import rag as rag_module
import regions
import shapes
import clouds.registry as cloud_registry
from core.selftest import Recorder
import clouds.aws.routes as aws_routes
import clouds.gcp.routes as gcp_routes
import clouds.azure.routes as azure_routes
import oci.routes as oci_routes

from core.helpers import render_tf, is_ref, parse_list, tf_bool
from clouds.aws.generator import (
    mod0_main, mod0_vars, mod0_outputs, mod0_tfvars,
    mod1_main, mod1_vars, mod1_outputs, mod1_tfvars,
    mod2_main, mod2_vars, mod2_outputs, mod2_tfvars,
    mod3_main, mod3_vars, mod3_outputs, mod3_tfvars,
    mod4_main, mod4_vars, mod4_outputs,
    build_root_main, build_root_vars, build_root_tfvars,
    _aws_net_defaults, _aws_infra_defaults, _aws_peer_defaults,
    _aws_cluster_defaults, _aws_avmc_defaults,
    generate_aws_tf, generate_cfn,
)
from clouds.gcp.generator import (
    _gcp_net_defaults, _gcp_infra_defaults, _gcp_cluster_defaults,
    generate_gcp_tf,
    _GCP_MOD_NET, _GCP_MOD_INFRA, _GCP_MOD_CLUSTER,
)
from clouds.azure.generator import (
    azure_vnet_main, azure_vnet_vars, azure_vnet_outputs, azure_vnet_tfvars,
    azure_infra_main, azure_infra_vars, azure_infra_outputs, azure_infra_tfvars,
    azure_cluster_main, azure_cluster_vars, azure_cluster_outputs, azure_cluster_tfvars,
    azure_build_root_main, azure_build_root_vars, azure_build_root_tfvars,
    _azure_vnet_defaults, _azure_infra_defaults, _azure_cluster_defaults,
    generate_azure_tf,
)
from oci import generate_oci_dg_tf, generate_oci_db_tf

app = Flask(__name__)


@app.before_request
def require_app_authentication():
    """Protect every page and API when network-access credentials are configured."""
    username = os.environ.get('APP_AUTH_USER', '')
    password = os.environ.get('APP_AUTH_PASSWORD', '')
    if not username and not password:
        return None
    if not username or not password:
        return jsonify({'error': 'Set both APP_AUTH_USER and APP_AUTH_PASSWORD.'}), 503
    auth = request.authorization
    if auth and auth.type == 'basic':
        user_ok = hmac.compare_digest((auth.username or '').encode('utf-8'), username.encode('utf-8'))
        password_ok = hmac.compare_digest((auth.password or '').encode('utf-8'), password.encode('utf-8'))
        if user_ok and password_ok:
            return None
    response = make_response('Authentication required.', 401)
    response.headers['WWW-Authenticate'] = 'Basic realm="Terraflow Studio", charset="UTF-8"'
    response.headers['Cache-Control'] = 'no-store'
    return response

# Each cloud owns its page route. Registering blueprints here is the only place
# app.py needs to know which clouds exist.
for _bp in (aws_routes.bp, gcp_routes.bp, azure_routes.bp, oci_routes.bp):
    app.register_blueprint(_bp)


def generate_all(data: dict) -> dict:
    # CloudFormation is an output format rather than a cloud, so it is checked
    # before the registry: it only applies to AWS and produces a single file.
    if data.get('iac_tool') == 'cloudformation':
        return {'cfn': generate_cfn(data)}
    return cloud_registry.get(data.get('cloud', 'aws')).generate(data)

# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────
#  LLM ROUTES
# ─────────────────────────────────────────────

@app.route('/api/llm/info', methods=['GET'])
def api_llm_info():
    return jsonify(llm_module.provider_info())

@app.route('/api/llm/debug', methods=['GET'])
def api_llm_debug():
    import os as _os, pathlib as _pl
    key = _os.environ.get('LLM_API_KEY', '')
    env_path = _pl.Path(__file__).parent / '.env'
    try:
        import dotenv; dotenv_installed = True
    except ImportError:
        dotenv_installed = False
    return jsonify({
        'env_file_path':    str(env_path),
        'env_file_exists':  env_path.exists(),
        'dotenv_installed': dotenv_installed,
        'LLM_PROVIDER':     _os.environ.get('LLM_PROVIDER', '(not set)'),
        'LLM_API_KEY':      f'{key[:8]}...{key[-4:]}' if len(key) > 12 else ('(set, short)' if key else '(not set)'),
        'LLM_MODEL':        _os.environ.get('LLM_MODEL', '(not set)'),
        'LLM_BASE_URL':     _os.environ.get('LLM_BASE_URL', '(not set)'),
        'LLM_MAX_TOKENS':   _os.environ.get('LLM_MAX_TOKENS', '(not set)'),
    })

@app.route('/api/llm/chat', methods=['POST'])
def api_llm_chat():
    body = request.get_json(force=True)
    messages = body.get('messages', [])
    if not messages:
        return jsonify({'error': 'messages array is required'}), 400
    try:
        return jsonify({'content': llm_module.chat(messages)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/llm/fill', methods=['POST'])
def api_llm_fill():
    body    = request.get_json(force=True)
    prompt  = body.get('prompt', '').strip()
    cloud   = body.get('cloud', 'aws')
    current = body.get('current', {})
    if not prompt:
        return jsonify({'error': 'prompt is required'}), 400
    system_msg = """You are a Terraform infrastructure assistant for Oracle AI Database@AWS and AI DB@GCP.
Return ONLY a raw JSON object — no markdown, no code fences, no explanation outside the JSON.

Output format (two keys, no others):
{"payload": { ... }, "explanation": "one sentence"}

Payload keys (use EXACTLY these names, omit unused ones):
  cloud            "aws" or "gcp"
  aws_networks     list of ODB Network objects
  aws_infras       list of Exadata Infrastructure objects
  aws_peerings     list of Network Peering objects
  aws_clusters     list of VM Cluster objects
  aws_avmclusters  list of Autonomous VM Cluster objects
  aws_autonomous_dbs list of AWS Autonomous Database (Serverless) objects
  aws_oci_databases list of OCI Database objects
  gcp_networks     list of GCP ODB Network objects
  gcp_infras       list of GCP Exadata Infrastructure objects
  gcp_clusters     list of GCP VM Cluster objects
  gcp_autonomous_dbs list of GCP Autonomous AI Database (Serverless) objects

Rules: module_name is a unique snake_case slug. shape: Exadata.X11M (default), X10M, X9M.
license_model: LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE. db_name: max 8 alphanumeric chars.
availability_zone_id examples: use1-az4, use1-az6, use2-az1, usw2-az3.

gcp_autonomous_dbs entries are Serverless: Oracle runs the fleet, so they take NO
infra_ref and NO gcp_oracle_zone. Fields: autonomous_database_id (lowercase, hyphens
allowed), database (max 30 alphanumeric, no hyphens), display_name, location,
network_ref (an ODB Network module_name — the database attaches to its client
subnet), db_workload (OLTP, DW, AJD or APEX), db_version (23ai or 19c), db_edition
(ENTERPRISE_EDITION or STANDARD_EDITION), license_type (LICENSE_INCLUDED or
BRING_YOUR_OWN_LICENSE), compute_count (ECPUs, minimum 2), data_storage_size_gb,
is_auto_scaling_enabled, is_storage_auto_scaling_enabled,
backup_retention_period_days (1-60), mtls_connection_required. Never emit an
admin_password — it is supplied at apply time.

aws_autonomous_dbs entries are Serverless too: no infra_ref. Fields: display_name,
db_name (letter first, max 30 alphanumeric), network_ref (an aws_networks
module_name), db_workload (OLTP, LH, AJD or APEX), license_model, compute_count
(ECPUs), data_storage_size_in_tbs (whole number, 1-384), admin_password_source
(write_only or secrets_manager; secrets_manager also needs secret_arn and
secret_iam_role_arn). Optional: db_version, is_auto_scaling_enabled,
is_auto_scaling_for_storage_enabled, backup_retention_period_in_days,
is_mtls_connection_required. Never emit an admin_password.

Example output for "Exadata infra in us-east-1 az4":
{"payload":{"cloud":"aws","aws_networks":[{"module_name":"odb_network","display_name":"ODB Network","client_subnet_cidr":"10.2.0.0/24","backup_subnet_cidr":"10.2.1.0/24"}],"aws_infras":[{"module_name":"odb_infra","display_name":"Exadata Infra","shape":"Exadata.X11M","compute_count":2,"storage_count":3,"availability_zone_id":"use1-az4","network_ref":"odb_network"}]},"explanation":"Created ODB network and Exadata X11M infra in us-east-1 az4."}"""
    # Augment with retrieved knowledge
    rag_context = rag_module.build_context(prompt, k=5)
    if rag_context:
        system_msg += f'\n\nRelevant reference documentation:\n{rag_context}'
    user_msg = f"Cloud: {cloud}\nCurrent: {json.dumps(current)[:3000]}\nRequest: {prompt}\nReturn JSON object."
    try:
        reply = llm_module.chat([{'role':'system','content':system_msg},{'role':'user','content':user_msg}])
        clean = reply.strip()
        # Strip markdown fences anywhere in the response
        clean = re.sub(r'```[a-z]*\n?', '', clean).strip()
        # Skip any preamble text before the opening brace
        start = clean.find('{')
        if start > 0:
            clean = clean[start:]
        # raw_decode parses the first valid JSON object and tolerates trailing text
        result, _ = json.JSONDecoder().raw_decode(clean)
        payload = result.get('payload', {})
        # LLM sometimes puts explanation inside payload — hoist it out
        explanation = result.get('explanation', '') or payload.pop('explanation', '')
        return jsonify({'payload': payload, 'explanation': explanation,
                        'rag_sources': [c['source'] for c in rag_module.retrieve(prompt, k=5)]})
    except json.JSONDecodeError as e:
        return jsonify({'error': f'LLM returned invalid JSON: {e}', 'raw': reply[:500]}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/llm/explain', methods=['POST'])
def api_llm_explain():
    body     = request.get_json(force=True)
    content  = body.get('content', '').strip()
    filename = body.get('filename', 'terraform file').strip()
    if not content:
        return jsonify({'error': 'content is required'}), 400
    system_msg = (
        "You are a senior Terraform and Oracle Database infrastructure engineer.\n"
        "Explain the following Terraform HCL file in clear, concise language.\n\n"
        "Structure your explanation as:\n"
        "1. What this file does (1-2 sentences)\n"
        "2. Key resources or variables defined, with their purpose\n"
        "3. Notable configuration choices, cross-module dependencies, or gotchas\n\n"
        "Be concrete and technical. Use the resource/variable names from the code. "
        "Keep the total response under 320 words. Plain text, no markdown."
    )
    rag_query   = (filename + ' ' + content[:400]).strip()
    rag_context = rag_module.build_context(rag_query, k=3)
    if rag_context:
        system_msg += f'\n\nRelevant reference documentation:\n{rag_context}'
    user_msg = f'File: {filename}\n\n```hcl\n{content[:8000]}\n```'
    try:
        reply = llm_module.chat([
            {'role': 'system', 'content': system_msg},
            {'role': 'user',   'content': user_msg},
        ])
        return jsonify({'explanation': reply.strip()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
#  AI TOOLS — PLAN EXPLAINER & ERROR TROUBLESHOOTER
# ─────────────────────────────────────────────

def _collect_cidrs(data: dict) -> list[tuple[str, str]]:
    """Return list of (label, cidr_string) from every CIDR field in the payload.

    Which keys hold CIDRs is per-cloud knowledge, so each cloud package supplies
    its own collector. This used to branch aws/else, which silently handed Azure
    payloads to the GCP collector and produced no findings for them at all.
    """
    return cloud_registry.get(data.get('cloud', 'aws')).collect_cidrs(data)


def _check_cidr_overlaps(data: dict) -> list[dict]:
    """Deterministically check for overlapping CIDRs across all networks. Returns findings list."""
    import ipaddress
    findings = []
    cidrs = _collect_cidrs(data)
    parsed = []
    for label, raw in cidrs:
        try:
            parsed.append((label, raw, ipaddress.ip_network(raw, strict=False)))
        except ValueError:
            findings.append({
                'severity': 'medium',
                'category': 'Network Security',
                'resource': label,
                'issue': f'Invalid CIDR format: {raw!r}',
                'recommendation': 'Correct the CIDR notation (e.g. 10.0.0.0/24).',
                'file': '',
            })

    # Check every pair for overlap
    seen = set()
    for i in range(len(parsed)):
        for j in range(i + 1, len(parsed)):
            la, ra, na = parsed[i]
            lb, rb, nb = parsed[j]
            key = tuple(sorted([la, lb]))
            if key in seen:
                continue
            if na.overlaps(nb):
                seen.add(key)
                findings.append({
                    'severity': 'high',
                    'category': 'Network Security',
                    'resource': f'{la}  ↔  {lb}',
                    'issue': f'Overlapping CIDRs: {ra} and {rb} share address space.',
                    'recommendation': (
                        'Assign non-overlapping CIDR ranges to each subnet. '
                        'Overlapping ranges will cause routing conflicts and peering failures.'
                    ),
                    'file': '',
                })
    return findings


@app.route('/api/ai/security-review', methods=['POST'])
def api_ai_security_review():
    data  = request.get_json(force=True)
    cloud = data.get('cloud', 'aws')

    # Generate all HCL files from the current payload
    try:
        files = generate_all(data)
    except Exception as e:
        return jsonify({'error': f'Generation failed: {e}'}), 500

    if not files:
        return jsonify({'error': 'No files generated — configure at least one resource first.'}), 400

    # Concatenate file contents for review (cap at 12 000 chars)
    hcl_chunks = []
    total = 0
    for path, content in files.items():
        if path.endswith('.tfvars'):
            continue  # tfvars hold actual values — skip
        snippet = f'### {path}\n{content}\n'
        if total + len(snippet) > 12000:
            break
        hcl_chunks.append(snippet)
        total += len(snippet)
    hcl_body = '\n'.join(hcl_chunks)

    rag_context = rag_module.build_context(
        f'security best practices oracle database {cloud} terraform network access encryption backup', k=5)

    _delp_check = (
        "- deletion_protection disabled on prod-like resources"
        " (GCP: google_oracle_database_* resources support this field)\n"
        if cloud == 'gcp' else
        "- delete_associated_resources enabled on ODB networks"
        " (AWS: setting this true deletes VPCs/subnets on network destroy — risky for prod)\n"
    )
    system_msg = (
        "You are a cloud security engineer specialising in Oracle AI Database@AWS and Oracle AI DB@GCP Terraform configurations.\n"
        "Review the HCL files provided and respond ONLY with a valid JSON object (no markdown, no code fences) matching exactly:\n"
        '{"score":<int 0-100>,"grade":"A|B|C|D|F","summary":"<1 sentence>",'
        '"findings":[{"severity":"critical|high|medium|low|info",'
        '"category":"Network Security|Access Control|Data Protection|Backup & Recovery|Compliance|Best Practice",'
        '"resource":"<resource type or module name>",'
        '"issue":"<concise description of the problem>",'
        '"recommendation":"<specific actionable fix>",'
        '"file":"<file path or empty string>"}]}\n\n'
        "Security checks to perform (check ALL that apply):\n"
        "- Open or overly broad CIDR ranges (0.0.0.0/0 or /8 or /16 on client/backup subnets)\n"
        "- Variables containing passwords, keys, or tokens missing sensitive = true\n"
        "- SSH public keys left as empty list or placeholder\n"
        "- Auto-backup disabled or recovery window < 7 days\n"
        "- Customer contacts not configured (maintenance notifications)\n"
        + _delp_check +
        "- S3 or Zero-ETL access enabled without clear need (check display names for 'prod'/'prd')\n"
        "- Maintenance window set to NO_PREFERENCE (recommend CUSTOM_PREFERENCE for prod)\n"
        "- Missing or empty tags / labels\n"
        "- License model check (BRING_YOUR_OWN_LICENSE without OCI confirmation)\n"
        "- Hardcoded non-reference values for cross-module IDs (should use module.x.output)\n"
        "- score: 100 = no issues. Deduct: critical=-20, high=-10, medium=-5, low=-2, info=-0. Min 0.\n"
        "- findings: only real issues found in the code. Empty array [] if config is clean.\n"
        "Return ONLY the JSON object."
    )
    if rag_context:
        system_msg += f'\n\nRelevant ODB security documentation:\n{rag_context}'

    user_msg = f'Cloud: {cloud.upper()}\nFiles reviewed: {len(files)}\n\n{hcl_body}'
    try:
        raw = llm_module.chat([
            {'role': 'system', 'content': system_msg},
            {'role': 'user',   'content': user_msg},
        ])
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw.strip(), flags=re.MULTILINE)
        result = json.loads(raw)
        # Merge deterministic CIDR overlap findings (always run, never hallucinated)
        cidr_findings = _check_cidr_overlaps(data)
        if cidr_findings:
            result.setdefault('findings', [])
            result['findings'] = cidr_findings + result['findings']
            # Recompute score: each high finding costs 10 points
            penalty = sum(10 for f in cidr_findings if f['severity'] == 'high') + \
                      sum(5  for f in cidr_findings if f['severity'] == 'medium')
            result['score'] = max(0, result.get('score', 100) - penalty)
            # Recompute grade
            s = result['score']
            result['grade'] = 'A' if s >= 90 else 'B' if s >= 80 else 'C' if s >= 65 else 'D' if s >= 50 else 'F'
        result['files_reviewed'] = len(files)
        return jsonify(result)
    except json.JSONDecodeError:
        return jsonify({'error': 'LLM returned unexpected format', 'raw': raw[:500]}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/explain-plan', methods=['POST'])
def api_ai_explain_plan():
    body      = request.get_json(force=True)
    plan_text = body.get('plan_text', '').strip()
    cloud     = body.get('cloud', 'aws')
    if not plan_text:
        return jsonify({'error': 'plan_text is required'}), 400

    rag_context = rag_module.build_context(
        f'terraform plan {cloud} oracle database changes risks', k=4)

    system_msg = (
        "You are a senior Terraform engineer specialising in Oracle AI Database@AWS and Oracle AI DB@GCP.\n"
        "Analyse the terraform plan output provided by the user and respond ONLY with a valid JSON object "
        "(no markdown, no code fences) matching exactly this schema:\n"
        '{"summary":"<1-2 sentence plain-English summary>","stats":{"add":<int>,"change":<int>,"destroy":<int>},'
        '"changes":[{"action":"add|modify|destroy|replace","resource":"<resource type.name>","note":"<why this matters>"}],'
        '"risks":[{"severity":"high|medium|low","message":"<concise risk description>"}],'
        '"recommendations":["<actionable recommendation>"]}\n\n'
        "Rules:\n"
        "- risks array must only contain REAL risks (destructive ops, replacements, open CIDRs, force-new). Empty array if none.\n"
        "- changes array: include every resource action from the plan. Max 20 entries.\n"
        "- recommendations: practical next steps. 2-4 items.\n"
        "- Return ONLY the JSON object. No other text."
    )
    if rag_context:
        system_msg += f'\n\nRelevant ODB reference documentation:\n{rag_context}'

    user_msg = f'Cloud: {cloud.upper()}\n\nTerraform plan output:\n```\n{plan_text[:10000]}\n```'
    try:
        raw = llm_module.chat([
            {'role': 'system', 'content': system_msg},
            {'role': 'user',   'content': user_msg},
        ])
        # Strip accidental markdown fences
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw.strip(), flags=re.MULTILINE)
        return jsonify(json.loads(raw))
    except json.JSONDecodeError:
        return jsonify({'summary': raw.strip(), 'stats': {}, 'changes': [], 'risks': [], 'recommendations': []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/troubleshoot', methods=['POST'])
def api_ai_troubleshoot():
    body       = request.get_json(force=True)
    error_text = body.get('error_text', '').strip()
    cloud      = body.get('cloud', 'aws')
    if not error_text:
        return jsonify({'error': 'error_text is required'}), 400

    rag_context = rag_module.build_context(
        f'terraform apply error {cloud} oracle database troubleshoot fix {error_text[:300]}', k=5)

    system_msg = (
        "You are a senior Terraform engineer specialising in Oracle AI Database@AWS and Oracle AI DB@GCP.\n"
        "Diagnose the terraform error provided by the user and respond ONLY with a valid JSON object "
        "(no markdown, no code fences) matching exactly this schema:\n"
        '{"root_cause":"<concise 1-sentence root cause>","explanation":"<2-4 sentence detailed explanation>",'
        '"fix_steps":["<step 1>","<step 2>"],"prevention":"<how to prevent this in future>",'
        '"docs_hint":"<relevant doc section or resource type to check, or empty string>"}\n\n'
        "Rules:\n"
        "- fix_steps: ordered, concrete, copy-paste-ready where possible. 2-6 steps.\n"
        "- root_cause: identify the specific Terraform or ODB provider issue, not generic advice.\n"
        "- Return ONLY the JSON object. No other text."
    )
    if rag_context:
        system_msg += f'\n\nRelevant ODB reference documentation:\n{rag_context}'

    user_msg = f'Cloud: {cloud.upper()}\n\nTerraform error:\n```\n{error_text[:8000]}\n```'
    try:
        raw = llm_module.chat([
            {'role': 'system', 'content': system_msg},
            {'role': 'user',   'content': user_msg},
        ])
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw.strip(), flags=re.MULTILINE)
        return jsonify(json.loads(raw))
    except json.JSONDecodeError:
        return jsonify({'root_cause': 'Could not parse response', 'explanation': raw.strip(),
                        'fix_steps': [], 'prevention': '', 'docs_hint': ''})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
#  RAG ROUTES
# ─────────────────────────────────────────────

@app.route('/api/rag/stats', methods=['GET'])
def api_rag_stats():
    return jsonify(rag_module.index_stats())

@app.route('/api/rag/rebuild', methods=['POST'])
def api_rag_rebuild():
    n = rag_module.rebuild()
    return jsonify({'ok': True, 'chunks_indexed': n, **rag_module.index_stats()})

@app.route('/api/rag/search', methods=['POST'])
def api_rag_search():
    body  = request.get_json(force=True)
    query = body.get('query', '').strip()
    k     = int(body.get('k', 5))
    if not query:
        return jsonify({'error': 'query is required'}), 400
    chunks = rag_module.retrieve(query, k)
    return jsonify({'results': [
        {'id': c['id'], 'source': c['source'],
         'title': c.get('title', c['source']), 'text': c['text'][:500]}
        for c in chunks
    ]})

@app.route('/api/rag/docs', methods=['GET'])
def api_rag_docs():
    docs_dir = rag_module.DOCS_DIR
    docs = []
    for p in sorted(docs_dir.glob('*.md')) + sorted(docs_dir.glob('*.txt')):
        stat = p.stat()
        docs.append({
            'name':     p.name,
            'size':     stat.st_size,
            'modified': int(stat.st_mtime),
        })
    return jsonify({'docs': docs, **rag_module.index_stats()})

@app.route('/api/rag/upload', methods=['POST'])
def api_rag_upload():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file provided'}), 400
    name = os.path.basename(f.filename or '')
    if not name:
        return jsonify({'error': 'Invalid filename'}), 400

    allowed = ('.md', '.txt', '.pptx', '.pdf', '.docx')
    if not any(name.endswith(ext) for ext in allowed):
        return jsonify({'error': 'Only .md, .txt, .pdf, .docx, and .pptx files are supported'}), 400

    rag_module.DOCS_DIR.mkdir(parents=True, exist_ok=True)

    _converters = {
        '.pptx': (rag_module.pptx_to_markdown, 5),
        '.pdf':  (rag_module.pdf_to_markdown,   4),
        '.docx': (rag_module.docx_to_markdown,  5),
    }
    ext = next((e for e in _converters if name.endswith(e)), None)

    if ext:
        fn, ext_len = _converters[ext]
        try:
            md_text = fn(f.read(), name)
        except RuntimeError as e:
            return jsonify({'error': str(e)}), 400
        save_name = name[:-ext_len] + '.md'
        (rag_module.DOCS_DIR / save_name).write_text(md_text, encoding='utf-8')
        saved = save_name
    else:
        dest = rag_module.DOCS_DIR / name
        f.save(str(dest))
        saved = name

    n = rag_module.rebuild()
    return jsonify({'ok': True, 'saved': saved, 'chunks_indexed': n, **rag_module.index_stats()})

@app.route('/api/rag/docs/<filename>', methods=['DELETE'])
def api_rag_delete_doc(filename):
    name = os.path.basename(filename)
    if not (name.endswith('.md') or name.endswith('.txt')):
        return jsonify({'error': 'Invalid file type'}), 400
    target = rag_module.DOCS_DIR / name
    if not target.exists():
        return jsonify({'error': 'File not found'}), 404
    target.unlink()
    n = rag_module.rebuild()
    return jsonify({'ok': True, 'deleted': name, 'chunks_indexed': n, **rag_module.index_stats()})

# ─────────────────────────────────────────────
#  GITHUB ROUTES
# ─────────────────────────────────────────────

@app.route('/api/github/info', methods=['GET'])
def api_github_info():
    return jsonify(github_module.github_info())

@app.route('/api/github/push', methods=['POST'])
def api_github_push():
    data           = request.get_json(force=True)
    commit_message = data.pop('commit_message', '')
    customer       = data.get('customer', '')
    try:
        files = _fmt_files(generate_all(data), data.get('iac_tool', 'terraform'))
    except Exception as e:
        return jsonify({'error': f'Generation failed: {e}'}), 500
    try:
        pusher = github_module.GitHubPusher()
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 400
    try:
        return jsonify(pusher.push_files(files, customer=customer, commit_message=commit_message))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────

@app.route('/')
def index():
    resp = make_response(render_template('home.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/cidr')
def cidr_page():
    resp = make_response(render_template('cidr.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

@app.route('/rag')
def rag_page():
    resp = make_response(render_template('rag.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

@app.route('/hub')
def hub_page():
    resp = make_response(render_template('hub.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

@app.route('/regions')
def regions_page():
    """Catalogue editor — regions/zones and Exadata shapes, a tab per cloud.

    Still served at /regions: the page grew a second catalogue rather than
    gaining a sibling page, so the URL people have bookmarked keeps working.
    """
    resp = make_response(render_template(
        'regions.html',
        clouds=list(regions.CLOUDS),
        catalogues=[
            {'key': 'regions', 'label': 'Regions & Zones', 'entries': 'regions',
             'noun': 'region', 'clouds': list(regions.CLOUDS)},
            {'key': 'shapes', 'label': 'Exadata Shapes', 'entries': 'shapes',
             'noun': 'shape', 'clouds': list(shapes.CLOUDS)},
        ]))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/api/shapes/<cloud>', methods=['GET'])
def api_shapes_get(cloud):
    if cloud not in shapes.CLOUDS:
        return jsonify({'error': f'unknown cloud "{cloud}"'}), 404
    try:
        doc = shapes.load(cloud, refresh=True)
    except shapes.ShapeConfigError as exc:
        # The file on disk is already broken. Say so plainly rather than
        # returning an empty editor that would overwrite it with nothing.
        return jsonify({'error': str(exc)}), 500
    return jsonify({'cloud': cloud, 'doc': doc, 'spec': shapes.field_spec(cloud)})


@app.route('/api/shapes/<cloud>', methods=['POST'])
def api_shapes_post(cloud):
    """Replace a shape catalogue, through the loader's own rules."""
    if cloud not in shapes.CLOUDS:
        return jsonify({'error': f'unknown cloud "{cloud}"'}), 404
    payload = request.get_json(force=True, silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get('doc'), dict):
        return jsonify({'error': 'expected {"doc": {...}}'}), 400

    doc = payload['doc']
    # Everything outside "shapes" is passed through from the file on disk —
    # _comment and default_shape. The editor only owns the shape list.
    try:
        current = shapes.load(cloud)
        merged = {k: v for k, v in current.items() if k != 'shapes'}
    except shapes.ShapeConfigError:
        merged = {}
    merged.update({k: v for k, v in doc.items() if k != 'shapes'})
    merged['shapes'] = doc.get('shapes', [])

    try:
        saved = shapes.save(cloud, merged)
    except shapes.ShapeConfigError as exc:
        return jsonify({'error': str(exc)}), 400
    except OSError as exc:
        return jsonify({'error': f'could not write catalogue: {exc}'}), 500
    return jsonify({'cloud': cloud, 'doc': saved, 'n_shapes': len(saved['shapes'])})


@app.route('/api/regions/<cloud>', methods=['GET'])
def api_regions_get(cloud):
    if cloud not in regions.CLOUDS:
        return jsonify({'error': f'unknown cloud "{cloud}"'}), 404
    try:
        doc = regions.load(cloud, refresh=True)
    except regions.RegionConfigError as exc:
        # The file on disk is already broken. Say so plainly rather than
        # returning an empty editor that would overwrite it with nothing.
        return jsonify({'error': str(exc)}), 500
    return jsonify({'cloud': cloud, 'doc': doc, 'spec': regions.field_spec(cloud)})


@app.route('/api/regions/<cloud>', methods=['POST'])
def api_regions_post(cloud):
    """Replace a catalogue. Validated with the loader's own rules before it
    touches disk: a rejected save leaves the existing file untouched."""
    if cloud not in regions.CLOUDS:
        return jsonify({'error': f'unknown cloud "{cloud}"'}), 404
    payload = request.get_json(force=True, silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get('doc'), dict):
        return jsonify({'error': 'expected {"doc": {...}}'}), 400

    doc = payload['doc']
    # Everything outside "regions" is passed through from the file on disk -
    # _comment, default_oci_region, zones_are_region_scoped, default_zones. The
    # editor only owns the region list.
    try:
        current = regions.load(cloud)
        merged = {k: v for k, v in current.items() if k != 'regions'}
    except regions.RegionConfigError:
        merged = {}
    merged.update({k: v for k, v in doc.items() if k != 'regions'})
    merged['regions'] = doc.get('regions', [])

    try:
        saved = regions.save(cloud, merged)
    except regions.RegionConfigError as exc:
        return jsonify({'error': str(exc)}), 400
    except OSError as exc:
        return jsonify({'error': f'could not write catalogue: {exc}'}), 500
    return jsonify({'cloud': cloud, 'doc': saved, 'n_regions': len(saved['regions'])})

@app.route('/api/llm/ask', methods=['POST'])
def api_llm_ask():
    body     = request.get_json(force=True)
    question = body.get('question', '').strip()
    cloud    = body.get('cloud', 'all').lower().strip()
    if not question:
        return jsonify({'error': 'question is required'}), 400
    q_lower = question.lower()
    cloud_prefix = '' if cloud == 'all' or q_lower.startswith(cloud) else f'{cloud} '
    query = f'{cloud_prefix}{question}'
    chunks  = rag_module.retrieve_hybrid(query, k=5)
    context = '\n\n---\n\n'.join(
        f'[{c["source"]} — {c.get("title", "")}]\n{c["text"]}' for c in chunks
    )
    sources = list(dict.fromkeys(c['source'] for c in chunks))
    scope   = f' Focus on {cloud.upper()} specifically.' if cloud != 'all' else ''
    system_msg = (
        'You are an expert on Oracle AI Database@AWS, Oracle AI DB@Azure, and Oracle AI DB@GCP deployments '
        'and Terraform/OpenTofu configuration.' + scope + '\n'
        'Read ALL of the documentation chunks below before composing your answer — '
        'relevant information may appear in any chunk, not just the first one.\n'
        'IMPORTANT: Do NOT say a topic is undocumented if any chunk contains relevant content. '
        'Synthesize across all chunks to give the most complete and accurate answer.\n'
        'Use plain text with short paragraphs. Keep answers under 400 words unless detail is essential.\n\n'
        'Reference documentation:\n' + context
    )
    try:
        answer = llm_module.chat([
            {'role': 'system', 'content': system_msg},
            {'role': 'user',   'content': question},
        ])
        return jsonify({
            'answer':       answer.strip(),
            'sources':      sources,
            'source_links': rag_module.source_links(chunks),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate', methods=['POST'])
def api_generate():
    data = request.get_json(force=True)
    file_key = data.get('file_key', 'main.tf')
    try:
        files = generate_all(data)
        content = files.get(file_key)
        if content is None:
            return jsonify({'error': f'Unknown file key: {file_key}'})
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/files', methods=['POST'])
def api_files():
    """Return the list of file paths generate_all() would produce for this payload.

    The output-panel file tree is built from this list so it always mirrors the
    real generated layout instead of guessing module directory names."""
    data = request.get_json(force=True)
    try:
        files = generate_all(data)
        return jsonify({'files': sorted(files.keys())})
    except Exception as e:
        return jsonify({'error': str(e), 'files': []})


@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json(force=True)
    cloud = data.get('cloud', 'aws')
    if data.get('iac_tool') == 'cloudformation':
        content = generate_cfn(data)
        buf = io.BytesIO(content.encode('utf-8'))
        return send_file(buf, mimetype='text/yaml', as_attachment=True, download_name='odb-stack.yaml')
    zip_name = cloud_registry.get(cloud).zip_name
    files = _fmt_files(generate_all(data), data.get('iac_tool', 'terraform'))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(f'{zip_name}/{path}', content)
        zf.writestr(f'{zip_name}/terraflow_config.json', json.dumps(data, indent=2))
    buf.seek(0)
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, download_name=f'{zip_name}.zip')


@app.route('/api/diagram/drawio', methods=['POST'])
def api_diagram_drawio():
    """Render the current config as an editable draw.io diagram."""
    data = request.get_json(force=True)
    try:
        from diagram.drawio import payload_to_drawio
        xml = payload_to_drawio(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    cloud = data.get('cloud', 'aws')
    buf = io.BytesIO(xml.encode('utf-8'))
    return send_file(buf, mimetype='application/xml', as_attachment=True,
                     download_name=f'terraflow-studio-{cloud}.drawio')


@app.route('/api/import/spreadsheet', methods=['POST'])
def api_import_spreadsheet():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file uploaded'})
    try:
        from spreadsheet_importer import parse_spreadsheet
        cloud_hint = request.form.get('cloud', '')
        result = parse_spreadsheet(f.stream, f.filename or 'upload.xlsx', cloud_hint)
        # Build import summary
        counts = {
            'Multi-AZ': len(result.get('dg_multi_az', [])),
            'Cross-Region': len(result.get('dg_cross_region', [])),
            'Networks': len(result.get('aws_networks', [])) or len(result.get('gcp_networks', [])) or len(result.get('azure_vnets', [])),
            'Infra': len(result.get('aws_infras', [])) or len(result.get('gcp_infras', [])) or len(result.get('azure_infras', [])),
            'VM Clusters': len(result.get('aws_clusters', [])) or len(result.get('gcp_clusters', [])) or len(result.get('azure_clusters', [])),
        }
        total = sum(counts.values())
        if total == 0:
            return jsonify({'error': 'No configuration rows found. Check column headers match the template — download via 📋 Download Template.'})
        parts = [f'{v} {k}' for k, v in counts.items() if v]
        result['_import_summary'] = f'Imported {", ".join(parts)}'
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/import/template/<cloud>', methods=['GET'])
def api_import_template(cloud):
    try:
        from spreadsheet_importer import generate_template
        data = generate_template(cloud)
        buf = io.BytesIO(data)
        return send_file(buf,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name=f'terraflow-{cloud}-template.xlsx')
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/load-zip', methods=['POST'])
def api_load_zip():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file uploaded'})
    try:
        buf = io.BytesIO(f.read())
        with zipfile.ZipFile(buf) as zf:
            cfg_name = next((n for n in zf.namelist() if n.endswith('terraflow_config.json')), None)
            if not cfg_name:
                return jsonify({'error': 'No terraflow_config.json found. Re-download the ZIP from Terraflow Studio to get a loadable archive.'})
            doc = json.loads(zf.read(cfg_name))
        return jsonify(doc)
    except zipfile.BadZipFile:
        return jsonify({'error': 'Not a valid ZIP file'})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/validate', methods=['POST'])
def api_validate():
    data   = request.get_json(force=True)
    cloud  = data.get('cloud', 'aws')
    errors = {}
    # Each cloud owns its own rules; oci validates client-side only and carries
    # no validator, which the registry represents as None.
    validator = cloud_registry.get(cloud).validate
    if validator is not None:
        validator(data, errors)
    flat_errors = {}
    for mn_errors in errors.values():
        flat_errors.update(mn_errors)
    return jsonify({'valid': len(errors) == 0, 'errors': flat_errors, 'errors_by_module': errors})


# ─────────────────────────────────────────────
#  CONFIG PERSISTENCE ROUTES
# ─────────────────────────────────────────────

@app.route('/api/config/save', methods=['POST'])
def api_config_save():
    """Save full form payload for a customer + cloud."""
    data = request.get_json(force=True)
    customer = (data.get('customer') or '').strip()
    if not customer:
        return jsonify({'error': 'customer name is required'}), 400
    cloud = data.get('cloud', 'aws')
    try:
        result = storage.save(customer, cloud, data)
        return jsonify({'ok': True, 'backend': storage.backend_name, **result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/load/<customer>/<cloud>', methods=['GET'])
def api_config_load(customer, cloud):
    """Load saved config for a customer + cloud."""
    try:
        doc = storage.load(customer, cloud)
        if doc is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(doc)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/list', methods=['GET'])
def api_config_list():
    """List all saved customers."""
    try:
        return jsonify(storage.list_customers())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/delete/<customer>/<cloud>', methods=['DELETE'])
def api_config_delete(customer, cloud):
    """Delete a saved config."""
    try:
        ok = storage.delete(customer, cloud)
        return jsonify({'ok': ok})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/backend', methods=['GET'])
def api_config_backend():
    """Return which storage backend is active."""
    return jsonify({'backend': storage.backend_name})


@app.route('/api/test', methods=['POST'])
def api_test():
    """
    Run Terraform generation tests for a specific customer config.
    Loads the saved config (or uses the posted payload directly),
    then runs all generation tests and returns structured results.

    The checks themselves live in clouds/<cloud>/selftest.py. This drives the
    run and stays free of cloud knowledge.
    """
    data     = request.get_json(force=True)
    customer = (data.get('customer') or '').strip()
    cloud    = data.get('cloud', 'aws')

    # Load saved config if customer name given, otherwise use posted payload
    payload = data
    if customer:
        saved = storage.load(customer, cloud)
        if saved:
            payload = saved

    spec = cloud_registry.get(cloud)
    suite = spec.selftest
    t = Recorder()

    derived = suite.derive(payload)

    t.start('Input Validation')
    suite.check_inputs(derived, t)

    t.start('Module Generation')
    # Rebuild a payload holding only this cloud's resources, so a config that
    # carries several clouds' keys still generates just the one under test.
    only_this_cloud = {**payload, 'cloud': cloud}
    for spec_cloud in cloud_registry.REGISTRY.values():
        keys = getattr(spec_cloud.selftest, 'PAYLOAD_KEYS', None) or {}
        for role, key in keys.items():
            if spec_cloud.name != cloud:
                only_this_cloud[key] = []
            else:
                # KeyError rather than .get(): a role this cloud's derive() does
                # not produce is a wiring bug, and defaulting to [] would hide it
                # by generating from empty input.
                only_this_cloud[key] = derived[role]
    try:
        all_files = generate_all(only_this_cloud)
        t.check('generate_all() succeeds without error', lambda: True, '')
    except Exception as e:
        t.fail('generate_all() succeeds without error', e)
        all_files = {}

    # The cloud products write one top-level root; Data Guard writes one root
    # per card and no top level at all, so asking it for main.tf is a false fail.
    roots = tf_roots(all_files)
    if '' in roots or not roots:
        for name in ('main.tf', 'terraform.auto.tfvars'):
            t.check(f'root {name} generated',
                    lambda n=name: n in all_files, f'{name} missing')
    else:
        for root in roots:
            t.check(f'{root}/main.tf generated',
                    lambda r=root: f'{r}/main.tf' in all_files, f'{root}/main.tf missing')
    t.check('All generated files are non-empty',
            lambda: all(c.strip() for c in all_files.values()),
            lambda: f'{next(p for p, c in all_files.items() if not c.strip())} is empty')

    for key in suite.module_keys(derived):
        t.check(f'{key} generated', lambda k=key: k in all_files, f'{key} missing')

    t.start('Content Checks')
    suite.check_content(derived, all_files, t)

    t.start('Uniqueness')
    all_mns = [r['module_name'] for r in (derived['nets'] + derived['infras'] +
                                          derived['peerings'] + derived['clusters'])]
    t.check('No duplicate module names',
            lambda: len(all_mns) == len(set(all_mns)),
            lambda: f'Duplicate names: {[m for m in all_mns if all_mns.count(m) > 1]}')

    return jsonify({'customer': customer or '(current)', 'cloud': cloud,
                    'passed': t.passed, 'failed': t.failed, 'total': len(t.results),
                    'results': t.results})


from tf_validator import validate_terraform, summarise, tf_roots


@app.route('/api/tf-validate', methods=['POST'])
def api_tf_validate():
    """
    Run the mock Terraform provider validator against a customer's generated files.
    Loads saved config (or uses posted payload), generates all files, then
    runs structural/schema validation simulating `terraform validate`.
    """
    data     = request.get_json(force=True)
    customer = (data.get('customer') or '').strip()
    cloud    = data.get('cloud', 'aws')

    payload = data
    if customer:
        saved = storage.load(customer, cloud)
        if saved:
            payload = saved

    try:
        files = generate_all({**payload, 'cloud': cloud})
    except Exception as e:
        return jsonify({'error': f'File generation failed: {e}',
                        'passed': 0, 'failed': 1, 'warned': 0, 'total': 1,
                        'results': [{'group': 'File Generation', 'name': 'generate_all()',
                                     'status': 'fail', 'error': str(e), 'file': None}]})

    results = validate_terraform(files, cloud)
    summary = summarise(results)
    summary['customer'] = customer or '(current)'
    summary['cloud']    = cloud
    summary['files_generated'] = len(files)
    return jsonify(summary)


def _find_tf_bin(name):
    """Locate terraform or tofu: env-var → .env file → shutil.which → common paths."""
    env_key = 'OPENTOFU_PATH' if name == 'tofu' else 'TERRAFORM_PATH'
    explicit = os.environ.get(env_key, '').strip()
    if not explicit:
        env_file = os.path.join(os.path.dirname(__file__), '.env')
        try:
            for line in open(env_file, encoding='utf-8').read().splitlines():
                line = line.strip()
                if line.startswith(env_key + '=') and not line.startswith('#'):
                    explicit = line.split('=', 1)[1].strip().strip('"').strip("'")
                    break
        except OSError:
            pass
    if explicit and os.path.isfile(explicit):
        return explicit
    found = shutil.which(name)
    if found:
        return found
    exts = ['.exe', ''] if os.name == 'nt' else ['']
    home = os.path.expanduser('~')
    if os.name == 'nt':
        lad = os.environ.get('LOCALAPPDATA', '')
        pf  = os.environ.get('PROGRAMFILES', 'C:\\Program Files')
        candidates = [
            os.path.join(lad, 'Programs', name),
            os.path.join(lad, 'Programs', 'HashiCorp', name),
            f'C:\\{name}\\{name}',
            f'C:\\HashiCorp\\{name.capitalize()}\\{name}',
            f'C:\\tools\\{name}\\{name}',
            os.path.join(pf, 'HashiCorp', name.capitalize(), name),
            os.path.join(home, 'bin', name),
            os.path.join(home, '.local', 'bin', name),
        ]
    else:
        candidates = [
            f'/usr/local/bin/{name}',
            f'/usr/bin/{name}',
            os.path.join(home, 'bin', name),
            os.path.join(home, '.local', 'bin', name),
            f'/opt/homebrew/bin/{name}',
        ]
    for base in candidates:
        for ext in exts:
            p = base + ext
            if os.path.isfile(p):
                return p
    return None


def _fmt_files(files: dict, iac_tool: str = 'terraform') -> dict:
    """Run terraform/tofu fmt on generated files and return formatted content.
    Falls back to original files silently if binary not found or fmt fails."""
    bin_path = _find_tf_bin('tofu' if iac_tool == 'opentofu' else 'terraform')
    if not bin_path:
        bin_path = _find_tf_bin('terraform') or _find_tf_bin('tofu')
    if not bin_path:
        return files
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            for path, content in files.items():
                full = os.path.join(tmpdir, path.replace('/', os.sep).replace('\\', os.sep))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, 'w', encoding='utf-8') as fh:
                    fh.write(content)
            subprocess.run(
                [bin_path, 'fmt', '-recursive', '.'],
                cwd=tmpdir, capture_output=True, text=True, timeout=30
            )
            result = {}
            for path, content in files.items():
                full = os.path.join(tmpdir, path.replace('/', os.sep).replace('\\', os.sep))
                try:
                    with open(full, encoding='utf-8') as fh:
                        result[path] = fh.read()
                except OSError:
                    result[path] = content
            return result
    except Exception:
        return files


@app.route('/api/tf-cli', methods=['POST'])
def api_tf_cli():
    """
    Write generated files to a temp dir, then run terraform fmt --check and
    terraform validate (via terraform init -backend=false).
    Uses terraform or tofu based on iac_tool in the payload.
    """
    data     = request.get_json(force=True)
    cloud    = data.get('cloud', 'aws')
    customer = (data.get('customer') or '').strip()
    iac_tool = data.get('iac_tool', 'terraform')

    _ansi = re.compile(r'\x1b\[[0-9;]*[mK]')
    def _strip(s): return _ansi.sub('', s or '').strip()

    bin_name = 'tofu' if iac_tool == 'opentofu' else 'terraform'
    bin_path = _find_tf_bin(bin_name)
    if not bin_path:
        alt = 'terraform' if bin_name == 'tofu' else 'tofu'
        bin_path = _find_tf_bin(alt)
        if bin_path:
            bin_name = alt

    if not bin_path:
        hint = ('Set TERRAFORM_PATH or OPENTOFU_PATH in your .env to the full path of the binary '
                '(e.g. TERRAFORM_PATH=C:\\terraform\\terraform.exe), '
                'or add the directory to your system PATH.')
        return jsonify({
            'passed': 0, 'failed': 1, 'warned': 0, 'total': 1,
            'bin': bin_name, 'bin_version': None,
            'customer': customer or '(current)', 'cloud': cloud, 'files_generated': 0,
            'results': [{'group': 'CLI Probe', 'name': f'{bin_name} not found',
                         'status': 'fail', 'error': hint}]
        })

    # Detect binary version
    try:
        ver_out = subprocess.run([bin_path, 'version', '-json'], capture_output=True, text=True, timeout=10)
        bin_version = json.loads(ver_out.stdout).get('terraform_version') or json.loads(ver_out.stdout).get('opentofu_version', '')
    except Exception:
        bin_version = ''

    payload = data
    if customer:
        saved = storage.load(customer, cloud)
        if saved:
            payload = saved

    try:
        files = _fmt_files(generate_all({**payload, 'cloud': cloud}), iac_tool)
    except Exception as e:
        return jsonify({
            'passed': 0, 'failed': 1, 'warned': 0, 'total': 1,
            'bin': bin_name, 'bin_version': bin_version,
            'customer': customer or '(current)', 'cloud': cloud, 'files_generated': 0,
            'results': [{'group': 'File Generation', 'name': 'generate_all()',
                         'status': 'fail', 'error': str(e)}]
        })

    results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for rel_path, content in files.items():
            abs_path = os.path.join(tmpdir, rel_path.replace('/', os.sep))
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, 'w', encoding='utf-8') as fh:
                fh.write(content)

        # ── terraform fmt --check ─────────────────────────────────────────────
        try:
            fmt = subprocess.run(
                [bin_path, 'fmt', '-check', '-recursive', '.'],
                cwd=tmpdir, capture_output=True, text=True, timeout=30
            )
            if fmt.returncode == 0:
                results.append({'group': 'terraform fmt', 'name': 'All files properly formatted', 'status': 'pass'})
            else:
                # stdout lists files that need reformatting (one per line)
                bad_files = [f.strip() for f in (fmt.stdout or '').splitlines() if f.strip()]
                if bad_files:
                    results.append({'group': 'terraform fmt', 'name': 'Files need reformatting',
                                    'status': 'fail', 'error': '\n'.join(bad_files)})
                else:
                    results.append({'group': 'terraform fmt', 'name': 'Formatting check failed',
                                    'status': 'fail', 'error': _strip(fmt.stderr or fmt.stdout)})
        except subprocess.TimeoutExpired:
            results.append({'group': 'terraform fmt', 'name': 'terraform fmt', 'status': 'fail', 'error': 'Timed out after 30s'})
        except Exception as e:
            results.append({'group': 'terraform fmt', 'name': 'terraform fmt', 'status': 'fail', 'error': str(e)})

        # ── terraform init -backend=false + validate, in every root ──────────
        # A product can emit several independent roots (one per Data Guard card,
        # two per KMS key), and init/validate only ever look at the directory
        # they run in — validating the top level alone reports a pass for code
        # that was never checked.
        tf_env = {**os.environ}
        cache_dir = os.path.expanduser('~/.terraform.d/plugin-cache')
        os.makedirs(cache_dir, exist_ok=True)
        tf_env['TF_PLUGIN_CACHE_DIR'] = cache_dir

        # Write a minimal CLI config that sets the cache dir.
        # Do NOT add a provider_installation block — mixing filesystem_mirror
        # with plugin_cache_dir pointing to the same path causes Terraform to
        # error with "cannot install provider directory to itself".
        cache_fwd = cache_dir.replace('\\', '/')
        rc_path = os.path.join(tmpdir, 'terraform.rc')
        with open(rc_path, 'w', encoding='utf-8') as _rc:
            _rc.write(f'plugin_cache_dir = "{cache_fwd}"\n')
        tf_env['TF_CLI_CONFIG_FILE'] = rc_path

        roots = tf_roots(files)
        if not roots:
            results.append({'group': 'terraform init', 'name': 'Terraform root generated',
                            'status': 'fail', 'error': 'No .tf files outside modules/ — nothing to init'})
        for root in roots:
            # The top-level root keeps the group names it always had.
            sfx = f' · {root}/' if root else ''
            cwd = os.path.join(tmpdir, root.replace('/', os.sep)) if root else tmpdir
            init_ok = False
            try:
                init = subprocess.run(
                    [bin_path, 'init', '-backend=false', '-no-color', '-input=false'],
                    cwd=cwd, capture_output=True, text=True, timeout=180,
                    env=tf_env
                )
                if init.returncode == 0:
                    results.append({'group': 'terraform init' + sfx, 'name': 'terraform init -backend=false', 'status': 'pass'})
                    init_ok = True
                else:
                    err = _strip(init.stderr or init.stdout)
                    _net_keywords = ('registry.terraform.io', 'could not retrieve', 'failed to query',
                                     'wsarecv', 'connection refused', 'no such host', 'i/o timeout',
                                     'dial tcp', 'tls handshake', 'EOF')
                    is_network_err = any(kw in err.lower() for kw in _net_keywords)
                    if is_network_err:
                        # Network failure ≠ bad generated code — report as warn so the
                        # overall test result reflects code quality, not connectivity.
                        results.append({'group': 'terraform init' + sfx,
                                        'name': 'terraform init -backend=false',
                                        'status': 'warn',
                                        'error': (f'Provider registry unreachable (network/IPv6 issue). '
                                                  f'Providers are cached at {cache_dir} after the first '
                                                  f'successful download. Run terraform init manually once '
                                                  f'with internet access (or via VPN/proxy) to populate '
                                                  f'the cache — TF CLI tests will then work offline.\n\n'
                                                  f'Original error: {err}')})
                    else:
                        results.append({'group': 'terraform init' + sfx, 'name': 'terraform init -backend=false',
                                        'status': 'fail', 'error': err})
            except subprocess.TimeoutExpired:
                results.append({'group': 'terraform init' + sfx, 'name': 'terraform init -backend=false',
                                'status': 'warn', 'error': 'Timed out after 180s — provider registry unreachable. Providers will be cached after the first successful init.'})
            except Exception as e:
                results.append({'group': 'terraform init' + sfx, 'name': 'terraform init -backend=false', 'status': 'fail', 'error': str(e)})

            if not init_ok:
                continue
            grp = 'terraform validate' + sfx
            try:
                val = subprocess.run(
                    [bin_path, 'validate', '-json', '-no-color'],
                    # Loading a large provider binary cold (oracle/oci, under an
                    # antivirus scan) can take most of 30s, once per root.
                    cwd=cwd, capture_output=True, text=True, timeout=120
                )
                try:
                    vj = json.loads(val.stdout)
                    if vj.get('valid'):
                        results.append({'group': grp, 'name': 'Configuration is valid', 'status': 'pass'})
                    else:
                        for diag in (vj.get('diagnostics') or []):
                            sev   = diag.get('severity', 'error')
                            fname = (diag.get('range') or {}).get('filename', '')
                            if fname and fname.startswith(cwd):
                                fname = fname[len(cwd):].lstrip('/\\')
                            if fname and root:
                                fname = f'{root}/{fname}'
                            results.append({
                                'group':  grp,
                                'name':   diag.get('summary', 'Unknown error'),
                                'status': 'fail' if sev == 'error' else 'warn',
                                'error':  diag.get('detail', ''),
                                'file':   fname or None,
                            })
                        if not vj.get('diagnostics'):
                            results.append({'group': grp, 'name': 'Invalid configuration',
                                            'status': 'fail', 'error': _strip(val.stdout or val.stderr)})
                except json.JSONDecodeError:
                    status = 'pass' if val.returncode == 0 else 'fail'
                    results.append({'group': grp, 'name': 'terraform validate',
                                    'status': status, 'error': _strip(val.stdout + val.stderr) if status == 'fail' else ''})
            except subprocess.TimeoutExpired:
                results.append({'group': grp, 'name': 'terraform validate', 'status': 'fail', 'error': 'Timed out after 120s'})
            except Exception as e:
                results.append({'group': grp, 'name': 'terraform validate', 'status': 'fail', 'error': str(e)})

    passed = sum(1 for r in results if r['status'] == 'pass')
    failed = sum(1 for r in results if r['status'] == 'fail')
    warned = sum(1 for r in results if r['status'] == 'warn')
    return jsonify({
        'customer':        customer or '(current)',
        'cloud':           cloud,
        'bin':             bin_name,
        'bin_version':     bin_version,
        'passed':          passed,
        'failed':          failed,
        'warned':          warned,
        'total':           len(results),
        'results':         results,
        'files_generated': len(files),
    })


# ─────────────────────────────────────────────
#  CONFIGURATION PAGE
# ─────────────────────────────────────────────

_ENV_PATH = _pl.Path(__file__).parent / '.env'

# Ordered schema used by both GET and POST
_CONFIG_SCHEMA = [
    {
        'id': 'couchdb',
        'label': 'CouchDB',
        'fields': [
            {'key': 'COUCHDB_USER',     'label': 'Username',  'type': 'text',     'placeholder': 'admin'},
            {'key': 'COUCHDB_PASSWORD', 'label': 'Password',  'type': 'password', 'placeholder': ''},
            {'key': 'COUCHDB_DB',       'label': 'Database',  'type': 'text',     'placeholder': 'terraflow_studio_configs'},
        ],
    },
    {
        'id': 'llm',
        'label': 'LLM Provider',
        'fields': [
            {'key': 'LLM_PROVIDER',    'label': 'Provider',     'type': 'select',   'placeholder': '',
             'options': ['anthropic', 'openai', 'gemini', 'ollama', 'oci_genai']},
            {'key': 'LLM_API_KEY',     'label': 'API Key',      'type': 'password', 'placeholder': 'sk-...'},
            {'key': 'LLM_MODEL',       'label': 'Model',        'type': 'text',     'placeholder': 'gpt-4o-mini'},
            {'key': 'LLM_BASE_URL',    'label': 'Base URL',     'type': 'text',     'placeholder': 'https://api.openai.com/v1'},
            {'key': 'LLM_MAX_TOKENS',  'label': 'Max Tokens',   'type': 'number',   'placeholder': '2048'},
            {'key': 'LLM_TEMPERATURE', 'label': 'Temperature',  'type': 'number',   'placeholder': '0.2'},
            {'key': 'LLM_TIMEOUT',     'label': 'Timeout (s)',  'type': 'number',   'placeholder': '60'},
        ],
    },
    {
        'id': 'oci_genai',
        'label': 'OCI GenAI',
        'fields': [
            {'key': 'OCI_GENAI_COMPARTMENT_ID', 'label': 'Compartment ID', 'type': 'text',   'placeholder': 'ocid1.compartment...'},
            {'key': 'OCI_GENAI_REGION',          'label': 'Region',         'type': 'text',   'placeholder': 'us-chicago-1'},
            {'key': 'OCI_GENAI_AUTH',            'label': 'Auth Method',    'type': 'select', 'placeholder': '',
             'options': ['config_file', 'instance_principal', 'resource_principal']},
            {'key': 'OCI_CONFIG_FILE',           'label': 'Config File',    'type': 'text',   'placeholder': '~/.oci/config'},
            {'key': 'OCI_CONFIG_PROFILE',        'label': 'Profile',        'type': 'text',   'placeholder': 'DEFAULT'},
        ],
    },
    {
        'id': 'embedding',
        'label': 'RAG Embeddings',
        'fields': [
            {'key': 'EMBEDDING_PROVIDER', 'label': 'Provider',  'type': 'select', 'placeholder': '',
             'options': ['', 'ollama', 'openai', 'gemini']},
            {'key': 'EMBEDDING_MODEL',    'label': 'Model',     'type': 'text',   'placeholder': 'nomic-embed-text'},
            {'key': 'EMBEDDING_BASE_URL', 'label': 'Base URL',  'type': 'text',   'placeholder': 'http://localhost:11434'},
        ],
    },
    {
        'id': 'tfcli',
        'label': 'Terraform CLI',
        'fields': [
            {'key': 'TERRAFORM_PATH', 'label': 'Terraform Binary', 'type': 'text', 'placeholder': '/usr/local/bin/terraform'},
            {'key': 'OPENTOFU_PATH',  'label': 'OpenTofu Binary',  'type': 'text', 'placeholder': '/usr/local/bin/tofu'},
        ],
    },
    {
        'id': 'server',
        'label': 'Flask Server',
        'note': 'Changes take effect on next server restart.',
        'fields': [
            {'key': 'APP_HOST',  'label': 'Host',       'type': 'text',   'placeholder': '0.0.0.0'},
            {'key': 'APP_PORT',  'label': 'Port',        'type': 'number', 'placeholder': '8000'},
            {'key': 'APP_DEBUG', 'label': 'Debug Mode',  'type': 'select', 'placeholder': '',
             'options': ['true', 'false']},
        ],
    },
    {
        'id': 'github',
        'label': 'GitHub Integration',
        'fields': [
            {'key': 'GITHUB_TOKEN',     'label': 'Personal Access Token', 'type': 'password', 'placeholder': 'ghp_...'},
            {'key': 'GITHUB_REPO',      'label': 'Repository',            'type': 'text',     'placeholder': 'owner/repo'},
            {'key': 'GITHUB_BRANCH',    'label': 'Branch',                'type': 'text',     'placeholder': 'main'},
            {'key': 'GITHUB_BASE_PATH', 'label': 'Base Path',             'type': 'text',     'placeholder': 'terraform'},
        ],
    },
]

_SENSITIVE_KEYS = {'LLM_API_KEY', 'COUCHDB_PASSWORD', 'GITHUB_TOKEN'}


def _read_env_file() -> dict:
    """Parse .env into {key: value}, ignoring comments and blank lines."""
    result = {}
    if not _ENV_PATH.exists():
        return result
    for line in _ENV_PATH.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            result[k] = v
    return result


def _write_env_file(updates: dict) -> None:
    """Update .env in-place: replace existing key values, append new ones."""
    lines = _ENV_PATH.read_text(encoding='utf-8').splitlines() if _ENV_PATH.exists() else []
    written = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            k = stripped.split('=', 1)[0].strip()
            if k in updates:
                new_lines.append(f'{k}={updates[k]}')
                written.add(k)
                continue
        new_lines.append(line)
    # Append keys not already present in file
    for k, v in updates.items():
        if k not in written:
            new_lines.append(f'{k}={v}')
    _ENV_PATH.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')


@app.route('/config')
def config_page():
    return render_template('config.html', schema=_CONFIG_SCHEMA)


@app.route('/api/config', methods=['GET'])
def api_config_get():
    env = _read_env_file()
    all_keys = {f['key'] for g in _CONFIG_SCHEMA for f in g['fields']}
    values = {k: env.get(k, '') for k in all_keys}
    return jsonify({'values': values, 'schema': _CONFIG_SCHEMA})


@app.route('/api/config', methods=['POST'])
def api_config_post():
    data = request.get_json(force=True)
    updates = {k: str(v) for k, v in data.items() if isinstance(k, str)}
    allowed = {f['key'] for g in _CONFIG_SCHEMA for f in g['fields']}
    updates = {k: v for k, v in updates.items() if k in allowed}
    try:
        _write_env_file(updates)
        # Reload into running process
        for k, v in updates.items():
            os.environ[k] = v
        return jsonify({'ok': True, 'saved': list(updates.keys())})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == '__main__':
    _host  = os.environ.get('APP_HOST',  '0.0.0.0')
    _port  = int(os.environ.get('APP_PORT',  '8000'))
    _debug = os.environ.get('APP_DEBUG', 'true').lower() == 'true'
    app.run(host=_host, debug=_debug, port=_port)
