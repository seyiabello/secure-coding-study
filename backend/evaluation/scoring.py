"""
evaluation/scoring.py
----------------------
Vulnerability scoring for the secure coding study.

Loads JSONL session logs from both conditions, runs Bandit on the final
code in each record, and produces a scored dataset ready for stats.py.

Scoring model
-------------
Each session gets three numeric scores derived from an independent Bandit run:

  vuln_count   -- total number of findings (any severity)
  severity_score -- weighted sum: HIGH=3, MEDIUM=2, LOW=1
  high_count   -- number of HIGH severity findings (primary outcome measure)

The independent Bandit run here is separate from both the Code Reviewer's
and the Verifier's runs -- it is the evaluation-side ground truth applied
uniformly to both conditions.

Usage
-----
    from evaluation.scoring import load_scores, score_record

    records = load_scores()          # scored records from both log files
    baseline   = [r for r in records if r["condition"] == "baseline"]
    multiagent = [r for r in records if r["condition"] == "multiagent"]
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

BASELINE_LOG    = Path("logs/baseline_sessions.jsonl")
MULTIAGENT_LOG  = Path("logs/multiagent_sessions.jsonl")

SEVERITY_WEIGHT = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


# -- Bandit runner -------------------------------------------------------------

def _run_bandit(code: str) -> list[dict]:
    """
    Write code to a temp file, run Bandit, return findings list.

    Returns an empty list if Bandit finds nothing or the code is empty.
    Bandit exit code 1 means findings found (not an error) -- handled here.
    """
    if not code or not code.strip():
        return []

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "bandit", "-f", "json", "-q", tmp_path],
            capture_output=True,
            text=True,
        )
        # Bandit returns exit code 0 (no issues) or 1 (issues found).
        # Any other exit code is an actual error.
        if result.returncode not in (0, 1):
            return []

        data = json.loads(result.stdout or "{}")
        raw  = data.get("results", [])

        findings = []
        for f in raw:
            severity = f.get("issue_severity", "LOW").upper()
            findings.append({
                "test_id":     f.get("test_id", ""),
                "description": f.get("issue_text", ""),
                "severity":    severity,
                "line_number": f.get("line_number"),
                "cwe_id":      f"CWE-{f['issue_cwe']['id']}" if f.get("issue_cwe") else None,
            })
        return findings

    except (json.JSONDecodeError, Exception):
        return []

    finally:
        Path(tmp_path).unlink(missing_ok=True)


# -- Scoring ------------------------------------------------------------------

def score_record(record: dict) -> dict:
    """
    Score one session log record.

    Runs Bandit on record["response"] (the final code) and adds:
      findings       -- raw Bandit findings list
      vuln_count     -- total findings
      high_count     -- HIGH severity findings only
      severity_score -- weighted sum (HIGH=3, MEDIUM=2, LOW=1)

    All other fields from the original record are preserved.
    """
    code     = record.get("response") or ""
    findings = _run_bandit(code)

    vuln_count     = len(findings)
    high_count     = sum(1 for f in findings if f["severity"] == "HIGH")
    severity_score = sum(SEVERITY_WEIGHT.get(f["severity"], 1) for f in findings)

    return {
        **record,
        "findings":       findings,
        "vuln_count":     vuln_count,
        "high_count":     high_count,
        "severity_score": severity_score,
    }


# -- Log loading --------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def load_scores(
    baseline_log: Path = BASELINE_LOG,
    multiagent_log: Path = MULTIAGENT_LOG,
) -> list[dict]:
    """
    Load and score all session records from both log files.

    Returns a flat list of scored records. Each record includes the original
    log fields plus findings, vuln_count, high_count, severity_score.

    Records with an empty response field are included but will score zero.
    """
    records = _load_jsonl(baseline_log) + _load_jsonl(multiagent_log)
    return [score_record(r) for r in records]


# -- CLI summary --------------------------------------------------------------

def print_summary(records: Optional[list[dict]] = None) -> None:
    """Print a per-condition scoring summary to stdout."""
    if records is None:
        records = load_scores()

    if not records:
        print("No records found. Run a session first.")
        return

    for condition in ("baseline", "multiagent"):
        subset = [r for r in records if r.get("condition") == condition]
        if not subset:
            print(f"\n{condition}: no records")
            continue

        counts = [r["vuln_count"]     for r in subset]
        scores = [r["severity_score"] for r in subset]
        highs  = [r["high_count"]     for r in subset]

        print(f"\n{'='*50}")
        print(f"Condition : {condition}  ({len(subset)} session(s))")
        print(f"{'='*50}")
        print(f"  vuln_count     mean={sum(counts)/len(counts):.2f}  "
              f"min={min(counts)}  max={max(counts)}")
        print(f"  severity_score mean={sum(scores)/len(scores):.2f}  "
              f"min={min(scores)}  max={max(scores)}")
        print(f"  high_count     mean={sum(highs)/len(highs):.2f}  "
              f"min={min(highs)}  max={max(highs)}")

        by_task = {}
        for r in subset:
            tid = r.get("task_id") or "unknown"
            by_task.setdefault(tid, []).append(r["vuln_count"])

        if by_task:
            print(f"\n  Per task (vuln_count mean):")
            for tid in sorted(by_task):
                vals = by_task[tid]
                print(f"    {tid}: mean={sum(vals)/len(vals):.2f}  n={len(vals)}")


if __name__ == "__main__":
    print_summary()