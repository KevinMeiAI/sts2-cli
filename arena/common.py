from __future__ import annotations
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

CHARACTERS = ('Ironclad', 'Silent', 'Defect', 'Necrobinder')
ACTIONS = {
    'select_map_node', 'play_card', 'end_turn', 'choose_option',
    'select_card_reward', 'skip_card_reward', 'buy_card', 'buy_relic',
    'buy_potion', 'remove_card', 'crystal_sphere_reveal', 'select_bundle',
    'select_cards', 'skip_select', 'use_potion', 'discard_potion',
    'leave_room', 'proceed',
}
TOOL_NAMES = ['mcp__sts2_exam__' + n for n in ('get_state', 'get_map', 'act')]


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, data, private=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + secrets.token_hex(4) + '.tmp')
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600 if private else 0o644)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.replace(tmp, path)


def load_json(path):
    return json.loads(Path(path).read_text())


def engine_fingerprints(game_root):
    root = Path(game_root)
    paths = ['sts2', 'src/Sts2Headless/bin/Debug/net9.0/Sts2Headless.dll',
             'src/Sts2Headless/bin/Debug/net9.0/GodotSharp.dll']
    paths += sorted(str(p.relative_to(root)) for p in (root / 'lib').glob('*.dll'))
    paths += sorted(str(p.relative_to(root)) for p in (root / 'localization_eng').glob('*.json'))
    return {p: digest(root / p) for p in paths}


def harness_fingerprints():
    root = Path(__file__).resolve().parent
    return {p.name: digest(p) for p in sorted(root.iterdir()) if p.suffix in ('.py', '.txt')}


def load_exam(path, game_root=None):
    path = Path(path).resolve()
    manifest = load_json(path)
    expected = path.with_suffix('.sha256').read_text().strip()
    if digest(path) != expected:
        raise ValueError('Exam manifest changed; create a new exam instead of editing a frozen one')
    if game_root and engine_fingerprints(game_root) != manifest['engine_files']:
        raise ValueError('Game/adapter binaries differ from the frozen exam')
    if harness_fingerprints() != manifest['harness_files']:
        raise ValueError('Arena code or prompt differs from the frozen exam')
    return manifest


def compact(state):
    # Keep all combat information and descriptions; omit only the repeated deck.
    out = dict(state)
    if isinstance(out.get('player'), dict):
        out['player'] = {k: v for k, v in out['player'].items() if k != 'deck'}
    return out


def minimal_env():
    keys = ('HOME', 'PATH', 'TMPDIR', 'LANG', 'LC_ALL', 'SYSTEMROOT')
    return {k: os.environ[k] for k in keys if k in os.environ}
