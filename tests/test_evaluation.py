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


SIGNED = {"annotated_by": "Annotator One", "signed_off_by": "Reviewer Two", "signed_off_on": "2026-11-20",
          "disagreements_settled_by": None}
AGENT_SETTINGS = {"system": "agent", "model": "claude-opus-5-5", "effort": "medium", "first_candidates": 8,
                  "max_lookups": 6, "max_submissions": 2, "retrieval": "BM25", "ocr": True,
                  "code_commit": "abc123", "code_fingerprint": "f1f1", "uncommitted_changes": False}
KEYWORD_SETTINGS = {"system": "keyword_search", "method": "BM25", "top_k": 10, "ocr": True,
                    "code_commit": "abc123", "code_fingerprint": "f1f1", "uncommitted_changes": False}
FROZEN = {"status": "frozen", "code_commit": "abc000", "code_fingerprint": "f1f1", "model_identifiers": {"agent": "claude-opus-5-5"},
          "sap_text": {"ocr_for_pages_without_text": True},
          "systems": {"agent": {"command": "traceability.agent", "model": "claude-opus-5-5", "effort": "medium",
                                "first_candidates": 8, "max_lookups": 6, "max_submissions": 2, "retrieval": "BM25"},
                      "keyword_search": {"command": "traceability.retrieval", "method": "BM25", "top_k": [1, 5, 10]}}}


@pytest.fixture
def workspace(tmp_path, monkeypatch, entries):
    evaluate = load("evaluate")
    shells = [{"document_id": "TEST-TABLE-1", "type": "table"}]
    manifest = {"partition_status": "frozen", "families": [
        {"family_id": "TEST", "partition": "development", "shells": shells},
        {"family_id": "TEST-HELD", "partition": "held_out", "shells": shells, "annotation_review": SIGNED},
        {"family_id": "TEST-HELD-2", "partition": "held_out", "shells": shells, "annotation_review": SIGNED}]}
    (tmp_path / "data").mkdir()
    (tmp_path / "data/source-manifest.json").write_text(json.dumps(manifest))
    for partition, family in (("development", "TEST"), ("held_out", "TEST-HELD"), ("held_out", "TEST-HELD-2")):
        folder = tmp_path / "benchmark" / partition / family
        folder.mkdir(parents=True)
        (folder / "reference-annotations.jsonl").write_text("".join(json.dumps(r) + "\n" for r in references().values()))
    run = tmp_path / "run.jsonl"
    run.write_text("".join(json.dumps({**item, "run_settings": AGENT_SETTINGS, "agent": {"served_models": ["claude-opus-5-5"]}}) + "\n"
                           for item in entries))
    saved = tmp_path / "retrieval.jsonl"
    saved.write_text("".join(json.dumps({**item["retrieval"], "run_settings": KEYWORD_SETTINGS}) + "\n" for item in entries))
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


def held_arguments(folder, run, saved, frozen=FROZEN):
    config = folder / "frozen.json"
    config.write_text(json.dumps(frozen))
    return ["--partition", "held_out", "--frozen-config", str(config),
            "--run", f"agent:TEST-HELD:{run}", "--run", f"agent:TEST-HELD-2:{run}",
            "--retrieval", f"keyword_search:TEST-HELD:{saved}", "--retrieval", f"keyword_search:TEST-HELD-2:{saved}"]


def test_held_out_gates_run_before_any_reference_is_read(workspace, monkeypatch, capsys):
    evaluate, _, run, saved, folder = workspace
    opened = []
    monkeypatch.setattr(evaluate, "read_jsonl", lambda path: opened.append(path) or [])
    code, error = run_main(evaluate, monkeypatch, capsys, "--partition", "held_out", "--run", f"agent:TEST-HELD:{run}")
    assert code == 1 and "requires --frozen-config" in error
    draft = held_arguments(folder, run, saved, {"status": "draft"})
    code, error = run_main(evaluate, monkeypatch, capsys, *draft)
    assert code == 1 and "not a frozen file" in error
    monkeypatch.setattr(evaluate.freezing, "freeze_problems", lambda root, frozen: [])
    complete = held_arguments(folder, run, saved)
    # One system alone cannot pass: the frozen roster names two.
    code, error = run_main(evaluate, monkeypatch, capsys, *complete[:8])
    assert code == 1 and "names systems ['agent', 'keyword_search'], and runs were given for ['agent']" in error
    # A missing family cannot pass.
    code, error = run_main(evaluate, monkeypatch, capsys, *complete[:6], *complete[8:])
    assert code == 1 and "agent needs exactly one run for every held-out family" in error
    (folder / "benchmark/final-evaluation-record.json").write_text("{}")
    code, error = run_main(evaluate, monkeypatch, capsys, *complete)
    assert code == 1 and "already been run" in error
    assert opened == []


