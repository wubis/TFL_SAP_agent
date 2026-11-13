"""Page-bounded SAP retrieval for the TFL traceability project."""

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
NUMBERED_HEADING = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,4})\.?\s+[A-Z][A-Za-z -]{2,}\S?.*$")
UNNUMBERED_HEADING = re.compile(r"^[A-Z][A-Z -]{4,}[A-Z]$")
OUTPUT_HEADING = re.compile(r"^Presentation of (?:Treatment Groups|Visits)$", re.IGNORECASE)
PAGE_FURNITURE = re.compile(
    r"^\s*(?:CONFIDENTIAL\b|Document:|Author:|Version Date:|Template No:|Effective Date:|"
    r"PROTOCOL ANB020-004\b|AnaptysBio\b|IND \d|STATISTICAL ANALYSIS PLAN\s*(?:Page \d+ of \d+)?$|"
    r"Page \d+ of \d+\s*$|APRIL Trial SAP\b|\d{1,2} [A-Z][a-z]+ \d{4}\s+\d+\s*$|\d+\s*$)",
    re.IGNORECASE,
)
STOP_WORDS = frozenset("a an and as at be by for from in is of on or that the to using was will with".split())


@dataclass(frozen=True)
class Passage:
    passage_id: str
    page: int
    pdf_page: int
    section: str | None
    text: str
    extraction: str


def tokens(text):
    return [term for term in re.findall(r"[^\W_]+", text.casefold()) if term not in STOP_WORDS]


def extract_pages(sap, pdf, *, ocr=False):
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != sap["source_pdf_sha256"]:
        raise ValueError("SAP PDF checksum does not match the selected family")
    first, last = sap["pdf_pages"]
    for pdf_page in range(first, last + 1):
        command = ["gs", "-q", "-dBATCH", "-dNOPAUSE"]
        page_args = [f"-dFirstPage={pdf_page}", f"-dLastPage={pdf_page}", "-sOutputFile=-", str(pdf.resolve())]
        text = subprocess.check_output([*command, "-sDEVICE=txtwrite", *page_args], encoding="utf-8")
        method = "pdf_text"
        if ocr and not any(tokens(line) for line in text.splitlines() if not PAGE_FURNITURE.match(line)):
            raster = subprocess.check_output([*command, "-sDEVICE=pnggray", "-r200", *page_args])
            text = subprocess.check_output(["tesseract", "stdin", "stdout", "--psm", "3"], input=raster).decode("utf-8")
            method = "ocr"
        yield pdf_page - first + 1, pdf_page, text, method


def segment_pages(sap_id, pages):
    section = None
    for page, pdf_page, text, method in pages:
        if method == "ocr":
            section = None
        lines = []
        ordinal = 0
        for line in [*text.splitlines(), None]:
            clean = " ".join(line.split()) if line is not None else ""
            if PAGE_FURNITURE.match(clean) or re.search(r"\.{4,}\s*\d+\s*$", clean):
                continue
            numbered = NUMBERED_HEADING.fullmatch(clean)
            heading = (numbered is not None or UNNUMBERED_HEADING.fullmatch(clean) is not None
                       or OUTPUT_HEADING.fullmatch(clean) is not None)
            if heading or (not clean and method != "ocr") or line is None:
                words = " ".join(lines).split()
                step = 60
                for start in range(0, len(words), step):
                    window = words[start:start + 90]
                    ordinal += 1
                    source_key = f"ocr:{ordinal}" if method == "ocr" else str(ordinal)
                    yield Passage(f"{sap_id}:p{page}:{source_key}", page, pdf_page, section, " ".join(window), method)
                    if start + 90 >= len(words):
                        break
                lines = []
            if heading:
                section = clean
            elif clean:
                lines.append(clean)


