# Pulse Fitness SmartQuote V9 — historical-calculations pilot

# Pulse Fitness SmartQuote V6 — Controlled Local Pilot

**Status: PILOT — do not issue commercially binding customer quotations from this build.**
The V6 application supports a genuine coordinator workflow, but it is not a central multi-user production service. Company-level approval of rate policy, maintenance-package terms, hosting, backups, IT security and Sage/Sicon data synchronization is still outstanding.

## What is included

- Drop-and-drop XLSX/CSV asset list import, including unusually formatted headers and legacy equipment codes.
- Search equipment by model, description, manufacturer and SKU, with suggested alternatives for unknown machines.
- Silver, Gold and Platinum pricing, source RRPs, mapped tariffs and explicitly identified RRP-based estimates.
- Monthly equivalent and annual line price, discounts applied to manual and catalogue rates, and unit × quantity penny reconciliation.
- Quantity checks: missing, non-numeric, zero, fractional and negative spreadsheet quantities are highlighted and **block completed PDFs** until corrected.
- Add, edit, exclude and resolve equipment directly in the quote; standard quoting has no separate review screen.
- Pulse-branded, invoice-inspired PDF, retained as immutable numbered snapshots at the application layer with SHA-256 integrity checks.
- Customer/site history lookup, routine auto-save, local quote register, manual pipeline labels, CSV export and summary counts.
- Restricted master-data administrator tools: edit item, preview import, apply changed price/console/model/category information and retain edit log.
- Local staff accounts with salted PBKDF2 password hashes, expiring bearer sessions, coordinator/manager/admin roles.

## 1. New Windows installation

1. Install **Python 3.11 or later** (tick **Add Python to PATH**).
2. Extract the ZIP into a folder with appropriate Windows user permissions, e.g. `C:\Pulse\SmartQuoteV6`.
3. Double-click **`start_windows.bat`**. Dependencies install and the first run asks you to create a local administrator username/password. The password must have at least 12 characters.
4. The application opens at **http://127.0.0.1:8765**. Sign in using the account just created.
5. Drag in `samples/Pulse_Messy_Asset_List_Sample.xlsx` and test the equipment review workflow.
6. Use **Generate Quote PDF** to create a test quotation. Completed pilot PDFs are **watermarked** and stored as numbered versions. Unresolved rows produce drafts.

Do **not** change the launcher to `0.0.0.0` or host this on an internet-facing computer. The local sign-in is a temporary access control, **not** corporate single sign-on, network hardening or an approved security architecture.

## 2. Upgrade from V5 without losing existing quotations

1. Exit V5 and make a safe backup of its complete folder.
2. Extract V6 to a **new folder**, not on top of V5.
3. If V5 has existing local quotes or catalogue edits, copy `smartquote_local.db` from V5 into V6 **before the first V6 run**.
4. Start V6 and create its first administrator account when prompted. Existing V5 data will remain available; V6 adds its own tables on first use.
5. Old PDFs previously downloaded from V5 are **not** retroactively archived in V6. Only PDFs generated using the new versioning function receive immutable application snapshots.

The database contains customer information and may contain staff password hashes. Store backups in a controlled, access-restricted location.

## 3. Accounts and roles

To create another staff member, open a terminal in the installed application folder and run:

```bat
py manage_users.py add contracts01 coordinator
py manage_users.py add pricing01 manager
```

A coordinator can prepare quotes, correct machines and record a manual customer-response status. Managers additionally administer equipment master data. The first administrator can run `manage_users.py add NAME admin` as needed. For a company-wide deployment, replace this local account store with centrally administered SSO and corporate identity lifecycle controls.

## 4. Typical workflow

