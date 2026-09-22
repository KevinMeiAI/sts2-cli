"""Replay the actual manually directed Act 1 + Act 2 wins, without debug state."""
import json
from pathlib import Path
import pytest
from test_session_checkpoint import save_and_restore


@pytest.mark.parametrize('fixture,hp,gold,rounds', [
    ('ironclad_act2', 16, 230, 9),
    ('necrobinder_a10_act2', 6, 96, 10),
])
def test_complete_manual_act2_trace_and_exact_checkpoint(game, tmp_path, fixture, hp, gold, rounds):
    root = Path(__file__).parent / 'fixtures'
    commands = json.loads((root / f'{fixture}_commands.json').read_text())
    expected = json.loads((root / f'{fixture}_expected.json').read_text())
    last_boss_round = 0
    for command in commands:
        assert command['cmd'] in ('start_run', 'action')  # No synthetic state/room changes.
        state = game.send(command)
        assert state.get('type') != 'error', state
        assert state.get('context', {}).get('act', 1) <= 2
        if state.get('decision') == 'combat_play' and state['context']['act'] == 2 and state['context']['room_type'] == 'Boss':
            last_boss_round = state['round']
    assert last_boss_round == rounds
    assert state == expected
    assert state['decision'] == 'card_reward'
    assert (state['context']['act'], state['context']['floor'], state['context']['room_type']) == (2, 16, 'Boss')
    assert (state['player']['hp'], state['player']['gold']) == (hp, gold)
    resumed, _ = save_and_restore(game, state, tmp_path)
    resumed.close()
    game.close()
    for process in (game, resumed):
        assert not any('[ERROR]' in line or 'Exception' in line or 'timeout' in line.lower() for line in process.stderr_lines)
