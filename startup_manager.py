"""Local Windows SmartQuote startup helper (standard library only).

Never downloads app source or mutates an existing quotation database. A downloaded
GitHub checkout / pilot ZIP is the application; only Python wheel dependencies
are installed into a private .venv on first run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
PORT = 8765
URL = f"http://127.0.0.1:{PORT}"
CHECK_IMPORTS = "import fastapi, uvicorn, reportlab, fitz"


class SetupError(RuntimeError):
    pass


def validate_source(root=ROOT):
    root = Path(root)
    required = (
        "main.py", "engine.py", "manage_users.py", "requirements.txt",
        "data/catalog.json", "data/pricing.json", "static/index.html",
    )
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise SetupError(
            "This download is missing application files: " + ", ".join(missing)
            + ". Download the entire SmartQuote folder from GitHub and use "
            + "Extract All (do not run the launcher inside the ZIP). "
            + "If using an Actions artifact, extract both ZIP layers."
        )
    if sys.version_info < (3, 11):
        raise SetupError("Python 3.11 or newer is required. Please install Python 3.11 from python.org.")
    return root


def environment_python(root=ROOT):
    env_dir = Path(root) / ".venv"
    return env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def requirements_fingerprint(root=ROOT):
    # Hash the *entire* requirements file; dependency changes prompt reinstall.
    return hashlib.sha256((Path(root) / "requirements.txt").read_bytes()).hexdigest()


def dependency_status(root=ROOT):
    root = Path(root)
    interpreter = environment_python(root)
    marker = root / ".venv" / ".smartquote_dependencies.json"
    if not interpreter.is_file() or not marker.is_file():
        return False
    try:
        state = json.loads(marker.read_text(encoding="utf-8"))
        if state.get("requirements_sha256") != requirements_fingerprint(root):
            return False
        completed = subprocess.run(
            [str(interpreter), "-c", CHECK_IMPORTS],
            cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, timeout=30,
        )
        return completed.returncode == 0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def prepare_dependencies(root=ROOT):
    root = validate_source(root)
    interpreter = environment_python(root)
    if not interpreter.is_file():
        print("[1/3] Creating an isolated Python environment ...", flush=True)
        try:
            subprocess.run([sys.executable, "-m", "venv", str(root / ".venv")],
                           cwd=root, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SetupError(
                "Could not create .venv. Extract the ZIP to a writable folder, "
                "for example Documents\\SmartQuote_V10. Check free disk space."
            ) from exc
    if not interpreter.is_file():
        raise SetupError("The Python environment did not create a runnable interpreter.")

    if dependency_status(root):
        print("[2/3] Python packages already installed; skipping download.", flush=True)
        return interpreter

    print("[2/3] Installing SmartQuote packages (first run requires internet) ...", flush=True)
    try:
        subprocess.run(
            [str(interpreter), "-m", "pip", "install", "--disable-pip-version-check",
             "-r", str(root / "requirements.txt")],
            cwd=root, check=True,
        )
        subprocess.run([str(interpreter), "-c", CHECK_IMPORTS], cwd=root, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SetupError(
            "Python dependency installation failed. Check your internet connection, "
            "firewall/proxy and Python version, then retry. "
            "Your existing quotations have not been changed."
        ) from exc
    marker = root / ".venv" / ".smartquote_dependencies.json"
    marker.write_text(json.dumps({
        "requirements_sha256": requirements_fingerprint(root),
        "python_executable": str(interpreter),
    }, indent=2), encoding="utf-8")
    return interpreter


def smartquote_running():
    # Do not open unrelated services that happen to use the same port.
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=1.5) as result:
            health = json.load(result)
            return health.get("ok") is True and health.get("name") == "Pulse Fitness SmartQuote"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def port_in_use():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
            return True
    except OSError:
        return False


def open_when_ready(timeout=45):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if smartquote_running():
            webbrowser.open(URL)
            return
        time.sleep(0.5)


def start(root=ROOT, check_only=False):
    root = validate_source(root)
    print("SmartQuote V10 - Internal Pilot", flush=True)
    print("Application folder: " + str(root), flush=True)
    interpreter = prepare_dependencies(root)
    if check_only:
        print("[3/3] INSTALLATION CHECK PASSED. All startup files and packages are available.", flush=True)
        print("To launch SmartQuote, double-click start_windows.bat without --check.")
        return 0

    if smartquote_running():
        print("SmartQuote is already running. Opening the existing browser page.", flush=True)
        webbrowser.open(URL)
        return 0
    if port_in_use():
        raise SetupError("Port 8765 is already in use by another application. Close it or contact IT.")

    print("[3/3] Checking staff sign-in ...", flush=True)
    try:
        subprocess.run([str(interpreter), "manage_users.py", "bootstrap"], cwd=root, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SetupError("Staff account setup was cancelled or failed. No server started.") from exc

    print("Starting SmartQuote securely on this computer: " + URL, flush=True)
    print("Leave this window open while using SmartQuote; close it to stop the server.", flush=True)
    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        process = subprocess.run(
            [str(interpreter), "-m", "uvicorn", "main:app",
             "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=root,
        )
    except OSError as exc:
        raise SetupError("Unable to launch the SmartQuote server: " + str(exc)) from exc
    if process.returncode:
        raise SetupError(f"SmartQuote server exited with error code {process.returncode}.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare and start Pulse Fitness SmartQuote V10")
    parser.add_argument("--check", action="store_true", help="Verify complete installation without starting the server")
    opts = parser.parse_args(argv)
    try:
        return start(check_only=opts.check)
    except SetupError as exc:
        print("\nSTARTUP ERROR: " + str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
