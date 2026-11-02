"""Secret / password datasets. All score the single family SECRET.

Public sets (fetched once into `bench/.cache`, see README):
  creddata       Samsung CredData, labelled lines of real repositories — the de-facto
                 benchmark for credential scanners. Only the 221 repos that are NOT in the
                 cbx-secrets-detector training list (`test_repos_crc.json`); UUID rows are
                 excluded from both sides (not a secret in our product's sense).
  gravitee-pw    gravitee-io/pii-detection-dataset rows with a PASSWORD span + as many
                 rows without one (English prose, JSON/XML records).
  aparte         apartejs/aparte-secrets-data — chat phrases, configs, JSON, HTTP, negatives
                 (en/fr, synthetic, ODC-BY).
  issue-reports  Zenodo 17430336 (CC BY 4.0): candidate strings in GitHub issue texts,
                 manually labelled; one example = ±400 chars around a candidate.
  pii-bench-secret  hivetrace/pii-bench rows with a TOKEN span (ru) + as many without.
Own: secrets-ru — generated (synthetic_secrets.py).
"""

from __future__ import annotations

import csv
import json
import os
import random
from pathlib import Path

from .types import IGNORE, Dataset, Example, Span

CACHE = Path(__file__).resolve().parent.parent / ".cache"
SEED = 506


def load_creddata(limit: int | None = None) -> Dataset:
    root = Path(os.environ.get("CREDDATA_DIR", CACHE / "creddata"))
    test_repos = set(json.loads((root / "test_repos_crc.json").read_text()))
    by_line: dict[tuple[str, int, int], tuple[str, list[Span], dict]] = {}
    files: dict[str, list[str]] = {}
    for meta in sorted((root / "meta").glob("*.csv")):
        for r in csv.DictReader(meta.open(encoding="utf-8")):
            if r["RepoName"] not in test_repos:
                continue
            start, end = int(r["LineStart"]), int(r["LineEnd"])
            key = (r["FilePath"], start, end)
            if key not in by_line:
                if r["FilePath"] not in files:
                    files[r["FilePath"]] = (root / r["FilePath"]).read_text(encoding="utf-8", errors="replace").split("\n")
                text = "\n".join(files[r["FilePath"]][start - 1:end])
                by_line[key] = (text, [], {"category": r["Category"], "gt": r["GroundTruth"],
                                           "path": r["FilePath"], "line": start, "lines": end - start + 1})
            if r["GroundTruth"] != "T":
                continue
            text, spans, _ = by_line[key]
            label = IGNORE if r["Category"].split(":")[0] == "UUID" else "SECRET"
            if r["ValueStart"] and start == end:
                value_end = int(r["ValueEnd"]) if r["ValueEnd"] else len(text.rstrip())
                spans.append(Span(int(r["ValueStart"]), value_end, label))
            else:
                stripped = text.strip()
                spans.append(Span(text.index(stripped), text.index(stripped) + len(stripped), label))
    examples = [Example(t, s, "en", m) for t, s, m in by_line.values() if t.strip()]
    return Dataset("creddata", examples[:limit], {"SECRET"}, "Apache-2.0 (+ per-repo licences)", "Samsung/CredData, test repos")


def load_gravitee_pw(limit: int | None = None) -> Dataset:
    from datasets import load_dataset

    rng = random.Random(SEED)
    positives, negatives = [], []
    for r in load_dataset("gravitee-io/pii-detection-dataset")["train"]:
        spans = [Span(s["start"], s["end"], "SECRET") for s in r["spans"] if s["label"] == "PASSWORD"]
        (positives if spans else negatives).append(Example(r["text"], spans, "en", {"source": r["source"]}))
    examples = positives + rng.sample(negatives, len(positives))
    rng.shuffle(examples)
    return Dataset("gravitee-pw", examples[:limit], {"SECRET"}, "Apache-2.0", "gravitee-io/pii-detection-dataset (PASSWORD)")


