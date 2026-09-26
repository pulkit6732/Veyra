# Competitive landscape — adversarial, function-first

**Evidence scope (accessed this session):** the working directory was empty before this research. No supplied Veyra documents, code, schema, or challenge PDF were present. The user's brief is the sole available authoritative challenge description. Live vendor pages below were fetched and read; vendor marketing establishes *claimed capabilities*, not independently verified deployment behavior. Search engines rate-limited or returned unrelated results. We do **not** infer absence of a feature from a missing web hit. SAP product site and NetSuite product pages were access-denied; RGIS site returned 503. Oruvo Stock Integrity could not be independently located: `oruvo.ai` is a general decision-platform website, not evidence for that named product. These three are **UNCLEAR**, not certified non-competitors.

## Directly observed evidence (source IDs used throughout)

| ID | Primary/first-party source | What it actually supports |
|---|---|---|
| S1 | [Odoo: inventory adjustments](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/inventory_management/count_products.html) | Physical vs recorded counts, calculated differences, adjustment, location, assigned user and count dates. |
| S2 | [Odoo: cycle counts](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/inventory_management/cycle_counts.html) | Per-location schedules/frequencies and count workflows. |
| S3 | [Microsoft Dynamics 365: cycle counting](https://learn.microsoft.com/en-us/dynamics365/supply-chain/warehousing/cycle-counting) | System/user-directed and spot counting, threshold/plan-generated work, pending review of differences, work priorities and mobile input. |
| S4 | [Oracle Fusion Cloud Inventory Management](https://www.oracle.com/scm/inventory-management/) | Inventory movement visibility, mobile tasks, automated cycle counting and actionable inventory management; product-level claims, not a proof of our precise gate. |
| S5 | [Dexory: warehouse intelligence](https://www.dexory.com/) | Particularly close: physical-vs-WMS SKU/location reconciliation, integrity ML flags, suggested actions, continuous view; requires its physical collection technology. First-party marketing claims only. |
| S6 | [Gather AI](https://gather.ai/) | Physical-vs-system discrepancies, ranked priorities and routed workflows from robotic/vision physical observations; first-party marketing claims only. |
| S7 | [Simbe Robotics](https://www.simberobotics.com/) | Retail shelf vision and inventory/placement monitoring, related physical verification prior art, not evidence of our exact warehouse transaction gate. |
| S8 | [Oruvo English homepage](https://www.oruvo.ai/en/) | General evidence/constraints/decisions platform; **does not verify** existence or capabilities of a product called “Oruvo Stock Integrity.” |

## Capability map

| Function / named family | Classification | Adversarial conclusion |
|---|---|---|
| Odoo inventory, counting, adjustments | KNOWN [S1,S2] | Basic integrity and physical reconciliation are not innovation. Blind-count-specific configuration not verified here. |
| Dynamics 365 WMS | KNOWN [S3] | Prioritized count work, differences under review and spot counts; kills generic count scheduling or exception queue. |
| Oracle Inventory | RELATED [S4] | Mobile/automated cycle counts and movement visibility; detailed approval/concurrency semantics not assessed. |
| SAP EWM inventory/warehouse integrity | RELATED, feature details UNCLEAR | SAP help portal accessible but product detail not retrievable in this session; do not assert SAP lacks a gate or investigation. |
| NetSuite Smart Count / inventory | RELATED, feature details UNCLEAR | Product pages blocked by 403; no substantiated feature-level claims. |
| RGIS “Inventory Integrity Twin” | UNCLEAR | Site 503; named proposition not independently verified. Assume dangerous overlap, not uniqueness. |
| Oruvo “Stock Integrity” | UNCLEAR [S8] | Named stock product not corroborated; general Oruvo site is **not** that evidence. |
| Warehouse reconciliation / digital twin / operational intelligence | KNOWN [S5,S6] | Dexory directly attacks integrity, discrepancy flags and suggestions; cannot claim our category is new. |
| Cycle counting / verification prioritization | KNOWN [S2,S3,S6] | Generic risk ranking or next-best count alone is not differentiating. |
| RFID verification | RELATED | Established sensing modality; no evidence for an RFID-specific advantage in a no-hardware hackathon. |
| Computer-vision verification | KNOWN [S5,S6,S7] | Needs physical collection infrastructure; not an MVP. |
| Inventory audit / exception management / anomaly detection | KNOWN or RELATED [S1,S3,S5] | Count deviations, review work and anomaly flags are already available. |
| Event tracing, root-cause investigation, recurrence | PARTIALLY COVERED [S3,S5] | Marketing/docs insufficient to compare exact algorithms. Cannot claim absence of existing root-cause workflows. |
| Confidence/trust scores, verification debt | PARTIALLY COVERED [S5,S6] | Mostly repackaging without calibrated evidence or decision enforcement. |
| Event-driven verification / prevention | PARTIALLY COVERED [S3,S5,S6] | Threshold-triggered counts and proactive action already exist. Exact transaction-bound gate remains UNCLEAR. |
| Cross-system reconciliation | KNOWN [S5] | Dexory explicitly describes API-first WMS integration and SKU/location matching. |
| **Version-bound evidence gate on an imminent pick** | POTENTIAL GAP [S1–S6] | We found no *verified* exact implementation in sources read. **Not** evidence that it does not exist in ERP/WMS or custom rules. Position as a crisp, testable integration, not invention. |

**Search coverage caveat:** queries covered the named vendors plus functional equivalents (reconciliation, cycle count, physical verification, event-driven checks, scoring, digital twins, exception management and prioritization). Blocked sites prevent exhaustive comparisons. Physical hardware-based products may already do more than their public pages disclose.
