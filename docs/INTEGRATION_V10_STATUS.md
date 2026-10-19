# Pulse SmartQuote V10 — historical source integration

The `develop/v10` branch now includes read-only historical identity retrieval in `engine.py` and an authenticated `/api/catalog/history/{identifier}` lookup endpoint; the quotation table can display the evidence. Existing V9 live pricing and issued PDFs remain unchanged.

## Source files
The complete 2020–2026 source set is large. The local source processing recovered **7,145 unique SKUs** from **129,916** observations. This includes repeated revisions, source-only entries and a metadata-only 2021 export. There were 653 recorded alias codes, of which 178 matched multiple candidate SKUs. **These are unapproved historical candidates**, not quotable crosswalks.

The resulting portable index is `data/historical_catalogue_index.json` and the audit is `data/historical_catalogue_manifest.json`. They are included in the downloadable V10 preview ZIP prepared with the full 2020–2026 historical source files. **They are not yet committed to this GitHub branch.** Until those data files are committed, the engine safely returns no new historical evidence on installations cloned from this branch.

## Testing
The fully populated ZIP preview was tested locally: **69 Python regression tests passed**, with `SMARTQUOTE_AUTH=off` set only for test execution. The ZIP was checked for corruption and retested after extraction. The GitHub Actions workflow has been queued but its CI result has not yet been confirmed.

## Commercial protections
The 2020–2026 historical evidence is strictly identity-only. The provisional `data/pricing.json` tariffs, `data/catalog.json` RRPs, `data/configs.json`, and V9 quote history were not modified. Staff must still verify any replacement SKU/console and current approved RRP before contractual issue.
