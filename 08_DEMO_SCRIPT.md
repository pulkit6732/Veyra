# 120-second live script (target product; not yet built)

**0–15s START STATE:** Open authenticated warehouse/order page. Bin A / high-value S: ledger 10; a witnessed count 10 at event version 0. Order #P-9 requests 9. State explicitly: recorded quantity alone does not ensure a safe pick.

**15–35s USER ACTION:** In another session RECEIVE 2 units into bin A (movement #R1). Recorded on-hand **12**. Submit order #P-9 for delivery of 9. No physical reconfirmation yet.

**35–55s SYSTEM REASONING:** Gate evaluates source `(S,A)`: recorded 12 ≥ 9, but last observation was at version 0, relevant receipt #R1 advanced version to 1. Explain only this fact; do not allege missing goods.

**55–75s SURPRISE:** Server **blocks** the real delivery despite sufficient digital stock; shows `STALE_EVIDENCE`, event #R1, and the *one* required action: count S at A. No stock movement for #P-9 exists.

**75–100s ACTION:** Counter physically enters synthetic observed 12 (in demo seed, declared synthetic) and witness ID at version 1. Retry #P-9; gate reevaluates, allows one commit, writes DELIVERY 9, recorded remainder 3. Count becomes stale for any subsequent guarded operation because delivery changed stock; explain policy cost.

**100–120s MEASURABLE OUTCOME:** Show one previously blocked order now delivered, zero duplicate delivery events, reason/version/event evidence on both decisions, one targeted recount rather than a warehouse-wide count. This is **not** proof of real-world loss reduction. Optional 15s challenge: inject another transfer during count; cannot release on stale snapshot.

**Fallback:** If real delivery hook is not integrated, honestly label the screen a local simulation and do not imply that a pick was prevented. The `K` probe scenario in `06_LOCAL_SCENARIO_RESULTS.json` exercises the 10→12, 9-unit order path in memory; it does not verify the UI/server demo.
