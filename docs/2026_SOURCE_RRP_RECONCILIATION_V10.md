# SmartQuote V10 — August 2026 Source RRP reconciliation workbench

**Development date:** 20 October 2026  
**Status:** Internal evidence and data-owner review only. **Not** a pricing tariff sign-off or production release.

## What has been integrated

A verified, sanitised read-only extract of `Full Master Price List 24-08-2026.xlsx` from the four source tabs. The original file SHA-256 is `fbc544db9365f6b47cd37fb3e085e5c75acc03042eff5d6f820ffa55f80b3433`. The 2026 *List Price* cells, not Sell Price or manufacturing cost, are used as staging data. Console/variant names, source sheet and original row references are kept. **Supplier and selling-cost fields are absent** from the packaged source dataset.

The admin UI shows a filterable, paginated SKU-level manager worklist, exact source evidence and side-by-side model-family comparison. Staff can view unapproved source variant evidence from Equipment Catalogue searches. Conflicting SKUs show both source rows and are blocked from having a single source RRP. There is no automatic catalogue update and **no quote repricing**.

## Reconciliation against current local V10 catalogue

| Status | SKU count |
|---|---:|
| Different source RRP compared with live SmartQuote | 3,530 |
| 2026 SKU not in current live SmartQuote catalogue | 1,053 |
| Conflicting source RRPs for same product code | 4 |
| Source rows lack positive equipment RRP (TRAKK service items) | 5 |
| Live catalogue has a SKU conflict | 1 |
| Source RRP matches current catalogue | 39 |
| **Total unique source codes** | **4,632** |

The 4,640 original rows are retained in the source evidence records. Figures describe a comparison at development time, *not* 3,530 commercially approved changes. All prices must be approved in accordance with Pulse pricing policy.

Conflicting 2026 source codes: `189G-AAB`, `280G-ABS`, `314H-ABH` and `385H-ACE`. `280G-ABS` has List Price £9,720.75 and £9,941.80 in separate rows. The existing `260G-ABZ` has £8,877.87 in SmartQuote vs £9,053.01 in the 2026 source master.

## Operator process (staff-first)

1. Go to **Master Price List → RRP reconciliation workbench**.
2. Filter *Conflicting source prices*, verify and correct those four records against product ownership, console and master worksheets first.
3. Filter *Different RRP*. Open an exact SKU, inspect the source sheet/row and actual console; have authorised managers confirm the current price list's validity and revision.
4. Review 1,053 missing current SKUs. Some are new or sellable items; others may be accessories, service items or non-maintainable equipment. **Do not bulk-add** all without classifying them.
5. For an unidentified machine, choose **Compare family**. The UI shows model configurations and a range of source RRPs but **does not choose the cheapest or latest console automatically**.
6. Only use controlled, audited catalogue edits after commercial and configuration approval. Existing open quotes are then re-checked under existing V10 rules. Issued quote snapshots stay unchanged.
7. Contract maintenance tariffs (Silver/Gold/Platinum) are still provisional and require independent commercial sign-off. The user's hybrid policy for older equipment does not approve any specific SKU-to-SKU conversion.

## Source and release controls

- Source data in `data/rrp_2026_source.json.gz`, loaded by `rrp_reconciliation.py`, generated via `build_rrp_2026_source.py` using the verified source workbook and staged CSV.
- Source list prices never replace `data/catalog.json` or `data/pricing.json` automatically, and no local quote customer DB is exported in the distributable ZIP.
- Manager endpoints `/api/catalog/admin/rrp-2026/summary`, `/search`, `/family/{model}` and `/reconciliation.csv`; authenticated staff have read-only `/api/catalog/rrp-evidence`.
- The historical 2020–2026 identity index still retains 7,159 physical equipment codes with 2025/26 workbook verification pending.
- Source completeness, commercial price sign-off, console mapping sign-off, user acceptance testing and PDF output sign-off remain explicit release gates.
