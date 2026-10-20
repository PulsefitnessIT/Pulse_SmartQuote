# SmartQuote V10 — staff equipment sorting and automatic source-RRP drafts

Development record, 20 October 2026. **Controlled internal pilot**, not a customer-approved tariff.

* Equipment quotation headers support ascending/descending sort (machine/model, description, quantity, unit/month, line/year, and status). Sort is display-only: physical assets, imported order, serial numbers and saved quote rows are untouched.
* The "apply to identical machines" scope checkbox is now visible immediately **above** the editor's save actions. Its scope remains restricted to the original identical model, site, description and console; audit data/serials stay on each original row.
* A distinctive complete imported description with one unambiguous 2026 RRP is now used as an **automatic draft price reference**. In the M Club sample, the imported Premium `200H` StepMill with 18.5-inch touchscreen, watch connectivity, mirroring and wireless charging maps to source-reference `200H-AAF` at £11,544.77. Feature order can differ. `200H-AAH` has EGYM and a different RRP; it is **not** chosen for this description.
* Bare strength models may display an existing model-AAA standard reference (e.g. 875G -> 875G-AAA). It is always a provisional **model family price**; no installed SKU or console is assumed. High-risk or special descriptions do not get a baseline.
* The automatic reference is a calculated draft line price (including unit/month and group line/year), not an edit to the actual equipment code or installed serials. Its source model/SKU reference is carried only as quotation evidence. It must not be treated as approved Silver/Gold/Platinum rates.
* Generic descriptions or missing/source-conflicted RRPs still show a range or TBC. A guide range is now shown in the annual column, explicitly as a guide and excluded from the numeric quote subtotal unless a valid single reference is available.
* The full selected-vs-source approval distinction is preserved: drafts are blocked by the normal issue-ready checks even if a numeric monthly/year amount exists. A commercial owner must approve the relevant current RRP, configuration and maintenance tariff before a customer-ready quotation can be issued.

Validation includes source-derived, synthetic `200H` and `875G` regression cases, complex M Club 165-asset import (locally), Python suite and JS syntax checks. Existing customer data, quote snapshots and protected branch history are unchanged.
