"""
evaluation/stats.py
--------------------
Statistical analysis for the secure coding study.

Primary test
------------
Mann-Whitney U (scipy.stats.mannwhitneyu) comparing vulnerability scores
between baseline and multiagent conditions. Used because:
  - Small samples (n=26 per condition)
  - Vulnerability counts are likely non-normally distributed
  - Non-parametric test is the appropriate choice (Perry et al., 2023)

Secondary analysis
------------------
Wilcoxon signed-rank within each condition across tasks, controlling for
task_order effects. Kruskal-Wallis across task_id to check task difficulty
as a confound.

Effect size
-----------
r = Z / sqrt(N)  where N = total observations across both groups.
Benchmarks: small=0.1, medium=0.3, large=0.5 (Cohen, 1988).

Usage
-----
    python -m evaluation.stats

    # or import for custom analysis:
    from evaluation.stats import run_analysis
    results = run_analysis()
"""

import json
from pathlib import Path
from typing import Optional

import numpy as np
from scipy import stats as scipy_stats

from evaluation.scoring import load_scores

RESULTS_PATH = Path("logs/stats_results.json")


# -- Core analysis ------------------------------------------------------------

def _effect_size_r(u_stat: float, n1: int, n2: int) -> float:
    """Convert Mann-Whitney U to effect size r via Z approximation."""
    n   = n1 * n2
    mu  = n / 2
    sigma = (n * (n1 + n2 + 1) / 12) ** 0.5
    if sigma == 0:
        return 0.0
    z = (u_stat - mu) / sigma
    return abs(z) / ((n1 + n2) ** 0.5)


def _descriptives(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "std": None,
                "min": None, "max": None}
    arr = np.array(values, dtype=float)
    return {
        "n":      len(arr),
        "mean":   round(float(np.mean(arr)), 3),
        "median": round(float(np.median(arr)), 3),
        "std":    round(float(np.std(arr, ddof=1)), 3),
        "min":    round(float(np.min(arr)), 3),
        "max":    round(float(np.max(arr)), 3),
    }


def _mann_whitney(a: list[float], b: list[float], label: str) -> dict:
    """Run Mann-Whitney U and return a result dict."""
    if len(a) < 2 or len(b) < 2:
        return {"test": label, "error": "insufficient data (need n>=2 per group)"}

    u_stat, p_value = scipy_stats.mannwhitneyu(a, b, alternative="two-sided")
    r = _effect_size_r(u_stat, len(a), len(b))

    return {
        "test":      label,
        "U":         round(float(u_stat), 3),
        "p_value":   round(float(p_value), 4),
        "significant": bool(p_value < 0.05),
        "effect_r":  round(r, 3),
        "effect_magnitude": (
            "large"  if r >= 0.5 else
            "medium" if r >= 0.3 else
            "small"  if r >= 0.1 else
            "negligible"
        ),
        "n_baseline":    len(a),
        "n_multiagent":  len(b),
    }


def _kruskal_wallis(groups: dict[str, list[float]], label: str) -> dict:
    """Kruskal-Wallis H test across multiple groups (e.g. tasks)."""
    valid = {k: v for k, v in groups.items() if len(v) >= 2}
    if len(valid) < 2:
        return {"test": label, "error": "need at least 2 groups with n>=2"}

    h_stat, p_value = scipy_stats.kruskal(*valid.values())
    return {
        "test":    label,
        "H":       round(float(h_stat), 3),
        "p_value": round(float(p_value), 4),
        "significant": bool(p_value < 0.05),
        "groups":  list(valid.keys()),
    }


def _wilcoxon_task_order(records: list[dict], condition: str) -> dict:
    """
    Wilcoxon signed-rank on task_order within one condition.

    Pairs task_order=1 with task_order=4 for each participant to test
    whether performance changes across the session (learning effect).
    """
    label = f"wilcoxon_task_order_{condition}"
    pid_records: dict[str, dict] = {}
    for r in records:
        if r.get("condition") != condition:
            continue
        pid   = r.get("participant_id", "")
        order = r.get("task_order")
        if pid and order in (1, 4):
            pid_records.setdefault(pid, {})[order] = r.get("vuln_count", 0)

    paired_first = []
    paired_last  = []
    for scores in pid_records.values():
        if 1 in scores and 4 in scores:
            paired_first.append(scores[1])
            paired_last.append(scores[4])

    if len(paired_first) < 4:
        return {"test": label, "error": f"insufficient paired data (n={len(paired_first)})"}

    stat, p_value = scipy_stats.wilcoxon(paired_first, paired_last)
    return {
        "test":      label,
        "W":         round(float(stat), 3),
        "p_value":   round(float(p_value), 4),
        "significant": bool(p_value < 0.05),
        "n_pairs":   len(paired_first),
        "note":      "Compares task_order=1 vs task_order=4 scores (learning effect check)",
    }


# -- Main analysis ------------------------------------------------------------

