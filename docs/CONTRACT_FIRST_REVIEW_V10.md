# V10 contract-first maintenance quoting — 20 October 2026

Status: controlled internal pilot. Commercial pricing and legal terms are not approved for customer issue.

## Grounded workflow reference

The supplied *Gang Warily Recreation Centre Maintenance Agreement (2026, agreement 00000960/7335 R1)*, Schedule 3, uses four customer-facing equipment columns:

- Machine code
- Description
- Quantity
- Serial Number(s)

Its Gold payment schedule presents the contract sum (£4,370.63) separately from the equipment lines. The V10 quotation now follows this **equipment schedule structure**, not the full legal agreement; existing customer quotation documents remain drafts until pricing and terms are approved. Do not infer individual machine maintenance charges from the agreement total.

## Implemented changes

1. Equipment list shows **machine/model, all available serials, description, quantity, unit/month, line/year and Edit**. Spreadsheet row, source sheet, historical family evidence, variant list and match reasoning remain in a collapsed *Original asset and catalogue details* panel within the editor, and in the original-asset CSV. No original machine or serial is discarded.
2. The console selector no longer inherits modal input width: radio dimensions are explicitly 17×17px; options flex and wrap, including on narrow screens. Console selection is optional and only expanded when needed.
3. For a bare, non-console-listed model with an actual `MODEL-AAA` source entry, offer a one-click **standard model-family draft reference** (e.g. 875G → 875G-AAA) at the August 2026 source RRP. The exact physical SKU is **not** assumed or written into the asset code. Actual console status remains *unconfirmed*. Special/IFI/inclusive/platform configurations do not silently qualify; cardio models with mandatory console do not qualify. All estimates require pricing-manager approval before issuance.
4. Staff can enter an optional **contract line note**, e.g. "Includes adjustable bench". With consent it copies only to identical machines at the same site with the same model, pricing selection and console; individual serials stay intact. Different notes create separate displayed groups.
5. Customer quote PDFs now show the concise four-column Schedule 3 equipment view, including *every available serial*. Individual per-machine prices and raw internal source data are omitted, keeping the contract total separate. For the real M Club workbook (165 assets, 72 groups), the **PDF now has four pages, down from twelve**. Full source provenance remains in local quote data and the downloadable original register CSV; no historical evidence has been deleted.

## Limitations

- This is a price-guide and UI workflow enhancement, not approval of August 2026 RRPs, console mappings, Gold tariffs, or agreement legal wording.
- A selected reference `875G-AAA` must not be presented as a verified installed product variant or used to certify a console.
- Use an approved new quote/contract production process before sending anything externally. The source agreement is a *reference* for equipment layout, not an approved replacement template for all schedules or clauses.
- Local data remains single-PC SQLite until a shared authenticated deployment and backup plan are approved.
