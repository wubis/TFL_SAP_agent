# Evaluation Report (draft)

[Project overview](project-overview.md) · [Build guide for evaluation](build/05-evaluation-and-release.md) · [Known limitations](limitations.md)

**Status on November 15, 2026.** This draft holds the design, the scoring rules, the team's decisions on procedure, and the results that exist: keyword and hybrid retrieval and shell parsing on the three development families. No language-model system has run against the API, no person has reviewed a shell, and nothing has been run on held-out families. Sections that wait on those runs say so. Every number here was produced by a script in this repository from the original source documents.

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

Each reference record can carry `challenge_cases` tags from the proposal's list. Five follow from the record and are filled by `benchmark/challenge_tags.py`. Three need an annotator's judgment and have not been assigned yet.

| Challenge case | Development records | How it is tagged |
| --- | ---: | --- |
| Evidence across multiple sections | 25 | Derived from the record |
| Incomplete specification | 23 | Derived from the record |
| Unsupported footnote | 1 | Derived from the record |
| Convention-only component | 1 | Derived from the record |
| Alternative valid passages | 0 | Derived from the record |
| Paraphrased label | not yet tagged | Annotator |
| Similar analysis for a different population | not yet tagged | Annotator |
| General convention with an endpoint-specific exception | not yet tagged | Annotator |

Also countable from the records: 36 components need more than one passage or claim, 8 have a needs-review reference status, and 6 have evidence on a scanned page.

Unsupported footnotes, convention-only components, and alternative valid passages have one record or none. The team decided that constructed shells may be written for cases this thin, to a real SAP in a development family, before any agent output is looked at. None has been written yet. 75 development components come from authentic shells and 7 from the constructed shell. Whether that mix is acceptable has not been confirmed with the TA. Held-out coverage is not reported here because held-out records stay unread until the final evaluation.

