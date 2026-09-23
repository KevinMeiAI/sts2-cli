"""One random A10 Defect run, replaying only the recorded manual decisions."""
import json
from pathlib import Path
from test_play import play
from test_session_checkpoint import save_and_restore


def test_manual_defect_a10_trace_and_exact_defeat(game, tmp_path, monkeypatch):
    monkeypatch.setattr(play, 'LANG', 'en')
    root = Path(__file__).parent / 'fixtures'
    commands = json.loads((root / 'defect_a10_commands.json').read_text())
    expected = json.loads((root / 'defect_a10_expected.json').read_text())
    assert len(commands) == 330
    assert commands[0] == {'cmd': 'start_run', 'character': 'Defect', 'seed': '8J7GIO83BN',
                           'ascension': 10, 'lang': 'en'}
    orb_types = set()
    rejected = boss_round = elite_round = 0
    saw_empty = saw_x = saw_upgraded_reward = saw_echo = saw_plasma_energy = False
    state = None
    for command in commands:
        assert command['cmd'] in ('start_run', 'action')
        before = state
        state = game.send(command)
        if state.get('type') == 'error':
            # Two malformed requests in the real log were caller errors;
            # keep them to verify they do not change the pending reward.
            assert state['message'] in ("select_card_reward requires 'card_index'",
                                         "select_map_node requires 'col' and 'row'")
            state = game.send({'cmd': 'get_state'})
            assert state == before
            rejected += 1
        ctx = state.get('context', {})
        if state.get('decision') == 'combat_play':
            assert 'orb_slots' in state and 'orbs' in state
            saw_empty |= not state['orbs']
            for orb in state['orbs']:
                orb_types.add(orb['type'])
                assert not orb['description_is_template']
                assert '{' not in orb['description']
                if orb['type'] == 'Plasma':
                    assert '1 Energy' in orb['description'] and '2 Energy' in orb['description']
                    assert 'unaffected by Focus' in orb['description']
                    saw_plasma_energy |= state['energy'] == 7
            if ctx['act'] == 1 and ctx['room_type'] == 'Boss':
                boss_round = state['round']
            if ctx['act'] == 2 and ctx['room_type'] == 'Elite':
                elite_round = state['round']
            saw_echo |= any(p['name'] == 'Echo Form' for p in state.get('player_powers') or [])
        if state.get('decision') == 'card_reward':
            for c in state['cards']:
                assert isinstance(c['upgraded'], bool)
                if c.get('costs_x'):
                    assert c['name'] == 'Tempest'
                    assert play.card_energy_cost(c) == 'X'
                    saw_x = True
                if c['id'] == 'CARD.GUNK_UP' and c['upgraded']:
                    assert c['stats']['damage'] == 5 and c['after_upgrade'] is None
                    saw_upgraded_reward = True
    assert state == expected
    assert state['decision'] == 'game_over' and state['victory'] is False
    assert (state['act'], state['floor'], state['player']['hp'], state['player']['gold']) == (2, 14, 0, 198)
    assert boss_round == 10 and elite_round == 4 and rejected == 2
    assert orb_types == {'Lightning', 'Frost', 'Dark', 'Glass', 'Plasma'}
    assert all((saw_empty, saw_x, saw_upgraded_reward, saw_echo, saw_plasma_energy))
    assert game.send({'cmd': 'get_state'}) == state
    metrics = game.send({'cmd': 'get_run_metrics'})
    # The final end_turn deals Lightning + Glass damage before the fatal attack.
    # A cached pre-action enemy state would incorrectly score 61 / 155.
    assert (metrics['total_floor'], metrics['enemy_hp'], metrics['enemy_max_hp']) == (31, 54, 155)
    assert metrics['player_hp'] == 0 and metrics['source'] == 'native_post_action'
    assert game.send({'cmd': 'get_state'}) == state
    restored, _ = save_and_restore(game, state, tmp_path)
    assert restored.send({'cmd': 'get_run_metrics'}) == metrics
    restored.close()
    for process in (game, restored):
        assert not any('Exception' in line or '[ERROR]' in line or 'timeout' in line.lower()
                       for line in process.stderr_lines)
