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

## Secrets and passwords (#740)

A separate family of runs: every dataset below scores only `SECRET`, and the
detectors are the shipped regexes, a regex extension and third-party models,
alone (`<name>`) or on top of the regexes (`rules+<name>`). Run with
`./run_secrets.sh` (one process per detector) and fold with `make bench-report`.

| name | lang | source | licence | what it is |
|---|---|---|---|---|
| agent-real | en | nvidia/Open-SWE-Traces (Claude Code, OpenHands, opencode harnesses) + nebius/SWE-agent-trajectories | CC BY 4.0 | tool outputs of real agent runs on real repos, **labelled by us** (`data/agent-real.jsonl`): every candidate a union of detectors flagged was reviewed, plus unflagged chunks as negatives |
| creddata | en | Samsung/CredData | Apache-2.0 + per-repo | labelled lines of real repositories, the standard credential-scanner benchmark; only the 221 repos outside the cbx training list; UUID rows ignored |
| creddata-files | en | Samsung/CredData | same | the same lines as an agent reads them: 15-line file windows |
| issue-reports | en | zenodo.org/records/17430336 | CC BY 4.0 | manually labelled candidates in GitHub issue texts (±400 chars) |
| aparte | en/fr | apartejs/aparte-secrets-data | ODC-BY | synthetic chat phrases, configs, JSON, HTTP, negatives |
| gravitee-pw | en | gravitee-io/pii-detection-dataset | Apache-2.0 | PASSWORD spans in prose / JSON / XML + as many rows without |
| pii-bench-secret | ru | hivetrace/pii-bench | Apache-2.0, eval only | TOKEN rows + as many without |
| secrets | en | `synthetic.py` | own | provider key formats + look-alikes |
| secrets-ru | ru | `synthetic_secrets.py` | own | Russian phrases, `.env`, compose, JSON, code, CLI with human passwords |
| agent-runs | ru/en | `synthetic_agent.py` | own | synthetic tool-output blocks (`cat .env`, diffs, logs, k8s secrets) |

Fetching the sets that are not on Hugging Face (once, into `.cache/`):

```sh
git clone --depth 1 https://github.com/Samsung/CredData .cache/creddata-src \
  && (cd .cache/creddata-src && python download_data.py --jobs 6) \
  && mkdir -p .cache/creddata && mv .cache/creddata-src/{data,meta,snapshot.json} .cache/creddata/
# test split = repos outside CobuildX-AI/cbx-secrets-detector-32M/training_data_sources.csv → .cache/creddata/test_repos_crc.json
curl -L -o /tmp/issues.zip 'https://zenodo.org/records/17430336/files/Secret-Leak-Detection-Issue-Report.zip?download=1' \
  && unzip -j /tmp/issues.zip '*/Data/test.csv' '*/Data/test_wild.csv' -d .cache/issue-reports
```

**agent-real labelling.** 124 117 tool-output chunks (≤1500 chars) were pulled from four trajectory
sets (Claude Code / OpenHands / opencode harnesses of Open-SWE-Traces, nebius SWE-agent); a seeded
24 000 of them went through a union of detectors at low thresholds (bardsai 0.2, cbx, CredSweeper,
shipped + extended regexes). Every chunk with a model or shipped-regex hit (420) plus 150 chunks with
only extended-regex hits were reviewed candidate by candidate; 600 unflagged chunks are negatives.
A value is a secret when it plays a credential role (password, token, key, private key, URL
userinfo) and is not an obvious placeholder, spec example, keyboard mash or dictionary word
(`your-client-secret`, RFC 6749 tokens, `sdfkjh345`, `password`); identifiers (UUID, ULID, client
id, OAuth `state`), hashes, public constants and encrypted Travis blobs are not. Realistic test
credentials count (CredData convention). Result: 1170 chunks, 13 with secrets, 22 gold spans — real
agent output is almost all noise, so this set mostly measures over-masking.

### Results (2026-11-02, 1500-row seeded samples; exact-span F1 per set, averages over the 8 labelled sets)

"clean 5" averages creddata, creddata-files, aparte, pii-bench and secrets — the sets nobody looked at
while writing the v2 regexes; gravitee-pw and agent-real supplied the misses v2 was written from, and
secrets-ru / agent-runs are our own synthetic sets, so the gain of v2 over v1 shows only there.

