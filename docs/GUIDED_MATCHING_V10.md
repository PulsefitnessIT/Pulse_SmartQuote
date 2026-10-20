# V10 — guided legacy-equipment matching and lossless source records

## What changed

- The editing modal now retrieves **ranked current-catalogue candidates** on demand and displays exact item codes, console variants, source reference RRPs and reasons for review.
- An older model with a suffix, e.g. `250G-0`, can display the broader `250G` family **for review only**. Its suffix and imported source cells are preserved. It cannot automatically select the reference SKU/RRP based on suffix removal.
- A model with no current SKU, such as `224B`, shows old service configuration records **without a verified RRP** and separately labels newer descriptive suggestions as *different models, not approved replacements*.
- The user can apply a **personally confirmed** catalogue choice to identical machines already detected by SmartQuote. This reuses the existing `/resolve` method and never changes serials, original descriptions or source row numbers.
- Two exports are available in Quote Builder: **Matching review CSV** (one line per condensed group) and **Original asset register CSV** (one line per imported physical source row; all original nonblank source columns, including unidentified or repeated headings, are retained).
- CSV output is safely escaped to prevent Excel formula injection from customer-supplied descriptions and notes.

## Non-negotiable boundaries

A fuzzy text suggestion is not an approved product equivalence, and a model family is not an approved console/RRP. Historical identities never carry approved prices. The current tariff catalogue is still provisional. We have deliberately **not** altered `data/catalog.json`, `data/configs.json`, `data/pricing.json`, quote discount formulas or issued quote snapshots. Previously generated PDFs continue to be immutable.

M Club Newcastle remains the principal complex test: 165 original assets condense into 72 display groups; the existing engine prices 32 source rows. The new assistant reduces manual searching but it does **not** claim that the remaining 133 have approved prices.

## Verification

`SMARTQUOTE_AUTH=off python -m unittest discover -s tests -v`

`node --check static/app.js`

`python build_v10_pilot.py --output dist/Pulse_Fitness_SmartQuote_V10_Guided_Matching_Pilot.zip`

The recovery archive included in some local pilots has 6,909 identities from eight revisions, not independently audited full 2020–2026 coverage. The release builder does not authorise customer issue.
