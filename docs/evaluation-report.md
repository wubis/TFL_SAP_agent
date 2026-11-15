# Evaluation Report (draft)

[Project overview](project-overview.md) · [Build guide for evaluation](build/05-evaluation-and-release.md) · [Known limitations](limitations.md)

**Status on November 15, 2026.** This draft holds the design, the scoring rules, and the results that exist: keyword retrieval and shell parsing on the three development families. No model-backed system has run, no person has reviewed a shell, and nothing has been run on held-out families. Sections that wait on those runs say so. Every number here was produced by a script in this repository from the original source documents.

## 1. Question

Can an agent link individual components of table, figure, and listing (TFL) shells to the statistical analysis plan (SAP) passages that support them, so reviewers can inspect the basis for each reporting specification?

## 2. Data

Six trial families, frozen on November 13, 2026 in the [source manifest](../data/source-manifest.json), split by whole family.

| Partition | Family | Shells | Components |
| --- | --- | --- | ---: |
| Development | ANB020-004 (`NCT03469934`) | FEV1 table, mean eosinophil profile figure, spirometry listing, one constructed FEV1 table | 64 |
| Development | TARVA (`NCT02128555`) | Table S4, MOXFQ walking/standing rows | 7 |
| Development | APRIL (`ISRCTN12368131`) | Appendix Table 3, continuous key secondary rows | 11 |
| Held out | MARCH-PFIC (`NCT03905330`) | Serum bile acid table and listing | 41 |
| Held out | E-SEE (`ISRCTN11079129`) | Summary table and mean profile figure | 33 |
| Held out | TAPS-2 (`NCT03975894`) | Table 4, birthweight row and headers | 8 |

`benchmark/coverage_report.py` counts the following in the 82 development records.

| Shell type | Components | | Reference status | Components |
| --- | ---: | --- | --- | ---: |
| Table | 57 | | supported | 35 |
| Listing | 17 | | partially supported | 23 |
| Figure | 8 | | not found in the supplied SAP | 16 |
| | | | needs review | 8 |

| Challenge case countable from the records | Components |
| --- | ---: |
| Support that needs more than one passage or claim | 36 |
| Evidence from more than one SAP section | 25 |
| Incomplete specification (partially supported) | 23 |
| Ambiguity or contradiction (needs review) | 8 |
| Evidence on a scanned page | 6 |
| Unsupported footnote | 2 |
| Display convention only | 1 |

75 development components come from authentic shells and 7 from the constructed shell. The records do not tag paraphrased labels, similar analyses for different populations, or general rules with endpoint-specific exceptions, so those cases are not counted. Held-out coverage is not reported here because held-out records stay unread until the final evaluation.

Reference annotations were written and source-audited by AI annotators. ANB020-004 also had a blind second AI annotation, which agreed with the first on 16 of the original 20 statuses before reconciliation. Human sign-off is open.

## 3. Systems

| System | What it gets | What it does | State |
| --- | --- | --- | --- |
| Keyword search | Component label and context, the paired SAP | BM25 over 90-word SAP passages. Ranks passages. Assigns no status. | Run on development |
| General-purpose LLM | One component, the whole paired SAP as text, display conventions | One model call. No tools, no quote check before the answer is accepted, no retry. | Written, not run |
| Agent | One component, first candidates from BM25, display conventions | One model with three lookup tools and a submit tool. Code checks every quotation. At most 6 lookups and 2 submissions per component, then needs review. | Written, not run |
| Assessor only | One component, the top candidates | One model call on retrieved candidates with a quote check and one retry. An ablation of the agent without lookups. | Written, not run |

All model-backed systems default to the same model and effort and log the model, full prompt, output, and token usage of every call. The settings to freeze are in `benchmark/evaluation-config.draft.json`.

## 4. Measures

| Proposal requirement | Measure | Script |
| --- | --- | --- |
| Component identification, scored apart from retrieval | Parsed component IDs, kinds, and labels against the inventory | Comparison in section 5.1 |
| Retrieval on reference components | Citation anchors found and components with every evidence group covered, at 1, 5, and 10 candidates | `score_development_retrieval.py` |
| Link precision and recall | Proposed links that match a reference anchor, and reference anchors found | `score_development_mappings.py` |
| All required passages found | Components whose every evidence group is covered | same |
| Equivalent valid spans | Unmatched links listed for human adjudication before they count as unsupported | manual step |
| Support-status classification | Status accuracy and the reference-to-proposed confusion table | same |
| Citation accuracy | Quotations found verbatim at the cited location | `evaluate.py` |
| Links that do not substantiate | Unmatched links after adjudication, and links on components whose reference has no evidence | `score_development_mappings.py` |
| Correct abstention | Reference not-found components answered not found, and those deferred with no link | same |
| Right context when similar language appears elsewhere | Failure review of wrong population, endpoint, visit, and method links | section 7 |
| Baselines on the same materials | Keyword search and the general-purpose LLM, same SAP pages and components | `evaluate.py` |
| Reviewer time and corrections | Decisions, status changes, links added and removed, seconds per component | `reviewer_effort.py` |
| Unsupported links remaining after review | The mapping scorer applied to the assessments that stand after review | `score_development_mappings.py --reviews` |
| Held-out families, by shell type | Pooled and per-type tables for the held-out partition, under a frozen configuration | `evaluate.py --partition held_out` |
| Parsing-to-linking workflow as well as reference components | The same scorers on components produced by the shell readers | section 5.3 |

