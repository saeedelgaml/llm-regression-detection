import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CHATBOT_DIR = Path(r"C:\Users\Original Nassar\Documents\egypt-data-jobs")
sys.path.insert(0, str(CHATBOT_DIR))

from rag import retrieve

with open("golden_set/test_cases.json", encoding="utf-8") as f:
    cases = json.load(f)

case = cases[25]  # case 26, the known retrieval failure
hits = retrieve.search(case["question"])

print("Question:", case["question"])
print("Expected to find:", case["retrieval_keys"])
print("Number of hits:", len(hits))
if not hits:
    sys.exit("No hits returned.")

print("Keys of the first hit:", list(hits[0].keys()))
print()
for i, hit in enumerate(hits[:3]):
    print(f"--- hit {i + 1} ---")
    for key, value in hit.items():
        print(key, ":", str(value)[:200])