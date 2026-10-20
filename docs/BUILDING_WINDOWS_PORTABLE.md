# V10 no-Python Windows pilot — deployment notes

This is a separate, controlled Windows application build produced from the **existing** `develop/v10` branch. It does **not** merge to `main`, authorise RRPs or turn SmartQuote into a network/multi-user production application.

## Why

`Code > Download ZIP` on GitHub downloads Python *source code*. `start_windows.bat` can use that source on developer PCs **only if Python 3.11 or newer is installed**. Staff should instead use the `SmartQuote-V10-Windows-No-Python` GitHub Actions artifact created by the `windows_portable` workflow job.

## What GitHub packages

1. Builds and checksum-verifies the pilot source ZIP; excludes existing quotes, local users, database files, backup folders and raw master workbooks.
2. On a Windows runner, uses PyInstaller (onedir) to bundle Python, FastAPI, Uvicorn, PDF dependencies, static interface and the authorised *staging/evidence* catalogue into one extracted directory.
3. Tests the actual `Pulse_SmartQuote_V10.exe` with `--check`, then starts it, calls `/api/health`, creates a draft quotation, previews and imports a synthetic asset.
4. Removes all test-created SQLite files before uploading the portable folder as the `SmartQuote-V10-Windows-No-Python` artifact.
5. Includes `BUILD_SHA256.txt` for the executable and a staff quick-start guide.

The download is an **unsigned** portable EXE, not an MSI or digitally signed production installer. IT approval may be required. Do not tell staff to bypass Windows SmartScreen or enterprise security policies.

## How to install/test

1. GitHub → Actions → most recent successful `SmartQuote V10 Python tests` run for `develop/v10` → Artifacts → `SmartQuote-V10-Windows-No-Python`.
2. Extract ZIP fully (one extraction, not the nested development source artifact).
3. Double-click `Start_SmartQuote_V10.bat` or `Pulse_SmartQuote_V10.exe`.
4. On the first run, create a local admin login. Confirm the browser says **V10 INTERNAL PILOT**.
5. Test a sample quote and M Club Newcastle imports.

## Maintaining customer data

The portable exe runs from the extracted directory, where it creates `smartquote_local.db`. The exe bundle excludes any `.db` or `.sqlite` files. On upgrading, install to a new folder; back up existing `smartquote_local.db` and move it manually **only after reviewing the version and migration strategy**. Do not delete the previous folder or store SQLite on an insecure share.

The portable build runs only on `127.0.0.1` and is not an internet-facing server. Staff acceptance, business pricing approval, security review, code signing and automated backups remain release gates.
