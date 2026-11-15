"""Shell readers for the registered TARVA and APRIL development shells, and a dispatcher for all three families.

Each reader is tied to one registered layout and the slice of it the source manifest selects. It
returns component records whose IDs match the benchmark inventory for that shell.
"""

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from traceability.anb020_shells import parse_pdf_shells
from traceability.retrieval import ROOT, select_family


WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def component(family, shell, key, kind, label, locator, context):
    return {"record_type": "component", "component_id": f"{shell['document_id']}:{key}",
            "family_id": family["family_id"], "shell_id": shell["document_id"], "shell_version": shell["version"],
            "locator": locator, "kind": kind, "label": label, "context": context}


def docx_tables(path):
    """Yield each table in a .docx file as rows of cell text, using only the standard library."""
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    for table in root.iter(f"{WORD}tbl"):
        yield [[" ".join("".join(node.text or "" for node in cell.iter(f"{WORD}t")).split())
                for cell in row.findall(f"{WORD}tc")] for row in table.findall(f"{WORD}tr")]


def parse_tarva(family, shell, path):
    """Table S4 of Additional file 1: the MOXFQ walking/standing rows and their headers."""
    if shell["document_id"] != "NCT02128555-TABLE-S4":
        raise ValueError("This reader supports the registered TARVA Table S4")
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != shell["source_sha256"]:
        raise ValueError("Shell checksum does not match the registered version")
    table = next((rows for rows in docx_tables(path) if rows and rows[0] and rows[0][0].startswith("Table S4.")), None)
    if table is None:
        raise ValueError("Table S4 was not found in the supplement")
    title = table[0][0].removeprefix("Table S4.").strip()
    arms = [cell for cell in table[1] if cell]
    if arms != ["TAR", "Arthrodesis"]:
        raise ValueError("Unexpected treatment columns in Table S4")
    endpoint, groups = "MOXFQ walking/standing domain score", family["arms"]
    blocks = [(index, row[0]) for index, row in enumerate(table) if re.fullmatch(r"At \d+ weeks, mean \(sd\)", row[0])]
    if [label for _, label in blocks] != ["At 26 weeks, mean (sd)", "At 52 weeks, mean (sd)"]:
        raise ValueError("Expected the Week 26 and Week 52 outcome blocks")

    def context(visit, treatment_groups, nearby):
        return {"population": None, "endpoint": endpoint, "visit": visit,
                "treatment_groups": treatment_groups, "surrounding_labels": nearby}

    place = "Additional file 1, Table S4"
    records = [
        component(family, shell, "table-title", "title", title, f"{place}, caption",
                  context("26 and 52 weeks", groups, [label for _, label in blocks])),
    ]
    for key, label, arm in zip(("tar-arm", "arthrodesis-arm"), arms, groups, strict=True):
        records.append(component(family, shell, key, "table_column", label, f"{place}, column header {label}",
                                 context(None, [arm], ["MOXFQ standing/walking"])))
    for index, heading in blocks:
        weeks = re.search(r"\d+", heading)[0]
        outcome = table[index + 1][0]
        if outcome != "MOXFQ standing/walking":
            raise ValueError(f"Expected the MOXFQ standing/walking row under {heading}")
        records.append(component(family, shell, f"week-{weeks}-mean-sd", "table_row", heading,
                                 f"{place}, row {index + 1}", context(f"{weeks} weeks", groups, [title, outcome])))
        records.append(component(family, shell, f"week-{weeks}-moxfq", "table_row", outcome,
                                 f"{place}, row {index + 2}", context(f"{weeks} weeks", groups, [heading])))
    return records


