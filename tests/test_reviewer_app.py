import json
import threading
import urllib.error
import urllib.request

import pytest

from traceability.reviewer_app import make_server


@pytest.fixture
def base(tmp_path, run_file):
    server = make_server(run_file, tmp_path / "reviews.jsonl", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path / "reviews.jsonl"
    server.shutdown()
    server.server_close()


def call(url, body=None, content_type="application/json"):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": content_type} if data else {})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def test_page_and_state(base):
    url, _ = base
    status, page = call(url + "/")
    assert status == 200 and "TFL to SAP reviewer" in page
    state = json.loads(call(url + "/api/state")[1])
    assert len(state["entries"]) == 3 and state["search_enabled"] is False
    assert state["summary"] == {"pending": 3, "accept": 0, "correct": 0, "reject": 0}
    assert all(item["review"] is None for item in state["entries"])


def test_review_is_saved_and_exported(base):
    url, reviews = base
    state = json.loads(call(url + "/api/state")[1])
    mapping_id = state["entries"][0]["mapping"]["mapping_id"]
    status, body = call(url + "/api/review", {"mapping_id": mapping_id, "action": "accept", "elapsed_seconds": 4})
    assert status == 200 and json.loads(body)["summary"]["accept"] == 1
    assert json.loads(reviews.read_text())["action"] == "accept"
    assert json.loads(call(url + "/api/state")[1])["entries"][0]["review"]["action"] == "accept"
    status, matrix = call(url + "/export.csv")
    assert status == 200 and matrix.splitlines()[1].count("accept") == 1


@pytest.mark.parametrize("body, content_type, message", [
    ({"mapping_id": "missing", "action": "accept"}, "application/json", "Unknown mapping ID"),
    ({"mapping_id": "run1:TEST-TABLE-1:ls-mean", "action": "approve"}, "application/json", "Unknown review action"),
    ({"mapping_id": "run1:TEST-TABLE-1:ls-mean", "action": "accept"}, "text/plain", "Send JSON"),
    ({"mapping_id": "run1:TEST-TABLE-1:ls-mean", "action": "correct"}, "application/json", "replacement assessment"),
])
def test_bad_requests_are_refused_without_writing(base, body, content_type, message):
    url, reviews = base
    status, text = call(url + "/api/review", body, content_type)
    assert status == 400 and message in json.loads(text)["error"]
    assert not reviews.exists()


def test_plan_hides_the_proposal_and_candidates_from_the_page(tmp_path, run_file, entries):
    ids = [item["component"]["component_id"] for item in entries]
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"assignments": {"R1": {ids[0]: "without_proposals", ids[1]: "with_proposals"}},
                                "order": {"R1": [ids[1], ids[0]]}}))
    with pytest.raises(ValueError, match="needs --family and --pdf"):
        make_server(run_file, tmp_path / "reviews.jsonl", port=0, plan=plan, reviewer="R1")
    with pytest.raises(ValueError, match="not named in the plan"):
        make_server(run_file, tmp_path / "reviews.jsonl", port=0, plan=plan, reviewer="R9")
    from traceability.review import ReviewStore, load_run
    from traceability.reviewer_app import Session, apply_plan
    loaded, conditions = apply_plan(load_run(run_file), json.loads(plan.read_text()), "R1")
    store = ReviewStore(tmp_path / "reviews.jsonl", loaded)
    session = Session(loaded, store, {"families": []}, reviewer="R1", conditions=conditions)
    shown, hidden = session.state()["entries"]
    assert shown["component"]["component_id"] == ids[1] and shown["condition"] == "with_proposals"
    assert hidden["condition"] == "without_proposals" and hidden["retrieval"]["candidates"] == []
    assert hidden["mapping"]["assessment"]["evidence"] == [] and "supported" not in json.dumps(hidden["mapping"])
    assert "Least squares" not in json.dumps(hidden)
    with pytest.raises(ValueError, match="Record your own assessment"):
        session.save({"mapping_id": hidden["mapping"]["mapping_id"], "action": "accept"}, 3)
    session.save({"mapping_id": hidden["mapping"]["mapping_id"], "action": "correct",
                  "correction": {"status": "not_found_in_supplied_sap", "rationale": "Searched for the statistic."}}, 90)
    session.save({"mapping_id": hidden["mapping"]["mapping_id"], "action": "correct", "correction": {
        "status": "supported", "rationale": "Own search.",
        "evidence": [{"passage_id": "TEST-SAP-v1:p9:1", "quote": "Least squares means and standard errors"}]}}, 90)
    again = Session(loaded, ReviewStore(tmp_path / "reviews.jsonl", loaded), {"families": []}, reviewer="R1", conditions=conditions)
    reopened = again.state()["entries"][1]
    assert [passage["passage_id"] for passage in reopened["reviewer_passages"]] == ["TEST-SAP-v1:p9:1"]
    assert reopened["retrieval"]["candidates"] == []
    event = json.loads(store.timing_path.read_text().splitlines()[-1])
    assert (event["reviewer"], event["condition"], event["elapsed_seconds"]) == ("R1", "without_proposals", 90)


def test_search_needs_a_sap_index(base):
    status, text = call(base[0] + "/api/search?q=baseline")
    assert status == 400 and "--family and --pdf" in json.loads(text)["error"]
