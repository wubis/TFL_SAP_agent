"""Local reviewer interface for proposed TFL to SAP mappings.

Serves one page on the loopback interface. A reviewer selects a shell component, reads its context,
the proposed status and rationale, and the SAP quotations with version, section, and page, then
accepts, corrects, or rejects the proposal. Decisions append to a JSONL file and survive reopening.
"""

import argparse
import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from traceability.retrieval import BM25, ROOT, extract_pages, segment_pages, select_family, tokens
from traceability.review import ReviewStore, load_conventions, load_run, matrix_csv, matrix_json, summary


PAGE = Path(__file__).with_name("reviewer.html")
MAX_BODY = 1_000_000


BLANK = {"status": "needs_review", "rationale": "No proposal is shown for this component.", "evidence": [],
         "convention_ids": [], "open_questions": ["Trace this component yourself."]}


class Session:
    def __init__(self, entries, store, manifest, index=None, pdf=None, reviewer=None, conditions=None):
        self.entries = entries
        self.store = store
        self.index = index
        self.pdf = pdf
        self.reviewer = reviewer
        self.conditions = conditions or {}
        self.images = {}
        self.shells = {}
        for family in manifest["families"]:
            for shell in family["shells"]:
                pages = shell.get("pdf_pages")
                self.shells[shell["document_id"]] = {
                    "type": shell["type"], "label": shell["label"], "authenticity": shell["authenticity"],
                    "version": shell["version"], "page": pages[0] if pages and pages[0] == pages[1] else None,
                    "family_id": family["family_id"]}

    def condition(self, entry):
        return self.conditions.get(entry["component"]["component_id"], "with_proposals")

    def tags(self, mapping_id):
        entry = self.store.entries.get(mapping_id)
        if entry is None or self.reviewer is None:
            return {}
        return {"reviewer": self.reviewer, "condition": self.condition(entry)}

    def visible(self, entry):
        """What the page may see. Without proposals, the agent's answer and candidates stay on the server."""
        review = self.store.decision(entry["mapping"]["mapping_id"])
        added = [self.store.extra_passages[passage_id] for passage_id in self.store.cited_extra(entry, review)]
        if self.condition(entry) == "with_proposals":
            return {**entry, "review": review, "condition": "with_proposals", "reviewer_passages": added}
        # The reviewer saw no candidates, so every passage they cited is shown back to them, whatever its origin.
        cited = [item["passage_id"] for item in review["corrected_assessment"]["evidence"]] if review and review["action"] == "correct" else []
        sources = {passage["passage_id"]: passage for passage in self.store.source_passages(entry)}
        added = [sources[passage_id] for passage_id in dict.fromkeys(cited) if passage_id in sources]
        return {"component": entry["component"], "review": review, "condition": "without_proposals",
                "reviewer_passages": added,
                "retrieval": {**entry["retrieval"], "candidates": []},
                "mapping": {**entry["mapping"], "assessment": BLANK}}

    def has_image(self, shell_id, family_ids):
        shell = self.shells.get(shell_id, {})
        return self.pdf is not None and shell.get("page") is not None and shell.get("family_id") in family_ids

    def export_entries(self):
        """Entries for the page's export. A proposal the reviewer was not shown is left out of it too."""
        return [entry if self.condition(entry) == "with_proposals"
                else {**entry, "mapping": {**entry["mapping"], "assessment": BLANK}} for entry in self.entries]

    def state(self):
        families = {entry["component"]["family_id"] for entry in self.entries}
        shell_ids = dict.fromkeys(entry["component"]["shell_id"] for entry in self.entries)
        return {
            "entries": [self.visible(entry) for entry in self.entries],
            "shells": {shell_id: {**self.shells.get(shell_id, {}), "has_image": self.has_image(shell_id, families)}
                       for shell_id in shell_ids},
            "conventions": load_conventions(),
            "summary": summary(self.entries, self.store.current),
            "search_enabled": self.index is not None,
            "reviewer": self.reviewer,
        }

    def shell_image(self, shell_id):
        """Render the registered shell page so the reviewer sees the component where it sits."""
        families = {entry["component"]["family_id"] for entry in self.entries}
        if shell_id not in {entry["component"]["shell_id"] for entry in self.entries} or not self.has_image(shell_id, families):
            raise ValueError("No page image is available for this shell")
        if shell_id not in self.images:
            page = self.shells[shell_id]["page"]
            self.images[shell_id] = subprocess.check_output(
                ["gs", "-q", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m", "-r110", f"-dFirstPage={page}",
                 f"-dLastPage={page}", "-sOutputFile=-", str(self.pdf.resolve())], stderr=subprocess.DEVNULL)
        return self.images[shell_id]

    def save(self, body, elapsed):
        mapping_id, action = body.get("mapping_id"), body.get("action")
        entry = self.store.entries.get(mapping_id)
        if entry is not None and self.condition(entry) == "without_proposals" and action not in ("correct", "pending"):
            raise ValueError("No proposal is shown for this component. Record your own assessment")
        return self.store.save(mapping_id, action, body.get("correction"), body.get("note"), elapsed, **self.tags(mapping_id))

    def search(self, query, limit=8):
        if self.index is None:
            raise ValueError("SAP search needs the app to be started with --family and --pdf")
        terms = dict.fromkeys(tokens(query), 1)
        if not terms:
            return []
        passages = self.index.search(terms, limit)
        self.store.add_passages(passages)
        return passages


