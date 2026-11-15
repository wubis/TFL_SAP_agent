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
        (folder / "components.jsonl").write_text("".join(json.dumps(item["component"]) + "\n" for item in entries))
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
    assert results["systems"]["agent"]["citation_accuracy"] == {
        "checked_against": ["passage text in the run file"], "citations": 2, "verified": 2, "rate": 1.0}
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
            "--retrieval", f"keyword_search:TEST-HELD:{saved}", "--retrieval", f"keyword_search:TEST-HELD-2:{saved}",
            "--pdf", "TEST-HELD:sap.pdf", "--pdf", "TEST-HELD-2:sap.pdf"]


def fictional_sap(family=None, pdf=None):
    """Stands in for reading a SAP PDF: the fictional passages and page text the fixtures were cut from."""
    from conftest import METHOD, OTHER_VISIT, POPULATION
    items = (POPULATION, METHOD, OTHER_VISIT)
    return {item[0]: item[3] for item in items}, {item[1]: f"{item[2]} {item[3]}" for item in items}


def open_freeze_gates(evaluate, monkeypatch):
    """Unit tests of the later gates skip the git checks, which have their own tests below."""
    monkeypatch.setattr(evaluate.freezing, "freeze_problems", lambda root, frozen: [])
    monkeypatch.setattr(evaluate.freezing, "frozen_file_problems", lambda root, path: [])
    monkeypatch.setattr(evaluate.freezing, "git", lambda root, *arguments: "abc123")
    monkeypatch.setattr(evaluate.mappings, "sap_sources", fictional_sap)


def reference_reads(evaluate, monkeypatch):
    """Record every reference-annotation file the runner opens."""
    opened, real = [], evaluate.read_jsonl
    monkeypatch.setattr(evaluate, "read_jsonl", lambda path: (opened.append(path.name) if "reference" in path.name else None) or real(path))
    return opened


def test_held_out_gates_run_before_any_reference_is_read(workspace, monkeypatch, capsys):
    evaluate, _, run, saved, folder = workspace
    opened = reference_reads(evaluate, monkeypatch)
    record = folder / "benchmark/final-evaluation-record.json"
    code, error = run_main(evaluate, monkeypatch, capsys, "--partition", "held_out", "--run", f"agent:TEST-HELD:{run}")
    assert code == 1 and "requires --frozen-config" in error
    code, error = run_main(evaluate, monkeypatch, capsys, *held_arguments(folder, run, saved, {"status": "draft"}))
    assert code == 1 and "must be benchmark/frozen-config-<date>.json" in error and "not a frozen file" in error
    outside = folder.parent / "frozen-config-2026-12-01.json"
    outside.write_text(json.dumps(FROZEN))
    code, error = run_main(evaluate, monkeypatch, capsys, "--partition", "held_out", "--frozen-config", str(outside),
                           "--run", f"agent:TEST-HELD:{run}")
    assert code == 1 and "must be the file committed in this repository" in error
    open_freeze_gates(evaluate, monkeypatch)
    complete = held_arguments(folder, run, saved)
    # One system alone cannot pass: the frozen roster names two.
    code, error = run_main(evaluate, monkeypatch, capsys, *complete[:8], *complete[12:])
    assert code == 1 and "names systems ['agent', 'keyword_search'], and runs were given for ['agent']" in error
    # A missing family cannot pass.
    code, error = run_main(evaluate, monkeypatch, capsys, *complete[:6], *complete[8:])
    assert code == 1 and "agent needs exactly one run for every held-out family" in error
    # The SAP itself must be supplied so quotations are checked against the source.
    code, error = run_main(evaluate, monkeypatch, capsys, *complete[:12])
    assert code == 1 and "give the original SAP PDF with --pdf" in error
    # An output path that cannot be written is caught before the run is spent.
    blocked = folder / "run.jsonl" / "report.md"
    code, error = run_main(evaluate, monkeypatch, capsys, *complete, "--out-md", str(blocked))
    assert code == 1 and "cannot write" in error
    assert opened == [] and not record.exists()
    record.write_text(json.dumps({"status": "failed after references were opened"}))
    code, error = run_main(evaluate, monkeypatch, capsys, *complete)
    assert code == 1 and "already been run (status: failed after references were opened)" in error
    assert opened == []


