# Traceability Agent

[Project overview](../project-overview.md) · [Previous step](02-benchmark-and-schema.md) · [Next step](04-reviewer-interface.md)

**Input** — A matched shell and SAP version, the shared schema, and development examples.

## Run the retrieval baseline

The current CLI takes existing component records. It checks the shell and SAP pairing against the frozen manifest, verifies the PDF checksum, and indexes only the selected SAP pages. Candidate results carry the SAP version, page, original PDF page, detected section heading when available, and BM25 score. Reference annotations are read by the scoring script.

Run from the repository root with Python 3.10+, `jsonschema`, and Ghostscript. Use the unchanged PDF linked in the [source manifest](../../data/source-manifest.json). The optional `--ocr` flag requires Tesseract and runs OCR on SAP pages without usable text. Each candidate identifies its extraction method. Check OCR-derived quotations against the page image when characters or layout affect the interpretation.

```sh
python3 -m traceability.retrieval \
  --family NCT03469934 \
  --pdf /path/to/SAP_001.pdf \
  --components benchmark/development/NCT03469934/components.jsonl \
  --top-k 10 --ocr > /tmp/traceability-retrieval.jsonl

python3 benchmark/score_development_retrieval.py \
  --family NCT03469934 \
  --results /tmp/traceability-retrieval.jsonl
```

In the ANB020-004 development run, OCR retrieved the scanned treatment-label rule in the top two candidates for all four authentic treatment headers and legend entries. Across the full sample at ten candidates, OCR hit 66 of 95 citation anchor occurrences and covered every evidence group for 24 of 49 components with citations. The text-only run hit 65 anchors and covered every group for 27 components. The OCR candidates can displace text-layer evidence at a fixed cutoff.

## Produce validated mappings

Pass the retrieved candidates to the mapping command. An optional JSONL file lets a reviewer supply contextual judgments. Each line contains `component_id`, `status`, `rationale`, and optional `open_questions`, `convention_ids`, and `evidence`. Each evidence selection identifies a candidate by `passage_id` and gives its exact `quote`. The command checks that the quotation occurs in the selected candidate, carries over the source location and extraction method, and validates every mapping against the shared schema. Components without a judgment are marked `needs_review` with empty evidence.

```sh
python3 -m traceability.mapping \
  --results /tmp/traceability-retrieval.jsonl \
  --assessments /path/to/assessments.jsonl > /tmp/traceability-mappings.jsonl
```

Use a result file produced by the retrieval command with the selected SAP. The mapping command checks consistency with that file. The assessor supplies the contextual support judgment.

## Run from the source shell

The one-command pipeline parses the registered [FEV1 Markdown challenge](../../data/shells/anb020-004-fev1-challenge.md), verifies its checksum and paired SAP, and returns one JSON record per component with its candidates and validated mapping. It reads the source shell and SAP directly. Its optional `--assessments` file has the same format as the mapping command above.

```sh
python3 -m traceability.shell_pipeline \
  --pdf /path/to/SAP_001.pdf --ocr > /tmp/traceability-shell-run.jsonl
```

The parser supports version 1.0 of this constructed Markdown shell. It uses the table and note positions to preserve the existing inventory IDs. It keeps both trial arms in context for dummy treatment labels until the SAP evidence resolves each label. The authentic PDF table, figure, and listing still use the component-inventory entry point. Automated contextual verification remains open.

## What to build

1. Build document parsers. Extract TFL components with stable IDs, source locations, and context from nearby titles, labels, and notes. Split each SAP into retrievable passages while preserving its document version, section, and page. Verify the input pairing against the manifest.
2. Build retrieval within the paired SAP. Start with BM25. On development cases, compare it with hybrid keyword and embedding retrieval. Query using the component label and context, and follow references to definitions, conventions, and endpoint-specific methods when needed.
3. Add an evidence checker. Verify applicability by population, endpoint, visit, treatment group, and method where relevant. Gather additional passages when a component depends on several sections, check for exceptions, and validate quoted text and locations against the parsed source.
4. Connect parsing, retrieval, and checking in one agent. Return one schema-validated mapping per component with its rationale, support status, and any unresolved questions. Preserve partial support and ambiguity, and record approved display conventions without attaching a fabricated SAP citation. Expose retrieval for a supplied reference component so evaluation can isolate it from parsing.

## Done when

One development family runs from source files to validated mappings, with examples of multi-passage support and abstention. Before held-out evaluation, the workflow runs on all three shell types using development inputs.
