# Local API

JSON at `/api/`; `Authorization: Bearer <token>` for all endpoints except `POST /api/signup`, `POST /api/login` (both `{username,password}`). `POST /api/logout` revokes token. Errors return `{"error":"CODE"}` with 4xx. Successful domain decisions return HTTP 200, including **BLOCKED** results: the decision is recorded. All GET endpoints require authentication.

| Method | Path | Body / result |
| --- | --- | --- |
| GET | dashboard, inventory, products, categories, warehouses, locations, deliveries, evidence, decisions, movements | live database reads; inventory accepts `search` SKU substring, `warehouse`, `location`, `category` URL query params |
| POST | categories | `{name}` |
| POST | products | `{sku,name,category?,uom?,reorder_point?}` |
| POST | products/update | `{sku,name?,uom?,category?,reorder_point?}` |
| POST | warehouses | `{code,name}` |
| POST | locations | `{warehouse,code,name}` |
| POST | movements | `{kind: RECEIVE|TRANSFER|ADJUST,ref,sku,location,qty,destination?,contact?}`. ADJUST qty is the **new recorded total**, not a delta; transfers need destination. |
| POST | counts/start | `{sku,location}` → `session_id,captured_version,recorded_qty` |
| POST | counts/submit | `{session_id,qty}`; captures version from start, never from submission |
| POST | deliveries/preflight | `{ref,sku,location,qty,contact?}`; creates PENDING order, persists PREFLIGHT decision; advisory only |
| POST | deliveries/commit | same order payload; evaluates and persists COMMIT decision, and for ALLOWED decrements stock and inserts one movement atomically |

Specify a warehouse-qualified location, e.g. `WH/A`; an unqualified `A` works only when unique. Policy currently guards **all** delivery commits; reasons: INSUFFICIENT_STOCK, MISSING_PHYSICAL_EVIDENCE, STALE_PHYSICAL_EVIDENCE, CONFLICTING_PHYSICAL_EVIDENCE, DISCREPANCY, VERIFIED. `required_action` is RECOUNT except insufficient stock (RECEIVE_STOCK). No previous approval authorizes a subsequent commit.
