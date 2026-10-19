# V9 — historical maintenance calculation importer

## What is new
* Import legacy Pulse .xls and .xlsx original maintenance calculation worksheets.
* Match original code and historical RRP, 3%/3.75%/9%/10%/13% source rates, quantities, original unit and line values.
* If agreement was imported first, old calcs annotate its existing 31 assets without disturbing serial numbers.
* If old calcs were imported first, they create machine rows. Importing the agreement later restores serials and reattaches calculation evidence.
* Current catalogue RRP drives the new quote when available. Two unpriced Skipton items may display historical-only RRP reference estimates, flagged as incomplete.
* The local pilot labels the original 20%, 10%, 10% factors as HISTORIC source rules; does not silently carry them into new customer prices.
* Historic model identity index created from 2025 Assembled Database (6,704 worksheet rows, 706 model families). This is NOT the RRP price list.

## Crucial source facts
* Previous equipment-only calculation before uplifts £9,788.1725 (unrounded).
* Legacy formula multiplies by 120% = £11,745.807, then two separate 110% factors = £14,212.42647, rounded £14,212.43.
* Source 230H Air Bike has manual £79.20 yearly uplift in the original calculation.
* 31 equipment lines, 55 machines. 29 newer family-RRP estimates + two only historic RRP references.
* Existing agreement has a fixed-price extension option; new rates are not presumed contractually permissible.

## Security / governance
* Upload only trusted internal workbooks. The importer is read-only and does not execute macros.
* Historic price overrides are never automatically stored as live catalogue RRPs.
* Do not rely on provisional current-family substitutions without equipment/console checks.
* Signed quotes remain immutable; old calcs import is disabled for a quotation with issued versions.
* Before production: central deployment, approval of equipment rates, contract terms and quoted output, and staff UAT.
