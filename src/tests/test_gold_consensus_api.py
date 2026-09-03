import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from fastapi.testclient import TestClient

from src.main import app
from src.tests.test_gold_consensus import config


def test_unauthenticated_reads_and_submission():
    client=TestClient(app)
    run_id=str(uuid.uuid4())
    for endpoint in ('', '/timeline','/history?symbol=A','/calibrations','/evaluation','/export.csv'):
        assert client.get(f'/api/v1/gold-kalman/runs/{run_id}{endpoint}').status_code==401
    assert client.post('/admin/tasks/run-gold-kalman',json=config().model_dump(mode='json')).status_code==401


def test_missing_wrong_family_and_invalid_parameters():
    client=TestClient(app)
    with patch('src.routes.gold_consensus._require_admin',new=AsyncMock()), patch('src.routes.gold_consensus.get_run',return_value=SimpleNamespace(family='parity')):
        assert client.get(f'/api/v1/gold-kalman/runs/{uuid.uuid4()}').status_code==404
    with patch('src.routes.gold_consensus._require_admin',new=AsyncMock()):
        assert client.get(f'/api/v1/gold-kalman/runs/{uuid.uuid4()}/timeline?limit=10001').status_code==422
        assert client.get(f'/api/v1/gold-kalman/runs/{uuid.uuid4()}/snapshot?decision_time=2026-08-01T10:00:00').status_code==422


def test_submission_uses_configured_celery_in_threadpool():
    from src.celery_app import celery
    from src.analytics.gold_consensus_config import DatasetManifest
    cfg=config()
    manifest=DatasetManifest(name='test',source_reference='fixture',calendar_reference='fixture',
        eligibility_reference='fixture',phase_reference='fixture',clock='synthetic',
        sessions=[{'open':cfg.validation_from,'close':cfg.validation_to,'eligible_symbols':cfg.symbols}])
    def enqueue(task,**kwargs):
        assert task.app is celery
        assert kwargs['config']['policy_hash']==cfg.policy_hash()
        assert kwargs['progress_total']>0
        return SimpleNamespace(run_id=uuid.uuid4()),SimpleNamespace(id='task')
    with patch('src.routes.gold_consensus._require_admin',new=AsyncMock()), \
         patch('src.routes.gold_consensus.validate_inputs',return_value=(SimpleNamespace(sha256='sha'),manifest)), \
         patch('src.routes.gold_consensus.enqueue_task',side_effect=enqueue):
        response=TestClient(app).post('/admin/tasks/run-gold-kalman',json=cfg.model_dump(mode='json'))
        assert response.status_code==200,response.text
        assert response.json()['task_id']=='task'


def test_migration_and_query_scoping():
    migration=importlib.import_module('src.db.clickhouse.migrations.versions.021_gold_consensus')
    client=MagicMock();migration.upgrade(client)
    assert len(client.command.call_args_list)==4
    for call in client.command.call_args_list[1:]:
        assert 'ReplacingMergeTree' in call.args[0] and 'run_id' in call.args[0]
    client.reset_mock();migration.downgrade(client)
    assert len(client.command.call_args_list)==4
    from src.db.clickhouse.gold_consensus import query_rows
    client.query.return_value.result_rows=[]
    with patch('src.db.clickhouse.gold_consensus.get_client',return_value=client):
        assert query_rows('scores',uuid.UUID(int=1),symbol='A',limit=10,offset=20)==[]
        query=client.query.call_args
        assert 'FINAL' in query.args[0] and 'run_id={id:UUID}' in query.args[0]
        assert query.kwargs['parameters']['offset']==20


def test_late_old_book_does_not_revive_state():
    import numpy as np
    from src.analytics.gold_consensus import canonical_events
    rows=np.array([[1,1,1,100,101,5,5,1],[3,3,3,0,0,0,0,0],[4,2,2,100,101,5,5,1]],dtype=float)
    assert len(canonical_events(rows))==2
