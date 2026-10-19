"""Build a clean, reproducible V10 *pilot*, never an approved customer release.

Includes the exact checkout, an integrity manifest and optional historical identity
index. Omits private databases, backups, local accounts, raw masters and secrets.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from catalogue_readiness import evaluate

ROOT = Path(__file__).resolve().parent
ALLOWED_DATA = {
    "2025_master_legacy_index.json", "catalog.json", "configs.json",
    "legacy.json", "pricing.json", "historical_catalogue_index.json",
    "historical_catalogue_manifest.json",
}
ROOT_EXTENSIONS = {".py", ".md", ".txt", ".bat", ".sh"}
PREFIX = "SmartQuote_V10/"


def source_files(root=ROOT):
    root = Path(root)
    files = [p for p in root.iterdir()
             if p.is_file() and (p.suffix.lower() in ROOT_EXTENSIONS or p.name == "requirements.txt")]
    for directory in ("static", "samples", "docs", "tests"):
        path = root / directory
        if path.is_dir():
            files.extend(p for p in path.rglob("*")
                         if p.is_file() and "__pycache__" not in p.parts
                         and p.suffix.lower() not in {".pyc", ".pyo"})
    data = root / "data"
    if data.is_dir():
        files.extend(data / name for name in ALLOWED_DATA if (data / name).is_file())
    return sorted(set(files), key=lambda p: p.relative_to(root).as_posix())


def build(output, root=ROOT):
    root = Path(root)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = source_files(root)
    readiness = evaluate(root)
    manifest = {
        "product": "Pulse Fitness SmartQuote V10",
        "release_class": "CONTROLLED INTERNAL PILOT - NOT CUSTOMER APPROVED",
        "historical_index_included": readiness["historical"]["index_loaded"],
        "automated_preflight_passes": readiness["automated_preflight_passes"],
        "preflight_warnings": readiness["warnings"],
        "sha256": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in files},
    }
    with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=7) as archive:
        for file in files:
            archive.write(file, PREFIX + file.relative_to(root).as_posix())
        archive.writestr(PREFIX + "BUILD_REPORT.json", json.dumps(manifest, indent=2))
        archive.writestr(PREFIX + "READ_THIS_FIRST.txt",
                         "INTERNAL PILOT ONLY. Not a customer release.\n"
                         "The historical index may be absent: inspect BUILD_REPORT.json.\n"
                         "Install full 2020-2026 index with install_historical_catalogue.py.\n"
                         "Keep and back up existing smartquote_local.db separately.\n"
                         "Never copy this archive over an existing installation.\n"
                         "Review RRPs and tariffs before customer quotations.\n")
    verify(output)
    return manifest


def verify(path):
    with ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive integrity check failed.")
        report = json.loads(archive.read(PREFIX + "BUILD_REPORT.json"))
        for filename, expected in report["sha256"].items():
            actual = hashlib.sha256(archive.read(PREFIX + filename)).hexdigest()
            if actual != expected:
                raise ValueError(f"Content hash mismatch: {filename}")
        required = {"main.py", "engine.py", "start_windows.bat",
                    "data/catalog.json", "data/pricing.json", "static/index.html"}
        if not required.issubset(report["sha256"]):
            raise ValueError("Required application files missing from pilot package.")
        if any(("smartquote_local.db" in s or "historical_backups" in s)
               for s in archive.namelist()):
            raise ValueError("Private or backup application data was included.")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dist/Pulse_Fitness_SmartQuote_V10_Internal_Pilot.zip")
    args = parser.parse_args()
    result = build(args.output)
    print(json.dumps({
        "output": args.output, "release_class": result["release_class"],
        "preflight_passes": result["automated_preflight_passes"],
        "files": len(result["sha256"]),
    }))


if __name__ == "__main__":
    main()
