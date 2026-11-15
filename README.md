# TFL to SAP Traceability Agent

[Project overview](docs/project-overview.md) · [Source manifest](data/README.md) · [Benchmark](benchmark/README.md) · [Retrieval baseline](docs/build/03-traceability-agent.md#run-the-retrieval-baseline)

Given a statistical analysis plan (SAP) and the table, figure, and listing (TFL) shells written for it, this project links each shell component to the SAP passages that support it, assigns a support status with a rationale, and lets a reviewer accept, correct, or reject each link and export a traceability matrix.

## Set up

Python 3.10 or later, Ghostscript, Tesseract, and Poppler.

```sh
pip install -r requirements.txt
python3 -m pytest tests
```

The source documents are not stored here. Download each from the link in the [source manifest](data/source-manifest.json). Every command checks the file against the manifest's checksum. Model-backed commands read `ANTHROPIC_API_KEY` from the environment.

## Commands

| Task | Command | Guide |
| --- | --- | --- |
| Parse a development family's shells | `python3 -m traceability.dev_shells` | [Step 3](docs/build/03-traceability-agent.md#parse-the-development-shells) |
| Keyword retrieval | `python3 -m traceability.retrieval` | [Step 3](docs/build/03-traceability-agent.md#run-the-retrieval-baseline) |
| Hybrid retrieval | `python3 -m traceability.hybrid` | [Step 3](docs/build/03-traceability-agent.md#hybrid-retrieval) |
| Agent with lookup tools | `python3 -m traceability.agent` | [Step 3](docs/build/03-traceability-agent.md#run-the-agent) |
| General-purpose LLM baseline | `python3 -m traceability.llm_baseline` | [Step 5](docs/build/05-evaluation-and-release.md#run-the-baselines-on-development-data) |
| Reviewer interface | `python3 -m traceability.reviewer_app` | [Step 4](docs/build/04-reviewer-interface.md#run-the-reviewer-interface) |
| Export the matrix | `python3 -m traceability.review export` | [Step 4](docs/build/04-reviewer-interface.md#run-the-reviewer-interface) |
| Score and report | `python3 benchmark/evaluate.py` | [Step 5](docs/build/05-evaluation-and-release.md#run-the-evaluation) |
| Blind check of unmatched links | `python3 benchmark/adjudication.py` | [Step 5](docs/build/05-evaluation-and-release.md#adjudicate-unmatched-links) |
| Reviewer crossover plan and effort | `python3 benchmark/crossover_plan.py`, `python3 benchmark/reviewer_effort.py` | [Step 4](docs/build/04-reviewer-interface.md#review-with-and-without-proposals) |
| Tag challenge cases, record sign-off | `python3 benchmark/challenge_tags.py`, `python3 benchmark/sign_off.py` | [Annotation guide](benchmark/annotation-guide.md#tag-challenge-cases) |
| Check the live API | `python3 benchmark/live_check.py` | [Step 5](docs/build/05-evaluation-and-release.md#check-the-live-api-first) |
| Freeze before the held-out run | `python3 benchmark/freeze_config.py` | [Step 5](docs/build/05-evaluation-and-release.md#freeze-and-run-the-held-out-evaluation) |

## Documents

[Terminology guide](benchmark/terminology.md) · [Annotation guide](benchmark/annotation-guide.md) · [Evaluation report (draft)](docs/evaluation-report.md) · [Known limitations](docs/limitations.md) · [Demo walkthrough](docs/demo.md)

## Rules that hold everywhere

- Reference annotations are used only for scoring. No retrieval index, prompt, or example reads them.
- Held-out families are not opened during development. The final evaluation runs once under a frozen configuration.
- Every quotation is checked against the SAP text it cites. A passing check shows the words exist there. It does not show the passage applies.
- No patient-level data and no populated results are stored here.
