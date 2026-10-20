# Pulse Fitness SmartQuote V10 — 2020–2026 historical equipment reconciliation

**Report date:** 20 October 2026  
**Status:** Source evidence integrated for internal pilot; archive completeness and commercial pricing NOT approved.

## Sources

- **19 physically supplied 2020–2024 master spreadsheets**, including eleven standard 2020 variants with `(1)` suffixes, the main 2020 `m` revision, and separate 2020 CH `i` file (all 13 physical 2020 revisions); 2021 `n`, 2022 `o`/`p`/`r`, 2023 `s`, 2024 `t`.
- **Recovered previous equipment index:** 2025 `U` and `V`, 2026 `W` references from historical SQLite archive. The ORIGINAL master XLSX files for those three revisions were not available in the current source set, so this evidence is NOT a confirmation of full completeness.
- Older duplicate recovered 2020–2024 observations were superseded with the newly supplied XLSX evidence when both existed.

## Results

| Indicator | Result |
|:--|--:|
| Source workbooks parsed (2020–2024) | 19 |
| Observations from physical XLSX files | 90,933 |
| Unique SKUs in physical files | 6,945 |
| Existing recovered SKUs before merge | 6,909 |
| Overlapping SKUs | 6,464 |
| Additional codes found in physical archives | 481 |
| Recovered-only codes preserved | 445 |
| **Total reconciled historical SKU identities** | **7,390** |
| Combined source observations represented by manifest | 123,852 |
| Alias codes | 231 |
| Ambiguous alias codes (human review) | 114 |
| Import failures | 0 |

**Year observations in manifest** (revisions may repeat the same equipment): {'2020': 57951, '2021': 4631, '2022': 15647, '2023': 6259, '2024': 6445, '2025': 26042, '2026': 6877}.

The 2021 file now has **4,631 observations**, with **4,622** on the Assembled Database worksheet; this resolves the former metadata-only year in the recovered pilot.

## Equipment catalogue behaviour

- Search a historical product code or model to find an evidence-only identity. Results display original variant, latest recorded console, latest master source and the number of original revisions seen.
- Retain older historical-only identities even if discontinued.
- Group identical machines at quotation stage but never automatically choose a console or modern replacement based solely on model family.
- **No live RRP, approved hybrid replacement mapping, tariff, price, customer quote or issued PDF has been overwritten.**

## Outstanding controls

1. **Source review:** The 2025 U/V and 2026 W details originate from recovered SQLite evidence, not a direct re-import of original workbooks. Validate original source revisions before marking archive complete.
2. **Aliases:** 114 old-code aliases resolve to multiple SKUs. Keep these as suggestions only; do not auto-select product configurations.
3. **Recovered-only:** 445 codes need verification against the original source where feasible.
4. **Commercial sign-off:** The staged August 2026 RRP list still has documented duplicate price discrepancies; apply only approved price/configuration mappings and the agreed hybrid legacy exceptions.
5. **Testing:** Automated tests are an internal pilot gate, not real-world customer issue approval. Staff UAT and final draft-PDF review remain required.

## Deliverables

- `historical_catalogue_index.json.gz` — compressed, integrated identity-only source index in the V10 pilot (plain JSON in the audit export).
- `historical_catalogue_manifest.json` — year/revision/sheet source control and readiness gates.
- `historical_full_provenance.json` — exact available source filename, worksheet and row for each SKU.
- `historical_equipment_history.jsonl` — 90,933 historical input observations from supplied physical masters (original source values excluding price data).
- `historical_reconciliation_review.csv` — 114 ambiguous aliases + 445 recovered-only SKU checks.
- `Pulse_SmartQuote_V10_Historical_Catalogue_2020_2026_Review.csv` — coordinator-readable 7,390-record catalogue review, no prices.

**Default policy:** Current-equivalent RRP for legacy equipment only after authorised product/configuration mapping; approved exceptions are separately reviewed. This historical archive never authorises prices on its own.
