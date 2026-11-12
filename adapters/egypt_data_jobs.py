"""Adapter for the egypt-data-jobs chatbot.

The engine (evaluator/run_eval.py) only talks to a chatbot through this file.
Required: ask(question) -> {"text": ..., "route": ... (optional)}
Optional: search(question) -> {"passages": [...], "best_score": ...}
Optional: route(question) -> "rag" | "database" | "refuse"   (CI mode: no language model)

Settings (environment variables; on your PC the defaults are used):
    EGYPT_CHATBOT_DIR  the chatbot repo           (CI: the checked-out repo)
    EGYPT_CHATBOT_DB   the DuckDB database file   (CI: data/sample.duckdb, the only database in git)
"""
import os
import sys
from pathlib import Path

CHATBOT_DIR = Path(os.environ.get(
    "EGYPT_CHATBOT_DIR", r"C:\Users\Original Nassar\Documents\egypt-data-jobs"))
DB_PATH = Path(os.environ.get("EGYPT_CHATBOT_DB", CHATBOT_DIR / "data" / "jobs.duckdb"))
sys.path.insert(0, str(CHATBOT_DIR))

import duckdb
from chatbot.ai import answer_question, reports_first
from chatbot.local_ai import BLOCKED, LocalAI
from chatbot.rag_route import RagRoute
from chatbot.router import RuleRouter
from config import MAX_QUESTION_CHARS
from rag import retrieve

# ---- Switch the chatbot on (runs once, when the engine loads this file). No model is called here. ----
con = duckdb.connect(str(DB_PATH), read_only=True)
chooser = RuleRouter(con)
rag = RagRoute()
fallback = LocalAI(con)


def route_of(result):
    """Translate this chatbot's internal function names into the golden set's route names."""
    fn = result["function"]
    if fn is None:
        return "refuse"
    if fn == "rag":
        return "rag"
    if fn == "ai_sql":
        return "sql"
    return "database"


def ask(question):
    result = answer_question(con, question, chooser, None, fallback, rag)
    return {"text": result["text"], "route": route_of(result)}


def search(question):
    hits = retrieve.search(question)
    return {
        "passages": [hit["text"] for hit in hits],
        "best_score": hits[0]["best_score"] if hits else None,
    }


def _reports_would_answer(question):
    """The check RagRoute makes before it asks the model: enabled, not blocked, best passage >= threshold."""
    if not rag.enabled or BLOCKED.search(question):
        return False
    hits = rag.search(question)
    return bool(hits) and hits[0]["best_score"] >= rag.threshold


def route(question):
    """Where the chatbot sends a question BEFORE any language model is asked. Deterministic, no Ollama.

    Same order as chatbot.ai.answer_question: fixed answers (rule router) -> reports -> refusal.
    Two things only the model decides are not covered: the model can still say "not covered" for a
    report question, and the SQL fallback can answer a question no fixed answer fits. So this is the
    "planned" route; ask() gives the final one."""
    question = question.strip()
    if not question or len(question) > MAX_QUESTION_CHARS:
        return "refuse"
    choice = chooser(question)
    if choice.get("function") is None:
        return "rag" if _reports_would_answer(question) else "refuse"
    if reports_first(chooser, question, choice) and _reports_would_answer(question):
        return "rag"
    return "database"