A link matches a reference anchor when it cites the same SAP page and its 90-word passage window contains the anchor. This passage-level rule is applied to every system.

## 5. Results on development data

### 5.1 Component identification

| Family | Shells read | Components in inventory | IDs, kinds, and labels reproduced | Context reproduced |
| --- | --- | ---: | ---: | ---: |
| ANB020-004 | Table, figure, listing (authentic) | 57 | 57 | 0 |
| ANB020-004 | Constructed FEV1 table | 7 | 7 | not compared |
| TARVA | Table S4 slice | 7 | 7 | 7 |
| APRIL | Appendix Table 3 slice | 11 | 11 | 11 |

The readers are written for these registered layouts, so this table shows that they reproduce the annotated inventory. It does not show how a reader would do on an unseen layout. For ANB020-004 the only context field that differs is the nearby-label list, which the reader fills with the same shell-wide labels for every component.

### 5.2 Keyword retrieval on reference components

Pooled over the three development families, 120 citation anchors and 66 components with citations.

| System | Candidates | Citation anchors found | Components with every evidence group covered |
| --- | ---: | --- | --- |
| BM25, text layer only | 1 | 27/120 (22%) | 9/66 (14%) |
| BM25, text layer only | 5 | 68/120 (57%) | 27/66 (41%) |
| BM25, text layer only | 10 | 83/120 (69%) | 39/66 (59%) |
| BM25 with OCR pages | 1 | 30/120 (25%) | 9/66 (14%) |
| BM25 with OCR pages | 5 | 71/120 (59%) | 28/66 (42%) |
| BM25 with OCR pages | 10 | 84/120 (70%) | 36/66 (55%) |

By family at ten candidates, text layer only: ANB020-004 65/95 anchors and 27/49 components, TARVA 6/11 and 4/7, APRIL 12/14 and 8/10.

Keyword search alone leaves about two in five components without complete evidence at ten candidates. OCR adds one anchor and loses three complete components, because scanned passages push text-layer passages below the cutoff.

### 5.3 Retrieval from parsed components

ANB020-004, BM25 with OCR, ten candidates: 64/95 anchors and 22/49 complete components from the reader's components, against 66/95 and 24/49 from the annotated components. The difference comes from the nearby-label context.

### 5.4 Mappings

No model-backed run exists. With no judgments, every mapping is needs review: 0 links, and 5 of 64 ANB020-004 statuses agree with the reference because 5 reference statuses are needs review. That is the floor any system is measured against.

Pending: status accuracy, link precision and recall, complete evidence, citation accuracy, and abstention for the agent, the assessor-only ablation, and the general-purpose LLM, by shell type.

## 6. Reviewer effort

Pending. The reviewer interface records each decision and the seconds between opening a component and saving. The planned comparison has each reviewer work through components with and without agent proposals and reports decisions by action, status changes, links added and removed, time per component, and links still unmatched after review. Sample size, reviewer assignment, and which shells are used are team decisions listed in the open questions.

## 7. Failure review

Pending model runs. Each unmatched or wrong-status mapping on development data will be assigned one cause:

- wrong population, endpoint, visit, or treatment group (a relevant mention taken as support)
- a general rule applied where an endpoint-specific exception governs
- a paraphrased label that retrieval or the model did not connect
- evidence in another section that was never retrieved
- a display convention given a SAP citation, or a SAP rule treated as a convention
- a quotation that failed verification
- a valid equivalent span the reference did not list
- a scanned or tabular passage that extracted badly

## 8. Held-out evaluation

Not run. It will be run once, after the team freezes the configuration, with `benchmark/evaluate.py --partition held_out --frozen-config <file>`. The runner refuses to report unless every system has a run for every held-out family.

## 9. Reproducing these results

```sh
python3 -m traceability.retrieval --family NCT03469934 --pdf SAP_001.pdf \
  --components benchmark/development/NCT03469934/components.jsonl --top-k 10 > runs/bm25-NCT03469934.jsonl

python3 benchmark/evaluate.py --partition development \
  --retrieval bm25:NCT03469934:runs/bm25-NCT03469934.jsonl \
  --out-json runs/evaluation.json --out-md runs/evaluation.md

python3 benchmark/coverage_report.py
```

Repeat the retrieval command for `NCT02128555` and `ISRCTN12368131` with their PDFs and add a `--retrieval` argument for each. Add `--ocr` for the OCR rows. Source links and checksums are in the manifest. These runs used Ghostscript 10.02.1, Tesseract 5.3.4, and Poppler 24.02.0.
