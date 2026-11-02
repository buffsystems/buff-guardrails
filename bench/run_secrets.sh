#!/usr/bin/env bash
# Secret-detection bench: one process per detector (torch / onnxruntime / spaCy in
# one process oversubscribe the CPU), light detectors on a 1500-row seeded sample
# per dataset, the two heavy models on 300 rows. Raw JSON → results/raw/, then
# `make bench-report`.
set -euo pipefail
cd "$(dirname "$0")"
export HF_HOME="$PWD/.cache/hf"
# `${VAR-default}`: an exported empty value means "none", only an unset variable takes the default.
DATASETS=${DATASETS-agent-real,creddata-files,creddata,issue-reports,aparte,gravitee-pw,pii-bench-secret,secrets,secrets-ru,agent-runs}
LIGHT=${LIGHT-rules-secret,rules-ext,bardsai,rules+bardsai,rules-ext+bardsai,credsweeper,rules+credsweeper,cbx-32m,rules+cbx-32m,rules-ext+cbx-32m,cbx-17m}
HEAVY=${HEAVY-gliner2-guardrails,rules+gliner2-guardrails,privacy-filter,rules+privacy-filter}
OUT=${OUT:-results/raw}
for d in ${LIGHT//,/ }; do
  .venv/bin/python -m buffbench.run run --detectors "$d" --datasets "$DATASETS" --sample "${SAMPLE:-1500}" --out "$OUT"
done
for d in ${HEAVY//,/ }; do
  .venv/bin/python -m buffbench.run run --detectors "$d" --datasets "$DATASETS" --sample "${HEAVY_SAMPLE:-300}" --out "$OUT"
done
