"""Read-only V10 deployment checks. Does not approve commercial prices or products."""
import json
from pathlib import Path

YEARS = set(range(2020, 2027))


def _load_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def evaluate(root, pricing=None):
    """Check archive presence and commercial status, without changing quote data.

    Passing these automated checks is NOT permission to issue a customer quote:
    staff still have to approve RRPs, tariffs, exceptions and output documents.
    """
    root = Path(root)
    index_path = root / "data" / "historical_catalogue_index.json"
    manifest_path = root / "data" / "historical_catalogue_manifest.json"
    index = _load_json(index_path)
    manifest = _load_json(manifest_path)
    records = index.get("records")
    aliases = index.get("aliases")
    records = records if isinstance(records, dict) else {}
    aliases = aliases if isinstance(aliases, dict) else {}
    sheets = manifest.get("worksheets")
    sheets = sheets if isinstance(sheets, list) else []
    years = sorted({
        row.get("year") for row in sheets if isinstance(row, dict)
        and row.get("status") == "read" and isinstance(row.get("year"), int)
    })
    failures = sum(1 for row in sheets if isinstance(row, dict)
                   and row.get("status") == "failed")
    consistent = (
        bool(manifest) and isinstance(manifest.get("unique_skus"), int)
        and manifest["unique_skus"] == len(records)
        and isinstance(manifest.get("alias_codes"), int)
        and manifest["alias_codes"] == len(aliases)
    )
    ambiguous = sum(1 for codes in aliases.values()
                    if isinstance(codes, list) and len(set(codes)) > 1)
    if pricing is None:
        pricing = _load_json(root / "data" / "pricing.json")
    pricing = pricing if isinstance(pricing, dict) else {}
    pricing_status = str(pricing.get("pricing_status") or "Not recorded")
    approved = pricing_status.strip().casefold() == "approved"
    complete_years = YEARS.issubset(set(years))
    # A year appearing in an archive is not proof that every master revision was supplied.
    # The importer deliberately does not assert completeness or authorised approval.
    source_reviewed = str(manifest.get("archive_review_status") or "").strip().casefold() == "approved"
    archive_ready = bool(records) and consistent and complete_years and failures == 0 and source_reviewed
    warnings = []
    if not index_path.is_file() or not records:
        warnings.append("Historical 2020-2026 catalogue index is not deployed.")
    if not manifest_path.is_file() or not consistent:
        warnings.append("Historical manifest is missing or does not match the index.")
    if not complete_years:
        missing = ", ".join(map(str, sorted(YEARS - set(years))))
        warnings.append("No imported source evidence for year(s): " + missing + ".")
    if failures:
        warnings.append(f"{failures} historical worksheet imports failed.")
    if not source_reviewed:
        warnings.append("Historical source completeness has not been signed off by an authorised data owner.")
    if ambiguous:
        warnings.append(f"{ambiguous} alias codes have multiple candidate SKUs; review each before use.")
    if not approved:
        warnings.append("Commercial RRP/tariff configuration is not explicitly approved.")
    return {
        "historical": {
            "index_loaded": bool(records),
            "unique_skus": len(records),
            "alias_codes": len(aliases),
            "ambiguous_alias_codes": ambiguous,
            "source_years": years,
            "failed_worksheets": failures,
            "manifest_consistent": consistent,
            "source_reviewed": source_reviewed,
            "archive_scope": str(manifest.get("archive_scope") or "unverified"),
            "archive_ready": archive_ready,
        },
        "commercial": {
            "pricing_status": pricing_status,
            "approved": approved,
        },
        "automated_preflight_passes": archive_ready and approved,
        "warnings": warnings,
        "notice": "Automated checks are informational; commercial sign-off, customer regression and PDF review are separately required.",
    }
