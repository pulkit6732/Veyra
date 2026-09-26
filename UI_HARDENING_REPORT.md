# UI integration / operator red-team pass

Local-only run on disposable seeded SQLite databases and headless Chrome. No user DB was reset; no commit was made. See `RED_TEAM_REPORT.md` for the earlier backend red-team findings and limitations.

## Verified UI issues and changes

- The old dashboard counted all historical blocked decisions as current holds. It now presents open delivery lines from the live deliveries response and groups the most recent COMMIT decisions per document; historical decisions remain visible in Evidence Holds/Audit. These decisions are limited to the latest 200 returned rows.
- Evidence history previously displayed submission status without current inventory version, which could make an old VERIFIED count appear usable. It now compares the returned captured and current versions, labels stale observations, and links to Investigation; Investigation states the reason and scoped movement context without claiming causation.
- A DONE delivery previously displayed its now-stale evidence as a prompt to recount; DONE line guidance now points to Audit. The PACKED view offers actions for affected lines only, and explains that final validation checks all lines before any stock changes.
- Double-clicking delivery transitions and final commit in the browser could send redundant requests (the server rejected or idempotently handled them). The buttons now disable before awaiting; quantity/count forms also guard repeat submission. A failed step/commit reloads the authoritative document state.
- Concurrent page loads could replace a newer screen with an older response. Render generation checks now discard stale results. HTTP error parsing and network failures now have explicit operator-facing messages, including 401 sign-in and 500/unreadable responses.
- Delivery orders previously showed only the first line's SKU and quantity without indicating that more lines existed. The list now identifies additional lines and labels the first-line quantity. Table overflow is contained within scrollable table wrappers, including on small screens.

## Executed attacks and checks

`node tests/browser_smoke.mjs` executes the full seeded discrepancy → adjustment → recount → receipt → two-line pick/pack → stale evidence block → affected-line recount → atomic commit → audit journey on a new database. It also exercises duplicate transition clicks, duplicate blocked-commit clicks (one attempt only), refresh through READY/PICKING/PICKED/PACKING/PACKED/blocked, browser back/forward, malformed and duplicate delivery lines, a nonexistent delivery URL, an invalid hash, a real duplicate-receipt HTTP 409 (stock unchanged), simulated delayed/failed GETs and HTTP 500, session loss followed by login recovery, and responsive inspection at 390, 430, 768, 1024, 1280 and 1440 CSS px. The section overflow check covers Dashboard, Inventory, Physical Verification, Investigation, Receipts, Deliveries and Audit at 390, 768 and 1440 px; table contents deliberately scroll *inside* their wrappers.

`python -m unittest discover -s tests -v` covers real local HTTP authentication/401, 403, 404, 409, invalid quantities, cross-document line IDs, concurrent commits, inventory changes after validation, conflicting/stale evidence and injected second-line SQLite failure with rollback. These are API tests, not additional browser-tab or power-loss simulations.

## Remaining limitations

No exhaustive multi-tab browser test, accessibility audit, server power-loss simulation, all-endpoint fuzzing, or exhaustive 400/401/404/409/500 test on every page. Direct receipt/transfer/adjustment forms are immediate movements, not document lifecycles. Inventory/evidence/decision/movement history views are bounded by the existing API (200 rows; investigation events 50); dashboard history metrics are therefore scoped to the returned window. No roles, reservation, TLS or independent physical proof are claimed. Run only on localhost. See `README.md` and `RED_TEAM_REPORT.md` for further limits.
