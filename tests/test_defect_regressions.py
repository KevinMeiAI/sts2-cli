"""Native Defect mechanics and the information needed to operate them."""
import json
from pathlib import Path

import pytest
from conftest import Game
from test_play import play
from test_session_checkpoint import save_and_restore


def prepare(game, deck, lang='en'):
    game.skip_neow(game.start(character='Defect', seed='defect-metadata', ascension=10, lang=lang))
    game.set_player(deck=deck, hp=200, max_hp=200, potions=[])
    state = game.enter_room('combat', encounter='SHRINKER_BEETLE_WEAK')
    assert state.get('decision') == 'combat_play', state
    return state


def card(state, entry):
    return next(c for c in state['hand'] if c['id'] == 'CARD.' + entry)


def test_empty_queue_retains_capacity_and_restores(game, tmp_path):
    state = prepare(game, ['DUALCAST'] + ['DEFEND_DEFECT'] * 4)
    state = game.act('play_card', card_index=card(state, 'DUALCAST')['index'])
    assert state['orbs'] == [] and state['orb_slots'] == 3
    restored, _ = save_and_restore(game, state, tmp_path)
    restored.close()


def test_bulk_up_can_report_zero_slots(game):
    state = prepare(game, ['BULK_UP'] * 5)
    for capacity in (2, 1, 0):
        state = game.act('play_card', card_index=0)
        assert state['orb_slots'] == capacity
        if capacity:
            state = game.act('end_turn')
    assert state['orbs'] == []


@pytest.mark.parametrize('lang', ['en', 'zh'])
def test_orb_descriptions_track_live_focus_and_dark_glass_values(game, lang):
    state = prepare(game, ['NULL', 'HOTFIX', 'GLASSWORK', 'DEFEND_DEFECT', 'DEFEND_DEFECT'], lang)
    state = game.act('play_card', card_index=card(state, 'NULL')['index'], target_index=0)
    state = game.act('play_card', card_index=card(state, 'HOTFIX')['index'])
    state = game.act('play_card', card_index=card(state, 'GLASSWORK')['index'])
    assert [(o['type'], o['passive'], o['evoke']) for o in state['orbs']] == [
        ('Lightning', 5, 10), ('Dark', 8, 6), ('Glass', 6, 12)]
    for orb in state['orbs']:
        assert not orb['description_is_template'] and '{' not in orb['description']
        assert str(orb['passive']) in orb['description'] and str(orb['evoke']) in orb['description']
    state = game.act('end_turn')
    assert [(o['type'], o['passive'], o['evoke']) for o in state['orbs']] == [
        ('Lightning', 3, 8), ('Dark', 6, 14), ('Glass', 3, 6)]


def test_tempest_x_spends_remaining_energy_not_zero(game):
    state = prepare(game, ['TEMPEST'] * 2 + ['DEFEND_DEFECT'] * 3)
    tempest = card(state, 'TEMPEST')
    assert tempest['costs_x'] is True and tempest['cost'] == 0
    deck_card = next(c for c in state['player']['deck'] if c['id'] == 'CARD.TEMPEST')
    assert deck_card['costs_x'] and deck_card['after_upgrade']['costs_x']
    assert deck_card['after_upgrade']['upgraded'] is True
    for _ in range(2):
        state = game.act('play_card', card_index=card(state, 'DEFEND_DEFECT')['index'])
    assert state['energy'] == 1
    state = game.act('play_card', card_index=card(state, 'TEMPEST')['index'])
    assert state['energy'] == 0 and len(state['orbs']) == 2
    # Native X=0 is legal but does not add an orb.
    state = game.act('play_card', card_index=card(state, 'TEMPEST')['index'])
    assert state['energy'] == 0 and len(state['orbs']) == 2


def test_uproar_two_hit_preview_matches_native_attack_without_followup(game):
    state = prepare(game, ['UPROAR'] + ['DEFEND_DEFECT'] * 4)
    attack = card(state, 'UPROAR')
    preview = attack['damage_by_target'][0]
    assert (preview['repeat'], preview['total_damage']) == (2, 12)
    hp = state['enemies'][0]['hp']
    state = game.act('play_card', card_index=attack['index'], target_index=0)
    assert hp - state['enemies'][0]['hp'] == 12


def test_terminal_shows_empty_slots_x_cost_and_upgraded_description(monkeypatch, capsys):
    monkeypatch.setattr(play, 'LANG', 'en')
    play.show_combat({'orbs': [], 'orb_slots': 3})
    assert 'Orbs [0/3]' in capsys.readouterr().out
    tempest = {'index': 0, 'name': 'Tempest', 'cost': 0, 'costs_x': True, 'upgraded': True,
               'description': 'Channel {IfUpgraded:show:X+1|X} Lightning.'}
    assert play.card_desc(tempest) == 'Channel X+1 Lightning.'
    play.show_card_reward({'cards': [tempest]})
    output = capsys.readouterr().out
    assert 'Tempest+' in output and '(X)' in output
    assert play.card_desc({**tempest, 'upgraded': False}) == 'Channel X Lightning.'
    assert play.card_desc({'description': 'Base.{IfUpgraded:show: Extra.}', 'upgraded': False}) == 'Base.'
    # Shop gold must not be mistaken for energy in the upgrade preview.
    play.show_shop({'cards': [{**tempest, 'is_stocked': True, 'cost': 51, 'card_cost': 0,
                              'after_upgrade': {'cost': 0, 'costs_x': True}}]})
    output = capsys.readouterr().out
    assert '(X)' in output and '51' in output and '51→' not in output


def test_debug_injected_cracked_core_has_owner_and_channels_normally(game):
    game.skip_neow(game.start(character='Defect', seed='defect-injected-core', ascension=10))
    game.set_player(relics=['CRACKED_CORE'], deck=['DEFEND_DEFECT'] * 5)
    state = game.enter_room('combat', encounter='SHRINKER_BEETLE_WEAK')
    assert state.get('decision') == 'combat_play', state
    assert state['orb_slots'] == 3 and len(state['orbs']) == 1
    assert state['orbs'][0]['type'] == 'Lightning'


def test_x_cost_shop_selection_and_upgrade_views(game):
    game.skip_neow(game.start(character='Defect', seed='defect-x-shop-0', ascension=10))
    # Deterministic inventory sequence found in an isolated synthetic test.
    for _ in range(18):
        state = game.enter_room('shop')
    tempest = next(c for c in state['cards'] if c['name'] == 'Tempest')
    assert tempest['costs_x'] and tempest['card_cost'] == 0 and tempest['cost'] == 77
    assert tempest['after_upgrade']['costs_x'] and tempest['after_upgrade']['upgraded']
    game.set_player(deck=['TEMPEST', 'DEFEND_DEFECT'])
    game.enter_room('rest')
    state = game.act('choose_option', option_index=1)
    assert state['decision'] == 'card_select'
    choice = next(c for c in state['cards'] if c['id'] == 'CARD.TEMPEST')
    assert choice['costs_x'] and choice['upgraded'] is False
    state = game.act('select_cards', indices=str(choice['index']))
    upgraded = next(c for c in state['player']['deck'] if c['id'] == 'CARD.TEMPEST')
    assert upgraded['costs_x'] and upgraded['upgraded']
    assert play.card_desc(upgraded) == 'Channel X+1 Lightning.'
