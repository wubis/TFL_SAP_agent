"""The evaluation runner is tested on a fictional manifest and benchmark built in a temporary folder."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from traceability.review import ReviewStore

from test_score_mappings import references

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmark" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def workspace(tmp_path, monkeypatch, entries):
    evaluate = load("evaluate")
    shells = [{"document_id": "TEST-TABLE-1", "type": "table"}]
    manifest = {"partition_status": "frozen", "families": [
        {"family_id": "TEST", "partition": "development", "shells": shells},
        {"family_id": "TEST-HELD", "partition": "held_out", "shells": shells},
        {"family_id": "TEST-HELD-2", "partition": "held_out", "shells": shells}]}
    (tmp_path / "data").mkdir()
    (tmp_path / "data/source-manifest.json").write_text(json.dumps(manifest))
    for partition, family in (("development", "TEST"), ("held_out", "TEST-HELD"), ("held_out", "TEST-HELD-2")):
        folder = tmp_path / "benchmark" / partition / family
        folder.mkdir(parents=True)
        (folder / "reference-annotations.jsonl").write_text("".join(json.dumps(r) + "\n" for r in references().values()))
    run = tmp_path / "run.jsonl"
    run.write_text("".join(json.dumps(item) + "\n" for item in entries))
    saved = tmp_path / "retrieval.jsonl"
    saved.write_text("".join(json.dumps({**item["retrieval"]}) + "\n" for item in entries))
    monkeypatch.setattr(evaluate, "ROOT", tmp_path)
    return evaluate, manifest, run, saved, tmp_path


def test_pools_systems_and_writes_a_report(workspace):
    evaluate, manifest, run, saved, _ = workspace
    results = evaluate.evaluate(manifest, "development", [("agent", "TEST", run)], [("bm25", "TEST", saved)])
    pooled = results["systems"]["agent"]["pooled"]
    assert pooled["all"]["status_correct"] == 1 and pooled["table"] == {**pooled["all"], "group": "table"}
    assert results["systems"]["agent"]["citation_accuracy"] == {"citations": 2, "verified": 2, "rate": 1.0}
    assert results["retrieval"]["bm25"]["pooled"]["10"]["matched_citation_anchors"] == 3
    report = evaluate.markdown(results)
    assert "| agent | all | 3 | 1/3 (33%) | 2/2 (100%) |" in report and "| bm25 | 10 | 3/3 (100%) | 2/2 (100%) | 1 |" in report


def test_family_from_another_partition_is_refused(workspace):
    evaluate, manifest, run, _, _ = workspace
    with pytest.raises(ValueError, match="not a development family"):
        evaluate.evaluate(manifest, "development", [("agent", "TEST-HELD", run)], [])


def run_main(evaluate, monkeypatch, capsys, *arguments):
    monkeypatch.setattr(sys, "argv", ["evaluate.py", *arguments])
    with pytest.raises(SystemExit) as stop:
        evaluate.main()
    return stop.value.code, capsys.readouterr().err


def test_held_out_needs_a_frozen_config_and_every_family(workspace, monkeypatch, capsys):
    evaluate, _, run, _, folder = workspace
    held = run.read_text()
    one = f"agent:TEST-HELD:{run}"
    code, error = run_main(evaluate, monkeypatch, capsys, "--partition", "held_out", "--run", one)
    assert code == 1 and "requires --frozen-config" in error
    config = folder / "frozen.json"
    config.write_text(json.dumps({"model": "claude-opus-5-5", "effort": "medium", "max_lookups": 6}))
    code, error = run_main(evaluate, monkeypatch, capsys, "--partition", "held_out", "--run", one, "--frozen-config", str(config))
    assert code == 1 and "every held-out family" in error
    assert held == run.read_text()


def test_reviewer_effort_counts_changes_and_time(tmp_path, entries):
    effort = load("reviewer_effort")
    store = ReviewStore(tmp_path / "reviews.jsonl", entries)
    first, second = entries[0]["mapping"]["mapping_id"], entries[1]["mapping"]["mapping_id"]
    store.save(first, "reject", elapsed_seconds=10)
    store.save(first, "accept", elapsed_seconds=5)
    store.save(second, "correct", {"status": "supported", "rationale": "Definition applies.",
                                   "evidence": [{"passage_id": "TEST-SAP-v1:p4:1", "quote": "received at least one dose"}]},
               elapsed_seconds=40)
    summary = effort.effort(entries, ReviewStore(tmp_path / "reviews.jsonl", entries))
    assert summary["decisions"] == {"accept": 1, "correct": 1, "reject": 0, "pending": 1}
    assert summary["decisions_revised"] == 1
    assert summary["corrections"] == {"status_changed": 1, "links_added": 1, "links_removed": 0, "rationale_changed": 1}
    assert (summary["components_timed"], summary["total_seconds"], summary["median_seconds_per_component"]) == (2, 55.0, 27.5)


def test_coverage_report_reads_development_only():
    coverage = load("coverage_report")
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text())
    report = coverage.coverage(manifest)
    assert report["partition"] == "development"
    assert set(report["by_family"]) == {f["family_id"] for f in manifest["families"] if f["partition"] == "development"}
    assert report["total"]["components"] == sum(family["components"] for family in report["by_family"].values())
