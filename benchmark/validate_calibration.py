"""Validate a development family's annotations and optionally check citations against its PDF."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path, record_type, validator):
    records = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        record = json.loads(line)
        error = next(validator.iter_errors(record), None)
        if error is not None:
            raise ValueError(f"{path.name}:{line_number}: {error.message}")
        component_id = record["component_id"]
        if record["record_type"] != record_type or component_id in records:
            raise ValueError(f"{path.name}:{line_number}: unexpected type or duplicate component ID")
        records[component_id] = record
    return records


def check_pdf(pdf, sap, passages):
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != sap["source_pdf_sha256"]:
        raise ValueError("Source PDF checksum does not match the manifest")
    pages = {}
    for passage in passages.values():
        local_page = passage["page"]
        pdf_page = sap["pdf_pages"][0] + local_page - 1
        if pdf_page not in pages:
            output = subprocess.check_output([
                "gs", "-q", "-dBATCH", "-dNOPAUSE", "-sDEVICE=txtwrite",
                f"-dFirstPage={pdf_page}", f"-dLastPage={pdf_page}", "-sOutputFile=-", str(pdf.resolve()),
            ], encoding="utf-8")
            pages[pdf_page] = " ".join(output.split())
        text = pages[pdf_page]
        span = passage.get("text_span")
        if span:
            if span["end"] > len(text):
                raise ValueError(f"Span extends past PDF page {pdf_page}")
            text = text[span["start"]:span["end"]]
        if passage["quote"] not in text:
            raise ValueError(f"Anchor {passage['passage_id']} does not match PDF page {pdf_page}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", help="Development family ID, defaults to the calibration family")
    parser.add_argument("--pdf", type=Path, help="Original family SAP PDF for citation checks with Ghostscript")
    args = parser.parse_args()

    schema = json.loads((ROOT / "schemas/traceability.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
    family_id = args.family or manifest["calibration_family_id"]
    family = next((item for item in manifest["families"] if item["family_id"] == family_id), None)
    if family is None or family["partition"] != "development" or family["source_status"] != "verified_pair":
        parser.error("Select a verified development family")
    sap = family["sap"]
    pdf_pages = sap.get("pdf_pages")
    sap_page_count = pdf_pages[1] - pdf_pages[0] + 1 if pdf_pages else None
    if args.pdf and (not pdf_pages or not sap.get("source_pdf_sha256")):
        parser.error("PDF checks require page bounds and a checksum in the manifest")
    shells = {shell["document_id"]: shell for shell in family["shells"]}
    folder = ROOT / "benchmark" / "development" / family_id
    components = read_jsonl(folder / "components.jsonl", "component", validator)
    annotations = read_jsonl(folder / "reference-annotations.jsonl", "reference_annotation", validator)
    if not components or components.keys() != annotations.keys():
        raise ValueError("Expected exactly one reference annotation per inventory component")

    passages = {}
    for component_id, annotation in annotations.items():
        component = components[component_id]
        shell = shells.get(component["shell_id"])
        if (shell is None or component["family_id"] != family_id
                or component["shell_version"] != shell["version"]
                or annotation["sap_id"] != sap["document_id"] or annotation["sap_id"] != shell["linked_sap_id"]
                or annotation["sap_version"] != sap["version"]):
            raise ValueError(f"{component_id}: inconsistent source IDs or versions")
        evidence = annotation["assessment"]["evidence"]
        evidence_ids = {passage["passage_id"] for passage in evidence}
        grouped_ids = {
            pid for group in annotation["evidence_groups"]
            for alternative in group["alternatives"] for pid in alternative
        }
        if len(evidence_ids) != len(evidence) or evidence_ids != grouped_ids:
            raise ValueError(f"{component_id}: duplicate evidence IDs or inconsistent evidence groups")
        for passage in evidence:
            pid = passage["passage_id"]
            if sap_page_count is not None and passage["page"] > sap_page_count:
                raise ValueError(f"{pid}: page outside the selected SAP")
            span = passage.get("text_span")
            if span and span["start"] >= span["end"]:
                raise ValueError(f"{pid}: span must have a positive length")
            if passages.setdefault(pid, passage) != passage:
                raise ValueError(f"{pid}: inconsistent locations or quotes for one passage ID")

    if args.pdf:
        check_pdf(args.pdf, sap, passages)
    statuses = Counter(record["assessment"]["status"] for record in annotations.values())
    print(f"Validated {len(components)} components, {len(annotations)} annotations, and {len(passages)} evidence citations.")
    if args.pdf:
        print("Verified the PDF checksum and matched every evidence anchor within its cited page and span.")
    for status, count in sorted(statuses.items()):
        print(f"{status}: {count}")


if __name__ == "__main__":
    main()
