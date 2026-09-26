# Veyra red-team report

Scope: this checkout, isolated local SQLite databases, stdlib HTTP server on `127.0.0.1`, and headless Chrome. The official StockSense problem statement/mockup is not present in this checkout; `docs/REQUIREMENTS.md` and the application were used for scope. No existing user database was reset. No changes were committed.

## Findings and fixes (highest value first)

| Priority | Reproduced before | Change | Verified after |
| --- | --- | --- | --- |
| P1 — conflict-resolution dead end | At one unchanged stock version, a discrepant count followed by an agreeing count held a delivery as `CONFLICTING_PHYSICAL_EVIDENCE`. Recounting at that version did not clear it. `POST /api/investigations/resolve` rejected the older disputed count as `STALE_EVIDENCE` and the latest agreeing count as `NOT_AN_OPEN_DISCREPANCY`. The Investigation page offered no resolution for the latest count. | `veyra.py` allows an explicit, noted resolution of the *latest* agreeing observation only if another current-version observation disagrees. It logs a linked adjustment/resolution, leaves quantity unchanged, advances the stock version and requires another count. Investigation labels this as conflict acknowledgement, not proof of physical stock; it no longer offers resolution for an older count. | New API test and actual Chrome test: conflict still blocks; acknowledgement leaves quantity unchanged, changes version, old evidence becomes stale, and a new count is required. An older count cannot be used to resolve it. |
| P1 — derived movement reference could strand an order | Before the fix, after creating a two-line order an operator could receive stock with reference `M#<second line id>`. The final commit then failed on a movement uniqueness constraint even with fresh evidence and enough stock. A rollback prevented partial stock changes, but the PACKED order could not finish using its existing reference. | Reject use of existing delivery-generated movement references by receipts/transfers/adjustments and by other delivery drafts. Reject a new draft transactionally if its generated references already belong to an existing movement or delivery. | API tests reject the collisions before pick/pack or before draft creation. A separate database trigger now injects failure *after the first line has changed inside a transaction*; the test checks no delivery stock changes, decisions, movements, DONE events or DONE state survive rollback. |
| P2 — blocked attempt lost its next action on refresh | The immediate result linked the affected line to a recount/investigation, but the persisted final-attempt summary after reload only described the problem. | Add per-line recount/investigation links to the persisted attempt. | Chrome reloads a blocked PACKED document, sees the `S`-only count action, and follows it; `B` remains current. |
| P2 — missing delivery URL silently looked like no selection | `#Deliveries/not-found` showed the order list without telling the operator that the requested record was absent. | Show the missing reference and direct the operator to the order list or URL. | Chrome opens that URL and checks the missing-record explanation. |

No new dashboard, AI features, frontend framework, roles or automatic evidence reinterpretation were added. Existing tests already passed for negative stock protection, invalid transitions, duplicate product/bin lines, nonexistent scopes, stale/missing/conflicting evidence, concurrent commits and authentication: those paths were not rewritten.

## Adversarial checks actually executed

- Baseline: `python -m unittest discover -s tests -v` **44 passed**; `node tests/browser_smoke.mjs` **passed** before changes. An isolated *running* seeded server was called over HTTP to reproduce the conflicting-count dead end; its ledger remained `S=768, v0` after rejected resolution and repeated counting.
- Final: `python -m unittest discover -s tests -v` **50 passed** and `node tests/browser_smoke.mjs` **passed**. `git diff --check` completed without whitespace errors. Python tests exercise zero/negative/invalid quantities, other SKU/bin evidence, duplicate refs, cross-delivery line IDs, second-account access, unauthenticated mutation, duplicate commits, old-version count submission, transfer with insufficient stock, simultaneous receipt/commit, explicit resolution, and injected second-line failure. Rollback asserts no commit decisions, movements, DONE events or state survived. Tests use local HTTP requests and isolated databases, not mock JSON as the product state.
- Browser smoke uses a clean seeded database and Chrome. It performs the discrepancy → explicit resolution → recount → receipt → two-line pick/pack → stale hold → affected-line recount → commit → audit flow. It tests refresh at several lifecycle states (READY, PICKING, PICKED, PACKING, PACKED and blocked PACKED), back/forward, invalid form lines, malformed hash, missing delivery URL, simulated failing and delayed inventory fetches, and viewport widths 390, 768 and 1280 CSS pixels. It also reproduces and resolves a latest-agreeing-count conflict against live local state. A failed fetch shows a retry error; a delayed fetch shows loading. The 390px layout had no document-width overflow (table scrolls inside its container).
- HTTP 401/403/404/409 and database rollback are asserted in tests. An authenticated *different* account can still change another account's delivery: this is existing shared-workspace behavior, **not** role- or owner-based authorization.

## Before / after for the central decision

Before: latest agreeing count after a differing same-version count still blocked release, but the investigation could not resolve that latest count; a user had to discover the generic adjustment route. After: still blocked until the operator explicitly records a decision with a note; the ledger stays at the chosen recorded total, version advances, and recount is required. Neither observation is treated as physical truth. A receipt or delivery invalidates prior evidence only for its affected product/bin; final commit rechecks every line inside one transaction. If one line fails, no line is deducted.

## Remaining limitations

- Physical observations are operator-entered, not independently verified. A signed-in operator can also use direct `ADJUST`; counts do not establish a cause. No role assignment, ownership restriction, TLS or rate limiting. Run on localhost, not a public network.
- The injected trigger test proves rollback for a SQLite constraint failure on the second movement. It does not simulate power loss or disk failure. SQLite's writer lock serializes writes; this is not a distributed transaction system.
- No comprehensive browser accessibility audit, full endpoint fuzzing, or exhaustive slow/error tests on every page. Browser checks use one Chrome installation and fixed viewport sizes; document lists and evidence history are bounded as described in the README. Existing legacy databases with already-stranded reference collisions are not repaired by the new draft guard. The UI's recent decision summary depends on the most recent 200 decision rows.
- The challenge's original statement/mockup cannot be cross-checked because it is absent from this checkout. Authentication is session-based, not role-based. Do not treat the seeded balances as measured physical stock.

## Strongest verified demo and exact reproduction

From `D:\Veyra` in PowerShell, use an isolated disposable DB so no existing inventory is overwritten:

```powershell
$env:VEYRA_DB = Join-Path (Get-Location) 'veyra-demo.sqlite3'
Remove-Item $env:VEYRA_DB -ErrorAction SilentlyContinue # only this demo file
python seed.py
python veyra.py # open http://127.0.0.1:8000
```

Create an account in the browser. Inventory shows **S/WH/A=768, B/WH/A=5**. Count S as **761**; Investigation shows expected 768, observed 761, variance -7 with no recorded movement proving its cause. After checking, resolve with adjustment ref **A1** and an actual note; recount S as **761** and B as **5**. Receive S **2** at WH/A with ref **R1** and supplier. Draft **D1** with lines S/WH/A **9** and B/WH/A **3**; complete READY → PICKING (pick both) → PICKED → PACKING (pack both) → PACKED. Attempt final delivery: S evidence is stale v1 vs ledger v2, B evidence still agrees; **neither** stock row is decremented. Recount **only S=763**; retry D1: S becomes **754/v3**, B becomes **2/v1**, with two linked DELIVER movements and an audit of both decisions. This journey was exercised by the browser smoke test. A repeatable automated run, also using a disposable database, is:

```sh
python -m unittest discover -s tests -v
node tests/browser_smoke.mjs
```
