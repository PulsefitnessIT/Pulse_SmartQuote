"""Build a traceable historical equipment identity register from Pulse master exports.

This module NEVER modifies data/catalog.json, maintenance tariffs, or live RRPs.
Only exact source facts are exported. Aliases are evidence, not automatic SKU
substitutions. Supports Excel's CSV UTF-8 and .xlsx/.xlsm (cached values only).
"""
from __future__ import annotations

import argparse
import csv
import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
SOURCE_EXTS = {".csv", ".xlsx", ".xlsm"}

FIELD_NAMES = {
    "sku": (
        "stock item code sku code", "stock item code", "sku code",
        "code", "sku", "stock code",
    ),
    "name": (
        "stock item name product name short description",
        "stock item name", "product name short description",
        "product name", "name",
    ),
    "description": (
        "stock item description master input file v2 description",
        "stock item description", "master input file v2 description",
        "description",
    ),
    "model": ("model no part code", "model no", "model number", "model"),
    "old_sku": ("old sku", "old stock item code", "old resale code"),
    "group": ("product group nominal", "product group"),
    "category": ("product category", "analysisname 20 product catagory analysisvalue 20"),
    "console": ("console", "console analysis code 6"),
    "status": ("status active inactive", "active inactive"),
    "end_of_life": ("end of life",),
    "manufacturer": ("manufacturer s name supplier analysis code 19",
                     "manufacturer s name", "manufacturer", "manufacturer name"),
}
EVIDENCE_FIELDS = (
    "name", "description", "model", "group", "category",
    "console", "status", "end_of_life", "manufacturer",
)
PLACEHOLDERS = {"", "0", "N/A", "NA", "NONE", "NULL", "-", "#N/A", "???"}


