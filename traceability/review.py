"""Persist reviewer decisions on proposed mappings and export the traceability matrix."""

import argparse
import csv
import io
import json
import time
from pathlib import Path

from jsonschema import Draft202012Validator

from traceability.mapping import assessment_for
from traceability.retrieval import ROOT


ACTIONS = ("pending", "accept", "correct", "reject")
MATRIX_COLUMNS = (
    "component_id", "shell_id", "shell_version", "kind", "label", "locator",
    "population", "endpoint", "visit", "treatment_groups", "surrounding_labels",
    "sap_id", "sap_version", "mapping_id", "review_action",
    "final_status", "final_evidence_origin", "final_evidence_number", "final_evidence_passage_id",
    "final_evidence_section", "final_evidence_page", "final_evidence_quote", "final_evidence_extraction",
    "final_rationale", "final_convention_ids", "final_open_questions", "reviewer_note",
    "proposed_status", "proposed_rationale", "proposed_evidence", "proposed_convention_ids", "proposed_open_questions",
)
FINAL_EVIDENCE = ("number", "passage_id", "section", "page", "quote", "extraction")


def load_schema():
    return json.loads((ROOT / "schemas/traceability.schema.json").read_text(encoding="utf-8"))


def load_conventions():
    document = json.loads((ROOT / "benchmark/display-conventions.json").read_text(encoding="utf-8"))
    return document["conventions"]


def read_jsonl(path):
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name} line {line_number}: {exc.msg}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{path.name} line {line_number}: expected a JSON object")
        yield record


def bundle(components, results, mappings):
    """Join component, retrieval, and mapping records into pipeline run entries."""
    results = {record["component_id"]: record for record in results}
    mappings = {record["component_id"]: record for record in mappings}
    entries = []
    for component in components:
        component_id = component["component_id"]
        if component_id not in results or component_id not in mappings:
            raise ValueError(f"{component_id}: missing retrieval result or mapping")
        entries.append({"component": component, "retrieval": results[component_id], "mapping": mappings[component_id]})
    if not entries:
        raise ValueError("No component records were supplied")
    return entries


def load_run(path, schema=None):
    """Read a run file in the shell pipeline's output format and check each record against the schema."""
    schema = schema or load_schema()
    validators = {name: Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": schema["$defs"]})
                  for name in ("component", "mapping")}
    entries = []
    seen = set()
    for number, entry in enumerate(read_jsonl(path), 1):
        if not {"component", "retrieval", "mapping"} <= entry.keys():
            raise ValueError(f"{path.name} line {number}: expected component, retrieval, and mapping")
        for name in ("component", "mapping"):
            error = next(validators[name].iter_errors(entry[name]), None)
            if error is not None:
                raise ValueError(f"{path.name} line {number}: invalid {name} ({error.message})")
        component_id = entry["component"]["component_id"]
        if entry["mapping"]["component_id"] != component_id or entry["retrieval"].get("component_id") != component_id:
            raise ValueError(f"{path.name} line {number}: records refer to different components")
        if component_id in seen:
            raise ValueError(f"{path.name} line {number}: duplicate component ID {component_id}")
        seen.add(component_id)
        entries.append(entry)
    if not entries:
        raise ValueError(f"{path.name}: no run entries")
    return entries


