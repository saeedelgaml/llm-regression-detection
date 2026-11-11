import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CHATBOT_DIR = Path(r"C:\Users\Original Nassar\Documents\egypt-data-jobs")
sys.path.insert(0, str(CHATBOT_DIR))

from rag import retrieve

with open("golden_set/test_cases.json", encoding="utf-8") as f:
    cases = json.load(f)


def normalize(text):
    # lowercase, straight quotes, single spaces, so PDF line breaks don't break matching
    text = text.lower()
    for fancy, plain in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"')):
        text = text.replace(fancy, plain)
    return " ".join(text.split())


def check_retrieval(case):
    hits = retrieve.search(case["question"])
    texts = [normalize(hit["text"]) for hit in hits]

    ranks = []  # for each key: the position of the first hit that contains it
    for key in case["retrieval_keys"]:
        found_at = [i + 1 for i, t in enumerate(texts) if normalize(key) in t]
        if found_at:
            ranks.append(min(found_at))

    ok = len(ranks) == len(case["retrieval_keys"])
    return {
        "id": case["id"],
        "retrieval_ok": ok,
        "rank": max(ranks) if ok else None,
        "source_found": case["source"] in [hit["source"] for hit in hits],
        "best_score": hits[0]["best_score"] if hits else None,
        "top_hits": [f"{hit['source']} p.{hit['page']}" for hit in hits],
    }


print("Search threshold:", retrieve.THRESHOLD)
print()

records = []
for case in cases:
    if case["expected_route"] != "rag":
        continue  # only report questions have a passage to find
    r = check_retrieval(case)
    records.append(r)
    score = f"{r['best_score']:.2f}" if r["best_score"] is not None else "none"
    status = "OK  " if r["retrieval_ok"] else "MISS"
    print(f"Case {r['id']:>2}: {status} rank={r['rank']} source_found={r['source_found']} "
          f"best_score={score} top={r['top_hits'][:2]}")

ok_count = sum(r["retrieval_ok"] for r in records)
misses = [r["id"] for r in records if not r["retrieval_ok"]]
print()
print(f"Retrieval found the right passage in {ok_count} of {len(records)} cases")
print("Misses:", misses)

Path("results").mkdir(exist_ok=True)
out = Path("results") / f"retrieval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)
print("Saved:", out)