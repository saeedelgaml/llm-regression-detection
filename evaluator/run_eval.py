"""The evaluation engine: asks every golden question, grades it and saves a report card.

    python evaluator/run_eval.py --adapter egypt_data_jobs            # full run (needs Ollama)
    python evaluator/run_eval.py --adapter egypt_data_jobs --limit 3  # quick test
    python evaluator/run_eval.py --adapter fake_bot --cases tests/fake_cases.json --runs 1
    python evaluator/run_eval.py --adapter egypt_data_jobs --ci     # CI mode: route + search only

The engine knows nothing about a particular chatbot. It talks to one only through an
adapter in adapters/<name>.py:
    ask(question)    -> {"text": ..., "route": ... (optional)}            required
    search(question) -> {"passages": [...], "best_score": ...}            optional
    route(question)  -> "rag" | "database" | "refuse" (no answer written) needed for --ci

CI mode (--ci) is for GitHub's servers, where there is no language model: it checks only the
route and the search, once per case (both are deterministic), and skips cases marked
"local_only" in the golden set. Its report card has "mode": "ci" and is compared with
baseline_ci.json, never with the full baseline.
"""
import argparse
import importlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so "adapters" and "evaluator" can be imported from any folder

from evaluator.checks import diagnose, keys_ok, retrieval_check, select_cases


def check_search(adapter, case):
    """Runs only the search (deterministic: once per case is enough). Returns (ok, rank, best_score)."""
    if case["expected_route"] != "rag" or not hasattr(adapter, "search"):
        return None, None, None
    found = adapter.search(case["question"])
    ok, rank = retrieval_check(case["retrieval_keys"], found["passages"])
    return ok, rank, found.get("best_score")


def grade_once(adapter, case, retrieval_ok):
    reply = adapter.ask(case["question"])
    route = reply.get("route")
    route_ok = None if route is None else route == case["expected_route"]
    return diagnose(route_ok, keys_ok(case["answer_keys"], reply["text"]), retrieval_ok), route, reply["text"]


def grade_route_only(adapter, case, retrieval_ok):
    """CI mode: the planned route and the search, no answer (keys_ok=None = not checked)."""
    route = adapter.route(case["question"])
    return diagnose(route == case["expected_route"], None, retrieval_ok), route, ""


def evaluate_case(adapter, case, runs, ci=False):
    retrieval_ok, rank, best_score = check_search(adapter, case)
    grade = grade_route_only if ci else grade_once
    diagnoses, last_route, last_text = [], None, ""
    for _ in range(runs):
        try:
            label, last_route, last_text = grade(adapter, case, retrieval_ok)
        except Exception as e:
            label, last_text = "crash", f"CRASH: {e}"
            print(f"  case {case['id']} crashed: {e}", flush=True)
        diagnoses.append(label)
    passes = diagnoses.count("pass")
    return {
        "id": case["id"],
        "expected_route": case["expected_route"],
        "runs": runs,
        "passes": passes,
        "pass_rate": passes / runs,
        "diagnoses": diagnoses,
        "retrieval_ok": retrieval_ok,
        "retrieval_rank": rank,
        "best_score": best_score,
        "last_route": last_route,
        "last_answer": last_text,
    }


def evaluate(adapter, adapter_name, cases, runs, ci=False, skipped=()):
    """Runs all cases and returns the report card (a dict)."""
    if ci and not hasattr(adapter, "route"):
        raise SystemExit(f"CI mode needs route(question) in adapters/{adapter_name}.py")
    if ci:
        runs = 1  # route and search are deterministic: one run is enough
    records = []
    for case in cases:
        r = evaluate_case(adapter, case, runs, ci)
        records.append(r)
        search = "n/a" if r["retrieval_ok"] is None else ("OK" if r["retrieval_ok"] else "MISS")
        print(f"Case {r['id']:>2}: {r['passes']}/{runs} passed | {', '.join(sorted(set(r['diagnoses'])))} | search: {search}",
              flush=True)
    report_cases = [r for r in records if r["retrieval_ok"] is not None]
    return {
        "adapter": adapter_name,
        "mode": "ci" if ci else "full",
        "skipped": list(skipped),
        "runs": runs,
        "average_pass_rate": sum(r["pass_rate"] for r in records) / len(records) if records else 0.0,
        "search_ok": sum(r["retrieval_ok"] for r in report_cases),
        "report_cases": len(report_cases),
        "cases": records,
    }


def print_summary(card):
    records = card["cases"]
    print()
    if card.get("mode") == "ci":
        print("CI mode: checked the route and the search only (no answers were written)")
    if card.get("skipped"):
        print(f"Skipped {len(card['skipped'])} local-only case(s): {card['skipped']}")
    print(f"Average pass rate: {card['average_pass_rate']:.1%} over {len(records)} cases x {card['runs']} runs")
    print(f"Search found the right passage in {card['search_ok']} of {card['report_cases']} report cases")
    print("Outcomes across all runs:", dict(Counter(d for r in records for d in r["diagnoses"])))
    print("Cases that did not pass every run:", [r["id"] for r in records if r["passes"] < r["runs"]])


def save(card, out=None):
    if out is None:
        Path("results").mkdir(exist_ok=True)
        out = Path("results") / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved:", out)
    return out


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Run the golden set against a chatbot.")
    p.add_argument("--adapter", required=True, help="module name in adapters/, e.g. egypt_data_jobs")
    p.add_argument("--cases", default="golden_set/test_cases.json", help="golden set file")
    p.add_argument("--runs", type=int, default=3, help="how many times each question is asked")
    p.add_argument("--limit", type=int, default=None, help="only the first N cases (quick test)")
    p.add_argument("--ci", action="store_true", help="CI mode: route + search only, no language model")
    p.add_argument("--out", default=None, help="where to save the report card (default results/run_<time>.json)")
    args = p.parse_args(argv)

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases, skipped = select_cases(cases, ci=args.ci, limit=args.limit)
    adapter = importlib.import_module(f"adapters.{args.adapter}")

    card = evaluate(adapter, args.adapter, cases, args.runs, ci=args.ci, skipped=skipped)
    print_summary(card)
    save(card, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
