"""Tests for the Discord alert. A fake opener stands in for the internet: nothing is sent."""
import json

import pytest

from evaluator import alert, compare
from evaluator.checks import compare_runs


def summary(regression=True):
    base = {"adapter": "egypt_data_jobs", "mode": "ci", "runs": 1, "cases": [
        {"id": 1, "pass_rate": 1.0, "retrieval_ok": True, "diagnoses": ["pass"]},
        {"id": 2, "pass_rate": 1.0, "retrieval_ok": True, "diagnoses": ["pass"]},
    ]}
    cur = json.loads(json.dumps(base))
    if regression:
        cur["cases"][0].update(pass_rate=0.0, diagnoses=["wrong route"])
        cur["cases"][1].update(pass_rate=0.0, retrieval_ok=False, diagnoses=["search missed"])
    return {"verdict": "REGRESSION" if regression else "OK", "mode": "ci", "current": "run_ci.json",
            **compare_runs(base, cur)}


class FakeOpener:
    def __init__(self, fail=False):
        self.requests, self.fail = [], fail

    def __call__(self, request, timeout):
        if self.fail:
            raise OSError("network down")
        self.requests.append(request)

        class Response:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return Response()


@pytest.fixture(autouse=True)
def no_github_env(monkeypatch):
    for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_REF_NAME", "GITHUB_SHA",
              "DISCORD_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)


def test_message_lists_cases_with_their_diagnosis_labels():
    text = alert.regression_message(summary())
    assert "LLM regression gate FAILED" in text
    assert "case 1: 100% -> 0%, **wrong route**" in text
    assert "chatbot/router.py" in text
    assert "case 2: 100% -> 0%, **search missed**" in text
    assert "rag/retrieve.py" in text


def test_message_links_to_the_github_run(monkeypatch):
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/chatbot")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234567")
    text = alert.regression_message(summary())
    assert "Run: https://github.com/someone/chatbot/actions/runs/42" in text
    assert "someone/chatbot @ main (abcdef1)" in text


def test_long_messages_are_cut_to_discords_limit():
    text = alert.shorten("x" * 5000)
    assert len(text) == alert.DISCORD_LIMIT and text.endswith("full list)")
    assert alert.shorten("short") == "short"


def test_sends_json_to_the_webhook(tmp_path, monkeypatch):
    path = tmp_path / "verdict.json"
    path.write_text(json.dumps(summary()), encoding="utf-8")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    opener = FakeOpener()
    assert alert.main([str(path)], opener=opener) == 0
    request = opener.requests[0]
    body = json.loads(request.data)
    assert request.full_url == "https://discord.example/webhook"
    assert request.get_method() == "POST"
    assert "wrong route" in body["content"]
    assert body["allowed_mentions"] == {"parse": []}  # never pings @everyone


def test_without_webhook_it_only_prints(tmp_path, capsys):
    path = tmp_path / "verdict.json"
    path.write_text(json.dumps(summary()), encoding="utf-8")
    opener = FakeOpener()
    assert alert.main([str(path)], opener=opener) == 0
    assert opener.requests == []
    assert "not set" in capsys.readouterr().out


def test_ok_verdict_sends_nothing(tmp_path, monkeypatch):
    path = tmp_path / "verdict.json"
    path.write_text(json.dumps(summary(regression=False)), encoding="utf-8")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    opener = FakeOpener()
    assert alert.main([str(path)], opener=opener) == 0
    assert opener.requests == []


def test_gate_did_not_run_message(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    opener = FakeOpener()
    assert alert.main(["--gate-did-not-run"], opener=opener) == 0
    assert "could not run" in json.loads(opener.requests[0].data)["content"]


def test_send_failure_does_not_print_the_secret_url(tmp_path, monkeypatch, capsys):
    path = tmp_path / "verdict.json"
    path.write_text(json.dumps(summary()), encoding="utf-8")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook/SECRET")
    assert alert.main([str(path)], opener=FakeOpener(fail=True)) == 1
    assert "SECRET" not in capsys.readouterr().out


def test_compare_writes_the_summary_the_alert_reads(tmp_path):
    base = {"adapter": "a", "mode": "ci", "runs": 1, "cases": [{"id": 1, "pass_rate": 1.0, "diagnoses": ["pass"]}]}
    cur = {**base, "cases": [{"id": 1, "pass_rate": 0.0, "diagnoses": ["search missed"]}]}
    (tmp_path / "b.json").write_text(json.dumps(base), encoding="utf-8")
    (tmp_path / "c.json").write_text(json.dumps(cur), encoding="utf-8")
    out = tmp_path / "verdict.json"
    assert compare.main([str(tmp_path / "c.json"), str(tmp_path / "b.json"), "--summary-out", str(out)]) == 1
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["verdict"] == "REGRESSION"
    assert saved["worse"][0]["reason"] == "search missed"
    assert "**search missed**" in alert.regression_message(saved)