Six families is the final count unless a new family fills a gap. A rule in the [source notes](../data/README.md#adding-a-family-after-the-freeze) fixes the partition of any added family before its documents are opened.

Reference annotations were written and source-audited by AI annotators. ANB020-004 also had a blind second AI annotation, which agreed with the first on 16 of the original 20 statuses before reconciliation. The proposal asks for reviewed reference links. A second teammate who did not write the annotations signs off each family, a third person or the group settles disagreements, and names and dates are recorded in the manifest. No family is signed off yet, and the held-out evaluation will not run until every held-out family is.

## 3. Systems

| System | What it gets | What it does | State |
| --- | --- | --- | --- |
| Keyword search | Component label and context, the paired SAP | BM25 over 90-word SAP passages. Ranks passages. Assigns no status. | Run on development |
| Hybrid retrieval | The same | BM25 and embedding rankings combined by reciprocal rank fusion, with a local embedding model. | Run on development with two models |
| General-purpose LLM | One component, the whole paired SAP as text, display conventions | One model call. No tools, no quote check before the answer is accepted, no retry. | Written, not run |
| Agent | One component, first candidates from BM25, display conventions | One model with three lookup tools and a submit tool. Code checks every quotation. At most 6 lookups and 2 submissions per component, then needs review. | Written, not run |
| Assessor only | One component, the top candidates | One model call on retrieved candidates with a quote check and one retry. An ablation of the agent without lookups. | Written, not run |

All three language-model systems use the same model at the same effort, which the team confirmed for a fair comparison. Each logs the model, full prompt, output, and token usage of every call, and every run file records its settings and a fingerprint of the code that produced it. The settings to freeze are in `benchmark/evaluation-config.draft.json`. The limits of 8 first candidates, 6 lookups, and 2 submissions were set as defaults before any model run and have not been tuned on any family.

All three may answer not found in the supplied SAP after a documented search, and the record lists the searches that were run. A component that rests only on a display convention takes the same status with the convention ID and no SAP passage. The team adopted this rule on November 15, 2026, because the proposal measures correct abstention and the earlier assessor instruction made every such reference component unanswerable.

## 4. Measures

| Proposal requirement | Measure | Script |
| --- | --- | --- |
| Component identification, scored apart from retrieval | Parsed component IDs, kinds, and labels against the inventory | Comparison in section 5.1 |
| Retrieval on reference components | Citation anchors found and components with every evidence group covered, at 1, 5, and 10 candidates | `score_development_retrieval.py` |
| Link precision and recall | Proposed links that match a reference anchor, and reference anchors found | `score_development_mappings.py` |
| All required passages found | Components whose every evidence group is covered | same |
| Equivalent valid spans | Unmatched links ruled on blind by a person who built none of the systems, before they count as unsupported | `adjudication.py` |
| Support-status classification | Status accuracy and the reference-to-proposed confusion table | same |
| Citation accuracy | Quotations found verbatim at the cited location. A link whose source passage was not saved, or whose quotation is not in it, is counted as unverified and never matched. | `evaluate.py`, `score_development_mappings.py` |
| Links that do not substantiate | Unmatched links after adjudication, and links on components whose reference has no evidence | `score_development_mappings.py` |
| Correct abstention | Reference not-found components answered not found, and those deferred with no link | same |
| Right context when similar language appears elsewhere | Every measure reported by tagged challenge case, plus the failure review of wrong population, endpoint, visit, and method links | `score_development_mappings.py`, section 7 |
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

Hybrid retrieval, text layer only, same components:

| System | Candidates | Citation anchors found | Components with every evidence group covered |
| --- | ---: | --- | --- |
| BM25 with `BAAI/bge-small-en-v1.5` | 1 | 31/120 (26%) | 8/66 (12%) |
| BM25 with `BAAI/bge-small-en-v1.5` | 5 | 67/120 (56%) | 27/66 (41%) |
| BM25 with `BAAI/bge-small-en-v1.5` | 10 | 78/120 (65%) | 35/66 (53%) |
| BM25 with MedCPT | 1 | 22/120 (18%) | 5/66 (8%) |
| BM25 with MedCPT | 5 | 58/120 (48%) | 23/66 (35%) |
| BM25 with MedCPT | 10 | 69/120 (57%) | 29/66 (44%) |

With OCR pages at ten candidates the small general model found 78/120 anchors and 35/66 complete components, and MedCPT found 71/120 and 31/66.

Neither hybrid beat BM25 at five or ten candidates on development data. The small general model found four more anchors than BM25 at one candidate and five fewer at ten. MedCPT was lower at every cutoff. MedCPT was trained on biomedical literature search, and SAP passages are procedural text, which may explain the gap. The agent therefore keeps BM25 for its first candidates and its `search_sap` tool. Rankings are fused with reciprocal rank fusion at k = 60 over the top 50 of each ranking, and neither value was tuned. MedCPT's article encoder takes a title and a text, and the SAP section heading was used as the title.

### 5.3 Retrieval from parsed components

ANB020-004, BM25 with OCR, ten candidates: 64/95 anchors and 22/49 complete components from the reader's components, against 66/95 and 24/49 from the annotated components. The difference comes from the nearby-label context.

### 5.4 Mappings

No model-backed run exists. With no judgments, every mapping is needs review: 0 links, and 5 of 64 ANB020-004 statuses agree with the reference because 5 reference statuses are needs review. That is the floor any system is measured against.

Pending: status accuracy, link precision and recall, complete evidence, citation accuracy, and abstention for the agent, the assessor-only ablation, and the general-purpose LLM, by shell type and by challenge case.

Before any of those runs, `benchmark/live_check.py` makes a few real calls on development components and checks that the commands finish, that the requested model served every call, that every cited quotation is in the passage it cites, and that prompts and token usage were logged. It has not been run, because no API key is available yet. Tests with a stand-in client cannot show that live calls and real model responses behave as intended.

## 6. Reviewer effort

Not yet run. The design the team agreed is a small crossover on development families.

- **Reviewers.** Two teammates who did not annotate the family they review.
- **Material.** One table, one figure, and one listing, 20 to 30 components per reviewer.
- **Conditions.** Each reviewer does half the components with the agent's proposals and half without. The halves swap between the two reviewers, so every component is reviewed once in each condition. Without proposals the page shows no status, rationale, evidence, or candidates, and the reviewer searches the SAP.
- **Measures.** Minutes per component in each condition, and the number of corrections to proposals. Also reported: status changes, links added and removed, and links still unmatched after review.

`benchmark/crossover_plan.py` builds the assignment from a run file with a fixed seed. On the authentic ANB020-004 shells it drew 8 table, 8 figure, and 8 listing components per reviewer, 12 in each condition. The reviewer interface takes the plan and a reviewer name, and `benchmark/reviewer_effort.py` reports the measures by condition. Time is measured from opening a component to saving it.

The workflow itself was run in a real browser on the 64 ANB020-004 components, with the script in `tests/browser/`. It corrected the table's population label with two candidate passages, corrected the listing's population label with a passage found by searching the SAP, accepted one proposal, and rejected one. The application was then stopped and started again. The decisions, the correction, and the searched passage with its highlighted quotation were all shown again, and the matrix was downloaded from the page. The export had 65 rows, with final evidence only on the corrected rows. Scoring the reviewed assessments gave 3 links, 2 matched to reference anchors, none unverified, and 1 component with complete evidence, against 0 links before review. The run was driven by a script, so it shows the workflow works. No person has done a review session yet.

## 6a. Adjudicating unmatched links

Not yet run. A link the scorer leaves unmatched may still be an equivalent valid span. Before it counts as unsupported:

1. `benchmark/adjudication.py export` writes one row per unmatched link, with the component, its context, the proposed quotation and passage, and the reference rationale and quotations. Links proposed by several systems appear once. The system name is kept in a separate key file.
2. A person who built none of the three systems rules on each row as equivalent, unsupported, or unsure, with a reason, and does not see the key.
3. A second person rules on every unsure row, with a reason.
4. `benchmark/adjudication.py apply` checks that every ruling has a reason and a name and reports the rulings per system.

The procedure is run on development runs first so it is settled, then once on the held-out runs after the freeze. A link that fails quotation verification is already unsupported and is not sent for adjudication.

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

Not run. One person runs it once. The team will set the freeze date several days before the report is due, so the unmatched-link check and the write-up fit. After the run nobody changes the agent.

1. On a clean checkout at the end of development, `python3 benchmark/freeze_config.py --date <date>` writes the frozen configuration with the exact model identifiers and a fingerprint of the protected code, schema, conventions, and manifest.
2. Commit that file alone and tag the commit.
3. From the tagged commit, produce one run per system for every held-out family.
4. `python3 benchmark/evaluate.py --partition held_out --frozen-config <file>` with every run.

Before it opens any held-out reference, the runner checks that the configuration is a frozen file, that the protected files are unchanged since the freeze, that the current commit is tagged, that runs were given for exactly the systems the frozen configuration names and for every held-out family, and that each run file's recorded model, effort, limits, retrieval, OCR setting, and code fingerprint equal the frozen ones. It then writes `benchmark/final-evaluation-record.json` and refuses to run again while that record exists. The fingerprint depends only on the protected files, so runs made after the frozen file is committed still match.

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
