"""Import provider assignments as data; never execute a supplied shell command."""
from __future__ import annotations
import re
import shlex
from urllib.parse import urlsplit
from .common import atomic_json, load_json

ENV_KEYS = {'ANTHROPIC_BASE_URL', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN',
            'ANTHROPIC_MODEL', 'ANTHROPIC_DEFAULT_OPUS_MODEL',
            'ANTHROPIC_DEFAULT_SONNET_MODEL', 'ANTHROPIC_DEFAULT_HAIKU_MODEL',
            'ANTHROPIC_SMALL_FAST_MODEL', 'CLAUDE_CODE_EFFORT_LEVEL'}


def safe_id(value):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', value):
        raise ValueError('Use a model id containing only letters, digits, dash and underscore')
    return value


def parse_oneliner(value):
    if any(s in value for s in ('$(', '`', '\n', '\r', '&&', '||', '|', '>', '<')):
        raise ValueError('Shell expansion, pipelines and multiline commands are not accepted')
    lexer = shlex.shlex(value, posix=True, punctuation_chars=';')
    lexer.whitespace_split = True
    lexer.commenters = ''
    tokens = list(lexer)
    env, model, effort = {}, None, None
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in ('env', 'export', ';'):
            i += 1
            continue
        if '=' in token and not token.startswith('--'):
            key, val = token.split('=', 1)
            if key not in ENV_KEYS or key in env:
                raise ValueError('Unsupported or duplicate environment assignment')
            env[key] = val
            i += 1
            continue
        if token == 'claude' or token.endswith('/claude'):
            i += 1
            while i < len(tokens):
                if tokens[i] in ('--model', '--effort') and i + 1 < len(tokens):
                    if tokens[i] == '--model':
                        model = tokens[i + 1]
                    else:
                        effort = tokens[i + 1]
                    i += 2
                elif tokens[i] == ';' and i == len(tokens) - 1:
                    i += 1
                else:
                    raise ValueError('Only --model and --effort may follow claude')
            break
        raise ValueError('Unsupported oneliner syntax; supply env assignments and claude --model')
    model = model or env.get('ANTHROPIC_MODEL')
    effort = effort or env.get('CLAUDE_CODE_EFFORT_LEVEL')
    if not model or len(model) > 200 or any(c.isspace() for c in model):
        raise ValueError('An explicit model id is required')
    credentials = [k for k in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN') if env.get(k)]
    if len(credentials) != 1 or len(env[credentials[0]]) < 4:
        raise ValueError('Supply exactly one API key or auth token')
    url = urlsplit(env.get('ANTHROPIC_BASE_URL', ''))
    if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Supply a base URL without credentials, query or fragment')
    if url.scheme == 'http' and url.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Remote provider URLs must use HTTPS')
    if effort and effort not in ('low', 'medium', 'high', 'xhigh', 'max'):
        raise ValueError('Unsupported effort level')
    # Pin every Claude alias to the same contestant. Never mix a helper model in.
    for key in ENV_KEYS:
        if key.endswith('_MODEL') or key == 'ANTHROPIC_MODEL':
            if env.get(key) and env[key] != model:
                raise ValueError('All supplied model aliases must name the same contestant')
            env[key] = model
    return {'model': model, 'effort': effort, 'env': env,
            'endpoint_origin': f'{url.scheme}://{url.netloc}'}


def register(directory, model_id, oneliner):
    model_id = safe_id(model_id)
    path = directory / (model_id + '.json')
    if path.exists():
        raise ValueError('Model id already registered; use a new id for another configuration')
    config = parse_oneliner(oneliner)
    config['id'] = model_id
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    atomic_json(path, config, private=True)
    return public_config(config)


def public_config(config):
    return {k: config[k] for k in ('id', 'model', 'effort', 'endpoint_origin')}


def read_config(directory, model_id):
    path = directory / (safe_id(model_id) + '.json')
    if path.stat().st_mode & 0o077:
        raise ValueError('Provider config must be private (chmod 600)')
    return load_json(path)


def redact(text, config):
    for key in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN'):
        secret = config['env'].get(key)
        if secret:
            text = text.replace(secret, '[REDACTED]')
    # A provider path can itself contain account identifiers.
    base = config['env']['ANTHROPIC_BASE_URL']
    return text.replace(base, config['endpoint_origin'])
