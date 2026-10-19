"""Recover a read-only identity index from a previous V10 equipment SQLite pilot.

This is a bridge for existing audit DBs, NOT a replacement for importing every
2020-2026 master revision. No RRP, rate, quote or customer data is exported.
Recovered manifests are expressly unapproved for commercial release.
"""
import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from historical_master import valid_alias


def recover(sqlite_path, output):
    sqlite_path, output = Path(sqlite_path), Path(output)
    if not sqlite_path.is_file():
        raise ValueError(f"Equipment audit SQLite file does not exist: {sqlite_path}")
    connection = sqlite3.connect(str(sqlite_path))
    connection.row_factory = sqlite3.Row
    try:
        expected = {"source_files", "equipment", "observations", "alias_evidence"}
        tables = {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not expected.issubset(tables):
            raise ValueError("Not a supported V10 identity audit database.")
        sources = [dict(row) for row in connection.execute(
            "SELECT id,year,revision,name FROM source_files ORDER BY year,id")]
        original = [dict(row) for row in connection.execute(
            "SELECT sku,name,model,console,status,end_of_life,product_group,category,"
            "last_observed_year,last_source FROM equipment ORDER BY sku")]
        evidence = defaultdict(list)
        for row in connection.execute(
            "SELECT o.sku,o.row_number,o.old_sku,s.year,s.revision,s.name "
            "FROM observations o JOIN source_files s ON s.id=o.source_id "
            "ORDER BY s.year,s.id,o.row_number"):
            evidence[row["sku"]].append({
                "year": row["year"], "revision": row["revision"],
                "source": row["name"], "row": row["row_number"],
                "old_sku": row["old_sku"] or "",
            })
        records = {}
        for item in original:
            code = str(item["sku"] or "").strip().upper()
            if not code:
                continue
            lineage = evidence.get(code, [])
            latest = lineage[-1] if lineage else {}
            records[code] = {
                "sku": code, "name": item["name"] or "",
                "model": item["model"] or "", "console": item["console"] or "",
                "status": item["status"] or "", "eol": item["end_of_life"] or "",
                "group": item["product_group"] or "", "category": item["category"] or "",
                "year": item["last_observed_year"], "rev": latest.get("revision", ""),
                "source": item["last_source"] or latest.get("source", ""),
                "first_seen": min((x["year"] for x in lineage), default=item["last_observed_year"]),
                "old_sku": latest.get("old_sku", ""),
                "evidence_only": True,
                "provenance": [{"year": x["year"], "revision": x["revision"],
                                "source": x["source"], "row": x["row"]} for x in lineage],
            }
        aliases = defaultdict(set)
        skipped_aliases = 0
        for row in connection.execute("SELECT alias,sku FROM alias_evidence"):
            alias, code = str(row["alias"] or "").strip().upper(), str(row["sku"] or "").strip().upper()
            if not valid_alias(alias) or code not in records:
                skipped_aliases += 1
                continue
            aliases[alias].add(code)
        mapping = {alias: sorted(values) for alias, values in sorted(aliases.items())}
        counts = Counter(x["year"] for rows in evidence.values() for x in rows)
        sheets = [{"file": s["name"], "sheet": "Recovered SQLite audit",
                   "year": s["year"], "revision": s["revision"],
                   "status": "read", "equipment_rows": counts.get(s["year"], 0),
                   "metadata_only": counts.get(s["year"], 0) == 0} for s in sources]
        manifest = {
            "archive_scope": "RECOVERED SUBSET - verify all revisions separately",
            "archive_review_status": "Not approved",
            "source_files": len(sources),
            "snapshots": sum(len(v) for v in evidence.values()),
            "unique_skus": len(records),
            "alias_codes": len(mapping),
            "ambiguous_alias_codes": sum(len(v) > 1 for v in mapping.values()),
            "skipped_unusable_alias_links": skipped_aliases,
            "worksheets": sheets,
            "by_year": dict(sorted(counts.items())),
            "pricing_status": "IDENTITY ONLY - NO APPROVED RRP",
            "note": "Recovery from prior equipment-audit SQLite; not proof every annual revision is present."
        }
        if not records or not sources:
            raise ValueError("No historical equipment identities or source references recovered.")
        output.mkdir(parents=True, exist_ok=True)
        (output / "historical_catalogue_index.json").write_text(
            json.dumps({"records": records, "aliases": mapping}, ensure_ascii=False,
                       separators=(",", ":")), encoding="utf-8")
        (output / "historical_catalogue_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description="Recover V10 SQLite equipment identities only")
    parser.add_argument("sqlite_db", type=Path)
    parser.add_argument("--output", type=Path, default=Path("recovered_historical"))
    args = parser.parse_args()
    try:
        report = recover(args.sqlite_db, args.output)
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        parser.exit(2, f"Recovery failed: {exc}\n")
    print(json.dumps({key: report[key] for key in
                     ("source_files", "snapshots", "unique_skus", "alias_codes",
                      "ambiguous_alias_codes", "skipped_unusable_alias_links")}, indent=2))


if __name__ == "__main__":
    main()