@pytest.mark.parametrize("change, message", [
    ({"model": "claude-haiku-5-5"}, "model is 'claude-haiku-5-5', frozen is 'claude-opus-5-5'"),
    ({"max_lookups": 12}, "max_lookups is 12, frozen is 6"),
    ({"ocr": False}, "ocr is False, frozen is True"),
    ({"code_fingerprint": "0000"}, "differs from the frozen code"),
    ({"code_fingerprint": None}, "differs from the frozen code"),
    ({"uncommitted_changes": True}, "uncommitted code changes"),
    ({"limit": 3}, "limited to its first 3 components"),
    ({"system": "llm_baseline"}, "the file was produced as 'llm_baseline'"),
    (None, "records no settings"),
])
def test_run_settings_must_equal_the_frozen_configuration(workspace, monkeypatch, capsys, entries, change, message):
    evaluate, _, run, saved, folder = workspace
    open_freeze_gates(evaluate, monkeypatch)
    opened = reference_reads(evaluate, monkeypatch)
    settings = None if change is None else {**AGENT_SETTINGS, **change}
    run.write_text("".join(json.dumps({**item, "run_settings": settings}) + "\n" for item in entries))
    code, error = run_main(evaluate, monkeypatch, capsys, *held_arguments(folder, run, saved))
    assert code == 1 and message in error and not (folder / "benchmark/final-evaluation-record.json").exists()
    assert opened == []


def test_fallback_model_partial_run_and_mixed_settings_are_refused(workspace, monkeypatch, capsys, entries):
    evaluate, _, run, saved, folder = workspace
    open_freeze_gates(evaluate, monkeypatch)
    opened = reference_reads(evaluate, monkeypatch)
    record = folder / "benchmark/final-evaluation-record.json"
    write = lambda items, **extra: run.write_text("".join(json.dumps({**item, "run_settings": AGENT_SETTINGS, **extra}) + "\n" for item in items))
    write(entries, agent={"served_models": ["claude-opus-5-5", "claude-opus-4-8"]})
    code, error = run_main(evaluate, monkeypatch, capsys, *held_arguments(folder, run, saved))
    assert code == 1 and "calls were served by claude-opus-4-8, not the frozen model" in error
    write(entries[:2])
    code, error = run_main(evaluate, monkeypatch, capsys, *held_arguments(folder, run, saved))
    assert code == 1 and "the run has 2 components and does not cover exactly the 3 in the inventory" in error
    assert "TEST-TABLE-1" not in error
    saved.write_text("".join(json.dumps({**item["retrieval"], "run_settings": {**KEYWORD_SETTINGS, "top_k": 5}}) + "\n" for item in entries))
    write(entries)
    code, error = run_main(evaluate, monkeypatch, capsys, *held_arguments(folder, run, saved))
    assert code == 1 and "top_k is 5, frozen needs at least 10" in error
    lines = [json.dumps({**item, "run_settings": {**AGENT_SETTINGS, "effort": effort}}) for item, effort in zip(entries, ("medium", "high", "medium"))]
    run.write_text("\n".join(lines) + "\n")
    code, error = run_main(evaluate, monkeypatch, capsys, *held_arguments(folder, run, saved))
    assert code == 1 and "records carry different run settings" in error
    assert opened == [] and not record.exists()


def test_unsigned_held_out_annotations_block_the_run(workspace, monkeypatch, capsys):
    evaluate, manifest, run, saved, folder = workspace
    open_freeze_gates(evaluate, monkeypatch)
    manifest["families"][1]["annotation_review"] = {**SIGNED, "signed_off_by": None}
    manifest["families"][2]["annotation_review"] = {**SIGNED, "signed_off_by": "annotator one"}
    (folder / "data/source-manifest.json").write_text(json.dumps(manifest))
    code, error = run_main(evaluate, monkeypatch, capsys, *held_arguments(folder, run, saved))
    assert code == 1 and "TEST-HELD: the reference annotations have no recorded sign-off" in error
    assert "TEST-HELD-2: the annotator cannot sign off their own annotations" in error
    assert not (folder / "benchmark/final-evaluation-record.json").exists()


