"""Repeated characters remain independent, paired seed cases throughout the arena."""
import json
from pathlib import Path
import sys
import pytest
from arena import __main__ as cli
from arena.common import atomic_json, load_exam
from arena.providers import register
from arena.scoring import score, standings
from arena.server import Attempt

ROOT = Path(__file__).resolve().parents[1]


def make_exam(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'claude_version', lambda _: 'test-version')
    directory = tmp_path / 'nine-case-exam'
    exam = cli.initialize(directory, ROOT, 'unused', character='Necrobinder', count=9)
    atomic_json(directory / 'policy.json', {'pilot_seconds':600, 'official_seconds':None,
        'official_unlimited':True, 'concurrency_per_model':2, 'stop_on_technical_failure':True})
    return directory, exam


def test_nine_unique_cases_exclude_old_seeds_and_freeze(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'claude_version', lambda _: 'test-version')
    sequence=iter(''.join(f'{i:010d}' for i in range(11)))
    monkeypatch.setattr(cli.secrets, 'choice', lambda _: next(sequence))
    directory=tmp_path/'exam'
    exam=cli.initialize(directory, ROOT, 'unused', character='Necrobinder', count=9, excluded_seeds=['0000000000'])
    assert [c['id'] for c in exam['cases']] == [f'necrobinder-{i:02d}' for i in range(1,10)]
    assert all(c['character']=='Necrobinder' for c in exam['cases'])
    assert len({c['seed'] for c in exam['cases']})==9
    assert exam['cases'][0]['seed']=='0000000001'
    assert exam['pilot']['seed']=='0000000010'
    assert load_exam(directory/'exam.json',ROOT)==exam
    cli.report(directory/'exam.json')
    text=(directory/'README.md').read_text()
    assert '全部 9 局' in text and 'necrobinder-09' in text
    assert '四局' not in text


@pytest.mark.parametrize('options',[{'character':'Necrobinder','count':0},{'character':'Necrobinder','count':101},{'character':None,'count':9},{'character':'missing','count':9}])
def test_invalid_exam_shape_rejected_before_creating_directory(tmp_path,options):
    directory=tmp_path/'exam'
    with pytest.raises(ValueError):cli.initialize(directory,ROOT,'unused',**options)
    assert not directory.exists()


def test_all_nine_case_ids_reach_native_engine_independently(tmp_path,monkeypatch):
    directory,exam=make_exam(tmp_path,monkeypatch)
    checkpoint_paths=[]
    for case in exam['cases']:
        target=tmp_path/'native'/case['id']
        attempt=Attempt(directory/'exam.json',case['id'],'official',ROOT,target)
        try:
            current=json.loads((target/'current.json').read_text())
            assert current['fault'] is None
            assert not current['score']['terminal']
            first=json.loads((target/'game.jsonl').read_text().splitlines()[0])
            assert first['request']=={'cmd':'start_run','character':'Necrobinder','seed':case['seed'],'ascension':10,'lang':'en'}
            assert (target/'checkpoint.save').exists()
            checkpoint_paths.append(target/'checkpoint.save')
        finally:attempt.close()
    assert len(set(checkpoint_paths))==9


def test_overall_requires_all_nine_and_pairs_by_case_id():
    cases=[f'necrobinder-{i:02d}' for i in range(1,10)]
    rows=[]
    for model in ['a','b']:
        for i,case in enumerate(cases,1):
            metrics={'total_floor':i+(model=='b'),'act':1,'act_floor':i,'player_hp':0,'player_max_hp':66,'enemy_hp':10,'enemy_max_hp':100,'enemy_hp_available':True,'enemies':[]}
            rows.append({'model_id':model,'case_id':case,'mode':'official','status':'completed','score':score({'decision':'game_over','victory':False},metrics)})
    ranked=standings(rows,cases)
    assert [(r['model_id'],r['total_floor']) for r in ranked['overall']]==[('b',54),('a',45)]
    assert all([r['model_id'] for r in ranked['per_case'][c]]==['b','a'] for c in cases)
    assert [r['model_id'] for r in standings(rows[:-1],cases)['overall']]==['a']


def test_serial_all_uses_manifest_ids_instead_of_character_names(tmp_path,monkeypatch,capsys):
    directory,exam=make_exam(tmp_path,monkeypatch)
    private=tmp_path/'private'
    register(private/'providers','mock','ANTHROPIC_BASE_URL=https://example.invalid ANTHROPIC_AUTH_TOKEN=dummy claude --model mock')
    called=[]
    def fake_run(manifest,game,private,config,mode,case,executable):
        called.append(case)
        return {'status':'completed','case_id':case}
    monkeypatch.setattr(cli,'run',fake_run)
    monkeypatch.setattr(sys,'argv',['arena','--exam',str(directory/'exam.json'),'--private-dir',str(private),'run','mock','--case','all'])
    cli.main()
    assert called==[c['id'] for c in exam['cases']]
    assert len(json.loads(capsys.readouterr().out))==9
