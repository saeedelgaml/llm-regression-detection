"""Build the evaluation report page (one self-contained HTML file, no external files).

    python evaluator/report.py results/run_ci.json results/verdict.json --out results/report/index.html

In CI the page is built only after the regression gate passed, and the chatbot's deploy job
publishes it to GitHub Pages at <site>/eval/. So the published page always shows a run that
passed the gate. This is a CI regression gate with a published report, not full CD.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CSS = """
:root { --bg:#ffffff; --fg:#1b1f24; --muted:#5b6470; --line:#d9dee4; --card:#f5f7f9;
        --ok:#1a7f37; --ok-bg:#dafbe1; --bad:#b42318; --bad-bg:#fee4e2; --na:#6e7781; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0f1216; --fg:#e6e9ed; --muted:#9aa4af; --line:#2c333b; --card:#171b21;
          --ok:#4ac26b; --ok-bg:#12261a; --bad:#ff7b72; --bad-bg:#2d1414; --na:#8b949e; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 1.5rem; margin: 0 0 4px; }
h2 { font-size: 1.1rem; margin: 32px 0 8px; }
p { margin: 8px 0; }
.muted { color: var(--muted); }
.banner { margin: 16px 0; padding: 12px 16px; border-radius: 8px; background: var(--ok-bg); color: var(--ok);
          font-weight: 600; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 16px 0; }
.tile { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; }
.tile .label { color: var(--muted); font-size: .85rem; }
.tile .value { font-size: 1.5rem; font-weight: 650; font-variant-numeric: tabular-nums; }
.scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
table { border-collapse: collapse; width: 100%; min-width: 640px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { background: var(--card); font-size: .85rem; color: var(--muted); font-weight: 600; }
tr:last-child td { border-bottom: 0; }
td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.pass { color: var(--ok); font-weight: 600; }
.fail { color: var(--bad); font-weight: 600; }
.na { color: var(--na); }
ul { padding-left: 20px; }
"""


def cell_search(r):
    if r["retrieval_ok"] is None:
        return '<span class="na">n/a</span>'
    if r["retrieval_ok"]:
        return f'<span class="pass">found</span> <span class="muted">(rank {r["retrieval_rank"]})</span>'
    return '<span class="fail">missed</span>'


def cell_result(r):
    labels = sorted(set(r["diagnoses"]))
    if labels == ["pass"]:
        return '<span class="pass">pass</span>'
    return ", ".join(f'<span class="{"pass" if d == "pass" else "fail"}">{escape(d)}</span>' for d in labels)


def build(card, summary, questions, built_at=None, source=""):
    mode = card.get("mode", "full")
    built_at = built_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    change = (summary["cur_avg"] - summary["base_avg"]) * 100
    skipped = card.get("skipped", [])
    rows = []
    for r in card["cases"]:
        rows.append(
            "<tr>"
            f'<td class="num">{r["id"]}</td>'
            f"<td>{escape(questions.get(r['id'], ''))}</td>"
            f"<td>{escape(r['expected_route'])}</td>"
            f"<td>{escape(str(r['last_route']))}</td>"
            f"<td>{cell_search(r)}</td>"
            f"<td>{cell_result(r)}</td>"
            "</tr>")
    what = ("CI mode: the route each question takes and whether search finds the right passage. "
            "No answers are written (GitHub's servers have no language model)."
            if mode == "ci" else "Full run: route, search and the written answers.")
    better = ", ".join(str(b["id"]) for b in summary["better"]) or "none"
    worse = ", ".join(str(w["id"]) for w in summary["worse"]) or "none"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chatbot Evaluation Report</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>Chatbot evaluation report</h1>
<p class="muted">Golden set of the egypt-data-jobs chatbot, checked by the CI regression gate.
Built {escape(built_at)}{(" from " + escape(source)) if source else ""}.</p>

<div class="banner">Regression gate passed: no regression against the baseline</div>

<div class="tiles">
  <div class="tile"><div class="label">Pass rate</div><div class="value">{summary['cur_avg']:.1%}</div></div>
  <div class="tile"><div class="label">Baseline</div><div class="value">{summary['base_avg']:.1%}</div></div>
  <div class="tile"><div class="label">Change</div><div class="value">{change:+.1f} pts</div></div>
  <div class="tile"><div class="label">Search found passage</div>
    <div class="value">{card['search_ok']} / {card['report_cases']}</div></div>
</div>

<h2>What was checked</h2>
<p>{escape(what)}</p>
<ul>
  <li>{len(card['cases'])} cases, {card['runs']} run(s) each.</li>
  <li>Skipped (local-only, need a file that is not published): {", ".join(map(str, skipped)) or "none"}.</li>
  <li>Got better than the baseline: {better}. Got worse: {worse}.</li>
  <li>The gate fails if the average drops more than {summary['tolerance'] * 100:.0f} points, a case that always
      passed now always fails, or search stops finding a passage it used to find.</li>
</ul>

<h2>Cases</h2>
<div class="scroll">
<table>
<thead><tr><th>#</th><th>Question</th><th>Expected route</th><th>Route taken</th><th>Search</th><th>Result</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
</div>
<p class="muted">Failures that are already in the baseline do not fail the gate; only changes do.
Labels: wrong route = the router chose the wrong path; search missed = the right passage was not found.</p>
</main>
</body>
</html>
"""


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Build the evaluation report page.")
    p.add_argument("run")
    p.add_argument("summary", help="verdict JSON from compare.py --summary-out")
    p.add_argument("--cases", default=str(ROOT / "golden_set" / "test_cases.json"))
    p.add_argument("--out", default="results/report/index.html")
    args = p.parse_args(argv)

    card = json.loads(Path(args.run).read_text(encoding="utf-8"))
    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    if summary["verdict"] != "OK":
        print("The gate did not pass: no report page is built.")
        return 1
    questions = {c["id"]: c["question"] for c in json.loads(Path(args.cases).read_text(encoding="utf-8"))}
    repo, sha = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_SHA", "")
    source = f"{repo} @ {sha[:7]}" if repo else ""
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(card, summary, questions, source=source), encoding="utf-8")
    print("Report page:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