def test_complete_held_out_run_writes_a_record_and_cannot_repeat(workspace, monkeypatch, capsys):
    evaluate, _, run, saved, folder = workspace
    open_freeze_gates(evaluate, monkeypatch)
    arguments = held_arguments(folder, run, saved)
    monkeypatch.setattr(sys, "argv", ["evaluate.py", *arguments])
    evaluate.main()
    report = capsys.readouterr().out
    assert "held_out partition" in report and "- agent: code_commit abc123, code_fingerprint f1f1, effort medium" in report
    assert "Quotations for agent were checked against the SAP PDF." in report
    record = json.loads((folder / "benchmark/final-evaluation-record.json").read_text())
    assert (record["status"], record["code_commit"]) == ("completed", "abc123")
    assert record["systems"] == {"agent": ["TEST-HELD", "TEST-HELD-2"], "keyword_search": ["TEST-HELD", "TEST-HELD-2"]}
    assert record["results"]["systems"]["agent"]["pooled"]["all"]["components"] == 6
    code, error = run_main(evaluate, monkeypatch, capsys, *arguments)
    assert code == 1 and "already been run (status: completed)" in error


def test_failure_after_references_open_spends_the_run_and_names_no_component(workspace, monkeypatch, capsys):
    evaluate, _, run, saved, folder = workspace
    open_freeze_gates(evaluate, monkeypatch)
    # The references disagree with the inventory, which only shows once they are opened.
    path = folder / "benchmark/held_out/TEST-HELD/reference-annotations.jsonl"
    path.write_text("\n".join(path.read_text().splitlines()[:2]) + "\n")
    arguments = held_arguments(folder, run, saved)
    code, error = run_main(evaluate, monkeypatch, capsys, *arguments)
    assert code == 1 and "failed after references were opened (ValueError)" in error and "TEST-TABLE-1" not in error
    record = json.loads((folder / "benchmark/final-evaluation-record.json").read_text())
    assert record["status"] == "failed after references were opened" and "results" not in record
    code, error = run_main(evaluate, monkeypatch, capsys, *arguments)
    assert code == 1 and "already been run" in error and "A rerun is a team decision" in error


def test_run_file_text_is_not_trusted_when_the_sap_is_supplied(workspace, entries):
    evaluate, manifest, run, _, _ = workspace
    forged = json.loads(json.dumps(entries))
    passage = forged[1]["retrieval"]["candidates"][0]
    passage.update(passage_id="TEST-SAP-v1:p4:forged", page=4, text="A forged passage: received at least one dose, and more.")
    forged[1]["mapping"]["assessment"] = {
        "status": "supported", "rationale": "x", "convention_ids": [], "open_questions": [],
        "evidence": [{"passage_id": passage["passage_id"], "page": 4, "section": "4.1", "quote": "A forged passage", "extraction": "pdf_text"}]}
    run.write_text("".join(json.dumps({**item, "run_settings": AGENT_SETTINGS}) + "\n" for item in forged))
    trusting = evaluate.evaluate(manifest, "development", [("agent", "TEST", run)], [])["systems"]["agent"]
    assert trusting["pooled"]["all"]["matched_links"] == 3 and trusting["citation_accuracy"]["verified"] == 3
    evaluate.mappings.sap_sources = fictional_sap
    checked = evaluate.evaluate(manifest, "development", [("agent", "TEST", run)], [], {"TEST": Path("sap.pdf")})["systems"]["agent"]
    assert (checked["pooled"]["all"]["matched_links"], checked["pooled"]["all"]["unverified_links"]) == (2, 1)
    assert checked["citation_accuracy"] == {"checked_against": ["the SAP PDF"], "citations": 3, "verified": 2, "rate": 0.667}


