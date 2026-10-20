# SmartQuote V10 — One Upload Panel

The Quote Builder now has **one drag-and-drop / Choose files panel** instead of separate cards for invoices, asset lists, existing maintenance agreements and previous calculations.

## Coordinator instructions

1. Drag or choose one or more documents. The supported formats are PDF, Excel (.xlsx/.xls), CSV, TSV and TXT.
2. Review the resulting **Files ready for review** queue, which shows file names, file sizes and an editable document-type selection.
3. Excel and CSV documents default to **Equipment / asset list**. For old calculations in .xlsx, change the dropdown to **Previous calculations**. Files in legacy .xls format use the old-calculations importer.
4. PDFs named like invoices or maintenance agreements receive a suggested document type. Unclear PDF filenames require manual selection; the app does **not** silently guess their contents.
5. Click **Review N sales invoices** to preview up to ten invoice PDFs for one site in a single batch. Review other file types individually with the Review button next to that file.
6. Every existing backend preview/confirmation is retained. Cancelled, failed or unconfirmed files remain queued. Only successful imports remove files from this browser queue.
7. Existing safeguards remain: duplicate serial checks, invoice content-hash checks, lease delivery site separation, old invoice sale values never used as current RRP, and commercial approval required before issuing.

## Constraints and important behavior

- The queue lives in the current browser page only. It is not a quotation attachment until the user deliberately reviews and confirms an import.
- A previous maintenance agreement may replace the draft equipment schedule, but the existing **replace** confirmation remains required when the quotation already contains machines. Mixed file types are **not** imported or replaced automatically.
- PDFs, scans or variants not supported by the existing importer still need staff review.
- Historical calculations and equipment lists retain distinct import logic, even though both are uploaded in one place.
- The app is still an **internal pilot**, not a production-approved pricing service.
