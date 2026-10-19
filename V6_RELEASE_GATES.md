# V6 Release Gates — Pulse Fitness

**Founder release decision:** approve controlled local user acceptance testing, **not** a company-wide or externally accessible deployment. The work marked "implemented" below is supported by V6 code and automated tests; it is not independent penetration testing, commercial audit or IT sign-off.

| Gate | V6 status | Required evidence before company-wide release | Responsible owner |
|---|---|---|---|
| 1. Discount and rounding accuracy | Implemented/tested | Finance validates 20 real equipment combinations, manual rates, discounts, VAT and annual × quantity rounding | Pricing Manager / Finance |
| 2. Input quality | Implemented/tested | Coordinators upload 15 representative messy customer files, including zero/invalid quantities and old SKUs | Aftersales Contracts |
| 3. Pricing policy | **Blocked** | Written authorisation of provisional source tariffs, price multipliers, rate groups, maintenance eligibility, margin floors, discounts and exception handling | Commercial Director / Service Director |
| 4. Terms and scope | **Blocked** | Signed-off Silver/Gold/Platinum benefits, exclusions, quote validity, PPM visits, contract duration and current agreement terms | Contracts / Legal |
| 5. Authentication | Partial pilot controls | Replace local passwords with SSO/MFA and lifecycle management; penetration assessment, access logging and review | IT / Security |
| 6. Central system of record | **Blocked** | Managed database, migrations, permissions, concurrency checks, recovery point objectives, backup restore tests | IT / Developer |
| 7. PDF archive | Implemented local snapshot | Test WORM/immutable offsite storage, version audit and retrieval when server restarts or fails | IT / Contracts |
| 8. Invoice-style templates | Tested pilot | Commercial/marketing sign-off on Pulse visual template; legal sign-off on proposal language | Marketing / Contracts |
| 9. Customer sending/acceptance | **Not integrated** | Authorised mail integration, delivery tracking, customer e-signature and acceptance records | Sales / IT / Legal |
| 10. Sage 200/Sicon contract handoff | **Not integrated** | Validated API operations for customer, site, asset, item code, service contract, annual fees and contract activation | IT / Sicon / Aftersales |
| 11. Cost-to-serve pricing | **Design stage** | Service-cost dataset, actual labour/parts/travel consumption, model risk classifications and pricing backtesting | Service / Finance |
| 12. Operational UAT | Pending | Two coordinators and a manager complete acceptance cases without developer assistance; sign-off documented | Service Manager |

## Minimum UAT scenarios

1. Clean CSV, messy XLSX and all six lines of the supplied messy sample.
2. Product selected using description rather than a known SKU.
3. Valid exact SKU, legacy crosswalk, and two alternative machine recommendations.
4. Duplicate SKU conflict cannot become an unambiguous automatic match.
5. Missing quantity, quantity zero, text, decimal and negative numbers; corrected quantities must clear the blocker.
6. Source-derived RRP estimate labelled correctly rather than passed off as an authorised service quote.
7. Manual £100 annual/unit rate with 10% discount gives £90/unit and £180 total for two machines.
8. Unit annual price × quantity matches displayed annual line total to the penny.
9. Silver/Gold/Platinum change updates totals without a hidden price-band selector.
10. Quote A generated and archived; source RRP subsequently changes; original PDF bytes and checksum remain intact.
11. Manager can update master catalogue; coordinator cannot call the administration endpoint.
12. Existing local customer details can be reused without retyping all addresses.
13. Pilot PDF remains visibly watermarked and unsuitable for unrestricted issue.
14. Backup created and independently restored; hash and SQLite integrity confirmed.
15. Final production trial: two simultaneous users cannot overwrite a quote; this requires the proposed central DB deployment, not local V6.

## Commercial policy decisions still needed

- Is the standard workbook tariff commercially approved for all named equipment groups, including third-party, steps, fluid machines and console variants?
- Should provisional prices be displayed, quoted with a notice, or blocked when margins fall outside policy?
- What is the minimum contribution margin by package after expected service labour, travel, parts and risk?
- Are Silver's lack of planned servicing, Gold's one-visit baseline and Platinum's scope aligned with the legally approved 2026 agreement?
- What is the permitted discount threshold for coordinators? What requires escalation (rather than approving each ordinary quote)?

**Do not set the production-release flag or remove the pilot watermark until the owners above sign off.**
