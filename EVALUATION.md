# Evaluation

The original blueprint describes a fixed task set, SQL correctness checks, and
judge-based summary scoring. This repository includes the scaffolding for that
workflow and the local workflow engine needed to run it.

Suggested local checks:

1. `pytest`
2. `POST /v1/run` for a refund anomaly question
3. `POST /v1/run` for a write request, then `POST /v1/approve`

