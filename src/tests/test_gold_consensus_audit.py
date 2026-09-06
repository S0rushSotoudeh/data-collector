"""Audit regressions: provenance, preflight, trace and bounded API reads."""
import copy
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.analytics.gold_consensus import calibrate, filter_grid, reconstruct
from src.analytics.gold_consensus_config import DatasetManifest, engine_identity
from src.analytics.gold_consensus_engine import calendar_readiness, validate_inputs, validation_usable
from src.db.clickhouse.gold_consensus import display_mapping, manifest_fingerprint, stream_csv, COLUMNS
from src.main import app
from src.tests.test_gold_consensus import config, events, grid


def manifest_for(cfg, seconds=600):
    return DatasetManifest(name='Synthetic audit fixture', source_reference='fixture',
        calendar_reference='fixture', eligibility_reference='fixture', phase_reference='fixture', clock='synthetic',
        sessions=[{'open': cfg.history_from + timedelta(days=i),
                   'close': cfg.history_from + timedelta(days=i, seconds=seconds),
                   'eligible_symbols': cfg.symbols} for i in range(7)])


def test_short_defaults_rejected_and_immediately_prior_history_required():
    cfg = config(warmup_seconds=120, min_calibration_observations=60)
    m = manifest_for(cfg, 30)
    errors = calendar_readiness(cfg, m)
    assert any('warmup_seconds' in e for e in errors)
    early = cfg.model_copy(update={'validation_from': m.sessions[2].open})
    assert any('immediately preceding' in e for e in calendar_readiness(early, m))
    assert not calendar_readiness(cfg, manifest_for(cfg))


def test_zero_outputs_cannot_promote_and_policy_engine_manifest_stay_locked():
    cfg = config().model_copy(update={'mode': 'test', 'validation_run_id': uuid.uuid4()})
    m = manifest_for(cfg)
    dataset = SimpleNamespace(status='ready', sha256='sha', manifest=m.model_dump(mode='json'))
    reference = SimpleNamespace(family='gold_kalman', status='completed', result={'sessions': []},
        config={'policy_hash': cfg.policy_hash(), 'policy': {'mode': 'validation'}, 'dataset_sha256': 'sha',
                'manifest_sha256': manifest_fingerprint(dataset.manifest), 'engine_identity': engine_identity()})
    support = {(i, s): 100 for i in range(7) for s in cfg.symbols}
    with patch('src.analytics.gold_consensus_engine.dataset_row', return_value=dataset), \
         patch('src.analytics.gold_consensus_engine.observation_support', return_value=support), \
         patch('src.analytics.gold_consensus_engine.get_run', return_value=reference):
        with pytest.raises(ValueError, match='no usable scores/outcomes'):
            validate_inputs(cfg)
        reference.result = {'sessions': [{'method': method, 'score_count': 100, 'outcome_count': 50}
                              for method in ('scheduled', 'frozen', 'peer_median')]}
        assert validation_usable(reference.result)
        validate_inputs(cfg)
        reference.config['engine_identity'] = 'old'
        with pytest.raises(ValueError, match='engine identity'):
            validate_inputs(cfg)
        reference.config['engine_identity'] = engine_identity()
        reference.config['manifest_sha256'] = 'changed'
        with pytest.raises(ValueError, match='manifest changed'):
            validate_inputs(cfg)
        reference.config['policy_hash'] = 'changed'
        with pytest.raises(ValueError, match='policy/dataset'):
            validate_inputs(cfg)


def test_preflight_rejects_all_excluded_support_without_mutating_policy():
    cfg = config()
    original = cfg.model_dump()
    m = manifest_for(cfg)
    with patch('src.analytics.gold_consensus_engine.dataset_row', return_value=SimpleNamespace(
            status='ready', sha256='sha', manifest=m.model_dump(mode='json'))), \
         patch('src.analytics.gold_consensus_engine.observation_support', return_value={}):
        with pytest.raises(ValueError, match='fewer than three'):
            validate_inputs(cfg)
    assert cfg.model_dump() == original


