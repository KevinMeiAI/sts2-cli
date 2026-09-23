"""One coordinator owns official queues and reports; workers own one game each."""
from __future__ import annotations
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import os
from pathlib import Path
import signal
import threading
from .common import atomic_json, digest, load_exam, load_json, utc
from .providers import public_config, read_config, redact
from .runner import claude_version, run, time_limit
from .scoring import standings


class FailureStop:
    """Publish the first failure and signal all workers before any cleanup waits."""
    def __init__(self, stop_event, path, enabled=True):
        self.stop_event, self.path, self.enabled = stop_event, path, enabled
        self.record = None
        self.lock = threading.Lock()

    def trip(self, key, reason):
        if not self.enabled:
            return
        with self.lock:
            if self.record is not None:
                return
            self.record = {'at': utc(), 'origin': key, 'reason': reason,
                           'status': 'technical_failure', 'action': 'stop_all'}
            self.stop_event.set()
            atomic_json(self.path, self.record)


def schedule(jobs, execute, concurrency, observe, stop_event, interval=5, stop_on_technical_failure=False):
    """Refill each model independently; a finished attempt is never resubmitted."""
    if type(concurrency) is not int or concurrency <= 0:
        raise ValueError('Concurrency must be a positive integer')
    if len({j['key'] for j in jobs}) != len(jobs):
        raise ValueError('Duplicate jobs')
    pending = {m: deque(j for j in jobs if j['model_id'] == m)
               for m in dict.fromkeys(j['model_id'] for j in jobs)}
    results, futures = {}, {}
    with ThreadPoolExecutor(max_workers=max(1, len(pending) * concurrency)) as pool:
        try:
            while True:
                for future in list(futures):
                    if future.done():
                        job = futures.pop(future)
                        results[job['key']] = future.result()
                        if stop_on_technical_failure and results[job['key']]['status'] == 'technical_failure':
                            stop_event.set()
                if not stop_event.is_set():
                    active = Counter(j['model_id'] for j in futures.values())
                    for model, queue in pending.items():
                        while queue and active[model] < concurrency and not stop_event.is_set():
                            job = queue.popleft()
                            futures[pool.submit(execute, job)] = job
                            active[model] += 1
                observe(results, {j['key'] for j in futures.values()})
                if not futures:
                    break
                wait(futures, timeout=interval, return_when=FIRST_COMPLETED)
        except BaseException:
            stop_event.set()
            raise
    return results


def snapshot(directory, jobs, results, active, halted=False):
    rows = []
    for job in jobs:
        path = directory / 'runs/official' / job['model_id'] / job['case_id']
        row = dict(job, status='starting' if job['key'] in active else ('cancelled_before_start' if halted else 'queued'))
        if (path / 'run.json').exists():
            record = load_json(path / 'run.json')
            row.update(status=record['status'], started_at=record['started_at'],
                       claude_pid=record.get('claude_pid'), session_header_id=record.get('session_header_id'))
        if (path / 'current.json').exists():
            current = load_json(path / 'current.json')
            row.update(score=current['score'], decision=current['state'].get('decision'),
                       native_state_updated_at=current['at'], engine_fault=current.get('fault'))
        if job['key'] in results:
            row.update(status=results[job['key']]['status'], result=results[job['key']])
        rows.append(row)
    data = {'updated_at': utc(), 'active': len(active),
            'active_by_model': dict(Counter(j['model_id'] for j in jobs if j['key'] in active)),
            'finished': len(results), 'total': len(jobs), 'jobs': rows}
    atomic_json(directory / 'progress.json', data)
    return data


def write_report(directory, plan, data):
    rank = standings([r['result'] for r in data['jobs'] if 'result' in r], plan['case_ids'])
    atomic_json(directory / 'leaderboard.json', rank)
    limit = '不限时' if plan['time_limit_seconds'] is None else str(plan['time_limit_seconds']) + ' 秒'
    lines = ['# Slay the Spire 2 · A10 正式模型比赛', '',
        f"每模型最多 {plan['concurrency_per_model']} 局并发，单局{limit}，统一 effort=max。",
        '同一角色使用同一种子；所有比赛均在独立 Claude Code 会话中运行。',
        f"状态：{plan['status']}；已结束 {data['finished']}/{data['total']}；活跃 {data['active']}。",
        f"更新时间：{data['updated_at']}",
        '故障策略：任一 technical_failure 立即停止所有对局与排队。' if plan.get('stop_on_technical_failure') else '故障策略：各局独立记录。', '',
        '| 模型 | 角色 | 正式种子 | 状态 | 累计楼层 | 角色 HP | 敌人 HP |',
        '|---|---|---|---|---|---|---|']
    for row in data['jobs']:
        s = row.get('score') or {}
        player = f"{s['player_hp']}/{s['player_max_hp']}" if s else '—'
        enemy = f"{s['enemy_hp']}/{s['enemy_max_hp']}" if s and s.get('enemy_max_hp') else '—'
        lines.append(f"| {row['model_id']} | {row['character']} | `{row['seed']}` | {row['status']} | {s.get('total_floor', '—')} | {player} | {enemy} |")
    lines += ['', '## 总榜', '', '只有四局全部自然胜败结束的模型参与总榜；运行中的楼层不是最终成绩。']
    for r in rank['overall']:
        lines.append(f"- {r['model_id']}：总楼层 {r['total_floor']}，通关 {r['wins']}，血量得分 {r['hp_score']}")
    lines += ['', '每角色先比累计楼层，同层胜利优先；胜局比自身 HP 百分比（高优），败局比敌方 HP 百分比（低优）。',
        '敌人分母包含终局战斗中已击杀与召唤的敌人。总榜比较总楼层、通关数、血量得分之和。',
        '接口错误、主动提前停止、引擎故障和外部中断单独记录，保留检查点，不伪装成死亡、不自动重开。',
        '每局 HOME、Claude 配置、会话标识、MCP 管道、原生引擎、存档和日志独立。模型仅有三个游戏工具。',
        '日志在 runs/official/<模型>/<角色>/；总控状态在 batch.json、progress.json。',
        'usage 可能不完整；第三方费用以供应商账单为准。']
    path = directory / 'README.md'
    temporary = path.with_suffix('.md.tmp')
    temporary.write_text('\n'.join(lines) + '\n')
    temporary.replace(path)


