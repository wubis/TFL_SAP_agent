import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from traceability.agent import TOOLS, run_agent, summarize
from traceability.review import load_run

from conftest import METHOD, OTHER_VISIT, POPULATION, SAP_ID, SAP_VERSION, entry

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/traceability.schema.json").read_text())
FAMILY = {"family_id": "TEST", "sap": {"document_id": SAP_ID, "version": SAP_VERSION},
          "shells": [{"document_id": "TEST-TABLE-1", "authenticity": "authentic", "linked_sap_id": SAP_ID}]}
EXTRA = ("TEST-SAP-v1:p20:1", 20, "9.1 Display conventions", "Percentages are displayed to one decimal place.")
# Fictional SAP pages. A numbered heading line starts each page so passages carry a section.
PAGES = [(item[1], item[1] + 1, f"{item[2]}\n\n{item[3]}\n", "pdf_text") for item in (POPULATION, METHOD, OTHER_VISIT, EXTRA)]
RULES = [{"convention_id": "not-applicable-em-dash", "scope": "fixtures", "rule": "em dash"}]
METHOD_QUOTE = "Least squares means and standard errors will be presented by treatment group, using the FAS."
POPULATION_QUOTE = "includes all randomized participants who received at least one dose"


def use(name, **arguments):
    return SimpleNamespace(type="tool_use", id=f"call-{name}-{len(json.dumps(arguments))}", name=name, input=arguments)


def submit(status, evidence=(), questions=(), conventions=()):
    return use("submit_assessment", status=status, rationale="Checked population, endpoint, visit, and statistic.",
               evidence=[{"passage_id": pid, "quote": quote} for pid, quote in evidence],
               open_questions=list(questions), convention_ids=list(conventions))


class FakeClient:
    """Stands in for anthropic.Anthropic. Each queued turn is a list of content blocks."""

    def __init__(self, *turns, stop_reason=None):
        self.turns, self.calls, self.stop_reason = list(turns), [], stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.turns.pop(0)
        stop = self.stop_reason or ("tool_use" if any(block.type == "tool_use" for block in content) else "end_turn")
        return SimpleNamespace(content=content, stop_reason=stop, model=kwargs["model"],
                               usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 100, "output_tokens": 10}))


def run(client, **limits):
    components = [entry("ls-mean", "table_row", "Change from baseline, LS mean (SE)")["component"]]
    return list(run_agent(FAMILY, components, PAGES, RULES, client, "claude-opus-5-5", "medium", SCHEMA, **limits))[0]


def results_sent(client, call):
    return client.calls[call]["messages"][-1]["content"]


def test_tools_are_strict_and_first_turn_carries_code_retrieved_candidates():
    assert all(tool["strict"] and tool["input_schema"]["additionalProperties"] is False for tool in TOOLS)
    client = FakeClient([submit("supported", [(METHOD[0], METHOD_QUOTE)])])
    result = run(client)
    first = client.calls[0]
    assert "tool_choice" not in first and [tool["name"] for tool in first["tools"]][-1] == "submit_assessment"
    payload = json.loads(first["messages"][0]["content"])
    assert METHOD[0] in [passage["passage_id"] for passage in payload["candidates"]]
    assert result["mapping"]["assessment"]["status"] == "supported"
    assert result["agent"] == {"lookups": [], "model_calls": 1, "handed_off": False,
                               "usage": {"input_tokens": 100, "output_tokens": 10}, "served_models": ["claude-opus-5-5"]}


def test_model_gathers_more_evidence_then_cites_a_passage_it_looked_up():
    client = FakeClient(
        [use("search_sap", query="display decimal places percentages"), use("read_section", heading="4.1")],
        [submit("supported", [(POPULATION[0], POPULATION_QUOTE), (METHOD[0], METHOD_QUOTE), (EXTRA[0], "one decimal place")])])
    result = run(client, top_k=1)
    sent = results_sent(client, 1)
    assert [block["type"] for block in sent] == ["tool_result", "tool_result"]
    assert json.loads(sent[0]["content"])["lookups_remaining"] == 5
    assert EXTRA[0] in [passage["passage_id"] for passage in json.loads(sent[0]["content"])["passages"]]
    assert [passage["passage_id"] for passage in json.loads(sent[1]["content"])["passages"]] == [POPULATION[0]]
    assert client.calls[1]["messages"][1]["role"] == "assistant"
    evidence = result["mapping"]["assessment"]["evidence"]
    assert [(item["page"], item["section"]) for item in evidence] == [
        (4, "4.1 Analysis populations"), (9, "7.2 Primary endpoint analysis"), (20, "9.1 Display conventions")]
    assert [lookup["tool"] for lookup in result["agent"]["lookups"]] == ["search_sap", "read_section"]
    assert {passage["passage_id"] for passage in result["retrieval"]["candidates"]} >= {POPULATION[0], METHOD[0], EXTRA[0]}


