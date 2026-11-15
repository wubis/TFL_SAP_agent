# Browser check of the reviewer workflow

`reviewer_workflow.js` drives the reviewer page in a real browser on the ANB020-004 development family. It needs Node, Playwright, the original ANB020-004 PDF, and a 64-component run file for that family. It is not part of `pytest`.

```sh
python3 -m traceability.retrieval --family NCT03469934 --pdf SAP_001.pdf \
  --components benchmark/development/NCT03469934/components.jsonl > runs/anb-retrieval.jsonl
python3 -m traceability.mapping --results runs/anb-retrieval.jsonl > runs/anb-mappings.jsonl
python3 -m traceability.review bundle --components benchmark/development/NCT03469934/components.jsonl \
  --results runs/anb-retrieval.jsonl --mappings runs/anb-mappings.jsonl > runs/anb-run.jsonl

# Phase 1: start the app, then make two corrections, one acceptance, and one rejection.
python3 -m traceability.reviewer_app --run runs/anb-run.jsonl --reviews runs/browser-reviews.jsonl \
  --family NCT03469934 --pdf SAP_001.pdf --port 8768 &
node tests/browser/reviewer_workflow.js correct http://127.0.0.1:8768 runs

# Phase 2: stop the app, start it again with the same files, then verify and export.
node tests/browser/reviewer_workflow.js verify http://127.0.0.1:8768 runs

python3 benchmark/score_development_mappings.py --family NCT03469934 \
  --run runs/anb-run.jsonl --reviews runs/browser-reviews.jsonl
```

Phase 1 corrects the table's population label with two candidate passages and the listing's population label with a passage found by search. Phase 2 checks, after a restart, that the decisions, the correction, and the searched passage are all shown again, and downloads the matrix.

Result on November 15, 2026: both phases passed with no page errors. The exported matrix had 65 rows. Scoring the reviewed assessments gave 3 links, 2 matched to reference anchors, 0 unverified, and 1 component with complete evidence, against 0 links before review.
