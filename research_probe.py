"""Research-only deterministic probe; NOT wired into Veyra or a WMS."""
from dataclasses import dataclass, field


@dataclass
class Ledger:
    stock: dict
    seq: int = 0
    events: list = field(default_factory=list)
    observations: dict = field(default_factory=dict)
    refs: set = field(default_factory=set)

    def move(self, kind, sku, qty, source=None, target=None, ref=None):
        if not isinstance(qty, int) or qty <= 0:
            raise ValueError('positive integer quantity required')
        if ref and ref in self.refs:
            return False  # idem-key duplicate does not create another adjustment
        if kind not in ('RECEIVE', 'DELIVER', 'TRANSFER', 'ADJUST_PLUS', 'ADJUST_MINUS'):
            raise ValueError('unknown movement')
        changes = []
        if kind in ('DELIVER', 'TRANSFER', 'ADJUST_MINUS'):
            changes.append(((sku, source), -qty))
        if kind in ('RECEIVE', 'TRANSFER', 'ADJUST_PLUS'):
            changes.append(((sku, target if kind in ('RECEIVE', 'TRANSFER') else source), qty))
        for key, delta in changes:
            if self.stock.get(key, 0) + delta < 0:
                raise ValueError('insufficient stock')
        for key, delta in changes:
            self.stock[key] = self.stock.get(key, 0) + delta
        self.seq += 1
        self.events.append({'seq': self.seq, 'kind': kind, 'sku': sku, 'qty': qty,
                            'source': source, 'target': target, 'ref': ref})
        if ref:
            self.refs.add(ref)
        return True

    def observe(self, sku, location, physical, at_seq=None, witness=None, resolve_conflict=False):
        if not isinstance(physical, int) or physical < 0:
            raise ValueError('nonnegative integer count required')
        if at_seq is None:
            at_seq = self.seq
        if at_seq > self.seq or at_seq < 0:
            raise ValueError('invalid snapshot version')
        key = (sku, location)
        prior = self.observations.get(key)
        conflicting = (not resolve_conflict and prior is not None and
                       (prior.get('conflicting', False) or
                        (prior['seq'] == at_seq and prior['physical'] != physical)))
        self.observations[key] = {'physical': physical, 'seq': at_seq,
                                  'witness': witness, 'conflicting': conflicting,
                                  'prior': prior}

    def relevant_after(self, sku, location, at_seq):
        return [e for e in self.events if e['seq'] > at_seq and e['sku'] == sku
                and location in (e['source'], e['target'])]

    def decide(self, sku, location, qty, high_value=False):
        key = (sku, location)
        digital = self.stock.get(key, 0)
        obs = self.observations.get(key)
        if qty > digital:
            return {'decision': 'BLOCK', 'reason': 'NOT_ENOUGH_RECORDED', 'action': 'investigate_stock'}
        if not obs:
            if high_value:
                return {'decision': 'BLOCK', 'reason': 'NO_EVIDENCE', 'action': f'count {sku}@{location}'}
            return {'decision': 'ALLOW', 'reason': 'POLICY_LOW_VALUE', 'action': 'deliver'}
        if obs['conflicting']:
            return {'decision': 'BLOCK', 'reason': 'CONFLICTING_COUNTS',
                    'action': f'supervisor recount {sku}@{location}'}
        moved = self.relevant_after(sku, location, obs['seq'])
        if moved:
            return {'decision': 'BLOCK', 'reason': 'STALE_EVIDENCE', 'action': f'recount {sku}@{location}',
                    'causal_event_seqs': [e['seq'] for e in moved]}
        if obs['physical'] != digital:
            return {'decision': 'BLOCK', 'reason': 'CONFLICTING_EVIDENCE',
                    'action': f'investigate and recount {sku}@{location}',
                    'gap': obs['physical'] - digital}
        return {'decision': 'ALLOW', 'reason': 'VERIFIED_AT_CURRENT_VERSION', 'action': 'deliver',
                'evidence_seq': obs['seq']}


def choose_count(ledger, orders):
    """Candidate 2: deterministic pick-impact priority; no claim of optimal info gain."""
    ranked = []
    for o in orders:
        result = ledger.decide(**o)
        if result['decision'] == 'BLOCK':
            ranked.append((o['qty'] * (10 if o.get('high_value') else 1), o['sku'],
                           o['location'], result['reason']))
    ranked.sort(key=lambda x: (-x[0], x[1], x[2]))
    return ranked


def hypotheses(ledger, sku, location):
    """Candidate 1: classify only; NEVER assert a root cause from a quantity gap."""
    obs = ledger.observations.get((sku, location))
    if not obs:
        return ['NO_PHYSICAL_EVIDENCE']
    if ledger.relevant_after(sku, location, obs['seq']):
        return ['STALE_COUNT', 'MOVEMENT_DURING_VERIFICATION_POSSIBLE']
    if obs['physical'] != ledger.stock.get((sku, location), 0):
        return ['UNEXPLAINED_GAP', 'LOCATION_ERROR_POSSIBLE', 'UNRECORDED_MOVEMENT_POSSIBLE']
    return ['NO_GAP_OBSERVED']
