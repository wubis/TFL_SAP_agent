"""A reviewer corrects a mapping with a passage found by search, the app restarts, the matrix is exported, and
the corrected assessment is scored. Everything goes through the HTTP interface and the files it writes."""

import csv
import io
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from traceability.review import ReviewStore, load_run
from traceability.reviewer_app import Session, handler_for

from conftest import passage
from test_score_mappings import references, scorer

FOUND = passage(("TEST-SAP-v1:p4:2", 4, "4.1 Analysis populations",
                 "Participants in the Full Analysis Set received at least one dose and are analyzed as randomized."))


class FakeIndex:
    """Stands in for the SAP search index. Returns one fictional passage that retrieval had missed."""

    def search(self, terms, limit):
        return [FOUND]


def start(run_file, reviews):
    entries = load_run(run_file)
    session = Session(entries, ReviewStore(reviews, entries), {"families": []}, index=FakeIndex())
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(session))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def call(url, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(request) as response:
        return response.read().decode()


def test_correct_restart_export_and_score(tmp_path, run_file, entries):
    reviews = tmp_path / "reviews.jsonl"
    server, url = start(run_file, reviews)
    state = json.loads(call(url + "/api/state"))
    target = next(item for item in state["entries"] if item["component"]["component_id"].endswith(":population"))
    mapping_id = target["mapping"]["mapping_id"]
    assert target["mapping"]["assessment"]["status"] == "needs_review"

    # 1. The reviewer searches the SAP, finds a passage retrieval missed, and corrects the mapping with it.
    found = json.loads(call(url + "/api/search?q=full+analysis+set"))["passages"][0]
    call(url + "/api/open", {"mapping_id": mapping_id})
    saved = json.loads(call(url + "/api/review", {
        "mapping_id": mapping_id, "action": "correct", "elapsed_seconds": 75, "note": "Definition found by search.",
        "correction": {"status": "supported", "rationale": "Section 4.1 defines the population shown in the title.",
                       "evidence": [{"passage_id": found["passage_id"], "quote": "received at least one dose"}]}}))
    assert saved["review"]["corrected_assessment"]["evidence"][0]["section"] == "4.1 Analysis populations"
    accepted = state["entries"][0]["mapping"]["mapping_id"]
    call(url + "/api/review", {"mapping_id": accepted, "action": "accept", "elapsed_seconds": 20})
    server.shutdown()
    server.server_close()

    # 2. The app restarts from the files alone. The decision and the passage the reviewer cited are both back.
    server, url = start(run_file, reviews)
    reopened = next(item for item in json.loads(call(url + "/api/state"))["entries"]
                    if item["mapping"]["mapping_id"] == mapping_id)
    assert reopened["review"]["action"] == "correct" and reopened["review"]["note"] == "Definition found by search."
    assert reopened["reviewer_passages"] == [FOUND]
    assert reopened["mapping"]["assessment"]["status"] == "needs_review"

    # 3. The exported matrix carries the corrected evidence as final and keeps the proposal apart.
    rows = list(csv.DictReader(io.StringIO(call(url + "/export.csv"))))
    row = next(item for item in rows if item["mapping_id"] == mapping_id)
    assert (row["review_action"], row["final_status"], row["final_evidence_origin"]) == ("correct", "supported", "correction")
    assert (row["final_evidence_page"], row["final_evidence_quote"]) == ("4", "received at least one dose")
    assert (row["proposed_status"], row["proposed_evidence"]) == ("needs_review", "")
    pending = next(item for item in rows if item["component_id"].endswith(":dash-note"))
    assert pending["review_action"] == "pending" and pending["final_status"] == ""
    exported = json.loads(call(url + "/export.json"))
    assert sum(item["assessment_after_review"] is not None for item in exported) == 2
    server.shutdown()
    server.server_close()

    # 4. Scoring the reviewed assessments credits the correction, using the passage text saved with the review.
    store = ReviewStore(reviews, load_run(run_file))
    before = scorer.report("all", scorer.score(entries, references(), {})["all"])
    after = scorer.report("all", scorer.score(entries, references(), {}, store.current, store.extra_passages)["all"])
    assert (before["status_correct"], before["matched_anchors"], before["complete_components"]) == (1, 2, 1)
    assert (after["status_correct"], after["matched_anchors"], after["complete_components"]) == (2, 3, 2)
    assert (after["proposed_links"], after["matched_links"], after["unverified_links"]) == (3, 3, 0)
    unsaved = scorer.report("all", scorer.score(entries, references(), {}, store.current, {})["all"])
    assert (unsaved["matched_links"], unsaved["unverified_links"]) == (2, 1)
    events = [json.loads(line) for line in store.timing_path.read_text().splitlines()]
    assert [event["event"] for event in events] == ["opened", "saved", "saved"] and events[1]["elapsed_seconds"] == 75
