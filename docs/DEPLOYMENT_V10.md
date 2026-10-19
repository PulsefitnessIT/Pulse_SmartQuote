# V10 installation, readiness and internal pilot build

The current `develop/v10` branch preserves the existing V9 quotation engine,
RRPs, tariffs, customer records and issued PDF snapshots.

## Historical archive deployment (developer / authorised admin)

1. Process **all** 2020–2026 CSV/XLSX master revisions with `historical_master.py`.
2. Check the generated `historical_review.json` and `historical_manifest.json`.
   Confirm that the archive is complete: an entry for a year does **not**
   prove that every revision for that year has been supplied.
3. From the SmartQuote checkout, run:
   `python install_historical_catalogue.py "C:\\PulseCSV\\Historical_Output"`
4. The installer checks all source years, import errors, SKU and alias counts,
   alias target existence and identity-only fields. It refuses historical
   pricing fields and does not modify `data/catalog.json` or `data/pricing.json`.
5. Any deployed indexes are backed up under `data/historical_backups`.
   Restart SmartQuote to reload the read-only evidence.
6. Sign in as a pricing manager / admin and open **Master Price List** to view
   the live catalogue and commercial readiness report.

## Commercial release gating

The production price and tariff file must be explicitly marked
`"pricing_status": "Approved"` **only following documented management
approval**. Do not edit that flag to bypass the review process. The admin
readiness panel's automated checks are **not** customer-issue permission;
real-customer quote regression, approved RRPs, legal renewal terms, and PDF
inspection are separately mandatory.

## Internal pilot ZIP

Build on an authenticated checkout with:

`python build_v10_pilot.py --output dist/Pulse_Fitness_SmartQuote_V10_Internal_Pilot.zip`

The build hashes every packaged file, verifies extraction integrity, contains
the current source and any installed validated historical identity index, and
excludes local customer database, user logins, raw source archives and backup
directories. The `BUILD_REPORT.json` within the ZIP states if the archive or
commercial approval is missing.

GitHub Actions produces this **pilot-only** ZIP when tests pass. A passing
GitHub build alone is not evidence that the missing historical index or
unapproved commercial prices have been resolved.
