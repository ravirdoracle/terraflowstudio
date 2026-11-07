"""
llm.py — Model-agnostic LLM provider layer for Terraflow Studio.
Supported: anthropic, openai (+ compatible), gemini, ollama, oci_genai
Set LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL in .env
"""
import json, os, urllib.request, urllib.error
from typing import Optional

_DEFAULTS = {
    'anthropic': 'claude-3-5-haiku-20241022',
    'openai':    'gpt-4o-mini',
    'gemini':    'gemini-2.0-flash',
    'ollama':    'llama3.2',
    'oci_genai': 'cohere.command-r-plus-08-2024',
}

def _post(url, payload, headers, timeout=60):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data,
           headers={'Content-Type':'application/json',
                    'User-Agent':'TerraflowStudio/1.0', **headers}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'HTTP {e.code}: {body[:400]}')
    except urllib.error.URLError as e:
        raise RuntimeError(f'Network error: {e.reason}')

class AnthropicProvider:
    URL = 'https://api.anthropic.com/v1/messages'
    def __init__(self, key, model):
        if not key: raise RuntimeError('LLM_API_KEY is required for anthropic.')
        self.key = key; self.model = model or _DEFAULTS['anthropic']
        self.max_tokens = int(os.environ.get('LLM_MAX_TOKENS','2048'))
        self.timeout    = int(os.environ.get('LLM_TIMEOUT','60'))
    def chat(self, messages):
        system = ''; filtered = []
        for m in messages:
            if m['role'] == 'system': system = m['content']
            else: filtered.append(m)
        payload = {'model':self.model,'max_tokens':self.max_tokens,'messages':filtered}
        if system: payload['system'] = system
        r = _post(self.URL, payload, {'x-api-key':self.key,'anthropic-version':'2023-06-01'}, self.timeout)
        return r['content'][0]['text']
    @property
    def info(self): return {'provider':'anthropic','model':self.model}

class OpenAIProvider:
    DEFAULT = 'https://api.openai.com/v1/chat/completions'
    def __init__(self, key, model, base_url=''):
        if not key: raise RuntimeError('LLM_API_KEY is required for openai.')
        self.key = key; self.model = model or _DEFAULTS['openai']
        self.temperature = float(os.environ.get('LLM_TEMPERATURE','0.2'))
        self.max_tokens  = int(os.environ.get('LLM_MAX_TOKENS','2048'))
        self.timeout     = int(os.environ.get('LLM_TIMEOUT','60'))
        url = (base_url or self.DEFAULT).rstrip('/')
        self.url = url if url.endswith('/chat/completions') else url + '/chat/completions'
    def chat(self, messages):
        r = _post(self.url, {'model':self.model,'messages':messages,
            'max_tokens':self.max_tokens,'temperature':self.temperature},
            {'Authorization':f'Bearer {self.key}'}, self.timeout)
        return r['choices'][0]['message']['content']
    @property
    def info(self): return {'provider':'openai','model':self.model,'base_url':self.url}

class GeminiProvider:
    BASE = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    def __init__(self, key, model, base_url=''):
        if not key: raise RuntimeError('LLM_API_KEY is required for gemini.')
        self.key = key; self.model = model or _DEFAULTS['gemini']
        self.base_url    = base_url.rstrip('/') if base_url else ''
        self.max_tokens  = int(os.environ.get('LLM_MAX_TOKENS','2048'))
        self.temperature = float(os.environ.get('LLM_TEMPERATURE','0.2'))
        self.timeout     = int(os.environ.get('LLM_TIMEOUT','60'))
    def _endpoint(self):
        if self.base_url:
            tmpl = self.base_url + ('/{model}:generateContent' if '{model}' not in self.base_url else '')
            return tmpl.format(model=self.model)
        return self.BASE.format(model=self.model) + f'?key={self.key}'
    def chat(self, messages):
        contents = []; system_parts = []
        for m in messages:
            if m['role'] == 'system': system_parts.append({'text':m['content']})
            elif m['role'] == 'user': contents.append({'role':'user','parts':[{'text':m['content']}]})
            else:                     contents.append({'role':'model','parts':[{'text':m['content']}]})
        payload = {'contents':contents,'generationConfig':{'maxOutputTokens':self.max_tokens,'temperature':self.temperature}}
        if system_parts: payload['systemInstruction'] = {'parts':system_parts}
        headers = {}
        if self.base_url:
            bearer = os.environ.get('LLM_BEARER_TOKEN','').strip()
            if bearer: headers['Authorization'] = f'Bearer {bearer}'
        r = _post(self._endpoint(), payload, headers, self.timeout)
        return r['candidates'][0]['content']['parts'][0]['text']
    @property
    def info(self):
        i = {'provider':'gemini','model':self.model}
        if self.base_url: i['base_url'] = self.base_url
        return i

