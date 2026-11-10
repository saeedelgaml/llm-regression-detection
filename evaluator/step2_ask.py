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

# 4. Ask one question
case = cases[25]
result = answer_question(con, case["question"], chooser, None, fallback, rag)

# 5. Show what came back
print("Question:", case["question"])
print("Route:", result["function"])
print("Answer:", result["text"])

# 6. Grade it
route_ok = result["function"] == case["expected_route"]

answer = result["text"].lower()
keys_ok = True
for key in case["answer_keys"]:
    if key.lower() not in answer:
        keys_ok = False

print("Route correct:", route_ok)
print("Answer keys found:", keys_ok)
if route_ok and keys_ok:
    print("RESULT: PASS")
else:
    print("RESULT: FAIL")