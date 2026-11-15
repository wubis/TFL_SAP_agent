# Known Limitations

[Project overview](project-overview.md) · [Evaluation report](evaluation-report.md)

Last updated November 15, 2026.

## Not yet measured

- No model-backed system has run. The Claude assessor, the tool-using agent, and the general-purpose LLM baseline are written and tested with a stand-in client. Their accuracy, cost, and run time are unknown.
- Hybrid retrieval has not been run with an embedding model. The fusion code is tested with a toy embedder only.
- No person has reviewed a full shell in the reviewer interface, so there is no reviewer time or correction data.
- Nothing has been run on the held-out families.

## Data

- The benchmark has six families, at the low end of the 6 to 8 the proposal asks for.
- In the development partition, figures and listings appear only in ANB020-004. TARVA and APRIL each contribute a slice of one table. Results by shell type on development data rest on one family for two of the three types.
- One shell is constructed. The others are authentic. The constructed shell holds the only display-convention case.
- Reference annotations were produced and audited by AI annotators. One family had a blind second AI annotation. Human sign-off is open, and so is independent human adjudication of the held-out labels.
- The records do not tag paraphrased labels, similar analyses for different populations, or general rules with endpoint-specific exceptions, so coverage of those challenge cases cannot be counted from the data.
- The MARCH-PFIC SAP and shell pairing is inferred from shared identifiers, as the source notes say.
- Redistribution status is unverified for most sources. The repository stores links and checksums, not the documents.

## Parsing

- Each shell reader is written for one registered layout and the slice the manifest selects. A new layout needs a new reader. There is no general shell parser.
- The figure reader depends on OCR of a scanned page and corrects two known recognition errors by rule.
- On ANB020-004 the reader reproduces every component ID, kind, and label. Its nearby-label context is the same shell-wide list for every component, where the annotated inventory uses labels local to each component. Retrieval from parsed components found 64 of 95 anchors at ten candidates with OCR, against 66 from the annotated components.
- SAP sections are detected from heading lines by pattern. Passages on scanned pages carry no section.

## Retrieval and scoring

- BM25 at ten candidates covered every evidence group for 39 of 66 development components that have citations. Evidence the first retrieval misses can reach the agent only through its own lookups.
- Adding OCR passages raised anchors found from 83 to 84 of 120 and lowered complete components from 39 to 36, because scanned passages displaced text-layer passages at the cutoff.
- A proposed link is matched to a reference anchor at passage level: same page, and the cited 90-word window contains the anchor. A correct quotation from another sentence in that window counts as matched. A valid equivalent span on another page counts as unmatched until a person checks it.
- Quotation checks are exact string matches after whitespace normalization. They confirm the words exist in the cited passage. They do not confirm the passage applies to the component.
- Page numbers are SAP-internal. The manifest records how they map to PDF pages for each family.

## Agent behavior

- The agent's lookups are keyword search, read a section by heading text, and read a page. It cannot view page images, so a table that extracts badly is hard for it to use.
- The agent and the LLM baseline may answer not found in the supplied SAP after searching. The assessor command follows the earlier instruction that keeps that status for display conventions. The team has to choose one rule before comparing them.
- When the agent reaches its lookup or submission limit it returns needs review with no evidence. That is safe for the reviewer and lowers measured accuracy.
- Prompts treat shell and SAP text as data. No test has probed adversarial text inside a SAP.

## Reviewer interface

- It is a single-user local page with no accounts. Two people reviewing the same file at once would interleave records.
- Reviewer time is the time between opening a component and saving, as measured by the browser. Time away from the page is included.
- The matrix exports as CSV and JSON. There is no PDF or Word export.

## Environment

- Citation offsets in the benchmark were produced with Ghostscript 10.05.1 and Tesseract 5.5.1. The development runs reported here used Ghostscript 10.02.1 and Tesseract 5.3.4 and reproduced the documented retrieval scores for ANB020-004.