def handler_for(session):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, content_type="application/json", headers=()):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, payload, status=200):
            self.send(status, json.dumps(payload, ensure_ascii=False))

        def do_GET(self):
            url = urlparse(self.path)
            try:
                if url.path == "/":
                    self.send(200, PAGE.read_bytes(), "text/html")
                elif url.path == "/api/state":
                    self.send_json(session.state())
                elif url.path == "/api/search":
                    query = parse_qs(url.query).get("q", [""])[0]
                    self.send_json({"passages": session.search(query)})
                elif url.path == "/shell.png":
                    self.send(200, session.shell_image(parse_qs(url.query).get("shell_id", [""])[0]), "image/png")
                elif url.path in ("/export.csv", "/export.json"):
                    csv_export = url.path.endswith(".csv")
                    writer = matrix_csv if csv_export else matrix_json
                    name = "traceability-matrix." + ("csv" if csv_export else "json")
                    self.send(200, writer(session.export_entries(), session.store.current),
                              "text/csv" if csv_export else "application/json",
                              [("Content-Disposition", f'attachment; filename="{name}"')])
                else:
                    self.send_json({"error": "Not found"}, 404)
            except (ValueError, subprocess.CalledProcessError, OSError) as exc:
                self.send_json({"error": str(exc)}, 400)

        def do_POST(self):
            try:
                # Browsers cannot send JSON cross-origin without a preflight, which this server never grants.
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    raise ValueError("Send JSON")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise ValueError("Request body is missing or too large")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
                if self.path == "/api/open":
                    session.store.log_event("opened", body.get("mapping_id"), **session.tags(body.get("mapping_id")))
                    self.send_json({"ok": True})
                elif self.path == "/api/review":
                    elapsed = body.get("elapsed_seconds")
                    if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or elapsed < 0:
                        elapsed = None
                    record = session.save(body, elapsed)
                    self.send_json({"review": record, "summary": summary(session.entries, session.store.current)})
                else:
                    self.send_json({"error": "Not found"}, 404)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc) or "Invalid request"}, 400)

    return Handler


def build_index(manifest, family_id, pdf, ocr):
    sap = select_family(manifest, family_id)["sap"]
    return BM25(segment_pages(sap["document_id"], extract_pages(sap, pdf, ocr=ocr)))


def apply_plan(entries, plan, reviewer):
    """Keep the components assigned to this reviewer, in the plan's order, with their conditions."""
    if reviewer not in plan.get("assignments", {}):
        raise ValueError("The reviewer is not named in the plan")
    conditions = plan["assignments"][reviewer]
    by_id = {entry["component"]["component_id"]: entry for entry in entries}
    if set(conditions) - by_id.keys():
        raise ValueError("The plan names components that are not in the run file")
    if set(conditions.values()) - {"with_proposals", "without_proposals"}:
        raise ValueError("Unknown review condition in the plan")
    return [by_id[component_id] for component_id in plan["order"][reviewer]], conditions


def make_server(run, reviews, *, family=None, pdf=None, ocr=False, host="127.0.0.1", port=8765, plan=None, reviewer=None):
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
    entries = load_run(run)
    conditions = None
    if plan is not None:
        entries, conditions = apply_plan(entries, json.loads(Path(plan).read_text(encoding="utf-8")), reviewer)
        if family is None and "without_proposals" in conditions.values():
            raise ValueError("Reviewing without proposals needs --family and --pdf so the reviewer can search the SAP")
    if (family is None) != (pdf is None):
        raise ValueError("SAP search needs both --family and --pdf")
    index = None
    if family is not None:
        if {entry["component"]["family_id"] for entry in entries} != {family}:
            raise ValueError("The run file does not belong to the selected family")
        sap = select_family(manifest, family)["sap"]
        if {(entry["mapping"]["sap_id"], entry["mapping"]["sap_version"]) for entry in entries} != {(sap["document_id"], sap["version"])}:
            raise ValueError("The run file was made against a different SAP version than the one being searched")
        index = build_index(manifest, family, pdf, ocr)
    session = Session(entries, ReviewStore(reviews, entries), manifest, index, pdf, reviewer, conditions)
    return ThreadingHTTPServer((host, port), handler_for(session))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True, help="Run file from the shell pipeline or the bundle command")
    parser.add_argument("--reviews", type=Path, required=True, help="JSONL file that stores review decisions")
    parser.add_argument("--family", help="Family ID, with --pdf, to let the reviewer search the whole paired SAP")
    parser.add_argument("--pdf", type=Path, help="Original paired SAP PDF from the source manifest")
    parser.add_argument("--ocr", action="store_true", help="Use Tesseract for SAP pages with no usable text layer")
    parser.add_argument("--plan", type=Path, help="Crossover plan from benchmark/crossover_plan.py")
    parser.add_argument("--reviewer", help="Reviewer name. Recorded with timing, and required with --plan")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.plan and not args.reviewer:
            raise ValueError("--plan needs --reviewer")
        server = make_server(args.run, args.reviews, family=args.family, pdf=args.pdf, ocr=args.ocr, port=args.port,
                             plan=args.plan, reviewer=args.reviewer)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Reviewer interface at http://127.0.0.1:{server.server_address[1]}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
