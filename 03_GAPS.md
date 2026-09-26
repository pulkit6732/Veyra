# Gap between a recorded balance and a safe action

An ERP records **10 at bin A**; a picker needs **9 now**. An independent counter saw **8** before a transfer, or two counters disagree, or the last count predates a movement. The balance alone is not evidence that the pick is safe. In a typical workflow someone checks chronology, locates the bin, chooses a recount, decides whether to hold or release and explains the override. This human decision burden is the relevant problem; NOT all ERPs lack holds, recounts or workflows.

| Hypothesis | Existing coverage / evidence | Unmet decision we can actually test | Missing evidence → smallest action |
|---|---|---|---|
| Uncertainty/location confidence | Dexory and Gather [S5,S6] cover physical discrepancy/visibility | Which imminent order must pause? | Count *source SKU+bin*, not whole warehouse |
| Timing/stale evidence | Odoo count dates [S1], Dynamics recurring work [S3]; exact version semantics unknown | Was this count taken before a later movement? | Bind observation to ledger version; invalidate on relevant movement |
| Conflicting evidence/chain of custody | Count workers and review [S1,S3] | Can a supervisor safely release despite disagreeing witnesses? | Preserve both records; require witnessed adjudication |
| Verification priority/scheduling | Already covered substantially [S2,S3,S6] | Which check restores the currently blocked order? | Gate returns exact SKU/bin and relevant order; not generic risk score |
| Exception propagation/downstream consequences | Integrity recommendations [S5,S6]; exact pick gate unverified | Does a variance affect a real pick *before* commit? | Enforce a rule at order confirmation and commit, not just email |
| Recurrence/prevention | Related [S5,S6] | Does a fixed record stop repeated errors? | Later analytics; no defensible mechanism today |
| Cross-system evidence | Dexory API-first WMS matching [S5] | Which source is authoritative? | Roadmap: source identity/version/latency; not MVP |

**Regeneration cycle 1:** From `display variance → human infers consequence` to `imminent pick → version-bound evidence check → block/recount/release`. Re-attack: WMS configurable holds and cycle count are related; no novelty monopoly. The useful demonstrable combination is *synchronous decision-time evidence gate with staleness replay*. Stop at this one cycle: further ideation cannot compensate for missing substrate/integration evidence.

**Critical falsifier:** if the available stack cannot intercept an actual delivery commit, this is just a warning screen. Then first build the mandatory system well; do not pitch the warning as an enforced gate.