def run_analysis(records: Optional[list[dict]] = None) -> dict:
    """
    Run the full statistical analysis and return a results dict.

    Results are also written to logs/stats_results.json.
    """
    if records is None:
        records = load_scores()

    baseline   = [r for r in records if r.get("condition") == "baseline"]
    multiagent = [r for r in records if r.get("condition") == "multiagent"]

    # -- Descriptives ----------------------------------------------------------
    desc = {
        "baseline": {
            "vuln_count":     _descriptives([r["vuln_count"]     for r in baseline]),
            "severity_score": _descriptives([r["severity_score"] for r in baseline]),
            "high_count":     _descriptives([r["high_count"]     for r in baseline]),
        },
        "multiagent": {
            "vuln_count":     _descriptives([r["vuln_count"]     for r in multiagent]),
            "severity_score": _descriptives([r["severity_score"] for r in multiagent]),
            "high_count":     _descriptives([r["high_count"]     for r in multiagent]),
        },
    }

    # -- Primary: Mann-Whitney U -----------------------------------------------
    mw_vuln = _mann_whitney(
        [r["vuln_count"]     for r in baseline],
        [r["vuln_count"]     for r in multiagent],
        "mann_whitney_vuln_count",
    )
    mw_severity = _mann_whitney(
        [r["severity_score"] for r in baseline],
        [r["severity_score"] for r in multiagent],
        "mann_whitney_severity_score",
    )
    mw_high = _mann_whitney(
        [r["high_count"]     for r in baseline],
        [r["high_count"]     for r in multiagent],
        "mann_whitney_high_count",
    )

    # -- Confound check: task difficulty (Kruskal-Wallis across task_id) -------
    task_groups_bl = {}
    task_groups_ma = {}
    for r in baseline:
        tid = r.get("task_id") or "unknown"
        task_groups_bl.setdefault(tid, []).append(r["vuln_count"])
    for r in multiagent:
        tid = r.get("task_id") or "unknown"
        task_groups_ma.setdefault(tid, []).append(r["vuln_count"])

    kw_baseline   = _kruskal_wallis(task_groups_bl, "kruskal_task_difficulty_baseline")
    kw_multiagent = _kruskal_wallis(task_groups_ma, "kruskal_task_difficulty_multiagent")

    # -- Learning effect: Wilcoxon across task_order --------------------------
    wilcoxon_bl = _wilcoxon_task_order(records, "baseline")
    wilcoxon_ma = _wilcoxon_task_order(records, "multiagent")

    results = {
        "n_sessions":  {"baseline": len(baseline), "multiagent": len(multiagent)},
        "descriptives": desc,
        "primary_tests": [mw_vuln, mw_severity, mw_high],
        "confound_checks": [kw_baseline, kw_multiagent],
        "learning_effect": [wilcoxon_bl, wilcoxon_ma],
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results


# -- CLI report ---------------------------------------------------------------

def _fmt(val) -> str:
    return "N/A" if val is None else str(val)


def print_report(results: Optional[dict] = None) -> None:
    if results is None:
        results = run_analysis()

    n = results["n_sessions"]
    print(f"\n{'='*60}")
    print(f"SECURE CODING STUDY — STATISTICAL RESULTS")
    print(f"{'='*60}")
    print(f"Sessions: baseline={n['baseline']}  multiagent={n['multiagent']}")

    print(f"\n--- DESCRIPTIVE STATISTICS ---")
    for condition in ("baseline", "multiagent"):
        d = results["descriptives"][condition]
        print(f"\n  {condition.upper()}")
        for metric, vals in d.items():
            print(
                f"    {metric:<20} "
                f"mean={_fmt(vals['mean'])}  "
                f"median={_fmt(vals['median'])}  "
                f"std={_fmt(vals['std'])}  "
                f"n={vals['n']}"
            )

    print(f"\n--- PRIMARY TESTS (Mann-Whitney U) ---")
    for t in results["primary_tests"]:
        if "error" in t:
            print(f"\n  {t['test']}: {t['error']}")
            continue
        sig = "*** SIGNIFICANT ***" if t["significant"] else "not significant"
        print(
            f"\n  {t['test']}\n"
            f"    U={t['U']}  p={t['p_value']}  r={t['effect_r']} "
            f"({t['effect_magnitude']})  {sig}"
        )

    print(f"\n--- CONFOUND CHECK (Kruskal-Wallis: task difficulty) ---")
    for t in results["confound_checks"]:
        if "error" in t:
            print(f"  {t['test']}: {t['error']}")
            continue
        sig = "significant — task difficulty is a confound" if t["significant"] else "not significant"
        print(f"  {t['test']}: H={t['H']}  p={t['p_value']}  {sig}")

    print(f"\n--- LEARNING EFFECT (Wilcoxon: task_order 1 vs 4) ---")
    for t in results["learning_effect"]:
        if "error" in t:
            print(f"  {t['test']}: {t['error']}")
            continue
        sig = "significant — order effect present" if t["significant"] else "not significant"
        print(f"  {t['test']}: W={t['W']}  p={t['p_value']}  n={t['n_pairs']} pairs  {sig}")

    print(f"\nFull results written to: {RESULTS_PATH}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print_report()