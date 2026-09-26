# Five hostile judges; no free passes

Candidates: C1 cause classifier (KILL); C2 ranked counts (KILL standalone); C3 version-bound pick gate (conditional survivor). Questions applied **to each candidate**, not assumed passed. Roles A operations, B engineer, C startup/product, D ERP/WMS expert, E innovation. Tags K=kill, W=weak, S=survives if delivered.

| Judge / attack | C1 | C2 | C3 |
|---|---|---|---|
| D/E 1. Seen it before; why different? | K: exception/review + suggestions [S3,S5] | K: directed/prioritized work [S3,S6] | W: specifically binding physical evidence to imminent commit; custom WMS could add it |
| B/E 2. Demonstrate it? | W: labels, no proven cause | W: queue reorder | S: sufficient stock → stale-count hold → recount → release |
| B 3. Data from? | Movement and count; cannot prove cause | Orders, counts, value policy; weights arbitrary | Versioned events, count, bin/SKU, order; if absent cannot demo |
| D 4. Odoo with nicer UI? | K: effectively yes [S1] | K: likely [S2,S3] | W: only if decision changes real commit; UI warning alone is yes |
| B/E 5. LLM wrapper? | W: if prose, yes; deterministic labels safer | S: deterministic, but commodity | S: deterministic gate; no LLM |
| A 6. Warehouse need? | W: explanations may shorten review | W: prioritization helpful, already available | S: do not pick from unverified bin; high-value rule reduces short-pick risk at cost of holds |
| A/B 7. Incomplete evidence? | W: UNKNOWN not theft | W: unknown may be counted first, not truth | S: guarded order held; low-value bypass explicitly labeled policy |
| B 8. Reproducible? | S: rule labels repeatable, not causal | S: deterministic sort, not optimality | S: snapshot + policy + event IDs reproduce decision; tests 11/11 in probe only |
| A/B 9. Movement during verification? | W: naive timeline mislabels | W: ranking becomes stale | S: count binds start version; relevant movement invalidates; transaction rechecks at commit (not yet tested) |
| A/B 10. Explanation wrong? | K: cannot substantiate causal claim | W: weight heuristic misleading | S: reason limited to checkable facts; supervisor can override with recorded rationale, not guessed cause |
| B 11. Technical difficulty? | K: simple classifier | K: trivial weighted sort | S: atomic race-free multi-line reservation and version check; not implemented in probe |
| D/C 12. Why can't incumbents add it? | K: they do related work | K: many already do | W: they can. Advantage is small, demonstrated integration for this challenge, not structural moat |

**Judgment:** C3 passes only as an *operationally observable decision*, not a novelty claim. Its hardest question (9) fails until a real transaction-level hook and concurrency test exist. If existing code is absent (as in this directory), shortage of time threatens challenge compliance; judge score must be conditional, not marketed as a shipped system.
