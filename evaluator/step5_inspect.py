import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CHATBOT_DIR = Path(r"C:\Users\Original Nassar\Documents\egypt-data-jobs")
sys.path.insert(0, str(CHATBOT_DIR))

from rag import retrieve

with open("golden_set/test_cases.json", encoding="utf-8") as f:
    cases = json.load(f)

for case_id in sys.argv[1:]:  # every number typed after the script name
    case = next(c for c in cases if c["id"] == int(case_id))

    # flatten the answer keys: ["a", ["b", "c"]] becomes ["a", "b", "c"]
    flat_keys = []
    for key in case["answer_keys"]:
        flat_keys.extend(key if isinstance(key, list) else [key])

    print("=" * 60)
    print(f"Case {case['id']}: {case['question']}")
    print("Expected:", case["source"], "p.", case["page"])
    print("Retrieval key:", case["retrieval_keys"])
    print("Answer keys:", flat_keys)

    for i, hit in enumerate(retrieve.search(case["question"]), start=1):
        text = " ".join(hit["text"].split()).lower()
        found = [k for k in flat_keys if k.lower() in text]
        print(f"Hit {i}: {hit['source']} p.{hit['page']} | answer keys in this hit: {found}")
        if found:
            pos = text.find(found[0].lower())
            print("    ...", text[max(0, pos - 80): pos + 80], "...")