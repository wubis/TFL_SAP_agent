# Tests

```sh
pip install -r requirements.txt
python3 -m pytest tests
```

All data in the tests is fictional. Two tests need the original source documents and are skipped unless `TRACEABILITY_SOURCES` points to a folder holding them. `tests/browser/` holds a separate browser check of the reviewer page.

## Review findings and the tests that would catch them again

| Finding | Test |
| --- | --- |
| Scoring credited a link whose passage was missing, using the proposed quotation as its own source text | `test_score_mappings.py::test_unverified_links_never_earn_credit`, `::test_reviewer_found_passage_counts_only_with_its_saved_text` |
| A run file's or sidecar's passage text was trusted | `test_evaluation.py::test_run_file_text_is_not_trusted_when_the_sap_is_supplied`, `test_review_findings.py::test_forged_reviewer_passage_earns_nothing_when_the_sap_is_supplied` |
| A held-out report with one system, a missing family, or unchecked settings could pass | `test_evaluation.py::test_held_out_gates_run_before_any_reference_is_read`, `::test_run_settings_must_equal_the_frozen_configuration`, `::test_fallback_model_partial_run_and_mixed_settings_are_refused` |
| The frozen file could be edited after the tag | `test_evaluation.py::test_freeze_requires_a_clean_tree_then_detects_later_changes` |
| Gate scripts, scorers, reference answers, and dependencies were outside the fingerprint | `test_evaluation.py::test_freeze_requires_a_clean_tree_then_detects_later_changes` |
| A failed held-out run could be repeated and its error named held-out components | `test_evaluation.py::test_failure_after_references_open_spends_the_run_and_names_no_component` |
| An unwritable output path consumed the single run | `test_evaluation.py::test_held_out_gates_run_before_any_reference_is_read` |
| Held-out reference quotations could be exported for adjudication at any time | `test_review_findings.py::test_held_out_adjudication_waits_for_the_completed_final_evaluation` |
| Reviewer search passages were lost on restart | `test_review.py::test_reviewer_found_passage_is_saved_and_reloaded_for_audit`, `test_reviewer_end_to_end.py::test_correct_restart_export_and_score`, `test_review_findings.py::test_missing_passages_file_is_reported_instead_of_exporting_an_unauditable_citation` |
| The searched SAP could differ from the run's SAP version | `test_review_findings.py::test_run_made_against_another_sap_version_cannot_be_searched` |
| The export mixed rejected proposals with final evidence | `test_review.py::test_rejected_and_pending_proposals_never_appear_as_final_evidence` |
| A blinded reviewer could read proposals through the export | `test_review_findings.py::test_export_from_the_page_hides_proposals_the_reviewer_was_not_shown` |
| Hybrid retrieval truncated mismatched embedding dimensions and accepted invalid values | `test_hybrid_and_shells.py::test_mismatched_embedding_dimensions_are_refused`, `test_review_findings.py::test_missing_or_infinite_embedding_values_are_refused` |
| The frozen commit differed from the run's commit and blocked the final evaluation | `test_evaluation.py::test_freeze_commit_tag_run_evaluate_sequence` |
| Baseline quotations crossing a paragraph break were scored as unsupported with no human check | `test_review_findings.py::test_baseline_quotation_crossing_a_paragraph_break_is_scored_like_any_verified_link` |
| Unsigned annotations could reach the held-out run | `test_evaluation.py::test_unsigned_held_out_annotations_block_the_run` |
