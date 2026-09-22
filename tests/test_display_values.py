"""Information needed to choose events, buy items, and understand temporary powers."""
import json
from pathlib import Path
import pytest


@pytest.mark.parametrize('lang,expected', [('en', 'Sharp'), ('zh', '锋利')])
def test_event_preserves_string_variables(game, lang, expected):
    game.skip_neow(game.start(seed='display-values', lang=lang, ascension=10))
    state = game.enter_room('event', event='SELF_HELP_BOOK')
    assert state['decision'] == 'event_choice'
    variables = state['options'][0]['vars']
    assert variables['Enchantment1'] == expected
    assert variables['Enchantment1Amount'] == 2
    assert all(isinstance(variables[f'Enchantment{i}'], str) for i in range(1, 4))


@pytest.mark.parametrize('lang', ['en', 'zh'])
def test_speed_potion_power_uses_its_actual_localization(game, lang):
    game.skip_neow(game.start(seed='speed-description', lang=lang, ascension=10))
    game.set_player(potions=['SPEED_POTION'])
    game.enter_room('combat', encounter='SHRINKER_BEETLE_WEAK')
    state = game.act('use_potion', potion_index=0)
    powers = state['player_powers']
    assert len(powers) == 2
    assert all(not p['name'].endswith('.title') and not p['description'].endswith('.description') for p in powers)
    assert all(p['amount'] == 5 for p in powers)
    state = game.act('end_turn')
    assert not any(p['amount'] == 5 for p in state.get('player_powers') or [])


def test_a10_shop_exposes_effect_values_before_buying(game):
    commands = json.loads((Path(__file__).parent / 'fixtures/ironclad_a10_act1_commands.json').read_text())
    for command in commands[:77]:
        state = game.send(command)
        assert state.get('type') != 'error', state
    assert state['decision'] == 'shop'
    assert [r['vars'] for r in state['relics']] == [{'Cards': 3}, {'Damage': 3}, {'Cards': 3}]
    assert state['potions'][0]['vars'] == {'DexterityPower': 2}
    assert state['potions'][1]['vars'] == {'WeakPower': 3}
    assert state['potions'][2]['vars'] == {'DexterityPower': 5}


@pytest.mark.parametrize('lang', ['en', 'zh'])
def test_fractional_power_variables_and_vulnerable_percentage(game, lang):
    game.skip_neow(game.start(seed='fractional-powers', lang=lang, ascension=10))
    game.set_player(deck=['PUTREFY'] * 5)
    game.enter_room('combat', encounter='SHRINKER_BEETLE_WEAK')
    state = game.act('play_card', card_index=0, target_index=0)
    powers = state['enemies'][0]['powers']
    vulnerable = next(p for p in powers if 'DamageIncrease' in p['vars'])
    weak = next(p for p in powers if 'DamageDecrease' in p['vars'])
    assert vulnerable['vars']['DamageIncrease'] == 1.5
    assert weak['vars']['DamageDecrease'] == 0.75
    assert '50%' in vulnerable['description']
    assert not vulnerable['description_is_template']