@pytest.mark.parametrize("change, message", [
    ({"model": "claude-haiku-5-5"}, "model is 'claude-haiku-5-5', frozen is 'claude-opus-5-5'"),
    ({"max_lookups": 12}, "max_lookups is 12, frozen is 6"),
    ({"ocr": False}, "ocr is False, frozen is True"),
    ({"code_fingerprint": "0000"}, "differs from the frozen code"),
    ({"code_fingerprint": None}, "differs from the frozen code"),
    ({"uncommitted_changes": True}, "uncommitted code changes"),
    ({"system": "llm_baseline"}, "the file was produced as 'llm_baseline'"),
    (None, "records no settings"),
])
def test_run_settings_must_equal_the_frozen_configuration(workspace, monkeypatch, capsys, entries, change, message):
    evaluate, _, run, saved, folder = workspace
    monkeypatch.setattr(evaluate.freezing, "freeze_problems", lambda root, frozen: [])
    settings = None if change is None else {**AGENT_SETTINGS, **change}
    run.write_text("".join(json.dumps({**item, "run_settings": settings}) + "\n" for item in entries))
    code, error = run_main(evaluate, monkeypatch, capsys, *held_arguments(folder, run, saved))
    assert code == 1 and message in error and not (folder / "benchmark/final-evaluation-record.json").exists()


def test_keyword_run_with_too_few_candidates_or_mixed_settings_is_refused(workspace, monkeypatch, capsys, entries):
    evaluate, _, run, saved, folder = workspace
    monkeypatch.setattr(evaluate.freezing, "freeze_problems", lambda root, frozen: [])
    saved.write_text("".join(json.dumps({**item["retrieval"], "run_settings": {**KEYWORD_SETTINGS, "top_k": 5}}) + "\n" for item in entries))
    code, error = run_main(evaluate, monkeypatch, capsys, *held_arguments(folder, run, saved))
    assert code == 1 and "top_k is 5, frozen needs at least 10" in error
    lines = [json.dumps({**item, "run_settings": {**AGENT_SETTINGS, "effort": effort}}) for item, effort in zip(entries, ("medium", "high", "medium"))]
    run.write_text("\n".join(lines) + "\n")
    code, error = run_main(evaluate, monkeypatch, capsys, *held_arguments(folder, run, saved))
    assert code == 1 and "records carry different run settings" in error


def test_unsigned_held_out_annotations_block_the_run(workspace, monkeypatch, capsys):
    evaluate, manifest, run, saved, folder = workspace
    monkeypatch.setattr(evaluate.freezing, "freeze_problems", lambda root, frozen: [])
    manifest["families"][1]["annotation_review"] = {**SIGNED, "signed_off_by": None}
    manifest["families"][2]["annotation_review"] = {**SIGNED, "signed_off_by": "annotator one"}
    (folder / "data/source-manifest.json").write_text(json.dumps(manifest))
    code, error = run_main(evaluate, monkeypatch, capsys, *held_arguments(folder, run, saved))
    assert code == 1 and "TEST-HELD: the reference annotations have no recorded sign-off" in error
    assert "TEST-HELD-2: the annotator cannot sign off their own annotations" in error
    assert not (folder / "benchmark/final-evaluation-record.json").exists()


def test_complete_held_out_run_writes_a_record_and_cannot_repeat(workspace, monkeypatch, capsys):
    evaluate, _, run, saved, folder = workspace
    monkeypatch.setattr(evaluate.freezing, "freeze_problems", lambda root, frozen: [])
    monkeypatch.setattr(evaluate.freezing, "git", lambda root, *arguments: "abc123")
    arguments = held_arguments(folder, run, saved)
    monkeypatch.setattr(sys, "argv", ["evaluate.py", *arguments])
    evaluate.main()
    report = capsys.readouterr().out
    assert "held_out partition" in report and "- agent: code_commit abc123, code_fingerprint f1f1, effort medium" in report and "model claude-opus-5-5" in report
    record = json.loads((folder / "benchmark/final-evaluation-record.json").read_text())
    assert record["code_commit"] == "abc123"
    assert record["systems"] == {"agent": ["TEST-HELD", "TEST-HELD-2"], "keyword_search": ["TEST-HELD", "TEST-HELD-2"]}
    code, error = run_main(evaluate, monkeypatch, capsys, *arguments)
    assert code == 1 and "already been run" in error