def normal(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def code_value(value: str) -> str:
    return clean(value).upper()


def valid_sku(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9][A-Z0-9._/+-]{1,75}", value)) and value not in PLACEHOLDERS


def valid_alias(value: str) -> bool:
    return valid_sku(value) and not value.isdigit()


def source_info(path: Path) -> tuple[int | None, str]:
    match = re.search(r"(?<!\d)(20(?:20|21|22|23|24|25|26))(?!\d)", path.name)
    year = int(match.group(1)) if match else None
    version = re.search(r"Transition_Iss\.([a-z])(?=\.|$)", path.name, re.I)
    return year, version.group(1).lower() if version else ""


def field_indexes(headers: list[str]) -> dict[str, int]:
    values = [normal(h) for h in headers]
    fields = {}
    for field, candidates in FIELD_NAMES.items():
        for candidate in candidates:
            # Exact match first to avoid "Console Software" becoming "Console".
            if candidate in values:
                fields[field] = values.index(candidate)
                break
        if field not in fields:
            for i, value in enumerate(values):
                if any(value.startswith(candidate + " ") for candidate in candidates):
                    fields[field] = i
                    break
    # Two late-2020 sheets use the column label "133h" for SKU codes.
    if "sku" not in fields and len(values) > 4 and values[2] == "133h" and values[4] == "stock item name":
        fields["sku"] = 2
    return fields


def identify_header(rows):
    """Consume at most 15 logical CSV/worksheet rows to locate a field header."""
    iterator = iter(rows)
    for index in range(15):
        row = next(iterator, None)
        if row is None:
            return None, [], iterator
        indexes = field_indexes(row)
        if "sku" in indexes and "name" in indexes:
            return index + 1, indexes, iterator
    return None, [], iterator


def csv_sheets(path: Path):
    # Generator keeps the file open while the returned iterator is consumed.
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
        yield "Imported CSV", csv.reader(stream)


def xlsx_shared_strings(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    strings = []
    with archive.open("xl/sharedStrings.xml") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag == NAMESPACE + "si":
                strings.append("".join(node.text or "" for node in element.iter(NAMESPACE + "t")))
                element.clear()
    return strings


def column_index(reference: str) -> int:
    prefix = re.match(r"[A-Z]+", reference or "")
    if not prefix:
        return -1
    value = 0
    for character in prefix.group(0):
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def xlsx_rows(stream, shared):
    for _, element in ET.iterparse(stream, events=("end",)):
        if element.tag != NAMESPACE + "row":
            continue
        values = {}
        for cell in element.findall(NAMESPACE + "c"):
            index = column_index(cell.get("r", ""))
            if index < 0 or index > 2000:
                continue
            raw = cell.find(NAMESPACE + "v")
            kind = cell.get("t", "")
            if kind == "inlineStr":
                value = "".join(node.text or "" for node in cell.iter(NAMESPACE + "t"))
            elif raw is None:
                value = ""
            elif kind == "s":
                try:
                    value = shared[int(raw.text)]
                except (ValueError, IndexError, TypeError):
                    value = ""
            else:
                value = raw.text or ""
            if value:
                values[index] = value
        if values:
            output = [""] * (max(values) + 1)
            for i, value in values.items():
                output[i] = value
            yield output
        element.clear()


def xlsx_sheets(path: Path):
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.get("Id"): item.get("Target") for item in relationships}
        shared = xlsx_shared_strings(archive)
        for sheet in workbook.findall(".//" + NAMESPACE + "sheet"):
            target = targets.get(sheet.get(REL + "id"), "")
            if not target:
                continue
            pathname = (
                target.lstrip("/") if target.startswith("/")
                else posixpath.normpath(posixpath.join("xl", target))
            )
            if not pathname.startswith("xl/worksheets/") or pathname not in archive.namelist():
                continue
            with archive.open(pathname) as stream:
                yield sheet.get("name", ""), xlsx_rows(stream, shared)


def read_sheets(path: Path):
    if path.suffix.lower() == ".csv":
        yield from csv_sheets(path)
    else:
        yield from xlsx_sheets(path)


def cell(row, fields: dict, name: str) -> str:
    index = fields.get(name, -1)
    return clean(row[index]) if 0 <= index < len(row) else ""


def prepare_record(row, fields, origin):
    sku = code_value(cell(row, fields, "sku"))
    name = cell(row, fields, "name")
    if not valid_sku(sku) or not name or normal(name) in {"tot", "total", "subtotal", "product name", "stock item name"}:
        return None
    record = {"sku": sku, **origin}
    for field in EVIDENCE_FIELDS:
        record[field] = cell(row, fields, field)
    raw_alias = code_value(cell(row, fields, "old_sku"))
    record["old_sku"] = raw_alias if valid_alias(raw_alias) and raw_alias != sku else ""
    return record


def build_master(files: list[Path], destination: Path):
    """Return a manifest and write source snapshots, canonical identities and issues.

    A newer observation wins for display, but *every* observation stays in the
    JSONL audit. Historical data does not assert price, eligibility or a
    confirmed replacement model.
    """
    destination.mkdir(parents=True, exist_ok=True)
    history_file = destination / "historical_equipment_history.jsonl"
    canonical = {}
    lineage = defaultdict(list)
    aliases = defaultdict(set)
    issues = []
    report = []
    total = 0
    source_files = sorted(files, key=lambda f: (source_info(f)[0] or 0, source_info(f)[1], str(f).lower()))
    with history_file.open("w", encoding="utf-8", newline="\n") as history:
        for source in source_files:
            year, revision = source_info(source)
            if year is None:
                report.append({"file": source.name, "status": "skipped", "reason": "No year 2020-2026 in filename"})
                continue
            try:
                sheets = read_sheets(source)
                for sheet_name, rows in sheets:
                    sheet_count = 0
                    header_at, fields, values = identify_header(rows)
                    if header_at is None:
                        report.append({"file": source.name, "sheet": sheet_name, "status": "skipped",
                                       "reason": "No SKU and product name header in first 15 rows"})
                        continue
                    seen_in_sheet = {}
                    for row_number, row in enumerate(values, start=header_at + 1):
                        origin = {"year": year, "revision": revision,
                                  "source": source.name, "sheet": sheet_name, "row": row_number}
                        record = prepare_record(row, fields, origin)
                        if record is None:
                            continue
                        sku = record["sku"]
                        if sku in seen_in_sheet:
                            prior = seen_in_sheet[sku]
                            if any(prior[field] != record[field] for field in EVIDENCE_FIELDS):
                                issues.append({"type": "conflicting_duplicate_in_source", "sku": sku,
                                               "source": source.name, "sheet": sheet_name,
                                               "rows": [prior["row"], row_number]})
                        else:
                            seen_in_sheet[sku] = record
                        if sku in canonical:
                            prior = canonical[sku]
                            for field in ("name", "model", "console", "status"):
                                if prior[field] and record[field] and prior[field] != record[field]:
                                    issues.append({"type": "changed_field", "sku": sku,
                                                   "field": field, "before": prior[field],
                                                   "after": record[field],
                                                   "before_source": prior["source"],
                                                   "after_source": source.name})
                        canonical[sku] = record
                        lineage[sku].append({"year": year, "revision": revision,
                                             "source": source.name, "sheet": sheet_name,
                                             "row": row_number})
                        if record["old_sku"]:
                            aliases[record["old_sku"]].add(sku)
                        history.write(json.dumps(record, ensure_ascii=False) + "\n")
                        total += 1
                        sheet_count += 1
                    report.append({"file": source.name, "year": year, "revision": revision,
                                   "sheet": sheet_name, "status": "read",
                                   "equipment_rows": sheet_count})
            except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError, csv.Error) as exc:
                report.append({"file": source.name, "year": year, "status": "failed", "reason": str(exc)})
    for sku, observation in canonical.items():
        observation["provenance"] = lineage[sku]
        observation["pricing_status"] = "IDENTITY ONLY - NO APPROVED RRP"
    for alias, targets in aliases.items():
        if len(targets) > 1:
            issues.append({"type": "ambiguous_old_sku", "old_sku": alias, "candidate_skus": sorted(targets)})
    (destination / "historical_equipment_master.json").write_text(
        json.dumps({k: canonical[k] for k in sorted(canonical)}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (destination / "historical_aliases.json").write_text(
        json.dumps({k: sorted(v) for k, v in sorted(aliases.items())}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (destination / "historical_review.json").write_text(
        json.dumps(issues, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    manifest = {"source_files": len(source_files), "snapshots": total,
                "unique_skus": len(canonical), "alias_codes": len(aliases),
                "review_items": len(issues),
                "by_year": dict(sorted(Counter(item["year"] for item in report if item.get("status") == "read").items())),
                "worksheets": report,
                "pricing_status": "Identity only: existing live RRP and tariff configuration unchanged."}
    (destination / "historical_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    # Output schema consumed by engine.historical_identity(). The entire
    # historical dataset is identity evidence; never an approved RRP source.
    compact = {}
    for code, item in canonical.items():
        compact[code] = {
            "sku": code, "year": item["year"], "rev": item["revision"],
            "model": item.get("model", ""), "name": item.get("name", ""),
            "console": item.get("console", ""), "status": item.get("status", ""),
            "eol": item.get("end_of_life", ""),
            "group": item.get("group", ""), "category": item.get("category", ""),
            "old_sku": item.get("old_sku", ""),
            "source": item.get("source", ""),
            "first_seen": min(entry["year"] for entry in lineage[code]),
            "evidence_only": True,
        }
    (destination / "historical_catalogue_index.json").write_text(
        json.dumps({"records": compact,
                    "aliases": {k: sorted(v) for k, v in aliases.items()}},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (destination / "historical_catalogue_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Pulse Fitness historical master catalogue importer")
    parser.add_argument("inputs", nargs="+", type=Path, help="CSV/XLSX files or directories")
    parser.add_argument("--output", type=Path, default=Path("historical_output"))
    args = parser.parse_args()
    files = []
    for item in args.inputs:
        if item.is_dir():
            files.extend(p for p in item.rglob("*") if p.is_file()
                         and p.suffix.lower() in SOURCE_EXTS and not p.name.startswith("~$"))
        elif item.is_file() and item.suffix.lower() in SOURCE_EXTS:
            files.append(item)
        else:
            parser.error(f"Missing or unsupported source: {item} (legacy .xls must be converted to CSV UTF-8)")
    if not files:
        parser.error("No supported master files found")
    summary = build_master(files, args.output)
    print(json.dumps({key: summary[key] for key in
                      ("source_files", "snapshots", "unique_skus", "alias_codes", "review_items")},
                     indent=2))
    if any(item["status"] == "failed" for item in summary["worksheets"]):
        sys.exit(2)


if __name__ == "__main__":
    main()
