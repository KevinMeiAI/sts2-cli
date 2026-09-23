"""python -m arena --help. All provider secrets enter through stdin."""
from __future__ import annotations
import argparse
import json
import secrets
import shutil
import string
import sys
from pathlib import Path
from .common import CHARACTERS, atomic_json, digest, engine_fingerprints, harness_fingerprints, load_exam, load_json, utc
from .providers import public_config, read_config, register, safe_id
from .runner import claude_version, run
from .scoring import standings


def initialize(directory, game_root, executable):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    used = set()
    def seed():
        while True:
            value = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(10))
            if value not in used:
                used.add(value)
                return value
    exam = {'schema': 1, 'id': safe_id(directory.name), 'created_at': utc(), 'ascension': 10,
            'engine_files': engine_fingerprints(game_root), 'harness_files': harness_fingerprints(),
            'claude_version': claude_version(executable),
            'cases': [{'id': c.lower(), 'character': c, 'seed': seed()} for c in CHARACTERS],
            'pilot': {'id': 'practice', 'character': 'Ironclad', 'seed': seed()},
            'rules': {'floor': 'native cumulative TotalFloor, including the entered fatal floor',
                'case_order': ['total_floor DESC', 'victory DESC', 'player HP ratio DESC for wins; enemy HP ratio ASC for defeats'],
                'enemy_roster': 'All distinct creatures present/spawned in final encounter, including slain enemies at 0 HP',
                'overall_order': ['sum total_floor DESC', 'number of victories DESC', 'sum(win player ratio or loss 1-enemy ratio) DESC'],
                'eligibility': 'Only completed official games; overall requires all four. Unavailable enemy HP leaves the HP tie unresolved.',
                'one_attempt': True}}
    path = directory / 'exam.json'
    atomic_json(path, exam)
    path.with_suffix('.sha256').write_text(digest(path) + '\n')
    atomic_json(directory / 'policy.json', {'pilot_seconds': 600, 'official_seconds': None})
    return exam


