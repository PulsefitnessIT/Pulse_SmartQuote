# V10 historical equipment master — Stage 1

The first V10 increment introduces a **separate**, source-traceable import
pipeline. It does not replace V9 catalogue files or silently adjust any RRP,
tier, rate, signed quote or customer record.

## Run (Python 3.11+, no external packages required)

1. Make a folder outside the GitHub repository containing the 2020–2026
   master CSV UTF-8 exports. Keep year and revision in each filename.
2. From the SmartQuote repository root, on the `develop/v10` branch, run:

```powershell
py historical_master.py "C:\PulseCSV\Converted_CSV" --output "C:\PulseCSV\Historical_Output"
```

3. Review `historical_manifest.json` for missing/failed exports.
4. Review `historical_review.json` for duplicate SKUs, inconsistent console
   assignments, and ambiguous aliases.
5. Check the canonical file against historical source records before promoting
   any alias into the live quoting engine.

## Outputs

- `historical_equipment_history.jsonl`: every supported source observation,
  retaining source filename, year, revision, worksheet and row.
- `historical_equipment_master.json`: latest-seen representation keyed by SKU
  with an explicit source lineage. **Identity only; no approved RRP.**
- `historical_aliases.json`: old code -> candidate current codes.
  **Candidate evidence, not approved crosswalks.**
- `historical_review.json`: detected conflicts and changes.
- `historical_manifest.json`: imports, counts and failed sheets.

## Known limits and required next stages

- The first 2021 file supplied is small; do not assume complete annual coverage.
- `.xls` must be exported to CSV UTF-8 before importing.
- An absent record in one revision is not proof the model is discontinued.
- An `Old SKU` value of 0 or a bare number is treated as unusable.
- Multiple worksheets and layouts require manual spot checks.
- Current display picks the latest observation, but neither that choice nor a
  legacy alias means the quoted product and console are approved equivalents.
- The source year is detected in the filename; files without a year are skipped
  and shown in the manifest.
- Prices are intentionally excluded even when source files include an RRP
  column. Commercial pricing requires a separate approved dataset.
- **This initial change does not mean the full historic archive has been
  processed or deployed into the V10 quote builder.**

## Validation

Run `python -m unittest discover -s tests -v`. A GitHub Actions workflow runs
the tests for development commits and PRs. Historical customer-dependent
regressions may skip when the private customer files are not available.
