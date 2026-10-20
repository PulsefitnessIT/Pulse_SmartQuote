# V10: Multiple Pulse Sales Invoices → One Maintenance Quotation

**Staff pilot only.** Applies to a single equipment delivery site per quotation. This adds support for the 2021 numbered-item Pulse invoice design, alongside the earlier tested Evesham invoice design. Does not imply all invoice formats or scanned PDFs are supported.

## Contract coordinator workflow
1. Create/open an unissued maintenance draft quotation.
2. Select **Add invoices (PDF)** and choose up to **10 at once** (max ~70MB original PDFs). More may be added in subsequent batches.
3. Review each invoice separately: reference, delivery site, billed-to party, new machine count, original SKU, number of serials, and non-maintenance products separated for optional scope review.
4. Confirm the entire group. Validation is **all-or-nothing**: site/serial/code conflicts block every invoice in that batch rather than partially adding data.
5. SmartQuote combines identical equipment for a short maintenance schedule, retaining the original SKU, invoice reference, each individual serial number and source invoice page. The existing customer data and approved PDF snapshots remain unchanged.

## Verified Phoenix 2021 example
- Invoice `0000000666`, 25 August 2021, 20 pages; purchaser billed: Siemens Financial Services Ltd; **delivery site Phoenix Pool & Gym**.
- 72 source invoice lines, of which 41 were conservatively classified as serviceable equipment candidates (80 units, 77 documented serials). 31 sales/software/accessory/loose-weights/other source lines are retained as separately reviewable evidence, not silently inserted as maintenance assets. Three candidate units lack serials and require confirmation.
- `260G-ABB` (7 treadmills) and `280G-AAZ` (4 cross trainers) retain their exact console-specific invoice SKU. `305H-AEP` and other 10.1" console-equipped resistance SKUs likewise retain exact identity. 21 `224B-AAB` cycles remain one line and all 21 serials are captured despite crossing three PDF pages.
- The invoice mentions a 5-year warranty and annual servicing. **The contract coordinator must confirm warranty start/end and any existing entitlements**; SmartQuote must not automatically assume new payable maintenance cover.
- Billing entity is **not** automatically populated as the legal maintenance-contract customer when it differs from the delivery site; staff must confirm that separately.

## Duplicate rules
- Same document fingerprint or invoice number already imported: skipped, not counted again.
- Same serial/SKU within the site: skip that previously recorded unit, preserving evidence for other newly delivered units on the second invoice.
- Same serial but *different* SKU: block the entire batch for physical/invoice investigation.
- Overlap where printed quantity and serial list do not reconcile: block rather than guessing the quantity.
- Equipment without a unique serial may be separately invoiced legitimately; the quote flags those lines for review rather than assuming duplicates.
- Different delivery sites are **not** automatically combined into one location-based equipment schedule; this requires a separate multi-site contract feature or separate site schedule.

## Commercial protection
The original invoice's **sale** values (even £0 sales) must never become maintenance RRPs. Exact invoice SKUs establish *purchase identity*, not proof of an unchanged 2026 console or an approved replacement value. If today's catalogue lacks the historic SKU, staff do not have to pick an arbitrary modern alternative simply to produce a price; the pricing team must approve the current-equivalent RRP/legacy exception under the established hybrid policy. All newly imported quotations are drafts until pricing and contract terms are verified.

## Scope limits
Selectable-text PDFs in the supported styles. Scans, credits, returns, materially different invoices, legal-customer ambiguity, and optional maintenance of exercise accessories require a designated review workflow; don't guess. Large PDF batches should be split into smaller uploads.
