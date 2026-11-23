from .slots import slots
from .tally import totals


def reconcile(decisions, legs, scan_counts, replay_states=None, manifest=None):
    rows, wrong = decisions['rows'], decisions['wrong']
    counts = totals(rows, wrong)
    by_leg = [dict(leg=leg, destination=leg_row['destination'], **totals(
        [row for row in rows if row['planned'] == leg], [row for row in wrong if row['planned'] == leg]
    )) for leg, leg_row in sorted(legs.items())]
    balance = counts['manifest'] - counts['loaded'] - counts['pending'] - counts['not_loaded']
    result = dict(counts=counts, balanced=balance == 0 and scan_counts['balanced'],
                  difference=balance, rows=by_leg)
    # 减载补装名额：回放末态占用对减载限额，见 app/modules/ledger/slots.py。
    if replay_states is not None and manifest is not None:
        result['slots'] = slots(legs, replay_states, manifest, rows)
    return result
