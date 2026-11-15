# Known Limitations

[Project overview](project-overview.md) · [Evaluation report](evaluation-report.md)

Last updated November 15, 2026.

## Not yet measured

- The agent and the general-purpose LLM have each run once on development data. The assessor-only ablation has not run. Results come from one run per system, and model output varies between runs.
- On development data the agent is level with the general-purpose LLM on status accuracy, abstains less often, and never answers needs review where the reference does.
- SAP text is extracted page by page without regard to columns. On a two-column SAP such as TARVA the columns interleave, passages mix unrelated sentences, and a quotation that is correct in the document may not be contiguous in the extracted text. TAPS-2 in the held-out set has the same layout. The Claude assessor, the tool-using agent, and the general-purpose LLM baseline are written and tested with a stand-in client. Whether the live calls and the model's responses behave as intended, and the accuracy, cost, and run time, are unknown until they run.
- No person has reviewed a full shell in the reviewer interface, so there is no reviewer time or correction data. The correct, restart, export, and score workflow has been run in a real browser by script on ANB020-004.
- No unmatched link has been adjudicated.
- Nothing has been run on the held-out families.

## Data

- The benchmark has six families, at the low end of the 6 to 8 the proposal asks for.
- In the development partition, figures and listings appear only in ANB020-004. TARVA and APRIL each contribute a slice of one table. Results by shell type on development data rest on one family for two of the three types.
- One shell is constructed. The others are authentic. The constructed shell holds the only display-convention case.
- Reference annotations were produced and audited by AI annotators. One family had a blind second AI annotation. No family has the teammate sign-off the team requires, so the links do not yet meet the proposal's wording of reviewed reference links.
- Three challenge cases need an annotator's tag and have none yet: paraphrased labels, similar analyses for different populations, and general conventions with endpoint-specific exceptions. Results for those cases cannot be reported until records are tagged. Held-out records carry no tags at all.
- Unsupported footnotes, convention-only components, and alternative valid passages have one development record or none. No constructed shell has been written for them yet.
- The acceptable mix of authentic and constructed shells has not been confirmed with the TA.
- The MARCH-PFIC SAP and shell pairing is inferred from shared identifiers, as the source notes say.
- Redistribution status is unverified for most sources. The repository stores links and checksums, not the documents.

## Parsing

- Each shell reader is written for one registered layout and the slice the manifest selects. A new layout needs a new reader. There is no general shell parser.
- The figure reader depends on OCR of a scanned page and corrects two known recognition errors by rule.
- On ANB020-004 the reader reproduces every component ID, kind, and label. Its nearby-label context is the same shell-wide list for every component, where the annotated inventory uses labels local to each component. Retrieval from parsed components found 64 of 95 anchors at ten candidates with OCR, against 66 from the annotated components.
- SAP sections are detected from heading lines by pattern. Passages on scanned pages carry no section.

## Retrieval and scoring

- BM25 at ten candidates covered every evidence group for 39 of 66 development components that have citations. Evidence the first retrieval misses can reach the agent only through its own lookups.
- Hybrid retrieval did not help on development data. With a small general embedding model it covered 35 of 66 components at ten candidates, and with MedCPT 29. Two models were tried, with untuned fusion settings, on three families.
- Adding OCR passages raised anchors found from 83 to 84 of 120 and lowered complete components from 39 to 36, because scanned passages displaced text-layer passages at the cutoff.
- A proposed link is matched to a reference anchor at passage level: same page, and the cited 90-word window contains the anchor. A correct quotation from another sentence in that window counts as matched. A valid equivalent span on another page counts as unmatched until a person checks it.
- The held-out gates and the code fingerprint guard against mistakes such as a changed setting, a missing system, or a late edit. They cannot stop someone who edits the checking code itself. The tagged commit and the evaluation record are the audit trail.
- Checking quotations against the SAP PDF re-extracts the text. A different Ghostscript or Tesseract version from the one a run used can extract slightly different text and turn a true quotation into an unverified one. Use the same tool versions for the runs and the evaluation.
- Without a PDF, the scorer checks quotations against the passage text in the run file and in a reviewer's saved passages, and takes that text as given.
- Quotation checks are exact string matches after whitespace normalization. They confirm the words exist in the cited passage. They do not confirm the passage applies to the component.
- Page numbers are SAP-internal. The manifest records how they map to PDF pages for each family.

## Agent behavior

- The agent's lookups are keyword search, read a section by heading text, and read a page. It cannot view page images, so a table that extracts badly is hard for it to use.
- All three systems may answer not found in the supplied SAP after a documented search. The assessor sees only its retrieved candidates, so its not-found answers rest on a narrower search than the agent's or the baseline's. Each record lists the searches behind the answer.
- The spending cap uses recorded list prices and counts cache writes at twice the input rate. It is a guard that errs high, not a bill.
- When the agent reaches its lookup or submission limit it returns needs review with no evidence. That is safe for the reviewer and lowers measured accuracy.
- Prompts treat shell and SAP text as data. No test has probed adversarial text inside a SAP.

## Reviewer interface

- It is a single-user local page with no accounts. Two people reviewing the same file at once would interleave records.
- Reviewer time is the time between opening a component and saving, as measured by the browser. Time away from the page is included.
- The matrix exports as CSV and JSON. There is no PDF or Word export.
- The shell page image is shown only for shells that sit on a single page of the supplied PDF. TARVA's shell is a Word supplement and has no image.
- Without proposals, a reviewer can cite only passages found through the search box, which is keyword search over the same passages the agent uses.
- The page's export leaves out proposals a reviewer was not shown. The command-line export includes them, so run it only after the review session.

## Environment

- Citation offsets in the benchmark were produced with Ghostscript 10.05.1 and Tesseract 5.5.1. The development runs reported here used Ghostscript 10.02.1 and Tesseract 5.3.4 and reproduced the documented retrieval scores for ANB020-004.