def test_symbols_are_matched_by_string_code_and_never_invented():
    large = '99999999999999999'
    codes = [large, '123', 'missing']
    db = MagicMock()
    db.__enter__.return_value.execute.return_value.all.return_value = [('123', 'طلا'), (large, 'عیار')]
    with patch('src.db.clickhouse.gold_consensus.SessionLocal', return_value=db):
        assert display_mapping(codes, 'exchange_time') == {large: 'عیار', '123': 'طلا', 'missing': 'Symbol unavailable'}
        assert display_mapping(['SYNTH_GOLD_17'], 'synthetic') == {'SYNTH_GOLD_17': 'SYNTH_GOLD_17'}
        assert display_mapping(codes, 'exchange_time', {large: 'Saved symbol'})['123'] == 'Symbol unavailable'


def test_full_manifest_fingerprint_changes_material_identity():
    manifest = manifest_for(config()).model_dump(mode='json')
    original = manifest_fingerprint(manifest)
    for field in ['clock', 'calendar_reference', 'eligibility_reference', 'phase_reference', 'display_symbols', 'sessions']:
        changed = copy.deepcopy(manifest)
        changed[field] = {'different': True}
        assert manifest_fingerprint(changed) != original
    assert manifest_fingerprint(dict(reversed(list(manifest.items())))) == original


def test_run_history_displays_symbols_without_mutating_internal_keys():
    from src.admin.run_views import _gold_display_fields
    code = '99999999999999999'
    item = SimpleNamespace(config={'policy': {'symbols': [code]}, 'display_symbols': {code: 'طلا'},
        'dataset_manifest': {'clock': 'exchange_time', 'sessions': [{'eligible_symbols': [code]}]}},
        result={'sessions': [{'residual_std_by_symbol': {code: 0.01}}]})
    original = copy.deepcopy(item.config)
    config_view, result_view = _gold_display_fields(item)
    assert code not in str(config_view) + str(result_view)
    assert config_view['policy']['symbols'] == ['طلا']
    assert item.config == original


@pytest.mark.parametrize('method', ['scheduled', 'frozen', 'peer_median'])
def test_trace_is_same_computation_and_does_not_change_outputs(method):
    cfg = config(warmup_seconds=0)
    fit = calibrate([grid()], cfg.symbols, cfg)
    g = grid(events(seed=9))
    plain = filter_grid(g, cfg.symbols, fit, cfg, method)
    traced = filter_grid(g, cfg.symbols, fit, cfg, method, trace_at=50)
    for key in plain:
        np.testing.assert_allclose(plain[key], traced[key], equal_nan=True)
    for j, symbol in enumerate(cfg.symbols):
        trace = traced['trace']['values'][symbol]
        assert trace['fair_price'] == plain['fair'][50, j]
        assert trace['z_score'] == plain['z'][50, j]
        assert trace['residual'] == plain['delta'][50, j]
        assert trace['P_excluded'] == plain['benchmark_variance'][50, j]
        assert trace['z_score'] == pytest.approx(trace['residual'] / np.sqrt(trace['r'] + trace['P_excluded']))
        if method != 'peer_median':
            batch = traced['trace']
            assert trace['f_excluded'] == pytest.approx(trace['P_excluded'] * (
                batch['f_prior']/batch['P_prior'] + batch['B'] - trace['u_i']*trace['p_i']))


def test_fractional_delayed_sparse_quote_age_and_cached_measurements():
    cfg = config(max_quote_age=2)
    raw = events(7)
    for symbol in raw:
        raw[symbol] = raw[symbol][[0, 4]]
        raw[symbol][1, 0] = 4.5
        raw[symbol][1, 1] = 4.25
    g = reconstruct(raw, cfg.symbols, np.arange(7), 0, 7, 2, set(cfg.symbols))
    np.testing.assert_allclose(g.times - g.quote_times[:, 0], [0, 1, 2, 3, 4, .75, 1.75])
    assert g.valid[:, 0].tolist() == [True, True, True, False, False, True, True]
    assert g.new[:, 0].tolist() == [True, False, False, False, False, True, False]


