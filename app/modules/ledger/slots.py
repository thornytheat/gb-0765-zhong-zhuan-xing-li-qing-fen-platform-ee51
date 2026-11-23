"""减载后补装名额。

名额必须按航段回放确认的末态占用计算，不能直接拿已装件数：待证行李可能已经占舱、
错装件占的是实际航段、迟到撤下只有回放确认后才腾舱。计算是输入的纯函数，补传批次
重跑得到同一结果，因此名额不会被重复释放。
"""

# 回放末态仍占舱的状态：LOADED 明确装载；CONFLICT 同刻装撤未决，保守计占以防超额。
OCCUPYING_STATES = {'LOADED', 'CONFLICT'}


def occupancy(states, manifest, decisions):
    """按 (行李牌, 航段) 末态汇总每个航段的实际占用件数及构成。"""
    planned_of = {tag: row['planned'] for tag, row in manifest.items()}
    status_of = {row['tag']: row['status'] for row in decisions}
    by_leg = {}
    for state in states:
        if state['state'] not in OCCUPYING_STATES:
            continue
        leg, tag = state['leg'], state['tag']
        bucket = by_leg.setdefault(leg, dict(planned=0, pending=0, wrong=0, unlisted=0, conflict=0, tags=[]))
        bucket['tags'].append(tag)
        if state['state'] == 'CONFLICT':
            # 同刻装撤未决，末态不能确定为撤下，保守计占，待人工裁决前不放名额。
            bucket['conflict'] += 1
            continue
        planned = planned_of.get(tag)
        if planned is None:
            bucket['unlisted'] += 1
        elif planned == leg:
            # 计划段末态装载：已装件与待证件都占舱，待证不能当作空位放名额。
            bucket['pending' if status_of.get(tag) == 'pending' else 'planned'] += 1
        else:
            # 非计划段末态装载即错装，占用的是实际航段而非计划航段。
            bucket['wrong'] += 1
    for bucket in by_leg.values():
        bucket['tags'] = sorted(bucket['tags'])
        bucket['occupied'] = (bucket['planned'] + bucket['pending'] + bucket['wrong']
                              + bucket['unlisted'] + bucket['conflict'])
    return by_leg


def slots(legs, states, manifest, decisions):
    """结合减载限额与航段回放占用，报出每航段可补装名额。"""
    occupied = occupancy(states, manifest, decisions)
    rows = []
    for leg, leg_row in sorted(legs.items()):
        bucket = occupied.get(leg, dict(planned=0, pending=0, wrong=0, unlisted=0, conflict=0,
                                        occupied=0, tags=[]))
        cap = leg_row['cap']
        remaining = cap - bucket['occupied']
        rows.append(dict(
            leg=leg, destination=leg_row['destination'], cap=cap,
            occupied=bucket['occupied'], remaining=max(remaining, 0), overbooked=remaining < 0,
            **{key: bucket[key] for key in ('planned', 'pending', 'wrong', 'unlisted', 'conflict')},
            occupied_tags=bucket['tags'],
        ))
    totals = dict(cap=sum(row['cap'] for row in rows),
                  occupied=sum(row['occupied'] for row in rows),
                  remaining=sum(row['remaining'] for row in rows),
                  overbooked=sum(1 for row in rows if row['overbooked']))
    return dict(rows=rows, totals=totals)