1. **Create** a quotation and upload an asset spreadsheet.
2. Resolve only genuinely missing matches, invalid quantities and conflicts. A corrected line immediately reprices.
3. Select the customer's Silver, Gold or Platinum package and enter the discount.
4. Choose an existing customer/site suggestion or enter the details once.
5. Select **Generate Quote PDF**. If the quote is complete the system archives a PDF version; otherwise it generates a visible draft.
6. **View saved PDF versions** retrieves original PDF bytes without recalculating them.
7. Optionally record a manual customer response for local reporting. This does **not** send email or update Sage/Sicon.

## 5. Master catalogue process

Managers use **Master Price List**. Preview and inspect changed data before applying it. Source spreadsheet import recognises clean CSV/XLSX rows with **Product Code / Description / RRP**. Changes to descriptions, RRP, model, category, group and console trigger an update. Duplicate conflicting codes and invalid lines are blocked from the import action.

The supplied **2025 Website Layout Master Input** workbook is useful for identity and descriptions but does not present a directly usable current-RRP price column in this application's required three-column layout. Do **not** treat it as an approved replacement price list. The clean **Pulse Fitness - Contract Quoting.xlsx** SKU Catalogue provides the pilot's initial RRP basis. Some original rates and mappings are provisional and require Pulse commercial approval.

- Asset import maximum: 25 MB per file.
- Catalogue price import maximum: 60 MB, but complex manufacturing/costing workbooks must be normalised into a clean SKU/RRP extract.
- The source JSON is preserved. Master edits and import audit are recorded in the local database.
- Current draft quotes reprice when loaded after a catalogue revision. Previously **archived PDF versions never change**.

## 6. Test and backup

Run automated tests in a **separate test copy** of the application (not a live installation):

```bat
run_tests_windows.bat
```

Use `python backup_database.py` while the application is installed to make a timestamped, integrity-checked database backup. Store the backup somewhere secure and separate from the PC. This is **not** automated corporate backup, and a recovery drill is still required before go-live.

## 7. Important limitations

- **Do not use V6 for unrestricted customer quoting yet.** Valid pilot PDFs carry a watermark; commercial prices have not all been signed off.
- Local SQLite is a single-computer pilot register, not a centrally administered team database or automatic cross-PC sync.
- Password authentication has no corporate SSO, MFA, centralized lockout, TLS gateway or enterprise monitoring.
- Automatic RRP-derived estimates may not cover actual cost-to-serve, travel, parts, PPM or maintenance liability; no historical Sicon economics are integrated.
- No email sending, customer e-signature, integrated contract activation, automated follow-up or verified Sage/Sicon sales pipeline.
- Terms, package inclusions, service visits, exclusions and legal wording must be approved by the Pulse commercial/legal owners.
- The manual pipeline field is user-recorded, not a verified payment or acceptance event.

See **V6_RELEASE_GATES.md** and **PRODUCTION_ROADMAP.md** for outstanding work and acceptance criteria.

## V7 additions — 16 October 2026

See **V7_RELEASE_NOTES.md** and **README_V7_START_HERE.txt** for the latest changes.

- The supplied **KA Leisure** asset spreadsheet imports, including all 150 machine records, serials, site moves and unusual headers.
- Digital Pulse maintenance agreement PDFs can be uploaded via **Upload previous agreement (PDF)** to prepare renewals. The supplied Skipton agreement imports all 31 lines (55 units), including its fixed-price extension warning.
- The equipment-line editor provides a console suggestion list with a free-text fallback.
- Administrators now have a **Staff Users** screen to create, deactivate and reset local user accounts; the command-line `manage_users.py` is still available.
- When several imported rows are identical at the **same site**, a coordinator can apply one confirmed catalogue match to those rows in bulk, retaining their serials.

**Note:** The original V6 statements above remain relevant where not explicitly changed here. This update has not deployed SmartQuote to a shared host or replaced local accounts with SSO.

## V8 changes - October 2026
See `README_V8_START_HERE.txt` and `V8_RELEASE_NOTES.md`. The existing Skipton renewal can be reopened, with automatic indicative pricing for recognised historic machine families. Still TWO unpriced codes. The partial total is not a full renewal price, and the 2026 fixed-price extension must be reviewed.
