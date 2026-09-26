"""Run independent, fixed expectations against the research-only probe."""
import json
from research_probe import Ledger, choose_count, hypotheses


def run(name):
    l = Ledger({('S', 'A'): 10})
    extra = {}
    order = {'sku': 'S', 'location': 'A', 'qty': 4, 'high_value': True}
    if name == 'A':
        l.observe('S', 'A', 10, witness='counter-1')
        expected = ('ALLOW', 'VERIFIED_AT_CURRENT_VERSION')
    elif name == 'B':
        l.observe('S', 'A', 8, witness='counter-1')
        expected = ('BLOCK', 'CONFLICTING_EVIDENCE')
    elif name == 'C':
        l.observe('S', 'A', 0, witness='counter-1')
        l.observe('S', 'B', 10, witness='counter-2')
        extra['other_location_result'] = l.decide('S', 'B', 1, high_value=True)
        expected = ('BLOCK', 'CONFLICTING_EVIDENCE')
    elif name == 'D':
        l.observe('S', 'A', 10, witness='counter-1')
        l.move('DELIVER', 'S', 2, source='A', ref='sale-1')
        expected = ('BLOCK', 'STALE_EVIDENCE')
    elif name == 'E':
        l.stock[('S', 'A')] = 5
        extra['first_adjustment'] = l.move('ADJUST_PLUS', 'S', 2, source='A', ref='adj-7')
        extra['duplicate_accepted'] = l.move('ADJUST_PLUS', 'S', 2, source='A', ref='adj-7')
        l.observe('S', 'A', 7, witness='counter-1')
        expected = ('ALLOW', 'VERIFIED_AT_CURRENT_VERSION')
    elif name == 'F':
        l.observe('S', 'A', 10, witness='counter-1')
        l.observe('S', 'A', 9, witness='counter-2')
        expected = ('BLOCK', 'CONFLICTING_COUNTS')
    elif name == 'G':
        l.observe('S', 'A', 8, witness='counter-1')
        expected = ('BLOCK', 'CONFLICTING_EVIDENCE')
    elif name == 'H':
        expected = ('BLOCK', 'NO_EVIDENCE')
    elif name == 'I':
        l.observe('S', 'A', 8, witness='counter-1')
        order['qty'] = 9
        expected = ('BLOCK', 'CONFLICTING_EVIDENCE')
    elif name == 'J':
        l.observe('S', 'A', 10, witness='counter-1')
        l.move('DELIVER', 'S', 2, source='A', ref='sale-1')
        extra['before_recount'] = l.decide(**order)
        l.observe('S', 'A', 8, witness='counter-2')
        expected = ('ALLOW', 'VERIFIED_AT_CURRENT_VERSION')
    elif name == 'K':  # exact high-stock but stale demo path
        order['qty'] = 9
        l.observe('S', 'A', 10, witness='counter-1')
        l.move('RECEIVE', 'S', 2, target='A', ref='receipt-1')
        extra['before_recount'] = l.decide(**order)
        extra['digital_balance_at_block'] = l.stock[('S', 'A')]
        l.observe('S', 'A', 12, witness='counter-2')
        expected = ('ALLOW', 'VERIFIED_AT_CURRENT_VERSION')
    else:
        raise ValueError(name)
    actual = l.decide(**order)
    cause_labels = hypotheses(l, 'S', 'A')
    rank = choose_count(l, [order])
    expected_cause = {'A': 'NO_GAP_OBSERVED', 'B': 'UNEXPLAINED_GAP',
                      'C': 'UNEXPLAINED_GAP', 'D': 'STALE_COUNT',
                      'E': 'NO_GAP_OBSERVED', 'F': 'UNEXPLAINED_GAP',
                      'G': 'UNEXPLAINED_GAP', 'H': 'NO_PHYSICAL_EVIDENCE',
                      'I': 'UNEXPLAINED_GAP', 'J': 'NO_GAP_OBSERVED',
                      'K': 'NO_GAP_OBSERVED'}[name]
    expected_ranked = name not in ('A', 'E', 'J', 'K')
    mechanism_checks = {
        'candidate_1_classification': expected_cause in cause_labels,
        'candidate_2_priority': bool(rank) == expected_ranked,
        'candidate_3_evidence_gate': (actual['decision'], actual['reason']) == expected,
    }
    checks = list(mechanism_checks.values())
    if name == 'C':
        checks.append(extra['other_location_result']['reason'] == 'NOT_ENOUGH_RECORDED')
    if name == 'E':
        checks.append(extra['first_adjustment'] is True and extra['duplicate_accepted'] is False and l.stock[('S','A')] == 7)
    if name == 'F':
        checks.append(l.observations[('S','A')]['prior']['physical'] == 10)
    if name == 'G':
        checks.append('UNRECORDED_MOVEMENT_POSSIBLE' in hypotheses(l, 'S', 'A'))
    if name in ('J', 'K'):
        checks.append(extra['before_recount']['reason'] == 'STALE_EVIDENCE')
    if name == 'K':
        checks.append(extra['digital_balance_at_block'] >= order['qty'])
    return {
        'scenario': name, 'input_state': {'initial_sku': 'S', 'initial_location': 'A',
                                          'initial_on_hand': 5 if name == 'E' else 10,
                                          'order': order},
        'events': l.events,
        'physical_observation': l.observations.get(('S', 'A')),
        'expected': {'decision': expected[0], 'reason': expected[1]},
        'actual': actual,
        'candidate_1': {'expected_contains': expected_cause, 'actual': cause_labels,
                        'result': 'PASS' if mechanism_checks['candidate_1_classification'] else 'FAIL'},
        'candidate_2': {'expected_queue_nonempty': expected_ranked, 'actual': rank,
                        'result': 'PASS' if mechanism_checks['candidate_2_priority'] else 'FAIL'},
        'candidate_3': {'result': 'PASS' if mechanism_checks['candidate_3_evidence_gate'] else 'FAIL'},
        'extra': extra,
        'result': 'PASS' if all(checks) else 'FAIL',
        'failure': None if all(checks) else 'expectation or invariant mismatch',
    }


if __name__ == '__main__':
    results = [run(n) for n in 'ABCDEFGHIJK']
    doc = {'scope': 'research-only in-memory probe; not existing product; no UI/DB/API tests',
           'limitations': ['single-process; no concurrent commit/transaction tested',
                           'physical observations synthetic; cannot prove physical truth',
                           'duplicate detection requires stable idempotency ref',
                           'hypotheses are not proven causes',
                           'no multi-SKU orders/lot identity/role auth tested'],
           'summary': {'pass': sum(r['result'] == 'PASS' for r in results),
                       'fail': sum(r['result'] == 'FAIL' for r in results)},
           'scenarios': results}
    with open('06_LOCAL_SCENARIO_RESULTS.json', 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=2)
        f.write('\n')
    print(json.dumps(doc['summary']))
    if doc['summary']['fail']:
        raise SystemExit(1)
