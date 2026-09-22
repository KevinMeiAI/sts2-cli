"""Regressions from the A10 event survey and manually played Silent run."""
import json
from pathlib import Path
import pytest
from test_session_checkpoint import save_and_restore


def test_dense_vegetation_rest_heals_once_then_offers_combat(game, tmp_path):
    game.skip_neow(game.start(character='Defect', seed='dense-rest', ascension=10))
    game.set_player(hp=10, max_hp=100)
    state = game.enter_room('event', event='DENSE_VEGETATION')
    option = next(o for o in state['options'] if o['title'] == 'Rest')
    state = game.act('choose_option', option_index=option['index'])
    assert state['decision'] == 'event_choice', state
    assert state['player']['hp'] == 40
    assert len(state['options']) == 1
    assert state['options'][0]['title'] == 'Fight!'
    restored, _ = save_and_restore(game, state, tmp_path)
    try:
        state = restored.act('choose_option', option_index=0)
        assert state['decision'] == 'combat_play', state
        assert state['player']['hp'] == 40
        assert state['enemies']
        combat, _ = save_and_restore(restored, state, tmp_path)
        combat.close()
    finally:
        restored.close()


def test_silent_a10_power_values_and_flight_choices(game, tmp_path):
    commands = json.loads((Path(__file__).parent / 'fixtures/silent_a10_act1_commands.json').read_text())
    seen = set()
    for command in commands:
        state = game.send(command)
        assert state.get('type') != 'error', state
        for power in state.get('player_powers') or []:
            if power['name'] == 'Shrink':
                assert power['amount'] == -1
                assert power['vars']['DamageDecrease'] == 30
                assert 'Shrinker Beetle' in power['description']
                assert '3 turns' not in power['description']
                assert not power['description_is_template']
                seen.add('shrink')
            elif power['name'] == 'Constrict':
                assert f"take {power['amount']} damage" in power['description']
                seen.add('constrict')
            elif power['name'] == 'Retain Hand':
                assert power['amount'] in (1, 2)
                expected = 'this turn' if power['amount'] == 1 else 'next 2 turns'
                assert expected in power['description']
                seen.add('retain')
        if state.get('decision') == 'map_select':
            boots = next((r for r in state['player']['relics'] if r['name'] == 'Winged Boots'), None)
            if boots and boots['vars']['Rooms'] > 0:
                full = game.get_map()
                current = next((p for row in full['rows'] for p in row if p['current']), None)
                if current:
                    next_points = [p for row in full['rows'] for p in row if p['row'] == current['row'] + 1]
                    assert {(p['row'], p['col']) for p in next_points} <= {(p['row'], p['col']) for p in state['choices']}
                    seen.add('flight')
    assert seen == {'shrink', 'constrict', 'retain', 'flight'}
    assert (state['decision'], state['floor'], state['player']['hp']) == ('game_over', 17, 0)
    restored, _ = save_and_restore(game, state, tmp_path)
    restored.close()


def test_necrobinder_a10_boss_victory_and_checkpoint(game, tmp_path):
    commands = json.loads((Path(__file__).parent / 'fixtures/necrobinder_a10_act1_commands.json').read_text())
    for step, command in enumerate(commands, 1):
        state = game.send(command)
        assert state.get('type') != 'error', (step, state)
    assert state['decision'] == 'card_reward'
    assert state['context']['room_type'] == 'Boss'
    assert (state['context']['act'], state['context']['floor']) == (1, 17)
    assert (state['player']['hp'], state['player']['gold']) == (22, 192)
    restored, _ = save_and_restore(game, state, tmp_path)
    restored.close()


def test_crystal_sphere_reports_unsupported_before_charging_or_cursing(game):
    game.skip_neow(game.start(seed='sphere-unsupported', ascension=10))
    game.set_player(gold=500)
    state = game.enter_room('event', event='CRYSTAL_SPHERE')
    assert all(o['is_supported'] is False for o in state['options'])
    for index in range(2):
        error = game.act('choose_option', option_index=index)
        assert error['code'] == 'unsupported_interaction'
        assert error['state_unchanged'] is True
        assert game.send({'cmd': 'get_state'}) == state


@pytest.mark.parametrize('branch,kind,result_name', [(0, 'Strike', 'Ultimate Strike'), (1, 'Defend', 'Ultimate Defend')])
def test_amalgamator_keeps_card_merge_after_skipping_screen_shake(game, tmp_path, branch, kind, result_name):
    game.skip_neow(game.start(character='Silent', seed='merge-regression', ascension=10))
    initial = game.enter_room('event', event='AMALGAMATOR')
    state = game.act('choose_option', option_index=branch)
    assert state['decision'] == 'card_select'
    assert state['min_select'] == 2
    state = game.act('select_cards', indices='0,1')
    assert state['decision'] == 'map_select', state
    before, after = initial['player']['deck'], state['player']['deck']
    assert len(after) == len(before) - 1
    assert sum(c['name'] == kind for c in after) == sum(c['name'] == kind for c in before) - 2
    assert sum(c['name'] == result_name for c in after) == 1
    restored, _ = save_and_restore(game, state, tmp_path)
    restored.close()


def test_punch_off_nab_preserves_curse_and_reward(game, tmp_path):
    game.skip_neow(game.start(character='Necrobinder', seed='matrix-PUNCH_OFF', ascension=10))
    initial = game.enter_room('event', event='PUNCH_OFF')
    state = game.act('choose_option', option_index=0)
    assert state['decision'] == 'map_select', state
    assert state['player']['deck_size'] == initial['player']['deck_size'] + 1
    assert state['player']['deck'][-1]['name'] == 'Injury'
    assert len(state['player']['relics']) == len(initial['player']['relics']) + 1
    restored, _ = save_and_restore(game, state, tmp_path)
    restored.close()


def test_trial_story_judgment_and_unsupported_abandon(game):
    game.skip_neow(game.start(character='Defect', seed='matrix-TRIAL', ascension=10))
    state = game.enter_room('event', event='TRIAL')
    state = game.act('choose_option', option_index=1)
    assert state['decision'] == 'event_choice'
    assert state['options'][1]['is_supported'] is False
    result = game.act('choose_option', option_index=1)
    assert result['code'] == 'unsupported_interaction'
    assert game.send({'cmd': 'get_state'}) == state
    state = game.act('choose_option', option_index=0)
    assert state['decision'] == 'event_choice', state
    assert '{TrialStory}' not in state['description']
    assert state['description_vars']['TrialStory'] in state['description']
    assert 'TRIAL.pages.' not in state['description']
    state = game.act('choose_option', option_index=0)
    assert state['decision'] == 'map_select', state


def test_flight_at_last_map_row_preserves_boss_destination(game):
    commands = json.loads((Path(__file__).parent / 'fixtures/silent_a10_act1_commands.json').read_text())
    for command in commands:
        if command.get('action') == 'select_map_node' and command.get('args', {}).get('row') == 16:
            break
        state = game.send(command)
        assert state.get('type') != 'error', state
    assert state['decision'] == 'map_select'
    original_choices = state['choices']
    game.set_player(relics=['WINGED_BOOTS'])
    state = game.send({'cmd': 'get_state'})
    assert state['decision'] == 'map_select', state
    assert state['choices'] == original_choices
    assert state['choices'][0]['type'] == 'Boss'
