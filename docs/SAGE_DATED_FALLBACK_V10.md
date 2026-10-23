# V10 dated Sage fallback and low-click quoting — 23 October 2026

## Source priority
1. Exact current August 2026 Master Price List RRP remains authoritative.
2. If no usable current Master RRP exists for the exact imported machine code, an authorised manager's dated Sage stock Sales Price export is a **provisional static price reference**. This DOES NOT prove that Sage Sales Price is retail RRP; do not silently update the official master catalogue.
3. Source conflict, wrong/missing exact code, parts/accessories, invalid/zero prices, missing cover/rate and conflicting console configurations stay as genuine exceptions. Never use the selling price on a customer invoice.

Sage fallback prices calculate Silver, Gold and Platinum automatically via the current tariff engine without coordinator machine-reselection. For recognised exact codes, the price record carries the original Sage sales price, reference name/group, source date, snapshot ID and annual review due date. The StepMill category uses the 3.8% base rate. Non-Pulse equipment uses the third-party rate group, which is marked for commercial review.

## One manager upload, no coordinator clicks
A pricing manager visits Equipment & Prices > Manage master prices > Sage price fallback and uploads the Sage XLSX/CSV dated export once. Compatible product codes become available to all staff using that installation's local database. Subsequent imports retain historical gzip-compressed snapshots in the same local database. The portable Windows user package may contain a preloaded original Sage export named `data/sage_price_seed_2026-10-23.xlsx`. If present and no previous Sage snapshot exists, it is installed automatically on first launch. Existing Sage snapshots and old quote versions are never overwritten.

The provided 23 October 2026 Sage static export has 21,063 product codes; 7,442 unique positive-priced equipment codes pass initial group and price checks; 2027-10-23 is the next annual source review due date. Parts and non-equipment records are excluded. These are fallback candidate codes, not 7,442 approved contract prices.

## Review / governance
Manager-only status displays source date, source owner, machine count and annual due date. Expired source prices create ONE quote-level issue, not a click on each machine, and require the manager to upload a refreshed export. Current provisional tariff sign-off remains a single separate quote-level blocker. No false commercial approval button is added. An authorised sign-off of the actual tariff and cover remains essential before issuing a customer-binding PDF.

## Staff quoting clicks
Uploaded invoices/asset lists still use one automatic content preview and a final explicit Import confirmation to prevent accidental changes to customer equipment; approved, correctly identified machine rows do not prompt for price-source selection or repeated reviews. Select a package, provide customer/site, generate PDF. All changes are covered by regression tests and Windows portable build checks.

## Installation and backup
The Sage snapshot lives inside `smartquote_local.db`, so include this database when migrating or backing up a staff installation. Save the complete previous app folder before upgrading. This pilot is not a hosted multi-user production service.
