"""Error analysis: print false negatives / false positives for one detector on
one dataset, per family, to see what the recognizers miss or over-match.

  python -m buffbench.errors --detector rules --dataset pii-bench --family CARD --limit 15
"""

from __future__ import annotations

import argparse
import random
from collections import defaultdict

from .detectors import DETECTORS
from .loaders import LOADERS
from .metrics import normalise
from .types import IGNORE


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--detector", default="rules")
    p.add_argument("--dataset", default="pii-bench")
    p.add_argument("--family", default=None, help="only this family (default: all)")
    p.add_argument("--limit", type=int, default=12, help="examples per family and error kind")
    p.add_argument("--sample", type=int, default=600)
    a = p.parse_args()

    ds = LOADERS[a.dataset](None)
    examples = ds.examples
    if len(examples) > a.sample:
        examples = random.Random(506).sample(examples, a.sample)
    det = DETECTORS[a.detector]
    det.load()
    fns: dict[str, list[str]] = defaultdict(list)
    fps: dict[str, list[str]] = defaultdict(list)
    for ex in examples:
        gold = normalise(ex.spans, ex.text, ds.families)
        pred = normalise(det.analyze(ex.text, ex.language), ex.text, ds.families)
        ignored = {i for s in ex.spans if s.label == IGNORE for i in range(s.start, s.end)}
        gset = {(s.start, s.end, s.label) for s in gold}
        pset = {(s.start, s.end, s.label) for s in pred}
        for s in gold:
            if (s.start, s.end, s.label) not in pset and (a.family in (None, s.label)):
                near = [ex.text[q.start:q.end] + ":" + q.label for q in pred if q.start < s.end and q.end > s.start]
                fns[s.label].append(f"{ex.text[s.start:s.end]!r}  pred_overlap={near}  ctx={ex.text[max(0, s.start - 25):s.end + 25]!r}")
        for s in pred:
            if (s.start, s.end, s.label) not in gset and (a.family in (None, s.label)) and not any(
                i in ignored for i in range(s.start, s.end)
            ):
                near = [ex.text[q.start:q.end] + ":" + q.label for q in gold if q.start < s.end and q.end > s.start]
                fps[s.label].append(f"{ex.text[s.start:s.end]!r}  gold_overlap={near}  ctx={ex.text[max(0, s.start - 25):s.end + 25]!r}")
    for fam in sorted(set(fns) | set(fps)):
        print(f"\n== {fam}: FN={len(fns[fam])} FP={len(fps[fam])}")
        for line in fns[fam][: a.limit]:
            print("  FN", line)
        for line in fps[fam][: a.limit]:
            print("  FP", line)


if __name__ == "__main__":
    main()