def report(manifest):
    manifest = Path(manifest)
    exam = load_exam(manifest)
    records = [load_json(p) for p in sorted(manifest.parent.glob('runs/*/*/*/result.json'))]
    result = standings(records, [c['id'] for c in exam['cases']])
    atomic_json(manifest.parent / 'leaderboard.json', result)
    lines = ['# Slay the Spire 2 · A10 模型考场', '',
             '同一组四个种子；所有参赛模型均在 Claude Code 内通过专用 MCP 操作。', '',
             '| 角色 | 固定种子 |', '|---|---|']
    lines.extend(f"| {c['character']} | `{c['seed']}` |" for c in exam['cases'])
    policy = load_json(manifest.parent / 'policy.json')
    lines.extend(['', f"连通性试跑：每模型 {policy['pilot_seconds']} 秒，共用独立 Ironclad 练习种子。",
                  f"正式单局上限：{'不限时' if policy.get('official_unlimited') else (str(policy['official_seconds']) + ' 秒' if policy['official_seconds'] else '待试跑后决定')}。", '',
                  '每角色先比累计楼层，同层先分胜败；胜者比自身剩余生命比例（高优），败者比敌方剩余生命比例（低优）。',
                  '敌方百分比包含该战斗内已击杀与召唤的敌人。非战斗死亡无敌人血量时保留并列。',
                  '总榜需要四局均自然结束，依次比较累计楼层之和、通关数、血量得分之和（胜局自身比例，败局 1−敌方比例）。',
                  '超时、接口错误、主动提前停止和引擎故障单独记录，不算死亡，不混入正式成绩。', '', '## 运行记录', ''])
    if not records:
        lines.append('尚无已结束的模型成绩；进行中的比赛见 progress.json。')
    else:
        lines.extend(['| 模型 | 模式 | 角色/题目 | 状态 | 累计层数 | HP 比例 |', '|---|---|---|---|---|---|'])
        for r in records:
            s = r.get('score') or {}
            hp = s.get('hp_ratio')
            lines.append(f"| {r['model_id']} | {r['mode']} | {r['case_id']} | {r['status']} | {s.get('total_floor', '—')} | {format(hp, '.2%') if hp is not None else '—'} |")
    lines.extend(['', '## 总榜', ''])
    if not result['overall']:
        lines.append('尚无完成全部四个正式题目的模型。')
    for row in result['overall']:
        lines.append(f"- {row['model_id']}：总楼层 {row['total_floor']}，通关 {row['wins']}，血量得分 {row['hp_score']}")
    (manifest.parent / 'README.md').write_text('\n'.join(lines) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exam', type=Path, default=Path('arena-exam/exam.json'))
    parser.add_argument('--game-root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--private-dir', type=Path, default=Path('.arena-private'))
    parser.add_argument('--claude', default=shutil.which('claude'))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init', help='Roll/freeze four exams and one separate practice seed exactly once')
    reg = sub.add_parser('register', help='Read a provider oneliner from stdin; never execute it')
    reg.add_argument('model_id')
    sub.add_parser('models', help='List redacted provider metadata')
    sub.add_parser('verify', help='Check frozen exam and binary/harness versions without an API call')
    limits = sub.add_parser('set-limits', help='Set formal per-game wall time before any official attempt')
    duration = limits.add_mutually_exclusive_group(required=True)
    duration.add_argument('--seconds', type=int)
    duration.add_argument('--unlimited', action='store_true')
    limits.add_argument('--concurrency', type=int, default=1, help='Maximum concurrent official games per model')
    limits.add_argument('--stop-on-technical-failure', action='store_true', help='Stop the entire batch immediately on any technical failure')
    batch = sub.add_parser('batch', help='Run all official cases with a separate queue per model')
    batch.add_argument('model_ids', nargs='+')
    for name in ('pilot', 'run'):
        p = sub.add_parser(name)
        p.add_argument('model_id')
        if name == 'run':
            p.add_argument('--case', choices=[c.lower() for c in CHARACTERS] + ['all'], default='all')
    sub.add_parser('report')
    args = parser.parse_args()
    try:
        if args.command == 'register':
            result = register(args.private_dir / 'providers', args.model_id, sys.stdin.read().strip())
        elif args.command == 'models':
            result = [public_config(read_config(args.private_dir / 'providers', p.stem))
                      for p in sorted((args.private_dir / 'providers').glob('*.json'))]
        elif args.command == 'init':
            result = initialize(args.exam.parent, args.game_root, args.claude)
            report(args.exam)
        elif args.command == 'verify':
            result = load_exam(args.exam, args.game_root)
            if claude_version(args.claude) != result['claude_version']:
                raise ValueError('Claude Code version changed')
            result = {'verified': True, 'exam_id': result['id'], 'provider_calls': 0}
        elif args.command == 'set-limits':
            load_exam(args.exam)
            if args.seconds is not None and args.seconds < 60:
                raise ValueError('Official limit must be at least 60 seconds')
            if args.concurrency not in range(1, len(CHARACTERS) + 1):
                raise ValueError('Concurrency must be between 1 and the number of cases')
            if (args.exam.parent / 'runs/official').exists():
                raise ValueError('Official attempts already exist; policy is locked')
            policy = load_json(args.exam.parent / 'policy.json')
            policy.update(official_seconds=args.seconds, official_unlimited=args.unlimited,
                          concurrency_per_model=args.concurrency,
                          stop_on_technical_failure=args.stop_on_technical_failure)
            atomic_json(args.exam.parent / 'policy.json', policy)
            result = policy
            report(args.exam)
        elif args.command == 'batch':
            from .batch import launch
            result = launch(args.exam, args.game_root, args.private_dir, args.model_ids, args.claude)
        elif args.command in ('pilot', 'run'):
            config = read_config(args.private_dir / 'providers', args.model_id)
            cases = ['practice'] if args.command == 'pilot' else ([c.lower() for c in CHARACTERS] if args.case == 'all' else [args.case])
            result = []
            for case in cases:
                row = run(args.exam, args.game_root, args.private_dir, config,
                          'pilot' if args.command == 'pilot' else 'official', case, args.claude)
                result.append(row)
                report(args.exam)
                if row['status'] != 'completed':
                    break
        else:
            result = report(args.exam)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, OSError, StopIteration) as error:
        # Provider parser messages deliberately omit the supplied command/values.
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
