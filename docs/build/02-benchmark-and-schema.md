# Benchmark and Traceability Schema

[Project overview](../project-overview.md) · [Previous step](01-source-collection.md) · [Next step](03-traceability-agent.md)

**Input** — The source manifest, calibration family, and frozen family split.

## What to build

1. Write a shared schema for **components**, **mappings**, and **review decisions**. A component has a stable ID, shell ID and version, locator, type, label, and analysis context. A mapping has the component ID, SAP ID and version, zero or more evidence passages with exact quotations, section and page, support status, rationale, convention flag, and unresolved questions. A review decision has the component ID, action, and any corrected evidence, status, or rationale.
2. Write an annotation guide with terminology, approved display conventions, examples of all four support statuses, and how to record evidence that spans multiple sections. Distinguish passages that are jointly required from alternative passages that can substantiate the same point. Follow the agreed review protocol and document how disagreements are resolved.
3. Annotate one development family together and resolve disagreements before scaling. Build a component inventory covering titles and population labels, table rows and columns, figure axes, legends and error bars, listing columns and selection notes, and analysis footnotes.
4. Produce reviewed annotations for development and held-out families. Include paraphrases, similar populations, endpoint-specific exceptions, multi-passage support, convention-only components, unsupported footnotes, and incomplete specifications. Store reference components, links, and labels apart from indexed sources.

## Done when

Each reference component has a stable ID, a source locator, a reviewed status, and a rationale. A second reader can locate the cited evidence and tell which passages are required. The agent's normal run has access only to the input shells and SAP collection, plus approved terminology and conventions.
