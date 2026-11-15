import csv
import io
import json

import pytest

from traceability.review import ReviewStore, bundle, load_run, matrix_csv, matrix_json, summary

from conftest import METHOD, OTHER_VISIT, passage


def mapping_id(entries, index):
    return entries[index]["mapping"]["mapping_id"]


def test_load_run_round_trips_and_rejects_duplicates(run_file, entries):
    assert load_run(run_file) == entries
    run_file.write_text(run_file.read_text() + json.dumps(entries[0]) + "\n")
    with pytest.raises(ValueError, match="duplicate component"):
        load_run(run_file)


def test_bundle_joins_by_component_and_reports_gaps(entries):
    components = [item["component"] for item in entries]
    results = [item["retrieval"] for item in entries]
    mappings = [item["mapping"] for item in entries]
    assert bundle(components, results, mappings) == entries
    with pytest.raises(ValueError, match="missing retrieval result or mapping"):
        bundle(components, results, mappings[:-1])


def test_decisions_survive_reopening_and_keep_history(tmp_path, entries):
    path = tmp_path / "reviews.jsonl"
    store = ReviewStore(path, entries)
    store.save(mapping_id(entries, 0), "reject", note="first pass")
    store.save(mapping_id(entries, 0), "accept")
    reopened = ReviewStore(path, entries)
    assert reopened.decision(mapping_id(entries, 0))["action"] == "accept"
    assert "note" not in reopened.decision(mapping_id(entries, 0))
    assert len(path.read_text().splitlines()) == 2
    assert summary(entries, reopened.current) == {"pending": 2, "accept": 1, "correct": 0, "reject": 0}


def test_correction_carries_location_and_keeps_the_proposal(tmp_path, entries):
    store = ReviewStore(tmp_path / "reviews.jsonl", entries)
    record = store.save(mapping_id(entries, 1), "correct", {
        "status": "partially_supported", "rationale": "The definition is linked. The applying section is not.",
        "open_questions": ["Which section applies the FAS to this table?"],
        "evidence": [{"passage_id": "TEST-SAP-v1:p4:1", "quote": "includes all randomized participants"}],
    })
    evidence = record["corrected_assessment"]["evidence"][0]
    assert (evidence["page"], evidence["section"]) == (4, "4.1 Analysis populations")
    assert entries[1]["mapping"]["assessment"]["status"] == "needs_review"


@pytest.mark.parametrize("correction, message", [
    ({"status": "supported", "rationale": "x",
      "evidence": [{"passage_id": "TEST-SAP-v1:p9:1", "quote": "Change from baseline at Week 24"}]}, "Quote does not match"),
    ({"status": "supported", "rationale": "x", "evidence": []}, "at least one linked SAP quotation"),
    ({"status": "needs_review", "rationale": "x", "evidence": []}, "require an open question"),
    ({"status": "not_found_in_supplied_sap", "rationale": "x",
      "evidence": [{"passage_id": "TEST-SAP-v1:p4:1", "quote": "includes all randomized participants"}]},
     "cannot carry SAP evidence"),
])
def test_invalid_corrections_are_refused_and_not_written(tmp_path, entries, correction, message):
    path = tmp_path / "reviews.jsonl"
    store = ReviewStore(path, entries)
    with pytest.raises(ValueError, match=message):
        store.save(mapping_id(entries, 1), "correct", correction)
    assert not path.exists()


def test_convention_needs_constructed_shell_and_no_sap_evidence(tmp_path, entries):
    store = ReviewStore(tmp_path / "reviews.jsonl", entries)
    convention = {"status": "not_found_in_supplied_sap", "rationale": "Display convention only.",
                  "convention_ids": ["not-applicable-em-dash"], "evidence": []}
    assert store.save(mapping_id(entries, 2), "correct", convention)["corrected_assessment"]["evidence"] == []
    with pytest.raises(ValueError, match="constructed shell"):
        store.save(mapping_id(entries, 1), "correct", convention)


def test_correction_can_cite_a_passage_found_by_search(tmp_path, entries):
    store = ReviewStore(tmp_path / "reviews.jsonl", entries)
    extra = passage(("TEST-SAP-v1:p20:1", 20, "9.1 Display", "Tables present two treatment columns."))
    selection = {"status": "supported", "rationale": "x",
                 "evidence": [{"passage_id": extra["passage_id"], "quote": "two treatment columns"}]}
    with pytest.raises(ValueError, match="Quote does not match"):
        store.save(mapping_id(entries, 1), "correct", selection)
    store.add_passages([extra])
    assert store.save(mapping_id(entries, 1), "correct", selection)["corrected_assessment"]["evidence"][0]["page"] == 20


