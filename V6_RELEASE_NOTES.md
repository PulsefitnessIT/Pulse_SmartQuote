# SmartQuote V6 — 16 October 2026

## 39 regression tests passed

This update follows the founder's V5 release audit and prioritises both coordinator efficiency and price integrity.

### Changes

1. Imported quantities that are empty, zero, negative, fractional or text now show an actionable quantity correction. An invalid quantity blocks issuing a completed PDF until it is corrected; no silent guess of one unit.
2. A manually entered annual unit base rate now receives the quotation-wide discount, consistent with catalogue pricing. Manual price evidence remains mandatory.
3. Annual line totals now reconcile to the displayed rounded unit price × quantity. This can change V5 totals by pennies where intermediate unrounded amounts previously appeared.
4. Master-price imports now compare console, model, group and category, not only name and RRP. Conflicting and invalid records are flagged.
5. Local users have sign-in accounts, role-restricted pricing administrator endpoints and expiring tokens. No shared default credentials are distributed.
6. Completed quotation PDFs are saved as numbered archived versions with original JSON snapshot, hash and issue date. Re-downloading unchanged quotes reuses the latest version rather than creating duplicates.
7. Issued PDF retrieval checks the stored SHA-256 digest and refuses to return damaged content.
8. Existing customer details can be reused, normal form changes auto-save, and Silver/Gold/Platinum package switching immediately recalculates the quote.
9. Local pipeline stage recording, reporting summary and CSV register export are available; these are **not reconciled to Sage/Sicon**.
10. Internal pilot PDFs carry **PILOT - NOT FOR CUSTOMER ISSUE** until Pulse completes go-live policy and IT approval.

### Preserved from V5

- Direct XLSX/CSV uploads, legacy code matching, ambiguous machine suggestions and edit-line functionality.
- Silver/Gold/Platinum; single standard underlying source tariff, no visible price-band selector.
- Invoice-style Pulse-branded PDF layout with price, VAT and exclusions.
- Equipment catalogue and managed price-list editor.
- No separate per-equipment approval process for routine user workflow.

### Not yet implemented

- Shared central cloud database, central identity/SSO, enforced corporate pricing authorisation, real margin model, live Sage/Sicon service contract integration, verified delivery/acceptance, automatic renewal and production DR.
- End-to-end GUI browser UAT on a real workstation: the development execution environment blocks loopback browser navigation.

The source data is unmodified; local overlays/quotes remain in `smartquote_local.db`. Do not unzip V6 on top of V5. See README for upgrade and role setup.
