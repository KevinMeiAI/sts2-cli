import json
from pathlib import Path
from test_session_checkpoint import save_and_restore


def test_lantern_key_reward_is_obtained_once_and_restored(game, tmp_path):
    commands = json.loads((Path(__file__).parent / 'fixtures/ironclad_act2_commands.json').read_text())
    saw_dagger = saw_goopy = False
    for command in commands:
        state = game.send(command)
        assert state.get('type') != 'error', state
        for card in state.get('hand', []):
            if card['name'] == 'Dagger Spray':
                assert all(p['repeat'] == 2 for p in card['damage_by_target'])
                saw_dagger = True
            if card.get('enchantment') == 'Goopy' and card.get('enchantment_amount', 0) > 1:
                assert card['stats']['block'] > 5
                saw_goopy = True
        if state.get('decision') == 'map_select' and state['context']['act'] == 2 and state['context']['floor'] == 10:
            break
    assert saw_dagger and saw_goopy
    assert state['decision'] == 'map_select'
    assert (state['context']['act'], state['context']['floor']) == (2, 10)
    assert sum(c['name'] == 'Lantern Key' for c in state['player']['deck']) == 1
    for _ in range(3):
        assert game.send({'cmd': 'get_state'}) == state
    resumed, _ = save_and_restore(game, state, tmp_path)
    resumed.close()


def test_decimillipede_revives_and_death_settles(game):
    commands = json.loads((Path(__file__).parent / 'fixtures/ironclad_act2_commands.json').read_text())
    seen_dead_segment = seen_revived_segment = False
    for command in commands:
        state = game.send(command)
        assert state.get('type') != 'error', state
        if state.get('decision') == 'combat_play' and state['context']['act'] == 2 and state['context']['floor'] == 11:
            if len(state['enemies']) == 2:
                seen_dead_segment = True
            if seen_dead_segment and len(state['enemies']) == 3:
                seen_revived_segment = True
        if state.get('decision') == 'card_reward' and state['context']['act'] == 2 and state['context']['floor'] == 11:
            break
    assert seen_dead_segment and seen_revived_segment
    assert state['decision'] == 'card_reward'
    assert state['context']['room_type'] == 'Elite'
    assert not any('[ERROR]' in line for line in game.stderr_lines)
