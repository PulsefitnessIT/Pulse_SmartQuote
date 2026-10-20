# V10 invoice RRP completeness rule

Run a **whole-invoice price audit**, not just a model-match test. For every imported in-scope equipment line:
1. Prefer the existing catalogue selection if its current RRP agrees with dated source evidence.
2. Where the invoice states an exact SKU and corroborating machine description and the August 2026 catalogue has one RRP, calculate a **provisional** maintenance price. This includes non-console equipment such as benches, racks and cycles; explicit contrary console information blocks this path.
3. If a previously mapped/live RRP differs from the uniquely identified 2026 source RRP, show a provisional line using the 2026 source rather than leaving an older price unflagged; record prior catalogue RRP for reconciliation. Never mutate the live master, imported invoice, historical records or issued PDFs.
4. Where a legacy SKU is absent, only use a feature-specific reference if all qualified products have the same RRP. Otherwise show a named exception.
5. The quote summary and UI must report **priced lines and every unpriced SKU**. Never use historic invoice sale values as RRPs or treat guide prices as approved commercial rates.
6. Customer issue remains blocked until source RRP, scope and tariff questions are resolved.

A local acceptance audit of Phoenix invoice 0000000666 (20 pages, user-supplied) found 72 invoice rows: 41 in-scope equipment lines, 80 machine units and 31 excluded sales/accessory/warranty rows. 39/41 equipment lines obtained numerical prices; two (200C-AAB and SC240MA-AAA) remain flagged without confirmed current RRP. 25 already-priced lines have live RRP figures that differ from August 2026 source and are now provisional review amounts. No private invoice data or customer serials are committed to GitHub. Anonymised code-only regression tests prevent silent omissions.
