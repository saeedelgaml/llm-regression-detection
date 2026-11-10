import json

with open("golden_set/test_cases.json", encoding="utf-8") as f:
    cases = json.load(f)

print("Number of cases:", len(cases))

for case in cases:
    print(case["id"], case["question"])