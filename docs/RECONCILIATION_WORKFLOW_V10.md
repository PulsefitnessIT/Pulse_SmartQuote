# V10 — Repeatable matching and equipment price-gap management

## Purpose

The same legacy machines often appear in messy customer registers. SmartQuote now
supports an **operator-confirmed matching memory**, plus a manager worklist of
unresolved equipment across **open draft** quotations. This is not permission
to guess modern SKU equivalence or RRP.

### Reviewed matching memory

1. A pricing manager opens a quotation, edits a machine, verifies its exact
   physical machine SKU and console against an external source and ticks
   **Remember an exact, physically verified SKU for future imports**.
2. The manager must enter a meaningful evidence reference (at least 12
   characters). The choice is saved in `smartquote_local.db` as an exact source
   fingerprint and the confirmed *catalogue identity*, with reviewer and audit
   events. The data includes the source **name, code, model, make and console**;
   it excludes the customer, site, serial and other customer-specific fields.
3. When the same imported identity appears on another quotation, the matching
   assistant shows it as a **previously verified candidate**, explicitly
   requiring operator confirmation. It never auto-selects the stored SKU,
   applies a price, removes ambiguity, or overrides catalogue pricing.
4. Distinct legacy variants (`250G` versus `250G-0`), source consoles, and
   different product codes have different fingerprints. A different target for
   the same fingerprint is blocked until a manager **revokes** the earlier
   mapping with a documented reason. History remains in the audit table.
5. When the catalogue revision changes, stored identity advice is marked
   **stale** and the new current SKU, console and RRP must be reconfirmed.
   Duplicate or missing current SKUs are never offered for application.
6. The matching-memory module checks the active source catalogue at the time
   of lookup. The staff member's identity is read from the application session
   and manager/admin authorisation is checked on the API, not just the UI.

The local SQLite database is intentionally **NOT INCLUDED** in distributable
pilot ZIPs. Back up the existing `smartquote_local.db` before testing or
upgrading. Do not overwrite a live database with a new empty one. The
matching-memory rules are part of the same retained database as the saved
quotes and catalogue overrides.

### Priority equipment worklist

The Master Price List page has an **Equipment still needing a match or price**
section showing unpriced items across saved quotes with no issued PDF snapshot.
Staff can export a CSV and jump directly to the source asset inside a quotation.
Records are ordered by **number of units**. Source rows and groups are preserved;
no merges affect the original asset register. Imports with unknown quantities
continue to require verification even when an estimated price is available.

`GET /api/catalog/admin/matching-gaps`

`GET /api/catalog/admin/matching-gaps.csv`

`GET /api/catalog/admin/matching-memory`

`POST /api/catalog/admin/matching-memory/{rule_id}/revoke`

These endpoints use the existing role-protected catalogue administration path.

### Verified source example — M Club Newcastle

- 165 individual imported source assets; **72 condensed quotation groups**.
- 32 assets have calculated draft prices, but one priced record (source row 78,
  *Club Line Sled in Sand Black*) has an unverified quantity. Therefore there
  are **31 priced-and-not-quantity-flagged** units and **134 needing review**
  under the stricter operational worklist.
- The highest-priority unpriced groups are 21 Group Cycles (`224B-AAB`),
  14 treadmills (`260G` family), seven ellipticals (`280G` family),
  six upright cycles (`240G` family). No prices have been invented.
- The recovered identity-only archive has 6,909 SKUs, 231 aliases; 2021 is
  **metadata only** and not counted as a source year with equipment evidence.
  Archive completeness still requires the data-owner's separate review.

### Commercial release constraints

The underlying tariffs are still `Provisional` and have not been commercially
signed off. Memory confirmation is NOT tariff approval. Catalogue version
changes still invalidate draft pricing approvals. Historical indexes are
identity-only, not RRP sources. All 11 customer-specific tests that require
unavailable customer fixtures remain skipped in the repository CI. Signed-off
pricing, complete archive reconciliation, customer UAT and issued PDF review
are required before external distribution.
