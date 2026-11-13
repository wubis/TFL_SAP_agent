# Reviewer Interface and Export

[Project overview](../project-overview.md) · [Previous step](03-traceability-agent.md) · [Next step](05-evaluation-and-release.md)

**Input** — Parsed shells and schema-validated agent mappings.

## What to build

1. Build a lightweight reviewer interface in the format agreed with the TA. Let a reviewer pick a shell and select a component using its location and label in context.
2. Show the component's analysis context, status, rationale, and unresolved questions alongside its SAP quotations, document version, section, and page. Display all required passages and identify any approved display convention.
3. Support **accept**, **correct**, and **reject**. Let reviewers amend linked passages, status, and rationale, or leave an unresolved question. Persist review actions and preserve the original proposal so corrections can be measured later.
4. Export a traceability matrix that joins component IDs, source locations, context, evidence, statuses, rationale, decisions, and unresolved questions. Preserve the association between every quotation and its location when a component has several passages.

## Done when

A reviewer can inspect and act on one development shell end to end. The saved actions survive reopening, and the exported matrix includes accepted, corrected, rejected, and pending mappings with their corresponding evidence and open questions.
