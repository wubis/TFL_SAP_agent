# Traceability Agent

[Project overview](../project-overview.md) · [Previous step](02-benchmark-and-schema.md) · [Next step](04-reviewer-interface.md)

**Input** — A matched shell and SAP version, the shared schema, and development examples.

## What to build

1. Build document parsers. Extract TFL components with stable IDs, source locations, and context from nearby titles, labels, and notes. Split each SAP into retrievable passages while preserving its document version, section, and page. Verify the input pairing against the manifest.
2. Build retrieval within the paired SAP. Start with BM25. On development cases, compare it with hybrid keyword and embedding retrieval. Query using the component label and context, and follow references to definitions, conventions, and endpoint-specific methods when needed.
3. Add an evidence checker. Verify applicability by population, endpoint, visit, treatment group, and method where relevant. Gather additional passages when a component depends on several sections, check for exceptions, and validate quoted text and locations against the parsed source.
4. Connect parsing, retrieval, and checking in one agent. Return one schema-validated mapping per component with its rationale, support status, and any unresolved questions. Preserve partial support and ambiguity, and record approved display conventions without attaching a fabricated SAP citation. Expose retrieval for a supplied reference component so evaluation can isolate it from parsing.

## Done when

One development family runs from source files to validated mappings, with examples of multi-passage support and abstention. Before held-out evaluation, the workflow runs on all three shell types using development inputs.
