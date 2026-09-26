# StockSense scope

The StockSense problem statement and mockup are not included in this checkout. The requirement list below is from the supplied challenge summary, not a substitute for checking the official documents. Repository/video submission and portal steps are outside the application.

| Challenge area | Veyra state |
| --- | --- |
| Account signup/login | Username/password and 24-hour sessions; no OTP password reset. |
| Dashboard/stock alerts | Product, unit, low-stock and pending-delivery counts; no pending receipt/transfer KPIs or complete filters. |
| Catalog and stock | SKU, name, category, unit, reorder point, warehouse/bin stock, search and history; no configurable reorder rules. |
| Receipts and transfers | Validated single-product movements with references; no pending document lifecycles. |
| Deliveries | Multi-line documents, persisted pick/pack, final stock/evidence check and atomic linked movements; no cancellation/returns. |
| Adjustments/physical inventory | Explicit logged adjustments, version-bound counts and discrepancy investigation; no automatic correction. |
| Roles | All authenticated users have the same operational access; no assigned permissions. |

See `README.md` for a reproducible demo and setup, and `docs/ARCHITECTURE.md` for how the commit gate works. Physical observations and movement history do not prove the cause of a variance.
