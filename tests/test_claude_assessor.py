import json
from types import SimpleNamespace

from traceability.claude_assessor import assess, problems

from conftest import METHOD, OTHER_VISIT, POPULATION


def request():
    return {
        "instructions": "Assess whether the supplied SAP evidence supports this shell component.",
        "component": {"kind": "table_row", "label": "Change from baseline, LS mean (SE)", "context": {}},
        "sap_version": "1", "constructed_shell": False, "display_conventions": [],
        "candidates": [{"passage_id": item[0], "page": item[1], "section": item[2], "text": item[3],
                        "extraction": "pdf_text"} for item in (METHOD, POPULATION, OTHER_VISIT)],
    }


def answer(status="supported", evidence=(), questions=(), conventions=()):
    return {"status": status, "rationale": "Checked population, endpoint, visit, and statistic.",
            "evidence": [{"passage_id": pid, "quote": quote} for pid, quote in evidence],
            "open_questions": list(questions), "convention_ids": list(conventions)}


class FakeClient:
    """Stands in for anthropic.Anthropic. Returns queued answers and records each call."""

    def __init__(self, *outputs, stop_reason="end_turn"):
        self.outputs, self.calls, self.stop_reason = list(outputs), [], stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = json.dumps(self.outputs.pop(0))
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=self.stop_reason,
                               model=kwargs["model"], usage=SimpleNamespace(model_dump=lambda: {"output_tokens": 1}))


GOOD = answer(evidence=[(METHOD[0], "Least squares means and standard errors will be presented by treatment group, using the FAS.")])
WRONG_VISIT_QUOTE = answer(evidence=[(METHOD[0], "Change from baseline at Week 24 will be summarized")])


def test_problems_catches_what_the_pipeline_would_reject():
    req = request()
    assert problems(GOOD, req) == []
    assert "not an exact continuous substring" in problems(WRONG_VISIT_QUOTE, req)[0]
    assert "not one of the supplied candidates" in problems(answer(evidence=[("unknown", "x")]), req)[0]
    assert "needs at least one quotation" in problems(answer(), req)[0]
    assert "needs at least one open question" in problems(answer("needs_review"), req)[0]
    assert "must have empty evidence" in problems(answer("not_found_in_supplied_sap", GOOD["evidence"] and [(METHOD[0], "ANCOVA model")]), req)[0]
    assert "was not supplied" in problems(answer("not_found_in_supplied_sap", conventions=["not-applicable-em-dash"]), req)[0]


def test_valid_answer_returns_after_one_call_and_logs_prompt_and_model(tmp_path):
    client, log = FakeClient(GOOD), tmp_path / "log.jsonl"
    assert assess(request(), client, "claude-opus-5-5", "medium", 2, log) == GOOD
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["output_config"]["effort"] == "medium"
    assert call["output_config"]["format"]["type"] == "json_schema" and call["fallbacks"] == "default"
    assert "instructions" not in json.loads(call["messages"][0]["content"])
    record = json.loads(log.read_text())
    assert record["requested_model"] == "claude-opus-5-5" and record["check_failures"] == []
    assert "exact string match" in record["system"] and record["messages"][0]["role"] == "user"


def test_failed_quote_gets_one_retry_naming_the_failure():
    client = FakeClient(WRONG_VISIT_QUOTE, GOOD)
    assert assess(request(), client, "claude-opus-5-5", "medium", 2) == GOOD
    retry = client.calls[1]["messages"]
    assert [message["role"] for message in retry] == ["user", "assistant", "user"]
    assert "not an exact continuous substring" in retry[2]["content"]


def test_attempt_limit_hands_the_component_to_a_reviewer():
    client = FakeClient(WRONG_VISIT_QUOTE, WRONG_VISIT_QUOTE, GOOD)
    decision = assess(request(), client, "claude-opus-5-5", "medium", 2)
    assert len(client.calls) == 2
    assert decision["status"] == "needs_review" and decision["evidence"] == []
    assert problems(decision, request()) == []


def test_refusal_is_handed_off_without_retry():
    client = FakeClient(GOOD, GOOD, stop_reason="refusal")
    assert assess(request(), client, "claude-opus-5-5", "medium", 2)["status"] == "needs_review"
    assert len(client.calls) == 1