| detector | creddata | creddata-files | aparte | gravitee-pw | pii-bench ru | secrets | secrets-ru | agent-runs | avg F1 | clean 5 | avg leak | avg overmask | agent-real: found of 22 / false spans |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| regexes before #740 (`rules-secret` in old raw files) | 0.59 | 0.58 | 0.56 | 0.12 | 0.93 | 1.00 | 0.57 | 0.75 | 0.638 | 0.732 | 0.304 | 0.178 | 13 / 426 |
| regexes v2 = shipped `rules` mode (`rules-ext2`) | 0.48 | 0.55 | 0.60 | 0.69 | 0.95 | 1.00 | 0.91 | 0.88 | 0.757 | 0.714 | 0.138 | 0.173 | 17 / 573 |
| bardsai | 0.84 | 0.86 | 0.70 | 0.48 | 0.24 | 0.98 | 0.77 | 0.89 | 0.721 | 0.725 | 0.236 | 0.124 | 8 / 74 |
| CredSweeper* | 0.94 | 0.96 | 0.61 | 0.30 | 0.16 | 0.74 | 0.53 | 0.58 | 0.603 | — | 0.413 | 0.135 | 12 / 97 |
| cbx-32M | 0.71 | 0.49 | 0.50 | 0.46 | 0.31 | 0.75 | 0.60 | 0.62 | 0.557 | — | 0.200 | 0.164 | 7 / 181 |
| old regexes + bardsai (union) | 0.64 | 0.70 | 0.70 | 0.45 | 0.93 | 1.00 | 0.78 | 0.84 | 0.754 | — | 0.138 | 0.196 | 18 / 483 |
| cascade v1 (old regexes + ext v1 → bardsai) | 0.83 | 0.80 | 0.69 | 0.50 | 0.93 | 0.99 | 0.90 | 0.95 | 0.825 | 0.851 | 0.119 | 0.136 | 12 / 91 |
| cascade v1, judge only | 0.85 | 0.80 | 0.60 | 0.37 | 0.93 | 1.00 | 0.92 | 0.95 | 0.802 | 0.835 | 0.183 | 0.050 | 10 / 61 |
| **cascade v2 = shipped `cascade` mode** (`cascade2-bardsai`, `product-cascade`) | 0.81 | 0.81 | 0.71 | 0.82 | 0.94 | 0.99 | 0.89 | 0.95 | **0.867** | **0.853** | **0.078** | 0.112 | **17 / 90** |
| cascade v2, judge only = shipped `cascade-strict` (`product-cascade-strict`) | 0.81 | 0.78 | 0.61 | 0.78 | 0.94 | 1.00 | 0.92 | 0.95 | 0.849 | 0.829 | 0.146 | **0.035** | 15 / 59 |
| GLiNER2-Guardrails (4 short sets, 150 rows) | 0.24 | — | — | — | 0.67 | — | 0.55 | 0.42 | 0.470 | — | 0.194 | 0.417 | 2 / 2618 |
| openai/privacy-filter (4 short sets) | 0.44 | — | — | — | 0.90 | — | 0.60 | 0.44 | 0.593 | — | 0.088 | 0.214 | 2 / 72 |

\* trained on all of CredData. Full table with every variant (thresholds, cbx cascades, unions):
`results/RESULTS.md`; raw JSON per (detector, dataset) in `results/raw/`. issue-reports is omitted
from the table — its labels mark one candidate per text, so only recall is meaningful there and it is
0.25–0.32 for every detector. Since the move into the product, `rules-secret` runs the shipped
regexes *with* the v2 password patterns (the old `rules-ext2` numbers); the pre-#740 regexes are
only in the old raw files.

Quiet-host latency (p50, 8-core CPU, torch at 4 threads): cascade v2 8 ms on a chat line, 19 ms on a
tool-output block, 29 ms on a 15-line file window, 57 ms on a 1500-char agent chunk — 3–6 ms above the
shipped regexes. GLiNER2 needs 200–1300 ms and 6 GB; privacy-filter 200–2000 ms and 3 GB.

What the numbers say:

- The pre-#740 regexes leave 30 % of secret characters unmasked and put 426 false spans into 1170
  real agent tool outputs; `assignment_secret` and `opaque_blob` produce 95 % of that noise.
- bardsai (0.7 MB byte CNN, Apache-2.0) is the best single detector on code but blind to Russian
  (pii-bench 0.24) and to private-key formats; regexes are the opposite. A plain union inherits the
  regex noise; the cascade keeps the regex hits it is sure about (provider formats, Russian context,
  v2 patterns) and lets bardsai judge the rest, which halves the leak and keeps the noise at the
  model's level. cbx, CredSweeper, GLiNER2 and privacy-filter lose in every role.
- Remaining cascade v2 misses on agent-real: `POSTGRES_PASSWORD=pipestat-password` (the value
  contains the placeholder word `password`) and `assert url["PASSWORD"] == "…"`. Its false spans are
  mostly dummy credentials in credential position (`password="thisiswrong"`, RFC example tokens) and
  ULIDs from the model.
- Presidio compiles patterns with IGNORECASE: `[A-Z]` in a value rule matches any letter. v2
  (`buff_guardrails.passwords`) passes `global_regex_flags` and scopes `(?i:)` to key names; the
  provider-format recognizer (`buff_guardrails.secrets`) still runs insensitive.
- Shipped as `GUARDRAILS_SECRETS`: `cascade` (v2, default), `cascade-strict` (judge only), `rules`
  (regexes v2), `none` (provider formats only).

Fairness: CredSweeper was trained on all of CredData (random 15 % row split), so
its CredData numbers are not held out; cbx and bardsai report their own held-out
repos, we use the cbx list. None of the models saw our own sets or agent-real.

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
