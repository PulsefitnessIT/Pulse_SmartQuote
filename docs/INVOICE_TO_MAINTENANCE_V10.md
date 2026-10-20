# SmartQuote V10 — Import a historic Pulse Fitness sales invoice

**Internal pilot.** This is a dedicated **invoice** importer, distinct from the previous **maintenance agreement** renewal importer. Supported input: selectable-text Pulse Fitness invoice PDFs following the tested invoice layout (example: invoice 53274, 5 December 2018, Evesham). Scanned or materially different invoice layouts require manual review and are not silently OCR-guessed.

## Staff process
1. Open a new draft quotation in SmartQuote.
2. Select **Read sales invoice (PDF)** in Step 01.
3. Review the customer, site, invoice identifier/date, candidate machine lines and unit/serial counts, separated commercial items, and extra narrative needing manual attention. **Preview makes no database change**.
4. Select **Add equipment lines to draft** to append the verified source candidates to the current quote. Invoice/document hash prevents a duplicate import into the same quote. Imports for a different customer or site are refused when the quote already contains assets. Previous issued PDF snapshots are never edited.
5. Verify installed machines, actual serials, physical configurations and contract scope. Historic **invoice sale values are not RRP** and are never copied into the maintenance pricing field; current catalogue/tariffs calculate a separate draft maintenance price. The quote remains unapproved.

## Evidence and exclusions
- Full source product code, description, printed equipment quantity, individual serial numbers, original page, original invoice reference/date, and historic sale value are traceable internally.
- PDF lines for Customer Care, Trade In, generic Accessories and Smart Centre are separated from machine candidates, without losing their existence in the preview.
- Physical machines invoiced at £0 (including H Range resistance equipment) **remain candidate equipment**. They do not get a £0 RRP or £0 maintenance rate.
- Repeated console metadata, QR/NFC descriptions and narrative without a reliable quantity are never converted to invented additional machines. Notable loose equipment descriptions (racks, sled, bespoke rigs, benches, freeweight accessories) are presented as **manual review notes**. They may describe items already included in a counted invoice row, so they cannot safely be imported automatically.
- Current rules flag quantities without sufficient individual serials, placeholder sales serials such as `5206/3`, and freeweight/accessory maintenance scope.
- New quote files record hash, invoice ref/date and imported source count. All user-specific quote databases are excluded from GitHub packaging.

## Evesham invoice 53274 result (actual input tested locally)
- 18 pages; customer Wychavon Leisure Ltd; site Evesham Leisure Centre; invoice date 05/12/2018.
- 65 structured invoice source lines; 61 candidate equipment lines totalling 113 equipment units; 105 verified actual serial entries; 17 machine lines with £0 historic sales value; 4 commercial or non-equipment rows separated; additional unstructured invoice descriptions held for review.
- Examples: `260G-6.0-DRST` 12 units/12 serials; `280G-6.0-DFST` 10/10; `240G-6.0-DST` 5/5; `250G-6.0-DST` 4/4; H Range `560HDS` is a legitimate machine despite £0 sale value.
- No source sale prices have been adopted as commercial RRP or current maintenance rates.

## Testing and limitations
Synthetic PDF tests cover: extraction, serials, £0 machines, commercial/negative lines, wrong PDF rejection, read-only preview, SHA-protected confirmation, duplicate blocking, preserved customer/site and unapproved pricing. The customer PDF itself is **not in the repository or CI**.

Before rollout: test other invoice template generations, scanned invoices, corrected invoices/credit notes, duplicate serials and customer-level import permissions. This importer is a controlled pilot, not an unconditional guarantee of complete equipment coverage.
