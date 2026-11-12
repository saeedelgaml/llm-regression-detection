"""Tests for the pure grading functions and for the engine with the fake bot (no chatbot, no Ollama)."""
import json
from pathlib import Path

from adapters import fake_bot
from evaluator import run_eval
from evaluator.checks import diagnose, key_found, keys_ok, main_reason, normalize, retrieval_check, select_cases

HERE = Path(__file__).parent


# ---- normalize / key_found ----

def test_normalize_lowercases_straightens_quotes_and_squeezes_spaces():
    assert normalize("Workers’  “Skills”\n Change") == "workers' \"skills\" change"


def test_key_found_is_case_insensitive():
    assert key_found("Cairo", "the capital is cairo.")


def test_key_found_list_means_any_option():
    assert key_found(["IT Services", "Information Technology"], "Mostly information technology firms")
    assert not key_found(["IT Services", "Information Technology"], "Mostly banks")


def test_keys_ok_needs_every_key():
    assert keys_ok(["170 million", "92 million"], "170 million created, 92 million displaced")
    assert not keys_ok(["170 million", "92 million"], "170 million created")
    assert keys_ok([], "anything")  # no keys = nothing to check (database and refuse cases)


# ---- retrieval_check ----

def test_retrieval_check_finds_key_and_reports_rank():
    passages = ["nothing here", "Youth unemployment was 15.7  per cent in 2012"]
    assert retrieval_check(["15.7 per cent"], passages) == (True, 2)


def test_retrieval_check_misses_when_one_key_is_absent():
    assert retrieval_check(["15.7 per cent", "48%"], ["15.7 per cent"]) == (False, None)


def test_retrieval_check_rank_is_the_worst_key():
    assert retrieval_check(["a1", "b2"], ["a1", "x", "b2"]) == (True, 3)


# ---- diagnose (order: route -> search -> answer) ----

def test_diagnose_labels_in_pipeline_order():
    assert diagnose(True, True, True) == "pass"
    assert diagnose(False, True, True) == "wrong route"
    assert diagnose(False, False, False) == "wrong route"  # route is checked first
    assert diagnose(True, False, False) == "search missed"
    assert diagnose(True, False, True) == "answer wrong"
    assert diagnose(True, False, None) == "answer wrong"  # no search for this case


def test_diagnose_pass_even_if_search_missed_but_answer_is_right():
    assert diagnose(True, True, False) == "pass"


def test_diagnose_without_route_information():
    assert diagnose(None, True, None) == "pass"
    assert diagnose(None, False, None) == "answer wrong"


def test_diagnose_ci_mode_has_no_answer_to_grade():
    assert diagnose(True, None, True) == "pass"
    assert diagnose(True, None, None) == "pass"
    assert diagnose(True, None, False) == "search missed"
    assert diagnose(False, None, True) == "wrong route"


def test_main_reason_is_most_common_failure():
    assert main_reason({"diagnoses": ["pass", "answer wrong", "answer wrong", "search missed"]}) == "answer wrong"
    assert main_reason({"diagnoses": ["pass"]}) == "unknown"


# ---- select_cases ----

CASES = [{"id": 1}, {"id": 2, "local_only": True}, {"id": 3}]


def test_select_cases_keeps_local_only_cases_in_full_mode():
    assert select_cases(CASES) == (CASES, [])


def test_select_cases_skips_local_only_cases_in_ci_mode():
    kept, skipped = select_cases(CASES, ci=True)
    assert [c["id"] for c in kept] == [1, 3]
    assert skipped == [2]


def test_select_cases_limit():
    assert [c["id"] for c in select_cases(CASES, limit=2)[0]] == [1, 2]


# ---- the engine with the fake bot ----

def test_engine_with_fake_bot():
    cases = json.loads((HERE / "fake_cases.json").read_text(encoding="utf-8"))
    card = run_eval.evaluate(fake_bot, "fake_bot", cases, runs=2)
    by_id = {c["id"]: c for c in card["cases"]}
    assert card["adapter"] == "fake_bot"
    assert by_id[1]["diagnoses"] == ["pass", "pass"]
    assert by_id[2]["diagnoses"] == ["pass", "pass"]
    assert by_id[3]["diagnoses"] == ["answer wrong", "answer wrong"]  # fails on purpose
    assert by_id[1]["retrieval_ok"] is None  # the fake bot has no search()
    assert by_id[1]["last_route"] is None    # ... and reports no route
    assert card["average_pass_rate"] == 2 / 3


def test_engine_counts_a_crash():
    class Broken:
        @staticmethod
        def ask(question):
            raise RuntimeError("boom")
    card = run_eval.evaluate(Broken, "broken", [{"id": 1, "question": "q", "expected_route": "rag",
                                                 "answer_keys": [], "retrieval_keys": []}], runs=1)
    assert card["cases"][0]["diagnoses"] == ["crash"]


def test_run_eval_command_line_saves_report_card(tmp_path):
    out = tmp_path / "run_fake.json"
    assert run_eval.main(["--adapter", "fake_bot", "--cases", str(HERE / "fake_cases.json"),
                          "--runs", "1", "--out", str(out)]) == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["adapter"] == "fake_bot"
    assert [c["passes"] for c in saved["cases"]] == [1, 1, 0]
