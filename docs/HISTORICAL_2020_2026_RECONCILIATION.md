# Pulse Fitness SmartQuote V10 — reconciled 2020–2026 historical equipment library

**Date:** 20 October 2026  
**Status:** Historical identity archive deployed for internal testing, NOT commercial sign-off.

## Verified source set

- **19 physical master files:** 2020 revisions a–m (including the separate CH i file); 2021 n; 2022 o, p and r; 2023 s; 2024 t.
- **Three 2025–2026 recovered revisions:** 2025 U/V and 2026 W from a prior equipment-audit SQLite snapshot; original workbooks for these were not provided with the current upload.
- All 19 actual source workbooks were parsed successfully with source year/revision/worksheet/row evidence.

## Reconciliation summary

| Measure | Count |
|---|---:|
| Workbooks physically examined (2020–2024) | 19 |
| **Equipment observations from physical workbooks** | **90,702** |
| Distinct equipment codes in physical masters | 6,714 |
| Recovered historical SKUs before merge | 6,909 |
| Product codes present in both data sources | 6,464 |
| Newly found equipment codes | 250 |
| Recovered-only historical codes retained | 445 |
| **Total reconciled product identities** | **7,159** |
| Combined observations represented in source manifest | 123,621 |
| Historical alias codes | 231 |
| Alias codes with multiple possible targets | 114 |
| Source workbook parsing failures | 0 |

**2021 fixed:** The actual n workbook contains 4,631 equipment observations, including 4,622 in Assembled Database. The old recovered catalogue incorrectly marked 2021 metadata-only.

**Important data-cleaning control:** The 2020 j workbook has a Suppliers worksheet with **231 supplier-account records** using Code and Stock Item Name columns; these are not equipment. We have excluded that entire worksheet from the equipment index and observation totals. Twelve genuine numeric 3-digit machine codes remain (e.g. 302 and 307). Current results exclude supplier accounts.

**Non-standard historical codes:** 12 old identity labels contain placeholders or spaces/punctuation; these remain evidence for tracing historical records but require manual verification before SKU assignment.

**Revision observations by year** (revisions duplicate SKUs and are not machine quantities): {'2020': 57720, '2021': 4631, '2022': 15647, '2023': 6259, '2024': 6445, '2025': 26042, '2026': 6877}.

## Controls and remaining approvals

- The index only contains historical identity, model, status, console, source and revision data. It **cannot approve RRP**, modern equivalent, console replacement, Silver/Gold/Platinum tariff or customer issue.
- Archive readiness remains **Not approved** until an authorised Pulse data owner verifies the source completeness and 2025–2026 physical files.
- **114 ambiguous aliases** remain reviewer-only. No automatic substitution where an alias has multiple targets.
- **445 recovered-only codes** require later verification against primary source evidence.
- Hybrid price policy remains current-equivalent RRP by default, with individually documented legacy exceptions requiring independent approval.
- Existing live `data/catalog.json`, `data/pricing.json`, customer quotes and issued PDF records have not been modified.

## Included outputs

- `historical_catalogue_index.json.gz` in V10 app (compressed index, source-identities only).
- `historical_catalogue_manifest.json` (physical and recovered sources, year/revision provenance, data-owner approval gate).
- `historical_full_provenance.json` in audit ZIP (full row-level evidence for 7,159 codes).
- `historical_equipment_history.jsonl` in audit ZIP (90,702 physical source observations excluding suppliers).
- `historical_reconciliation_review.csv` in audit ZIP (alias conflicts and recovered-only codes).
- `Pulse_SmartQuote_V10_Historical_Catalogue_2020_2026_Review.csv` in audit ZIP (spreadsheet-readable equipment identities without prices).
