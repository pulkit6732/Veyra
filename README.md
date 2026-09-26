# Veyra

Veyra is a **local inventory application** for the Odoo × GCET StockSense challenge. StockSense calls for a centralized inventory ledger, products and SKU, warehouses/bins, receipts, deliveries, transfers, adjustments, history and stock visibility. Veyra adds a version-bound physical evidence gate: a count proves what was seen *at one bin/SKU ledger version*. A later movement invalidates that count for guarded delivery. A delivery that looks numerically available can be held at **server commit**, then released only after a fresh, agreeing recount. This is a workflow mechanism, not a claim of novelty or physical truth.

## Start locally

Requires Python 3.11+; no third-party packages, internet, cloud account or external DB. On Windows PowerShell or bash from the project root:

```sh
python seed.py             # optional: only on a new DB, initializes S/WH/A=768 at v0
python veyra.py            # http://127.0.0.1:8000
```

First open the URL and create an account (username 3+ chars; password 8+ chars). SQLite file `veyra.sqlite3` is created in the repository; set `VEYRA_DB` to a separate file path for isolated data. `VEYRA_HOST` defaults to 127.0.0.1; `VEYRA_PORT` defaults to 8000. Do not expose the development server publicly. For a clean database, stop the server, back up and remove `veyra.sqlite3`, then run the seed command again. Seed does not overwrite an existing catalog.

## Demo (browser)

1. Run seed before signup. Sign up. Open **Inventory → Investigate** for S / WH/A. There is no count yet. In **Physical Verification**, start S / WH/A, submit **761**. The investigation shows expected **768**, observed **761**, variance **-7**, and no recorded movement explaining the difference. This is not an automatic attribution.
2. Check the bin and records yourself. In **Investigation**, enter reference `A1` and a real note, then explicitly adjust to 761. Audit records the adjustment and note; the prior count is now stale. Recount 761 to verify at v1.
3. In **Receipts**, receive S at WH/A, quantity **2**, unique reference `R1` and supplier. Current stock is **763 / v2**. Open the earlier verified count from **Physical Verification → Evidence history** to see the receipt scoped to the bin.
4. In **Deliveries**, order `D1`, S, WH/A, quantity 9. Check then attempt delivery. The backend records `STALE_PHYSICAL_EVIDENCE`, evidence v1, current v2, action RECOUNT.
5. Recount 763 at v2. Return to Deliveries, check D1 and attempt again. Exactly one DELIVER movement commits, ending stock **754 / v3**. Inspect **Evidence Holds** and **Audit** for decisions, movements and resolution.

Subsequent deliveries need new evidence because delivery itself changes the inventory version. Count sessions can be resumed after reload by the actor who started them. Investigations are based on persisted count snapshots and version-scoped movements, not AI or claims of proven causality. Stock adjustments are explicit; submitting a count never changes stock.

## Tests

```sh
python -m unittest discover -s tests -v
node tests/browser_smoke.mjs   # optional: needs Node 22+ and Chrome (CHROME_PATH overrides default)
```

Tests use an isolated temporary SQLite database and real localhost HTTP server. The optional browser smoke runs the full seeded discrepancy → resolution → receipt → stale hold → recount → delivery flow in headless Chrome with a temporary browser profile and database. No mock database or static JSON store. See `docs/REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, and `docs/API.md`.

## Known gaps (not claimed complete)

OTP password reset, rich receipt/delivery document lifecycle (draft/waiting/ready/canceled, multi-line picking/packing), pending receipts/transfers KPIs, configurable reordering rules, full dashboard filters, and assigned roles are **not implemented**. Authentication is simple username/password + 24h bearer session and no role separation; do not deploy on a public network. Counts can be wrong even when recorded as agreeing; this system does not independently verify physical truth. Supplied official participant document requires one repository branch, mentor collaborator and team-leader submission of repo/video; milestones are only visible in the authenticated hackathon portal and must be checked by the actual team. See `docs/REQUIREMENTS.md` for sourced vs product requirements.
