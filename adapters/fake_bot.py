"""A pretend chatbot for testing the engine itself. No model, no database, instant.

It has only ask() and returns only text: no route and no search(). That is the
smallest thing an adapter can be, so it proves the engine works with any chatbot.
Used with tests/fake_cases.json, where case 3 is built to fail.
"""

ANSWERS = {
    "What is the capital of Egypt?": "The capital of Egypt is Cairo.",
    "How many days are in a week?": "A week has 7 days.",
    "What colour is the sky on a clear day?": "I am not sure.",  # wrong on purpose: case 3 must fail
}


def ask(question):
    return {"text": ANSWERS.get(question, "I don't know.")}
