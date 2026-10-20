# V10: Simple guide pricing for messy asset lists

## Staff journey

1. Import the spreadsheet; identical source machines remain grouped and every source record and serial is preserved.
2. Where an exact priced configuration cannot be confirmed, display an **internal 2026 RRP-based guide** instead of an unexplained TBC. Show per-machine monthly range and an unmissable `GUIDE ONLY` qualification.
3. In Edit line, ask a simple question: which console is fitted? Show only console bands present for that model family in the dated source master, plus **Not sure**. Never assume a console from a missing value.
4. Each console band shows observed RRP/maintenance-guide amounts for distinct source price levels. If upholstery, finish or specification makes RRPs differ, show each tier; don't silently take the cheapest for a full quote.
5. A coordinator can explicitly apply a provisional guide to identical rows after confirming what they checked. This is **not** an exact SKU, a price-source approval or a customer-ready quotation. An original model/SKU/serial is not overwritten.
6. Manager confirms exact SKU/console, current RRP and authorised tariff in the controlled catalogue before release. Issued customer quote is blocked while any provisional family guide remains.

## Supported source evidence

- Dated `Full Master Price List 24-08-2026.xlsx` normalised source stored in `data/rrp_2026_source.json.gz`. No fabricated RRPs.
- Historical `Quote spreadsheet v5 - USE THIS ONE.xls` has an identifiable 3% default annual maintenance calculation for many strength machines; other rate groups include 3.75% treadmill/elliptical/Impulse plate-loaded, 13% Fluid Rowers and 10% Fluid UBE/recumbent. These are historical calculation evidence only, not current authorisation to issue prices.
- Existing `data/pricing.json` has provisional Silver/Gold/Platinum tier multipliers and source rate groups. The guide uses them, not any client-supplied tariff.
- Console description 'not stated' in the price list is **not proof that the machine has no console**. The user must verify the physical equipment before using any guide.

## Tests / restrictions

- Model families are exact 3-digit+letter matches, not fuzzy guesses; no current family means no guide.
- Source rows with conflicting RRPs or console identities for the same exact SKU are ineligible for the assistant.
- Explicit third-party manufacturers cannot inherit a Pulse family guide.
- The browser never supplies the trusted RRP, rate or price; server resolves a source reference, price and console band itself.
- Draft selections store `sku=''`, `reference_sku=...`, source evidence and staff audit event; never imply an exact physical variant was identified.
- The guide can be applied to genuinely identical source rows only and cannot overwrite a previously confirmed selection.
- `calc_quote` blocks completed/customer issue when `basis=staff-guided-estimate` even though a provisional draft amount appears. PDF versioning, hash integrity and old quotes remain unchanged.

## M Club Newcastle local regression (20 October 2026)

- Import: 165 records, 165 units, 72 condensed groups.
- Before: 32 draft-priced records.
- After: 110 additional rows receive a dated-source guide-price range; 23 remain without a reliable current-model guide.
- Example source lists: 560G Leg Extension basic £5,931.60 RRP, 530G Seated Calf £5,650.81, 615G Rotary Torso £5,578.83.
- Amounts are indicative, do not imply a validated current replacement, finish or installed console, and are subject to commercial sign-off.
