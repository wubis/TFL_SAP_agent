import importlib.util
from pathlib import Path

from conftest import METHOD, POPULATION, SAP_ID, SAP_VERSION, cited

spec = importlib.util.spec_from_file_location(
    "score_development_mappings", Path(__file__).resolve().parents[1] / "benchmark/score_development_mappings.py")
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def reference(key, status, evidence=(), groups=()):
    return {"record_type": "reference_annotation", "component_id": f"TEST-TABLE-1:{key}", "sap_id": SAP_ID,
            "sap_version": SAP_VERSION, "evidence_groups": list(groups),
            "assessment": {"status": status, "rationale": "fictional", "evidence": list(evidence),
                           "convention_ids": [], "open_questions": []}}


def references():
    population = {"passage_id": "fas-definition", "section": "4.1", "page": 4, "quote": "received at least one dose"}
    method = {"passage_id": "ls-means", "section": "7.2", "page": 9, "quote": "Least squares means"}
    both = [{"claim": "population and method", "alternatives": [["fas-definition", "ls-means"]]}]
    records = [reference("ls-mean", "supported", [population, method], both),
               reference("population", "supported", [population], [{"claim": "definition", "alternatives": [["fas-definition"]]}]),
               reference("dash-note", "not_found_in_supplied_sap")]
    return {record["component_id"]: record for record in records}


def test_scores_status_links_groups_and_abstention(entries):
    groups = scorer.score(entries, references(), {"TEST-TABLE-1": "table"})
    result = scorer.report("all", groups["all"])
    assert groups["table"] == groups["all"]
    assert (result["components"], result["status_correct"]) == (3, 1)
    assert (result["proposed_links"], result["matched_links"], result["link_precision_proxy"]) == (2, 2, 1.0)
    assert (result["reference_anchors"], result["matched_anchors"]) == (3, 2)
    assert (result["complete_components"], result["components_with_citations"]) == (1, 2)
    assert (result["reference_not_found"], result["correct_abstentions"], result["deferred_without_links"]) == (1, 0, 1)
    assert result["status_confusion_reference_to_proposed"]["supported->needs_review"] == 1


def test_link_on_wrong_page_or_where_reference_has_none_is_not_matched(entries):
    entries[2]["mapping"]["assessment"] = {
        "status": "supported", "rationale": "x", "convention_ids": [], "open_questions": [],
        "evidence": [cited(METHOD, "ANCOVA model")]}
    entries[1]["mapping"]["assessment"] = {
        "status": "supported", "rationale": "x", "convention_ids": [], "open_questions": [],
        "evidence": [cited(METHOD, "using the FAS")]}
    result = scorer.report("all", scorer.score(entries, references(), {})["all"])
    assert (result["proposed_links"], result["matched_links"]) == (4, 2)
    assert result["links_where_reference_has_none"] == 1
    assert result["complete_components"] == 1


def test_results_are_reported_by_tagged_challenge_case(entries):
    tagged = references()
    tagged["TEST-TABLE-1:ls-mean"]["challenge_cases"] = ["paraphrased_label", "evidence_across_multiple_sections"]
    tagged["TEST-TABLE-1:population"]["challenge_cases"] = ["paraphrased_label"]
    groups = scorer.score(entries, tagged, {"TEST-TABLE-1": "table"})
    assert sorted(groups) == ["all", "case: evidence_across_multiple_sections", "case: paraphrased_label", "table"]
    paraphrase = scorer.report("case: paraphrased_label", groups["case: paraphrased_label"])
    assert (paraphrase["components"], paraphrase["status_correct"], paraphrase["matched_links"]) == (2, 1, 2)
    assert scorer.report("x", groups["case: evidence_across_multiple_sections"])["complete_components"] == 1


def test_unverified_links_never_earn_credit(entries):
    anchor = "received at least one dose"
    wrong_text = cited(METHOD, anchor)
    wrong_text["page"] = 4
    unknown = {"passage_id": "TEST-SAP-v1:p4:unknown", "page": 4, "section": "4.1", "quote": anchor, "extraction": "pdf_text"}
    entries[1]["mapping"]["assessment"] = {"status": "supported", "rationale": "x", "convention_ids": [],
                                           "open_questions": [], "evidence": [unknown, wrong_text]}
    entries[0]["mapping"]["assessment"]["evidence"] = []
    result = scorer.report("all", scorer.score(entries, references(), {})["all"])
    assert (result["proposed_links"], result["matched_links"], result["unverified_links"]) == (2, 0, 2)
    assert result["matched_anchors"] == 0


def test_reviewer_found_passage_counts_only_with_its_saved_text(entries):
    found = {"passage_id": "TEST-SAP-v1:p4:found", "page": 4, "pdf_page": 5, "section": "4.1", "extraction": "pdf_text",
             "text": "Participants in the FAS received at least one dose of study treatment.", "score": 1.0}
    link = {"passage_id": found["passage_id"], "page": 4, "section": "4.1", "quote": "received at least one dose", "extraction": "pdf_text"}
    mapping_id = entries[1]["mapping"]["mapping_id"]
    reviews = {mapping_id: {"action": "correct", "corrected_assessment": {
        "status": "supported", "rationale": "x", "convention_ids": [], "open_questions": [], "evidence": [link]}}}
    entries[0]["mapping"]["assessment"]["evidence"] = []
    without = scorer.report("all", scorer.score(entries, references(), {}, reviews)["all"])
    assert (without["matched_links"], without["unverified_links"]) == (0, 1)
    saved = scorer.report("all", scorer.score(entries, references(), {}, reviews, {found["passage_id"]: found})["all"])
    assert (saved["matched_links"], saved["unverified_links"]) == (1, 0)


def test_review_decisions_change_what_is_scored(entries):
    mapping_id = entries[1]["mapping"]["mapping_id"]
    corrected = {"status": "supported", "rationale": "x", "convention_ids": [], "open_questions": [],
                 "evidence": [cited(POPULATION, "received at least one dose")]}
    reviews = {mapping_id: {"record_type": "review", "component_id": entries[1]["component"]["component_id"],
                            "mapping_id": mapping_id, "action": "correct", "corrected_assessment": corrected},
               entries[0]["mapping"]["mapping_id"]: {"action": "reject"}}
    result = scorer.report("all", scorer.score(entries, references(), {}, reviews)["all"])
    assert (result["status_correct"], result["proposed_links"], result["complete_components"]) == (1, 1, 1)
