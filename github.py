"""
github.py — GitHub repository integration for Terraflow Studio.
Pushes generated Terraform files via GitHub Contents REST API.
Set GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH, GITHUB_BASE_PATH in .env
"""
import base64, json, os, urllib.request, urllib.error
from datetime import datetime, timezone
from typing import Optional

def _cfg(k, default=''): return os.environ.get(k, default).strip()

class GitHubPusher:
    API = 'https://api.github.com'
    def __init__(self):
        self.token     = _cfg('GITHUB_TOKEN')
        self.repo      = _cfg('GITHUB_REPO')
        self.branch    = _cfg('GITHUB_BRANCH','main')
        self.base_path = _cfg('GITHUB_BASE_PATH','terraform').strip('/')
        if not self.token: raise RuntimeError('GITHUB_TOKEN is not set in .env — generate at https://github.com/settings/tokens')
        if not self.repo or '/' not in self.repo: raise RuntimeError('GITHUB_REPO must be owner/repo in .env')

    def _headers(self):
        return {'Authorization':f'Bearer {self.token}','Accept':'application/vnd.github+json',
                'X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'}

    def _get_sha(self, path):
        url = f'{self.API}/repos/{self.repo}/contents/{path}'
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read())
                return d.get('sha') if isinstance(d, dict) else None
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            raise RuntimeError(f'GitHub GET {path} failed ({e.code})')

    def _put(self, path, content, message, sha=None):
        url  = f'{self.API}/repos/{self.repo}/contents/{path}'
        body = {'message':message,'content':base64.b64encode(content.encode()).decode(),'branch':self.branch}
        if sha: body['sha'] = sha
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=self._headers(), method='PUT')
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'GitHub PUT {path} failed ({e.code}): {e.read().decode()[:200]}')

    def push_files(self, files, customer='', commit_message=''):
        if not commit_message:
            ts  = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            who = f' [{customer}]' if customer else ''
            commit_message = f'chore: Terraflow update{who} — {ts}'
        pushed=[]; errors=[]; last_url=None
        for rel_path, content in files.items():
            full = f'{self.base_path}/{rel_path}' if self.base_path else rel_path
            try:
                sha  = self._get_sha(full)
                resp = self._put(full, content, commit_message, sha)
                pushed.append(full)
                last_url = (resp.get('content') or {}).get('html_url')
            except Exception as e:
                errors.append({'path':full,'error':str(e)})
        repo_url = f'https://github.com/{self.repo}/tree/{self.branch}'
        if self.base_path: repo_url += f'/{self.base_path}'
        return {'pushed':pushed,'errors':errors,'total':len(files),'commit_url':last_url,'repo_url':repo_url}

def github_info():
    token = _cfg('GITHUB_TOKEN'); repo = _cfg('GITHUB_REPO')
    if not token or not repo:
        missing = [k for k,v in [('GITHUB_TOKEN',token),('GITHUB_REPO',repo)] if not v]
        return {'configured':False,'error':f"Not set in .env: {', '.join(missing)}"}
    return {'configured':True,'repo':repo,'branch':_cfg('GITHUB_BRANCH','main'),
            'base_path':_cfg('GITHUB_BASE_PATH','terraform'),'repo_url':f'https://github.com/{repo}'}
