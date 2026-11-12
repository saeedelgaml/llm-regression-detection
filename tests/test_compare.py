"""Tests for the regression rules and for compare.py refusing to mix adapters."""
import json
import os

import pytest

from evaluator import compare
from evaluator.checks import compare_runs


def case(i, pass_rate, retrieval_ok=None, diagnoses=None):
    runs = 3
    diagnoses = diagnoses or (["pass"] * round(pass_rate * runs) + ["answer wrong"] * (runs - round(pass_rate * runs)))
    return {"id": i, "pass_rate": pass_rate, "retrieval_ok": retrieval_ok, "diagnoses": diagnoses}


def run(cases, adapter="egypt_data_jobs", mode=None):
    data = {"adapter": adapter, "runs": 3, "cases": cases}
    if mode:
        data["mode"] = mode
    return data


# ---- the three rules ----

def test_identical_runs_are_ok():
    base = run([case(1, 1.0), case(2, 0.0)])
    assert compare_runs(base, base)["regression"] is False


def test_small_drop_is_ok():
    # 20 cases, one goes from 3/3 to 2/3: average drops 1.7 points (< 5)
    base = run([case(i, 1.0) for i in range(20)])
    cur = run([case(i, 1.0) for i in range(19)] + [case(19, 2 / 3)])
    result = compare_runs(base, cur)
    assert result["regression"] is False
    assert [w["id"] for w in result["worse"]] == [19]


def test_rule1_average_drop_over_tolerance():
    base = run([case(i, 1.0) for i in range(10)])
    cur = run([case(i, 1.0) for i in range(9)] + [case(9, 1 / 3)])  # drop 6.7 points
    result = compare_runs(base, cur)
    assert result["regression"] is True
    assert "average pass rate fell" in result["problems"][0]
    assert result["broken"] == []  # 1/3 is not "always fail"


def test_rule2_always_pass_to_always_fail():
    base = run([case(i, 1.0) for i in range(40)])
    cur = run([case(i, 1.0) for i in range(39)] + [case(39, 0.0, diagnoses=["wrong route"] * 3)])  # drop 2.5 only
    result = compare_runs(base, cur)
    assert result["broken"] == [39]
    assert result["regression"] is True
    assert result["worse"][0]["reason"] == "wrong route"


def test_rule3_search_lost_a_passage():
    base = run([case(1, 1.0, retrieval_ok=True)])
    cur = run([case(1, 1.0, retrieval_ok=False)])
    result = compare_runs(base, cur)
    assert result["search_lost"] == [1]
    assert result["regression"] is True


def test_search_gain_and_improvement_are_not_regressions():
    base = run([case(1, 0.0, retrieval_ok=False)])
    cur = run([case(1, 1.0, retrieval_ok=True)])
    result = compare_runs(base, cur)
    assert result["regression"] is False
    assert result["search_gained"] == [1]
    assert [b["id"] for b in result["better"]] == [1]


def test_only_shared_cases_are_compared():
    base = run([case(1, 1.0), case(2, 1.0)])
    cur = run([case(1, 1.0)])
    result = compare_runs(base, cur)
    assert result["shared"] == [1]
    assert result["missing"] == [2]
    assert result["regression"] is False


# ---- compare.py: which run, and refusing other adapters ----

def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_newest_run_ignores_other_adapters_and_modes(tmp_path):
    base = run([case(1, 1.0)])
    real = write(tmp_path / "run_1.json", run([case(1, 1.0)]))
    fake = write(tmp_path / "run_2.json", run([case(1, 0.0)], adapter="fake_bot"))
    ci = write(tmp_path / "run_3.json", run([case(1, 0.0)], mode="ci"))
    os.utime(real, (1, 1))  # oldest
    os.utime(fake, (2, 2))
    os.utime(ci, (3, 3))    # newest, but a CI run
    assert compare.newest_run(base, tmp_path) == real
    assert compare.newest_run(run([], mode="ci"), tmp_path) == ci
    assert compare.newest_run(run([], adapter="nobody"), tmp_path) is None


def test_compare_refuses_a_different_adapter(tmp_path, capsys):
    base = write(tmp_path / "baseline.json", run([case(1, 1.0)]))
    fake = write(tmp_path / "run_fake.json", run([case(1, 0.0)], adapter="fake_bot"))
    assert compare.main([str(fake), str(base)]) == 2
    assert "Cannot compare" in capsys.readouterr().out


def test_compare_refuses_a_different_mode(tmp_path):
    base = write(tmp_path / "baseline.json", run([case(1, 1.0)]))
    ci = write(tmp_path / "run_ci.json", run([case(1, 1.0)], mode="ci"))
    assert compare.main([str(ci), str(base)]) == 2


@pytest.mark.parametrize("after, code, verdict", [(1.0, 0, "VERDICT: OK"), (0.0, 1, "REGRESSION DETECTED")])
def test_compare_exit_codes(tmp_path, capsys, after, code, verdict):
    base = write(tmp_path / "baseline.json", run([case(1, 1.0)]))
    cur = write(tmp_path / "run_x.json", run([case(1, after)]))
    assert compare.main([str(cur), str(base)]) == code
    assert verdict in capsys.readouterr().out


def test_real_baseline_is_marked_with_its_adapter():
    base = compare.load(compare.ROOT / "baseline.json")
    assert base["adapter"] == "egypt_data_jobs"
