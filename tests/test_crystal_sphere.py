"""The native Crystal Sphere minigame, without a Godot screen."""
import pytest
from test_session_checkpoint import save_and_restore


@pytest.mark.parametrize('branch,count', [(0, 3), (1, 6)])
def test_crystal_grid_payment_fog_actions_and_checkpoint(game, tmp_path, branch, count):
    game.skip_neow(game.start(seed='sphere-grid', ascension=10))
    game.set_player(gold=500)
    initial = game.enter_room('event', event='CRYSTAL_SPHERE')
    assert all(o['is_supported'] for o in initial['options'])
    state = game.act('choose_option', option_index=branch)
    assert state.get('decision') == 'crystal_sphere', state
    assert state['divinations_remaining'] == count
    if branch == 0:
        cost = initial['options'][0]['vars']['UncoverFutureCost']
        assert state['player']['gold'] == 500 - cost
        assert state['player']['deck_size'] == initial['player']['deck_size']
    else:
        assert state['player']['gold'] == 500
        assert state['player']['deck_size'] == initial['player']['deck_size'] + 1
        assert any(c['name'] == 'Debt' for c in state['player']['deck'])
    assert (state['width'], state['height']) == (11, 11)
    for row in state['grid']:
        for cell in row:
            if cell['hidden']:
                assert set(cell) == {'x', 'y', 'hidden'}
    for args in ({'x': -1, 'y': 0}, {'x': 11, 'y': 0}, {'x': 5, 'y': 5, 'tool': 'bad'}):
        assert game.act('crystal_sphere_reveal', **args)['type'] == 'error'
        assert game.send({'cmd': 'get_state'}) == state
    assert game.act('leave_room')['type'] == 'error'
    assert game.send({'cmd': 'get_state'}) == state
    state = game.act('crystal_sphere_reveal', x=5, y=5, tool='small')
    assert state['decision'] == 'crystal_sphere', state
    assert not state['grid'][5][5]['hidden']
    assert game.act('crystal_sphere_reveal', x=5, y=5)['type'] == 'error'
    assert game.send({'cmd': 'get_state'}) == state
    resumed, _ = save_and_restore(game, state, tmp_path)
    try:
        for _ in range(30):
            if state.get('decision') == 'crystal_sphere':
                hidden = [c for row in state['grid'] for c in row if c['hidden']]
                # Coverage driver: use only exported fog, never hidden item locations.
                def area(c):
                    return sum(abs(c['x']-t['x']) <= 1 and abs(c['y']-t['y']) <= 1 for t in hidden)
                cell = max(hidden, key=area)
                state = resumed.act('crystal_sphere_reveal', x=cell['x'], y=cell['y'], tool='big')
            elif state.get('decision') == 'card_reward':
                state = resumed.act('skip_card_reward')
            else:
                break
            assert state.get('type') != 'error', state
        assert state.get('decision') == 'map_select', state
        final, _ = save_and_restore(resumed, state, tmp_path)
        final.close()
    finally:
        resumed.close()
