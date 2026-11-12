"""Adapter for the egypt-data-jobs chatbot.

The engine (evaluator/run_eval.py) only talks to a chatbot through this file.
Required: ask(question) -> {"text": ..., "route": ... (optional)}
Optional: search(question) -> {"passages": [...], "best_score": ...}
"""
import os
import sys
from pathlib import Path

# Where the chatbot repo lives. CI will set EGYPT_CHATBOT_DIR; on your PC the default is used.
CHATBOT_DIR = Path(os.environ.get(
    "EGYPT_CHATBOT_DIR", r"C:\Users\Original Nassar\Documents\egypt-data-jobs"))
sys.path.insert(0, str(CHATBOT_DIR))

import duckdb
from chatbot.ai import answer_question
from chatbot.router import RuleRouter
from chatbot.rag_route import RagRoute
from chatbot.local_ai import LocalAI
from rag import retrieve

# ---- Switch the chatbot on (runs once, when the engine loads this file) ----
con = duckdb.connect(str(CHATBOT_DIR / "data" / "jobs.duckdb"), read_only=True)
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