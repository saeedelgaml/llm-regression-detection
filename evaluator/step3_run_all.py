import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# 1. Tell Python where the chatbot's code lives
CHATBOT_DIR = Path(r"C:\Users\Original Nassar\Documents\egypt-data-jobs")
sys.path.insert(0, str(CHATBOT_DIR))

import duckdb
from chatbot.ai import answer_question
from chatbot.router import RuleRouter
from chatbot.rag_route import RagRoute
from chatbot.local_ai import LocalAI

# 2. Settings
RUNS = 1      # how many times each question is asked (use 3 for the baseline)
LIMIT = None  # how many cases to run; None = all 32

# 3. Read the exam
with open("golden_set/test_cases.json", encoding="utf-8") as f:
    cases = json.load(f)

# 4. Switch the chatbot on, once
con = duckdb.connect(str(CHATBOT_DIR / "data" / "jobs.duckdb"), read_only=True)
chooser = RuleRouter(con)
rag = RagRoute()
fallback = LocalAI(con)


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


def grade(case):
    result = answer_question(con, case["question"], chooser, None, fallback, rag)
    route = route_of(result)
    answer = result["text"].lower()
    route_ok = route == case["expected_route"]
    keys_ok = all(key_found(key, answer) for key in case["answer_keys"])
    return route_ok and keys_ok, route, result["text"]


# 5. Ask every case, RUNS times each
records = []
for case in cases[:LIMIT]:
    passes = 0
    last_route = None
    last_text = ""
    for run in range(RUNS):
        try:
            ok, last_route, last_text = grade(case)
        except Exception as e:
            print(f"  case {case['id']} crashed: {e}", flush=True)
            ok = False
            last_text = f"CRASH: {e}"
        if ok:
            passes += 1
    records.append({
        "id": case["id"],
        "expected_route": case["expected_route"],
        "passes": passes,
        "runs": RUNS,
        "pass_rate": passes / RUNS,
        "last_route": last_route,
        "last_answer": last_text,
    })
    print(f"Case {case['id']}: {passes}/{RUNS} passed (route: {last_route})", flush=True)

# 6. Summary
avg = sum(r["pass_rate"] for r in records) / len(records)
failed = [r["id"] for r in records if r["passes"] < r["runs"]]
print()
print(f"Average pass rate: {avg:.0%} over {len(records)} cases")
print("Cases that did not pass every run:", failed)

# 7. Save the results
Path("results").mkdir(exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out = Path("results") / f"run_{stamp}.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump({"runs": RUNS, "average_pass_rate": avg, "cases": records},
              f, ensure_ascii=False, indent=2)
print("Saved:", out)