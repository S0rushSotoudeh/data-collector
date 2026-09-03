from datetime import datetime, timedelta, timezone
import uuid

import numpy as np
import pytest

from src.analytics.gold_consensus import canonical_events, reconstruct, calibrate, filter_grid, outcome_arrays, peer_medians
from src.analytics.gold_consensus_config import GoldKalmanRunConfig


def config(**kwargs):
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    return GoldKalmanRunConfig(dataset_id=uuid.UUID(int=1), symbols=['A','B','C','D'],
        history_from=now, validation_from=now+timedelta(days=3), validation_to=now+timedelta(days=4),
        test_from=now+timedelta(days=5), test_to=now+timedelta(days=6),
        **({'min_calibration_observations':3, 'warmup_seconds':2, 'max_quote_age':3} | kwargs))


def events(seconds=200, n=4, seed=42, start=0):
    rng = np.random.default_rng(seed)
    factor = np.cumsum(rng.normal(0, .0001, seconds))
    output = {}
    for j in range(n):
        mid = (100+j*30)*np.exp(factor+rng.normal(0,.001,seconds))
        t=np.arange(seconds,dtype=float)+start
        output[chr(65+j)] = np.column_stack([t,t,np.arange(seconds),mid-.05,mid+.05,
                                            np.full(seconds,10),np.full(seconds,12),np.ones(seconds)])
    return output


def grid(raw=None, end=200):
    return reconstruct(raw or events(end), ['A','B','C','D'], np.arange(end), 0,end,3,{'A','B','C','D'})


def test_peer_medians_matches_brute_force():
    rng=np.random.default_rng(2)
    for n in range(3,40):
        values=rng.integers(0,10,n)
        np.testing.assert_allclose(peer_medians(values),[np.median(np.delete(values,i)) for i in range(n)])


def test_canonical_duplicates_conflicts_order():
    rows=events(5)['A']
    np.testing.assert_array_equal(canonical_events(np.vstack([rows[::-1],rows])),rows)
    changed=rows.copy();changed[0,3]+=1
    with pytest.raises(ValueError,match='conflicting'):
        canonical_events(np.vstack([rows,changed]))
    changed=rows.copy();changed[0,1]=1
    with pytest.raises(ValueError,match='future'):
        canonical_events(changed)


def test_invalidating_change_cached_stale_and_no_future_backfill():
    raw=events(10)
    raw['A']=raw['A'][[2,4,6]]
    raw['A'][1,3]=0
    raw['A'][2,7]=0
    g=grid(raw,10)
    assert not g.valid[:2,0].any()
    assert g.valid[2:4,0].all()
    assert not g.valid[4:,0].any()
    assert not g.new[3,0]
    raw['A']=raw['A'][:1]
    g=grid(raw,10)
    assert not g.valid[6:,0].any()


def test_calibration_past_only_and_zero_mad_rejected():
    cfg=config();g=grid();fit=calibrate([g],cfg.symbols,cfg)
    assert fit['available'] and fit['q']>0 and len(fit['symbols'])==4
    raw=events()
    for value in raw.values():value[:,3:7]=[100,101,10,10]
    fit=calibrate([grid(raw)],cfg.symbols,cfg)
    assert not fit['available']


def test_score_before_update_and_prefix_invariance():
    cfg=config(warmup_seconds=0)
    fit=calibrate([grid()],cfg.symbols,cfg)
    raw=events(seed=30);g=grid(raw);original=filter_grid(g,cfg.symbols,fit,cfg)
    edited={s:r.copy() for s,r in raw.items()};edited['A'][50,3:5]*=1.01
    changed=filter_grid(grid(edited),cfg.symbols,fit,cfg)
    assert original['fair'][50,0] == pytest.approx(changed['fair'][50,0])
    assert original['z'][50,0] != changed['z'][50,0]
    np.testing.assert_allclose(original['z'][:50],changed['z'][:50],equal_nan=True)
    prefix=filter_grid(grid({s:r[:100] for s,r in raw.items()},100),cfg.symbols,fit,cfg)
    np.testing.assert_allclose(original['z'][:100],prefix['z'],equal_nan=True)
    assert np.isnan(original['z'][0]).all()


