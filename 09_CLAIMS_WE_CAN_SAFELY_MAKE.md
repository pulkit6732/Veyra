# Safe claims (scope must accompany each)

- “Physical-vs-recorded inventory reconciliation, cycle counts and exception review already exist in major systems.” [S1–S6 in 01_COMPETITIVE_LANDSCAPE.md]
- “Our proposed demo centers on a *decision at delivery time*, not another discrepancy dashboard.” This is a plan, **not a shipped product claim**.
- “In a deterministic, in-memory synthetic probe, 11 scenarios passed their fixed expectations across cause-label, count-queue and evidence-gate rules.” `python run_scenarios.py`, `06_LOCAL_SCENARIO_RESULTS.json`. No production integration or concurrency tested.
- “A stale count can be detected using a source-bin/SKU ledger event sequence, and can trigger a policy hold for high-value orders.” Valid as implemented in *research probe*; actual system needs transactional enforcement.
- “No unique patented mechanism is asserted. We did not verify whether SAP, NetSuite, RGIS or Oruvo implements an equivalent delivery gate.”
- “A physical count is fallible; evidence-bound means traceable to a snapshot, not guaranteed correct.”
- “This directory contained no existing Veyra implementation or documents when inspected. Challenge substrate and stack remain unverified.”
