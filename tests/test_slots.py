from app.input import sample
from app.modules.ledger.slots import occupancy, slots
from app.pipeline import compute


def row_for(result, leg):
    return next(r for r in result['ledger']['slots']['rows'] if r['leg'] == leg)


def test_dirty_slots_match_replay_occupancy(dirty):
    table = {r['leg']: r for r in dirty['ledger']['slots']['rows']}
    # NX-01：000101 计划装载（迟到撤下经回放后仍以 LOAD 收尾）+ 000105 错装到此段，共占 2。
    assert (table['NX-01']['occupied'], table['NX-01']['cap'], table['NX-01']['remaining']) == (2, 2, 0)
    assert not table['NX-01']['overbooked']
    # NX-02：000102 计划装载 + 000108 错装，限额 1，超额 1、名额 0。
    assert (table['NX-02']['occupied'], table['NX-02']['remaining'], table['NX-02']['overbooked']) == (2, 0, True)
    assert table['NX-02']['wrong'] == 1
    # JL-08：待证 000106 已占舱、清单外 009999 占舱、000107 同刻装撤未决保守计占。
    jl = table['JL-08']
    assert (jl['occupied'], jl['pending'], jl['unlisted'], jl['conflict']) == (3, 1, 1, 1)
    assert jl['overbooked'] and jl['remaining'] == 0
    # HX-41：000103 航段未决，无采信装载，不占舱，名额等于限额。
    assert (table['HX-41']['occupied'], table['HX-41']['remaining']) == (0, 2)
    # HX-42：000104 回放末态撤下不占舱，仅 000110 在舱。
    assert (table['HX-42']['occupied'], table['HX-42']['remaining']) == (1, 1)


def test_loaded_totals_would_overbook_but_slots_do_not(dirty):
    # 朴素口径只看已装 3 件会在 JL-08 凭空放出名额；回放口径下 JL-08 已超额。
    jl = row_for(dirty, 'JL-08')
    ledger_jl = next(r for r in dirty['ledger']['rows'] if r['leg'] == 'JL-08')
    assert ledger_jl['loaded'] == 0
    assert jl['occupied'] == 3 and jl['cap'] == 2 and jl['remaining'] == 0


def test_late_offload_only_releases_after_replay_confirms(dirty):
    # 000101：迟到撤下 E02（生效 23:55，晚到 00:11）后又有 E03 装载，回放末态 LOADED，仍占 NX-01。
    nx01 = row_for(dirty, 'NX-01')
    assert '000101' in nx01['occupied_tags'] and nx01['remaining'] == 0


def test_confirmed_offload_frees_slot():
    # 构造：计划件先装后撤（正常收件），回放末态 OFFLOADED，应腾出名额。
    files = sample('clean')
    scans = files['scans.csv'] + (
        'C99,000103,HX701,HX-41,OFFLOAD,2026-11-20T23:40:00+08:00,2026-11-20T23:40:00+08:00\r\n'
    )
    result = compute(dict(files, **{'scans.csv': scans}))
    hx41 = row_for(result, 'HX-41')
    assert hx41['occupied'] == 1 and hx41['remaining'] == 1


def test_rerun_is_idempotent_no_double_release(desk):
    first = desk.post('/api/archive', json={'sample': 'dirty'}).json
    again = desk.post(f"/api/archive/{first['id']}/rerun").json
    assert again['id'] == first['id'] and again['reused']
    stored = desk.get(f"/api/archive/{first['id']}").json
    slots_once = compute(sample('dirty'))['ledger']['slots']
    assert stored['manifest']['result_sha256'] == first['manifest']['result_sha256']
    assert desk.get('/api/stage/ledger').json['slots'] == slots_once


def test_clean_sample_has_no_overbooking():
    rows = compute(sample('clean'))['ledger']['slots']['rows']
    assert all(not r['overbooked'] for r in rows)
    assert sum(r['occupied'] for r in rows) == 12


def test_occupancy_helpers_on_synthetic_states():
    legs = {'L1': dict(leg='L1', destination='X', cap=2)}
    manifest = {'A': dict(tag='A', planned='L1'), 'B': dict(tag='B', planned='L9')}
    states = [
        dict(tag='A', leg='L1', state='LOADED', source_lines=[]),
        dict(tag='B', leg='L1', state='LOADED', source_lines=[]),       # 错装占实际航段
        dict(tag='C', leg='L1', state='LOADED', source_lines=[]),       # 清单外
        dict(tag='D', leg='L1', state='CONFLICT', source_lines=[]),     # 未决保守计占
        dict(tag='E', leg='L1', state='OFFLOADED', source_lines=[]),    # 已撤不占
    ]
    decisions = dict(rows=[
        dict(tag='A', status='loaded'), dict(tag='B', status='pending'),
        dict(tag='C', status='unlisted'), dict(tag='D', status='pending'),
        dict(tag='E', status='not_loaded'),
    ])
    bucket = occupancy(states, manifest, decisions['rows'])['L1']
    assert (bucket['planned'], bucket['wrong'], bucket['unlisted'], bucket['conflict'], bucket['occupied']) == (1, 1, 1, 1, 4)
    table = slots(legs, states, manifest, decisions['rows'])['rows'][0]
    assert table['remaining'] == 0 and table['overbooked']
