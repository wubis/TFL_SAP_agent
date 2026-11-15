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


class Session:
    def __init__(self, entries, store, manifest, index=None):
        self.entries = entries
        self.store = store
        self.index = index
        self.shells = {shell["document_id"]: {"type": shell["type"], "label": shell["label"],
                                             "authenticity": shell["authenticity"], "version": shell["version"]}
                       for family in manifest["families"] for shell in family["shells"]}

    def state(self):
        return {
            "entries": [{**entry, "review": self.store.decision(entry["mapping"]["mapping_id"])}
                        for entry in self.entries],
            "shells": {entry["component"]["shell_id"]: self.shells.get(entry["component"]["shell_id"], {})
                       for entry in self.entries},
            "conventions": load_conventions(),
            "summary": summary(self.entries, self.store.current),
            "search_enabled": self.index is not None,
        }

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
                elif url.path in ("/export.csv", "/export.json"):
                    csv_export = url.path.endswith(".csv")
                    writer = matrix_csv if csv_export else matrix_json
                    name = "traceability-matrix." + ("csv" if csv_export else "json")
                    self.send(200, writer(session.entries, session.store.current),
                              "text/csv" if csv_export else "application/json",
                              [("Content-Disposition", f'attachment; filename="{name}"')])
                else:
                    self.send_json({"error": "Not found"}, 404)
            except ValueError as exc:
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
                    session.store.log_event("opened", body.get("mapping_id"))
                    self.send_json({"ok": True})
                elif self.path == "/api/review":
                    elapsed = body.get("elapsed_seconds")
                    if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or elapsed < 0:
                        elapsed = None
                    record = session.store.save(body.get("mapping_id"), body.get("action"),
                                                body.get("correction"), body.get("note"), elapsed)
                    self.send_json({"review": record, "summary": summary(session.entries, session.store.current)})
                else:
                    self.send_json({"error": "Not found"}, 404)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc) or "Invalid request"}, 400)

    return Handler


def build_index(manifest, family_id, pdf, ocr):
    sap = select_family(manifest, family_id)["sap"]
    return BM25(segment_pages(sap["document_id"], extract_pages(sap, pdf, ocr=ocr)))


def make_server(run, reviews, *, family=None, pdf=None, ocr=False, host="127.0.0.1", port=8765):
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
    entries = load_run(run)
    if (family is None) != (pdf is None):
        raise ValueError("SAP search needs both --family and --pdf")
    index = None
    if family is not None:
        if {entry["component"]["family_id"] for entry in entries} != {family}:
            raise ValueError("The run file does not belong to the selected family")
        index = build_index(manifest, family, pdf, ocr)
    session = Session(entries, ReviewStore(reviews, entries), manifest, index)
    return ThreadingHTTPServer((host, port), handler_for(session))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True, help="Run file from the shell pipeline or the bundle command")
    parser.add_argument("--reviews", type=Path, required=True, help="JSONL file that stores review decisions")
    parser.add_argument("--family", help="Family ID, with --pdf, to let the reviewer search the whole paired SAP")
    parser.add_argument("--pdf", type=Path, help="Original paired SAP PDF from the source manifest")
    parser.add_argument("--ocr", action="store_true", help="Use Tesseract for SAP pages with no usable text layer")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        server = make_server(args.run, args.reviews, family=args.family, pdf=args.pdf, ocr=args.ocr, port=args.port)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
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