def make_repo(tmp_path):
    """A git repository holding a copy of the real code and scripts, with a fictional manifest and held-out benchmark."""
    import shutil
    import subprocess
    git = lambda *arguments: subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.com",
                                             *arguments], check=True, capture_output=True)
    shutil.copytree(ROOT / "traceability", tmp_path / "traceability", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "schemas", tmp_path / "schemas")
    (tmp_path / "benchmark/held_out/TEST-HELD").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    for path in [*(ROOT / "benchmark").glob("*.py"), ROOT / "benchmark/display-conventions.json",
                 ROOT / "benchmark/evaluation-config.draft.json"]:
        shutil.copy(path, tmp_path / "benchmark" / path.name)
    shutil.copy(ROOT / "requirements.txt", tmp_path / "requirements.txt")
    (tmp_path / ".gitignore").write_text("__pycache__/\n")
    (tmp_path / "data/source-manifest.json").write_text(json.dumps({"partition_status": "frozen", "families": [
        {"family_id": "TEST-HELD", "partition": "held_out", "annotation_review": SIGNED,
         "sap": {"document_id": "TEST-SAP-v1", "version": "1"},
         "shells": [{"document_id": "TEST-TABLE-1", "type": "table", "authenticity": "authentic", "linked_sap_id": "TEST-SAP-v1"}]}]}))
    held = tmp_path / "benchmark/held_out/TEST-HELD"
    (held / "reference-annotations.jsonl").write_text("".join(json.dumps(record) + "\n" for record in references().values()))
    git("init", "-q")
    return git


