import json
import sys
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

# 2. Read the exam (same as step 1)
with open("golden_set/test_cases.json", encoding="utf-8") as f:
    cases = json.load(f)

# 3. Switch the chatbot on, once
con = duckdb.connect(str(CHATBOT_DIR / "data" / "jobs.duckdb"), read_only=True)
chooser = RuleRouter(con)
rag = RagRoute()
fallback = LocalAI(con)


# Translate the chatbot's route name into the test set's route name
def route_of(result):
    fn = result["function"]
    if fn is None:
        return "refuse"
    if fn == "rag":
        return "rag"
    if fn == "ai_sql":
        return "sql"
    return "database"


# A key is either a plain string, or a list of alternatives where any one is enough
def key_found(key, answer):
    if isinstance(key, list):
        return any(option.lower() in answer for option in key)
    return key.lower() in answer


# 4. Ask one question
case = cases[7]  # case 27: the database question
result = answer_question(con, case["question"], chooser, None, fallback, rag)

# 5. Show what came back
print("Question:", case["question"])
print("Route:", result["function"])
print("Answer:", result["text"])

# 6. Grade it
route_ok = route_of(result) == case["expected_route"]
answer = result["text"].lower()
keys_ok = True
for key in case["answer_keys"]:
    if not key_found(key, answer):
        keys_ok = False

print("Route correct:", route_ok)
print("Answer keys found:", keys_ok)
if route_ok and keys_ok:
    print("RESULT: PASS")
else:
    print("RESULT: FAIL")