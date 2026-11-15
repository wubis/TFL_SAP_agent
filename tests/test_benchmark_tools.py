"""Tests for the benchmark housekeeping scripts, on fictional records in a temporary folder."""

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from conftest import SAP_ID, SAP_VERSION, entry
from test_score_mappings import references

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmark" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_derived_challenge_tags_follow_the_record_and_keep_annotator_tags(tmp_path):
    tags = load("challenge_tags")
    records = references()
    footnote = records["TEST-TABLE-1:dash-note"]
    two_sections = records["TEST-TABLE-1:ls-mean"]
    two_sections["challenge_cases"] = ["paraphrased_label"]
    components = {key: entry(key.split(":")[1], "footnote" if "dash" in key else "table_row", "x")["component"] for key in records}
    (tmp_path / "components.jsonl").write_text("".join(json.dumps(c) + "\n" for c in components.values()))
    (tmp_path / "reference-annotations.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records.values()))
    counts, changed = tags.process(tmp_path, write=False)
    assert changed == 0 and "challenge_cases" not in json.loads((tmp_path / "reference-annotations.jsonl").read_text().splitlines()[2])
    counts, changed = tags.process(tmp_path, write=True)
    written = {r["component_id"]: r for r in map(json.loads, (tmp_path / "reference-annotations.jsonl").read_text().splitlines())}
    assert written["TEST-TABLE-1:ls-mean"]["challenge_cases"] == ["paraphrased_label", "evidence_across_multiple_sections"]
    assert written["TEST-TABLE-1:dash-note"]["challenge_cases"] == ["unsupported_footnote"]
    assert "challenge_cases" not in written["TEST-TABLE-1:population"]
    assert (changed, counts["records_with_a_judged_tag"], counts["unsupported_footnote"]) == (2, 1, 1)
    assert tags.process(tmp_path, write=True)[1] == 0
    schema = json.loads((ROOT / "schemas/traceability.schema.json").read_text())
    validator = Draft202012Validator({"$ref": "#/$defs/referenceAnnotation", "$defs": schema["$defs"]})
    record = {**written["TEST-TABLE-1:ls-mean"], "review_state": "draft"}
    assert validator.is_valid(record)
    assert not validator.is_valid({**record, "challenge_cases": ["made_up_case"]})
    del footnote


def test_sign_off_needs_a_second_person_and_is_checked_by_partition(tmp_path):
    signing = load("sign_off")
    (tmp_path / "data").mkdir()
    manifest = {"families": [
        {"family_id": "DEV", "partition": "development", "annotation_review": {"annotated_by": "Annotator One", "signed_off_by": None, "signed_off_on": None}},
        {"family_id": "HELD", "partition": "held_out", "annotation_review": {"annotated_by": "Annotator One", "signed_off_by": None, "signed_off_on": None}}]}
    (tmp_path / "data/source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    assert len(signing.sign_off_problems(manifest)) == 2 and len(signing.sign_off_problems(manifest, "held_out")) == 1
    with pytest.raises(ValueError, match="cannot sign off their own"):
        signing.sign_off(tmp_path, "HELD", "annotator one", "2026-11-20")
    with pytest.raises(ValueError, match="third person or the group"):
        signing.sign_off(tmp_path, "HELD", "Reviewer Two", "2026-11-20", settled_by="Reviewer Two")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        signing.sign_off(tmp_path, "HELD", "Reviewer Two", "20 Nov")
    signing.sign_off(tmp_path, "HELD", "Reviewer Two", "2026-11-20", settled_by="The group")
    saved = json.loads((tmp_path / "data/source-manifest.json").read_text())
    assert saved["families"][1]["annotation_review"] == {
        "annotated_by": "Annotator One", "signed_off_by": "Reviewer Two", "signed_off_on": "2026-11-20",
        "disagreements_settled_by": "The group"}
    assert signing.sign_off_problems(saved, "held_out") == [] and len(signing.sign_off_problems(saved)) == 1


def test_real_manifest_has_a_sign_off_record_for_every_family():
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text())
    assert all({"annotated_by", "signed_off_by", "signed_off_on", "disagreements_settled_by"} <= set(family["annotation_review"])
               for family in manifest["families"])


def test_live_check_reads_real_command_output(tmp_path):
    """The live check's assertions, applied to run files produced by the real commands with a stand-in client."""
    from test_agent import FAMILY, PAGES, RULES, SCHEMA, METHOD, METHOD_QUOTE, FakeClient, submit, use
    from test_llm_baseline import FakeClient as BaselineClient, answer
    from traceability.agent import run_agent
    from traceability.llm_baseline import run_baseline
    from traceability.provenance import run_settings
    live = load("live_check")
    component = entry("ls-mean", "table_row", "Change from baseline, LS mean (SE)")["component"]
    model = "claude-opus-5-5"
    agent_log, baseline_log = tmp_path / "agent-log.jsonl", tmp_path / "baseline-log.jsonl"
    client = FakeClient([use("read_page", page=9)], [submit("supported", [(METHOD[0], METHOD_QUOTE)])])
    agent = list(run_agent(FAMILY, [component], PAGES, RULES, client, model, "medium", SCHEMA, log=agent_log))
    baseline = list(run_baseline(FAMILY, [component], PAGES, RULES, BaselineClient(answer("supported", [(9, METHOD_QUOTE)])),
                                 model, "medium", baseline_log))
    for name, entries in (("agent", agent), ("llm_baseline", baseline)):
        settings = run_settings(name, model=model, effort="medium")
        (tmp_path / f"{name}-run.jsonl").write_text("".join(json.dumps({**item, "run_settings": settings}, default=str) + "\n" for item in entries))
    agent_checks = dict(live.checks_for_run("agent", tmp_path / "agent-run.jsonl", agent_log, 1, model))
    baseline_checks = dict(live.checks_for_run("llm_baseline", tmp_path / "llm_baseline-run.jsonl", baseline_log, 1, model))
    assert all(agent_checks.values()) and len(agent_checks) == 9
    assert all(baseline_checks.values()) and any("1 cited, 1 verified" in label for label in baseline_checks)
    wrong_model = dict(live.checks_for_run("agent", tmp_path / "agent-run.jsonl", agent_log, 1, "claude-sonnet-5-5"))
    assert [label for label, passed in wrong_model.items() if not passed] == ["agent: requested model served every call (['claude-opus-5-5'])"]
