"""One test per gap found in the independent review of the fixes. Data is fictional."""

import csv
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

from traceability.hybrid import HybridIndex
from traceability.llm_baseline import run_baseline
from traceability.review import ReviewStore, load_run
from traceability.reviewer_app import Session, apply_plan, make_server

from conftest import METHOD, POPULATION, SAP_ID, SAP_VERSION, entry, passage
from test_hybrid_and_shells import passages as fixture_passages
from test_llm_baseline import FAMILY, RULES, FakeClient, answer
from test_score_mappings import references, scorer

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmark" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_quotation_crossing_a_paragraph_break_is_scored_like_any_verified_link():
    # Two paragraphs on one page. The agent's windows split at the blank line. The quotation crosses it.
    page = ("7.2 Primary endpoint analysis\n\nChange from baseline at Week 12 will be analyzed with an ANCOVA model.\n\n"
            "Least squares means and standard errors will be presented by treatment group, using the FAS.\n")
    quote = "analyzed with an ANCOVA model. Least squares means and standard errors"
    component = entry("ls-mean", "table_row", "Change from baseline, LS mean (SE)")["component"]
    result = list(run_baseline(FAMILY, [component], [(9, 10, page, "pdf_text")], RULES,
                               FakeClient(answer("supported", [(9, quote)])), "claude-opus-5-5", "medium"))[0]
    assert result["baseline"]["citations"][0]["outcome"] == "verified"
    source = result["retrieval"]["candidates"][0]
    assert quote in source["text"] and ":span:" in source["passage_id"] and source["page"] == 9
    reference = references()["TEST-TABLE-1:ls-mean"]
    matched, hits, unverified = scorer.matched_reference_ids(
        result["mapping"]["assessment"], reference, {source["passage_id"]: source["text"]})
    assert (hits, unverified) == (1, 0) and matched == {"ls-means"}
    # With the SAP supplied, the span is accepted because it is cut from the page text.
    sap = ({}, {9: " ".join(page.split())})
    assert scorer.trusted_sources([source], sap) == {source["passage_id"]: source["text"]}
    # A link like this that matches no anchor reaches the adjudicator instead of being dropped as unverified.
    adjudication = load("adjudication")
    other = {**reference, "assessment": {**reference["assessment"], "evidence": [reference["assessment"]["evidence"][0]]}}
    # (the remaining reference anchor is on another page, so the link is verified and unmatched)
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        run = Path(folder) / "run.jsonl"
        run.write_text(json.dumps(result) + "\n")
        items, _ = adjudication.unmatched_items([("llm_baseline", "TEST", run)], lambda family: {component["component_id"]: other})
    assert [item["proposed_quote"] for item in items] == [quote]


def test_forged_reviewer_passage_earns_nothing_when_the_sap_is_supplied(entries):
    forged = {"passage_id": "TEST-SAP-v1:p4:forged", "page": 4, "pdf_page": 5, "section": "4.1", "extraction": "pdf_text",
              "text": "Invented text saying participants received at least one dose.", "score": 1.0}
    link = {"passage_id": forged["passage_id"], "page": 4, "section": "4.1", "quote": "received at least one dose", "extraction": "pdf_text"}
    reviews = {entries[1]["mapping"]["mapping_id"]: {"action": "correct", "corrected_assessment": {
        "status": "supported", "rationale": "x", "convention_ids": [], "open_questions": [], "evidence": [link]}}}
    entries[0]["mapping"]["assessment"]["evidence"] = []
    sidecar = {forged["passage_id"]: forged}
    trusting = scorer.report("all", scorer.score(entries, references(), {}, reviews, sidecar)["all"])
    assert (trusting["matched_links"], trusting["unverified_links"]) == (1, 0)
    sap = ({POPULATION[0]: POPULATION[3], METHOD[0]: METHOD[3]}, {4: f"{POPULATION[2]} {POPULATION[3]}", 9: METHOD[3]})
    checked = scorer.report("all", scorer.score(entries, references(), {}, reviews, sidecar, sap)["all"])
    assert (checked["matched_links"], checked["unverified_links"]) == (0, 1)