def test_matrix_has_one_row_per_standing_quotation_with_its_own_location(tmp_path, entries):
    store = ReviewStore(tmp_path / "reviews.jsonl", entries)
    store.save(mapping_id(entries, 0), "accept")
    store.save(mapping_id(entries, 2), "reject", note="not a reporting specification")
    rows = list(csv.DictReader(io.StringIO(matrix_csv(entries, store.current))))
    assert [row["component_id"].split(":")[1] for row in rows] == ["ls-mean", "ls-mean", "population", "dash-note"]
    assert [(row["final_evidence_section"], row["final_evidence_page"]) for row in rows[:2]] == [
        ("4.1 Analysis populations", "4"), ("7.2 Primary endpoint analysis", "9")]
    assert METHOD[3].endswith(rows[1]["final_evidence_quote"])
    assert [(row["review_action"], row["final_status"]) for row in rows[1:]] == [
        ("accept", "supported"), ("pending", ""), ("reject", "")]
    assert rows[3]["reviewer_note"] == "not a reporting specification"
    exported = json.loads(matrix_json(entries, store.current))
    assert [item["assessment_after_review"] is not None for item in exported] == [True, False, False]
    assert OTHER_VISIT[3] not in matrix_csv(entries, store.current)


def test_rejected_and_pending_proposals_never_appear_as_final_evidence(tmp_path, entries):
    store = ReviewStore(tmp_path / "reviews.jsonl", entries)
    store.save(mapping_id(entries, 0), "reject")
    rows = list(csv.DictReader(io.StringIO(matrix_csv(entries, store.current))))
    rejected = [row for row in rows if row["component_id"].endswith("ls-mean")]
    assert len(rejected) == 1
    assert all(value == "" for name, value in rejected[0].items() if name.startswith("final_"))
    assert rejected[0]["proposed_status"] == "supported"
    assert "p4 [4.1 Analysis populations]" in rejected[0]["proposed_evidence"] and "p9 [" in rejected[0]["proposed_evidence"]
    pending = next(row for row in rows if row["component_id"].endswith("population"))
    assert pending["final_rationale"] == "" and pending["proposed_rationale"].startswith("Contextual evidence")
    exported = json.loads(matrix_json(entries, store.current))[0]
    assert exported["assessment_after_review"] is None and exported["evidence_origin"] is None
    assert exported["proposal"]["assessment"]["status"] == "supported"


def test_reviewer_found_passage_is_saved_and_reloaded_for_audit(tmp_path, entries):
    path = tmp_path / "reviews.jsonl"
    store = ReviewStore(path, entries)
    extra = passage(("TEST-SAP-v1:p20:1", 20, "9.1 Display", "Tables present two treatment columns."))
    unused = passage(("TEST-SAP-v1:p21:1", 21, "9.2 Display", "Listings are sorted by participant."))
    store.add_passages([extra, unused])
    store.save(mapping_id(entries, 1), "correct", {"status": "supported", "rationale": "x",
                                                   "evidence": [{"passage_id": extra["passage_id"], "quote": "two treatment columns"}]})
    saved = [json.loads(line) for line in store.passages_path.read_text().splitlines()]
    assert [(item["sap_id"], item["sap_version"], item["passage"]["passage_id"]) for item in saved] == [
        ("TEST-SAP-v1", "1", extra["passage_id"])]
    reopened = ReviewStore(path, entries)
    assert reopened.extra_passages == {extra["passage_id"]: extra}
    assert reopened.source_passages(entries[1])[-1] == extra and len(reopened.source_passages(entries[0])) == 3
    store.passages_path.write_text(json.dumps({"sap_id": "TEST-SAP-v1", "sap_version": "2", "passage": extra}) + "\n")
    with pytest.raises(ValueError, match="different SAP version"):
        ReviewStore(path, entries)


def test_timing_events_go_to_a_sidecar(tmp_path, entries):
    store = ReviewStore(tmp_path / "reviews.jsonl", entries)
    store.log_event("opened", mapping_id(entries, 0))
    store.save(mapping_id(entries, 0), "accept", elapsed_seconds=12.5)
    events = [json.loads(line) for line in store.timing_path.read_text().splitlines()]
    assert [event["event"] for event in events] == ["opened", "saved"]
    assert events[1]["elapsed_seconds"] == 12.5
    with pytest.raises(ValueError, match="Unknown mapping"):
        store.log_event("opened", "missing")
