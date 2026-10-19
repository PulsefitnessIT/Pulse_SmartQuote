# Pulse Fitness SmartQuote V8 - Historic Maintenance Agreement Pricing

## Problem reproduced (Skipton, 16 October 2026)
The previous maintenance agreement uses short, historic model family codes (`305H`, `866H`, `260G-6.0`) rather than full modern current-catalogue SKUs (`305H-AGG`, etc.). V7 created candidate suggestions but did not calculate model-family RRP prices. Source agreement: North Yorkshire Council, Skipton Leisure & Wellbeing Hub, C15001/7323.

## Corrective changes
- Import of the 31-line/55-unit Schedule 3 remains unchanged, including original codes and serials.
- When a previous agreement supplies a family code and no precise SKU can be resolved, a new **family-level indicative maintenance estimate** is offered where at least one suitable current catalogue RRP exists.
- An RRP reference is chosen from the compatible **current family** with the highest applicable RRP, rather than falsely matching to a specific historic SKU. The RRP range, current reference model and reference SKU are recorded for review. The price is derived with the existing Silver/Gold/Platinum tariff rules, no new percentage is invented.
- Historic 6.0/19-inch Fusion console generations are explicitly labelled *modern-family proxies, not verified equivalent*. They should be reviewed before customer commitment.
- A small semantic cross-reference handles historic bench model transitions, Concept2 Model E and floor-mounted SkiErg. These are **comparisons, not approved manufacturer supersessions**.
- Counterbalanced Smith + bench must reference a current Smith + bench SKU, not the cheaper no-bench model. Half-rack without platform must not reference an included-platform bundle.
- For this real Skipton agreement **29/31 lines now have indicative or source-derived current pricing**. `270G-6.0` (Fusion Lateral Trainer) and `WattBPro` do not have a sufficiently supported current RRP match; prices remain TBC.
- Existing V7 saved renewal drafts are upgraded automatically on opening; confirmed selections, manual prices and exclusions are not overwritten. Saved issued PDF versions remain immutable.
- The browser now identifies these as **Family estimate**, shows the modern reference SKU and family RRP span, and retains the original machine code. The matching modal no longer offers an invalid 'Reconfirm' button for family-only pseudo-selections.
- An incomplete quote's total now says **PARTIAL subtotal**, not the full annual quotation. PDF also highlights the contractual fixed-price extension.

## Commercial caveat
The existing agreement includes an extension option at £14,212.43 + VAT for 01/12/2026 to 30/11/2027. This must be checked before sending a differently priced renewal. Historic-family rates are *indicative internal model estimates*, not confirmed rates for the original machine; use actual legacy price data or an authorised manual service price where known.

## Tests
- 45 existing V7 tests + 9 new regression tests = **54 passing** when `SMARTQUOTE_AUTH=off` in the test environment.
- Tests cover family reference identity, no silent SKU substitution, Smith including bench, rack without platform, SkiErg floor model, obsolete Fusion console, two unsupported codes, no automatic family inference for unrelated asset CSVs, real Skipton API import and upgrading an old V7 draft.
- Draft PDF generated and visually checked, 3 pages. Real coordinator browser testing outstanding.

## Upgrade
1. Close the V7 server command window entirely so port 8765 is available.
2. Back up your V7 folder and `smartquote_local.db` file (customer data and staff accounts).
3. Extract V8 into a new folder. Copy your V7 `smartquote_local.db` into the **root** of the extracted V8 application folder before launch.
4. Double-click `start_windows.bat`, sign in normally, open the existing Skipton quotation and review newly calculated family estimates.
5. Verify the current service-price eligibility and confirm the fixed-price extension. For the two unresolved models, enter documented manual rates or use Master Price List administration to add verified historical SKUs and retail prices.

**Production status:** Controlled local pilot only. The historical/current model-family comparisons have not been commercially authorised for binding customer quotations; full production security, centrally hosted database and Sage/Sicon integrations remain outstanding.
