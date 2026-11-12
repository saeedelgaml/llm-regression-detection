"""Send a Discord message when the CI regression gate fails.

    python evaluator/alert.py results/verdict.json          # the gate found a regression
    python evaluator/alert.py --gate-did-not-run            # an earlier step failed (e.g. a PDF download)

The webhook URL comes from the environment variable DISCORD_WEBHOOK_URL (a GitHub secret in CI).
If it is not set, the message is only printed and the script exits 0, so forks and local runs work.
Every failed case is listed with its diagnosis label, plus which part of the chatbot to look at.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DISCORD_LIMIT = 2000  # Discord refuses messages longer than this

WHERE_TO_LOOK = {
    "wrong route": "the router (chatbot/router.py) sent it to the wrong path",
    "search missed": "the search (rag/retrieve.py, rag/ingest.py) did not return the right passage",
    "answer wrong": "the answer step (rag/answer.py, the prompt or the model) wrote a wrong answer",
    "crash": "the chatbot raised an error",
    "unknown": "no failure label recorded",
}


def run_link():
    """Link to this GitHub Actions run (empty outside GitHub Actions)."""
    server, repo, run_id = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run_id}" if server and repo and run_id else ""


def where(fallback):
    """'owner/repo @ branch (commit)' in GitHub Actions, else the fallback text."""
    repo, ref_name, sha = (os.environ.get(k, "") for k in ("GITHUB_REPOSITORY", "GITHUB_REF_NAME", "GITHUB_SHA"))
    return f"{repo} @ {ref_name} ({sha[:7]})" if repo else fallback


def regression_message(summary):
    lines = [f"**LLM regression gate FAILED** - {where(summary.get('current', ''))}",
             f"Pass rate {summary['base_avg']:.1%} -> {summary['cur_avg']:.1%} "
             f"({(summary['cur_avg'] - summary['base_avg']) * 100:+.1f} points, mode: {summary.get('mode', 'full')})",
             "", "**Why it failed:**"]
    lines += [f"- {p}" for p in summary["problems"]]
    if summary["worse"]:
        lines += ["", "**Cases that got worse:**"]
        for w in summary["worse"]:
            lines.append(f"- case {w['id']}: {w['before']:.0%} -> {w['after']:.0%}, **{w['reason']}**: "
                         f"{WHERE_TO_LOOK.get(w['reason'], w['reason'])}")
    for i in summary["search_lost"]:
        if i not in {w["id"] for w in summary["worse"]}:
            lines.append(f"- case {i}: **search missed**: {WHERE_TO_LOOK['search missed']}")
    if run_link():
        lines += ["", f"Run: {run_link()}"]
    return "\n".join(lines)


def did_not_run_message():
    lines = [f"**LLM regression gate could not run** - {where('local run')}",
             "A step before the comparison failed (installing, downloading the report PDFs, building the "
             "index or running the golden set), so there is no verdict. The deploy is blocked."]
    if run_link():
        lines.append(f"Run: {run_link()}")
    return "\n".join(lines)


def shorten(text, limit=DISCORD_LIMIT):
    if len(text) <= limit:
        return text
    tail = "\n... (cut; see the run for the full list)"
    return text[:limit - len(tail)] + tail


def send(text, url, opener=urllib.request.urlopen):
    body = json.dumps({"content": text, "allowed_mentions": {"parse": []}}).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "User-Agent": "llm-regression-detection (CI alert)",  # Discord rejects Python's default user agent
    })
    with opener(request, timeout=20) as response:
        return response.status


def main(argv=None, opener=urllib.request.urlopen):
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--gate-did-not-run"]:
        text = did_not_run_message()
    elif len(argv) == 1:
        summary = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
        if summary["verdict"] != "REGRESSION":
            print("Verdict is OK: no alert.")
            return 0
        text = regression_message(summary)
    else:
        print(__doc__)
        return 2
    text = shorten(text)
    print(text)
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        print("\nDISCORD_WEBHOOK_URL is not set: message printed only, not sent.")
        return 0
    try:
        status = send(text, url, opener)
    except Exception as e:  # never print the URL: it is a secret
        print(f"\nCould not send the Discord message ({type(e).__name__}).")
        return 1
    print(f"\nDiscord message sent (HTTP {status}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
