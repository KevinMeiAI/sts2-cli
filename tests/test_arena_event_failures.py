"""Original official actions, replayed offline: these are not new model attempts."""
import json
from pathlib import Path
import pytest
from test_session_checkpoint import save_and_restore

FIXTURES = Path(__file__).parent / 'fixtures/arena_failures'


def test_event_inventory_comes_from_native_pools_and_does_not_change_run(game):
    before = game.skip_neow(game.start(seed='native-event-inventory'))
    metrics = game.send({'cmd': 'get_run_metrics'})
    catalog = game.send({'cmd': 'list_events'})
    assert catalog['type'] == 'event_catalog'
    ids = [e['id'] for e in catalog['events']]
    assert 'JUNGLE_MAZE_ADVENTURE' in ids
    assert len(set(ids)) == len(ids)
    assert any(e['ancient'] for e in catalog['events'])
    assert game.send({'cmd': 'get_state'}) == before
    assert game.send({'cmd': 'get_run_metrics'}) == metrics


def assert_join_forces(before, after):
    assert after['decision'] == 'map_select', after
    assert after['player']['hp'] == before['player']['hp']
    gold = before['options'][1]['vars']['JoinForcesGold']
    assert after['player']['gold'] == before['player']['gold'] + int(gold)
    assert after['player']['deck'] == before['player']['deck']
    assert after['player']['relics'] == before['player']['relics']


@pytest.mark.parametrize('path', sorted(FIXTURES.glob('*.json')), ids=lambda p: p.stem)
def test_three_official_failures_replay_to_native_reward(game, tmp_path, path):
    fixture = json.loads(path.read_text())
    for command in fixture['commands'][:-1]:
        state = game.send(command)
        # Original invalid requests are preserved; they are not technical faults.
        assert 'Exception' not in state.get('message', ''), state
    assert state['event_name'] == 'Jungle Maze Adventure'
    assert state['player']['hp'] == fixture['before']['hp']
    assert state['player']['gold'] == fixture['before']['gold']
    before = state
    state = game.send(fixture['commands'][-1])
    assert_join_forces(before, state)
    # Reading and checkpointing must not award the gold twice.
    assert game.send({'cmd': 'get_state'}) == state
    restored, _ = save_and_restore(game, state, tmp_path)
    try:
        metrics = restored.send({'cmd': 'get_run_metrics'})
        assert metrics['total_floor'] == fixture['before']['context']['floor']
    finally:
        restored.close()


@pytest.mark.parametrize('character', ['Ironclad', 'Silent', 'Defect', 'Necrobinder'])
@pytest.mark.parametrize('branch', [0, 1])
def test_jungle_maze_both_branches_all_contest_characters(game, tmp_path, character, branch):
    game.skip_neow(game.start(character=character, seed='maze-all-characters', ascension=10))
    game.set_player(hp=60, gold=100)
    before = game.enter_room('event', event='JUNGLE_MAZE_ADVENTURE')
    state = game.act('choose_option', option_index=branch)
    assert state['decision'] == 'map_select', state
    if branch == 1:
        assert_join_forces(before, state)
    else:
        values = before['options'][0]['vars']
        assert state['player']['hp'] == before['player']['hp'] - values['SoloHp']
        assert state['player']['gold'] == before['player']['gold'] + int(values['SoloGold'])
    restored, _ = save_and_restore(game, state, tmp_path)
    restored.close()
