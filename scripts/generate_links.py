#!/usr/bin/env python3
"""
scripts/generate_links.py
--------------------------
Generates participant study links from data/participants.json.

Usage:
    BASE_URL=https://your-app.vercel.app python scripts/generate_links.py

Prints one line per participant and writes scripts/participant_links.csv.
The CSV is gitignored because it maps participant IDs to conditions and
should not be committed to a public repository.
"""

import csv
import json
import os
import pathlib
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

participants_file = ROOT / "data" / "participants.json"
output_csv = HERE / "participant_links.csv"

base_url = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")

with open(participants_file) as f:
    participants: dict[str, str] = json.load(f)

rows = []
print(f"{'PID':<8} {'Condition':<12} URL")
print("-" * 80)

for pid, condition in sorted(participants.items()):
    params = urllib.parse.urlencode({"pid": pid, "condition": condition})
    url = f"{base_url}/study?{params}"
    print(f"{pid:<8} {condition:<12} {url}")
    rows.append({"participant_id": pid, "condition": condition, "url": url, "email_sent": "FALSE"})

with open(output_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["participant_id", "condition", "url", "email_sent"])
    writer.writeheader()
    writer.writerows(rows)

print(f"\n{len(rows)} links written to {output_csv}")