def load_aparte(limit: int | None = None) -> Dataset:
    from huggingface_hub import snapshot_download

    root = Path(snapshot_download("apartejs/aparte-secrets-data", repo_type="dataset"))
    rng = random.Random(SEED)
    examples: list[Example] = []
    for path in sorted((root / "data").glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for r in rng.sample(rows, min(400, len(rows))):
            spans = [Span(s["start"], s["end"], "SECRET") for s in r["secrets"]]
            examples.append(Example(r["text"], spans, "en", {"file": path.stem, "lang": r["lang"], "mode": r["mode"]}))
    rng.shuffle(examples)
    return Dataset("aparte", examples[:limit], {"SECRET"}, "ODC-BY 1.0", "apartejs/aparte-secrets-data")


def load_issue_reports(limit: int | None = None) -> Dataset:
    root = Path(os.environ.get("ISSUE_REPORTS_DIR", CACHE / "issue-reports"))
    csv.field_size_limit(1 << 30)
    examples: list[Example] = []
    for name, key in (("test.csv", "Issue_id"), ("test_wild.csv", "issue_url")):
        rows = list(csv.DictReader((root / name).open(encoding="utf-8", errors="replace", newline="")))
        positives: dict[str, list[tuple[int, int]]] = {}
        for r in rows:
            if r["label"] == "1" and (pos := r["text"].find(r["candidate_string"])) >= 0:
                positives.setdefault(r[key], []).append((pos, pos + len(r["candidate_string"])))
        for r in rows:
            pos = r["text"].find(r["candidate_string"])
            if pos < 0:
                continue
            lo, hi = max(0, pos - 400), min(len(r["text"]), pos + len(r["candidate_string"]) + 400)
            spans = [Span(s - lo, e - lo, "SECRET") for s, e in positives.get(r[key], []) if s >= lo and e <= hi]
            examples.append(Example(r["text"][lo:hi], spans, "en", {"file": name, "label": r["label"]}))
    return Dataset("issue-reports", examples[:limit], {"SECRET"}, "CC BY 4.0", "zenodo.org/records/17430336 (test + test_wild)")


def load_pii_bench_secret(limit: int | None = None) -> Dataset:
    from datasets import load_dataset

    rng = random.Random(SEED)
    ds = load_dataset("hivetrace/pii-bench")
    positives, negatives = [], []
    for split in ("domain", "entity"):
        for r in ds[split]:
            spans = [Span(e["start"], e["end"], "SECRET") for e in r["entities"] if e["type"] == "TOKEN"]
            (positives if spans else negatives).append(Example(r["text"], spans, "ru", {"split": split}))
    examples = positives + rng.sample(negatives, len(positives))
    rng.shuffle(examples)
    return Dataset("pii-bench-secret", examples[:limit], {"SECRET"}, "Apache-2.0 (eval only)", "hivetrace/pii-bench (TOKEN)")


def load_secrets_ru(limit: int | None = None) -> Dataset:
    from .synthetic_secrets import generate_secrets_ru

    examples = generate_secrets_ru(seed=SEED, count=limit or 450)
    return Dataset("secrets-ru", examples, {"SECRET"}, "own (generated)", "bench/buffbench/synthetic_secrets.py")


def load_agent_real(limit: int | None = None) -> Dataset:
    """Tool outputs of real agent trajectories with our own labels (bench/data/agent-real.jsonl)."""
    path = Path(__file__).resolve().parent.parent / "data" / "agent-real.jsonl"
    examples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        spans = [Span(s["start"], s["end"], "SECRET") for s in r["spans"]]
        examples.append(Example(r["text"], spans, "en", {"src": r["src"], "repo": r["repo"], "id": r["id"]}))
    return Dataset("agent-real", examples[:limit], {"SECRET"}, "CC BY 4.0 (traces) + per-repo; labels: own",
                   "nvidia/Open-SWE-Traces + nebius/SWE-agent-trajectories, labelled by us")


def load_agent_runs(limit: int | None = None) -> Dataset:
    from .synthetic_agent import generate_agent_runs

    examples = generate_agent_runs(seed=SEED, count=limit or 340)
    return Dataset("agent-runs", examples, {"SECRET"}, "own (generated)", "bench/buffbench/synthetic_agent.py")


def load_creddata_files(limit: int | None = None, window: int = 7) -> Dataset:
    """CredData as an agent reads it: ±`window` lines of the file around a labelled line
    (positives around T lines, negatives around F lines), all T spans inside as gold."""
    lines_ds = load_creddata()
    by_file: dict[str, list[Example]] = {}
    for ex in lines_ds.examples:
        by_file.setdefault(ex.meta["path"], []).append(ex)
    rng = random.Random(SEED)
    examples: list[Example] = []
    root = Path(os.environ.get("CREDDATA_DIR", CACHE / "creddata"))
    for path, rows in by_file.items():
        lines = (root / path).read_text(encoding="utf-8", errors="replace").split("\n")
        examples.extend(_windows(rng, path, lines, rows, window))
    rng.shuffle(examples)
    return Dataset("creddata-files", examples[:limit], {"SECRET"}, lines_ds.licence, "Samsung/CredData, 15-line windows")


def _windows(rng: random.Random, path: str, lines: list[str], rows: list[Example], window: int) -> list[Example]:
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    gold = [(offsets[r.meta["line"] - 1] + s.start, offsets[r.meta["line"] - 1] + s.end, s.label)
            for r in rows for s in r.spans if r.meta["lines"] == 1]
    centers = [r.meta["line"] for r in rows if r.spans and r.meta["lines"] == 1] + rng.sample(
        [r.meta["line"] for r in rows if not r.spans], min(2, sum(1 for r in rows if not r.spans)))
    out: list[Example] = []
    for line_no in sorted(set(centers)):
        lo_line, hi_line = max(0, line_no - 1 - window), min(len(lines), line_no + window)
        lo, hi = offsets[lo_line], offsets[hi_line] - 1
        text = "\n".join(lines[lo_line:hi_line])
        spans = [Span(s - lo, e - lo, label) for s, e, label in gold if s >= lo and e <= hi]
        out.append(Example(text, spans, "en", {"path": path, "center": line_no}))
    return out


SECRET_LOADERS = {
    "agent-real": load_agent_real,
    "agent-runs": load_agent_runs,
    "creddata-files": load_creddata_files,
    "creddata": load_creddata,
    "gravitee-pw": load_gravitee_pw,
    "aparte": load_aparte,
    "issue-reports": load_issue_reports,
    "pii-bench-secret": load_pii_bench_secret,
    "secrets-ru": load_secrets_ru,
}