class ReviewStore:
    """Append-only JSONL of review records. The latest record for a mapping is its current decision.

    Earlier records stay in the file, so a changed decision remains measurable. Timing events go to a
    sidecar file because the shared review record has no time fields.
    """

    def __init__(self, path, entries, schema=None, conventions=None):
        self.path = Path(path)
        self.timing_path = self.path.with_name(self.path.name + ".timing.jsonl")
        self.entries = {entry["mapping"]["mapping_id"]: entry for entry in entries}
        schema = schema or load_schema()
        self.validator = Draft202012Validator({"$ref": "#/$defs/review", "$defs": schema["$defs"]})
        rules = load_conventions() if conventions is None else conventions
        self.convention_ids = {rule["convention_id"] for rule in rules}
        self.passages_path = self.path.with_name(self.path.name + ".passages.jsonl")
        self.saps = {(entry["mapping"]["sap_id"], entry["mapping"]["sap_version"]) for entry in entries}
        self.extra_passages = {}
        if self.passages_path.exists():
            # Passages a reviewer found by search and cited. They are reloaded so the citation can be audited later.
            for number, record in enumerate(read_jsonl(self.passages_path), 1):
                if (record.get("sap_id"), record.get("sap_version")) not in self.saps:
                    raise ValueError(f"{self.passages_path.name} line {number}: passage is from a different SAP version")
                self.extra_passages[record["passage"]["passage_id"]] = record["passage"]
        self.saved_passages = set(self.extra_passages)
        self.current = {}
        if self.path.exists():
            known = {entry["mapping"]["mapping_id"]: {passage["passage_id"] for passage in entry["retrieval"]["candidates"]}
                     for entry in entries}
            for number, record in enumerate(read_jsonl(self.path), 1):
                error = next(self.validator.iter_errors(record), None)
                if error is not None:
                    raise ValueError(f"{self.path.name} line {number}: invalid review ({error.message})")
                if record["mapping_id"] in self.entries:
                    self.current[record["mapping_id"]] = record
            for mapping_id, record in self.current.items():
                cited = [item["passage_id"] for item in record.get("corrected_assessment", {}).get("evidence", [])]
                lost = [passage_id for passage_id in cited
                        if passage_id not in known[mapping_id] and passage_id not in self.extra_passages]
                if lost:
                    raise ValueError(f"{self.path.name}: a correction cites {len(lost)} passage(s) whose text is not in the "
                                     f"run file or in {self.passages_path.name}. Restore that file so the citation can be audited")

    def add_passages(self, passages):
        """Register SAP passages found by reviewer search so a correction can cite them."""
        for passage in passages:
            self.extra_passages[passage["passage_id"]] = passage

    def build(self, mapping_id, action, correction=None, note=None):
        entry = self.entries.get(mapping_id)
        if entry is None:
            raise ValueError("Unknown mapping ID")
        if action not in ACTIONS:
            raise ValueError("Unknown review action")
        record = {"record_type": "review", "component_id": entry["component"]["component_id"],
                  "mapping_id": mapping_id, "action": action}
        if action == "correct":
            if not isinstance(correction, dict):
                raise ValueError("A correction needs a replacement assessment")
            cited = {item.get("passage_id") for item in correction.get("evidence", []) if isinstance(item, dict)}
            known = {passage["passage_id"] for passage in entry["retrieval"]["candidates"]}
            extra = [self.extra_passages[passage_id] for passage_id in cited - known if passage_id in self.extra_passages]
            result = {**entry["retrieval"], "candidates": [*entry["retrieval"]["candidates"], *extra]}
            corrected = assessment_for(result, correction, self.convention_ids)
            status = corrected["status"]
            if status in ("supported", "partially_supported") and not corrected["evidence"]:
                raise ValueError("This status needs at least one linked SAP quotation")
            if status == "not_found_in_supplied_sap" and corrected["evidence"]:
                raise ValueError("Not found in the supplied SAP cannot carry SAP evidence")
            if status in ("partially_supported", "needs_review") and not corrected["open_questions"]:
                raise ValueError("Partially supported and needs review require an open question")
            record["corrected_assessment"] = corrected
        elif correction is not None:
            raise ValueError("Only a correction carries a replacement assessment")
        if note and note.strip():
            record["note"] = note.strip()
        error = next(self.validator.iter_errors(record), None)
        if error is not None:
            raise ValueError(f"Invalid review: {error.message}")
        return record

    def save(self, mapping_id, action, correction=None, note=None, elapsed_seconds=None, **tags):
        record = self.build(mapping_id, action, correction, note)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = self.entries[mapping_id]
        for passage_id in self.cited_extra(entry, record):
            if passage_id not in self.saved_passages:
                with self.passages_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"sap_id": entry["mapping"]["sap_id"], "sap_version": entry["mapping"]["sap_version"],
                                             "passage": self.extra_passages[passage_id]}, ensure_ascii=False) + "\n")
                self.saved_passages.add(passage_id)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.current[mapping_id] = record
        self.log_event("saved", mapping_id, action=action, elapsed_seconds=elapsed_seconds, **tags)
        return record

    def log_event(self, event, mapping_id, **fields):
        if mapping_id not in self.entries:
            raise ValueError("Unknown mapping ID")
        record = {"event": event, "mapping_id": mapping_id, "at": round(time.time(), 3),
                  **{key: value for key, value in fields.items() if value is not None}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.timing_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def decision(self, mapping_id):
        return self.current.get(mapping_id)

    def cited_extra(self, entry, review):
        """IDs of reviewer-found passages a review cites, in citation order."""
        if not review or review["action"] != "correct":
            return []
        known = {passage["passage_id"] for passage in entry["retrieval"]["candidates"]}
        cited = dict.fromkeys(item["passage_id"] for item in review["corrected_assessment"]["evidence"])
        return [passage_id for passage_id in cited if passage_id not in known and passage_id in self.extra_passages]

    def source_passages(self, entry):
        """Every passage whose text can back a citation for this entry: retrieved, then reviewer-found."""
        review = self.decision(entry["mapping"]["mapping_id"])
        return [*entry["retrieval"]["candidates"], *(self.extra_passages[pid] for pid in self.cited_extra(entry, review))]


def resolve(entry, review):
    """Return the action, the assessment that stands after review, and where its evidence came from."""
    action = review["action"] if review else "pending"
    proposal = entry["mapping"]["assessment"]
    if action == "correct":
        return action, review["corrected_assessment"], "correction"
    return action, proposal, "proposal"


def matrix_rows(entries, reviews):
    """One row per component and standing quotation, so every quotation keeps its own location.

    The final_* columns hold only what stands after a reviewer accepted or corrected the mapping. A
    pending or rejected mapping leaves them empty. The agent's proposal is always in the proposed_*
    columns, so nothing unreviewed or rejected can be read as approved evidence.
    """
    for entry in entries:
        component, mapping = entry["component"], entry["mapping"]
        review = reviews.get(mapping["mapping_id"])
        action, assessment, origin = resolve(entry, review)
        stands = action in ("accept", "correct")
        context, proposal = component["context"], mapping["assessment"]
        base = {
            "component_id": component["component_id"], "shell_id": component["shell_id"],
            "shell_version": component["shell_version"], "kind": component["kind"], "label": component["label"],
            "locator": component["locator"], "population": context["population"] or "",
            "endpoint": context["endpoint"] or "", "visit": context["visit"] or "",
            "treatment_groups": "; ".join(context["treatment_groups"]),
            "surrounding_labels": "; ".join(context["surrounding_labels"]),
            "sap_id": mapping["sap_id"], "sap_version": mapping["sap_version"], "mapping_id": mapping["mapping_id"],
            "review_action": action,
            "final_status": assessment["status"] if stands else "",
            "final_evidence_origin": origin if stands else "",
            "final_rationale": assessment["rationale"] if stands else "",
            "final_convention_ids": "; ".join(assessment["convention_ids"]) if stands else "",
            "final_open_questions": " | ".join(assessment["open_questions"]) if stands else "",
            "reviewer_note": (review or {}).get("note", ""),
            "proposed_status": proposal["status"], "proposed_rationale": proposal["rationale"],
            "proposed_evidence": " | ".join(f"p{item['page']} [{item['section']}] {item['quote']}" for item in proposal["evidence"]),
            "proposed_convention_ids": "; ".join(proposal["convention_ids"]),
            "proposed_open_questions": " | ".join(proposal["open_questions"]),
        }
        evidence = (assessment["evidence"] if stands else []) or [None]
        for number, passage in enumerate(evidence, 1):
            row = {**base, **{f"final_evidence_{name}": "" for name in FINAL_EVIDENCE}}
            if passage is not None:
                row.update(final_evidence_number=number, final_evidence_passage_id=passage["passage_id"],
                           final_evidence_section=passage["section"], final_evidence_page=passage["page"],
                           final_evidence_quote=passage["quote"],
                           final_evidence_extraction=passage.get("extraction", "pdf_text"))
            yield row


def matrix_csv(entries, reviews):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=MATRIX_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(matrix_rows(entries, reviews))
    return output.getvalue()


def matrix_json(entries, reviews):
    records = []
    for entry in entries:
        review = reviews.get(entry["mapping"]["mapping_id"])
        action, assessment, origin = resolve(entry, review)
        records.append({
            "component": entry["component"], "proposal": entry["mapping"], "review": review,
            "review_action": action, "assessment_after_review": assessment if action in ("accept", "correct") else None,
            "evidence_origin": origin if action in ("accept", "correct") else None,
        })
    return json.dumps(records, ensure_ascii=False, indent=2) + "\n"


def summary(entries, reviews):
    counts = dict.fromkeys(ACTIONS, 0)
    for entry in entries:
        review = reviews.get(entry["mapping"]["mapping_id"])
        counts[review["action"] if review else "pending"] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    join = commands.add_parser("bundle", help="Join component, retrieval, and mapping JSONL files into a run file")
    join.add_argument("--components", type=Path, required=True)
    join.add_argument("--results", type=Path, required=True)
    join.add_argument("--mappings", type=Path, required=True)
    export = commands.add_parser("export", help="Export the traceability matrix with reviewer decisions")
    export.add_argument("--run", type=Path, required=True, help="Run file from the shell pipeline or the bundle command")
    export.add_argument("--reviews", type=Path, required=True, help="Review decisions JSONL")
    export.add_argument("--format", choices=("csv", "json"), default="csv")
    args = parser.parse_args()
    try:
        if args.command == "bundle":
            for entry in bundle(read_jsonl(args.components), read_jsonl(args.results), read_jsonl(args.mappings)):
                print(json.dumps(entry, ensure_ascii=False))
            return
        entries = load_run(args.run)
        store = ReviewStore(args.reviews, entries)
        writer = matrix_csv if args.format == "csv" else matrix_json
        print(writer(entries, store.current), end="")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
