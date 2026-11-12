"""Compare a run with the baseline and give a verdict (exit code 1 = regression).

    python evaluator/compare.py                         # newest run of the baseline's adapter vs baseline.json
    python evaluator/compare.py results/run_X.json      # a chosen run vs baseline.json
    python evaluator/compare.py results/run_X.json other_baseline.json

Exit codes: 0 = OK, 1 = REGRESSION, 2 = cannot compare (no run, or a different adapter).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluator.checks import TOLERANCE, compare_runs


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def same_kind(run, baseline):
    """A run may only be compared with a baseline of the same adapter (and the same mode)."""
    return run.get("adapter") == baseline.get("adapter") and run.get("mode", "full") == baseline.get("mode", "full")


def newest_run(baseline, folder="results"):
    """The newest results/run_*.json made with the baseline's adapter and mode (other runs are ignored)."""
    files = sorted(Path(folder).glob("run_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        if same_kind(load(f), baseline):
            return f
    return None


def describe(data):
    return f"adapter={data.get('adapter', '?')}, mode={data.get('mode', 'full')}"


def print_report(result, base_path, base_data, cur_path, cur_data):
    print(f"Baseline: {base_path}  ({describe(base_data)}, {base_data['runs']} run(s) per case, {result['base_avg']:.1%})")
    print(f"Current:  {cur_path}  ({describe(cur_data)}, {cur_data['runs']} run(s) per case, {result['cur_avg']:.1%})")
    if result["missing"]:
        print(f"Note: the current run has {len(result['shared'])} of {len(base_data['cases'])} baseline cases; "
              f"comparing those only (missing: {result['missing']}).")
    print(f"Change in average pass rate: {(result['cur_avg'] - result['base_avg']) * 100:+.1f} points "
          f"(allowed drop: {result['tolerance'] * 100:.0f})")
    print()
    print(f"Got worse ({len(result['worse'])}):")
    for w in result["worse"]:
        print(f"  Case {w['id']}: {w['before']:.0%} -> {w['after']:.0%}  (main problem now: {w['reason']})")
    if not result["worse"]:
        print("  none")
    print(f"Got better ({len(result['better'])}):")
    for b in result["better"]:
        print(f"  Case {b['id']}: {b['before']:.0%} -> {b['after']:.0%}")
    if not result["better"]:
        print("  none")
    print(f"Search stopped finding the passage: {result['search_lost'] or 'none'}")
    print(f"Search now finds the passage:       {result['search_gained'] or 'none'}")
    print()
    if result["regression"]:
        print("VERDICT: REGRESSION DETECTED")
        for problem in result["problems"]:
            print(" -", problem)
    else:
        print("VERDICT: OK - no regression against the baseline")


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:] if argv is None else argv
    base_path = Path(argv[1]) if len(argv) > 1 else ROOT / "baseline.json"
    base_data = load(base_path)

    if argv:
        cur_path = Path(argv[0])
    else:
        cur_path = newest_run(base_data)
        if cur_path is None:
            print(f"No run in results/ for {describe(base_data)}. Run evaluator/run_eval.py first.")
            return 2
    cur_data = load(cur_path)

    if not same_kind(cur_data, base_data):
        print(f"Cannot compare: the run is {describe(cur_data)} but the baseline is {describe(base_data)}.")
        return 2

    result = compare_runs(base_data, cur_data, TOLERANCE)
    print_report(result, base_path, base_data, cur_path, cur_data)
    return 1 if result["regression"] else 0


if __name__ == "__main__":
    sys.exit(main())
