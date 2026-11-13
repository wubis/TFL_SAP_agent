"""Build schema-valid mappings from explicit assessments of retrieved SAP passages."""

import argparse
import json
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator

from traceability.retrieval import ROOT


def read_jsonl(path):
    records = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        record = json.loads(line)
        if not isinstance(record, dict) or not isinstance(record.get("component_id"), str):
            raise ValueError(f"{path.name} line {line_number}: expected a component ID")
        component_id = record["component_id"]
        if component_id in records:
            raise ValueError(f"Duplicate component ID in {path.name}: {component_id}")
        records[component_id] = record
    return records


def assessment_for(result, decision, conventions):
    if decision is None:
        question = "Which candidate passages, if any, support this component in its analysis context?"
        return {"status": "needs_review", "rationale": "Contextual evidence has yet to be assessed.",
                "evidence": [], "convention_ids": [], "open_questions": [question]}
    allowed = {"component_id", "status", "rationale", "open_questions", "convention_ids", "evidence"}
    if set(decision) - allowed or not {"status", "rationale"} <= decision.keys():
        raise ValueError("Expected an assessment with a status and rationale")
    convention_ids = decision.get("convention_ids", [])
    if not isinstance(convention_ids, list) or not all(isinstance(item, str) and item in conventions for item in convention_ids):
        raise ValueError("Unknown display convention")
    if convention_ids and (not result.get("constructed_shell") or decision["status"] != "not_found_in_supplied_sap"):
        raise ValueError("The current display convention requires a constructed shell and no SAP evidence")

    candidates = {passage["passage_id"]: passage for passage in result["candidates"]}
    evidence = []
    citations = decision.get("evidence", [])
    if not isinstance(citations, list):
        raise ValueError("Evidence selections must be an array")
    for citation in citations:
        if not isinstance(citation, dict) or set(citation) != {"passage_id", "quote"}:
            raise ValueError("Each evidence selection must contain a passage ID and exact quote")
        passage_id = citation["passage_id"]
        quote = citation["quote"]
        if not isinstance(passage_id, str) or not isinstance(quote, str) or not quote.strip():
            raise ValueError("Evidence requires a passage ID and exact quote")
        candidate = candidates.get(passage_id)
        quote = " ".join(quote.split())
        if candidate is None or quote not in candidate["text"]:
            raise ValueError(f"Quote does not match the retrieved passage: {passage_id}")
        evidence.append({"passage_id": passage_id, "page": candidate["page"],
                         "section": candidate["section"] or "Unidentified section",
                         "quote": quote, "extraction": candidate.get("extraction", "pdf_text")})
    return {"status": decision["status"], "rationale": decision["rationale"], "evidence": evidence,
            "convention_ids": convention_ids, "open_questions": decision.get("open_questions", [])}


def build_mappings(results, decisions, conventions, schema):
    if not results:
        raise ValueError("No retrieval results were supplied")
    if decisions.keys() - results.keys():
        raise ValueError("An assessment references a component absent from the retrieval results")
    validator = Draft202012Validator({"$ref": "#/$defs/mapping", "$defs": schema["$defs"]})
    run_id = uuid.uuid4().hex
    mappings = []
    for component_id, result in results.items():
        try:
            mapping = {"record_type": "mapping", "mapping_id": f"{run_id}:{component_id}",
                       "component_id": component_id, "sap_id": result["sap_id"], "sap_version": result["sap_version"],
                       "assessment": assessment_for(result, decisions.get(component_id), conventions)}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{component_id}: invalid results or assessment: {exc}") from exc
        error = next(validator.iter_errors(mapping), None)
        if error is not None:
            raise ValueError(f"{component_id}: {error.message}")
        mappings.append(mapping)
    return mappings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True, help="JSONL emitted by the retrieval command")
    parser.add_argument("--assessments", type=Path, help="JSONL contextual decisions with evidence selections")
    args = parser.parse_args()
    schema = json.loads((ROOT / "schemas/traceability.schema.json").read_text(encoding="utf-8"))
    convention_doc = json.loads((ROOT / "benchmark/display-conventions.json").read_text(encoding="utf-8"))
    try:
        results = read_jsonl(args.results)
        decisions = read_jsonl(args.assessments) if args.assessments else {}
        conventions = {item["convention_id"] for item in convention_doc["conventions"]}
        for mapping in build_mappings(results, decisions, conventions, schema):
            print(json.dumps(mapping, ensure_ascii=False))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
