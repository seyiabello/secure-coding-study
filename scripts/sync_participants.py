"""
scripts/sync_participants.py
-----------------------------
Sync data/participants.json from a CSV export of the Google Sheet.

The Apps Script assigns participant IDs and sends study links.
Export the sheet as CSV and run this script to keep the backend in sync.

Expected CSV columns (case-insensitive):
    participant_id, condition

Usage:
    python scripts/sync_participants.py --csv path/to/sheet_export.csv [--dry-run]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

PARTICIPANTS_FILE = Path(__file__).resolve().parent.parent / "data" / "participants.json"
VALID_CONDITIONS = {"baseline", "multiagent"}


def load_csv(path: Path) -> dict[str, str]:
    new_entries: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Normalise header names to lowercase
        if reader.fieldnames is None:
            print("Error: CSV appears to be empty.", file=sys.stderr)
            sys.exit(1)
        headers = [h.strip().lower() for h in reader.fieldnames]
        if "participant_id" not in headers or "condition" not in headers:
            print(
                f"Error: CSV must have 'participant_id' and 'condition' columns. "
                f"Found: {reader.fieldnames}",
                file=sys.stderr,
            )
            sys.exit(1)
        for row in reader:
            normalised = {k.strip().lower(): v.strip() for k, v in row.items()}
            pid = normalised.get("participant_id", "").strip()
            condition = normalised.get("condition", "").strip().lower()
            if not pid:
                continue
            if condition not in VALID_CONDITIONS:
                print(
                    f"Warning: skipping {pid!r} — unrecognised condition {condition!r}",
                    file=sys.stderr,
                )
                continue
            new_entries[pid] = condition
    return new_entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync participants.json from CSV export.")
    parser.add_argument("--csv", required=True, help="Path to the CSV export from Google Sheets.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing anything.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Error: file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    # Load existing data
    existing: dict[str, str] = {}
    if PARTICIPANTS_FILE.exists():
        try:
            with open(PARTICIPANTS_FILE) as f:
                existing = json.load(f)
        except json.JSONDecodeError:
            print("Warning: existing participants.json is invalid — will overwrite.", file=sys.stderr)

    incoming = load_csv(csv_path)
    merged = {**existing, **incoming}

    added   = {pid for pid in incoming if pid not in existing}
    changed = {pid for pid in incoming if pid in existing and existing[pid] != incoming[pid]}
    removed = set(existing) - set(incoming)  # informational only — we never remove entries

    print(f"Existing entries : {len(existing)}")
    print(f"Incoming entries : {len(incoming)}")
    print(f"Added            : {len(added)}")
    print(f"Changed condition: {len(changed)}")
    print(f"Not in CSV       : {len(removed)} (retained)")

    if changed:
        for pid in sorted(changed):
            print(f"  CHANGED {pid}: {existing[pid]!r} -> {incoming[pid]!r}", file=sys.stderr)

    if args.dry_run:
        print("\nDry run — no changes written.")
        return

    PARTICIPANTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PARTICIPANTS_FILE, "w") as f:
        json.dump(merged, f, indent=2)
        f.write("\n")

    print(f"\nWrote {len(merged)} entries to {PARTICIPANTS_FILE}")


if __name__ == "__main__":
    main()
