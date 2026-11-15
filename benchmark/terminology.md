# Terminology Guide

[Annotation guide](annotation-guide.md) · [Display conventions](display-conventions.json) · [Record schema](../schemas/traceability.schema.json)

This guide fixes the words the team uses in annotations, prompts, the reviewer interface, and the report. The annotation guide says how to apply them. Trial-specific abbreviations are in the annotation guide's terminology table. Confirm each trial's own definitions in its SAP.

## Documents

| Term | Meaning in this project |
| --- | --- |
| Statistical analysis plan (SAP) | The document, written before unblinding, that fixes the analysis populations, endpoints, statistical methods, and how results are presented. Each SAP is identified by document ID, version, and date in the source manifest. |
| Table, figure, or listing (TFL) | An output that reports a trial. A table summarizes, a figure plots, a listing shows subject-level rows. |
| Shell | A TFL with its full layout and no results. It specifies what will be shown. Also called a mock or dummy table. |
| Authentic shell | A shell published with, or for, a real SAP. |
| Constructed shell | A shell the team wrote against a real SAP to exercise a case. Its provenance label is `constructed` and results on it are reported apart from authentic shells. |
| Document family | One trial's SAP, the shells written for it, and any constructed variants. A family belongs to exactly one partition. |
| Partition | `development` or `held_out`. Development families are used to build and tune. Held-out families are used once, for the final evaluation. |

## Shell components

A component is the smallest selectable unit of a shell that carries a reporting specification. Data cells and decorative marks are not components.

| Kind | What it is |
| --- | --- |
| `title` | The shell's title or caption. |
| `population_label` | The analysis set named in the title or header. |
| `table_row` | A row label, including a statistic label such as `n` or `Mean (SD)` and a block heading such as a visit. |
| `table_column` | A column header, including a treatment arm header and a sub-column. |
| `figure_axis` | An axis caption with its unit. |
| `figure_legend` | A legend entry. |
| `figure_error_bar` | The definition of the uncertainty shown, such as a 95% confidence interval. |
| `listing_column` | A listing column header. |
| `listing_selection_note` | A note that says which records the listing includes. |
| `footnote` | An analysis footnote or programming note. |

**Context** is what a component inherits from its surroundings: population, endpoint, visit, treatment groups, and nearby labels. A label such as `n` or `Baseline` has no meaning without it. Two components with the same label under different rows, columns, or visits are different components.

**Locator** says where the exact instance sits in the shell. **Component ID** is stable across parsing runs and annotation edits.

## Evidence

| Term | Meaning in this project |
| --- | --- |
| Passage | A stretch of SAP text with its document version, section, and page. |
| Quotation | Words copied exactly from a passage. Whitespace and line breaks may be normalized. Words, negation, punctuation, and units may not. |
| Anchor | The short exact quotation a reference annotation uses to identify a longer supporting passage. |
| Link | A proposed connection between a component and one quotation. |
| Relevant mention | A passage that uses the component's words under a different population, endpoint, visit, or analysis. It is not support. |
| Support | Evidence that applies to the component in its context. Several passages may be needed together, for example a population definition and the section that applies it to the endpoint. |
| Evidence group | In a reference annotation, one claim the evidence must establish. Every group must be covered. Inside a group, any one alternative is enough, and all passages in that alternative are required together. |
| Equivalent span | A different quotation that establishes the same claim as a reference anchor. Scoring accepts it after a blind human ruling. |
| Unverified link | A link whose quotation cannot be found in the passage it cites, or whose source passage was not saved. It never earns credit. |
| Display convention | A presentation rule the team has approved, recorded in the display convention list with its scope. It is never given a SAP citation. |
| Extraction method | `pdf_text` for a text layer, `ocr` for a scanned page. Check OCR quotations against the page image when a character affects the meaning. |

## Support statuses

The four statuses are spelled exactly as below in records. In prose they read supported, partially supported, not found in the supplied SAP, and needs review.

| Status | Meaning |
| --- | --- |
| `supported` | Applicable evidence covers the component in its context. |
| `partially_supported` | Evidence supports a material part of the component and a stated detail remains unsupported. The missing detail is written as an open question. |
| `not_found_in_supplied_sap` | A documented search of the supplied SAP version found no supporting passage. Evidence is empty. It records an absence. It is not a finding that the shell is wrong. A component that rests only on an approved display convention also takes this status, with the convention ID. |
| `needs_review` | Ambiguity, contradiction, or competing readings prevent a reliable determination. Both readings and a question for the reviewer are recorded. An agent that reaches its limits without a verifiable answer also returns this status. |

## Review

| Term | Meaning in this project |
| --- | --- |
| Mapping | One proposed assessment of a component against a specific SAP: status, rationale, evidence, conventions, open questions. |
| Review decision | `accept` keeps the proposal. `correct` replaces it with the reviewer's assessment. `reject` discards it. `pending` means no decision. The proposal is always kept so corrections can be measured. |
| Traceability matrix | The export that joins each component, its context, the evidence that stands after review, the status, the rationale, the decision, and open questions. |
| Reference annotation | The benchmark answer for a component. It is used only for scoring and is never shown to a system under evaluation. |
| Abstention | Returning `not_found_in_supplied_sap` or `needs_review` with no link when the SAP lacks the information. |
