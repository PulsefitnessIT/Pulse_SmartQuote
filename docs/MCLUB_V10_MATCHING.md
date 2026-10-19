# M Club Newcastle — SmartQuote V10 messy assets regression

Source: `M Club Newcastle.xlsx`, sheet `ExportData`, 165 equipment rows.
This original customer file is not included in the repository or pilot ZIP.

## Reproduced V10 baseline problem

- Before development: 165 source rows, only two priced by the existing engine.
- The exported `Make` column sometimes contains a Pulse stock code (e.g. `224B-AAB`, `751G-AAQ`), while `Make` and `Model` often contain `0`.
- Source descriptions include asset IDs such as `PF00108`, and serials reveal a model family such as `260G` but **not** an exact configuration or approved RRP.
- The current catalogue has different console variants and RRPs for the same model family.

## Tested revised behaviour

- 165 original rows retained, 165 source row numbers and original cell values saved.
- 72 compact display groups for the tested file, including 21 Group Cycles as one group and 14 treadmills as one group.
- 32 original machines now receive a maintenance calculation from source catalogue records; other rows remain unpriced or in candidate review. **These are draft calculations, not authorised customer pricing.**
- Excel `Correct Serial Number` supersedes `Serial Number` for matching provenance, while both original and corrected fields are preserved.
- Grouping includes site, explicit SKU, model, console, name, manufacturer, selection, exclusions and unit pricing basis; different items are never blended for convenience.
- The quote PDF presents condensed group lines with a separate asset schedule containing individual source rows, asset IDs, serial numbers, original descriptions and install-date cells.
- Equipment Catalogue searches both the existing priced source and the deployed historical identity index; historical identities do not expose an RRP or turn an alias into an approved product.

## Gaps still requiring data-owner work

The available historical index is a recovered subset: 6,909 identity SKUs and 231 alias codes from eight source revisions, not the independently verified full 2020–2026 historical catalogue. The 2021 record is metadata-only. Its source completeness and commercial approval status remain **not approved**. Check model console configuration, current RRP, maintenance eligibility, external brands and unusual variants before final issue. Do not claim full machine coverage solely from the number of imported records.