def test_prediction_only_does_not_reduce_variance_and_warmup():
    cfg=config(warmup_seconds=3,max_quote_age=100)
    fit=calibrate([grid()],cfg.symbols,cfg)
    raw={s:r[:1] for s,r in events(20).items()}
    g=reconstruct(raw,cfg.symbols,np.arange(20),0,20,cfg.max_quote_age,set(cfg.symbols));out=filter_grid(g,cfg.symbols,fit,cfg)
    assert np.all(np.diff(out['market'][:,1])>0)
    assert np.isnan(out['z'][:3]).all()
    assert np.isfinite(out['z'][3:]).all()


def test_mid_session_reset_and_exact_horizon_missing_peer():
    cfg=config(warmup_seconds=0)
    raw=events();fit=calibrate([grid()],cfg.symbols,cfg)
    g=reconstruct(raw,cfg.symbols,np.arange(50,100),50,100,3,set(cfg.symbols))
    out=filter_grid(g,cfg.symbols,fit,cfg)
    assert np.isnan(out['z'][0]).all()
    endpoint=reconstruct(raw,cfg.symbols,g.times+1.5,50,100,3,set(cfg.symbols))
    labels=outcome_arrays(g,endpoint,out,1.5,100,set(cfg.symbols),cfg.symbols)
    assert not labels['available'][-1].any()
    endpoint.valid[10,2]=False
    missing=outcome_arrays(g,endpoint,out,1.5,100,set(cfg.symbols),cfg.symbols)
    assert not missing['available'][10].any()


def test_persistent_step_is_not_price_recovery():
    cfg=config(warmup_seconds=0)
    raw=events();fit=calibrate([grid()],cfg.symbols,cfg)
    for r in raw.values():r[:,3:5]=r[0,3:5]
    raw['A'][20:,3:5]*=1.02
    g=grid(raw);out=filter_grid(g,cfg.symbols,fit,cfg)
    endpoint=reconstruct(raw,cfg.symbols,g.times+5,0,200,3,set(cfg.symbols))
    labels=outcome_arrays(g,endpoint,out,5,200,set(cfg.symbols),cfg.symbols)
    assert labels['recovery'][30,0]==pytest.approx(0)
    raw['A'][35:,3:5]/=1.02
    endpoint=reconstruct(raw,cfg.symbols,g.times+5,0,200,3,set(cfg.symbols))
    labels=outcome_arrays(g,endpoint,out,5,200,set(cfg.symbols),cfg.symbols)
    assert labels['recovery'][30,0]>0


def test_config_validation_and_locked_policy_hash():
    cfg=config()
    with pytest.raises(ValueError):config(k=0)
    with pytest.raises(ValueError):config(kalman_half_life_seconds=float('nan'))
    test=cfg.model_copy(update={'mode':'test','validation_run_id':uuid.uuid4()})
    assert test.policy_hash()==cfg.policy_hash()
    assert cfg.model_copy(update={'max_quote_age':2}).policy_hash()!=cfg.policy_hash()


def test_template_compiles_and_navigation():
    from src.admin._render import _TEMPLATE_ENV
    from src.admin.gold.consensus_views import GoldKalmanView,GoldKalmanRunsView
    from pathlib import Path
    _TEMPLATE_ENV.get_template('gold/kalman.html')
    assert GoldKalmanView.category==GoldKalmanRunsView.category=='Gold Analytics'
    source=Path('src/admin/__init__.py').read_text()
    assert source.index('admin.add_view(GoldBestQuotesChartView)')<source.index('admin.add_view(GoldKalmanView)')<source.index('admin.add_view(GoldKalmanRunsView)')


def test_phase_and_insufficient_coverage_reset_persistence():
    cfg=config(z_alert=.000001,warmup_seconds=0)
    fit=calibrate([grid()],cfg.symbols,cfg)
    raw=events()
    raw['A'][30:40,7]=2
    raw['B'][30:40,7]=3
    g=grid(raw);out=filter_grid(g,cfg.symbols,fit,cfg)
    assert (g.phases[30:40,0]==2).all()
    assert np.isnan(out['z'][30:40]).all()
    assert np.nanmax(out['persistence'][40])==1


