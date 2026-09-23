from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import threading
import pytest
from arena.batch import schedule
from arena.runner import session_headers, time_limit


def test_unlimited_must_be_explicit_and_pilot_stays_bounded():
    policy = {'pilot_seconds': 600, 'official_seconds': None}
    with pytest.raises(ValueError, match='unset'):
        time_limit(policy, 'official')
    policy['official_unlimited'] = True
    assert time_limit(policy, 'official') is None
    assert time_limit(policy, 'pilot') == 600
    policy['official_seconds'] = 3600
    with pytest.raises(ValueError, match='also specify'):
        time_limit(policy, 'official')
    policy['official_unlimited'] = False
    assert time_limit(policy, 'official') == 3600


def test_session_header_is_replaced_without_changing_other_headers():
    assert session_headers('X-Extra: a\nx-session-id: stale\nX-Session-Id: stale2', 'unique') == 'X-Extra: a\nX-Session-Id: unique'


def test_two_lanes_per_model_refill_independently_without_retry():
    jobs = [dict(key=f'{model}/{case}', model_id=model) for model in ('a', 'b', 'c') for case in range(4)]
    started = {j['key']: threading.Event() for j in jobs}
    release = {j['key']: threading.Event() for j in jobs}
    calls, active, peak = Counter(), Counter(), Counter()
    lock, stop = threading.Lock(), threading.Event()
    def execute(job):
        key, model = job['key'], job['model_id']
        with lock:
            calls[key] += 1
            active[model] += 1
            peak[model] = max(peak[model], active[model])
        started[key].set()
        assert release[key].wait(10)
        with lock:
            active[model] -= 1
        return {'status': 'technical_failure' if key == 'a/0' else 'completed'}
    def observe(results, running):
        counts = Counter(key.split('/')[0] for key in running)
        assert all(v <= 2 for v in counts.values())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(schedule, jobs, execute, 2, observe, stop, .01)
        try:
            for model in ('a', 'b', 'c'):
                assert started[f'{model}/0'].wait(3)
                assert started[f'{model}/1'].wait(3)
                assert not started[f'{model}/2'].is_set()
            release['a/0'].set()
            assert started['a/2'].wait(3)
            assert not started['a/3'].is_set()
            assert not started['b/2'].is_set()
        finally:
            for event in release.values():
                event.set()
        results = future.result(timeout=10)
    assert len(results) == 12
    assert all(v == 1 for v in calls.values())
    assert peak == Counter(a=2, b=2, c=2)
    assert results['a/0']['status'] == 'technical_failure'


def test_stop_does_not_start_queued_games():
    jobs = [dict(key=str(i), model_id='a') for i in range(4)]
    stop = threading.Event()
    calls = []
    def execute(job):
        calls.append(job['key'])
        stop.wait(3)
        return {'status': 'interrupted'}
    def observe(*_):
        stop.set()
    result = schedule(jobs, execute, 2, observe, stop, .01)
    assert len(result) == len(calls) == 2


def test_observer_failure_releases_workers():
    stop = threading.Event()
    def execute(_):
        assert stop.wait(3)
    def observe(*_):
        raise RuntimeError('report failure')
    with pytest.raises(RuntimeError, match='report failure'):
        schedule([dict(key='a/0', model_id='a')], execute, 1, observe, stop, .01)
    assert stop.is_set()
