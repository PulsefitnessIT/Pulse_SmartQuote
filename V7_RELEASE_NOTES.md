# Pulse Fitness SmartQuote V7 — Import, Renewals, Consoles & Staff Access

## Fixes for real files supplied on 16 October 2026

**KA Leisure — Kit at KA Leisure Sites - MASTER.xlsx**
- Correctly detects worksheet `Pulse Assets (2026)` and all **150 asset rows**.
- Recognises `Name`, `Location`, `Model Code`, `SerialNumber`, `Site`, and optional `Repair`.
- Preserves numeric serial numbers without unwanted `.0` suffixes and keeps leading zeros when Excel stores them as text.
- Supports one-asset-per-row spreadsheets: one row with an explicit serial means one machine; missing serial and missing quantity remains a correction task.
- Parses relocated equipment into the current destination and preserves the source location/status on each machine record.
- Displays site per equipment line. The PDF includes each site's name when the uploaded list spans multiple locations.
- Retains all unpriced/uncertain machines; it never substitutes an unauthorised product price.
- Can apply one verified catalogue selection to other **identical** equipment rows at the same site, while preserving individual serial numbers.

**Previous Maintenance Agreement (digital PDF)**
- New **Upload previous agreement (PDF)** command. Select a digital, selectable-text Pulse agreement with Schedule 3 machine tables.
- Reads the customer's name, site, address, contract reference, old agreement package and dates, previous annual price, machine descriptions, code, quantity and serials.
- The provided Skipton agreement imported **31 equipment lines and 55 units**, across pages 3 and 4.
- Old annual price **£14,212.43** is retained as a comparison, **not reused as a new product price**. All equipment is priced from the current catalogue where matching is substantiated.
- An option to extend at the **same annual price** is flagged. A specific confirmation is required before a potentially different renewal quote can be issued. This avoids silently contradicting an existing customer entitlement.
- Ambiguous and obsolete product codes remain unpriced until identified or given a documented manual rate. A renewal can remain a **draft** even though every old machine was imported.
- Not a general scanned-PDF/OCR importer. It supports searchable digital Pulse agreement forms; other layouts should be assessed separately.

**Console selection**
- Equipment editor now provides a searchable choice list of frequent consoles plus free-text entry for old or third-party products.
- The chosen console is shown in equipment review and PDF details. Selection does **not** imply a different RRP or tariff; where a console changes the actual SKU, select the correct catalogue variant.

**Staff accounts**
- A new **Staff Users** navigation item appears only to administrators.
- Create coordinators, managers or administrators; activate/deactivate accounts; reset passwords (invalidates active sessions).
- Managers can maintain catalogue/prices, coordinators can quote, administrators additionally manage users.
- Controls prevent self-deactivation and the removal of the final active administrator.
- Local user accounts remain in `smartquote_local.db`; this is **not** yet multi-PC access, identity federation or production SSO.

## Operational limitations
- The application is a controlled local pilot; **not approved for unrestricted customer issue**.
- The KA asset list yields imported rows, not necessarily fully priced rows. Machines without exact codes/configurations still need review.
- The Skipton agreement has old models requiring confirmation of present-day equivalence and console configuration. Do not imply that the current-price quote is automatically valid for an existing fixed-price extension.
- Workflows still require UK package scope, cost-to-serve and price policies to be commercially signed off before external issue.
- Production requires secure centrally hosted multi-user data, SSO, backups and verified Sage/Sicon integration.

## Upgrade
1. Close V6. Copy/back up the entire V6 folder and `smartquote_local.db`.
2. Extract V7 to a **fresh folder**. Copy the V6 `smartquote_local.db` file into V7 **before starting V7**.
3. Launch `start_windows.bat`, sign in with the existing V6 user credentials. Previously issued PDF versions remain saved in the database.
4. Test the KA workbook as a normal asset list, or choose **Upload previous agreement (PDF)** for a renewal.
5. Administrators can now use **Staff Users** from the sidebar, without the command-line tool.

## Developer verification
- Review `tests/test_v7_imports.py` for reproduction tests. The full-upload cases require the actual user-supplied files at `/mnt/data` and will skip if absent in a customer installation.
- Execute `run_tests_windows.bat` against a **separate test copy**; never run test scripts against the live customer database.
- Start with the normal test account-setup workflow; do not include the test DB or credential from development.
