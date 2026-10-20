# SmartQuote V10 — legacy equipment RRP policy (20 October 2026)

## Commercial decision confirmed by Pulse Fitness

**Default: current equivalent RRP.** Use an identifiable current product with exact product code, model, console and verified RRP where possible, while retaining original serial numbers, source rows, model and historic provenance. An RRP from the 2026 source spreadsheet is evidence, not automatically a signed-off tariff.

**Approved exceptions:** Document why a legacy machine is not adequately represented by a current equivalent, original source, independently validated exception RRP, specific installed console, review expiry and authorisers. Only the independently reviewed record becomes a source of evidence. A second manager must approve a proposed exception (the control also applies to equivalence proposals).

**Unknown console:** Do not default to cheapest, most expensive or newest option. Leave `Unconfirmed`, present exact alternatives for human identification, and do not apply an assumed equivalent to quote totals. An old record without a confirmed console is insufficient to automatically select a current configuration.

## Workflow and controls

- Pricing managers create a *pending* recommendation under Master Price List. Coordinator accounts cannot create, approve or revoke it.
- Validation rejects unrecognised/conflicting current SKUs and mismatched known console configurations.
- A different authorised manager must independently approve, with a written evidence check. This is an exception/equivalence register approval, **not** global RRP or maintenance tariff approval.
- A source or catalogue revision change makes previously recorded equivalence evidence stale; a time-expired exception does not pass for reuse.
- Original imported code must match the signed rule exactly. No approximate surname/family matching, no automatic model substitution, no auto-selection, no implicit RRP overrides.
- Per-quote equipment matching review can surface the rule, but the original user must still confirm the actual configuration for each site and quotation.
- All proposal/approval/revocation actions retain local immutable audit rows in `smartquote_local.db`, which must be backed up when migrating. The pilot ZIP excludes that database.

## Remaining release dependencies

- Historical master input revisions 2021–2024 and reconciliation with already supplied 2020, 2025 and 2026.
- Authorised commercial sign-off for the latest master list, console/voltage/finish configurations and maintenance tariff formula, plus resolving conflicting SKU RRPs.
- Staff acceptance testing with M Club and other complex asset lists, and independent review of the PDF output.

**Internal pilot only** until these dependencies are completed. Approval of the *policy* is not authorisation to issue customer prices.
