#!/usr/bin/env sh
set -e
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt
python3 manage_users.py bootstrap
python3 -m uvicorn main:app --host 127.0.0.1 --port 8765
