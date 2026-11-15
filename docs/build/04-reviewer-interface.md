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

Decisions append to the reviews file as schema-valid `review` records. The latest record for a mapping is its current decision and earlier records stay in the file, so the original proposal and every change remain measurable. A sidecar `<reviews>.timing.jsonl` logs when a component was opened and how long the reviewer spent before saving, for the reviewer-effort measurement in Step 5.

Export from the page header or from the command line.

```sh
python3 -m traceability.review export \
  --run runs/pdf-run.jsonl --reviews runs/reviews.jsonl --format csv > runs/traceability-matrix.csv
```

The CSV has one row per component and quotation, so each quotation keeps its own section and page. `final_status` is filled only for accepted and corrected mappings. The JSON export nests the component, the proposal, the review record, and the assessment that stands after review.

The page was exercised in a headless browser on the authentic ANB020-004 run: accept, a correction with a cited quotation, a refused correction with no open question, SAP search, reject, reload, and export. Team members have yet to review a full shell with it.

## What to build

1. Build a lightweight reviewer interface in the format agreed with the TA. Let a reviewer pick a shell and select a component using its location and label in context.
2. Show the component's analysis context, status, rationale, and unresolved questions alongside its SAP quotations, document version, section, and page. Display all required passages and identify any approved display convention.
3. Support **accept**, **correct**, and **reject**. Let reviewers amend linked passages, status, and rationale, or leave an unresolved question. Persist review actions and preserve the original proposal so corrections can be measured later.
4. Export a traceability matrix that joins component IDs, source locations, context, evidence, statuses, rationale, decisions, and unresolved questions. Preserve the association between every quotation and its location when a component has several passages.

## Done when

A reviewer can inspect and act on one development shell end to end. The saved actions survive reopening, and the exported matrix includes accepted, corrected, rejected, and pending mappings with their corresponding evidence and open questions.
