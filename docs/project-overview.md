# TFL to SAP Traceability Agent

## Project goal

Given a table, figure, or listing (TFL) shell and its corresponding statistical analysis plan (SAP), help a reviewer find and verify the SAP passages that support each shell component. A reviewer can inspect the evidence, correct a proposed mapping, and export the resulting traceability matrix.

## Scope

- Use 6–8 matched document families from two-arm trials. Cover continuous-outcome summary tables, mean-by-visit figures, and simple subject-level endpoint listings.
- Trace titles, population labels, table rows and columns, figure axes, legends and error-bar definitions, listing columns and selection notes, and analysis footnotes. Carry population, endpoint, visit, treatment group, and surrounding labels into each mapping as applicable.
- Work with reporting specifications in unpopulated shells. The project excludes patient-level analysis, shell generation as a product feature, judging statistical method appropriateness, protocol auditing, and SAP amendment tracking. Constructed shells are permitted benchmark fixtures and carry that provenance label.

## Evidence and review rules

- A trial, its SAP versions, shells, and constructed variants belong to one partition. Freeze the development and held-out split before agent development. Keep reference annotations outside the materials available to the agent in every run.
- Evidence must apply to the component's analysis context. Several passages may be required, such as a population definition and the endpoint method that applies it. Record exact quotations with SAP version, section, and page. Check endpoint-specific exceptions and accept equivalent valid passages during scoring.
- Use four statuses. **Supported** means the evidence covers the applicable specification. **Partially supported** means some evidence applies and a required element is missing. **Not found in the supplied SAP** records the absence of located support in that version. **Needs review** captures unresolved ambiguity, contradictions, or competing interpretations.
- Record approved display conventions separately from SAP evidence. Reviewers can accept, correct, or reject mappings. Preserve the agent's proposal and the review outcome so both can be evaluated.

## Build sequence

| Step | Guide | What it delivers |
| --- | --- | --- |
| 1 | [Source collection and provenance](build/01-source-collection.md) | Matched document families and a frozen partition manifest |
| 2 | [Benchmark and traceability schema](build/02-benchmark-and-schema.md) | Stable component inventory, reviewed reference annotations, and shared record schema |
| 3 | [Traceability agent](build/03-traceability-agent.md) | One agent that parses shells, retrieves SAP passages, and verifies contextual support |
| 4 | [Reviewer interface and export](build/04-reviewer-interface.md) | Selectable components, a source panel, review actions, and an exportable matrix |
| 5 | [Evaluation and release](build/05-evaluation-and-release.md) | Held-out comparisons, evaluation report, reproducible package, and demo |

Use one development family to calibrate annotation and then build a working path from shell parsing through reviewer export. Expand to all three shell types on development data before running the held-out evaluation.

The project proposal defines requirements, and the planning slides capture the team's initial approach. [Project proposal](03_TFL_Component_to_SAP_Traceability_Agent.docx) · [Planning slides](TFL_SAP_Traceability_Agent_Planning_Present.pdf)
