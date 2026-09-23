"""Opt-in real Claude Code + local mock provider + native game smoke test.

RUN_CLAUDE_MOCK=1 ./sts2 test -q tests/test_arena_claude_mock.py
No real model or billable provider is used; this is not a gameplay result.
"""
import json
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pytest
from arena.__main__ import initialize
from arena.common import TOOL_NAMES, atomic_json
from arena.providers import parse_oneliner
from arena.runner import run

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = shutil.which('claude') or str(Path.home() / '.local/bin/claude')
pytestmark = pytest.mark.skipif(os.environ.get('RUN_CLAUDE_MOCK') != '1', reason='Explicitly opt in to local Claude Code infrastructure test')


@pytest.mark.parametrize('auth', ['ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN'])
@pytest.mark.parametrize('timeout', [False, True, 'unlimited'])
def test_real_claude_uses_only_game_tools_with_mock_provider(tmp_path, auth, timeout):
    requests = []
    release = threading.Event()
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if 'count_tokens' in self.path:
                data = json.dumps({'input_tokens': 100}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            requests.append({'body': body, 'api_key': self.headers.get('x-api-key'), 'auth': self.headers.get('Authorization')})
            count = sum(1 for msg in body.get('messages', []) if isinstance(msg.get('content'), list)
                        for block in msg['content'] if block.get('type') == 'tool_result')
            if timeout is True and count >= 2:
                release.wait(10)
                return
            if count == 0:
                block = {'type': 'tool_use', 'id': 'toolu_mock_state', 'name': TOOL_NAMES[0], 'input': {}}
                reason = 'tool_use'
            elif count == 1:
                block = {'type': 'tool_use', 'id': 'toolu_mock_action', 'name': TOOL_NAMES[2],
                         'input': {'action': 'choose_option', 'args': {'option_index': 0}}}
                reason = 'tool_use'
            else:
                block = {'type': 'text', 'text': 'Mock connectivity test finished.'}
                reason = 'end_turn'
            response = {'id': 'msg_mock_' + str(count), 'type': 'message', 'role': 'assistant',
                        'model': 'mock-exam-model', 'content': [block], 'stop_reason': reason,
                        'stop_sequence': None, 'usage': {'input_tokens': 100, 'output_tokens': 20}}
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream' if body.get('stream') else 'application/json')
            self.end_headers()
            if not body.get('stream'):
                self.wfile.write(json.dumps(response).encode())
                return
            start = dict(response, content=[], stop_reason=None)
            start['usage'] = {'input_tokens': 100, 'output_tokens': 0}
            events = [{'type': 'message_start', 'message': start}]
            if block['type'] == 'tool_use':
                events += [{'type': 'content_block_start', 'index': 0, 'content_block': dict(block, input={})},
                           {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(block['input'])}}]
            else:
                events += [{'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
                           {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': block['text']}}]
            events += [{'type': 'content_block_stop', 'index': 0},
                       {'type': 'message_delta', 'delta': {'stop_reason': reason, 'stop_sequence': None}, 'usage': {'output_tokens': 20}},
                       {'type': 'message_stop'}]
            for event in events:
                self.wfile.write(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode())
            self.wfile.flush()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        exam_dir = tmp_path / 'mock-exam'
        initialize(exam_dir, ROOT, CLAUDE)
        # This synthetic test has a short bound and its own throwaway exam.
        atomic_json(exam_dir / 'policy.json', {'pilot_seconds': 4 if timeout is True else 30,
                    'official_seconds': None, 'official_unlimited': timeout == 'unlimited'})
        secret = 'dummy-not-a-real-key'
        config = parse_oneliner(f'ANTHROPIC_BASE_URL=http://127.0.0.1:{server.server_port} {auth}={secret} claude --model mock-exam-model')
        config['id'] = 'mock'
        mode, case = ('official', 'ironclad') if timeout == 'unlimited' else ('pilot', 'practice')
        result = run(exam_dir / 'exam.json', ROOT, tmp_path / 'private', config, mode, case, CLAUDE)
        assert result['connected'], result
        assert result['status'] == ('time_limit' if timeout is True else 'early_stop'), result
        if timeout == 'unlimited':
            assert result['time_limit_seconds'] is None
        assert result['score']['terminal'] is False
        assert result['tools_verified'] and result['tool_calls'] == 2
        assert requests
        for req in requests:
            assert req['body']['model'] == 'mock-exam-model'
            assert {t['name'] for t in req['body']['tools']} == set(TOOL_NAMES)
            if auth == 'ANTHROPIC_API_KEY':
                assert req['api_key'] == secret and not req['auth']
            else:
                assert req['auth'] == 'Bearer ' + secret and not req['api_key']
        directory = exam_dir / 'runs' / mode / 'mock' / case
        trace = [json.loads(line) for line in (directory / 'game.jsonl').read_text().splitlines()]
        assert sum(row['request']['cmd'] == 'start_run' for row in trace) == 1
        assert sum(row['request'].get('action') == 'choose_option' for row in trace) == 1
        assert (directory / 'checkpoint.save').exists()
        for path in directory.iterdir():
            if path.is_file():
                assert secret.encode() not in path.read_bytes(), path.name
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
