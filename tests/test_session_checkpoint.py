"""Real engine regression coverage for purchases and exact pending-decision checkpoints."""
import json
from pathlib import Path

from conftest import Game


def save_and_restore(game, state, tmp_path):
    path = tmp_path / 'checkpoint.save'
    saved = game.send({'cmd': 'write_continue_save', 'path': str(path)})
    assert saved.get('success') is True, saved
    assert saved['format'] == 'sts2-cli-checkpoint'
    game.close()
    restored = Game()
    actual = restored.send({'cmd': 'load_save', 'path': str(path)})
    assert actual == state
    return restored, path


def test_recorded_first_act_purchases_and_boss_reward_checkpoint(tmp_path):
    commands = json.loads((Path(__file__).parent / 'fixtures/ironclad_act1_commands.json').read_text())
    game = Game()
    try:
        for step, command in enumerate(commands, 1):
            before = state if step > 1 else None
            state = game.send(command)
            assert state.get('type') != 'error', (step, state)
            if step == 107:
                assert state['decision'] == 'shop'
                assert state['player']['gold'] == 135
                assert any(r['name'] == 'Membership Card' for r in state['player']['relics'])
                assert state['relics'][2] == {'index': 2, 'is_stocked': False}
                assert state['card_removal_cost'] == 37
                retry = game.act('buy_relic', relic_index=2)
                assert retry['type'] == 'error'
                assert game.send({'cmd': 'get_state'}) == state
            if step == 111:
                assert state['player']['gold'] == 57
                assert state['player']['potions'][0]['name'] == 'Power Potion'
                assert state['potions'][1] == {'index': 1, 'is_stocked': False}
                retry = game.act('buy_potion', potion_index=1)
                assert retry['type'] == 'error'
                assert game.send({'cmd': 'get_state'}) == state
            if step == 176:
                card = before['hand'][command['args']['card_index']]
                assert card['name'] == 'Twin Strike'
                damage = card['damage_by_target'][0]
                assert damage['repeat'] == 2
                assert damage['total_damage'] == 44
                assert before['enemies'][0]['hp'] - state['enemies'][0]['hp'] == damage['total_damage']
        assert state['decision'] == 'card_reward'
        assert state['context']['room_type'] == 'Boss'
        assert (state['context']['floor'], state['player']['hp'], state['player']['gold']) == (17, 58, 177)
        assert not any('Buy potion failed' in line or 'Unobserved task exception' in line for line in game.stderr_lines)
        restored, _ = save_and_restore(game, state, tmp_path)
        try:
            state = restored.act('select_card_reward', card_index=1)
            assert state.get('type') != 'error', state
            assert any(c['name'] == 'Pyre' for c in state['player']['deck'])
        finally:
            restored.close()
    finally:
        game.close()


def test_combat_checkpoint_restores_exact_turn_and_hand(tmp_path):
    game = Game()
    try:
        game.skip_neow(game.start(seed='checkpoint-combat'))
        state = game.enter_room('combat', encounter='SHRINKER_BEETLE_WEAK')
        state = game.act('end_turn')
        assert state['round'] == 2
        restored, _ = save_and_restore(game, state, tmp_path)
        try:
            result = restored.act('end_turn')
            assert result['decision'] == 'combat_play'
            assert result['round'] == 3
        finally:
            restored.close()
    finally:
        game.close()


def test_pending_card_selection_checkpoint(tmp_path):
    game = Game()
    try:
        game.skip_neow(game.start(seed='checkpoint-selection'))
        game.set_player(deck=['THINKING_AHEAD'] * 2 + ['STRIKE_IRONCLAD'] * 4)
        state = game.enter_room('combat', encounter='SHRINKER_BEETLE_WEAK')
        card = next(c for c in state['hand'] if c['name'] == 'Thinking Ahead')
        state = game.act('play_card', card_index=card['index'])
        assert state['decision'] == 'card_select'
        restored, _ = save_and_restore(game, state, tmp_path)
        try:
            result = restored.act('select_cards', indices='0')
            assert result['decision'] == 'combat_play', result
        finally:
            restored.close()
    finally:
        game.close()


def test_random_seed_is_persisted_and_engine_mismatch_is_rejected(tmp_path):
    game = Game()
    try:
        state = game.start(seed=None)
        restored, path = save_and_restore(game, state, tmp_path)
        try:
            data = json.loads(path.read_text())
            assert data['commands'][0]['seed']
            data['engine_sha256'] = 'wrong-engine'
            result = restored.send({'cmd': 'load_save', 'json': json.dumps(data)})
            assert result['type'] == 'error'
            assert restored.send({'cmd': 'get_state'}) == state
        finally:
            restored.close()
    finally:
        game.close()


def test_failed_quit_save_keeps_run_alive(game, tmp_path):
    state = game.start(seed='save-failure')
    result = game.send({'cmd': 'quit', 'path': str(tmp_path)})
    assert result['type'] == 'save_error'
    assert game.send({'cmd': 'get_state'}) == state


def test_replay_divergence_is_reported(tmp_path):
    game = Game()
    try:
        state = game.start(seed='checkpoint-tamper')
        path = tmp_path / 'checkpoint.save'
        assert game.send({'cmd': 'write_continue_save', 'path': str(path)})['success']
        data = json.loads(path.read_text())
        data['expected_state']['player']['hp'] -= 1
        result = game.send({'cmd': 'load_save', 'json': json.dumps(data)})
        assert result['type'] == 'error'
        assert 'diverged' in result['message']
    finally:
        game.close()
