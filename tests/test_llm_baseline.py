import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from traceability.llm_baseline import NOT_FOUND_TEXT, run_baseline, summarize
from traceability.review import load_run

from conftest import METHOD, OTHER_VISIT, POPULATION, SAP_ID, SAP_VERSION, entry

ROOT = Path(__file__).resolve().parents[1]
FAMILY = {"family_id": "TEST", "sap": {"document_id": SAP_ID, "version": SAP_VERSION},
          "shells": [{"document_id": "TEST-TABLE-1", "authenticity": "authentic", "linked_sap_id": SAP_ID}]}
# Fictional SAP pages. Page numbers follow the fixture passages.
PAGES = [(item[1], item[1] + 1, f"{item[2]}\n\n{item[3]}\n", "pdf_text") for item in (POPULATION, METHOD, OTHER_VISIT)]
RULES = [{"convention_id": "not-applicable-em-dash", "scope": "fixtures", "rule": "em dash"}]


def answer(status, evidence=(), questions=(), conventions=()):
    return {"status": status, "rationale": "Read the whole SAP.", "open_questions": list(questions),
            "evidence": [{"page": page, "quote": quote} for page, quote in evidence], "convention_ids": list(conventions)}


class FakeClient:
    def __init__(self, *outputs, stop_reason="end_turn"):
        self.outputs, self.calls, self.stop_reason = list(outputs), [], stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        usage = SimpleNamespace(model_dump=lambda: {"input_tokens": 10, "output_tokens": 2, "cache_read_input_tokens": 5})
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(self.outputs.pop(0)))],
                               stop_reason=self.stop_reason, model=kwargs["model"], usage=usage)


def components(count=1):
    return [entry(key, "table_row", "Change from baseline, LS mean (SE)")["component"]
            for key in ("ls-mean", "population", "dash-note")[:count]]


def run(client, count=1, log=None):
    return list(run_baseline(FAMILY, components(count), PAGES, RULES, client, "claude-opus-5-5", "medium", log))


def test_model_sees_whole_sap_once_cached_and_no_tools(tmp_path):
    client = FakeClient(answer("supported", [(9, "Least squares means and standard errors will be presented by treatment group, using the FAS.")]))
    run(client, log=tmp_path / "log.jsonl")
    call = client.calls[0]
    instructions, document = call["system"]
    assert "cache_control" not in instructions and document["cache_control"] == {"type": "ephemeral"}
    assert all(f"=== SAP page {page} ===" in document["text"] for page in (4, 9, 11))
    assert POPULATION[3] in document["text"] and OTHER_VISIT[3] in document["text"]
    assert "tools" not in call and call["output_config"]["format"]["type"] == "json_schema"
    assert json.loads(call["messages"][0]["content"])["display_conventions"] == []
    assert json.loads((tmp_path / "log.jsonl").read_text())["component_id"] == "TEST-TABLE-1:ls-mean"


def test_verified_quote_lands_in_the_agent_passage_window():
    quote = "Least squares means and standard errors will be presented by treatment group, using the FAS."
    result = run(FakeClient(answer("supported", [(9, quote)])))[0]
    evidence = result["mapping"]["assessment"]["evidence"][0]
    assert (evidence["page"], evidence["section"], evidence["quote"]) == (9, "7.2 Primary endpoint analysis", quote)
    assert result["retrieval"]["candidates"][0]["passage_id"] == evidence["passage_id"] == f"{SAP_ID}:p9:1"
    assert quote in result["retrieval"]["candidates"][0]["text"]
    assert result["baseline"]["citations"] == [{"page": 9, "quote": quote, "outcome": "verified"}]


def test_wrong_page_and_invented_quotes_are_kept_and_flagged():
    result = run(FakeClient(answer("supported", [
        (4, "Change from baseline at Week 24 will be summarized"), (9, "LS means will be shown with 95% confidence intervals")])))[0]
    assert [check["outcome"] for check in result["baseline"]["citations"]] == ["on_another_page", "not_found"]
    assert len(result["mapping"]["assessment"]["evidence"]) == 2
    assert {passage["text"] for passage in result["retrieval"]["candidates"]} == {NOT_FOUND_TEXT}
    assert summarize([result], "m", "medium")["citation_accuracy"] == 0.0


@pytest.mark.parametrize("bad", [
    answer("supported"), answer("needs_review"), answer("not_found_in_supplied_sap", [(4, "dose")]),
    answer("not_found_in_supplied_sap", conventions=["not-applicable-em-dash"]),
])
def test_rule_breaking_answers_are_recorded_as_rejected_without_a_retry(bad):
    client = FakeClient(bad, bad)
    result = run(client)[0]
    assert len(client.calls) == 1 and result["baseline"]["rule_failures"]
    assert result["mapping"]["assessment"]["status"] == "needs_review"
    assert result["mapping"]["assessment"]["evidence"] == []


def test_refusal_is_recorded_as_no_usable_answer():
    result = run(FakeClient(answer("supported", [(4, "dose")]), stop_reason="refusal"))[0]
    assert result["baseline"]["rule_failures"] == ["no usable answer"]


def test_output_is_a_valid_run_file_the_scorer_can_read(tmp_path):
    client = FakeClient(
        answer("supported", [(4, "received at least one dose"), (9, "Least squares means and standard errors")]),
        answer("partially_supported", [(4, "includes all randomized participants")], ["Which section applies it?"]),
        answer("not_found_in_supplied_sap"))
    results = run(client, count=3)
    schema = json.loads((ROOT / "schemas/traceability.schema.json").read_text())
    validator = Draft202012Validator({"$ref": "#/$defs/mapping", "$defs": schema["$defs"]})
    assert all(validator.is_valid(item["mapping"]) for item in results)
    path = tmp_path / "run.jsonl"
    path.write_text("".join(json.dumps(item) + "\n" for item in results))
    assert len(load_run(path)) == 3
    spec = importlib.util.spec_from_file_location("scorer", ROOT / "benchmark/score_development_mappings.py")
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    from test_score_mappings import references
    report = scorer.report("all", scorer.score(results, references(), {})["all"])
    assert (report["status_correct"], report["matched_links"], report["proposed_links"]) == (2, 3, 3)
    assert (report["complete_components"], report["correct_abstentions"]) == (2, 1)
    assert results[2]["mapping"]["assessment"]["rationale"].endswith("Searches run: read of the whole supplied SAP text, pages 4 to 11.")
    total = summarize(results, "claude-opus-5-5", "medium")
    assert (total["citations"], total["citation_accuracy"], total["token_usage"]["input_tokens"]) == (3, 1.0, 30)


def test_component_from_another_sap_is_refused():
    other = dict(FAMILY, shells=[{"document_id": "TEST-TABLE-1", "authenticity": "authentic", "linked_sap_id": "OTHER"}])
    with pytest.raises(ValueError, match="does not match the selected SAP"):
        list(run_baseline(other, components(), PAGES, RULES, FakeClient(), "m", "medium"))
