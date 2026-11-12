"""Tests for CI mode (route + search only) and for the PDF downloader. No chatbot, no network."""
import hashlib
import json
from pathlib import Path

import pytest

from ci import fetch_docs
from evaluator import run_eval

ROOT = Path(__file__).resolve().parent.parent


class RouteOnlyBot:
    """Pretend chatbot for CI mode. ask() must never be called in CI mode."""

    ROUTES = {"report q": "rag", "db q": "database", "bad q": "refuse"}

    @staticmethod
    def ask(question):
        raise AssertionError("CI mode must not ask for an answer")

    @staticmethod
    def route(question):
        return RouteOnlyBot.ROUTES[question]

    @staticmethod
    def search(question):
        return {"passages": ["the key 15.7 per cent is here"] if question == "report q" else ["nothing"],
                "best_score": 0.5}


CASES = [
    {"id": 1, "question": "report q", "expected_route": "rag", "answer_keys": ["x"], "retrieval_keys": ["15.7 per cent"]},
    {"id": 2, "question": "db q", "expected_route": "rag", "answer_keys": ["x"], "retrieval_keys": ["missing key"]},
    {"id": 3, "question": "bad q", "expected_route": "refuse", "answer_keys": [], "retrieval_keys": []},
    {"id": 4, "question": "db q", "expected_route": "database", "answer_keys": [], "retrieval_keys": [],
     "local_only": True},
]


def test_ci_mode_checks_route_and_search_only():
    card = run_eval.evaluate(RouteOnlyBot, "route_only", CASES[:3], runs=3, ci=True, skipped=[4])
    by_id = {c["id"]: c for c in card["cases"]}
    assert card["mode"] == "ci"
    assert card["runs"] == 1  # deterministic: one run is enough, whatever --runs says
    assert card["skipped"] == [4]
    assert by_id[1]["diagnoses"] == ["pass"]           # right route, search found the key
    assert by_id[2]["diagnoses"] == ["wrong route"]    # route is checked before search
    assert by_id[2]["retrieval_ok"] is False
    assert by_id[3]["diagnoses"] == ["pass"]
    assert by_id[3]["last_route"] == "refuse"


def test_ci_mode_needs_route():
    class TextOnly:
        @staticmethod
        def ask(question):
            return {"text": ""}
    with pytest.raises(SystemExit, match="route"):
        run_eval.evaluate(TextOnly, "text_only", CASES[:1], runs=1, ci=True)


def test_ci_command_line_skips_local_only_cases(tmp_path, monkeypatch, capsys):
    import sys
    import types
    fake = types.ModuleType("adapters.route_only")
    fake.ask, fake.route, fake.search = RouteOnlyBot.ask, RouteOnlyBot.route, RouteOnlyBot.search
    monkeypatch.setitem(sys.modules, "adapters.route_only", fake)
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps(CASES), encoding="utf-8")
    out = tmp_path / "run.json"
    assert run_eval.main(["--adapter", "route_only", "--cases", str(cases), "--ci", "--out", str(out)]) == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert [c["id"] for c in saved["cases"]] == [1, 2, 3]
    assert saved["skipped"] == [4]
    assert "Skipped 1 local-only case(s): [4]" in capsys.readouterr().out


# ---- the real golden set and CI baseline ----

def test_only_resume_guide_cases_are_local_only():
    cases = json.loads((ROOT / "golden_set" / "test_cases.json").read_text(encoding="utf-8"))
    local_only = {c["id"] for c in cases if c.get("local_only")}
    assert local_only == {c["id"] for c in cases if c.get("source") == "365ds-resume-guide"}
    assert local_only == {25, 26}


def test_ci_baseline_matches_the_golden_set():
    base = json.loads((ROOT / "baseline_ci.json").read_text(encoding="utf-8"))
    cases = json.loads((ROOT / "golden_set" / "test_cases.json").read_text(encoding="utf-8"))
    assert base["adapter"] == "egypt_data_jobs" and base["mode"] == "ci"
    assert {c["id"] for c in base["cases"]} == {c["id"] for c in cases if not c.get("local_only")}


def test_docs_list_has_no_resume_guide_and_valid_hashes():
    docs = json.loads((ROOT / "ci" / "docs.json").read_text(encoding="utf-8"))["docs"]
    assert {d["filename"] for d in docs} == {"wef-fojr-2025.pdf", "eces-wp241.pdf", "ilo-swts-egypt.pdf",
                                             "wb-egypt-brief4.pdf"}
    assert all(len(d["sha256"]) == 64 for d in docs)


# ---- fetch_docs: hash check, using local file:// URLs instead of the internet ----

def make_source(tmp_path, content):
    src = tmp_path / "source.pdf"
    src.write_bytes(content)
    return {"filename": "doc.pdf", "url": src.as_uri(), "sha256": hashlib.sha256(content).hexdigest()}


def test_fetch_downloads_and_checks_hash(tmp_path):
    doc = make_source(tmp_path, b"%PDF report")
    target = tmp_path / "docs"
    assert fetch_docs.fetch(target, [doc]) == []
    assert (target / "doc.pdf").read_bytes() == b"%PDF report"


def test_fetch_skips_a_file_that_is_already_correct(tmp_path, capsys):
    doc = make_source(tmp_path, b"%PDF report")
    target = tmp_path / "docs"
    fetch_docs.fetch(target, [doc])
    doc["url"] = "file:///does/not/exist.pdf"  # would fail if it downloaded again
    assert fetch_docs.fetch(target, [doc]) == []
    assert "already there" in capsys.readouterr().out


def test_fetch_reports_a_changed_file(tmp_path):
    doc = make_source(tmp_path, b"%PDF report")
    doc["sha256"] = "0" * 64
    problems = fetch_docs.fetch(tmp_path / "docs", [doc])
    assert len(problems) == 1 and "SHA-256 differs" in problems[0]


def test_fetch_reports_a_failed_download(tmp_path):
    problems = fetch_docs.fetch(tmp_path / "docs", [{"filename": "x.pdf", "url": "file:///no/such/file.pdf",
                                                     "sha256": "0" * 64}])
    assert len(problems) == 1 and "download failed" in problems[0]
