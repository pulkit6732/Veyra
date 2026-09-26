# Veyra

Veyra is a local, browser-based inventory application for the StockSense challenge. It keeps a recorded stock ledger by product and warehouse/bin, captures operator-entered counts, and requires current, agreeing count evidence before committing a delivery. It is a working local MVP, not an independently verified physical-inventory system or an assertion of production readiness. The original challenge statement and mockup are not in this checkout; [the scoped requirements](docs/REQUIREMENTS.md) derive from a supplied challenge summary.

## Problem, operational risk, and solution

A ledger balance, a pick confirmation, and a physical observation answer different questions. A count can agree with the ledger when it is taken, but a subsequent receipt, transfer, adjustment, or delivery changes the ledger version for that product/bin. Releasing an order on the strength of an old count or an earlier advisory check would treat stale information as a current authorization; releasing one line before discovering a problem with another would leave a partially fulfilled document.

Veyra records movements and version-bound observations separately. Operators can investigate a variance, record a noted adjustment or conflict acknowledgement, and recount. A delivery can be drafted and picked/packed without reserving stock, but the final commit rechecks every line's stock and count evidence inside one SQLite transaction. If any line is blocked, the entire delivery stays PACKED and no line is deducted. This is a control over *recorded* evidence and ledger changes, not proof that an entered observation matches physical reality.

## Who it is for and why it might matter

- **Target users (intended, not validated):** operators who record receipts, counts, picks, packs, transfers, and deliveries; colleagues who review holds and investigation/audit records in a shared local workspace.
- **Potential buyer/evaluator (hypothesis):** an inventory-operations lead or small organization evaluating whether an evidence-gated delivery workflow suits its process. The repository has no customer research, purchases, adoption figures, or evidence of a commercial deployment.
- **Illustrative user persona:** an operator preparing a two-line delivery finds that one bin's last agreeing count predates a receipt. They need to know which line is held, keep the document and other line intact, recount the affected bin, and retry without creating duplicate stock deductions. This is a scenario illustrated by the seeded demo, not a description of a real user.
- **Value proposition as implemented:** recorded counts, holds with explicit next actions, and linked decisions/movements make that local workflow reviewable. Whether this reduces losses, speeds work, or meets a buyer's needs has not been measured.

### Example operator conversation / journey

The following is an illustrative script using the *synthetic* seed, not a customer interview or independently measured stock:

> **Operator:** “The ledger says S / WH/A = 768, but I entered 761 from a bin count. Can I ship?”
>
> **Investigation:** “The count differs by -7. No movement in this version window establishes a cause; check the bin and records.”
>
> **Operator:** “After checking, I record adjustment A1 with a note and recount S = 761. I also count B = 5. Then I receive 2 S (R1), pick and pack D1: 9 S and 3 B.”
>
> **Final commit:** “Held: S's count is at v1, while the receipt moved S to v2; B's count is still current. Neither line was deducted. Recount S and retry.”
>
> **Operator:** “I enter S = 763 at v2, then retry D1. The ledger shows S = 754 / v3 and B = 2 / v1, with two linked DELIVER movements.”

These quantities and versions come from `seed.py` and the scripted path in `tests/browser_smoke.mjs`. The application cannot tell whether the operator's physical observations or explanation are correct.

## MVP: implemented scope and development

**Implemented:** username/password signup and login; product/category/warehouse/location setup; integer stock and reorder points; dashboard and inventory views; immediate single-product RECEIVE, TRANSFER, and ADJUST movements; count sessions, evidence history, investigation and noted resolution; single- and multi-line delivery drafts with persisted pick/pack steps; final all-line evidence/stock gate; decision and movement logs. Inventory search and delivery-editor stock/evidence hints are advisory; the server revalidates on commit. All signed-in users share the same operational access.

**Development recorded in Git:** the initial local service and tests were followed by evidence-scoped investigation and resolution, then UI and adversarial-workflow hardening, then a delivery-list/evidence-query optimization. The relevant design and boundaries are in [architecture](docs/ARCHITECTURE.md), [database](docs/DATABASE.md), [API](docs/API.md), [red-team findings](RED_TEAM_REPORT.md), and [UI hardening notes](UI_HARDENING_REPORT.md). Those reports describe checks at their respective revisions; use the current tests for this checkout's verification. No separate release process or roadmap implementation should be inferred from the commit sequence.