class OciGenAIProvider:
    def __init__(self, compartment_id, model, region, auth='config_file'):
        try:
            import oci as _oci
            self._oci = _oci
        except ImportError:
            raise RuntimeError(
                "oci package not installed. Run: pip install oci\n"
                "Then set OCI_GENAI_COMPARTMENT_ID and OCI_GENAI_REGION in .env"
            )
        if not compartment_id:
            raise RuntimeError('OCI_GENAI_COMPARTMENT_ID is required for oci_genai provider.')
        self.compartment_id = compartment_id
        self.model       = model or _DEFAULTS['oci_genai']
        self.region      = region or 'us-chicago-1'
        self.max_tokens  = int(os.environ.get('LLM_MAX_TOKENS', '2048'))
        self.temperature = float(os.environ.get('LLM_TEMPERATURE', '0.2'))
        self.timeout     = int(os.environ.get('LLM_TIMEOUT', '60'))
        endpoint = f'https://inference.generativeai.{self.region}.oci.oraclecloud.com'
        auth_lower = (auth or 'config_file').lower()
        if auth_lower == 'instance_principal':
            signer = _oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            self.client = _oci.generative_ai_inference.GenerativeAiInferenceClient(
                config={}, signer=signer, service_endpoint=endpoint)
        elif auth_lower == 'resource_principal':
            signer = _oci.auth.signers.get_resource_principals_signer()
            self.client = _oci.generative_ai_inference.GenerativeAiInferenceClient(
                config={}, signer=signer, service_endpoint=endpoint)
        else:
            profile  = os.environ.get('OCI_CONFIG_PROFILE', 'DEFAULT')
            cfg_file = os.environ.get('OCI_CONFIG_FILE', _oci.config.DEFAULT_LOCATION)
            config   = _oci.config.from_file(cfg_file, profile)
            self.client = _oci.generative_ai_inference.GenerativeAiInferenceClient(
                config=config, service_endpoint=endpoint)

    def _is_cohere(self):
        return self.model.startswith('cohere.')

    def chat(self, messages):
        oci = self._oci
        models = oci.generative_ai_inference.models
        if self._is_cohere():
            system = next((m['content'] for m in messages if m['role'] == 'system'), None)
            chat_msgs = [m for m in messages if m['role'] != 'system']
            history = [
                models.CohereMessage(
                    role='USER' if m['role'] == 'user' else 'CHATBOT',
                    message=m['content'])
                for m in chat_msgs[:-1]
            ]
            last = chat_msgs[-1]['content'] if chat_msgs else ''
            chat_req = models.CohereChatRequest(
                message=last,
                chat_history=history or None,
                preamble=system,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                is_stream=False)
        else:
            _role_map = {'system': 'SYSTEM', 'user': 'USER', 'assistant': 'ASSISTANT'}
            _cls_map  = {
                'system':    models.SystemMessage,
                'user':      models.UserMessage,
                'assistant': models.AssistantMessage,
            }
            generic_msgs = [
                _cls_map.get(m['role'], models.UserMessage)(
                    role=_role_map.get(m['role'], 'USER'),
                    content=[models.TextContent(type='TEXT', text=m['content'])])
                for m in messages
            ]
            chat_req = models.GenericChatRequest(
                messages=generic_msgs,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                is_stream=False)
        details = models.ChatDetails(
            compartment_id=self.compartment_id,
            serving_mode=models.OnDemandServingMode(
                model_id=self.model,
                serving_type='ON_DEMAND'),
            chat_request=chat_req)
        try:
            resp = self.client.chat(details)
        except oci.exceptions.ServiceError as e:
            raise RuntimeError(f'OCI GenAI error {e.status}: {e.message}')
        if self._is_cohere():
            return resp.data.chat_response.text
        return resp.data.chat_response.choices[0].message.content[0].text

    @property
    def info(self):
        return {'provider': 'oci_genai', 'model': self.model, 'region': self.region}

