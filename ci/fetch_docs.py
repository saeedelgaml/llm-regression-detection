"""Download the report files listed in ci/docs.json and check their SHA-256.

    python ci/fetch_docs.py <target folder>      e.g. python ci/fetch_docs.py ../chatbot/rag/docs

A file that is already there with the right hash is not downloaded again (CI caches the folder).
Exits 1 if a download fails or a file's hash differs: if a publisher changes a PDF, CI must stop
instead of silently comparing against a baseline built from different documents.
"""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

LIST = Path(__file__).resolve().parent / "docs.json"
USER_AGENT = "Mozilla/5.0 (compatible; llm-regression-detection CI)"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url, path):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, open(path, "wb") as f:
        while block := response.read(1 << 20):
            f.write(block)


def fetch(target, docs):
    target.mkdir(parents=True, exist_ok=True)
    problems = []
    for doc in docs:
        path = target / doc["filename"]
        if path.exists() and sha256(path) == doc["sha256"]:
            print(f"ok (already there)  {doc['filename']}")
            continue
        try:
            download(doc["url"], path)
        except Exception as e:
            problems.append(f"{doc['filename']}: download failed ({e})")
            continue
        if sha256(path) != doc["sha256"]:
            problems.append(f"{doc['filename']}: SHA-256 differs from ci/docs.json (the publisher changed the file?)")
            continue
        print(f"ok (downloaded)     {doc['filename']}")
    return problems


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    problems = fetch(Path(argv[0]), json.loads(LIST.read_text(encoding="utf-8"))["docs"])
    for p in problems:
        print("ERROR:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