def header_columns(lines):
    """Read a stacked column header. Lower lines define leaf columns; the top line labels or groups them."""
    fields = [[(match.start(), match.end(), match[0]) for match in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", line)]
              for line in lines]
    leaves = []
    for line in fields[1:]:
        for start, end, text in line:
            leaf = next((item for item in leaves if start < item["end"] and end > item["start"]), None)
            if leaf is None:
                leaves.append({"start": start, "end": end, "parts": [text]})
            else:
                leaf.update(start=min(start, leaf["start"]), end=max(end, leaf["end"]))
                leaf["parts"].append(text)
    leaves.sort(key=lambda item: item["start"])
    groups, singles = [], []
    for start, end, text in fields[0]:
        under = [leaf for leaf in leaves if start < leaf["end"] and end > leaf["start"]]
        if len(under) > 1:
            groups.append((text, [" ".join(leaf["parts"]) for leaf in under]))
        elif under:
            under[0]["parts"].insert(0, text)
        else:
            singles.append(text)
    return groups, [" ".join(leaf["parts"]) for leaf in leaves], singles


def parse_april(family, shell, pdf, pdftotext="pdftotext"):
    """Appendix Table 3: the continuous key secondary outcome rows and their headers and notes."""
    if shell["document_id"] != "ISRCTN12368131-TABLE-APP3" or shell["pdf_pages"][0] != shell["pdf_pages"][1]:
        raise ValueError("This reader supports the registered APRIL Appendix Table 3")
    if hashlib.sha256(Path(pdf).read_bytes()).hexdigest() != family["sap"]["source_pdf_sha256"]:
        raise ValueError("SAP and shell PDF checksum does not match the registered source")
    page = shell["pdf_pages"][0]
    text = subprocess.check_output([pdftotext, "-f", str(page), "-l", str(page), "-layout", str(Path(pdf).resolve()), "-"],
                                   encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    start = next((index for index, line in enumerate(lines) if "Appendix Table 3:" in line), None)
    if start is None:
        raise ValueError("Appendix Table 3 was not found on the registered page")
    title = lines[start].split("Appendix Table 3:", 1)[1].strip()
    groups, leaves, singles = header_columns(lines[start + 1:start + 4])
    arm_labels = groups[0][1] if groups else []
    if ([name for name, _ in groups] != ["Outcome at 3-months"] or arm_labels != ["Intervention arm (N=)", "Control arm (N=)"]
            or leaves[2:] != ["Effect size (95% CI) for intervention vs control*"] or singles != ["P-value"]):
        raise ValueError("Unexpected column header in Appendix Table 3")
    body = [line.strip() for line in lines[start + 4:]]
    first = next((index for index, line in enumerate(body) if line.startswith("Key secondary outcomes")), None)
    last = next((index for index, line in enumerate(body) if line.startswith("Secondary outcomes")), None)
    if first is None or last is None or last <= first:
        raise ValueError("Expected the key secondary outcome block")
    block, rows = body[first], []
    for line in body[first + 1:last]:
        if line.startswith("Quality of life") or not rows:
            rows.append(line)
        else:
            rows[-1] += " " + line
    if len(rows) != 2 or "PROMIS" not in rows[0] or "EuroQol" not in rows[1]:
        raise ValueError("Expected the PROMIS 29+2 and EuroQol rows")
    flat = " ".join(text.split())
    note = re.search(r"\*(Adjusted for baseline level of outcome\.) (Effect sizes represent mean difference in outcome "
                     r"score between intervention and control arms unless otherwise specified)", flat)
    if note is None:
        raise ValueError("Expected the asterisk note under Appendix Table 3")

    both, effect = family["arms"], leaves[2]
    general = "Continuous key secondary outcomes"

    def context(endpoint, treatment_groups, nearby):
        return {"population": None, "endpoint": endpoint, "visit": "3 months",
                "treatment_groups": treatment_groups, "surrounding_labels": nearby}

    place = f"Appendix Table 3, PDF page {page}"
    entries = [
        ("table-title", "title", title, "caption", context(general, both, [block])),
        ("three-month-visit", "table_column", groups[0][0], "group header over both arms",
         context(general, both, [label.removesuffix(" (N=)") for label in arm_labels])),
        ("intervention-arm", "table_column", arm_labels[0], "left arm column", context(general, both[:1], [groups[0][0]])),
        ("control-arm", "table_column", arm_labels[1], "right arm column", context(general, both[1:], [groups[0][0]])),
        ("effect-ci", "table_column", effect, "effect-estimate column", context(general, both, [note[1]])),
        ("p-value", "table_column", singles[0], "rightmost column", context(general, both, [effect])),
        ("mean-and-sd", "table_row", block, "group label above the continuous rows",
         context("PROMIS 29+2 summary score and EQ-VAS", both, [groups[0][0]])),
        ("promis-row", "table_row", rows[0], "first key secondary outcome row", context("PROMIS 29+2 summary score", both, [block])),
        ("eq-vas-row", "table_row", rows[1], "second key secondary outcome row", context("EQ-VAS", both, [block])),
        ("baseline-adjustment", "footnote", note[1], "asterisk note, first sentence",
         context(general, both, [effect.removesuffix("*")])),
        ("mean-difference", "footnote", note[2], "asterisk note, second sentence",
         context(general, both, [effect, note[1]])),
    ]
    return [component(family, shell, key, kind, label, f"{place}, {where}", ctx) for key, kind, label, where, ctx in entries]


def parse_family_shells(family, pdf, shell_file=None, pdftotext="pdftotext"):
    """Parse the registered authentic shells of a development family from its source files."""
    family_id = family["family_id"]
    if family.get("partition") != "development":
        raise ValueError("Shell readers exist for development families only")
    if family_id == "NCT03469934":
        return list(parse_pdf_shells(family, pdf, pdftotext))
    shell = next(item for item in family["shells"] if item["authenticity"] == "authentic")
    if family_id == "ISRCTN12368131":
        return parse_april(family, shell, pdf, pdftotext)
    if family_id == "NCT02128555":
        if shell_file is None:
            raise ValueError("TARVA needs --shell-file pointing to Additional file 1 (.docx)")
        return parse_tarva(family, shell, shell_file)
    raise ValueError(f"No shell reader is registered for {family_id}")


def main():
    parser = argparse.ArgumentParser(description="Parse a development family's registered shells into component records.")
    parser.add_argument("--family", required=True)
    parser.add_argument("--pdf", type=Path, required=True, help="Original SAP PDF from the source manifest")
    parser.add_argument("--shell-file", type=Path, help="Separate shell document, where the shell is outside the SAP PDF")
    parser.add_argument("--pdftotext", default="pdftotext")
    args = parser.parse_args()
    try:
        manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
        for record in parse_family_shells(select_family(manifest, args.family), args.pdf, args.shell_file, args.pdftotext):
            print(json.dumps(record, ensure_ascii=False))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
