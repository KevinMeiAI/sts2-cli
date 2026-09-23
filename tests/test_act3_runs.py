"""Actual Act 1–3 continuations; every gameplay decision is recorded, not automated."""
import json
from pathlib import Path
import pytest
from test_session_checkpoint import save_and_restore
from test_play import play


@pytest.mark.parametrize('fixture,victory,hp,gold,rounds', [
    ('ironclad_act3', True, 86, 98, 3),
    ('necrobinder_a10_act3', False, 0, 110, 8),
])
def test_complete_manual_act3_trace_and_exact_ending(game, tmp_path, monkeypatch,
                                                    fixture, victory, hp, gold, rounds):
    monkeypatch.setattr(play, 'LANG', 'en')
    root = Path(__file__).parent / 'fixtures'
    commands = json.loads((root / f'{fixture}_commands.json').read_text())
    expected = json.loads((root / f'{fixture}_expected.json').read_text())
    last_boss_round = rejected = 0
    saw_custom_hand = saw_custom_selection = False
    state = None
    for command in commands:
        assert command['cmd'] in ('start_run', 'action')
        before = state
        state = game.send(command)
        if state.get('type') == 'error':
            # These two real caller mistakes are retained to check atomic rejection.
            assert state['message'] in ('Potion purchase was declined (check potion capacity)',
                                         'Invalid potion index 1'), state
            state = game.send({'cmd': 'get_state'})
            assert state == before
            rejected += 1
        ctx = state.get('context', {})
        assert ctx.get('act', 1) <= 3
        if state.get('decision') == 'combat_play' and ctx['act'] == 3 and ctx['room_type'] == 'Boss':
            last_boss_round = state['round']
        for field in ('hand', 'cards'):
            for card in state.get(field, []):
                if card.get('name') != 'Mad Science':
                    continue
                assert card['tinker_time'] == {'card_type': 'Skill', 'rider': 'Energized'}
                assert card['description_vars']['Energized'] is True
                assert card['description_vars']['Wisdom'] is False
                text = play.card_desc(card)
                assert 'Gain 2E.' in text and 'Block.' in text
                assert 'Draw' not in text and '???' not in text and '{' not in text
                if card.get('after_upgrade'):
                    assert card['after_upgrade']['tinker_time'] == card['tinker_time']
                saw_custom_hand |= field == 'hand'
                saw_custom_selection |= field == 'cards'
    assert last_boss_round == rounds
    assert state == expected
    assert state['decision'] == 'game_over' and state['victory'] is victory
    assert (state['context']['act'], state['context']['floor']) == (3, 15)
    assert (state['player']['hp'], state['player']['gold']) == (hp, gold)
    assert rejected == (0 if victory else 2)
    if not victory:
        assert saw_custom_hand and saw_custom_selection
        card = next(c for c in state['player']['deck'] if c['name'] == 'Mad Science')
        assert play.card_desc(card) == 'Gain 8 Block.\nGain 2E.'
        assert card['after_upgrade']['description_vars'] == card['description_vars']
    for _ in range(2):
        assert game.send({'cmd': 'get_state'}) == state
    metrics = game.send({'cmd': 'get_run_metrics'})
    assert metrics['total_floor'] == 48
    assert metrics['player_hp'] == hp
    resumed, _ = save_and_restore(game, state, tmp_path)
    assert resumed.send({'cmd': 'get_run_metrics'}) == metrics
    resumed.close()
    game.close()
    for process in (game, resumed):
        assert not any('[ERROR]' in line or 'Exception' in line or 'timeout' in line.lower()
                       for line in process.stderr_lines)