### Team and contribution model

This is a small repository without a published contributor guide, stewardship rota, code-of-conduct process, or review SLA. For a proposed change, inspect the applicable docs and code, use an isolated `VEYRA_DB`, add or update tests for changes to ledger/evidence decisions, run both suites where browser behavior changes, and describe what was and was not verified. Keep physical observations distinct from ledger facts and advisory UI state distinct from final decisions. Git history records commit authors and handles; it does not establish team size or a formal ownership/review process. Contributions and deployment policy need human review.

## Architecture and evidence/decision model

```text
Browser: index.html (HTML/CSS/JavaScript)
    ⇅ local JSON HTTP /api/
veyra.py: Python standard-library ThreadingHTTPServer + inventory functions
    ⇅ SQLite transactions
SQLite file: catalog, stock, movements, counts/evidence, deliveries, decisions, events
```

There is no frontend build step, ORM, external database, or required third-party Python package. `seed.py` populates only a database without existing products. `veyra.py` creates/migrates its schema at startup; back up existing data before migration. The server defaults to `127.0.0.1:8000`. Every API operation enters `BEGIN IMMEDIATE`, serializing SQLite writers (including the final validation and decrement) rather than providing row-level locks or distributed coordination. Schema checks prevent negative recorded stock and enforce per-table reference uniqueness; application checks cross-resource reference collisions. Migration tests exercise specific legacy layouts; they are not a substitute for a backup and migration rehearsal on your own data.

A count session captures product/bin, recorded quantity, inventory version, actor, and start time. Submission stores an observation and a status at that time; **submission does not change stock**. A movement advances the relevant stock-row version, so an earlier agreeing count can become stale. At decision time, insufficient stock takes precedence; otherwise missing/current-version evidence, differing same-version observations, and disagreement with the ledger can produce `MISSING_PHYSICAL_EVIDENCE`, `STALE_PHYSICAL_EVIDENCE`, `CONFLICTING_PHYSICAL_EVIDENCE`, or `DISCREPANCY`. `VERIFIED` means the applicable operator-entered count(s) agree with the recorded quantity at the current version; it does **not** mean the bin was independently verified. A later-submitted stale count does not hide current-version observations. An earlier preflight approval never authorizes final commit.

Investigation shows count-start expected quantity, entered observation, variance, captured/current versions, earlier verified evidence, and scoped recorded movements. It does not infer the cause of a mismatch. An operator may explicitly resolve the latest, still-current discrepant count to its observed total, with a reference and note; if the latest count agrees but other counts at that version conflict, an explicit acknowledgement can keep the ledger total unchanged. Both paths record a linked ADJUST movement/resolution, advance the version, and require a recount. A general ADJUST movement is also accessible to any authenticated operator and can change the ledger without a count; the evidence gate is a *delivery-commit* policy, not a blanket prohibition on adjustments.

### Core delivery workflow

1. Create a document with one or more distinct SKU/source-bin combinations. `POST /api/deliveries/preflight` creates DRAFT and records per-line **advisory** decisions. The editor displays recorded stock; it is not a reservation.
2. Transition DRAFT → READY → PICKING → PICKED → PACKING → PACKED, recording each line's picked and packed quantities. These persisted confirmations do not change stock. Changes to stock after picking can still prevent delivery.
3. `POST /api/deliveries/commit` requires a fully picked/packed document. Under one SQLite write transaction it evaluates all lines using current stock and applicable counts. A blocked result identifies each line and an action (receive stock, recount, or investigate); it persists the decision but leaves the document PACKED and stock unchanged.
4. If every line passes, stock decrements, one linked DELIVER movement and DONE event per line, and the DONE transition commit together. Repeating a completed document returns `ALREADY_COMPLETED` without another deduction. A transaction error rolls back the attempted changes.

### Auditability and its limits

