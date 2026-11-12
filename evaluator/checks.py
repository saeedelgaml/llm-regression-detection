"""Pure checking functions used by run_eval.py and compare.py.

"Pure" means: no chatbot, no files, no network. Each function only looks at the
values it is given and returns a result, so tests/test_checks.py can test them in
milliseconds.
"""

TOLERANCE = 0.05  # allowed drop in the average pass rate (5 points)


# ---- Grading one answer ----

def normalize(text):
    """Lower case, straight quotes, single spaces. Used to match retrieval keys inside PDF text."""
    text = text.lower()
    for fancy, plain in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"')):
        text = text.replace(fancy, plain)
    return " ".join(text.split())


def key_found(key, answer):
    """True if an answer key appears in the answer (case-insensitive).
    A list means "any one of these is fine", e.g. ["IT Services", "Information Technology"]."""
    answer = answer.lower()
    if isinstance(key, list):
        return any(option.lower() in answer for option in key)
    return key.lower() in answer


def keys_ok(answer_keys, answer):
    return all(key_found(key, answer) for key in answer_keys)


def retrieval_check(retrieval_keys, passages):
    """Did the search return every retrieval key? Returns (ok, rank).
    rank = the worst position (1 = top passage) at which a key was found, or None if one is missing."""
    texts = [normalize(p) for p in passages]
    ranks = []
    for key in retrieval_keys:
        found_at = [i + 1 for i, t in enumerate(texts) if normalize(key) in t]
        if found_at:
            ranks.append(min(found_at))
    ok = len(ranks) == len(retrieval_keys)
    return ok, (max(ranks) if ok else None)


def diagnose(route_ok, keys_ok, retrieval_ok):
    """One label per run, checked in pipeline order: route -> search -> answer.

    Each argument is True, False or None ("not checked"). None happens when the
    adapter does not report a route (route_ok), in CI mode where no answer is
    written (keys_ok), and for cases without a search (retrieval_ok)."""
    if route_ok is False:
        return "wrong route"
    if keys_ok is None:  # CI mode: nothing to grade but the route and the search
        return "search missed" if retrieval_ok is False else "pass"
    if keys_ok:
        return "pass"
    if retrieval_ok is False:
        return "search missed"
    return "answer wrong"


def main_reason(case):
    """The most common failure label of a case ("unknown" if it never failed)."""
    bad = [d for d in case.get("diagnoses", []) if d != "pass"]
    return max(set(bad), key=bad.count) if bad else "unknown"


# ---- Choosing cases ----

def select_cases(cases, ci=False, limit=None):
    """Returns (cases to run, ids skipped). In CI mode cases marked "local_only" are skipped
    (they need a file that is not available on GitHub's servers)."""
    skipped = [c["id"] for c in cases if ci and c.get("local_only")]
    kept = [c for c in cases if c["id"] not in skipped]
    return kept[:limit], skipped


# ---- Comparing two runs ----

def _average(by_id, ids):
    return sum(by_id[i]["pass_rate"] for i in ids) / len(ids) if ids else 0.0


def compare_runs(base_data, cur_data, tolerance=TOLERANCE):
    """Compare a run with the baseline. Returns a dict; "regression" is True when any rule fires:
    1. the average pass rate drops by more than `tolerance`,
    2. a case that passed every baseline run now fails every run,
    3. search stops finding a passage it used to find."""
    base = {c["id"]: c for c in base_data["cases"]}
    cur = {c["id"]: c for c in cur_data["cases"]}
    shared = sorted(set(base) & set(cur))
    base_avg, cur_avg = _average(base, shared), _average(cur, shared)
    drop = base_avg - cur_avg

    worse, better, broken = [], [], []
    for i in shared:
        b, c = base[i]["pass_rate"], cur[i]["pass_rate"]
        if c < b:
            worse.append({"id": i, "before": b, "after": c, "reason": main_reason(cur[i])})
            if b == 1.0 and c == 0.0:
                broken.append(i)
        elif c > b:
            better.append({"id": i, "before": b, "after": c})

    search_lost = [i for i in shared if base[i].get("retrieval_ok") is True and cur[i].get("retrieval_ok") is False]
    search_gained = [i for i in shared if base[i].get("retrieval_ok") is False and cur[i].get("retrieval_ok") is True]

    problems = []
    if drop > tolerance:
        problems.append(f"average pass rate fell by {drop * 100:.1f} points (allowed: {tolerance * 100:.0f})")
    if broken:
        problems.append(f"cases that passed every baseline run now fail every run: {broken}")
    if search_lost:
        problems.append(f"search stopped finding the right passage in cases {search_lost}")

    return {
        "shared": shared,
        "missing": sorted(set(base) - set(cur)),
        "base_avg": base_avg,
        "cur_avg": cur_avg,
        "drop": drop,
        "tolerance": tolerance,
        "worse": worse,
        "better": better,
        "broken": broken,
        "search_lost": search_lost,
        "search_gained": search_gained,
        "problems": problems,
        "regression": bool(problems),
    }
