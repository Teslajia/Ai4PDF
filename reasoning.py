"""Model-specific reasoning choices; gateway declarations override assumptions."""
import hashlib
import json
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit

POLICY = json.loads((Path(__file__).parent / 'static/reasoning-models.json').read_text(encoding='utf-8'))
_catalogs = {}
_lock = threading.Lock()


def connection_key(config):
    base = str(config.get('baseUrl', '')).strip().rstrip('/').removesuffix('/chat/completions')
    return hashlib.sha256((base + '\0' + str(config.get('apiKey', '')).strip()).encode()).hexdigest()


def remember_capabilities(config, entries):
    capabilities = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('id'), str):
            continue
        values = entry.get('supported_reasoning_efforts', entry.get('reasoning_efforts'))
        if values is None and isinstance(entry.get('capabilities'), dict):
            values = entry['capabilities'].get('reasoning_efforts')
        if isinstance(values, list) and all(isinstance(value, str) for value in values):
            capabilities[entry['id'].strip()] = [v for v in POLICY['values'] if v in values]
    with _lock:
        if len(_catalogs) >= 32:
            _catalogs.pop(next(iter(_catalogs)))
        _catalogs[connection_key(config)] = capabilities
    return capabilities


def available_efforts(config):
    model = str(config.get('model', '')).strip()
    with _lock:
        declared = _catalogs.get(connection_key(config), {}).get(model)
    if declared is not None:
        return ['default', *declared]
    canonical = re.sub(r'-\d{4}-\d{2}-\d{2}$', '', model)
    values = POLICY['models'].get(canonical, POLICY['fallback'])
    url = urlsplit(str(config.get('baseUrl', '')).strip())
    official = url.scheme == 'https' and url.hostname == 'api.openai.com' and url.port in (None, 443)
    # Compatible gateways may route the same ID to a different model/version.
    if not official:
        values = [v for v in values if v != 'max']
    return ['default', *values]
