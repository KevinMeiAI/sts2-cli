"""Damage previews found while continuing the Necrobinder's real Act 2."""


def test_pull_from_below_zero_hits_and_osty_damage(game):
    game.skip_neow(game.start(character='Necrobinder', seed='act2-preview', ascension=10))
    game.set_player(deck=['PULL_FROM_BELOW', 'POKE', 'ENFEEBLING_TOUCH', 'DEFILE', 'DEFEND_NECROBINDER'])
    state = game.enter_room('combat', encounter='SHRINKER_BEETLE_WEAK')
    pull = next(c for c in state['hand'] if c['name'] == 'Pull from Below')
    assert pull['stats']['calculatedhits'] == 0
    assert pull['damage_by_target'][0]['repeat'] == 0
    assert pull['damage_by_target'][0]['total_damage'] == 0
    hp = state['enemies'][0]['hp']
    state = game.act('play_card', card_index=pull['index'], target_index=0)
    assert state['enemies'][0]['hp'] == hp
    poke = next(c for c in state['hand'] if c['name'] == 'Poke')
    damage = poke['damage_by_target'][0]['total_damage']
    assert damage > 0
    state = game.act('play_card', card_index=poke['index'], target_index=0)
    assert hp - state['enemies'][0]['hp'] == damage


def test_rattle_first_attack_hit_count_matches_engine(game):
    game.skip_neow(game.start(character='Necrobinder', seed='rattle-preview', ascension=10))
    game.set_player(deck=['RATTLE'] * 5)
    state = game.enter_room('combat', encounter='SHRINKER_BEETLE_WEAK')
    for _ in range(2):
        preview = state['hand'][0]['damage_by_target'][0]
        hp = state['enemies'][0]['hp']
        state = game.act('play_card', card_index=0, target_index=0)
        assert hp - state['enemies'][0]['hp'] == preview['total_damage']


def test_spite_repeat_tracks_native_hp_loss_condition(game):
    game.skip_neow(game.start(character='Ironclad', seed='spite-preview'))
    game.set_player(deck=['SPITE', 'SPITE', 'BLOODLETTING', 'DEFEND_IRONCLAD', 'DEFEND_IRONCLAD'])
    state = game.enter_room('combat', encounter='SHRINKER_BEETLE_WEAK')
    for damaged in (False, True):
        if damaged:
            blood = next(c for c in state['hand'] if c['name'] == 'Bloodletting')
            state = game.act('play_card', card_index=blood['index'])
        card = next(c for c in state['hand'] if c['name'] == 'Spite')
        preview = card['damage_by_target'][0]
        assert preview['repeat'] == (2 if damaged else 1)
        hp = state['enemies'][0]['hp']
        state = game.act('play_card', card_index=card['index'], target_index=0)
        assert hp - state['enemies'][0]['hp'] == preview['total_damage']