def test_quote_from_the_wrong_visit_is_rejected_then_corrected():
    wrong = submit("supported", [(METHOD[0], "Change from baseline at Week 24 will be summarized")])
    client = FakeClient([wrong], [submit("supported", [(METHOD[0], METHOD_QUOTE)])])
    result = run(client)
    rejection = results_sent(client, 1)[0]
    assert rejection["is_error"] and "not an exact continuous substring" in rejection["content"]
    assert result["mapping"]["assessment"]["evidence"][0]["quote"] == METHOD_QUOTE


def test_passage_never_shown_to_the_model_cannot_be_cited():
    client = FakeClient([submit("supported", [(EXTRA[0], "one decimal place")])],
                        [submit("supported", [(EXTRA[0], "one decimal place")])])
    result = run(client, top_k=1)
    assert "not one of the supplied candidates" in results_sent(client, 1)[0]["content"]
    assert result["agent"]["handed_off"] and result["mapping"]["assessment"]["status"] == "needs_review"
    assert result["mapping"]["assessment"]["evidence"] == []


def test_lookup_limit_is_enforced_and_loop_always_ends_with_a_record():
    endless = [[use("search_sap", query=f"query {number}")] for number in range(20)]
    client = FakeClient(*endless)
    result = run(client, max_lookups=2, max_submissions=1)
    assert len(result["agent"]["lookups"]) == 2
    assert len(client.calls) == 2 + 1 + 3
    assert "No lookups remain" in results_sent(client, 3)[0]["content"]
    assert result["agent"]["handed_off"] and result["mapping"]["assessment"]["status"] == "needs_review"
    assert result["mapping"]["assessment"]["open_questions"]


def test_model_that_stops_without_submitting_is_nudged_once_then_handed_off():
    text = [SimpleNamespace(type="text", text="The row looks supported.")]
    client = FakeClient(text, text, text)
    result = run(client)
    assert len(client.calls) == 2 and "submit_assessment" in client.calls[1]["messages"][-1]["content"]
    assert result["agent"]["handed_off"]


def test_refusal_is_handed_off():
    client = FakeClient([submit("supported", [(METHOD[0], METHOD_QUOTE)])], stop_reason="refusal")
    assert run(client)["agent"]["handed_off"]


def test_abstention_and_run_file_round_trip(tmp_path):
    client = FakeClient([use("search_sap", query="em dash not applicable cell")],
                        [submit("not_found_in_supplied_sap")])
    result = run(client)
    assert result["mapping"]["assessment"] == {
        "status": "not_found_in_supplied_sap", "evidence": [], "convention_ids": [], "open_questions": [],
        "rationale": "Checked population, endpoint, visit, and statistic. Searches run: first keyword retrieval "
                     'for the component (8 passages); search_sap "em dash not applicable cell".'}
    path = tmp_path / "run.jsonl"
    path.write_text(json.dumps(result) + "\n")
    assert len(load_run(path)) == 1
    totals = summarize([result], "claude-opus-5-5", "medium")
    assert (totals["model_calls"], totals["lookups"], totals["handed_off_to_reviewer"]) == (2, {"search_sap": 1}, 0)


def test_convention_is_refused_on_an_authentic_shell():
    answer = submit("not_found_in_supplied_sap", conventions=["not-applicable-em-dash"])
    client = FakeClient([answer], [use("read_page", page=20)], [submit("not_found_in_supplied_sap")])
    run(client)
    assert "was not supplied" in results_sent(client, 1)[0]["content"]


def test_not_found_without_a_lookup_is_sent_back_once_and_costs_no_submission():
    client = FakeClient([submit("not_found_in_supplied_sap")], [use("read_section", heading="9.1")],
                        [submit("not_found_in_supplied_sap")])
    result = run(client, max_submissions=1)
    assert "needs a documented search" in results_sent(client, 1)[0]["content"]
    assessment = result["mapping"]["assessment"]
    assert assessment["status"] == "not_found_in_supplied_sap" and not result["agent"]["handed_off"]
    assert assessment["rationale"].endswith('Searches run: first keyword retrieval for the component (8 passages); read_section "9.1".')


def test_not_found_is_accepted_without_lookups_when_none_are_allowed():
    result = run(FakeClient([submit("not_found_in_supplied_sap")]), max_lookups=0)
    assert result["mapping"]["assessment"]["status"] == "not_found_in_supplied_sap"
