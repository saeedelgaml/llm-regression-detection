import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CHATBOT_DIR = Path(r"C:\Users\Original Nassar\Documents\egypt-data-jobs")
sys.path.insert(0, str(CHATBOT_DIR))

import duckdb
from chatbot.ai import answer_question
from chatbot.router import RuleRouter
from chatbot.rag_route import RagRoute
from chatbot.local_ai import LocalAI
from rag import retrieve

# ---- Settings ----
RUNS = 3      # how many times each question is asked
LIMIT = None  # None = all cases; use 3 for a quick test

# ---- Load the exam and switch the chatbot on ----
with open("golden_set/test_cases.json", encoding="utf-8") as f:
    cases = json.load(f)

con = duckdb.connect(str(CHATBOT_DIR / "data" / "jobs.duckdb"), read_only=True)
chooser = RuleRouter(con)
rag = RagRoute()
fallback = LocalAI(con)


# ---- Helpers ----
def normalize(text):
    text = text.lower()
    for fancy, plain in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"')):
        text = text.replace(fancy, plain)
    return " ".join(text.split())


def route_of(result):
    fn = result["function"]
    if fn is None:
        return "refuse"
    if fn == "rag":
        return "rag"
    if fn == "ai_sql":
        return "sql"
    return "database"


def key_found(key, answer):
    if isinstance(key, list):
        return any(option.lower() in answer for option in key)
    return key.lower() in answer


def check_retrieval(case):
    """Runs only the search. Returns (ok, rank, best_score); all None for non-report cases."""
    if case["expected_route"] != "rag":
        return None, None, None
    hits = retrieve.search(case["question"])
    texts = [normalize(hit["text"]) for hit in hits]
    ranks = []
    for key in case["retrieval_keys"]:
        found_at = [i + 1 for i, t in enumerate(texts) if normalize(key) in t]
        if found_at:
            ranks.append(min(found_at))
    ok = len(ranks) == len(case["retrieval_keys"])
    best_score = hits[0]["best_score"] if hits else None
    return ok, (max(ranks) if ok else None), best_score


def grade(case):
    result = answer_question(con, case["question"], chooser, None, fallback, rag)
    route = route_of(result)
    answer = result["text"].lower()
    route_ok = route == case["expected_route"]
    keys_ok = all(key_found(key, answer) for key in case["answer_keys"])
    return route_ok, keys_ok, route, result["text"]


def diagnose(route_ok, keys_ok, retrieval_ok):
    if route_ok and keys_ok:
        return "pass"
    if not route_ok:
        return "wrong route"
    if retrieval_ok is False:
        return "search missed"
    return "answer wrong"


# ---- Run the exam ----
records = []
for case in cases[:LIMIT]:
    retrieval_ok, rank, best_score = check_retrieval(case)  # deterministic: once is enough

    diagnoses = []
    last_route, last_text = None, ""
    for run in range(RUNS):
        try:
            route_ok, keys_ok, last_route, last_text = grade(case)
            diagnoses.append(diagnose(route_ok, keys_ok, retrieval_ok))
        except Exception as e:
            diagnoses.append("crash")
            last_text = f"CRASH: {e}"
            print(f"  case {case['id']} crashed: {e}", flush=True)

    passes = diagnoses.count("pass")
    records.append({
        "id": case["id"],
        "expected_route": case["expected_route"],
        "runs": RUNS,
        "passes": passes,
        "pass_rate": passes / RUNS,
        "diagnoses": diagnoses,
        "retrieval_ok": retrieval_ok,
        "retrieval_rank": rank,
        "best_score": best_score,
        "last_route": last_route,
        "last_answer": last_text,
    })
    search = "n/a" if retrieval_ok is None else ("OK" if retrieval_ok else "MISS")
    print(f"Case {case['id']:>2}: {passes}/{RUNS} passed | {', '.join(sorted(set(diagnoses)))} | search: {search}", flush=True)

# ---- Summary ----
avg = sum(r["pass_rate"] for r in records) / len(records)
report_cases = [r for r in records if r["retrieval_ok"] is not None]
search_ok = sum(r["retrieval_ok"] for r in report_cases)
outcomes = Counter(d for r in records for d in r["diagnoses"])

print()
print(f"Average pass rate: {avg:.0%} over {len(records)} cases x {RUNS} runs")
print(f"Search found the right passage in {search_ok} of {len(report_cases)} report cases")
print("Outcomes across all runs:", dict(outcomes))
print("Cases that did not pass every run:", [r["id"] for r in records if r["passes"] < r["runs"]])

# ---- Save ----
Path("results").mkdir(exist_ok=True)
out = Path("results") / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump({"runs": RUNS, "average_pass_rate": avg, "search_ok": search_ok,
               "report_cases": len(report_cases), "cases": records},
              f, ensure_ascii=False, indent=2)
print("Saved:", out)