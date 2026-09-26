# Veyra

Veyra is a local inventory application for the StockSense challenge. It records products, stock by warehouse/bin, receipts, transfers, adjustments and deliveries. A physical count records an observation against the ledger version of one product/bin. A later movement advances that version. At final delivery, the server checks every line against current stock and agreeing physical evidence in one SQLite transaction. Missing, stale, conflicting or discrepant counts hold the entire delivery without deducting stock. The operator can investigate, explicitly adjust the ledger when warranted, recount and retry. A count is an operator observation, not independent proof of physical stock or the cause of a discrepancy. If counts disagree at the same version and the latest agrees with the ledger, Investigation can record an explicit acknowledgement that keeps the ledger quantity unchanged, advances the version, and requires a recount; an agreeing count alone cannot clear a conflict.

## Start locally

Requires Python 3.11+; no third-party packages, internet, cloud account or external DB. From the project root:

```sh
python seed.py             # optional: new DB only; S/WH/A=768, B/WH/A=5 at v0
python veyra.py            # http://127.0.0.1:8000
```

First open the URL and create an account (username 3+ chars; password 8+ chars). SQLite file `veyra.sqlite3` is created in the repository; set `VEYRA_DB` to a separate file path for isolated data. `VEYRA_HOST` defaults to 127.0.0.1; `VEYRA_PORT` defaults to 8000. Do not expose the development server publicly. For a clean database, stop the server, back up and remove `veyra.sqlite3`, then run the seed command again. Seed does not overwrite an existing catalog.

## Demo (browser)

1. Run seed before signup. Sign up. Open **Inventory → Investigate** for S / WH/A. There is no count yet. In **Physical Verification**, start S / WH/A, submit **761**. The investigation shows expected **768**, observed **761**, variance **-7**, and no recorded movement explaining the difference. This is not an automatic attribution.
2. Check the bin and records yourself. In **Investigation**, enter reference `A1` and a real note, then explicitly adjust to 761. Audit records the adjustment and note; the prior count is now stale. Recount S = 761 to verify at v1. Count B / WH/A = 5 at v0.
3. In **Receipts**, receive S at WH/A, quantity **2**, unique reference `R1` and supplier. Current stock is **763 / v2**. Open the earlier verified count from **Physical Verification → Evidence history** to see the receipt scoped to the bin.
4. In **Deliveries**, create draft `D1`: select S / WH/A / 9, **Add line** B / WH/A / 3 (availability and errors appear immediately). Open D1, mark READY, start PICKING, record 9 S and 3 B picked, complete picking, start PACKING, record 9 S and 3 B packed, complete packing. Reload D1 to verify PACKED persists. Attempt final delivery. S is blocked with `STALE_PHYSICAL_EVIDENCE` (evidence v1, current v2); B is VERIFIED at v0. No line has been decremented.
5. Recount only S = 763 at v2. Return to Deliveries, open D1 and retry final delivery. Exactly two linked DELIVER movements commit atomically: S = **754 / v3**, B = **2 / v1**. Inspect **Evidence Holds**, **Investigation** and **Audit** for the blocked and successful decisions, evidence IDs, actors, delivery transitions, movements and resolution. This is one reproducible seeded journey; no state is simulated in the UI.

For a multi-line document, use **Add line** in the delivery form. Select a product, source bin and whole-unit quantity for each line; the editor shows on-hand availability and validates before creating a draft. Each line must have a distinct product/bin pair. This is advisory; server commit always revalidates. Pick and pack each line before completing the document. On final commit every line is checked under one SQLite write transaction; a blocked line holds the entire document without decrementing any stock. Blocked results identify each line and its required action. A fresh count is needed only for a line whose evidence became stale (unless another line independently requires one). Each committed line has its own DELIVER movement linked to document and line ID; the first line keeps the document reference for legacy clients. References of the form `document#line_id` are reserved for that document's generated movements.

Subsequent deliveries need a new count because delivery changes the inventory version. Count sessions survive reload for the starting operator. Investigations show the expected and observed quantities, variance, captured/current versions, scoped movements, evidence status, resolution and recount. Movements recorded after a count do not establish the physical cause. Submitting a count never changes stock.

## Tests

```sh
python -m unittest discover -s tests -v
node tests/browser_smoke.mjs   # optional: needs Node 22+ and Chrome (CHROME_PATH overrides default)
```

Python tests cover API validation, authorization, migration, races, rollback and stock conservation. Browser smoke uses a temporary SQLite database, local server and headless Chrome to run the seeded journey, including refresh and a 390px viewport. See `docs/REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md` and `docs/API.md`.

## Known gaps (not claimed complete)

OTP reset, receipt/transfer document lifecycles, returns/cancellations, assigned roles, configurable reorder rules, complete dashboard filters and pending receipt/transfer KPIs are not implemented. All signed-in operators can access and change the same inventory and deliveries. Authentication uses 24-hour bearer sessions with no TLS or rate limiting; run on localhost only. Picking does not reserve stock. Evidence may be factually wrong. List views show recent records (up to 200); investigation shows up to 50 movements with an exact total. Back up a database before migration.