class BM25:
    def __init__(self, passages):
        self.passages = list(passages)
        if not self.passages:
            raise ValueError("No SAP passages were extracted")
        self.counts = [Counter(tokens(passage.text + " " + (passage.section or ""))) for passage in self.passages]
        self.lengths = [sum(counts.values()) for counts in self.counts]
        self.mean_length = sum(self.lengths) / len(self.lengths)
        if not self.mean_length:
            raise ValueError("No searchable terms were extracted from the SAP")
        frequency = Counter(term for counts in self.counts for term in counts)
        total = len(self.passages)
        self.idf = {term: math.log1p((total - count + 0.5) / (count + 0.5)) for term, count in frequency.items()}

    def search(self, query, limit):
        scores = []
        for index, counts in enumerate(self.counts):
            norm = 1.2 * (0.25 + 0.75 * self.lengths[index] / self.mean_length)
            score = sum(
                weight * self.idf[term] * (2.2 * counts[term]) / (counts[term] + norm)
                for term, weight in query.items() if term in counts
            )
            if score > 0:
                scores.append((score, index))
        scores.sort(key=lambda item: (-item[0], item[1]))
        return [{**asdict(self.passages[index]), "score": score} for score, index in scores[:limit]]


def component_query(component):
    context = component["context"]
    contextual_values = [context["population"], context["endpoint"], context["visit"],
                         *context["treatment_groups"], *context["surrounding_labels"]]
    query = dict.fromkeys(tokens(" ".join(value for value in contextual_values if value)), 1)
    label_terms = tokens(component["label"])
    query.update(dict.fromkeys(label_terms, 2))
    arm_terms = set(tokens(" ".join(context["treatment_groups"])))
    if component["kind"] in {"table_column", "figure_legend"} and arm_terms.intersection(label_terms):
        query.update(dict.fromkeys(("presentation", "treatment", "groups"), 2))
    return query


def select_family(manifest, family_id):
    family = next((item for item in manifest["families"] if item["family_id"] == family_id), None)
    if manifest["partition_status"] != "frozen" or family is None or family["source_status"] != "verified_pair":
        raise ValueError("Select a verified family from the frozen source manifest")
    return family


def read_components(component_path):
    for line_number, line in enumerate(component_path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            yield json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Component line {line_number}: {exc.msg}") from exc


def retrieve(manifest, family_id, pdf, component_path, limit, *, ocr=False):
    return retrieve_components(select_family(manifest, family_id), pdf, read_components(component_path), limit, ocr=ocr)


def retrieve_components(family, pdf, records, limit, *, ocr=False):
    family_id = family["family_id"]
    sap = family["sap"]
    if not sap.get("pdf_pages") or not sap.get("source_pdf_sha256"):
        raise ValueError("The selected SAP has no verified PDF page range and checksum")
    if limit < 1:
        raise ValueError("Top-k must be positive")
    schema = json.loads((ROOT / "schemas/traceability.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    components = []
    component_ids = set()
    shells = {shell["document_id"]: shell for shell in family["shells"]}
    for line_number, component in enumerate(records, 1):
        if not isinstance(component, dict) or component.get("record_type") != "component" or not validator.is_valid(component):
            raise ValueError(f"Component line {line_number}: expected a schema-valid component record")
        shell = shells.get(component["shell_id"])
        if (component["family_id"] != family_id or shell is None or shell["version"] != component["shell_version"]
                or shell["linked_sap_id"] != sap["document_id"]):
            raise ValueError(f"Component {component['component_id']} does not match the selected SAP and shell version")
        if component["component_id"] in component_ids:
            raise ValueError(f"Duplicate component ID {component['component_id']}")
        component_ids.add(component["component_id"])
        components.append(component)
    if not components:
        raise ValueError("No component records were supplied")
    index = BM25(segment_pages(sap["document_id"], extract_pages(sap, pdf, ocr=ocr)))
    for component in components:
        yield {
            "component_id": component["component_id"], "sap_id": sap["document_id"],
            "sap_version": sap["version"], "shell_id": component["shell_id"],
            "constructed_shell": shells[component["shell_id"]]["authenticity"] == "constructed",
            "candidates": index.search(component_query(component), limit),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--components", type=Path, required=True, help="JSONL inventory of shell components")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--ocr", action="store_true", help="Use Tesseract for SAP pages with no usable text layer")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
    try:
        for result in retrieve(manifest, args.family, args.pdf, args.components, args.top_k, ocr=args.ocr):
            print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
