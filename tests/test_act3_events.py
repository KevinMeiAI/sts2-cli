import json
from pathlib import Path
import pytest
from test_session_checkpoint import save_and_restore


def test_actual_ironclad_event_chain_and_dummy_rewards(game, tmp_path):
    commands = json.loads((Path(__file__).parent / 'fixtures/ironclad_act3_commands.json').read_text())
    saw_key = saw_history_selection = saw_upgraded_title = False
    for command in commands:
        try:
            state = game.send(command)
        except RuntimeError:
            game.close()
            pytest.fail(f"Command {command}:\n" + ''.join(game.stderr_lines[-100:]))
        assert state.get('type') != 'error', state
        context = state.get('context', {})
        if context.get('act') != 3:
            continue
        if state.get('event_name') == 'War Historian, Repy':
            saw_key = any(c['name'] == 'Lantern Key' for c in state['player']['deck'])
        if context.get('floor') == 10 and state.get('decision') == 'card_select' and state['player']['block'] == 30:
            saw_history_selection = True
        if state.get('event_name') == 'Slippery Bridge':
            name = state['options'][0]['vars']['RandomCard']
            assert '.title' not in name
            if name.endswith('+'):
                saw_upgraded_title = True
        if context.get('floor') == 13 and state.get('decision') == 'map_select':
            break
    assert saw_key and saw_history_selection and saw_upgraded_title
    assert state['decision'] == 'map_select'
    assert state['player']['gold'] == 98  # No ordinary combat gold/card/potion reward.
    assert state['player']['deck_size'] == 35
    assert len(state['player']['potions']) == 3  # The selected event reward only.
    assert not any(c['name'] == 'Lantern Key' for c in state['player']['deck'])
    assert any(r['name'] == 'History Course' for r in state['player']['relics'])
    restored, _ = save_and_restore(game, state, tmp_path)
    restored.close()
    game.close()
    assert not any('[ERROR]' in line or 'Exception' in line for line in game.stderr_lines)


@pytest.mark.parametrize('setting', [0, 1, 2])
def test_dummy_native_setting_rewards_without_extra_combat_loot(game, tmp_path, setting):
    game.skip_neow(game.start(character='Silent', seed=f'dummy-setting-{setting}'))
    game.set_player(hp=500, max_hp=500, gold=123, deck=['GRAND_FINALE'] * 5, relics=[], potions=[])
    game.enter_room('event', event='BATTLEWORN_DUMMY')
    state = game.act('choose_option', option_index=setting)
    for _ in range(30):
        if state.get('decision') != 'combat_play':
            break
        playable = next((c for c in state['hand'] if c['can_play']), None)
        state = game.act('play_card', card_index=playable['index']) if playable else game.act('end_turn')
        assert state.get('type') != 'error', state
    assert state['decision'] == 'map_select', state
    player = state['player']
    assert player['gold'] == 123 and player['deck_size'] == 5
    assert len(player['potions']) == (1 if setting == 0 else 0)
    if setting != 2:  # The random relic may itself upgrade cards (e.g. Whetstone).
        assert sum(c['upgraded'] for c in player['deck']) == (2 if setting == 1 else 0)
    assert len(player['relics']) == (1 if setting == 2 else 0)
    for _ in range(2):
        assert game.send({'cmd': 'get_state'}) == state
    restored, _ = save_and_restore(game, state, tmp_path)
    restored.close()


def test_dummy_timeout_does_not_grant_victory_rewards(game):
    game.skip_neow(game.start(seed='dummy-timeout'))
    game.set_player(hp=500, max_hp=500, gold=123, deck=['DEFEND_IRONCLAD'] * 5, relics=[], potions=[])
    game.enter_room('event', event='BATTLEWORN_DUMMY')
    state = game.act('choose_option', option_index=2)
    for _ in range(5):
        if state.get('decision') != 'combat_play':
            break
        state = game.act('end_turn')
        assert state.get('type') != 'error', state
    assert state['decision'] == 'map_select', state
    assert state['player']['gold'] == 123
    assert state['player']['relics'] == [] and state['player']['potions'] == []
    assert state['player']['deck_size'] == 5


@pytest.mark.parametrize('lang', ['en', 'zh'])
def test_tinker_violence_preview_matches_native_hits(game, tmp_path, monkeypatch, lang):
    from test_play import play
    monkeypatch.setattr(play, 'LANG', lang)
    game.skip_neow(game.start(seed='tinker-0', lang=lang))
    game.set_player(hp=500, max_hp=500, deck=['DEFEND_IRONCLAD'] * 4, relics=[], potions=[])
    game.enter_room('event', event='TINKER_TIME')
    types = game.act('choose_option', option_index=0)
    attack = next(o['index'] for o in types['options'] if o['text_key'].endswith('.ATTACK'))
    riders = game.act('choose_option', option_index=attack)
    violence = next(o['index'] for o in riders['options'] if o['text_key'].endswith('.VIOLENCE'))
    state = game.act('choose_option', option_index=violence)
    card = next(c for c in state['player']['deck'] if c['id'] == 'CARD.MAD_SCIENCE')
    assert card['tinker_time'] == {'card_type': 'Attack', 'rider': 'Violence'}
    assert card['after_upgrade']['tinker_time'] == card['tinker_time']
    assert card['after_upgrade']['added_keywords'] == ['Innate']
    text = play.card_desc(card)
    assert '???' not in text and '{' not in text
    assert '12' in text and '3' in text
    if lang == 'en':
        assert text == 'Deal 12 damage 3 times.'
    state = game.enter_room('combat', encounter='SHRINKER_BEETLE_WEAK')
    card = next(c for c in state['hand'] if c['id'] == 'CARD.MAD_SCIENCE')
    preview = card['damage_by_target'][0]
    assert (preview['damage'], preview['repeat'], preview['total_damage']) == (12, 3, 36)
    hp = state['enemies'][0]['hp']
    assert hp > 36
    state = game.act('play_card', card_index=card['index'], target_index=0)
    assert hp - state['enemies'][0]['hp'] == 36
    restored, _ = save_and_restore(game, state, tmp_path)
    restored.close()
