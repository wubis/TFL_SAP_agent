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


def test_search_needs_a_sap_index(base):
    status, text = call(base[0] + "/api/search?q=baseline")
    assert status == 400 and "--family and --pdf" in json.loads(text)["error"]
