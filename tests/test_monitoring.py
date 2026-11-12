"""Tests for production monitoring: reading chat.log and promoting candidates to golden cases.
Everything works on temporary copies; the real golden set and log are never touched."""
import json
from pathlib import Path

from monitoring import promote, review_log

ROOT = Path(__file__).resolve().parent.parent

LOG_LINES = [
    {"time": "2026-11-01T10:00:00", "question": "Who won the 2022 World Cup?", "function": None, "params": {}, "ok": False},
    {"time": "2026-11-02T10:00:00", "question": "What is the best laptop?", "function": None, "params": {}, "ok": False},
    {"time": "2026-11-03T10:00:00", "question": "what is the best  laptop?", "function": None, "params": {}, "ok": False},
    {"time": "2026-11-04T10:00:00", "question": "Which university is best?", "function": "ai_sql", "params": {}, "ok": True},
    {"time": "2026-11-05T10:00:00", "question": "Salary of a data analyst?", "function": "salary_for_role",
     "params": {}, "ok": True},
]


def write_log(tmp_path, extra=""):
    path = tmp_path / "chat.log"
    path.write_text("\n".join(json.dumps(line) for line in LOG_LINES) + "\n" + extra, encoding="utf-8")
    return path


def write_golden(tmp_path):
    """A small golden set with CRLF line endings and a hand-formatted nested list, like the real one."""
    text = ('[\r\n  {\r\n    "id": 7,\r\n    "question": "Who won the 2022 World Cup?",\r\n'
            '    "expected_route": "refuse",\r\n    "answer_keys": [\r\n      ["a","b"]\r\n    ]\r\n  }\r\n]\r\n')
    path = tmp_path / "golden.json"
    path.write_bytes(text.encode("utf-8"))
    return path


def run_review(tmp_path, *extra):
    cand = tmp_path / "candidates.json"
    code = review_log.main(["--log", str(write_log(tmp_path, "not json\n")), "--candidates", str(cand),
                            "--golden", str(write_golden(tmp_path)), *extra])
    return code, cand


# ---- review_log ----

def test_labels():
    assert review_log.label_of({"ok": False, "function": None}) == "refused"
    assert review_log.label_of({"ok": True, "function": "ai_sql"}) == "sql fallback"
    assert review_log.label_of({"ok": True, "function": "rag"}) == "answered"


def test_review_collects_failures_not_in_golden_set(tmp_path, capsys):
    code, cand = run_review(tmp_path)
    assert code == 0
    candidates = json.loads(cand.read_text(encoding="utf-8"))
    by_q = {c["question"]: c for c in candidates}
    assert set(by_q) == {"What is the best laptop?", "Which university is best?"}  # World Cup is already golden
    assert by_q["What is the best laptop?"]["times"] == 2  # same question, different spelling (first kept)
    assert by_q["Which university is best?"]["label"] == "sql fallback"
    assert by_q["Which university is best?"]["seen_route"] == "sql"
    assert all(c["approve"] is False and c["expected_route"] is None for c in candidates)
    out = capsys.readouterr().out
    assert "Questions: 5  (1 unreadable line(s) skipped)" in out


def test_review_all_includes_answered_questions(tmp_path):
    _, cand = run_review(tmp_path, "--all")
    assert "Salary of a data analyst?" in {c["question"] for c in json.loads(cand.read_text(encoding="utf-8"))}


def test_review_keeps_what_the_user_filled_in(tmp_path):
    _, cand = run_review(tmp_path)
    candidates = json.loads(cand.read_text(encoding="utf-8"))
    candidates[0].update(approve=True, expected_route="refuse")
    cand.write_text(json.dumps(candidates), encoding="utf-8")
    run_review(tmp_path)  # second run
    again = {c["question"]: c for c in json.loads(cand.read_text(encoding="utf-8"))}
    assert again[candidates[0]["question"]]["approve"] is True
    assert again[candidates[0]["question"]]["expected_route"] == "refuse"
    assert len(again) == 2  # no duplicates


def test_review_days_filter(tmp_path):
    entries, _ = review_log.read_log(write_log(tmp_path), since=review_log.datetime(2026, 11, 4))
    assert len(entries) == 2


# ---- promote ----

def candidate(question, **fields):
    return {"question": question, "approve": True, "expected_route": None, "answer_keys": [],
            "retrieval_keys": [], "source": None, "page": None, "type": "from production", **fields}


def test_problems_with_incomplete_candidates():
    assert problems_with_route(None)
    assert promote.problems_with(candidate("q", expected_route="refuse")) == []
    rag = promote.problems_with(candidate("q", expected_route="rag"))
    assert len(rag) == 3  # needs answer_keys, retrieval_keys, source


def problems_with_route(route):
    return promote.problems_with(candidate("q", expected_route=route))


def test_promote_appends_ready_cases_and_keeps_the_rest(tmp_path):
    golden = write_golden(tmp_path)
    original = golden.read_bytes().decode("utf-8")
    cand = tmp_path / "candidates.json"
    cand.write_text(json.dumps([
        candidate("Give me a laptop recommendation", expected_route="refuse"),
        candidate("What share of postings ask for a degree?", expected_route="rag"),  # incomplete
        {**candidate("Not approved yet"), "approve": False},
        candidate("who won the 2022 world cup?", expected_route="refuse"),  # already golden
    ]), encoding="utf-8")

    assert promote.main(["--candidates", str(cand), "--golden", str(golden)]) == 0

    text = golden.read_bytes().decode("utf-8")
    cases = json.loads(text)
    assert [c["id"] for c in cases] == [7, 8]
    assert cases[1]["question"] == "Give me a laptop recommendation"
    assert cases[1]["expected_route"] == "refuse"
    assert text.startswith(original.rstrip()[:-1].rstrip())  # old cases untouched (nested list stays on one line)
    assert '["a","b"]' in text
    assert "\n" not in text.replace("\r\n", "")  # still CRLF everywhere
    left = [c["question"] for c in json.loads(cand.read_text(encoding="utf-8"))]
    assert left == ["What share of postings ask for a degree?", "Not approved yet"]


def test_promote_dry_run_changes_nothing(tmp_path):
    golden = write_golden(tmp_path)
    before = golden.read_bytes()
    cand = tmp_path / "candidates.json"
    cand.write_text(json.dumps([candidate("A new question", expected_route="refuse")]), encoding="utf-8")
    assert promote.main(["--dry-run", "--candidates", str(cand), "--golden", str(golden)]) == 0
    assert golden.read_bytes() == before


def test_append_to_the_real_golden_set_keeps_it_valid():
    text = (ROOT / "golden_set" / "test_cases.json").read_bytes().decode("utf-8")
    new = promote.to_case(candidate("A new question", expected_route="refuse"), 33)
    result = promote.append_cases(text, [new])
    cases = json.loads(result)
    assert len(cases) == 33 and cases[-1]["id"] == 33
    assert result.startswith(text.rstrip()[:-1].rstrip())
