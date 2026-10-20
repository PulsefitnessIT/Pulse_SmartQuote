# SmartQuote V10 — Multi-group review workbench (20 October 2026)

## Staff workflow

1. Import an asset list using **Preview → Add to quote**. Check the source quantities before importing.
2. Go to **Equipment list → Review several groups**. The workbench prioritises physical machine counts, not worksheet order.
3. For each suggested group, confirm an **exact product SKU** using the machine label, console or an engineer's recorded evidence. Leave uncertain groups unmatched.
4. The workbench will not permit quick selection for **no original model family**, **different catalogue model families**, **console contradictions**, **missing current reference RRP**, **duplicate SKUs**, or **catalogue suggestions absent from the original match candidates**. Use **Review individually** to inspect these exceptions.
5. For selected groups, enter source evidence (minimum 12 characters) and check physical verification. Click **Preview selected matches**. Review impact: groups, original source rows, units, suggested SKU, new *draft-priced* asset count, and every outstanding warning.
6. A separate acknowledgement enables **Confirm groups and save changes**. The server validates the original quote and catalogue snapshot again; stale reviews fail without applying any changes.
7. Repeat on the next page of groups. The quotation's original rows, source columns, serials, sites and asset identifiers remain intact; the condensed display may change after confirmation.

## Commercial and security boundaries

- This workflow **confirms identity only**, not RRP approval, maintenance cover eligibility, authorised pricing, contract discount or customer issue.
- Live catalogue SKUs are validated on the server. A model family, historical alias or similar-sounding product is **not** enough to apply a different model in bulk.
- Changes are staged in a deep-copy of the quote and committed together. Either every selected group passes validation, or **none** changes. All changes are logged under the current staff user.
- The preview token covers every source asset, console, current chosen equipment and price-affecting quote inputs, plus the catalogue revision. Stale tokens require a fresh review.
- At most 20 equipment groups and 1,200 source asset rows may be confirmed in one action.
- Individual manual-rate handling and conflicting catalogue entries remain outside this bulk workflow.
- Existing signed/PDF versions stay immutable. Any newly created version uses the changed quote state, and commercial pricing/review approval fields are reset.
- All state remains in `smartquote_local.db` with existing quotes. Back up before replacing software. No original customer fixtures or local databases are committed to GitHub.

## Testing

- Synthetic mixed-site, multi-variant list checks two-phase previews and atomic saves, source preservation, separate sites, quantity priority, missing evidence, invalid SKUs, ambiguous replacements, stale edits, idempotent resubmission, and quote history.
- `M Club Newcastle.xlsx` was loaded locally, without committing the private file: **165 source records, 72 condensed groups, 32 existing draft-priced source records**. The batch review worklist did not create any additional price before explicit confirmation.
- **21 older `224B-AAB` group cycles** remain blocked from quick matching to different modern model families; they need evidenced physical and commercial review.
- Exact pricing source for historical equipment remains provisional; the verified complete 2020–2026 source archive is still outstanding.
