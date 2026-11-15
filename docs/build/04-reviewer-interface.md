# Reviewer Interface and Export

[Project overview](../project-overview.md) · [Previous step](03-traceability-agent.md) · [Next step](05-evaluation-and-release.md)

**Input** — Parsed shells and schema-validated agent mappings.

## Run the reviewer interface

The interface is a local web page served from the loopback address. It needs a run file and a path for saved decisions. Add `--family` and `--pdf` to let the reviewer search the whole paired SAP for a passage that retrieval missed.

```sh
python3 -m traceability.reviewer_app \
  --run runs/pdf-run.jsonl --reviews runs/reviews.jsonl \
  --family NCT03469934 --pdf /path/to/SAP_001.pdf --ocr
```

Open the printed address. Pick a shell, then a component. The middle pane shows the component in context, the agent's status, rationale, open questions, and any display convention, and the linked quotations with SAP version, section, and page. The right pane shows the candidate passages with linked quotations highlighted.

- **Accept** keeps the proposal. **Reject** discards it. **Back to pending** withdraws a decision.
- **Correct** opens a replacement assessment. Select the exact words in a passage and press **Cite selected text** to link them. The server checks each quotation against the passage text and applies the schema's status rules before saving.

The middle pane can also show the shell page itself, for shells that sit on one page of the supplied PDF, and the searches the agent ran. The header filters the list by status and decision. `j` and `k` move through the list, `a` accepts, `c` starts a correction, and `x` rejects.

Decisions append to the reviews file as schema-valid `review` records. The latest record for a mapping is its current decision and earlier records stay in the file, so the original proposal and every change remain measurable. A sidecar `<reviews>.timing.jsonl` logs when a component was opened and how long the reviewer spent before saving, for the reviewer-effort measurement in Step 5.

Export from the page header or from the command line.

```sh
python3 -m traceability.review export \
  --run runs/pdf-run.jsonl --reviews runs/reviews.jsonl --format csv > runs/traceability-matrix.csv
```

The CSV has one row per component and standing quotation, so each quotation keeps its own section and page. The `final_*` columns hold only what stands after a reviewer accepted or corrected the mapping. For a pending or rejected mapping they are empty. The agent's proposal is always in the `proposed_*` columns, so unreviewed or rejected evidence cannot be read as approved. The JSON export nests the component, the proposal, the review record, and the assessment that stands after review.

A passage the reviewer finds by search and cites is saved to `<reviews>.passages.jsonl` with its SAP ID and version. It is reloaded when the application restarts, shown again beside the correction, and used when the corrected assessment is scored. A saved passage from a different SAP version is refused.

### Review with and without proposals

For the reviewer-effort study, build a crossover plan and start the interface once per reviewer, each with their own reviews file.

```sh
python3 benchmark/crossover_plan.py --run runs/agent-run.jsonl --reviewers R1 R2 \
  --per-reviewer 24 --seed 7 > runs/crossover-plan.json

python3 -m traceability.reviewer_app --run runs/agent-run.jsonl --reviews runs/reviews-R1.jsonl \
  --family NCT03469934 --pdf /path/to/SAP_001.pdf --ocr --plan runs/crossover-plan.json --reviewer R1
```

Each reviewer sees only their assigned components, in a shuffled order. For half of them the server withholds the agent's status, rationale, evidence, and candidates, and the reviewer searches the SAP and records their own assessment. The halves swap between the two reviewers. The timing file records the reviewer and the condition with each decision.

The page was exercised in a headless browser on the authentic ANB020-004 run: accept, a correction with a cited quotation, a refused correction with no open question, SAP search, reject, reload, export, the plan mode, and the shell page image. The whole workflow was also run by script through the interface on ANB020-004: a correction citing a searched passage, a restart, export, and scoring of the corrected assessment. Team members have yet to review a full shell with it.

## What to build

1. Build a lightweight reviewer interface in the format agreed with the TA. Let a reviewer pick a shell and select a component using its location and label in context.
2. Show the component's analysis context, status, rationale, and unresolved questions alongside its SAP quotations, document version, section, and page. Display all required passages and identify any approved display convention.
3. Support **accept**, **correct**, and **reject**. Let reviewers amend linked passages, status, and rationale, or leave an unresolved question. Persist review actions and preserve the original proposal so corrections can be measured later.
4. Export a traceability matrix that joins component IDs, source locations, context, evidence, statuses, rationale, decisions, and unresolved questions. Preserve the association between every quotation and its location when a component has several passages.

## Done when

A reviewer can inspect and act on one development shell end to end. The saved actions survive reopening, and the exported matrix includes accepted, corrected, rejected, and pending mappings with their corresponding evidence and open questions.