`decisions` record advisory/final attempts (including blocked ones), reason, evidence/version/stock snapshot, line and actor; `delivery_events` track transitions and quantity increments; `movements` link successful lines to their document; `resolutions` link a noted decision to its adjustment. Timestamps have SQLite second precision, so IDs distinguish same-second order. These are operational database records, **not** immutable or tamper-evident logs. GET list endpoints for evidence, movements, decisions, events, and resolutions return the latest 200 records; investigation returns the latest 50 scoped movements plus an exact count in its version window. Dashboard and UI history summaries using these bounded lists may omit older decisions. Backups, independent audit custody, and retention controls are not implemented here.

### Authorization and security behavior

Signup/login use a username and password; the server stores salted `scrypt` password hashes and issues random bearer tokens with 24-hour expiry. Logout removes a session. All GET and operational POST API routes require a token; tests exercise unauthenticated 401s and another account being forbidden (403) from submitting the first operator's count session. **There are no assigned roles or delivery ownership restrictions:** another signed-in account can operate someone else's delivery. The browser holds its token in `sessionStorage`. Default loopback binding is a deployment restriction, not transport security; this HTTP server has no TLS or login rate limiting. Do not publish it to a network or treat these controls as a security certification.

## API overview

JSON routes live under `/api/`. Signup and login (`POST`) are the only unauthenticated routes; otherwise send `Authorization: Bearer <token>`. Examples of route groups:

| Purpose | Routes |
| --- | --- |
| Accounts/catalog | `POST signup`, `login`, `logout`; `GET products`, `categories`, `warehouses`, `locations`; `POST products`, `products/update`, `categories`, `warehouses`, `locations` |
| Stock and review | `GET dashboard`, `inventory`, `movements`, `evidence`, `investigations`, `resolutions`, `decisions`, `delivery-events`; `POST movements` for RECEIVE / TRANSFER / ADJUST |
| Counts/investigation | `GET counts/open`; `POST counts/start`, `counts/submit`, `investigations/resolve` |
| Delivery | `GET deliveries`; `POST deliveries/preflight`, `deliveries/step`, `deliveries/commit` |

`inventory` supports SKU substring and warehouse/location/category filters. Use warehouse-qualified bins such as `WH/A`; an unqualified bin code is accepted only if unique. An ADJUST quantity is the new recorded total, not a delta. Errors return `{"error":"CODE"}` with a 4xx response. A valid **blocked** delivery decision is a persisted workflow result with HTTP 200, not a transport error. See [docs/API.md](docs/API.md) for bodies, state actions, and reason codes; the implementation in `veyra.py` is authoritative.

## Run locally

Use Python 3.11+ (standard library only). From the repository root, with a **disposable, separate database path** if you want to preserve existing data:

```sh
# Optional for a NEW database: synthetic S / WH/A = 768 and B / WH/A = 5 at v0
python seed.py
python veyra.py
# Open http://127.0.0.1:8000 and sign up (username >= 3, password >= 8 characters)
```