def test_held_out_adjudication_waits_for_the_completed_final_evaluation(tmp_path, monkeypatch, capsys):
    adjudication = load("adjudication")
    monkeypatch.setattr(adjudication, "ROOT", tmp_path)
    (tmp_path / "benchmark").mkdir()
    arguments = ["adjudication.py", "export", "--partition", "held_out", "--run", "agent:HELD:run.jsonl",
                 "--items", str(tmp_path / "items.csv"), "--key", str(tmp_path / "key.json")]
    for record in (None, {"status": "started"}, {"status": "failed after references were opened"}):
        if record:
            (tmp_path / "benchmark/final-evaluation-record.json").write_text(json.dumps(record))
        monkeypatch.setattr(sys, "argv", arguments)
        with pytest.raises(SystemExit) as stop:
            adjudication.main()
        assert stop.value.code == 1 and "only after the frozen held-out evaluation has completed" in capsys.readouterr().err
    assert not (tmp_path / "items.csv").exists()


def test_export_from_the_page_hides_proposals_the_reviewer_was_not_shown(tmp_path, run_file, entries):
    ids = [item["component"]["component_id"] for item in entries]
    plan = {"assignments": {"R1": {ids[0]: "without_proposals", ids[1]: "with_proposals"}}, "order": {"R1": [ids[0], ids[1]]}}
    loaded, conditions = apply_plan(load_run(run_file), plan, "R1")
    session = Session(loaded, ReviewStore(tmp_path / "reviews.jsonl", loaded), {"families": []}, reviewer="R1", conditions=conditions)
    from traceability.review import matrix_csv, matrix_json
    rows = list(csv.DictReader(io.StringIO(matrix_csv(session.export_entries(), session.store.current))))
    hidden = [row for row in rows if row["component_id"] == ids[0]]
    assert len(hidden) == 1 and hidden[0]["proposed_evidence"] == "" and hidden[0]["proposed_status"] == "needs_review"
    exported = matrix_csv(session.export_entries(), session.store.current) + matrix_json(session.export_entries(), session.store.current)
    assert "Least squares means" not in exported and "Population and method both apply" not in exported
    assert "Least squares means" in matrix_csv(session.entries, session.store.current)


def test_run_made_against_another_sap_version_cannot_be_searched(tmp_path, entries):
    for item in entries:
        item["component"]["family_id"] = "NCT03469934"
    run = tmp_path / "run.jsonl"
    run.write_text("".join(json.dumps(item) + "\n" for item in entries))
    with pytest.raises(ValueError, match="different SAP version than the one being searched"):
        make_server(run, tmp_path / "reviews.jsonl", family="NCT03469934", pdf=tmp_path / "missing.pdf", port=0)


def test_missing_passages_file_is_reported_instead_of_exporting_an_unauditable_citation(tmp_path, entries):
    path = tmp_path / "reviews.jsonl"
    store = ReviewStore(path, entries)
    extra = passage(("TEST-SAP-v1:p20:1", 20, "9.1 Display", "Tables present two treatment columns."))
    store.add_passages([extra])
    store.save(entries[1]["mapping"]["mapping_id"], "correct", {
        "status": "supported", "rationale": "x", "evidence": [{"passage_id": extra["passage_id"], "quote": "two treatment columns"}]})
    assert ReviewStore(path, entries).extra_passages
    store.passages_path.unlink()
    with pytest.raises(ValueError, match="Restore that file so the citation can be audited"):
        ReviewStore(path, entries)


def test_missing_or_infinite_embedding_values_are_refused():
    with pytest.raises(ValueError, match="missing or infinite value"):
        HybridIndex(fixture_passages(), lambda texts: [[1.0, float("nan")] for _ in texts])
    calls = []
    embed = lambda texts: calls.append(1) or [[1.0, float("inf") if len(calls) > 1 else 0.5] for _ in texts]
    index = HybridIndex(fixture_passages(), embed)
    with pytest.raises(ValueError, match="query vector has a missing or infinite value"):
        index.search(entry("ls-mean", "table_row", "Change from baseline, LS mean (SE)")["component"], 2)
