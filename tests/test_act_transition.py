"""Continue real first-act wins: native Ancient healing must run only once."""
import json
from pathlib import Path
import pytest
from test_session_checkpoint import save_and_restore


@pytest.mark.parametrize('fixture,reward,before,healed', [
    ('necrobinder_a10_act1_commands.json', 2, 22, 57),
    ('ironclad_act1_commands.json', 1, 58, 80),
])
def test_native_ancient_heal_once_and_checkpoint(game, tmp_path, fixture, reward, before, healed):
    commands = json.loads((Path(__file__).parent / 'fixtures' / fixture).read_text())
    for command in commands:
        state = game.send(command)
        assert state.get('type') != 'error', state
    assert state['decision'] == 'card_reward'
    state = game.act('select_card_reward', card_index=reward)
    assert state['context']['act'] == 2
    assert state['player']['hp'] == before  # not healed by the adapter
    assert len(state['choices']) == 1
    ancient = state['choices'][0]
    assert ancient['type'] == 'Ancient'
    denied = game.act('select_map_node', col=0, row=1)
    assert denied['type'] == 'error'
    assert game.send({'cmd': 'get_state'}) == state
    restored, _ = save_and_restore(game, state, tmp_path)
    try:
        state = restored.act('select_map_node', col=ancient['col'], row=ancient['row'])
        assert state['decision'] == 'event_choice', state
        assert state['player']['hp'] == healed
        assert not state['context']['boss']['name'].endswith('.name')
        assert restored.get_map()['boss']['name'] == state['context']['boss']['name']
        for _ in range(2):
            assert restored.send({'cmd': 'get_state'}) == state
        denied = restored.act('select_map_node', col=ancient['col'], row=ancient['row'])
        assert denied['type'] == 'error'
        assert restored.send({'cmd': 'get_state'}) == state
        resumed, _ = save_and_restore(restored, state, tmp_path)
        resumed.close()
    finally:
        restored.close()
