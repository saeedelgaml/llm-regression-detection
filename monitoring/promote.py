"""Production monitoring, part 2: turn approved candidates into new golden cases.

    python monitoring/promote.py --dry-run      # show what would be added, change nothing
    python monitoring/promote.py                # add them to golden_set/test_cases.json

A candidate in monitoring/candidates.json is promoted when "approve" is true and it is complete:
    expected_route   "rag", "database" or "refuse"
    rag cases also need answer_keys, retrieval_keys and source (the same rules as the hand-written cases)
Incomplete approved candidates are listed with what is missing and stay in candidates.json.

New cases are appended at the end of the golden set with the next free id; the rest of the
file is not reformatted. The baselines do not know the new cases yet, so after promoting:
re-run the full evaluation and save it as baseline.json (and baseline_ci.json from a CI-mode run).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluator.checks import normalize

CANDIDATES = ROOT / "monitoring" / "candidates.json"
GOLDEN = ROOT / "golden_set" / "test_cases.json"

ROUTES = {"rag", "database", "refuse"}
CASE_FIELDS = ("question", "expected_route", "answer_keys", "retrieval_keys", "source", "page", "type")


def problems_with(c):
    """What is missing before a candidate can become a golden case (empty list = ready)."""
    out = []
    if c.get("expected_route") not in ROUTES:
        out.append(f"expected_route must be one of {sorted(ROUTES)}")
    if c.get("expected_route") == "rag":
        for field in ("answer_keys", "retrieval_keys", "source"):
            if not c.get(field):
                out.append(f"a rag case needs {field}")
    return out


def to_case(c, new_id):
    return {"id": new_id, **{field: c.get(field) for field in CASE_FIELDS}}


def append_cases(golden_text, new_cases):
    """Insert the cases before the final ']' so the existing (hand-formatted) cases stay as they are."""
    nl = "\r\n" if "\r\n" in golden_text else "\n"
    body = golden_text.rstrip()
    assert body.endswith("]"), "golden set must be a JSON list"
    head = body[:-1].rstrip()
    blocks = []
    for case in new_cases:
        block = json.dumps(case, ensure_ascii=False, indent=2)
        blocks.append("\n".join("  " + line for line in block.splitlines()))
    joined = ("," + nl).join(b.replace("\n", nl) for b in blocks)
    separator = "," + nl if head.endswith("}") else nl
    return head + separator + joined + nl + "]" + (nl if golden_text.endswith(("\n", "\r\n")) else "")


def promote(candidates, golden_cases):
    """Returns (new golden cases, remaining candidates, not-ready messages)."""
    next_id = max((c["id"] for c in golden_cases), default=0) + 1
    known = {normalize(c["question"]) for c in golden_cases}
    added, remaining, not_ready = [], [], []
    for c in candidates:
        if not c.get("approve"):
            remaining.append(c)
            continue
        if normalize(c["question"]) in known:
            not_ready.append(f"already in the golden set: {c['question']}")
            continue  # dropped from candidates: nothing left to do
        missing = problems_with(c)
        if missing:
            not_ready.append(f"{c['question']}: " + "; ".join(missing))
            remaining.append(c)
            continue
        added.append(to_case(c, next_id))
        known.add(normalize(c["question"]))
        next_id += 1
    return added, remaining, not_ready


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Turn approved candidates into golden cases.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--candidates", default=str(CANDIDATES))
    p.add_argument("--golden", default=str(GOLDEN))
    args = p.parse_args(argv)

    cand_path, golden_path = Path(args.candidates), Path(args.golden)
    if not cand_path.exists():
        print(f"No {cand_path}. Run python monitoring/review_log.py first.")
        return 1
    candidates = json.loads(cand_path.read_text(encoding="utf-8"))
    golden_text = golden_path.read_bytes().decode("utf-8")  # keeps the file's CRLF line endings
    added, remaining, not_ready = promote(candidates, json.loads(golden_text))

    for case in added:
        print(f"{'Would add' if args.dry_run else 'Added'} case {case['id']} ({case['expected_route']}): {case['question']}")
    for message in not_ready:
        print("Not promoted:", message)
    if not added:
        print("Nothing to promote (set \"approve\": true on complete candidates).")
        return 0
    if args.dry_run:
        return 0
    golden_path.write_bytes(append_cases(golden_text, added).encode("utf-8"))
    cand_path.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"{len(added)} case(s) added to {golden_path}.")
    print("The baselines do not contain them yet: re-run the full evaluation and save it as baseline.json,")
    print("and a CI-mode run as baseline_ci.json, when you are happy with the results.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
