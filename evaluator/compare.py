import json
import sys
from pathlib import Path

TOLERANCE = 0.05  # allowed drop in the average pass rate (5 points)


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data, {case["id"]: case for case in data["cases"]}


def newest_run():
    files = sorted(Path("results").glob("run_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit("No run files found in results/. Run evaluator\\run_eval.py first.")
    return files[-1]


def average(by_id, ids):
    return sum(by_id[i]["pass_rate"] for i in ids) / len(ids)


def main_reason(case):
    bad = [d for d in case.get("diagnoses", []) if d != "pass"]
    return max(set(bad), key=bad.count) if bad else "unknown"


# 1. Which two report cards to compare
current_path = Path(sys.argv[1]) if len(sys.argv) > 1 else newest_run()
baseline_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("baseline.json")

base_data, base = load(baseline_path)
cur_data, cur = load(current_path)

# 2. Compare only the cases both runs contain
shared = sorted(set(base) & set(cur))
if len(shared) < len(base):
    print(f"Note: the current run has {len(shared)} of {len(base)} baseline cases; comparing those only.")

base_avg = average(base, shared)
cur_avg = average(cur, shared)
drop = base_avg - cur_avg

print(f"Baseline: {baseline_path}  ({base_data['runs']} run(s) per case, {base_avg:.1%})")
print(f"Current:  {current_path}  ({cur_data['runs']} run(s) per case, {cur_avg:.1%})")
print(f"Change in average pass rate: {(cur_avg - base_avg) * 100:+.1f} points (allowed drop: {TOLERANCE * 100:.0f})")
print()

# 3. Case by case
worse, better, broken = [], [], []
for i in shared:
    b, c = base[i]["pass_rate"], cur[i]["pass_rate"]
    if c < b:
        worse.append(i)
        if b == 1.0 and c == 0.0:
            broken.append(i)
    elif c > b:
        better.append(i)

print(f"Got worse ({len(worse)}):")
for i in worse:
    print(f"  Case {i}: {base[i]['pass_rate']:.0%} -> {cur[i]['pass_rate']:.0%}  (main problem now: {main_reason(cur[i])})")
if not worse:
    print("  none")

print(f"Got better ({len(better)}):")
for i in better:
    print(f"  Case {i}: {base[i]['pass_rate']:.0%} -> {cur[i]['pass_rate']:.0%}")
if not better:
    print("  none")

# 4. Search changes (deterministic, so any change is a real signal)
search_lost = [i for i in shared if base[i].get("retrieval_ok") is True and cur[i].get("retrieval_ok") is False]
search_gained = [i for i in shared if base[i].get("retrieval_ok") is False and cur[i].get("retrieval_ok") is True]
print(f"Search stopped finding the passage: {search_lost or 'none'}")
print(f"Search now finds the passage:       {search_gained or 'none'}")

# 5. Verdict
problems = []
if drop > TOLERANCE:
    problems.append(f"average pass rate fell by {drop * 100:.1f} points (allowed: {TOLERANCE * 100:.0f})")
if broken:
    problems.append(f"cases that passed every baseline run now fail every run: {broken}")
if search_lost:
    problems.append(f"search stopped finding the right passage in cases {search_lost}")

print()
if problems:
    print("VERDICT: REGRESSION DETECTED")
    for problem in problems:
        print(" -", problem)
    sys.exit(1)
print("VERDICT: OK - no regression against the baseline")