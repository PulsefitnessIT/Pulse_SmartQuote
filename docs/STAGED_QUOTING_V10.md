# SmartQuote V10: drag-and-drop staged cover and sorted customer PDFs

## Coordinator workflow

1. Import one or more invoices, asset lists or agreements as usual. Existing equipment, serial numbers, source documents, quote records and previously archived PDF versions remain unchanged.
2. In the **Equipment start dates** panel, enter the initial contract start and common end date. Leave both blank for a standard annual quotation. All machines default to the initial start date.
3. Add the dates when additional machines should begin cover. Each date becomes a drop zone. Drag an equipment row onto a date, or tick multiple machine checkboxes and drag them together. Keyboard/touch alternative: use the **Cover start date** selector at the end of each equipment line.
4. SmartQuote saves the machine assignments in one bulk operation. Different dates for the same SKU remain separate from each other; individual source identities and serials remain unchanged.
5. PDF output always sorts machine item codes in ascending natural numeric/alphanumeric order (e.g. 20A before 100C). For staged cover, it shows each machine's start date, the common end date, its pro-rata period charge, the overall contract value through expiry and the full annualised amount when all equipment is covered.

## Price and rounding convention

- Regular Silver/Gold/Platinum pricing continues to use the normal RRP/tariff price engine. This feature does not alter equipment RRP, discounts or tariff policy.
- Pro-rata is `annual line charge × actual covered days / actual days in each calendar year`. The first and last days of cover are included. Leap years use a denominator of 366.
- For multi-year terms, the engine sums each affected calendar year before rounding each equipment line to pence. The overall staged contract amount is the sum of rounded equipment-line amounts; it can differ from `full-year price × term` because some equipment begins later.
- Staged dates are future contractual intentions. **This build does not automatically activate cover, invoice the customer, confirm the end of an existing warranty, create a Sage/Sicon contract or send a notice.** Those actions still belong to the operational process.
- Source RRP evidence, central commercial authorisation and the existing pilot-only PDF issue gates remain in place.

## Data model, validation and permissions

- Quote: `contract_start`, `contract_end`, and unique `stage_dates`. Equipment: optional `cover_start` (blank means the main contract start).
- All dates must be real ISO calendar dates within the signed contract period, with a common end date later than the start and a maximum of five years. Up to 40 later date groups are supported.
- The bulk assignment endpoint requires existing, included equipment IDs. An invalid group or unknown ID aborts the operation without changes. Used date groups cannot be deleted until the equipment is moved elsewhere.
- The original machine list and accepted/saved PDF snapshots are not rewritten; any subsequent quote changes are new revisions of the live draft.

## Routes

- `PUT /api/quotes/{id}`: update start/end dates alongside standard quote details.
- `POST /api/quotes/{id}/stages`: add a future group.
- `POST /api/quotes/{id}/stages/assign`: assign a group of IDs together (or blank date to return to main start).
- `DELETE /api/quotes/{id}/stages/{YYYY-MM-DD}`: remove unused group.

## Acceptance

Run `python -m unittest discover -s tests -p 'test_*.py' -q`. New regression tests cover natural code order in both ordinary and staged PDF output, inclusive days and leap years, staged totals, invalid dates, grouping separation, bulk assignments and deletion guards. The generated PDF was rendered and visually inspected on A4.