By default the server uses `veyra.sqlite3` in this directory. Set `VEYRA_DB` in your shell to a separate SQLite file **before** running either command to isolate data (for example, `export VEYRA_DB=/tmp/veyra-demo.sqlite3` on POSIX or `$env:VEYRA_DB = 'veyra-demo.sqlite3'` in PowerShell). `VEYRA_HOST` and `VEYRA_PORT` default to `127.0.0.1` and `8000`. Seeding skips a database with existing products; it does not reset existing stock. Do not delete or reseed an existing inventory file to follow the example; back it up before migrations. No external service is needed for local use. Browser smoke requires Node 22+ and a Chrome-compatible executable (set `CHROME_PATH` if not at the script's default location).

## Repository map

| Path | Purpose |
| --- | --- |
| `index.html` | Browser UI served by the Python service; no build pipeline |
| `veyra.py` | HTTP routing, inventory logic, SQLite schema and migrations |
| `seed.py` | Synthetic new-database demo balances |
| `docs/REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DATABASE.md` | Scope, transaction model, endpoints, and persistence |
| `tests/test_api.py`, `tests/test_multiline.py`, `tests/test_migration.py` | Local HTTP/SQLite and migration tests |
| `tests/browser_smoke.mjs` | Seeded headless-Chrome browser journey and selected UI checks |
| `RED_TEAM_REPORT.md`, `UI_HARDENING_REPORT.md` | Prior adversarial and UI investigation notes |
| `LICENSE` | MIT license |

## Verification methodology and measured results

Run from the root:

```sh
python -m unittest discover -s tests -v
node tests/browser_smoke.mjs
git diff --check
```

These test suites were not run during this final documentation-only cleanup. Their coverage is described below; run the commands above for results in your environment.

**Tests in this checkout:** `test_api.py` starts a local threaded HTTP server on an ephemeral port and exercises signup and token-required paths, validation/errors, transfers and stock conservation, count submission and scope, stale/missing/conflicting/discrepant decisions, investigation and resolution, lifecycle transitions, idempotent delivery, and threaded races between counts, movements, resolutions, and commits. `test_multiline.py` exercises per-line validation and links, a blocked last line leaving *both* rows intact, an injected SQLite error on the second movement with rollback, duplicate/auto-created reference protection, another signed-in account's shared delivery access, racing commits/inventory changes, and the delivery-list evidence labels/query count. `test_migration.py` checks two constructed legacy database shapes for preservation, idempotent startup, and foreign-key integrity. These are isolated local HTTP/SQLite tests; the direct SQLite fixtures and injected error are not field deployments or power-loss tests.

`browser_smoke.mjs` seeds a temporary database, starts the local service and headless Chrome, and runs the illustrated two-line journey through the actual UI. It checks draft editor validation, refresh across pick/pack and blocked states, back/forward routing, the affected-line recount, linked final records, conflict acknowledgement, duplicate receipt, selected 401/409 and simulated 500/delayed inventory responses, and layout overflow at specified viewport widths (390, 430, 768, 1024, 1280, 1440; page-level checks at 390, 768, 1440). Signup for this smoke run is made via HTTP and its token injected into browser session storage; it does **not** exercise browser-based signup end to end. The script prints a single Chrome render measurement including API calls; it is not a performance benchmark.

**Measured engineering metric (isolated database work only):** the reported delivery-list measurement for a **50-order / 100-line fixture with current evidence** is **251 → 3 SQL statements**. That fixture is not checked into this repository and was not rerun in this documentation pass. The pre-optimization code in Git ran one order query, one line query per order, and two evidence queries per line (1 + 50 + 100 + 100); the current path batches orders, lines, and evidence scopes. The committed delivery-list batching test separately checks **3 SELECT/WITH statements for 13 orders / 26 lines** and the evidence labels. Statement count on a fixture is **not** application-wide latency, throughput, or a guarantee of performance at scale; query cost, response serialization, browser rendering, and workload are not captured by this figure. Python suite and browser-smoke wall-clock runtimes, if reported by the commands, describe test execution, **not** application latency.

**Not tested/established:** correct physical stock or cause of a variance; actual customer demand or operational savings; production deployments, backup/restore, TLS, rate limiting or adversarial security assurance; disk/power-loss recovery or distributed/multi-process load; full endpoint fuzzing, every UI error path, cross-browser support, multi-tab consistency, or a comprehensive accessibility audit. Tests use temporary databases and selected threaded races, not exhaustive concurrency schedules or long-running scale studies. The included migration fixtures do not cover every possible historical database.

## Limitations and future work (not implemented)

Receipts and transfers are immediate movements, not document lifecycles; picking does not reserve stock. There are no returns/cancellations, assigned roles, ownership policy, OTP reset, configurable reorder rules, complete dashboard filters, pending receipt/transfer KPIs, independent physical measurement, or supervisor override for conflicting counts. Stock quantities are nonnegative whole units; there is no fractional-unit conversion. A wrong operator-entered count can appear `VERIFIED` when it matches the ledger. The app is loopback-only by default and its logs/live views are not an external audit system.

Potential future work, subject to human prioritization and design: role/ownership policy; secure deployment and session controls; backup/restore and migration rehearsals; richer receipt/transfer lifecycles; reservation/return flows; stronger accessibility/cross-browser and recovery/load testing; and a trusted physical-count process if independently measured truth is required. None of these is a shipped feature or a committed schedule.

## License

MIT; see [LICENSE](LICENSE). Copyright 2026 Pulkit Kr Srivastava. The license grant does not imply a warranty or an independent security/physical-inventory assurance.
