# Evaluation and Release

[Project overview](../project-overview.md) · [Previous step](04-reviewer-interface.md)

**Input** — The frozen family split, reviewed reference set, working agent, and reviewer interface.

## What to build

1. Build a reproducible evaluation runner. Freeze the agent configuration and scoring rules after development. Run keyword search and a general-purpose LLM as baselines using the same source materials and equivalent inputs for each comparison.
2. Evaluate component identification separately, then measure retrieval on reference components and run the full parsing-to-linking workflow. Accept equivalent valid spans and track whether all required passages were found. Report results separately for tables, figures, and listings.
3. Report retrieval recall at k, link precision and recall, complete multi-passage support, citation accuracy, support-status accuracy, unsupported-link rate, and correct abstention. Use the challenge cases to explain where the agent confuses analysis contexts, misses exceptions, or mishandles conventions.
4. Measure reviewer time, corrections, and unsupported links remaining after review. Record the review conditions and sample sizes so the comparison can be interpreted.
5. Package the prototype, schema, example matrix, annotated benchmark and guides, partition manifest, permitted source documents or provenance, pinned dependencies, run instructions, and evaluation report. Prepare a demo that traces one component through evidence inspection, a review action, and export.

## Done when

A teammate can reproduce the held-out runs and generate an example export from the documented commands. The final report includes baseline comparisons, results by shell type, reviewer effort, failure examples, and known limitations.
