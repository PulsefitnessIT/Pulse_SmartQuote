# Pulse Fitness SmartQuote V10 — Staff-first workflow pilot

## What has changed

SmartQuote's quotation builder now has a context-aware **Your next step** prompt.
The intended sequence is: **import preview → review unpriced/uncertain machines →
complete customer/contract details → generate a controlled draft PDF**. The
existing tariff source remains provisional and must still receive commercial
sign-off; a completed workflow is not evidence of commercial approval.

### Import without accidental loss of data

1. Select an Excel (`.xlsx`) or CSV equipment list, or drag it into the upload
   area. The existing parser reads the file into an **unsaved preview**.
2. The preview shows detected sheets, original physical asset records, total
   units, *reversible grouped display lines*, recognised machine identities,
   draft-priced rows, quantity exceptions and an equipment sample.
3. Review the detected quantities and headline warnings, then **Add assets to
   quote**. If the quote already has equipment, the preview explicitly warns
   that these rows will be appended rather than replacing existing records.
4. SmartQuote checks a SHA-256 hash of the uploaded file. The same bytes cannot
   be imported twice into the same quotation, even with another filename.
   Legacy pre-V10 imports without stored hashes remain unaffected.
5. The file hash is checked again on commit. A file changed between preview
   and commit requires a fresh preview. Original source rows and all retained
   custom columns are still available in **Original asset register CSV**.
6. **Undo last import** removes one untouched, most recently imported
   spreadsheet batch only. Undo is rejected if any member has been edited,
   confirmed, deleted, or if a PDF quote version has been issued. Historical
   imports lacking batch markers are never eligible for automatic undo.
   Every successful undo is recorded in quote events.

### Find and reuse saved quotes

The quote register can search quote number, customer, site, contact, account
number or contract reference and filter by recorded commercial status. It
searches server-side across saved quote records, not just the first 60 visible.
Results are capped to prevent massive responses on busy installations. Commercial
status is a staff-entered value; it is not a Sage-confirmed result.

### Keyboard accessibility and status

- **Ctrl+S** (or Cmd+S) saves the quote detail fields.
- **Alt+N** opens the next unresolved machine in the builder.
- **Esc** closes a dialogue. Visible buttons, fields and links have a
  keyboard focus outline.
- Changes to quote detail fields still save when leaving a field. Requests
  are now serialized to avoid out-of-order responses overwriting saved quote
  details. The save area shows progress and errors.
- **Quick help** summarises how staff should review the equipment and where
  provisional prices require separate approval.

### Actual customer example used for regression

`M Club Newcastle.xlsx` in local isolated tests:

- 165 source asset rows and 165 physical units
- 72 grouped display/quotation rows
- 32 draft-priced rows and 32 identified records
- Two quantity checks and eight identity checks
- Preview produced no quote mutations; commit preserved all original records
- Re-importing identical bytes returned 409 and added no assets
- Undo of the untouched last batch restored the empty quote

The workbook and customer details are **not committed to the source repository**.
The test suite also exercises a synthetic 165-row register and import history.

### Release boundaries

- Historical library still lacks a fully reconciled, signed-off 2020–2026
  source archive (notably the recorded 2021 metadata-only revision).
- Identifying a machine is not the same as confirming its current SKU, console,
  approved RRP, tariff or third-party eligibility.
- The previous commercial-price `Provisional` designation remains in force.
- Customer-specific fixture tests are skipped in GitHub without the private
  files. Run staff UAT on real messy lists before a wider release.
- Keep a backup of `smartquote_local.db` when upgrading. It contains the live
  quotes, audited matches and local user data, and is excluded from pilot ZIPs.
