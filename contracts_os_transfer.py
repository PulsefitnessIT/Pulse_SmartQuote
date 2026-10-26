"""Controlled SmartQuote -> Contracts OS accepted-quotation handoff.

The source is the previously issued immutable PDF *snapshot*, not mutable
draft inputs or current prices. No outbound network transfer or Sicon write.
"""
from __future__ import annotations
from decimal import Decimal,ROUND_HALF_UP

SCHEMA="pulse.smartquote.accepted.v1"


def _money(value):
    return float(Decimal(str(value)).quantize(Decimal(".01"),rounding=ROUND_HALF_UP))


def from_accepted_pdf_snapshot(q,summary,version,pdf_sha256,*,pilot_snapshot=False):
    """Return a minimal source-provenance handoff, without login secrets or raw documents."""
    if not q.get("id") or not q.get("quote_no"):
        raise ValueError("Accepted quote ID and original quote number are required.")
    if not version or len(str(pdf_sha256))!=64:
        raise ValueError("An issued PDF version and SHA-256 fingerprint are required.")
    if not q.get("customer") or not q.get("site"):
        raise ValueError("The original customer and site must be present.")
    if q.get("tier") not in ("Silver","Gold","Platinum","Mixed"):
        raise ValueError("Unknown maintenance package.")
    prices={x.get("id"):x.get("price") for x in summary.get("lines",[])}
    staged=summary.get("staged") or {}
    coverage={x.get("id"):x for x in staged.get("lines",[])}
    lines=[]
    for asset in q.get("assets",[]):
        if asset.get("excluded"):
            continue
        price=prices.get(asset.get("id"))
        if not price:
            raise ValueError("Incomplete priced equipment lines cannot be exported as accepted.")
        qty=int(asset.get("qty") or 0)
        if qty<=0:
            raise ValueError("Equipment quantity must be positive.")
        sku=(str(asset.get("code") or "").strip() or
             str((asset.get("selected") or {}).get("sku") or "").strip())
        if not sku:
            raise ValueError("Resolve the original item code before the contract setup handoff.")
        raw_serial=asset.get("serial") or ""
        serials=([str(x).strip() for x in raw_serial if str(x).strip()]
                 if isinstance(raw_serial,list) else
                 [x.strip() for x in str(raw_serial).replace("; ",",").split(",") if x.strip()])
        if len(serials)>qty:
            raise ValueError("Serial count exceeds equipment quantity.")
        first=coverage.get(asset.get("id"),{}).get("period_charge")
        lines.append({
            "source_line_id":str(asset.get("id") or ""),
            "item_code":sku.upper(),
            "description":str(asset.get("name") or asset.get("source_description") or ""),
            "model":str(asset.get("model") or ""),
            "quantity":qty,
            "serial_numbers":serials,
            "cover_start":str(asset.get("cover_start") or q.get("contract_start") or ""),
            "cover_end":str(q.get("contract_end") or ""),
            "annual_total":_money(price["annual"]),
            "first_period_total":_money(first if first is not None else price["annual"]),
            "price_basis":str(price.get("basis") or "mapped"),
        })
    if not lines:
        raise ValueError("An accepted maintenance quote requires equipment.")
    annual=_money(sum(Decimal(str(x["annual_total"])) for x in lines))
    if annual!=_money(summary.get("annual",0)):
        raise ValueError("Archived annual total differs from equipment prices.")
    term_total=_money(summary.get("term_total",0))
    if term_total<=0:
        raise ValueError("The accepted quote total is missing.")
    return {
        "schema_version":SCHEMA,
        "source_system":"Pulse SmartQuote",
        "source_quote_id":str(q["id"]),
        "quote_number":str(q["quote_no"]),
        "source_revision":"pdf-v"+str(version),
        "acceptance_status":"Accepted",
        "customer":{
            "legal_name":str(q.get("customer") or ""),
            "site_name":str(q.get("site") or ""),
            "sage_account_ref":str(q.get("account_ref") or ""),
            # Site account identifier is NOT inferred from customer_ref or address.
            "sicon_site_ref":str(q.get("sicon_site_ref") or ""),
            "billing_address":str(q.get("billing_address") or ""),
            "site_address":str(q.get("delivery_address") or ""),
            "contact_name":str(q.get("contact") or ""),
            "contact_email":str(q.get("contact_email") or ""),
        },
        "contract":{
            "reference":str(q.get("contract_ref") or ""),
            "package":str(q["tier"]),
            "start_date":str(q.get("contract_start") or ""),
            "end_date":str(q.get("contract_end") or ""),
            "payment_terms":str(q.get("payment_terms") or ""),
            "visits":q.get("visits"),
        },
        "pricing":{
            "annual_total":annual,
            "term_total":term_total,
            "currency":"GBP",
            "commercially_approved":bool(q.get("pricing_approved") is True and not pilot_snapshot),
            "source_quote_pdf_sha256":str(pdf_sha256),
        },
        "equipment":lines,
    }
