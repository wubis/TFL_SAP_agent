# Traceability Benchmark

[Step 2 build guide](../docs/build/02-benchmark-and-schema.md) · [Source manifest](../data/source-manifest.json) · [Record schema](../schemas/traceability.schema.json) · [Annotation guide](annotation-guide.md)

## Calibration set

Use the development family **NCT03469934** for the first annotation session. The component inventory and first-pass labels are in [components.jsonl](development/NCT03469934/components.jsonl) and [reference-annotations.jsonl](development/NCT03469934/reference-annotations.jsonl). Each line is an independent JSON record.

The 20-component inventory samples a summary table, an illustrative figure shell, and a spirometry listing. It includes treatment headers, visit-specific statistic rows, legend entries, and a study-day footnote. SAP page numbers are local to the SAP. In this bundle the printed CSR page is one higher. [ANB020-004 statistical methods bundle](https://cdn.clinicaltrials.gov/large-docs/34/NCT03469934/SAP_001.pdf)

All labels are drafts. For independent review, share the inventory with a second annotator and keep the reference annotations closed until they finish. Prioritize the listing population, the figure legend counts, the difference between predicted and actual FEV1, and the endpoint-specific baseline. Reconcile the annotations before using them as benchmark answers. The family split is frozen and the remaining sources are listed in the [source manifest](../data/source-manifest.json). Assign held-out annotation to reviewers and keep those answers outside agent development.

## Additional development example

The APRIL trial adds five draft components from the continuous key secondary outcome rows of Appendix Table 3. Its inventory includes the three-month header, PROMIS and EQ-VAS rows, the summary statistic label, and the baseline-adjustment footnote. [APRIL components](development/ISRCTN12368131/components.jsonl) · [APRIL draft annotations](development/ISRCTN12368131/reference-annotations.jsonl)

## Validate the records

With Python 3.10+ and Python's `jsonschema` package installed, run from the repository root.

```sh
python3 benchmark/validate_calibration.py
```

For source verification, add `--pdf /path/to/SAP_001.pdf` using the original bundle linked above. This checks the manifest checksum and extracts each cited PDF page with Ghostscript 10.05.1 `txtwrite`. Collapse whitespace with `" ".join(text.split())` before applying `text_span`. The offsets identify a longer passage in this normalized text. The short `quote` anchors the passage for lookup. Use the resolved span for review and scoring.

For APRIL, pass `--family ISRCTN12368131` and its own original PDF. [APRIL SAP](https://www.isrctn.com/editorial/retrieveFile/f9e43ab8-60c8-4eb7-875d-3afe157430ed/42176)

## Record boundaries

- **Component** describes the shell. Keep its ID stable across parsing runs and edits to the annotation. Use the shell ID, component kind, and a stable location key. Treat repeated labels under distinct rows or columns as separate instances if their context differs.
- **Mapping** is a proposed assessment for a component and a specific SAP. Keep its ID when referring to that proposal. A new run that produces a distinct proposal should have a distinct mapping ID.
- **Review** refers to the proposal by mapping ID. A correction includes a full replacement assessment, so the original proposal can still be evaluated. An omitted review record means the mapping is pending.
- **Reference annotation** is the benchmark answer. Its evidence groups describe how to score equivalent supporting passages. Serve only shell inputs, the applicable SAP pages, and approved guides during normal agent runs. Pass benchmark components explicitly only for the retrieval-only evaluation. Keep reference annotations outside all agent retrieval and prompts.

Schema validation covers individual records. At import or evaluation time, also verify unique record IDs, that component and SAP references resolve against the inventory and source manifest, that conventions reference the approved list, and that every evidence group references passage IDs from its own assessment.
