import json


def test_diverged_restore_requires_fresh_process_instead_of_retrying(game, tmp_path):
    game.skip_neow(game.start(seed='failed-restore'))
    path = tmp_path / 'original.save'
    assert game.send({'cmd': 'write_continue_save', 'path': str(path)})['success']
    saved = json.loads(path.read_text())
    saved['expected_state']['player']['hp'] += 1
    state = game.send({'cmd': 'load_save', 'json': json.dumps(saved)})
    assert state['type'] == 'error' and 'diverged' in state['message']
    retry = game.send({'cmd': 'load_save', 'path': str(path)})
    assert retry['type'] == 'error' and 'restart the CLI process' in retry['message']
