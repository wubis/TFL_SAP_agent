# Demo Walkthrough

[Project overview](project-overview.md) · [Reviewer interface](build/04-reviewer-interface.md)

This walkthrough traces one component from the shell to the exported matrix, using the development calibration family ANB020-004. It takes about five minutes to present.

## Before the demo

Download the ANB020-004 statistical methods bundle linked in the [source manifest](../data/source-manifest.json) and install the tools in [README](../README.md). Then produce a run file. With an API key, use the agent:

```sh
python3 -m traceability.dev_shells --family NCT03469934 --pdf SAP_001.pdf > runs/anb-components.jsonl

python3 -m traceability.agent --family NCT03469934 --pdf SAP_001.pdf --ocr \
  --components runs/anb-components.jsonl --log runs/agent-log.jsonl > runs/agent-run.jsonl
```

Without a key, the pipeline still parses and retrieves, and every mapping starts as needs review:

```sh
python3 -m traceability.shell_pipeline --pdf SAP_001.pdf --pdf-shells --ocr > runs/agent-run.jsonl
```

Start the reviewer interface and open the printed address.

```sh
python3 -m traceability.reviewer_app --run runs/agent-run.jsonl --reviews runs/reviews.jsonl \
  --family NCT03469934 --pdf SAP_001.pdf --ocr
```

## Steps to show

1. **The shell and its components.** Pick the FEV1 summary table in the shell menu. The left pane lists every component the parser found: the title, the population label, each column and row label, and the footnotes.
2. **One component in context.** Select the population label, Full Analysis Set. The middle pane shows what the label inherits: the endpoint, the treatment groups, and the shell and SAP versions.
3. **The evidence.** The right pane shows candidate SAP passages with section and page. Two passages matter here. Section 5.3 defines the Full Analysis Set. Section 17.2.1.1 applies it to the secondary efficacy endpoints, which include FEV1. The label needs both.
4. **A relevant mention that is not support.** Point to the Safety Analysis Set passage among the candidates. It uses similar words for a different population.
5. **A review action.** If the proposal cites both passages, accept it. Otherwise press Correct, select the exact words in each passage, press Cite selected text, set the status, and save. Show that a correction with a status of partially supported is refused until an open question is written.
6. **A component with no SAP support.** Select the `Predicted FEV1 (L)` listing column. Show a search of the whole SAP from the right pane, and that not found in the supplied SAP records an absence, with no claim that the shell is wrong.
7. **Reopen.** Reload the page. The decisions are still there.
8. **Export.** Press Export matrix (CSV). Open the file and show one row per quotation, each with its own section and page, the proposed status, the decision, and the status that stands after review.

## Points to state while presenting

- Code parses, retrieves, and checks every quotation. The model chooses what to look up and judges whether a passage applies. A person makes the final decision.
- The agent stops after a fixed number of lookups and attempts and hands the component to the reviewer.
- Reference annotations are never shown to the agent. They are used only for scoring.
- State which results are measured and which are pending, as listed in the [evaluation report](evaluation-report.md).
