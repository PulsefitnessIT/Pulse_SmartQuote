"""Validate and install the generated V10 identity-only archive into an existing checkout.

Usage: python install_historical_catalogue.py /path/to/historical_output
No commercial prices, customer records or issued quote snapshots are modified.
Restart SmartQuote after installation; engine identity data is loaded at startup.
"""
import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

INDEX = "historical_catalogue_index.json"
MANIFEST = "historical_catalogue_manifest.json"
YEARS = set(range(2020, 2027))
FORBIDDEN = {"rrp", "price", "price_pence", "annual", "monthly", "approved_rrp"}


def read_object(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must be a JSON object.")
    return data


def validate(folder):
    """Returns identity statistics; raises ValueError on unsafe/incomplete sources."""
    folder = Path(folder)
    for name in (INDEX, MANIFEST):
        if not (folder / name).is_file():
            raise ValueError(f"Missing {name}. Run historical_master.py on the entire source set.")
    index = read_object(folder / INDEX)
    manifest = read_object(folder / MANIFEST)
    records = index.get("records")
    aliases = index.get("aliases")
    if not isinstance(records, dict) or not records or not isinstance(aliases, dict):
        raise ValueError("Historical index has no valid identity records or aliases.")
    if manifest.get("unique_skus") != len(records) or manifest.get("alias_codes") != len(aliases):
        raise ValueError("Index counts do not match the source-traceable manifest.")
    source_sheets = manifest.get("worksheets")
    if not isinstance(source_sheets, list) or not source_sheets:
        raise ValueError("Manifest must contain source worksheets.")
    years = {x.get("year") for x in source_sheets
             if isinstance(x, dict) and x.get("status") == "read"
             and x.get("equipment_rows", 1) > 0 and not x.get("metadata_only")}
    missing = YEARS - years
    if missing:
        raise ValueError("No imported source sheets for year(s): " + ", ".join(map(str, sorted(missing))))
    failures = [x for x in source_sheets if isinstance(x, dict) and x.get("status") == "failed"]
    if failures:
        raise ValueError(f"{len(failures)} source sheets failed: review the manifest.")
    for sku, row in records.items():
        if not isinstance(row, dict) or row.get("sku") != sku or row.get("evidence_only") is not True:
            raise ValueError(f"Missing identity-only marker / inconsistent SKU: {sku}")
        if FORBIDDEN.intersection(set(row)):
            raise ValueError(f"Unapproved price field in historical identity record: {sku}")
    for alias, targets in aliases.items():
        if not isinstance(targets, list) or any(sku not in records for sku in targets):
            raise ValueError(f"Alias {alias!r} points to a missing or invalid SKU.")
    return {
        "unique_skus": len(records),
        "alias_codes": len(aliases),
        "ambiguous_aliases": sum(len(set(v)) > 1 for v in aliases.values()),
        "source_years": sorted(years),
        "source_sheets": len(source_sheets),
        "identity_only": True,
    }


def install(source, destination):
    """Backup existing identity files and replace them only after validation."""
    source, destination = Path(source), Path(destination)
    report = validate(source)
    destination.mkdir(parents=True, exist_ok=True)
    backups = destination / "historical_backups"
    staged = []
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        for name in (INDEX, MANIFEST):
            with tempfile.NamedTemporaryFile(dir=destination, prefix=".v10-", delete=False) as handle:
                stage = Path(handle.name)
            staged.append((name, stage))
            shutil.copyfile(source / name, stage)
        backups.mkdir(exist_ok=True)
        for name, stage in staged:
            target = destination / name
            if target.exists():
                shutil.copy2(target, backups / f"{name}.{timestamp}.bak")
            os.replace(stage, target)
        return report
    finally:
        for _, stage in staged:
            if stage.exists():
                stage.unlink()


def main():
    parser = argparse.ArgumentParser(description="Install a validated V10 historical index (not prices)")
    parser.add_argument("source", type=Path, help="Folder containing importer output")
    parser.add_argument("--target", type=Path,
                        default=Path(__file__).resolve().parent / "data")
    args = parser.parse_args()
    try:
        report = install(args.source, args.target)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Archive not installed: {exc}\n")
    print(json.dumps({"status": "installed - restart app to load identities", **report}, indent=2))


if __name__ == "__main__":
    main()
