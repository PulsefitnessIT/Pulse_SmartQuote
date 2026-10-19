# Developer implementation handoff — Pulse SmartQuote Production

Use the V6 source code as a business-rule and UX prototype, not a network-deployable production application.

**Mandatory:** clone user-tested UI behaviour (import => match => amend => price => archive PDF). Preserve current Pulse invoice-style quotation formatting, catalogue provenance, normal quotes without routine approval and exceptional pricing warnings.

## Service boundaries

- **Identity:** corporate SSO; coordinator, manager, admin and auditor scopes with server-enforced permissions.
- **Pricing master:** controlled SKU, model, console, aliases, source RRP, effective dates, contract eligibility, tariff group and auditable approvals. Maintain a staging/preview/rollback process.
- **Asset ingestion:** XLSX/CSV parser, strict quantity validation, matched aliases, supported models, scored suggestions and action-needed queue.
- **Pricing:** deterministic DECIMAL arithmetic, package selection, consistent discounts, PPM/scoping rules, minimum contributions and cost-to-serve floor when approved data exists.
- **Quotation service:** transactional quote IDs, optimistic locking, versioned drafts, versioned released documents with immutable object storage and SHA digests.
- **Document service:** central Pulse templates reviewed against the supplied invoice and 2026 maintenance agreement; explicit legal revision and package scopes.
- **External integration:** documented Sicon/Sage adapter with stable identifiers, retries, idempotency, error logs and reconciliation; no guessed endpoints.
- **Customer acceptance:** Pulse-authorised email integration, monitored delivery, optional e-signature, acceptance audit and contract handoff.
- **Reporting:** pipeline status, conversion, margin and fulfilment metrics reconciled to authoritative systems.

## Unacceptable implementation shortcuts

- Silent SKU substitution, auto-accepting invalid quantities or inventing RRPs.
- Mistaking an RRP-estimated quote for a signed-off company tariff.
- Copying a customer quote into the contract register without acceptance and clear idempotency checks.
- Exposing a local SQLite application or `SMARTQUOTE_AUTH=off` pilot configuration to the internet.
- Overwriting the PDF or equipment list of an issued quotation.
- Calling a provisional/held maintenance pricing configuration approved without Finance/Commercial sign-off.

## Source references

- Pulse Fitness - Contract Quoting.xlsx
- Master Full May 26 updated essential(4).xlsx
- 2025 - Master Input File v2 (Website Layout) - Transition_Iss.u(2).xlsx
- 02. Maintenance Agreement Packages(1).docx
- 01. New Maintenance Agreement - 130226(2).pdf
- 654351-Invoice.pdf

Verify the currency, VAT, pack inclusions and sales descriptions against the current signed-off Pulse data before real issuance. See PRODUCTION_ROADMAP.md and V6_RELEASE_GATES.md.
