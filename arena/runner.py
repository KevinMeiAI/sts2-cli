from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from .common import TOOL_NAMES, atomic_json, digest, load_exam, load_json, minimal_env, utc
from .providers import public_config, redact

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def claude_version(executable):
    return subprocess.check_output([str(executable), '--version'], text=True, timeout=15).strip()


def command(executable, config, mcp_path):
    args = [str(executable), '-p', '--output-format', 'stream-json', '--verbose',
            '--restricted', '--tools', '', '--allowedTools', ','.join(TOOL_NAMES),
            '--strict-mcp-config', '--mcp-config', str(mcp_path), '--setting-sources', '',
            '--permission-mode', 'dontAsk', '--permission-prompts', 'none',
            '--disable-slash-commands', '--no-session-persistence', '--no-chrome',
            '--model', config['model'], '--system-prompt',
            (PACKAGE_ROOT / 'arena/prompt.txt').read_text()]
    if config['env'].get('ANTHROPIC_API_KEY'):
        args.append('--bare')
    if config.get('effort'):
        args.extend(['--effort', config['effort']])
    # stdin carries only this prompt, never the provider oneliner.
    return args


def time_limit(policy, mode):
    seconds = policy['pilot_seconds'] if mode == 'pilot' else policy['official_seconds']
    if mode == 'official' and policy.get('official_unlimited') is True:
        if seconds is not None:
            raise ValueError('Unlimited policy must not also specify a time limit')
        return None
    if seconds is None:
        raise ValueError('Official time limit is unset; select seconds or explicit unlimited mode')
    if type(seconds) is not int or seconds <= 0:
        raise ValueError('Time limit must be a positive integer')
    return seconds


def session_headers(existing, session_id):
    headers = [h for h in existing.splitlines() if h.split(':', 1)[0].strip().lower() != 'x-session-id']
    return '\n'.join(headers + ['X-Session-Id: ' + session_id])


