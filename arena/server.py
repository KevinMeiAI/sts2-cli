"""Minimal stdio MCP judge. The model can observe/play, never restart or debug."""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from .common import ACTIONS, atomic_json, compact, load_exam, utc
from .engine import Engine, EngineError
from .scoring import score

TOOLS = [
    {'name': 'get_state', 'description': 'Get the current legal decision. view=full includes the complete deck; compact omits only the repeated deck.',
     'inputSchema': {'type': 'object', 'properties': {'view': {'type': 'string', 'enum': ['compact', 'full']}}, 'additionalProperties': False}},
    {'name': 'get_map', 'description': 'Inspect the current act map and routes. This does not move.',
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'act', 'description': 'Perform exactly one legal game action. Read returned state before the next action because indices change. Cannot restart, load, edit, debug or change the seed.',
     'inputSchema': {'type': 'object', 'required': ['action'], 'properties': {
         'action': {'type': 'string', 'enum': sorted(ACTIONS)},
         'args': {'type': 'object', 'properties': {
             key: {'type': 'integer', 'minimum': 0} for key in ('card_index', 'target_index', 'option_index', 'potion_index', 'relic_index', 'bundle_index', 'col', 'row', 'x', 'y')
         } | {'indices': {'type': 'string'}, 'tool': {'type': 'string', 'enum': ['big', 'small']}}, 'additionalProperties': False}}, 'additionalProperties': False}},
]
ARG_KEYS = set(TOOLS[2]['inputSchema']['properties']['args']['properties'])


def validate_action(arguments):
    if not isinstance(arguments, dict) or set(arguments) - {'action', 'args'}:
        raise ValueError('Only action and args are accepted')
    if arguments.get('action') not in ACTIONS:
        raise ValueError('Action is not allowed by the exam')
    args = arguments.get('args', {})
    if not isinstance(args, dict) or set(args) - ARG_KEYS:
        raise ValueError('Unknown action argument')
    for key, value in args.items():
        if key in ('indices', 'tool'):
            if not isinstance(value, str) or len(value) > 200:
                raise ValueError('Invalid string argument')
        elif type(value) is not int or value < 0 or value > 10000:
            raise ValueError('Invalid integer argument')
    if 'tool' in args and args['tool'] not in ('big', 'small'):
        raise ValueError('Invalid crystal sphere tool')
    return {'cmd': 'action', 'action': arguments['action'], 'args': args}


class Attempt:
    def __init__(self, manifest, case_id, mode, game_root, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        # A reconnect must not reroll an already-started attempt.
        fd = os.open(self.directory / 'engine.lock', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        exam = load_exam(manifest, game_root)
        case = exam['pilot'] if mode == 'pilot' else next(c for c in exam['cases'] if c['id'] == case_id)
        self.game = Engine(game_root, self.directory / 'engine.log')
        self.log = open(self.directory / 'game.jsonl', 'a')
        self.step = 0
        self.fault = None
        try:
            self.state = self.request({'cmd': 'start_run', 'character': case['character'],
                                       'seed': case['seed'], 'ascension': 10, 'lang': 'en'})
            if self.state.get('type') == 'error':
                raise EngineError(self.state['message'])
            self.refresh()
        except Exception:
            self.close()
            raise

    def request(self, command):
        response = self.game.send(command)
        self.step += 1
        self.log.write(json.dumps({'step': self.step, 'at': utc(), 'request': command,
                                  'response': response}, ensure_ascii=False) + '\n')
        self.log.flush()
        return response

    def refresh(self):
        self.metrics = self.request({'cmd': 'get_run_metrics'})
        if self.metrics.get('type') != 'run_metrics':
            raise EngineError('Native scoring metrics are unavailable')
        if self.game.faults:
            self.fault = 'engine_exception'
        atomic_json(self.directory / 'current.json', {'at': utc(), 'state': self.state,
                    'metrics': self.metrics, 'score': score(self.state, self.metrics), 'fault': self.fault})
        if self.fault:
            # An exception can leave a partially applied action in the native
            # replay history. Keep the last healthy checkpoint for diagnosis.
            return
        saved = self.request({'cmd': 'write_continue_save', 'path': str(self.directory / 'checkpoint.save')})
        if not saved.get('success'):
            raise EngineError('Judge checkpoint could not be saved')

    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError('Tool arguments must be an object')
        if self.fault:
            raise EngineError('Attempt frozen after a technical fault')
        if name == 'get_state':
            if set(arguments) - {'view'} or arguments.get('view', 'compact') not in ('compact', 'full'):
                raise ValueError('Invalid state view')
            return {'state': self.state if arguments.get('view') == 'full' else compact(self.state),
                    'progress': {'total_floor': self.metrics['total_floor']}}
        if name == 'get_map':
            if arguments:
                raise ValueError('get_map takes no arguments')
            return self.request({'cmd': 'get_map'})
        if name != 'act':
            raise ValueError('Unknown tool')
        command = validate_action(arguments)
        if self.state.get('decision') == 'game_over':
            raise ValueError('Attempt has finished; further actions are disabled')
        response = self.request(command)
        if response.get('type') == 'error':
            if 'Exception' in response.get('message', '') or response.get('code') == 'combat_not_completed':
                self.fault = 'engine_error'
                atomic_json(self.directory / 'fault.json', {'at': utc(), 'type': self.fault,
                    'request': command, 'response': response, 'checkpoint_preserved': True})
            self.state = self.request({'cmd': 'get_state'})
        else:
            self.state = response
        self.refresh()
        if response.get('type') == 'error':
            return {'error': response, 'state': compact(self.state)}
        return {'state': compact(self.state), 'progress': {'total_floor': self.metrics['total_floor']}}

    def close(self):
        self.game.close()
        self.log.close()


def serve(attempt):
    for line in sys.stdin:
        message = None
        try:
            if len(line) > 1_000_000:
                raise ValueError('Request too large')
            message = json.loads(line)
            if 'id' not in message:
                continue
            method = message.get('method')
            if method == 'initialize':
                result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'sts2-exam-judge', 'version': '1.0.0'}}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                params = message.get('params', {})
                response = attempt.call(params.get('name'), params.get('arguments', {}))
                result = {'content': [{'type': 'text', 'text': json.dumps(response, ensure_ascii=False)}],
                          'isError': 'error' in response}
            else:
                raise ValueError('Unsupported MCP method')
            output = {'jsonrpc': '2.0', 'id': message['id'], 'result': result}
        except Exception as error:
            if not isinstance(message, dict) or 'id' not in message:
                continue
            if isinstance(error, EngineError):
                atomic_json(attempt.directory / 'fault.json', {'at': utc(), 'type': type(error).__name__, 'message': str(error)})
                attempt.fault = 'engine_error'
            output = {'jsonrpc': '2.0', 'id': message['id'], 'result': {
                'content': [{'type': 'text', 'text': json.dumps({'error': str(error)})}], 'isError': True}}
        print(json.dumps(output, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    for name in ('manifest', 'case', 'game-root', 'directory'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--mode', choices=['pilot', 'official'], required=True)
    args = parser.parse_args()
    # Never propagate provider credentials into the game process.
    for key in list(os.environ):
        if key.startswith('ANTHROPIC_') or 'API_KEY' in key or 'AUTH_TOKEN' in key:
            os.environ.pop(key, None)
    attempt = Attempt(args.manifest, args.case, args.mode, args.game_root, args.directory)
    try:
        serve(attempt)
    finally:
        attempt.close()


if __name__ == '__main__':
    main()
