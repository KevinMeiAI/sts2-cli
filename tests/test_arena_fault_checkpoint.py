import json
import pytest
from arena.engine import Engine, EngineError
from arena.server import Attempt
from test_arena import ROOT, manifest


@pytest.mark.parametrize('response', [
    {'type': 'error', 'message': 'Event choose failed: NullReferenceException'},
    {'type': 'error', 'code': 'combat_not_completed', 'message': 'Combat did not settle'},
])
def test_native_fault_keeps_last_healthy_checkpoint_and_freezes_attempt(tmp_path, monkeypatch, response):
    directory = tmp_path / 'attempt'
    attempt = Attempt(manifest(tmp_path), 'practice', 'pilot', ROOT, directory)
    checkpoint = directory / 'checkpoint.save'
    initial = checkpoint.read_bytes()
    before = attempt.state
    send = attempt.game.send
    def fail_action(command):
        return response if command['cmd'] == 'action' else send(command)
    monkeypatch.setattr(attempt.game, 'send', fail_action)
    try:
        result = attempt.call('act', {'action': 'choose_option', 'args': {'option_index': 0}})
        assert result['error'] == response
        assert checkpoint.read_bytes() == initial
        assert json.loads((directory / 'fault.json').read_text())['response'] == response
        assert json.loads((directory / 'current.json').read_text())['fault'] == 'engine_error'
        with pytest.raises(EngineError, match='frozen'):
            attempt.call('act', {'action': 'choose_option', 'args': {'option_index': 0}})
    finally:
        attempt.close()
    game = Engine(ROOT, tmp_path / 'restore.log')
    try:
        assert game.send({'cmd': 'load_save', 'path': str(checkpoint)}) == before
    finally:
        game.close()
