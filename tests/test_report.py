"""Tests for the evaluation report page."""
import json
from html.parser import HTMLParser

from evaluator import report
from evaluator.checks import compare_runs

CARD = {"adapter": "a", "mode": "ci", "skipped": [25, 26], "runs": 1, "search_ok": 1, "report_cases": 2, "cases": [
    {"id": 1, "expected_route": "rag", "last_route": "rag", "retrieval_ok": True, "retrieval_rank": 1,
     "pass_rate": 1.0, "diagnoses": ["pass"]},
    {"id": 2, "expected_route": "rag", "last_route": "database", "retrieval_ok": False, "retrieval_rank": None,
     "pass_rate": 0.0, "diagnoses": ["wrong route"]},
    {"id": 3, "expected_route": "refuse", "last_route": "refuse", "retrieval_ok": None, "retrieval_rank": None,
     "pass_rate": 1.0, "diagnoses": ["pass"]},
]}
QUESTIONS = {1: "How many jobs?", 2: "Salary <script>alert(1)</script>?", 3: "Who won?"}


def summary(verdict="OK"):
    return {"verdict": verdict, **compare_runs(CARD, CARD)}


class TagCounter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = 0
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        self.rows += tag == "tr"
        self.scripts += tag == "script"


def test_page_shows_every_case_and_the_numbers():
    page = report.build(CARD, summary(), QUESTIONS, built_at="2026-11-12 10:00 UTC")
    counter = TagCounter()
    counter.feed(page)
    assert counter.rows == 1 + 3  # header + one row per case
    assert "Regression gate passed" in page
    assert "66.7%" in page and "+0.0 pts" in page
    assert "1 / 2" in page
    assert "25, 26" in page  # skipped local-only cases are listed
    assert "wrong route" in page and "missed" in page and "n/a" in page
    assert "No answers are written" in page


def test_questions_are_escaped():
    page = report.build(CARD, summary(), QUESTIONS)
    counter = TagCounter()
    counter.feed(page)
    assert counter.scripts == 0
    assert "&lt;script&gt;" in page


def test_no_page_when_the_gate_did_not_pass(tmp_path):
    run, verdict, out = tmp_path / "run.json", tmp_path / "verdict.json", tmp_path / "report" / "index.html"
    run.write_text(json.dumps(CARD), encoding="utf-8")
    verdict.write_text(json.dumps(summary("REGRESSION")), encoding="utf-8")
    assert report.main([str(run), str(verdict), "--out", str(out)]) == 1
    assert not out.exists()


def test_command_line_writes_the_page(tmp_path):
    run, verdict, out = tmp_path / "run.json", tmp_path / "verdict.json", tmp_path / "report" / "index.html"
    run.write_text(json.dumps(CARD), encoding="utf-8")
    verdict.write_text(json.dumps(summary()), encoding="utf-8")
    assert report.main([str(run), str(verdict), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