def make_repo(tmp_path):
    """A small git repository with the protected paths, a draft configuration, and a fictional held-out benchmark."""
    import subprocess
    git = lambda *arguments: subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.com",
                                             *arguments], check=True, capture_output=True)
    for folder in ("benchmark/held_out/TEST-HELD", "traceability", "data", "schemas"):
        (tmp_path / folder).mkdir(parents=True)
    (tmp_path / "traceability/agent.py").write_text("LIMIT = 6\n")
    (tmp_path / "data/source-manifest.json").write_text(json.dumps({"partition_status": "frozen", "families": [
        {"family_id": "TEST-HELD", "partition": "held_out", "shells": [{"document_id": "TEST-TABLE-1", "type": "table"}],
         "annotation_review": SIGNED}]}))
    (tmp_path / "benchmark/held_out/TEST-HELD/reference-annotations.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in references().values()))
    (tmp_path / "benchmark/evaluation-config.draft.json").write_text(json.dumps({
        "status": "draft", "sap_text": {"ocr_for_pages_without_text": True},
        "systems": {"agent": {"command": "traceability.agent", "model": "claude-opus-5-5", "effort": "medium",
                              "first_candidates": 8, "max_lookups": 6, "max_submissions": 2, "retrieval": "BM25"}}}))
    git("init", "-q")
    return git


def test_freeze_requires_a_clean_tree_then_detects_later_changes(tmp_path):
    freezing = load("freeze_config")
    git = make_repo(tmp_path)
    with pytest.raises(ValueError, match="Commit or discard"):
        freezing.freeze(tmp_path, "2026-12-01")
    git("add", "-A"); git("commit", "-q", "-m", "code")
    target = freezing.freeze(tmp_path, "2026-12-01")
    frozen = json.loads(target.read_text())
    assert frozen["status"] == "frozen" and frozen["model_identifiers"] == {"agent": "claude-opus-5-5"}
    git("add", "-A"); git("commit", "-q", "-m", "freeze")
    assert freezing.git(tmp_path, "rev-parse", "HEAD") != frozen["code_commit"]
    assert freezing.freeze_problems(tmp_path, frozen) == ["Tag the commit that holds the frozen configuration before the held-out run"]
    git("tag", "evaluation-freeze-2026-12-01")
    assert freezing.freeze_problems(tmp_path, frozen) == []
    (tmp_path / "traceability/agent.py").write_text("LIMIT = 9\n")
    assert "There are uncommitted changes to frozen files" in freezing.freeze_problems(tmp_path, frozen)
    git("commit", "-q", "-am", "tuned after the freeze"); git("tag", "later")
    assert freezing.freeze_problems(tmp_path, frozen) == ["Code, schema, conventions, or manifest changed since the freeze"]
    assert freezing.freeze_problems(tmp_path, {"status": "draft"}) == ["The configuration is not a frozen file written by benchmark/freeze_config.py"]


def test_freeze_commit_tag_run_evaluate_sequence(tmp_path, monkeypatch, capsys, entries):
    """The documented workflow end to end, with no gate replaced: freeze, commit the frozen file, tag, run, evaluate."""
    from traceability.provenance import run_settings
    evaluate, freezing = load("evaluate"), load("freeze_config")
    monkeypatch.setattr(evaluate, "ROOT", tmp_path)
    git = make_repo(tmp_path)
    git("add", "-A"); git("commit", "-q", "-m", "code at the end of development")
    target = freezing.freeze(tmp_path, "2026-12-01")
    git("add", "-A"); git("commit", "-q", "-m", "Freeze evaluation configuration"); git("tag", "evaluation-freeze-2026-12-01")
    frozen = json.loads(target.read_text())

    def produce_run(name):
        settings = run_settings("agent", root=tmp_path, model="claude-opus-5-5", effort="medium", first_candidates=8,
                                max_lookups=6, max_submissions=2, retrieval="BM25", ocr=True)
        path = tmp_path.parent / name
        path.write_text("".join(json.dumps({**item, "run_settings": settings}) + "\n" for item in entries))
        return settings, path

    settings, run = produce_run("held-run.jsonl")
    # The run was produced one commit after the frozen code commit, and still matches by content.
    assert settings["code_commit"] != frozen["code_commit"] and settings["code_fingerprint"] == frozen["code_fingerprint"]
    arguments = ["--partition", "held_out", "--frozen-config", str(target), "--run", f"agent:TEST-HELD:{run}"]
    monkeypatch.setattr(sys, "argv", ["evaluate.py", *arguments])
    evaluate.main()
    assert "held_out partition" in capsys.readouterr().out
    record = json.loads((tmp_path / "benchmark/final-evaluation-record.json").read_text())
    assert record["code_commit"] == settings["code_commit"] and record["systems"] == {"agent": ["TEST-HELD"]}
    code, error = run_main(evaluate, monkeypatch, capsys, *arguments)
    assert code == 1 and "already been run" in error

    # Tuning the agent after the freeze is caught twice: by the checkout check and by the run's own fingerprint.
    (tmp_path / "benchmark/final-evaluation-record.json").unlink()
    (tmp_path / "traceability/agent.py").write_text("LIMIT = 9\n")
    git("commit", "-q", "-am", "tuned after the freeze"); git("tag", "later")
    _, tuned = produce_run("tuned-run.jsonl")
    code, error = run_main(evaluate, monkeypatch, capsys, "--partition", "held_out", "--frozen-config", str(target),
                           "--run", f"agent:TEST-HELD:{tuned}")
    assert code == 1 and "changed since the freeze" in error
    monkeypatch.setattr(evaluate.freezing, "freeze_problems", lambda root, config: [])
    code, error = run_main(evaluate, monkeypatch, capsys, "--partition", "held_out", "--frozen-config", str(target),
                           "--run", f"agent:TEST-HELD:{tuned}")
    assert code == 1 and "differs from the frozen code" in error
    assert not (tmp_path / "benchmark/final-evaluation-record.json").exists()


def test_budget_estimates_high_and_stops_at_the_cap():
    from traceability.budget import Budget
    budget = Budget("claude-opus-5-5", max_usd=0.05)
    budget.add({"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 10000,
                "cache_creation_input_tokens": 2000, "server_tool_use": None})
    assert budget.spent == pytest.approx((1000 * 4 + 2000 * 8 + 10000 * 0.2 + 500 * 20) / 1e6)
    assert not budget.exhausted()
    budget.add({"input_tokens": 5000, "output_tokens": 0})
    assert budget.exhausted() and budget.report() == {"estimated_usd": 0.052, "max_usd": 0.05}
    with pytest.raises(ValueError, match="No price is recorded"):
        Budget("some-other-model", max_usd=1)
    assert Budget("some-other-model").report() == {"estimated_usd": None, "max_usd": None}


def test_reviewer_effort_counts_changes_and_minutes_by_condition(tmp_path, entries):
    effort = load("reviewer_effort")
    store = ReviewStore(tmp_path / "reviews.jsonl", entries)
    first, second, third = (entry["mapping"]["mapping_id"] for entry in entries)
    own = {"status": "supported", "rationale": "Definition applies.",
           "evidence": [{"passage_id": "TEST-SAP-v1:p4:1", "quote": "received at least one dose"}]}
    store.save(first, "reject", elapsed_seconds=60, reviewer="R1", condition="with_proposals")
    store.save(first, "accept", elapsed_seconds=30, reviewer="R1", condition="with_proposals")
    store.save(second, "correct", own, elapsed_seconds=120, reviewer="R1", condition="with_proposals")
    store.save(third, "correct", {"status": "not_found_in_supplied_sap", "rationale": "Searched for em dash rules."},
               elapsed_seconds=240, reviewer="R1", condition="without_proposals")
    summary = effort.effort(entries, ReviewStore(tmp_path / "reviews.jsonl", entries))
    assert summary["reviewers"] == ["R1"] and summary["decisions"] == {"accept": 1, "correct": 2, "reject": 0, "pending": 0}
    assert summary["decisions_revised"] == 1
    assert summary["corrections_to_proposals"] == {"corrections": 1, "status_changed": 1, "links_added": 1,
                                                   "links_removed": 0, "rationale_changed": 1}
    assert summary["by_condition"]["with_proposals"]["median_minutes_per_component"] == 1.75
    assert summary["by_condition"]["without_proposals"] == {
        "components_timed": 1, "total_minutes": 4.0, "median_minutes_per_component": 4.0,
        "mean_minutes_per_component": 4.0, "decisions": {"correct": 1}}


def test_crossover_plan_swaps_halves_and_balances_shell_types(entries):
    plan_module = load("crossover_plan")
    from conftest import entry
    run = [entry(f"c{number}", "table_row", f"Row {number}") for number in range(12)]
    for number, item in enumerate(run):
        shell = ("TABLE", "FIGURE", "LISTING")[number % 3]
        item["component"]["shell_id"] = shell
    types = {"TABLE": "table", "FIGURE": "figure", "LISTING": "listing"}
    plan = plan_module.build_plan(run, types, ["R1", "R2"], 6, seed=3)
    first, second = plan["assignments"]["R1"], plan["assignments"]["R2"]
    assert plan["shell_types"] == {"figure": 2, "listing": 2, "table": 2} and len(first) == 6
    assert set(first) == set(second) == set(plan["order"]["R1"]) == set(plan["order"]["R2"])
    assert all(first[component] != second[component] for component in first)
    assert sorted(first.values()).count("with_proposals") == 3
    assert plan == plan_module.build_plan(run, types, ["R1", "R2"], 6, seed=3)
    with pytest.raises(ValueError, match="exactly two different reviewers"):
        plan_module.build_plan(run, types, ["R1", "R1"], 6, seed=3)
    with pytest.raises(ValueError, match="only 12 components"):
        plan_module.build_plan(run, types, ["R1", "R2"], 20, seed=3)


def test_adjudication_is_blind_merges_systems_and_needs_reasons(entries, tmp_path):
    adjudication = load("adjudication")
    from conftest import METHOD, cited
    spare = cited(METHOD, "analyzed with an ANCOVA model")
    spare["page"] = 9
    entries[1]["mapping"]["assessment"] = {"status": "supported", "rationale": "x", "convention_ids": [],
                                           "open_questions": [], "evidence": [spare]}
    run = tmp_path / "run.jsonl"
    run.write_text("".join(json.dumps(item) + "\n" for item in entries))
    items, key = adjudication.unmatched_items([("agent", "TEST", run), ("llm_baseline", "TEST", run)], lambda family: references())
    assert len(items) == 1 and "system" not in items[0] and "mapping_id" not in items[0]
    assert sorted(owner["system"] for owner in key[items[0]["item_id"]]) == ["agent", "llm_baseline"]
    assert items[0]["proposed_quote"] == "analyzed with an ANCOVA model" and "received at least one dose" in items[0]["reference_quotes"]
    row = dict(items[0])
    assert adjudication.apply([row], key)["agent"] == {"unmatched_links": 1, "ruled_equivalent": 0, "ruled_unsupported": 0, "undecided": 1}
    row.update(decision="unsupported")
    with pytest.raises(ValueError, match="needs a reason"):
        adjudication.apply([row], key)
    row.update(decision="unsure", reason="Method sentence, but the label is a population.", adjudicator="Reviewer A")
    assert adjudication.apply([row], key)["agent"]["undecided"] == 1
    row.update(second_decision="unsupported", second_reason="Does not define or apply the population.", second_adjudicator="Reviewer A")
    with pytest.raises(ValueError, match="different person"):
        adjudication.apply([row], key)
    row.update(second_adjudicator="Reviewer B")
    assert adjudication.apply([row], key) == {
        "agent": {"unmatched_links": 1, "ruled_equivalent": 0, "ruled_unsupported": 1, "undecided": 0},
        "llm_baseline": {"unmatched_links": 1, "ruled_equivalent": 0, "ruled_unsupported": 1, "undecided": 0}}


def test_coverage_report_reads_development_only():
    coverage = load("coverage_report")
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text())
    report = coverage.coverage(manifest)
    assert report["partition"] == "development"
    assert set(report["by_family"]) == {f["family_id"] for f in manifest["families"] if f["partition"] == "development"}
    assert report["total"]["components"] == sum(family["components"] for family in report["by_family"].values())
