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

## Check the live API first

Before any model-backed evaluation run, make a few real calls and check what comes back. Set `ANTHROPIC_API_KEY` and a spending cap.

```sh
python3 benchmark/live_check.py --family NCT03469934 --pdf /path/to/SAP_001.pdf --ocr --limit 3 --max-usd 2
```

It runs the agent, the LLM baseline, and the assessor on the first components of a development family and prints one line per check: the commands finish, there is a valid record per component, settings are recorded, the requested model served every call, every cited quotation is in the passage it cites, and prompts and token usage are logged. It has not been run yet.

## Run the evaluation

`benchmark/evaluate.py` scores every system's saved runs for one partition and writes a JSON file and a Markdown report with pooled, per-shell-type, and per-family results.

```sh
python3 benchmark/evaluate.py --partition development \
  --retrieval bm25:NCT03469934:runs/bm25-NCT03469934.jsonl \
  --run agent:NCT03469934:runs/agent-NCT03469934.jsonl \
  --run llm-baseline:NCT03469934:runs/baseline-NCT03469934.jsonl \
  --out-json runs/evaluation.json --out-md runs/evaluation.md
```

Every run command writes its settings and a fingerprint of the protected code beside its results, and the report lists them.

### Adjudicate unmatched links

```sh
python3 benchmark/adjudication.py export --partition development \
  --run agent:NCT03469934:runs/agent-NCT03469934.jsonl \
  --run llm_baseline:NCT03469934:runs/baseline-NCT03469934.jsonl \
  --items runs/adjudication-items.csv --key runs/adjudication-key.json

python3 benchmark/adjudication.py apply --items runs/adjudication-items.csv --key runs/adjudication-key.json
```

Give the adjudicator the items file only. They built none of the systems and do not see which system proposed a link. They rule equivalent, unsupported, or unsure, with a reason. A second person rules on unsure rows. Run this on development runs first, then once on held-out runs after the freeze.

### Reviewer effort

`benchmark/reviewer_effort.py --run <run> --reviews <reviews>` summarizes a review session: decisions by action, corrections to proposals, status changes, links added and removed, and minutes per component, split by condition when a [crossover plan](04-reviewer-interface.md#review-with-and-without-proposals) was used. `benchmark/coverage_report.py` counts what the development records cover.

### Freeze and run the held-out evaluation

One person does this once.

```sh
python3 benchmark/freeze_config.py --date 2026-12-01
git add benchmark/frozen-config-2026-12-01.json
git commit -m "Freeze evaluation configuration"
git tag evaluation-freeze-2026-12-01
```

Sign off every family's annotations before the freeze with `python3 benchmark/sign_off.py --family <id> --reviewer <name> --date <date>`. `--status` lists the families still open. The dates here are examples. The team sets the real ones.

Produce one run per system for every held-out family from the tagged commit, using the frozen settings and the system names in the frozen file (`keyword_search`, `llm_baseline`, `agent`). Then pass every run and every held-out SAP PDF to the runner:

```sh
python3 benchmark/evaluate.py --partition held_out \
  --frozen-config benchmark/frozen-config-2026-12-01.json \
  --run agent:<family>:<run file> --run llm_baseline:<family>:<run file> \
  --retrieval keyword_search:<family>:<results file> \
  --pdf <family>:<SAP PDF> \
  --out-json runs/held-out.json --out-md runs/held-out.md
```

Before any held-out reference is opened, the runner checks all of the following and lists every problem it finds:

- The frozen file is `benchmark/frozen-config-<date>.json` in this repository, committed, and never edited since it was first committed.
- The protected files have the same content as at the freeze, with no uncommitted change, and the current commit is tagged. Protected files are the `traceability` package, the schema, every script and record under `benchmark` including the reference annotations, the manifest, and `requirements.txt`. Documentation is not protected.
- Every held-out family's annotations are signed off by someone other than the annotator.
- Runs were given for exactly the systems the frozen file names, one per held-out family.
- Each run file's recorded model, effort, limits, retrieval, OCR setting, and code fingerprint equal the frozen ones, the run was not limited to a subset, and the frozen model served every call.
- Each run covers exactly the components in the family's inventory.
- A SAP PDF was supplied for every family, and the output paths can be written.

It then writes `benchmark/final-evaluation-record.json` with status `started`, opens the references, and updates the record to `completed` with the full results, or to `failed after references were opened`. In either case it will not run again while the record exists, and a rerun is a team decision. A failure message names no held-out component.

With `--pdf`, quotations are checked against the SAP page text, and passage text is rebuilt from the SAP, so nothing a run file or a reviewer's saved passage claims is taken on trust. `benchmark/score_development_mappings.py` takes the same option. Held-out links can be exported for adjudication only after the record shows `completed`.

These checks guard against mistakes. They cannot stop someone who edits the checks themselves, so the tagged commit and the record are the audit trail.

The current development results, and what is still unmeasured, are in the [evaluation report draft](../evaluation-report.md). Limits are in [known limitations](../limitations.md). The [demo walkthrough](../demo.md) traces one component through review and export.

## What to build

1. Build a reproducible evaluation runner. Freeze the agent configuration and scoring rules after development. Run keyword search and a general-purpose LLM as baselines using the same source materials and equivalent inputs for each comparison.
2. Evaluate component identification separately, then measure retrieval on reference components and run the full parsing-to-linking workflow. Accept equivalent valid spans and track whether all required passages were found. Report results separately for tables, figures, and listings.
3. Report retrieval recall at k, link precision and recall, complete multi-passage support, citation accuracy, support-status accuracy, unsupported-link rate, and correct abstention. Use the challenge cases to explain where the agent confuses analysis contexts, misses exceptions, or mishandles conventions.
4. Measure reviewer time, corrections, and unsupported links remaining after review. Record the review conditions and sample sizes so the comparison can be interpreted.
5. Package the prototype, schema, example matrix, annotated benchmark and guides, partition manifest, permitted source documents or provenance, pinned dependencies, run instructions, and evaluation report. Prepare a demo that traces one component through evidence inspection, a review action, and export.

## Done when

A teammate can reproduce the held-out runs and generate an example export from the documented commands. The final report includes baseline comparisons, results by shell type, reviewer effort, failure examples, and known limitations.
