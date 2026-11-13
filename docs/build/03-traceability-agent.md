# Traceability Agent

[Project overview](../project-overview.md) · [Previous step](02-benchmark-and-schema.md) · [Next step](04-reviewer-interface.md)

**Input** — A matched shell and SAP version, the shared schema, and development examples.

## Run the retrieval baseline

The current CLI takes existing component records. It checks the shell and SAP pairing against the frozen manifest, verifies the PDF checksum, and indexes only the selected SAP pages. Candidate results carry the SAP version, page, original PDF page, detected section heading when available, and BM25 score. Reference annotations are read by the scoring script.

Run from the repository root with Python 3.10+, `jsonschema`, and Ghostscript. Use the unchanged PDF linked in the [source manifest](../../data/source-manifest.json).

```sh
python3 -m traceability.retrieval \
  --family NCT03469934 \
  --pdf /path/to/SAP_001.pdf \
  --components benchmark/development/NCT03469934/components.jsonl \
  --top-k 10 > /tmp/traceability-retrieval.jsonl

python3 benchmark/score_development_retrieval.py \
  --family NCT03469934 \
  --results /tmp/traceability-retrieval.jsonl
```

The development smoke run found 33 of 42 draft citation anchors in the top ten candidates across ANB020-004 and APRIL. It covered all required evidence groups for 17 of the 24 components that have citations. This diagnostic matches each short anchor on its recorded SAP page. Final scoring will need reviewed labels, full passage verification, and acceptance of equivalent spans.

## What to build

1. Build document parsers. Extract TFL components with stable IDs, source locations, and context from nearby titles, labels, and notes. Split each SAP into retrievable passages while preserving its document version, section, and page. Verify the input pairing against the manifest.
2. Build retrieval within the paired SAP. Start with BM25. On development cases, compare it with hybrid keyword and embedding retrieval. Query using the component label and context, and follow references to definitions, conventions, and endpoint-specific methods when needed.
3. Add an evidence checker. Verify applicability by population, endpoint, visit, treatment group, and method where relevant. Gather additional passages when a component depends on several sections, check for exceptions, and validate quoted text and locations against the parsed source.
4. Connect parsing, retrieval, and checking in one agent. Return one schema-validated mapping per component with its rationale, support status, and any unresolved questions. Preserve partial support and ambiguity, and record approved display conventions without attaching a fabricated SAP citation. Expose retrieval for a supplied reference component so evaluation can isolate it from parsing.

## Done when

One development family runs from source files to validated mappings, with examples of multi-passage support and abstention. Before held-out evaluation, the workflow runs on all three shell types using development inputs.
