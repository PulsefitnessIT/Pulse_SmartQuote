"""Portable Windows launcher for the *internal* SmartQuote V10 pilot.

This is the entrypoint for the GitHub Actions PyInstaller Windows ZIP. The
standard GitHub source ZIP retains start_windows.bat and requires Python.
The frozen build has an embedded Python runtime and requires no staff-side pip.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import threading
import webbrowser


def installation_directory():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def validate_portable_directory(root=None):
    root = Path(root) if root is not None else installation_directory()
    expected = ("data/catalog.json", "data/pricing.json", "static/index.html")
    missing = [item for item in expected if not (root / item).is_file()]
    if missing:
        raise RuntimeError(
            "Incomplete Windows application download. Missing: " + ", ".join(missing)
            + ". Extract the entire Windows Portable ZIP (not Code > Download ZIP) "
            "into a writable folder before opening Start_SmartQuote_V10.bat."
        )
    return root


def initialise_admin():
    import security
    if not security.enabled():
        print("TEST MODE: local sign-in is disabled by SMARTQUOTE_AUTH.", flush=True)
        return
    if security.count():
        return
    print("\nWelcome to Pulse Fitness SmartQuote V10.")
    print("One-time setup: create a local administrator login (12+ character password).")
    import manage_users
    original_argv = sys.argv
    try:
        sys.argv = ["manage_users.py", "bootstrap"]
        manage_users.main()
    finally:
        sys.argv = original_argv
    if not security.count():
        raise RuntimeError("Administrator setup was not completed.")


def serve(no_browser=False, check=False):
    root = validate_portable_directory()
    os.chdir(root)
    # Import the app after switching to the installed folder. This keeps the
    # catalogue and local SQLite data beside the EXE, not inside a temporary dir.
    import main
    import startup_manager
    if Path(main.ROOT).resolve() != root.resolve():
        raise RuntimeError("Bundled application data path does not match the installation directory.")
    if check:
        print("INSTALLATION CHECK PASSED: bundled Python, server, catalogue and UI are present.", flush=True)
        return 0

    initialise_admin()
    port, already_running = startup_manager.choose_port(root)
    url = startup_manager.app_url(port)
    if already_running:
        print("This same V10 installation is already running at " + url, flush=True)
        if not no_browser:
            webbrowser.open(url)
        return 0
    if port != startup_manager.PORT:
        print("Port 8765 is in use by another program. Using " + url, flush=True)
    print("\nPULSE FITNESS SMARTQUOTE V10 — CONTROLLED INTERNAL PILOT")
    print("Application: " + str(root))
    print("Open in your browser: " + url)
    print("Leave this window open while SmartQuote is running. Press Ctrl+C to stop.", flush=True)
    if not no_browser:
        threading.Thread(target=startup_manager.open_when_ready, args=(port, root), daemon=True).start()
    import uvicorn
    uvicorn.run(main.app, host="127.0.0.1", port=port, log_level="info", access_log=False)
    return 0


def main_cli(argv=None):
    p = argparse.ArgumentParser(description="Run SmartQuote V10 Windows Portable")
    p.add_argument("--check", action="store_true", help="Confirm bundled application completeness")
    p.add_argument("--no-browser", action="store_true", help="Don't open a browser (test automation)")
    opts = p.parse_args(argv)
    try:
        return serve(no_browser=opts.no_browser, check=opts.check)
    except (RuntimeError, OSError, ValueError) as exc:
        print("\nSMARTQUOTE COULD NOT START: " + str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
