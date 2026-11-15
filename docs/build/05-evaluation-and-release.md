# Evaluation and Release

[Project overview](../project-overview.md) · [Previous step](04-reviewer-interface.md)

**Input** — The frozen family split, reviewed reference set, working agent, and reviewer interface.

## Run the baselines on development data

**Keyword search.** The BM25 retrieval in [Step 3](03-traceability-agent.md#run-the-retrieval-baseline) is the keyword baseline. Score it with `benchmark/score_development_retrieval.py`. It ranks passages and assigns no status.

**General-purpose LLM.** `traceability.llm_baseline` makes one model call per component. The model gets the same selected SAP pages the agent indexes, as one document with page markers, plus the component and any display conventions. It has no retrieval step, no quote check before its answer is accepted, and no retry. Install `anthropic` and set `ANTHROPIC_API_KEY`.

```sh
python3 -m traceability.llm_baseline \
  --family NCT03469934 --pdf /path/to/SAP_001.pdf --ocr \
  --components benchmark/development/NCT03469934/components.jsonl \
  --log runs/baseline-log.jsonl --summary runs/baseline-summary.json > runs/baseline-run.jsonl

python3 benchmark/score_development_mappings.py \
  --family NCT03469934 --run runs/baseline-run.jsonl
```

Use `--limit 3` for a trial run before a full one. The SAP text sits in a cached system block, so calls after the first reuse it. `--log` records the model, full prompt, output, and token usage per call.

After each answer the command checks every quotation against the cited page and writes the result to the summary: verified on the cited page, found on another page, or not found. Quotations that fail stay in the record, flagged, so unsupported links can be counted. A verified quotation is placed in the agent's own passage window for that page, so the mapping scorer applies the same match rule to both systems. An answer that breaks the record rules, such as `supported` with no quotation, is recorded as `needs_review` and counted under `answers_rejected_by_record_rules`. The output is a run file, so the reviewer interface opens it as well.

Two differences from the agent's assessor matter when comparing. The baseline reads the whole SAP, so its instructions let it answer `not_found_in_supplied_sap` when it finds no supporting passage. The assessor sees only retrieved candidates and is told to keep that status for display conventions. The baseline also uses the same model and effort defaults as the assessor unless `--model` or `--effort` says otherwise. Record both settings with any reported comparison.

The baseline's parsing, citation checks, and run-file output are covered by tests with a stand-in client, and the citation check was exercised on the real ANB020-004 SAP text, including a scanned page. It has yet to run against the API, so there are no baseline results.

## What to build

1. Build a reproducible evaluation runner. Freeze the agent configuration and scoring rules after development. Run keyword search and a general-purpose LLM as baselines using the same source materials and equivalent inputs for each comparison.
2. Evaluate component identification separately, then measure retrieval on reference components and run the full parsing-to-linking workflow. Accept equivalent valid spans and track whether all required passages were found. Report results separately for tables, figures, and listings.
3. Report retrieval recall at k, link precision and recall, complete multi-passage support, citation accuracy, support-status accuracy, unsupported-link rate, and correct abstention. Use the challenge cases to explain where the agent confuses analysis contexts, misses exceptions, or mishandles conventions.
4. Measure reviewer time, corrections, and unsupported links remaining after review. Record the review conditions and sample sizes so the comparison can be interpreted.
5. Package the prototype, schema, example matrix, annotated benchmark and guides, partition manifest, permitted source documents or provenance, pinned dependencies, run instructions, and evaluation report. Prepare a demo that traces one component through evidence inspection, a review action, and export.

## Done when

A teammate can reproduce the held-out runs and generate an example export from the documented commands. The final report includes baseline comparisons, results by shell type, reviewer effort, failure examples, and known limitations.
