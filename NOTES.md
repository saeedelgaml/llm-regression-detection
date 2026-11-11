# Notes

## The AI feature
The thing being tested is my RAG chatbot from egypt-data-jobs. It first routes a question to one of three paths: answer from the reports (rag), answer from the job database, or refuse. The reports path searches the PDFs, then a small local model run through Ollama (qwen2.5:3b by default) writes the answer from the passages it finds. Because the model can word things differently each time, the same question can pass once and fail the next time.

## Golden set
The golden set is my exam: 32 questions (26 report questions, 1 database question, 5 that should be refused). Each one stores the route the chatbot should take and short "answer keys", which are words or numbers that must appear in a correct answer. I use short keys instead of full sentences because the model never words an answer the same way twice. A nested list in the keys means "either one is fine" (for example "IT Services" or "Information Technology").

## Evaluator
run_eval.py asks every question 3 times and checks the route and the answer keys each time. For report questions it also checks once whether the search found the right passage, using short number-based "retrieval keys". Every failure gets one label, checked in this order: wrong route, search missed, answer wrong. A crash is counted separately. The labels tell me which stage of the chatbot to fix instead of just "it failed". My first full run scored 59.4%, and search found the right passage in 24 of 26 report questions.

## Comparison with the baseline
baseline.json is a saved copy of that first run. compare.py checks a new run against it and says REGRESSION (and exits with code 1, which CI will use to block a change) if any one of three things happens: the average score drops by more than 5 points, a case that always passed now always fails, or search stops finding a passage it used to find. Otherwise it says OK.

## What the evaluator cannot check
It only checks that certain words or numbers appear in the answer. An answer can contain the right number and still be wrong or misleading around it, and it can be correct while worded so differently that no key matches. It cannot judge tone or completeness. Case 27 (a database question) only checks the route, because its answer changes with the data. With only 32 cases and 3 runs each, a small drop can be noise, which is why the alert threshold is 5 points and not 1.

## Lesson: short retrieval keys
My first retrieval keys were long phrases, and the check said "search missed" even when search had found the right page. The text extracted from PDFs has odd spacing and symbols, so long exact phrases rarely match. Short, distinctive keys built around numbers (like "15.7 per cent") match reliably. After I shortened the keys for six cases (5, 14, 17, 19, 20, 23), search found the right passage in 24 of 26 report questions. The two that still miss (cases 15 and 26) are real search problems, not key problems.