def test_time_queries_are_bounded_exclusive_and_authenticated():
    run = SimpleNamespace(family='gold_kalman')
    client = TestClient(app)
    path = f'/api/v1/gold-kalman/runs/{uuid.uuid4()}'
    for suffix in ('/timeline', '/history?symbol=A', '/explain?symbol=A&decision_time=2026-08-04T00:00:01Z'):
        assert client.get(path+suffix).status_code == 401
    with patch('src.routes.gold_consensus._require_admin', new=AsyncMock()), \
         patch('src.routes.gold_consensus.get_run', return_value=run), \
         patch('src.routes.gold_consensus.query_rows', return_value=[]) as query:
        response = client.get(path+'/timeline?start=2026-08-04T00:00:00Z&end=2026-08-04T00:33:20Z')
        assert response.status_code == 200
        assert query.call_args.kwargs['start'].tzinfo is not None
        assert (query.call_args.kwargs['end']-query.call_args.kwargs['start']).total_seconds() == 2000


def test_csv_has_symbols_not_codes_and_missing_metadata_stays_unavailable():
    code = '99999999999999999'
    values = [None] * len(COLUMNS['scores'])
    values[COLUMNS['scores'].index('instrument_code')] = code
    client = MagicMock()
    client.query_row_block_stream.return_value.__enter__.return_value = [[values]]
    with patch('src.db.clickhouse.gold_consensus.get_client', return_value=client):
        content = ''.join(stream_csv('scores', uuid.uuid4(), 'scheduled', {code: 'عیار'}))
        assert 'عیار' in content and code not in content and 'instrument_code' not in content
        content = ''.join(stream_csv('scores', uuid.uuid4(), 'scheduled', {}))
        assert 'Symbol unavailable' in content and code not in content


@pytest.mark.parametrize('method', ['scheduled', 'frozen', 'peer_median'])
def test_explanation_api_matches_saved_value_without_writing(method):
    cfg = config(warmup_seconds=0)
    m = manifest_for(cfg)
    start = cfg.validation_from.timestamp()
    raw = events(100, start=start)
    fit = calibrate([grid()], cfg.symbols, cfg)
    g = reconstruct(raw, cfg.symbols, np.arange(start, start+100), start, start+600, cfg.max_quote_age, set(cfg.symbols))
    out = filter_grid(g, cfg.symbols, fit, cfg, method)
    stored = {key: float(out[value][50, 0]) for key, value in
              [('fair_price', 'fair'), ('z_score', 'z'), ('residual', 'delta'), ('persistence', 'persistence')]}
    dataset = SimpleNamespace(sha256='sha', manifest=m.model_dump(mode='json'))
    run = SimpleNamespace(family='gold_kalman', config={'policy': cfg.model_dump(mode='json'),
        'engine_identity': engine_identity(), 'dataset_sha256': 'sha',
        'manifest_sha256': manifest_fingerprint(dataset.manifest)})
    db = MagicMock()
    db.__enter__.return_value.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(
        payload=fit, calibration_id=uuid.uuid4())
    context = {'manifest': dataset.manifest, 'display_symbols': {s:s for s in cfg.symbols}}
    path = f'/api/v1/gold-kalman/runs/{uuid.uuid4()}/explain'
    with patch('src.routes.gold_consensus._require_admin', new=AsyncMock()), \
         patch('src.routes.gold_consensus.get_run', return_value=run), \
         patch('src.routes.gold_consensus.result_context', return_value=context), \
         patch('src.routes.gold_consensus.load_events', return_value=raw), \
         patch('src.routes.gold_consensus.dataset_row', return_value=dataset), \
         patch('src.routes.gold_consensus.SessionLocal', return_value=db), \
         patch('src.routes.gold_consensus.query_rows', return_value=[stored]):
        response = TestClient(app).get(path, params={'symbol':'A', 'method':method,
            'decision_time':(cfg.validation_from+timedelta(seconds=50)).isoformat()})
        assert response.status_code == 200, response.text
        assert response.json()['matches_stored'] is True
        assert response.json()['inputs']['quote_age'] == 0
        assert response.json()['inputs']['sequence'] == 50
        db.__enter__.return_value.commit.assert_not_called()
        run.config['engine_identity'] = 'legacy'
        response = TestClient(app).get(path, params={'symbol':'A', 'method':method,
            'decision_time':(cfg.validation_from+timedelta(seconds=50)).isoformat()})
        assert 'Full trace unavailable' in response.json()['reason']
        assert 'trace' not in response.json()