def load_from(folder, name):
    spec = importlib.util.spec_from_file_location(f"{name}_copy", folder / "benchmark" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freeze_requires_a_clean_tree_then_detects_later_changes(tmp_path):
    freezing = load("freeze_config")
    git = make_repo(tmp_path)
    with pytest.raises(ValueError, match="Commit or discard"):
        freezing.freeze(tmp_path, "2026-12-01")
    git("add", "-A"); git("commit", "-q", "-m", "code")
    target = freezing.freeze(tmp_path, "2026-12-01")
    frozen = json.loads(target.read_text())
    assert frozen["status"] == "frozen" and frozen["model_identifiers"] == {"llm_baseline": "claude-opus-5-5", "agent": "claude-opus-5-5"}
    assert freezing.frozen_file_problems(tmp_path, target) == ["The frozen configuration has uncommitted changes or is not committed"]
    git("add", "-A"); git("commit", "-q", "-m", "freeze")
    assert freezing.git(tmp_path, "rev-parse", "HEAD") != frozen["code_commit"]
    assert freezing.frozen_file_problems(tmp_path, target) == []
    assert freezing.freeze_problems(tmp_path, frozen) == ["Tag the commit that holds the frozen configuration before the held-out run"]
    git("tag", "evaluation-freeze-2026-12-01")
    assert freezing.freeze_problems(tmp_path, frozen) == []
    changed = "Code, schema, benchmark records, manifest, or dependencies changed since the freeze"
    # Every kind of protected file is covered: agent code, a gate script, a scorer, reference answers, and dependencies.
    for relative in ("traceability/agent.py", "benchmark/sign_off.py", "benchmark/adjudication.py", "benchmark/evaluate.py",
                     "benchmark/held_out/TEST-HELD/reference-annotations.jsonl", "requirements.txt", "data/source-manifest.json"):
        path = tmp_path / relative
        original = path.read_text()
        path.write_text(original + "\n")
        assert freezing.freeze_problems(tmp_path, frozen) == ["There are uncommitted changes to frozen files"], relative
        git("commit", "-q", "-am", "changed after the freeze"); git("tag", f"later-{relative.replace('/', '-')}")
        assert freezing.freeze_problems(tmp_path, frozen) == [changed], relative
        path.write_text(original)
        git("commit", "-q", "-am", "restored"); git("tag", f"restored-{relative.replace('/', '-')}")
        assert freezing.freeze_problems(tmp_path, frozen) == [], relative
    # Documentation and the frozen file itself are outside the fingerprint.
    (tmp_path / "benchmark/notes.md").write_text("notes\n")
    git("add", "-A"); git("commit", "-q", "-m", "docs"); git("tag", "docs")
    assert freezing.freeze_problems(tmp_path, frozen) == []
    # Editing the frozen settings after they were committed is caught, even when recommitted and retagged.
    target.write_text(target.read_text().replace('"max_lookups": 6', '"max_lookups": 12'))
    assert freezing.frozen_file_problems(tmp_path, target) == ["The frozen configuration has uncommitted changes or is not committed"]
    git("commit", "-q", "-am", "more lookups"); git("tag", "retagged")
    assert freezing.frozen_file_problems(tmp_path, target) == ["The frozen configuration was changed after it was first committed"]
    assert freezing.freeze_problems(tmp_path, {"status": "draft"}) == ["The configuration is not a frozen file written by benchmark/freeze_config.py"]


def test_freeze_commit_tag_run_evaluate_sequence(tmp_path, monkeypatch, capsys):
    """The documented workflow with the real scripts and all three frozen systems. No gate is replaced.

    The only stand-ins are the model client and the SAP text, because the data is fictional.
    """
    from test_agent import FAMILY, PAGES, RULES, SCHEMA, METHOD, METHOD_QUOTE, FakeClient, submit, use
    from test_llm_baseline import FakeClient as BaselineClient, answer
    from traceability.agent import run_agent
    from traceability.llm_baseline import run_baseline
    from traceability.provenance import run_settings
    from traceability.retrieval import segment_pages
    from conftest import entry
    git = make_repo(tmp_path)
    family = {**FAMILY, "family_id": "TEST-HELD"}
    components = [{**entry(key, "table_row", label)["component"], "family_id": "TEST-HELD"} for key, label in
                  (("ls-mean", "Change from baseline, LS mean (SE)"), ("population", "Full Analysis Set"), ("dash-note", "Em dash note"))]
    (tmp_path / "benchmark/held_out/TEST-HELD/components.jsonl").write_text("".join(json.dumps(c) + "\n" for c in components))
    git("add", "-A"); git("commit", "-q", "-m", "code at the end of development")
    freezing = load_from(tmp_path, "freeze_config")
    target = freezing.freeze(tmp_path, "2026-12-01")
    git("add", "-A"); git("commit", "-q", "-m", "Freeze evaluation configuration"); git("tag", "evaluation-freeze-2026-12-01")
    frozen = json.loads(target.read_text())
    assert sorted(frozen["systems"]) == ["agent", "keyword_search", "llm_baseline"]
    evaluate = load_from(tmp_path, "evaluate")
    assert evaluate.ROOT == tmp_path
    passages = {passage.passage_id: passage.text for passage in segment_pages("TEST-SAP-v1", PAGES)}
    monkeypatch.setattr(evaluate.mappings, "sap_sources",
                        lambda family, pdf: (passages, {page: " ".join(text.split()) for page, _, text, _ in PAGES}))
    out = tmp_path.parent / "runs"
    out.mkdir()

    def produce(served="claude-opus-5-5", count=3):
        """Runs made by the real agent and baseline code from the tagged commit, with a stand-in model client."""
        agent_settings = run_settings("agent", root=tmp_path, model="claude-opus-5-5", effort="medium", first_candidates=8,
                                      max_lookups=6, max_submissions=2, retrieval="BM25", ocr=True, limit=None)
        turns = [[submit("supported", [(METHOD[0], METHOD_QUOTE)])], [use("read_page", page=4)],
                 [submit("needs_review", questions=["Which section applies the population?"])],
                 [use("search_sap", query="em dash")], [submit("not_found_in_supplied_sap")]]
        client = FakeClient(*turns)
        agent = list(run_agent(family, components[:count], PAGES, RULES, client, served, "medium", SCHEMA))
        baseline_client = BaselineClient(answer("supported", [(9, METHOD_QUOTE)]), answer("supported", [(4, "received at least one dose")]),
                                         answer("not_found_in_supplied_sap"))
        baseline = list(run_baseline(family, components, PAGES, RULES, baseline_client, "claude-opus-5-5", "medium"))
        baseline_settings = run_settings("llm_baseline", root=tmp_path, model="claude-opus-5-5", effort="medium", tools="none",
                                         retries=0, ocr=True, limit=None)
        keyword_settings = run_settings("keyword_search", root=tmp_path, method="BM25", top_k=10, ocr=True)
        files = {}
        for name, records in (("agent", [{**item, "run_settings": agent_settings} for item in agent]),
                              ("llm_baseline", [{**item, "run_settings": baseline_settings} for item in baseline]),
                              ("keyword_search", [{**item["retrieval"], "run_settings": keyword_settings} for item in baseline])):
            files[name] = out / f"{name}-{served}-{count}.jsonl"
            files[name].write_text("".join(json.dumps(record, default=str) + "\n" for record in records))
        return agent_settings, files

    def arguments(files):
        return ["--partition", "held_out", "--frozen-config", str(target), "--pdf", "TEST-HELD:sap.pdf",
                "--run", f"agent:TEST-HELD:{files['agent']}", "--run", f"llm_baseline:TEST-HELD:{files['llm_baseline']}",
                "--retrieval", f"keyword_search:TEST-HELD:{files['keyword_search']}"]

    record = tmp_path / "benchmark/final-evaluation-record.json"
    settings, files = produce()
    # Runs made after the frozen file was committed record a later commit and still match by content.
    assert settings["code_commit"] != frozen["code_commit"] and settings["code_fingerprint"] == frozen["code_fingerprint"]
    assert settings["uncommitted_changes"] is False

    # Refused before any reference is read: a fallback model, a partial run, and a missing system.
    _, fallback = produce(served="claude-opus-4-8")
    code, error = run_main(evaluate, monkeypatch, capsys, *arguments(fallback))
    assert code == 1 and "served by claude-opus-4-8, not the frozen model" in error
    _, partial = produce(count=2)
    code, error = run_main(evaluate, monkeypatch, capsys, *arguments(partial))
    assert code == 1 and "does not cover exactly the 3 in the inventory" in error
    code, error = run_main(evaluate, monkeypatch, capsys, *arguments(files)[:8])
    assert code == 1 and "names systems ['agent', 'keyword_search', 'llm_baseline'], and runs were given for ['agent']" in error
    assert not record.exists()

    # The complete, matching submission passes every real gate.
    monkeypatch.setattr(sys, "argv", ["evaluate.py", *arguments(files)])
    evaluate.main()
    report = capsys.readouterr().out
    assert "held_out partition" in report and "| agent | all | 3 |" in report and "| llm_baseline | all | 3 |" in report
    saved = json.loads(record.read_text())
    assert saved["status"] == "completed" and saved["code_commit"] == settings["code_commit"]
    assert saved["systems"] == {"agent": ["TEST-HELD"], "keyword_search": ["TEST-HELD"], "llm_baseline": ["TEST-HELD"]}
    assert saved["results"]["systems"]["agent"]["citation_accuracy"]["checked_against"] == ["the SAP PDF"]
    code, error = run_main(evaluate, monkeypatch, capsys, *arguments(files))
    assert code == 1 and "already been run (status: completed)" in error

    # Tuning the agent after the freeze is caught by the checkout check and by each run's own fingerprint.
    record.unlink()
    agent_code = tmp_path / "traceability/agent.py"
    agent_code.write_text(agent_code.read_text() + "\n# tuned after the freeze\n")
    git("commit", "-q", "-am", "tuned after the freeze"); git("tag", "later")
    tuned_settings, tuned = produce()
    assert tuned_settings["code_fingerprint"] != frozen["code_fingerprint"]
    code, error = run_main(evaluate, monkeypatch, capsys, *arguments(tuned))
    assert code == 1 and "changed since the freeze" in error and not record.exists()
    code, error = run_main(evaluate, monkeypatch, capsys, *arguments(files))
    assert code == 1 and "changed since the freeze" in error and not record.exists()


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