def run(manifest, game_root, private_dir, config, mode, case_id, executable, stop_event=None, on_technical_failure=None):
    manifest, game_root = Path(manifest).resolve(), Path(game_root).resolve()
    exam = load_exam(manifest, game_root)
    version = claude_version(executable)
    if version != exam['claude_version']:
        raise ValueError('Claude Code version differs from the frozen exam')
    policy_path = manifest.parent / 'policy.json'
    policy = load_json(policy_path)
    seconds = time_limit(policy, mode)
    if mode == 'official':
        for previous in manifest.parent.glob('runs/official/*/*/run.json'):
            if load_json(previous)['policy_sha256'] != digest(policy_path):
                raise ValueError('Official policy changed after the first attempt')
    if mode == 'pilot':
        case_id = exam['pilot']['id']
    if case_id not in {c['id'] for c in exam['cases']} | {exam['pilot']['id']}:
        raise ValueError('Unknown exam case')
    if mode == 'official' and case_id == exam['pilot']['id']:
        raise ValueError('The practice seed is not an official case')
    directory = manifest.parent / 'runs' / mode / config['id'] / case_id
    directory.mkdir(parents=True, exist_ok=False)
    private = Path(private_dir).resolve() / 'sessions' / exam['id'] / mode / config['id'] / case_id
    private.mkdir(parents=True, mode=0o700, exist_ok=False)
    private.chmod(0o700)
    cwd = private / 'cwd'
    cwd.mkdir(mode=0o700)
    home = private / 'home'
    home.mkdir(mode=0o700)
    mcp_path = private / 'mcp.json'
    atomic_json(mcp_path, {'mcpServers': {'sts2_exam': {'type': 'stdio',
        'command': sys.executable, 'args': ['-m', 'arena.server', '--manifest', str(manifest),
        '--case', case_id, '--mode', mode, '--game-root', str(game_root),
        '--directory', str(directory)], 'env': {'PYTHONPATH': str(PACKAGE_ROOT)}}}}, private=True)
    env = minimal_env()
    env.update(config['env'])
    session_id = str(uuid.uuid4())
    env['ANTHROPIC_CUSTOM_HEADERS'] = session_headers(env.get('ANTHROPIC_CUSTOM_HEADERS', ''), session_id)
    env.update({'HOME': str(home), 'CLAUDE_CONFIG_DIR': str(private / 'claude'),
                'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1', 'DISABLE_AUTOUPDATER': '1',
                'DISABLE_TELEMETRY': '1', 'DISABLE_ERROR_REPORTING': '1',
                'CLAUDE_CODE_SIMPLE': '1', 'ENABLE_TOOL_SEARCH': 'false',
                'MCP_TOOL_TIMEOUT': '35000', 'MAX_MCP_OUTPUT_TOKENS': '100000'})
    metadata = {'schema': 1, 'model_id': config['id'], 'provider': public_config(config),
        'mode': mode, 'case_id': case_id, 'started_at': utc(), 'time_limit_seconds': seconds,
        'exam_sha256': digest(manifest), 'policy_sha256': digest(policy_path),
        'claude_version': version, 'status': 'running', 'allowed_tools': TOOL_NAMES}
    metadata['session_header_id'] = session_id
    atomic_json(directory / 'run.json', metadata)
    events, parsing_errors = [], []
    def capture(stream, path, structured=False):
        with open(path, 'w') as output:
            for line in stream:
                cleaned = redact(line, config)
                output.write(cleaned)
                output.flush()
                if structured:
                    try:
                        event = json.loads(cleaned)
                        if isinstance(event, dict):
                            events.append(event)
                    except ValueError:
                        parsing_errors.append('Non-JSON Claude stdout')
    started = time.monotonic()
    proc = None
    readers = []
    stopped = None
    terminal_since = None
    def notify_failure(reason):
        if on_technical_failure is not None:
            on_technical_failure(reason)

    try:
        if stop_event is not None and stop_event.is_set():
            stopped = 'interrupted'
        else:
            proc = subprocess.Popen(command(executable, config, mcp_path), cwd=cwd, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, start_new_session=True)
        if proc is not None:
            metadata['claude_pid'] = proc.pid
            atomic_json(directory / 'run.json', metadata)
            for stream, filename, structured in [(proc.stdout, 'claude.jsonl', True), (proc.stderr, 'claude.stderr.log', False)]:
                thread = threading.Thread(target=capture, args=(stream, directory / filename, structured), daemon=True)
                thread.start()
                readers.append(thread)
            proc.stdin.write('Begin your assigned run now. Keep playing through every act until game_over.\n')
            proc.stdin.close()
            while proc.poll() is None:
                if stop_event is not None and stop_event.is_set():
                    stopped = 'interrupted'
                    break
                init = next((e for e in events if e.get('type') == 'system' and e.get('subtype') == 'init'), None)
                if init and set(init.get('tools', [])) != set(TOOL_NAMES):
                    stopped = 'tool_isolation_failure'
                    notify_failure(stopped)
                    break
                if parsing_errors or any(b.get('name') not in TOOL_NAMES for e in events if e.get('type') == 'assistant' for b in e.get('message', {}).get('content', []) if b.get('type') == 'tool_use'):
                    stopped = 'technical_failure'
                    notify_failure('claude_protocol_failure')
                    break
                current_path = directory / 'current.json'
                if (directory / 'fault.json').exists():
                    stopped = 'technical_failure'
                    notify_failure('engine_fault')
                    break
                if current_path.exists():
                    current = load_json(current_path)
                    if current.get('fault'):
                        stopped = 'technical_failure'
                        notify_failure('engine_fault')
                        break
                    if current['score']['terminal']:
                        terminal_since = terminal_since or time.monotonic()
                        if time.monotonic() - terminal_since > 3:
                            stopped = 'game_finished'
                            break
                if seconds is not None and time.monotonic() - started >= seconds:
                    stopped = 'time_limit'
                    break
                if stop_event is None:
                    time.sleep(.1)
                else:
                    stop_event.wait(.1)
    except KeyboardInterrupt:
        stopped = 'interrupted'
    except Exception as error:
        stopped = 'runner_error'
        metadata['error'] = redact(f'{type(error).__name__}: {error}', config)
        notify_failure('runner_error')
    finally:
        if proc:
            # Also clean up MCP/game descendants after an early Claude exit.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=3)
            # Close descendant pipes before joining readers; otherwise an orphan
            # that ignores SIGTERM can hold shutdown up for each stream.
            # A child can ignore SIGTERM even when its parent has already exited.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            for reader in readers:
                reader.join(timeout=3)
            for stream in (proc.stdout, proc.stderr):
                stream.close()
    current = load_json(directory / 'current.json') if (directory / 'current.json').exists() else None
    init = next((e for e in events if e.get('type') == 'system' and e.get('subtype') == 'init'), None)
    result = next((e for e in reversed(events) if e.get('type') == 'result'), None)
    tools_ok = init is not None and set(init.get('tools', [])) == set(TOOL_NAMES)
    technical = stopped in ('technical_failure', 'runner_error', 'tool_isolation_failure') or (directory / 'fault.json').exists() or bool(current and current.get('fault'))
    if technical or parsing_errors or (init is not None and not tools_ok):
        status = 'technical_failure'
    elif current and current['score']['terminal']:
        status = 'completed'
    elif stopped == 'time_limit':
        status = 'time_limit'
    elif stopped == 'interrupted':
        status = 'interrupted'
    elif not tools_ok:
        status = 'technical_failure'
    elif (result and result.get('is_error')) or (proc and proc.returncode != 0):
        status = 'provider_error'
    else:
        status = 'early_stop'
    calls = [b for e in events if e.get('type') == 'assistant'
             for b in e.get('message', {}).get('content', []) if b.get('type') == 'tool_use']
    if any(b.get('name') not in TOOL_NAMES for b in calls):
        status = 'technical_failure'
    if status == 'technical_failure':
        notify_failure(stopped or 'claude_protocol_failure')
    successful_actions = invalid_actions = 0
    if (directory / 'game.jsonl').exists():
        with open(directory / 'game.jsonl') as trace:
            for line in trace:
                entry = json.loads(line)
                if entry['request']['cmd'] == 'action':
                    if entry['response'].get('type') == 'error':
                        invalid_actions += 1
                    else:
                        successful_actions += 1
    metadata.update(status=status, ended_at=utc(), elapsed_seconds=round(time.monotonic() - started, 3),
        stop_reason=stopped, exit_code=proc.returncode if proc else None, tools_verified=tools_ok,
        connected=bool(tools_ok and successful_actions), tool_calls=len(calls),
        successful_game_actions=successful_actions, invalid_game_actions=invalid_actions,
        score=current['score'] if current else None,
        reported_models=sorted({e['message']['model'] for e in events if e.get('type') == 'assistant' and e.get('message', {}).get('model')}),
        usage=result.get('usage') if result else None,
        model_usage=result.get('modelUsage') if result else None,
        claude_reported_cost_usd=result.get('total_cost_usd') if result else None,
        result_subtype=result.get('subtype') if result else None)
    atomic_json(directory / 'result.json', metadata)
    atomic_json(directory / 'run.json', metadata)
    return metadata
