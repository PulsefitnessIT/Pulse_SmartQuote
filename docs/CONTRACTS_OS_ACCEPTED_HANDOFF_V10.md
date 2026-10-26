# SmartQuote to Contracts OS — accepted quote handoff

Feature branch: feature/contracts-os-accepted-handoff. Controlled pilot only.

An Accepted quote with an archived PDF version has one Export accepted quote to Contracts OS button.
The JSON export is a minimal schema pulse.smartquote.accepted.v1; it does not send anything over the network.
The source is the archived immutable quote PDF snapshot. A mismatched catalogue revision blocks export rather
than silently recalculating new prices against an old accepted quotation.

Transferred fields: legal customer, site, Sage customer account ref, contract dates, package,
equipment identity, unit quantities, serial numbers, individual future coverage dates, annual
and pro-rata totals, source quote number/version and archived PDF SHA-256.

No customer portal password, raw document uploads, sign-in tokens or staff credentials are transferred.
A Sicon site reference is never fabricated from an unrelated SmartQuote customer reference.
Pilot-only or unapproved tariff pricing is explicitly marked commercially_approved=false and must be
reviewed by Contracts OS before setup. Acceptance alone is not evidence of commercial approval.

The Contracts OS PWA feature/unified-smartquote-intake accepts this schema into an audit-protected
review worklist. That stage does NOT create a contract or asset in Sage/Sicon.

Next step: a centrally hosted SmartQuote pricing service and shared Contracts OS database, eliminating
the temporary JSON transfer once credentials, source-data ownership and the production integration
architecture have been approved by IT and the Contracts team.