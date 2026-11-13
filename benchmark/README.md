# Traceability Benchmark

[Step 2 build guide](../docs/build/02-benchmark-and-schema.md) · [Source manifest](../data/source-manifest.json) · [Record schema](../schemas/traceability.schema.json) · [Annotation guide](annotation-guide.md)

## Calibration set

The development calibration family is **NCT03469934 (ANB020-004)**. The [component inventory](development/NCT03469934/components.jsonl) and [reference annotations](development/NCT03469934/reference-annotations.jsonl) cover three authentic shells and a constructed FEV1 challenge. Each line is an independent JSON record.

The [calibration review](development/NCT03469934/calibration-review.jsonl) records a blind second AI annotation of the original 20 components. The two passes initially agreed on 16 statuses. Reconciliation changed four treatment header and legend labels to `needs_review` after the second pass found a scanned appendix prescribing dummy group names. The spirometry listing's population scope remains an unresolved SAP question. SAP pages in citations use the SAP's own numbering. The printed CSR page is one higher. [ANB020-004 statistical methods bundle](https://cdn.clinicaltrials.gov/large-docs/34/NCT03469934/SAP_001.pdf)

The remaining records were reviewed against the published sources by AI annotators. Here `reviewed` records source audit or reconciliation. Team sign-off and any required independent human review remain separate from that status. A reviewed annotation can still classify a component as `needs_review` where the SAP and shell leave a substantive question open.

## Development and held-out coverage

The benchmark has 164 reviewed records across the selected shell regions. The authentic shells remain the source corpus, with one constructed challenge fixture in development.

| Partition | Family | Components |
| --- | --- | ---: |
| Development | ANB020-004 | 64 |
| Development | APRIL | 11 |
| Development | TARVA | 7 |
| Held out | MARCH-PFIC | 41 |
| Held out | E-SEE | 33 |
| Held out | TAPS-2 | 8 |

APRIL covers the continuous key secondary outcomes in Appendix Table 3. TARVA covers the selected MOXFQ walking/standing rows and associated headers in Table S4. The TARVA shell describes follow-up from randomisation, while the SAP describes follow-up from surgery. [APRIL records](development/ISRCTN12368131) · [TARVA records](development/NCT02128555)

The evaluation reference files live under `benchmark/held_out/` and cover MARCH-PFIC, E-SEE, and TAPS-2. Keep that directory outside agent development inputs and retrieval. The development scorer restricts reference reads to development families. Use the held-out inventories only as inputs for retrieval-only evaluation, and use the held-out answers only for scoring and reviewer audit.

## Validate the records

With Python 3.10+ and Python's `jsonschema` package installed, run from the repository root.

```sh
python3 benchmark/validate_calibration.py --require-reviewed
```

For source verification, add `--pdf /path/to/SAP_001.pdf` using the original linked in the manifest. This checks the checksum and extracts cited pages with Ghostscript 10.05.1 `txtwrite`. Citations marked `ocr` use a 200 DPI render and Tesseract 5.5.1 with `--psm 3`. Collapse whitespace with `" ".join(text.split())` before applying `text_span`. The short `quote` anchors the longer passage. Use the resolved span and consult the source image when checking scanned evidence.

For any other family, pass `--family FAMILY_ID` and its own original PDF. The validator reads the frozen partition from the manifest and reports aggregate validation counts for held-out families. [Source manifest](../data/source-manifest.json)

## Record boundaries

- **Component** describes the shell. Keep its ID stable across parsing runs and edits to the annotation. Use the shell ID, component kind, and a stable location key. Treat repeated labels under distinct rows or columns as separate instances if their context differs.
- **Mapping** is a proposed assessment for a component and a specific SAP. Keep its ID when referring to that proposal. A new run that produces a distinct proposal should have a distinct mapping ID.
- **Review** refers to the proposal by mapping ID. A correction includes a full replacement assessment, so the original proposal can still be evaluated. An omitted review record means the mapping is pending.
- **Reference annotation** is the benchmark answer. Its evidence groups describe how to score equivalent supporting passages. Serve only shell inputs, the applicable SAP pages, and approved guides during normal agent runs. Pass benchmark components explicitly only for the retrieval-only evaluation. Keep reference annotations outside all agent retrieval and prompts.

Schema validation covers individual records. At import or evaluation time, also verify unique record IDs, that component and SAP references resolve against the inventory and source manifest, that conventions reference the approved list, and that every evidence group references passage IDs from its own assessment.
