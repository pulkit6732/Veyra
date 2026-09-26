# Local API

JSON at `/api/`; `Authorization: Bearer <token>` for all endpoints except `POST /api/signup`, `POST /api/login` (both `{username,password}`). `POST /api/logout` revokes token. Errors return `{"error":"CODE"}` with 4xx. Successful domain decisions return HTTP 200, including **BLOCKED** results: the decision is recorded. All GET endpoints require authentication.

| Method | Path | Body / result |
| --- | --- | --- |
| GET | dashboard, inventory, products, categories, warehouses, locations, deliveries, delivery-events, evidence, decisions, movements, resolutions | live database reads; inventory accepts `search` SKU substring, `warehouse`, `location`, `category` URL query params |
| POST | categories | `{name}` |
| POST | products | `{sku,name,category?,uom?,reorder_point?}` |
| POST | products/update | `{sku,name?,uom?,category?,reorder_point?}` |
| POST | warehouses | `{code,name}` |
| POST | locations | `{warehouse,code,name}` |
| POST | movements | `{kind: RECEIVE|TRANSFER|ADJUST,ref,sku,location,qty,destination?,contact?}`. ADJUST qty is the **new recorded total**, not a delta; transfers need destination. |
| GET | counts/open | newest OPEN session for current actor, or `null`; supports reload while counting |
| GET | investigations | `?evidence_id=ID` or `?sku=S&location=WH/A`; returns scoped snapshot, last earlier verified count, signals, resolution, latest 50 relevant events and full event count. Signals are evidence, not causal proof. |
| POST | investigations/resolve | `{evidence_id,ref,note}`; only latest current discrepant count; explicitly adjusts stock to observation and audits note, actor and movement; requires new count afterward; stale evidence and duplicate resolutions return 409 |
| POST | counts/start | `{sku,location}` → `session_id,captured_version,recorded_qty` |
| POST | counts/submit | `{session_id,qty}`; captures version from start, never from submission |
| POST | deliveries/preflight | `{ref,sku,location,qty,contact?}` legacy single line, or `{ref,lines:[{sku,location,qty},...],contact?,destination?}`; creates DRAFT if absent, persists per-line advisory PREFLIGHT decisions; no stock mutation. Existing document can be preflighted by `{ref}`. Lines are immutable after creation. |
| POST | deliveries/step | `{ref,action,qty?,line_id?}`; actions READY, START_PICKING, PICK, COMPLETE_PICKING, START_PACKING, PACK, COMPLETE_PACKING; PICK/PACK require positive integer increment `qty` and `line_id` for multi-line documents (optional for single line). Completion requires ALL lines full; rejects invalid transitions 409. |
| POST | deliveries/commit | `{ref}` (or matching document payload); requires PACKED with full picked/packed quantities across every line. Revalidates evidence and stock for each line inside BEGIN IMMEDIATE. Blocked returns 200 with status BLOCKED and per-line `lines` results; no stock or completion audit changes. Allowed decrements all rows, inserts one movement and DONE event per line, transitions document to DONE atomically. Repeated DONE returns ALREADY_COMPLETED without mutation. |

GET deliveries includes `lines` with IDs, per-line requested/picked/packed/on-hand/version and advisory evidence indicator. GET decisions includes line_id; GET movements includes delivery_ref and line_id; investigations return movement links for traceability. Specify a warehouse-qualified location, e.g. `WH/A`; an unqualified `A` works only when unique. Policy guards **all** final delivery commits; reasons: INSUFFICIENT_STOCK, MISSING_PHYSICAL_EVIDENCE, STALE_PHYSICAL_EVIDENCE, CONFLICTING_PHYSICAL_EVIDENCE, DISCREPANCY, VERIFIED. `required_action` is RECOUNT for stale/missing evidence, INVESTIGATE for discrepancies/conflicting counts (repeating a count at the same version does not clear conflicting evidence), or RECEIVE_STOCK for insufficient stock. No previous approval authorizes a subsequent commit.