class OllamaProvider:
    DEFAULT = 'http://localhost:11434/api/chat'
    def __init__(self, model, base_url=''):
        self.model    = model or _DEFAULTS['ollama']
        self.url      = base_url or self.DEFAULT
        self.temperature = float(os.environ.get('LLM_TEMPERATURE','0.2'))
        self.timeout     = int(os.environ.get('LLM_TIMEOUT','60'))
    def chat(self, messages):
        r = _post(self.url, {'model':self.model,'messages':messages,'stream':False,
            'options':{'temperature':self.temperature}}, {}, self.timeout)
        return r['message']['content']
    @property
    def info(self): return {'provider':'ollama','model':self.model,'base_url':self.url}

def _make_provider():
    p        = os.environ.get('LLM_PROVIDER','anthropic').lower()
    key      = os.environ.get('LLM_API_KEY','').strip()
    model    = os.environ.get('LLM_MODEL','').strip()
    base_url = os.environ.get('LLM_BASE_URL','').strip()
    if p == 'anthropic': return AnthropicProvider(key, model)
    if p == 'openai':    return OpenAIProvider(key, model, base_url)
    if p == 'gemini':    return GeminiProvider(key, model, base_url)
    if p == 'ollama':    return OllamaProvider(model, base_url)
    if p == 'oci_genai':
        compartment_id = os.environ.get('OCI_GENAI_COMPARTMENT_ID','').strip()
        region         = os.environ.get('OCI_GENAI_REGION','us-chicago-1').strip()
        auth           = os.environ.get('OCI_GENAI_AUTH','config_file').strip()
        return OciGenAIProvider(compartment_id, model, region, auth)
    raise RuntimeError(f"Unknown LLM_PROVIDER '{p}'. Use: anthropic, openai, gemini, ollama, oci_genai")

_provider = None; _provider_error = None

def _get_provider():
    global _provider, _provider_error
    if _provider is None and _provider_error is None:
        try: _provider = _make_provider()
        except Exception as e: _provider_error = str(e)
    if _provider_error: raise RuntimeError(_provider_error)
    return _provider

def chat(messages): return _get_provider().chat(messages)

def provider_info():
    p        = os.environ.get('LLM_PROVIDER','anthropic').lower()
    key      = os.environ.get('LLM_API_KEY','').strip()
    model    = os.environ.get('LLM_MODEL','').strip() or _DEFAULTS.get(p,'')
    base_url = os.environ.get('LLM_BASE_URL','').strip()
    if p == 'oci_genai':
        compartment_id = os.environ.get('OCI_GENAI_COMPARTMENT_ID','').strip()
        region         = os.environ.get('OCI_GENAI_REGION','us-chicago-1').strip()
        auth           = os.environ.get('OCI_GENAI_AUTH','config_file').strip()
        if not compartment_id:
            return {'configured':False,'provider':p,'error':'OCI_GENAI_COMPARTMENT_ID is not set in .env'}
        return {'configured':True,'provider':p,'model':model,'region':region,'auth':auth}
    configured = p == 'ollama' or bool(key)
    if not configured:
        return {'configured':False,'provider':p,'error':f'LLM_API_KEY is not set in .env'}
    return {'configured':True,'provider':p,'model':model,'base_url':base_url or None}
