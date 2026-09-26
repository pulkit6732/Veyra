# Current Veyra thesis: kill decision

**KILLED:** “inventory integrity + physical reconciliation + event/root-cause analysis is our unique core.” Odoo already handles discrepancy/count adjustment [S1,S2], Dynamics handles count work and difference review [S3], and Dexory markets continuous physical-vs-WMS integrity, SKU/location reconciliation and explainable suggestions [S5]. Root-cause *quality* remains unclear, but uniqueness of the broad bundle is indefensible. Current `DEFINE → IDENTIFY → VERIFY → COMPARE → CLASSIFY → TRACE → EXPLAIN → RESOLVE → RECORD` is workflow packaging, not a technical moat. An event timeline and guessed causes are especially vulnerable to “show me the proof.”

**Retain** required substrate and any working flows **if found**; none were present in this directory. The user's described existing demo is an *assertion*, not observed functionality. Do not delete code on this finding.

Legend: K = known comparable implementation; R = related/partially covered; U = unclear exact analogue. “30s” assesses a distinct judge-visible action, not ease of describing the incumbent. “Build” assumes available movement ledger and SKU/bin records; this prerequisite has NOT been verified.

| Idea | Prior art | Beyond terminology/UI? | 30s / build in 6h / measurable value | Verdict |
|---|---|---|---|---|
| A Blind physical counting | R: count/mobile workflows [S1,S3], blind mode unverified | No obvious distinction | No / Yes / fewer biased counts possible | KILL as innovation; optionally keep count input |
| B Physical-vs-digital reconciliation | K [S1,S5] | No | No / Yes / detects variances | KILL |
| C Discrepancy investigation | K/R: pending review [S3], integrity suggestions [S5] | Only if intervention changes | Weak / Yes / potential time saved | KILL as standalone |
| D Event timeline | R [S4,S5]; transaction history is ordinary WMS | UI only | No / Yes / traceability | KILL as innovation |
| E Root-cause hypotheses | R [S5] | Unproven without discriminatory evidence | Weak / Yes (labels) / weak | KILL; never label a guess a cause |
| F Resolution workflow | K [S1,S3] | No | No / Yes / closed cases | KILL as innovation |
| G Audit trail | K/R [S1,S3,S4] | No | No / Yes / accountability | KILL as innovation, keep required logs |
| H Warehouse accuracy score | R [S5,S6] | Score without denominator/ground truth is decoration | No / Yes / unreliable | KILL |
| I Inventory trust/confidence | R [S5,S6] | A made-up probability is UI | No / Yes / uncalibrated | KILL score; binary evidence state may survive |
| J Verification debt | R [S2,S3,S6] | Mostly renaming overdue count work | No / Yes / prioritizes work | KILL |
| K Event-driven verification | K/R threshold-generated counts [S3], proactive [S5] | Trigger-at-decision could matter | Yes / Yes / avoided bad picks | SUBSUME under conditional gate, not unique |
| L Next-best verification | K/R ranked work [S3,S6] | Only if minimum check unblocks a real order | Yes / Yes / reduced wasted checks | KILL standalone; use as gate's action |
| M Predictive discrepancy prevention | R [S5,S6] | No model/evidence available | No / No / unvalidated | ROADMAP ONLY, not pitch |
| N Continuous inventory integrity | K [S5,S6] | No | No / No without sensors / potentially high | KILL |
| O Cross-system reconciliation | K [S5] | No; requires integration | No / No / valuable | KILL for hackathon |

Rule applied: being implementable or valuable does not restore a feature's claim to differentiation. Source IDs: [01_COMPETITIVE_LANDSCAPE.md](01_COMPETITIVE_LANDSCAPE.md).
