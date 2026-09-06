"""Opt-in real-stack verification. Run inside Docker Compose; never during pytest.

python -m src.tests.gold_consensus_benchmark --seconds 14400 --symbols 35
Creates explicitly synthetic datasets/runs, preserving all existing market data.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import resource
import tempfile
import time
from datetime import datetime, timedelta, timezone

import httpx
import numpy as np

from src.analytics.gold_consensus_config import DatasetManifest
from src.db.clickhouse import get_client
from src.db.clickhouse.gold_consensus import CSV_COLUMNS, import_dataset, dataset_row
from src.db.session import SessionLocal
from src.db.models.stock import StockInstrument
from sqlalchemy import select


def fixture(seconds, n):
    symbols=[f'SYNTH_GOLD_{i:02d}' for i in range(n)]
    start=datetime(2026,8,1,8,30,tzinfo=timezone.utc)
    sessions=[{'open':start+timedelta(days=d),'close':start+timedelta(days=d,seconds=seconds),
               'eligible_symbols':symbols} for d in range(4)]
    manifest=DatasetManifest(name=f'SYNTHETIC benchmark {n} ETFs x {seconds}s x 4 sessions',
        source_reference='Deterministic synthetic fixture seed 740; not market evidence',
        calendar_reference='Four explicitly synthetic sessions',eligibility_reference='Fixed synthetic universe',
        phase_reference='Generated continuous phase, with explicit invalidation samples',clock='synthetic',sessions=sessions)
    file=tempfile.TemporaryFile(mode='w+b')
    import io
    wrapper=io.TextIOWrapper(file,encoding='utf-8',newline='')
    writer=csv.writer(wrapper);writer.writerow(CSV_COLUMNS)
    rng=np.random.default_rng(740)
    for d,session in enumerate(sessions):
        factor=np.cumsum(rng.normal(0,.00006,seconds))
        times=[(session['open']+timedelta(seconds=t)).isoformat() for t in range(seconds)]
        for j,symbol in enumerate(symbols):
            price=(100000+j*14000)*np.exp(factor+rng.normal(0,.0007,seconds))
            # An instrument-specific temporary premium plus subsequent recovery.
            if j==0:price[seconds//3:seconds//2]*=1.012
            rows=((symbol,times[t],times[t],t+1,round(price[t]-30,3),round(price[t]+30,3),
                   0 if j==1 and t%997==0 else 100+j,150-j%10,'continuous') for t in range(seconds))
            writer.writerows(rows)
        print(json.dumps({'phase':'generate','session':d+1}),flush=True)
    wrapper.flush();wrapper.detach();file.seek(0)
    return manifest,file,symbols,sessions


def real_data_audit():
    with SessionLocal() as session:
        codes=list(session.execute(select(StockInstrument.instrument_code).where(StockInstrument.is_gold_etf.is_(True))).scalars())
    client=get_client();start=time.perf_counter();count=0
    # Read actual source data in bounded blocks; do not infer historical phase or membership.
    with client.query_row_block_stream('SELECT instrument_code,trade_date,trade_time,ref_id,bid_price,ask_price,bid_volume,ask_volume '
        'FROM stock_order_book WHERE depth_level=1 AND instrument_code IN {codes:Array(String)} '
        'ORDER BY trade_date,instrument_code,trade_time,ref_id',parameters={'codes':codes}) as stream:
        invalid=0
        for block in stream:
            count+=len(block)
            invalid+=sum(not (r[4]>0 and r[5]>r[4] and r[6]>0 and r[7]>0) for r in block)
    return {'gold_metadata_count':len(codes),'raw_level1_rows_read':count,'invalid_level1_rows':invalid,
            'read_validate_seconds':time.perf_counter()-start,
            'limitation':'Current metadata is only an audit selector. Historical eligibility, phases, arrival times and pre-merge source events are not established; no real-market scoring claim.'}


def run(seconds,n,output,dataset_id=None):
    started=time.perf_counter();report={'seconds_per_session':seconds,'symbols':n,'sessions':4}
    if dataset_id:
        stored=dataset_row(dataset_id)
        assert stored and stored.status=='ready'
        manifest=DatasetManifest.model_validate(stored.manifest)
        assert manifest.clock=='synthetic', 'benchmark reuse is restricted to synthetic datasets'
        sessions=[s.model_dump() for s in manifest.sessions];symbols=sessions[0]['eligible_symbols']
        assert len(symbols)==n and (sessions[0]['close']-sessions[0]['open']).total_seconds()==seconds
        dataset={'dataset_id':str(stored.dataset_id),'row_count':stored.row_count,'sha256':stored.sha256}
        report['import_seconds']=None
        report['reused_immutable_dataset']=True
    else:
        manifest,file,symbols,sessions=fixture(seconds,n)
        began=time.perf_counter();dataset=import_dataset(manifest,file);file.close()
        report['import_seconds']=time.perf_counter()-began
    report['dataset']=dataset
    print(json.dumps({'phase':'imported',**dataset}),flush=True)
    client=httpx.Client(base_url='http://127.0.0.1:8000',timeout=180,follow_redirects=True)
    assert client.get('/api/v1/gold-kalman/datasets').status_code==401
    response=client.post('/admin/login',data={'username':os.environ['ADMIN_USER'],'password':os.environ['ADMIN_PASSWORD']})
    assert response.status_code==200
    assert client.get('/admin/gold-kalman').status_code==200
    assert client.get('/admin/gold-kalman-runs').status_code==200
    policy={'dataset_id':dataset['dataset_id'],'symbols':symbols,
            'history_from':sessions[0]['open'].isoformat(),
            'validation_from':sessions[2]['open'].isoformat(),'validation_to':sessions[2]['close'].isoformat(),
            'test_from':sessions[3]['open'].isoformat(),'test_to':sessions[3]['close'].isoformat(),
            'calibration_lookback_sessions':2,'min_calibration_observations':20,
            'warmup_seconds':10,'analysis_horizon_seconds':5,'max_quote_age':3}
    results=[]
    for mode in ('validation','test'):
        policy['mode']=mode
        if results:policy['validation_run_id']=results[0]['run_id']
        response=client.post('/admin/tasks/run-gold-kalman',json=policy)
        assert response.status_code==200,response.text
        submitted=response.json();run_id=submitted['run_id'];path=f'/api/v1/gold-kalman/runs/{run_id}'
        began=time.perf_counter();last=-1
        while True:
            detail=client.get(path).json()
            progress=detail['progress_current'];assert progress>=last
            if progress!=last:
                print(json.dumps({'phase':mode,'run_id':run_id,'status':detail['status'],'progress':progress,'total':detail['progress_total']}),flush=True)
                last=progress
            if detail['status'] in ('completed','failed','skipped'):break
            if time.perf_counter()-began>1800:raise TimeoutError('worker did not finish in 30 minutes')
            time.sleep(2)
        assert detail['status']=='completed',detail.get('error')
        assert detail['progress_current']==detail['progress_total']
        data=client.get(path+'/timeline?limit=10000').json();assert data['items']
        selected=next(row for row in data['items'] if row['ready'])
        snapshot=client.get(path+'/snapshot',params={'decision_time':selected['decision_time']})
        assert snapshot.status_code==200,snapshot.text
        assert len(snapshot.json()['items'])>=3
        history=client.get(path+'/history',params={'symbol':symbols[0],'limit':10}).json()
        assert len(history['items'])==10 and history['next_offset']==10
        assert len(client.get(path+'/calibrations').json()['items'])==3
        assert client.get(path+'/evaluation').json()['result']['sessions']
        with client.stream('GET',path+'/export.csv') as stream:
            assert stream.status_code==200
            lines=stream.iter_lines();assert next(lines).startswith('# ')
            assert 'run_id' in next(lines)
            assert next(lines)
        counts=get_client().query('SELECT count(),uniqExact(tuple(method,range_name,decision_time,instrument_code)) '
            'FROM gold_kalman_scores FINAL WHERE run_id={id:UUID}',parameters={'id':run_id}).result_rows[0]
        assert counts[0]==counts[1] and counts[0]>0
        results.append({'run_id':run_id,'mode':mode,'elapsed_seconds':time.perf_counter()-began,
                        'score_rows':counts[0],'result':detail['result']})
    report['runs']=results
    report['real_data_audit']=real_data_audit()
    report['wall_seconds']=time.perf_counter()-started
    report['client_peak_rss_mb']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(report,indent=2,default=str))
    print(json.dumps({'phase':'complete','report':output,'wall_seconds':report['wall_seconds']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=int,default=14400)
    parser.add_argument('--symbols',type=int,default=35)
    parser.add_argument('--output',default='/app/src/tests/artifacts/gold_consensus_performance.json')
    parser.add_argument('--dataset-id',default=None)
    args=parser.parse_args();run(args.seconds,args.symbols,args.output,args.dataset_id)
