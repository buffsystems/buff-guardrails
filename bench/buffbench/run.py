"""CLI: run detectors over datasets, write raw JSON results, render a table.

  python -m buffbench.run run --detectors rules,spacy-lg --datasets pii-bench,jayguard [--limit N]
  python -m buffbench.run report results/raw/*.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import sys
import time
from pathlib import Path

from .detectors import DETECTORS as PII_DETECTORS
from .detectors_secrets import SECRET_DETECTORS
from .loaders import LOADERS

DETECTORS = {**PII_DETECTORS, **SECRET_DETECTORS}
from .metrics import Scores, score_example

RESULTS = Path(__file__).resolve().parent.parent / "results"


def run(detector_names: list[str], dataset_names: list[str], limit: int | None, out_dir: Path,
        sample: int | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    datasets = {name: LOADERS[name](limit) for name in dataset_names}
    if sample:  # seeded random subset — the same rows for every detector
        for ds in datasets.values():
            if len(ds.examples) > sample:
                ds.examples = random.Random(506).sample(ds.examples, sample)
    written: list[Path] = []
    for dname in detector_names:
        detector = DETECTORS[dname]
        t0 = time.perf_counter()
        detector.load()
        load_s = time.perf_counter() - t0
        print(f"[{dname}] loaded in {load_s:.1f}s", file=sys.stderr, flush=True)
        for name, ds in datasets.items():
            total = Scores()
            latencies: list[float] = []
            for i, ex in enumerate(ds.examples):
                t = time.perf_counter()
                spans = detector.analyze(ex.text, ex.language)
                latencies.append(time.perf_counter() - t)
                total.add(score_example(ex, spans, ds.families))
                if (i + 1) % 200 == 0:
                    print(f"[{dname}/{name}] {i + 1}/{len(ds.examples)}", file=sys.stderr, flush=True)
            record = {
                "detector": dname,
                "description": detector.description,
                "dataset": name,
                "licence": ds.licence,
                "source": ds.source,
                "n": len(ds.examples),
                "families": sorted(ds.families),
                "load_s": round(load_s, 1),
                "latency_ms": {
                    "p50": round(statistics.median(latencies) * 1000, 1),
                    "p95": round(sorted(latencies)[int(len(latencies) * 0.95) - 1] * 1000, 1),
                    "mean": round(statistics.fmean(latencies) * 1000, 1),
                },
                "cpu": platform.processor() or platform.machine(),
                "threads": os.cpu_count(),
                "leak": round(total.leak, 4),
                "overmask": round(total.overmask, 4),
                "exact": {k: {"p": v.precision, "r": v.recall, "f1": v.f1, "tp": v.tp, "fp": v.fp, "fn": v.fn}
                          for k, v in total.exact.items()},
                "chars": {k: {"p": v.precision, "r": v.recall, "f1": v.f1} for k, v in total.chars.items()},
            }
            path = out_dir / f"{dname}__{name}.json"
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            written.append(path)
            print(f"[{dname}/{name}] leak={record['leak']:.3f} overmask={record['overmask']:.3f} "
                  f"p50={record['latency_ms']['p50']}ms", file=sys.stderr, flush=True)
    return written


def report(paths: list[Path]) -> str:
    records = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    records.sort(key=lambda r: (r["dataset"], r["detector"]))
    lines: list[str] = ["## Summary — leak (PII characters left unmasked) per detector and dataset\n"]
    detectors = sorted({r["detector"] for r in records})
    datasets = sorted({r["dataset"] for r in records})
    lines.append("| detector | " + " | ".join(datasets) + " | p50 ms (pii-bench) |")
    lines.append("|---|" + "---|" * len(datasets) + "---|")
    for d in detectors:
        by_ds = {r["dataset"]: r for r in records if r["detector"] == d}
        cells = [f"{by_ds[x]['leak']:.3f} / {by_ds[x]['overmask']:.3f}" if x in by_ds else "—" for x in datasets]
        p50 = by_ds.get("pii-bench", {}).get("latency_ms", {}).get("p50", "—")
        lines.append(f"| {d} | " + " | ".join(cells) + f" | {p50} |")
    lines.append("\nCells are `leak / overmask`. Lower is better for both.\n")
    lines.extend(per_type_table(records, "rules", "pii-bench"))
    for dataset in sorted({r["dataset"] for r in records}):
        rows = [r for r in records if r["dataset"] == dataset]
        fams = rows[0]["families"]
        lines.append(f"\n### {dataset}  ({rows[0]['source']}, {rows[0]['licence']})\n")
        lines.append("| detector | n | leak | overmask | " + " | ".join(f"{f} F1" for f in fams) + " | p50 ms | p95 ms |")
        lines.append("|---|---|---|---|" + "---|" * len(fams) + "---|---|")
        for r in rows:
            cells = [f"{r['exact'].get(f, {}).get('f1', 0):.2f}/{r['chars'].get(f, {}).get('f1', 0):.2f}" for f in fams]
            lines.append(
                f"| {r['detector']} | {r['n']} | {r['leak']:.3f} | {r['overmask']:.3f} | " + " | ".join(cells)
                + f" | {r['latency_ms']['p50']} | {r['latency_ms']['p95']} |"
            )
        lines.append("\nF1 cells are `exact-span / character-level`.")
    return "\n".join(lines)


def per_type_table(records: list[dict], detector: str, dataset: str) -> list[str]:
    """Exact-span precision / recall / F1 of one detector per entity family (the README table)."""
    rows = [r for r in records if r["detector"] == detector and r["dataset"] == dataset]
    if not rows:
        return []
    r = rows[0]
    out = [f"## Per-type accuracy — `{detector}` on {dataset} (n={r['n']}, exact span match)\n",
           "| type | precision | recall | F1 | gold spans |", "|---|---|---|---|---|"]
    for fam, c in sorted(r["exact"].items(), key=lambda kv: -kv[1]["f1"]):
        gold = c["tp"] + c["fn"]
        if gold == 0:
            continue
        out.append(f"| {fam} | {c['p']:.2f} | {c['r']:.2f} | {c['f1']:.2f} | {gold} |")
    out.append("")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="buffbench")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--detectors", default="rules,spacy-lg")
    p_run.add_argument("--datasets", default=",".join(LOADERS))
    p_run.add_argument("--limit", type=int, default=None, help="take the first N rows (smoke tests)")
    p_run.add_argument("--sample", type=int, default=None, help="seeded random subset of N rows per dataset")
    p_run.add_argument("--out", default=str(RESULTS / "raw"))
    p_rep = sub.add_parser("report")
    p_rep.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    if args.cmd == "run":
        run(args.detectors.split(","), args.datasets.split(","), args.limit, Path(args.out), args.sample)
    else:
        print(report([Path(p) for p in args.paths]))


if __name__ == "__main__":
    main()