def test_quantity_only_change_has_no_midpoint_recovery():
    cfg=config(warmup_seconds=0)
    raw=events();fit=calibrate([grid()],cfg.symbols,cfg)
    for r in raw.values():r[:,3:5]=r[0,3:5]
    raw['A'][30:,5]*=10
    g=grid(raw);out=filter_grid(g,cfg.symbols,fit,cfg)
    endpoint=reconstruct(raw,cfg.symbols,g.times+5,0,200,3,set(cfg.symbols))
    labels=outcome_arrays(g,endpoint,out,5,200,set(cfg.symbols),cfg.symbols)
    assert g.new[30,0]
    np.testing.assert_allclose(labels['recovery'][25:35],0)


def test_calibration_exclusion_recalculates_final_peer_support():
    cfg=config(min_calibration_observations=20)
    raw=events();raw['D']=raw['D'][:2]
    fit=calibrate([grid(raw)],cfg.symbols,cfg)
    assert fit['available'] and fit['symbols']==['A','B','C']
    assert fit['exclusions']['D']=='insufficient_distinct_observations'
    raw['C']=raw['C'][:2]
    assert not calibrate([grid(raw)],cfg.symbols,cfg)['available']


def test_reference_half_life_equation_and_grid_time_weighting():
    cfg=config();fit=calibrate([grid()],cfg.symbols,cfg)
    gain=1-2**(-fit['delta_ref']/cfg.kalman_half_life_seconds)
    assert fit['q']==pytest.approx(fit['r_ref']*gain**2/((1-gain)*fit['delta_ref']))
    raw={s:canonical_events(np.repeat(r,3,axis=0)) for s,r in events().items()}
    repeated=calibrate([grid(raw)],cfg.symbols,cfg)
    assert repeated==fit


def test_scalar_update_matches_hand_calculation():
    cfg=config(warmup_seconds=0)
    fit={'available':True,'symbols':cfg.symbols,'alpha':[0]*4,'r':[.01]*4,'q':.001}
    g=grid(events(3),3);out=filter_grid(g,cfg.symbols,fit,cfg)
    initial=np.mean(np.log(g.micro[0]));prior_variance=1/400+.001
    expected_variance=1/(1/prior_variance+400)
    expected_factor=expected_variance*(initial/prior_variance+100*np.log(g.micro[1]).sum())
    assert out['market'][1,0]==pytest.approx(expected_factor)
    assert out['market'][1,1]**2==pytest.approx(expected_variance)
    excluded_variance=1/(1/prior_variance+300)
    excluded_factor=excluded_variance*(initial/prior_variance+100*np.log(g.micro[1,1:]).sum())
    assert out['fair'][1,0]==pytest.approx(np.exp(excluded_factor))


def test_overshoot_and_common_shock_outcomes():
    from src.analytics.gold_consensus import Grid
    books=np.array([[[100.9,101.1,10,10],[99.9,100.1,10,10],[99.9,100.1,10,10]]])
    flags=np.ones((1,3),dtype=bool)
    g=Grid(np.array([1]),books,np.ones((1,3)),flags,flags,np.ones((1,3)))
    future=books.copy();future[0,0,:2]-=4
    endpoint=Grid(np.array([2]),future,np.ones((1,3)),flags,flags,np.ones((1,3)))
    scores={'z':np.ones((1,3)),'delta':np.ones((1,3))*.01,'fair':np.ones((1,3))*100}
    labels=outcome_arrays(g,endpoint,scores,1,3,{'A','B','C'},['A','B','C'])
    assert labels['recovery'][0,0]>0 and labels['reduction'][0,0]<0
    endpoint.books=books.copy();endpoint.books[:,:,:2]*=1.1
    labels=outcome_arrays(g,endpoint,scores,1,3,{'A','B','C'},['A','B','C'])
    np.testing.assert_allclose(labels['recovery'],0,atol=1e-10)
