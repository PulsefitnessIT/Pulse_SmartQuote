# SmartQuote V10: Browser connection and upload reliability

## Why a V9 screen can appear after starting V10

Older SmartQuote V9 and V10 both used localhost port 8765 and an identical
`/api/health` application name. Prior launchers considered the old server a
valid response and reopened the V9 browser page. A browser-side `Failed to
fetch` cannot diagnose the file content: it means the HTTP request could not
complete. Other causes include closing the command window, server crashes or
an interrupted localhost request.

## Corrected startup

- V10 health includes a protocol version and a deterministic instance fingerprint.
- The launcher reuses a server only if it matches this exact V10 folder.
- If an earlier SmartQuote instance occupies 8765, V10 starts on the next
  available loopback port from 8766 to 8772 and opens that exact URL.
- The application still binds to 127.0.0.1, never to the external network.
- An unresponsive backend displays a specific staff-facing instruction rather
  than a raw `Failed to fetch` browser error.
- Requests that could change a quotation are **never automatically retried**;
  coordinators should inspect the quote and avoid duplicate imports.

## Staff instructions

1. Extract the latest GitHub ZIP into a NEW directory.
2. Run `start_windows.bat` and leave the command window open.
3. Use the address which the launcher opens. It may be `127.0.0.1:8766` if
   an older V9 app is already occupying 8765.
4. Confirm the page heading reads **V10 INTERNAL PILOT**.
5. Upload `M Club Newcastle.xlsx` and review the preview showing 165 asset
   rows, 165 units and 72 equipment groups before confirming.
6. If upload fails, leave the command window open and report its last messages;
   the uploaded spreadsheet itself remains unchanged.

## Verification

API unit tests cover the version and installation checks, port selection and
end-to-end synthetic CSV preview / commit / duplicate protection. The real M
Club workbook was exercised locally, not checked in to GitHub.

This is a controlled internal pilot; commercial RRPs remain unapproved.
