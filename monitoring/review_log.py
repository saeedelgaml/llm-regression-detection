"""Production monitoring, part 1: find real chatbot failures in the chatbot's own log.

    python monitoring/review_log.py                 # read the chatbot's data/chat.log
    python monitoring/review_log.py --days 7        # only the last 7 days
    python monitoring/review_log.py --all           # also list answered questions (a wrong answer still logs ok)
    python monitoring/review_log.py --log path/to/chat.log

The chatbot (chatbot/chat.py) already writes one JSON line per real question to data/chat.log:
{"time", "question", "function", "params", "ok"}. Nothing in the chatbot is changed for this.

What counts as a failure:
    refused       the chatbot could not answer (ok is false): a correct refusal, or a gap to fix
    sql fallback  the local model wrote its own SQL (function "ai_sql"): the riskiest route, check it

Failures that are not in the golden set yet are added to monitoring/candidates.json (your edits
there are kept on the next run). Fill in a candidate and set "approve": true, then run
monitoring/promote.py to turn it into a golden case. candidates.json holds real users' questions,
so it is git-ignored.
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluator.checks import normalize

CHATBOT_DIR = Path(os.environ.get("EGYPT_CHATBOT_DIR", r"C:\Users\Original Nassar\Documents\egypt-data-jobs"))
DEFAULT_LOG = CHATBOT_DIR / "data" / "chat.log"
CANDIDATES = ROOT / "monitoring" / "candidates.json"
GOLDEN = ROOT / "golden_set" / "test_cases.json"


def route_of(function):
    """The chatbot's function name -> the golden set's route name (same as adapters/egypt_data_jobs.py)."""
    if function is None:
        return "refuse"
    if function == "rag":
        return "rag"
    if function == "ai_sql":
        return "sql"
    return "database"


def label_of(entry):
    if not entry.get("ok"):
        return "refused"
    if entry.get("function") == "ai_sql":
        return "sql fallback"
    return "answered"


def read_log(path, since=None):
    """The log lines as dicts; broken lines are skipped and counted."""
    entries, broken = [], 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            entry["time"] = datetime.fromisoformat(entry["time"])
        except (ValueError, KeyError, TypeError):
            broken += 1
            continue
        if since is None or entry["time"] >= since:
            entries.append(entry)
    return entries, broken


def group(entries, include_answered=False):
    """One record per distinct question (normalized), newest route first."""
    groups = {}
    for e in sorted(entries, key=lambda e: e["time"]):
        label = label_of(e)
        if label == "answered" and not include_answered:
            continue
        key = normalize(e["question"])
        g = groups.setdefault(key, {"question": e["question"], "times": 0, "first_seen": e["time"]})
        g.update(times=g["times"] + 1, last_seen=e["time"], label=label, seen_route=route_of(e.get("function")))
    return groups


def new_candidate(g):
    return {
        "question": g["question"],
        "label": g["label"],
        "seen_route": g["seen_route"],
        "times": g["times"],
        "first_seen": g["first_seen"].isoformat(timespec="seconds"),
        "last_seen": g["last_seen"].isoformat(timespec="seconds"),
        # ---- fill these in, then set approve to true and run monitoring/promote.py ----
        "approve": False,
        "expected_route": None,
        "answer_keys": [],
        "retrieval_keys": [],
        "source": None,
        "page": None,
        "type": "from production",
    }


def merge(existing, groups, golden_questions):
    """Add new failures, refresh counts of known ones, keep everything the user filled in."""
    by_key = {normalize(c["question"]): c for c in existing}
    added = 0
    for key, g in groups.items():
        if key in golden_questions:
            continue
        if key in by_key:
            c = by_key[key]
            c.update(times=g["times"], label=g["label"], seen_route=g["seen_route"],
                     last_seen=g["last_seen"].isoformat(timespec="seconds"))
        else:
            by_key[key] = new_candidate(g)
            added += 1
    return list(by_key.values()), added


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Find real chatbot failures in chat.log.")
    p.add_argument("--log", default=str(DEFAULT_LOG))
    p.add_argument("--days", type=int, default=None, help="only the last N days")
    p.add_argument("--all", action="store_true", help="also collect answered questions")
    p.add_argument("--candidates", default=str(CANDIDATES))
    p.add_argument("--golden", default=str(GOLDEN))
    args = p.parse_args(argv)

    if not Path(args.log).exists():
        print(f"No log at {args.log}. The chatbot writes it when you use python -m chatbot.chat.")
        return 1
    since = datetime.now() - timedelta(days=args.days) if args.days else None
    entries, broken = read_log(args.log, since)
    labels = Counter(label_of(e) for e in entries)
    total = len(entries)

    print(f"Log: {args.log}" + (f" (last {args.days} days)" if args.days else ""))
    print(f"Questions: {total}" + (f"  ({broken} unreadable line(s) skipped)" if broken else ""))
    for label in ("answered", "refused", "sql fallback"):
        share = f"{labels[label] / total:.0%}" if total else "-"
        print(f"  {label:<13} {labels[label]:>4}  ({share})")

    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    golden_questions = {normalize(c["question"]) for c in golden}
    groups = group(entries, include_answered=args.all)
    path = Path(args.candidates)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    candidates, added = merge(existing, groups, golden_questions)

    already = sum(1 for k in groups if k in golden_questions)
    print()
    print(f"Distinct questions to review: {len(groups)} ({already} already in the golden set)")
    for c in sorted(candidates, key=lambda c: -c["times"]):
        mark = "approved" if c["approve"] else "to review"
        print(f"  [{c['label']}] x{c['times']}  {c['question']}  (seen route: {c['seen_route']}, {mark})")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"{added} new candidate(s) saved to {path}")
    print("Next: open it, fill in expected_route and the keys for the good ones, set \"approve\": true,")
    print("then run: python monitoring/promote.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