def launch(manifest, game_root, private_dir, models, executable):
    manifest, game_root, private_dir = Path(manifest).resolve(), Path(game_root).resolve(), Path(private_dir).resolve()
    exam = load_exam(manifest, game_root)
    if claude_version(executable) != exam['claude_version']:
        raise ValueError('Claude Code version differs from the frozen exam')
    policy = load_json(manifest.parent / 'policy.json')
    seconds = time_limit(policy, 'official')
    concurrency = policy.get('concurrency_per_model', 1)
    if type(concurrency) is not int or not 1 <= concurrency <= len(exam['cases']):
        raise ValueError('Invalid official concurrency')
    if not models or len(set(models)) != len(models):
        raise ValueError('Supply unique model IDs')
    configs = {m: read_config(private_dir / 'providers', m) for m in models}
    jobs = [dict(key=m + '/' + c['id'], model_id=m, case_id=c['id'],
                 character=c['character'], seed=c['seed']) for m in models for c in exam['cases']]
    for job in jobs:
        if (manifest.parent / 'runs/official' / job['model_id'] / job['case_id']).exists():
            raise ValueError('Official attempt already exists; no automatic restart')
        if (private_dir / 'sessions' / exam['id'] / 'official' / job['model_id'] / job['case_id']).exists():
            raise ValueError('Private official session already exists')
    # This claim deliberately survives shutdown: a new coordinator cannot duplicate attempts.
    with (manifest.parent / 'batch.lock').open('x') as lock:
        lock.write(str(os.getpid()) + '\n')
    plan = {'schema': 1, 'kind': 'official', 'status': 'running', 'started_at': utc(),
        'coordinator_pid': os.getpid(), 'models': [public_config(configs[m]) for m in models],
        'case_ids': [c['id'] for c in exam['cases']], 'cases': exam['cases'],
        'concurrency_per_model': concurrency, 'time_limit_seconds': seconds,
        'stop_on_technical_failure': policy.get('stop_on_technical_failure', False),
        'exam_sha256': digest(manifest), 'policy_sha256': digest(manifest.parent / 'policy.json'),
        'prompt_sha256': digest(Path(__file__).with_name('prompt.txt')), 'claude_version': exam['claude_version']}
    atomic_json(manifest.parent / 'batch.json', plan)
    stop_event = threading.Event()
    breaker = FailureStop(stop_event, manifest.parent / 'halt.json', plan['stop_on_technical_failure'])
    old_handlers = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, lambda *_: stop_event.set())
    def execute(job):
        config = configs[job['model_id']]
        try:
            return run(manifest, game_root, private_dir, config, 'official', job['case_id'], executable, stop_event,
                       lambda reason: breaker.trip(job['key'], reason))
        except Exception as error:
            breaker.trip(job['key'], 'worker_exception')
            result = {'model_id': job['model_id'], 'case_id': job['case_id'], 'mode': 'official',
                      'status': 'technical_failure', 'score': None, 'ended_at': utc(),
                      'error': redact(f'{type(error).__name__}: {error}', config)}
            atomic_json(manifest.parent / 'runs/official' / job['model_id'] / job['case_id'] / 'coordinator-error.json', result)
            return result
    seen = set()
    def observe(results, active):
        for key in results.keys() - seen:
            print(json.dumps({'finished': key, 'status': results[key]['status'], 'at': utc()}), flush=True)
            seen.add(key)
        if breaker.record:
            plan.update(status='halting_technical_failure', halt=breaker.record)
            atomic_json(manifest.parent / 'batch.json', plan)
        data = snapshot(manifest.parent, jobs, results, active, stop_event.is_set())
        write_report(manifest.parent, plan, data)
    try:
        results = schedule(jobs, execute, concurrency, observe, stop_event,
                           stop_on_technical_failure=plan['stop_on_technical_failure'])
        plan.update(status='halted_technical_failure' if breaker.record else ('interrupted' if stop_event.is_set() else 'finished'), ended_at=utc(),
                    completed_games=sum(r['status'] == 'completed' for r in results.values()),
                    ended_attempts=len(results), total_attempts=len(jobs))
        atomic_json(manifest.parent / 'batch.json', plan)
        data = snapshot(manifest.parent, jobs, results, set(), stop_event.is_set())
        write_report(manifest.parent, plan, data)
        atomic_json(manifest.parent / 'summary.json', {'batch': plan, **data})
        return {'status': plan['status'], 'completed_games': plan['completed_games'], 'attempts': len(jobs)}
    finally:
        stop_event.set()
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
