def test_kaiser_crab_starts_and_cannot_be_skipped(game, tmp_path):
    from test_session_checkpoint import save_and_restore
    game.skip_neow(game.start(character='Necrobinder', seed='crab-start', ascension=10))
    game.set_player(hp=1000, max_hp=1000, deck=['BLIGHT_STRIKE'] * 5)
    state = game.enter_room('combat', encounter='KAISER_CRAB_BOSS')
    assert state.get('decision') == 'combat_play', (state, '\n'.join(game.stderr_lines[-50:]))
    assert state['round'] == 1
    assert len(state['enemies']) == 2
    assert all(e['hp'] > 0 and e['intents'] for e in state['enemies'])
    assert game.act('proceed')['type'] == 'error'
    assert game.send({'cmd': 'get_state'}) == state
    resumed, _ = save_and_restore(game, state, tmp_path)
    try:
        for _ in range(150):
            if state.get('decision') != 'combat_play':
                break
            card = next((c for c in state['hand'] if c['can_play']), None)
            state = resumed.act('play_card', card_index=card['index'], target_index=0) if card else resumed.act('end_turn')
            if state.get('type') == 'error':
                print(''.join(resumed.stderr_lines))
            assert state.get('type') != 'error', (state, '\n'.join(resumed.stderr_lines[-50:]))
        assert state.get('decision') == 'card_reward', state
        assert state['context']['room_type'] == 'Boss'
        assert not any('[ERROR]' in line for line in resumed.stderr_lines)
    finally:
        resumed.close()
