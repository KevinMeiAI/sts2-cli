"""Offline A10 event coverage from native pools; no model calls or official scores.

Each character/event/entry option has an independent process. Follow-up choices
use a deterministic policy; combat handoffs are recorded rather than auto-won.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arena.common import CHARACTERS, atomic_json, engine_fingerprints, utc
from arena.engine import Engine


def act(game, action, **args):
    return game.send({'cmd': 'action', 'action': action, 'args': args})


def resolve(game, state):
    visits = Counter()
    for _ in range(60):
        if state.get('type') == 'error':
            return state
        decision = state.get('decision')
        if decision in ('map_select', 'game_over', 'combat_play', 'shop', 'rest_site'):
            return state
        if decision == 'card_select':
            if state['min_select'] == 0:
                state = act(game, 'skip_select')
            else:
                state = act(game, 'select_cards', indices=','.join(map(str, range(state['min_select']))))
        elif decision == 'card_reward':
            state = act(game, 'select_card_reward', card_index=0)
        elif decision == 'bundle_select':
            state = act(game, 'select_bundle', bundle_index=0)
        elif decision == 'crystal_sphere':
            cell = next(c for row in state['grid'] for c in row if c['hidden'])
            state = act(game, 'crystal_sphere_reveal', x=cell['x'], y=cell['y'], tool='big')
        elif decision == 'event_choice':
            options = [o for o in state['options'] if not o.get('is_locked') and o.get('is_supported', True)]
            if not options:
                raise RuntimeError('No supported follow-up choices')
            signature = tuple(o.get('text_key', o['title']) for o in options)
            visits[signature] += 1
            option = options[0] if visits[signature] == 1 else options[-1]
            state = act(game, 'choose_option', option_index=option['index'])
        else:
            raise RuntimeError('Unhandled decision: ' + str(decision))
    raise RuntimeError('Follow-up sequence exceeded 60 actions')


class Probe:
    def __init__(self, game_root, directory, label):
        self.game = Engine(game_root, directory / (label + '.engine.log'), timeout=30)
        self.trace = []

    def send(self, command):
        response = self.game.send(command)
        self.trace.append({'request': command, 'response': response})
        return response

    def close(self):
        self.game.close()


def prepare(probe, character, event):
    state = probe.send({'cmd': 'start_run', 'character': character,
                        'seed': 'coverage-' + event['id'], 'ascension': 10, 'lang': 'en'})
    state = resolve(probe, state)
    if state.get('decision') != 'map_select':
        raise RuntimeError('Initial ancient did not resolve: ' + str(state))
    probe.send({'cmd': 'set_player', 'hp': 60, 'max_hp': 100, 'gold': 500})
    return probe.send({'cmd': 'enter_room', 'type': 'event', 'event': event['id']})


def sweep_one(job):
    character, event, game_root, directory = job
    branches, results = [None], []
    for branch in branches:
        label = character + '-' + event['id'] + ('-entry' if branch is None else '-' + str(branch))
        result = {'character': character, 'event': event['id'], 'ancient': event['ancient'],
                  'branch': branch, 'ascension': 10, 'synthetic': True}
        probe = None
        try:
            probe = Probe(game_root, directory, label)
            before = prepare(probe, character, event)
            if before.get('type') == 'error':
                result.update(status='entry_error', error=before)
            elif branch is None:
                branches.extend(o['index'] for o in before.get('options', []) if not o.get('is_locked'))
                result.update(status='entry_ok', options=before.get('options', []), decision=before.get('decision'))
            else:
                option = next(o for o in before['options'] if o['index'] == branch)
                result['option'] = option
                state = act(probe, 'choose_option', option_index=branch)
                if state.get('code') == 'unsupported_interaction':
                    assert probe.send({'cmd': 'get_state'}) == before, 'Unsupported option mutated state'
                    result.update(status='unsupported', message=state['message'])
                else:
                    state = resolve(probe, state)
                    result.update(status='error' if state.get('type') == 'error' else 'ok', decision=state.get('decision'))
                    if state.get('type') == 'error':
                        result['error'] = state
                    else:
                        # Restore every successful entry branch, including combat handoffs.
                        path = directory / (label + '.save')
                        saved = probe.send({'cmd': 'write_continue_save', 'path': str(path)})
                        assert saved.get('success'), saved
                        metrics = probe.send({'cmd': 'get_run_metrics'})
                        restored = Engine(game_root, directory / (label + '.restore.log'), timeout=60)
                        try:
                            actual = restored.send({'cmd': 'load_save', 'path': str(path), 'lang': 'en'})
                            assert actual == state, {'restore_error': actual.get('message'), 'decision': actual.get('decision')}
                            assert restored.send({'cmd': 'get_run_metrics'}) == metrics, 'Native metrics changed after restore'
                            assert not restored.faults, restored.faults
                            result['checkpoint_exact'] = True
                        finally:
                            restored.close()
                if probe.game.faults:
                    result.update(status='engine_fault', faults=probe.game.faults)
        except Exception as error:
            result.update(status='exception', error=f'{type(error).__name__}: {error}')
        finally:
            if probe:
                atomic_json(directory / (label + '.trace.json'), probe.trace)
                probe.close()
        atomic_json(directory / (label + '.result.json'), result)
        results.append(result)
        if result['status'] not in ('entry_ok', 'ok'):
            print(json.dumps(result, ensure_ascii=False), flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--events', nargs='*')
    parser.add_argument('--characters', nargs='+', default=list(CHARACTERS))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    game = Engine(args.game_root, args.output / 'catalog.engine.log')
    try:
        catalog = game.send({'cmd': 'list_events'})
        assert catalog['type'] == 'event_catalog', catalog
    finally:
        game.close()
    atomic_json(args.output / 'catalog.json', catalog)
    events = [e for e in catalog['events'] if not args.events or e['id'] in args.events]
    plan = {'started_at': utc(), 'characters': args.characters, 'events': events,
            'engine_files': engine_fingerprints(args.game_root), 'workers': args.workers,
            'scope': 'Every unlocked initial option; deterministic follow-ups; stop on combat handoff; exact checkpoint restore per successful branch; synthetic A10'}
    atomic_json(args.output / 'plan.json', plan)
    jobs = [(c, e, args.game_root, args.output) for c in args.characters for e in events]
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for rows in pool.map(sweep_one, jobs):
            results.extend(rows)
            atomic_json(args.output / 'progress.json', {'at': utc(), 'counts': dict(Counter(r['status'] for r in results)), 'rows': len(results)})
    summary = {'ended_at': utc(), 'counts': dict(Counter(r['status'] for r in results)),
               'events': len(events), 'characters': args.characters,
               'checkpoint_restores': sum(r.get('checkpoint_exact', False) for r in results), 'results': results}
    atomic_json(args.output / 'summary.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k != 'results'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
