# TFL to SAP Annotation Guide

[Benchmark files](README.md) · [Record schema](../schemas/traceability.schema.json)

## Inventory the shell

1. Confirm the shell and SAP versions against the source manifest. Identify their page numbering before recording citations.
2. Capture the smallest selectable unit carrying a reporting specification, such as a title, population label, row or column label, axis, legend entry, uncertainty label, selection note, or footnote. Give it a stable ID and a locator pointing to the exact instance. Preserve the displayed wording and put inferred meaning in the analysis context or rationale.
3. Carry the enclosing endpoint, visit, population, treatment group, and nearby labels into the component. Use `null` for an unavailable scalar context field and an empty array for unavailable group or label lists. Keep data cells and decorative marks out of the inventory. Explicitly identify illustrative figure ticks and artwork so the team can decide which reporting specifications they actually express.

## Assess SAP support

Search the paired SAP for definitions, general rules, endpoint methods, and relevant exceptions. Use the evidence section and the page printed within the SAP. Record the smallest exact span that supports the claim and expand it when a qualifier is necessary. A record can store a short exact `quote` with a `text_span` that identifies the complete passage in a reproducible page extraction. Normalize line breaks and incidental whitespace. Preserve words, negation, punctuation, and units. For text spanning pages, cite each contributing page as its own passage.

| Status | When to use it | Calibration example |
| --- | --- | --- |
| `supported` | Applicable evidence covers the component in context. | The FEV1 baseline footnote matches the endpoint-specific instruction in §17.2.1.1. |
| `partially_supported` | Evidence supports a material part of the component and a specified detail remains unsupported. | The illustrative time axis has support for nominal sampling time on a linear scale. Hours and the drawn tick schedule still need confirmation. |
| `not_found_in_supplied_sap` | A documented search yielded no passage supporting the component's claim. Leave `evidence` empty. | The `Predicted FEV1 (L)` listing column requires a predicted measurement. Generic guidance about observed FEV1 does not establish that field. |
| `needs_review` | Ambiguity or contradiction prevents a reliable determination. Record the competing readings and a question for adjudication. | The spirometry listing says FAS. The SAP assigns efficacy analyses to FAS and generally directs listings to include patients outside analysis sets. |

Use a narrowly scoped passage to establish how an analysis applies a population, then use its definition if eligibility matters. Use the same approach for general defaults and endpoint-specific exceptions. A candidate mention from the wrong population, visit, or analysis never counts as supporting evidence. Where a contradiction drives `needs_review`, cite both applicable passages and explain their roles. A missing link records the result of a search in the selected SAP version.

### Record evidence requirements

Use a reference `evidence_groups` entry for each substantiated claim or conflict the evidence needs to capture. Every group must be covered. Within a group's `alternatives`, any one inner list suffices and all passage IDs inside that list are required together. For example, `[["fas-definition", "fas-application"], ["equivalent-combined-span"]]` allows two passages used together or a single span that substantiates both claims. For partial support, group the supported portions and document the missing details in `open_questions`. During scoring, accept equivalent verified spans even if the annotators did not list them in advance.

### Terminology and display conventions

| Term | Reading for annotation |
| --- | --- |
| FAS, PD, SAF | Full, pharmacodynamic, and safety analysis sets. Confirm each trial's definition in its own SAP. |
| FEV1 | Forced expiratory volume in one second. Preserve distinctions among actual, predicted, and percent predicted. |
| `n`, `N` | Often an observation or available-case count and a population total, respectively. Resolve each using its local row, column, and footnotes. |
| SD, SE, CI, LS mean | Standard deviation, standard error, confidence interval, and least-squares mean. Check the statistic and whether it describes observations or a fitted estimate. |
| CFB, EOS, ET | Change from baseline, end of study, and early termination. Check the endpoint-specific baseline and visit definitions. |

The approved display convention list is empty pending team review. Candidate conventions for discussion include placeholder typography and line or marker styling. Once approved, give each convention a stable ID and documented scope. Record applicable IDs in `convention_ids`. A convention-only component uses `not_found_in_supplied_sap` and has no SAP evidence. Where the SAP specifies a display detail, assess it using the SAP passage.

## Review protocol

For calibration, have a second person independently label the same components before reading the drafts. Compare component boundaries, citation spans, status, and which evidence is required. Resolve disagreements against the selected SAP and document the resolution in `review_note`. Use `reviewed` only once that review is recorded. Confirm with the team and TA how to extend review to the remaining families. Track benchmark coverage of paraphrases, similar populations, endpoint-specific exceptions, multi-section support, convention-only components, unsupported footnotes, and incomplete specifications.
