# Benchmarks

`buffbench` runs the same analyzer that ships in the image over public and own
datasets and writes one JSON per (detector, dataset) into `results/raw/`;
`report` folds them into `results/RESULTS.md`.

```sh
make bench-venv                      # once: venv, CPU torch, spaCy models
make bench                           # rules + spacy-lg on all datasets
make bench DETECTORS=rubert-redmadrobot,gliner-guard-omni
make bench-report
```

## Datasets

| name | lang | source | licence | note |
|---|---|---|---|---|
| pii-bench | ru | hivetrace/pii-bench | Apache-2.0, eval only | 13 types, valid checksums, 9 domains |
| jayguard | ru | just-ai/jayguard-ner-benchmark | MIT / Apache-2.0 (card conflicts) | noisy chats, names and addresses only |
| redmadrobot | ru | redmadrobot-rnd/pii_benchmark | MIT | 21 types incl. ОМС, driver licence |
| synthetic-ru | ru | `buffbench/synthetic.py` | own | Faker + checksum-valid IDs, hard negatives; generated from seed |
| secrets | — | `buffbench/synthetic.py` | own | gitleaks-style key formats + look-alike negatives |

## Metrics

Labels of every dataset and detector are mapped to one family
(`buffbench/types.py`); a dataset is scored only on the families it annotates.

- **exact F1** — span must match after trimming punctuation and merging adjacent
  same-family spans (so `Иван` + `Петров` vs `Иван Петров` is one match).
- **char F1** — character-level overlap per family (fair for addresses, where
  datasets disagree on span boundaries).
- **leak** — share of annotated PII characters the detector left unmasked
  (what actually reaches the model).
- **overmask** — share of masked characters that were not PII.
- **p50 / p95 ms** — analyzer latency per text on CPU (`threads` = cores).

## Caveats

- **jayguard** labels people and addresses selectively (a surname only, names in
  LLM-generated passages left unlabeled), so its precision/overmask is not a
  judgement on the detector; read its **leak** (recall) only.
- **redmadrobot** carries tokenisation artefacts (`ivanov @ ya . ru`, `+ 7 ( 812 )`)
  and identifiers with invalid checksums; shapes with a context word are still masked.
- Heavy detectors run on a seeded 200-row sample per dataset (`--sample 200`),
  rules and spaCy on the full sets. Latency is per text on an 8-core CPU of a
  shared host; the pii-bench p50 of rules, spaCy, ruBERT and DistilBERT comes from
  a quiet re-run, the GLiNER/nemotron figures were taken under load and are upper
  bounds.
