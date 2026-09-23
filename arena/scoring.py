"""Scores come exclusively from judge-owned native state, never model text."""
from __future__ import annotations
from fractions import Fraction


def score(state, metrics):
    result = {'total_floor': metrics['total_floor'], 'act': metrics['act'],
              'act_floor': metrics['act_floor'], 'round': metrics.get('round'),
              'player_hp': metrics['player_hp'], 'player_max_hp': metrics['player_max_hp'],
              'enemy_hp': metrics['enemy_hp'], 'enemy_max_hp': metrics['enemy_max_hp'],
              'enemies': metrics['enemies'], 'terminal': state.get('decision') == 'game_over',
              'victory': state.get('victory') if state.get('decision') == 'game_over' else None}
    if not result['terminal']:
        result.update(status='unfinished', hp_ratio=None)
    elif result['victory']:
        result.update(status='victory', hp_ratio=metrics['player_hp'] / metrics['player_max_hp'])
    elif metrics['enemy_hp_available'] and metrics['enemy_max_hp'] > 0:
        result.update(status='defeat', hp_ratio=metrics['enemy_hp'] / metrics['enemy_max_hp'])
    else:
        result.update(status='defeat', hp_ratio=None, tie_note='No enemy HP exists for this death; leave HP tie unresolved')
    return result


def tie_fraction(result):
    if result['hp_ratio'] is None:
        return None
    if result['victory']:
        return Fraction(result['player_hp'], result['player_max_hp'])
    return 1 - Fraction(result['enemy_hp'], result['enemy_max_hp'])


def case_comparison(a, b):
    """1 if a wins, -1 if b wins, 0 for ties including unavailable HP."""
    for key in ('total_floor', 'victory'):
        if a[key] != b[key]:
            return 1 if a[key] > b[key] else -1
    x, y = tie_fraction(a), tie_fraction(b)
    if x is None or y is None:
        return 0
    return (x > y) - (x < y)


def standings(records, case_ids):
    from functools import cmp_to_key
    valid = [r for r in records if r.get('mode') == 'official' and r.get('status') == 'completed'
             and r.get('score', {}).get('terminal')]
    per_case = {}
    for case in case_ids:
        rows = [r for r in valid if r['case_id'] == case]
        # If any HP tie cannot be resolved, do not invent an HP ordering.
        unresolved = {(r['score']['total_floor'], r['score']['victory'])
                      for r in rows if tie_fraction(r['score']) is None}
        def compare(a, b):
            sa, sb = a['score'], b['score']
            if (sa['total_floor'], sa['victory']) in unresolved and (sa['total_floor'], sa['victory']) == (sb['total_floor'], sb['victory']):
                return 0
            return -case_comparison(sa, sb)
        rows.sort(key=cmp_to_key(compare))
        last = None
        for i, row in enumerate(rows):
            row = dict(row)
            rank = i + 1 if last is None or compare(last, row) else last['rank']
            row['rank'] = rank
            rows[i] = row
            last = row
        per_case[case] = rows
    overall = []
    for model in sorted({r['model_id'] for r in valid}):
        rows = [r for r in valid if r['model_id'] == model]
        if {r['case_id'] for r in rows} != set(case_ids) or len(rows) != len(case_ids):
            continue
        ties = [tie_fraction(r['score']) for r in rows]
        overall.append({'model_id': model, 'total_floor': sum(r['score']['total_floor'] for r in rows),
                        'wins': sum(bool(r['score']['victory']) for r in rows),
                        'hp_score': float(sum(ties)) if all(t is not None for t in ties) else None})
    overall.sort(key=lambda r: (-r['total_floor'], -r['wins']))
    # Compare HP only within otherwise tied groups, with complete HP evidence.
    import itertools
    ordered = []
    for _, group in itertools.groupby(overall, key=lambda r: (r['total_floor'], r['wins'])):
        group = list(group)
        if all(r['hp_score'] is not None for r in group):
            group.sort(key=lambda r: -r['hp_score'])
        for r in group:
            r['hp_tie_resolved'] = all(x['hp_score'] is not None for x in group)
        ordered.extend(group)
    return {'per_case': per_case, 'overall': ordered,
            'excluded_or_incomplete': [r for r in records if r not in valid]}
