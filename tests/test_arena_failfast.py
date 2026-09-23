"""Exercise full coordinator/runner shutdown with real OS process groups, no API."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import pytest
from arena import batch, runner
from arena.__main__ import initialize
from arena.common import atomic_json, load_json, TOOL_NAMES
from arena.providers import register

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('failure', ['engine_fault', 'protocol', 'tools'])
def test_failure_stops_all_six_process_groups_without_starting_queued(tmp_path, monkeypatch, failure):
    monkeypatch.setattr('arena.__main__.claude_version', lambda _: 'mock')
    monkeypatch.setattr(runner, 'claude_version', lambda _: 'mock')
    monkeypatch.setattr(batch, 'claude_version', lambda _: 'mock')
    exam = tmp_path / 'exam'
    private = tmp_path / 'private'
    initialize(exam, ROOT, 'unused')
    atomic_json(exam / 'policy.json', {'pilot_seconds': 600, 'official_seconds': None,
        'official_unlimited': True, 'concurrency_per_model': 2, 'stop_on_technical_failure': True})
    for model in ('a', 'b', 'c'):
        register(private / 'providers', model, 'ANTHROPIC_BASE_URL=https://example.invalid ANTHROPIC_AUTH_TOKEN=dummy claude --model mock')
    fake = tmp_path / 'fake_claude.py'
    fake.write_text('''import json, os, signal, subprocess, sys, time
from pathlib import Path
mcp=json.loads(Path(sys.argv[1]).read_text())
args=mcp['mcpServers']['sts2_exam']['args']
d=Path(args[args.index('--directory')+1]); root=d.parents[1]
def stop(*_):
    (d/'stopped.json').write_text(json.dumps({'at':time.monotonic()}))
    sys.exit(0)
signal.signal(signal.SIGTERM,stop)
child=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'])
(d/'child.pid').write_text(str(child.pid))
# One healthy sibling intentionally has not finished Claude startup.
if not (d.parent.name=='b' and d.name=='ironclad'):
    print(json.dumps({'type':'system','subtype':'init','tools':json.loads(sys.argv[2])}),flush=True)
(d/'ready').touch()
if d.parent.name=='a' and d.name=='ironclad':
    deadline=time.monotonic()+10
    while len(list(root.glob('*/*/ready')))<6:
        if time.monotonic()>deadline: raise RuntimeError('Six lanes did not start')
        time.sleep(.01)
    (d/'injected.json').write_text(json.dumps({'at':time.monotonic()}))
    if sys.argv[3]=='engine_fault': (d/'fault.json').write_text('{}')
    elif sys.argv[3]=='protocol': print('malformed stdout',flush=True)
    else: print(json.dumps({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Bash'}]}}),flush=True)
time.sleep(60)
''')
    monkeypatch.setattr(runner, 'command', lambda exe, config, mcp: [sys.executable, str(fake), str(mcp), json.dumps(TOOL_NAMES), failure])
    result = batch.launch(exam / 'exam.json', ROOT, private, ['a', 'b', 'c'], 'unused')
    assert result['status'] == 'halted_technical_failure'
    halt = load_json(exam / 'halt.json')
    assert halt['origin'] == 'a/ironclad'
    progress = load_json(exam / 'progress.json')
    assert progress['active'] == 0
    assert sum(r['status'] == 'technical_failure' for r in progress['jobs']) == 1
    assert sum(r['status'] == 'interrupted' for r in progress['jobs']) == 5
    assert sum(r['status'] == 'cancelled_before_start' for r in progress['jobs']) == 6
    paths = list((exam / 'runs/official').glob('*/*/run.json'))
    assert len(paths) == 6
    injected = load_json(exam / 'runs/official/a/ironclad/injected.json')['at']
    for path in paths:
        d = path.parent
        assert load_json(d / 'stopped.json')['at'] - injected < 1.5
        pid = load_json(path)['claude_pid']
        with pytest.raises(ProcessLookupError): os.killpg(pid, 0)
    with pytest.raises(ValueError, match='already exists'):
        batch.launch(exam / 'exam.json', ROOT, private, ['a', 'b', 'c'], 'unused')


def test_first_failure_wins_and_signals_before_disk_write(tmp_path, monkeypatch):
    stop = threading.Event()
    real_write = batch.atomic_json
    def write(path, record):
        assert stop.is_set()
        real_write(path, record)
    monkeypatch.setattr(batch, 'atomic_json', write)
    breaker = batch.FailureStop(stop, tmp_path / 'halt.json')
    breaker.trip('first', 'engine_fault')
    breaker.trip('second', 'other')
    assert load_json(tmp_path / 'halt.json')['origin'] == 'first'


def test_worker_exception_stops_other_models_and_queued(tmp_path, monkeypatch):
    monkeypatch.setattr('arena.__main__.claude_version', lambda _: 'mock')
    monkeypatch.setattr(batch, 'claude_version', lambda _: 'mock')
    exam, private = tmp_path / 'exam', tmp_path / 'private'
    initialize(exam, ROOT, 'unused')
    atomic_json(exam / 'policy.json', {'pilot_seconds':600, 'official_seconds':None,
        'official_unlimited':True, 'concurrency_per_model':2, 'stop_on_technical_failure':True})
    register(private / 'providers', 'a', 'ANTHROPIC_BASE_URL=https://example.invalid ANTHROPIC_AUTH_TOKEN=dummy claude --model mock')
    def fail(*args): raise RuntimeError('injected runner exception')
    monkeypatch.setattr(batch, 'run', fail)
    assert batch.launch(exam / 'exam.json', ROOT, private, ['a'], 'unused')['status'] == 'halted_technical_failure'
    assert load_json(exam / 'halt.json')['reason'] == 'worker_exception'
    assert any(r['status'] == 'cancelled_before_start' for r in load_json(exam / 'progress.json')['jobs'])
