# Veyra

Veyra is a **local inventory application** for the Odoo × GCET StockSense challenge. StockSense calls for a centralized inventory ledger, products and SKU, warehouses/bins, receipts, deliveries, transfers, adjustments, history and stock visibility. Veyra adds a version-bound physical evidence gate: a count proves what was seen *at one bin/SKU ledger version*. A later movement invalidates that count for guarded delivery. A delivery that looks numerically available can be held at **server commit**, then released only after a fresh, agreeing recount. This is a workflow mechanism, not a claim of novelty or physical truth.

## Start locally

Requires Python 3.11+; no third-party packages, internet, cloud account or external DB. On Windows PowerShell or bash from the project root:

```sh
python seed.py             # optional: only on a new DB, initializes S/WH/A=10 at v0
python veyra.py            # http://127.0.0.1:8000
```

First open the URL and create an account (username 3+ chars; password 8+ chars). SQLite file `veyra.sqlite3` is created in the repository; set `VEYRA_DB` to a separate file path for isolated data. `VEYRA_HOST` defaults to 127.0.0.1; `VEYRA_PORT` defaults to 8000. Do not expose the development server publicly. For a clean database, stop the server, back up and remove `veyra.sqlite3`, then run the seed command again. Seed does not overwrite an existing catalog.

## Demo (browser)

1. Run seed before signup. Sign up. In **Physical Verification**, start S / WH/A, submit count 10 (v0).
2. In **Receipts**, receive SKU S, location WH/A, quantity 2, unique reference R1 and supplier. Inventory shows 12 / v1.
3. In **Deliveries**, order D1, SKU S, WH/A, quantity 9. Check delivery, then **Attempt delivery**. Backend records a blocked commit: `STALE_PHYSICAL_EVIDENCE`, evidence v0, current v1, action RECOUNT.
4. Start a new count of S at WH/A. Submit observed 12 at v1. Return to Deliveries; check D1 and attempt again. Exactly one DELIVER movement commits, ending stock 3 / v2. Inspect **Evidence Holds** and **Audit** for both decisions and the movements.

Subsequent deliveries need new evidence because delivery itself changes the inventory version. Stock adjustments are explicit; submitting a count never changes stock.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests use an isolated temporary SQLite database and real localhost HTTP server. No mock database or static JSON store. See `docs/REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, and `docs/API.md`.

## Known gaps (not claimed complete)

OTP password reset, rich receipt/delivery document lifecycle (draft/waiting/ready/canceled, multi-line picking/packing), pending receipts/transfers KPIs, configurable reordering rules, full dashboard filters, and assigned roles are **not implemented**. Authentication is simple username/password + 24h bearer session and no role separation; do not deploy on a public network. Counts can be wrong even when recorded as agreeing; this system does not independently verify physical truth. Supplied official participant document requires one repository branch, mentor collaborator and team-leader submission of repo/video; milestones are only visible in the authenticated hackathon portal and must be checked by the actual team. See `docs/REQUIREMENTS.md` for sourced vs product requirements.
