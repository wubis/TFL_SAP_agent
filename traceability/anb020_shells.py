"""Layout readers for the three registered ANB020-004 PDF shell pages."""

import hashlib
import re
import subprocess


def match(pattern, text):
    result = re.search(pattern, text, re.MULTILINE)
    if result is None:
        raise ValueError(f"Expected shell layout marker was not found: {pattern}")
    return result


def table_entries(text, arms):
    title, population = match(r"^\s*(Spriometry \(FEV1\))\s+–\s+(Full Analysis Set)", text).groups()
    entries = [("title", "title", title, "table title", None, arms),
               ("population", "population_label", population, "table title suffix", None, arms)]
    header = match(r"Statistics\s+(\S+)\s+(\S+)\s*\n\s*(\(N=XX\))\s+(\(N=XX\))\s*\n([^\n]+)", text)
    labels = re.split(r"\s{2,}", header[5].strip())
    if len(labels) != 4 or list(header.groups()[:2]) != arms:
        raise ValueError("Unexpected treatment columns in the FEV1 table")
    for index, arm in enumerate(arms):
        key = arm.lower()
        entries.append((f"{key}-column", "table_column", f"{arm} {header[index + 3]}", f"{arm} header", None, [arm]))
        for offset, suffix in enumerate(("observed", "cfb")):
            entries.append((f"{key}-{suffix}-column", "table_column", labels[index * 2 + offset],
                            f"{arm} subcolumn {offset + 1}", None, [arm]))
    for key, pattern in (("predicted-litres", r"Predicted FEV1 \(L\)"), ("actual-observed", r"Actual FEV1\(L\)"),
                         ("percent-predicted", r"FEV1 % Predicted")):
        entries.append((key, "table_row", match(pattern, text)[0], "parameter stub", None, arms))

    visit_rows = list(re.finditer(r"(Screening|Baseline \(Pre-|Post-Bronchodilator)\s{2,}(n)\s{2,}[^\n]+", text))
    if len(visit_rows) != 3:
        raise ValueError("Expected the three explicit FEV1 visit blocks")
    for row, visit_key in zip(visit_rows, ("screening", "baseline", "post"), strict=True):
        visit = row[1]
        following = text[row.end():].splitlines()[1:6]
        if visit.endswith("-"):
            visit += following.pop(0).strip()
        entries.append((f"visit-{visit_key}", "table_row", visit, "predicted FEV1 visit stub", visit, arms))
        stats = [row[2], *(re.split(r"\s{2,}", line.strip())[0] for line in following[:4])]
        if stats != ["n", "Mean (SD)", "95% CI", "Median", "Min, Max"]:
            raise ValueError(f"Unexpected statistic labels in {visit}")
        keys = [f"predicted-{visit_key}-{field}" for field in ("n", "mean-sd", "ci", "median", "range")]
        if visit_key == "screening":
            keys[:2] = ["contributed-observation-count", "predicted-screening-mean"]
        entries.extend((key, "table_row", label, f"Predicted FEV1 (L), {visit}, statistic {number}", visit, arms)
                       for number, (key, label) in enumerate(zip(keys, stats, strict=True), 1))
    for key, pattern, visit in (("group-n-footnote", r"^\s*-\s+(N is the number[^\n]+)", None),
                                ("baseline-footnote", r"^\s*-\s+(Day1 pre-bronchodilator[^\n]+)", "Day 1"),
                                ("all-visits-programming-note", r"Programming Note:\s*([^\n]+)", None)):
        entries.append((key, "footnote", match(pattern, text)[1].strip(), key, visit, arms))
    return entries, population, "Spirometry (FEV1)", ["Predicted FEV1 (L)", "Actual FEV1(L)", *arms]


def listing_entries(text, arms):
    title, population = match(r"^\s*(Spirometry) - (Full Analysis Set)", text).groups()
    entries = [("title", "title", title, "listing title", None, arms),
               ("population", "population_label", population, "listing title suffix", None, arms)]
    header = match(r"^ +Patient +Age/ +Visit[^\n]+", text)
    starts = [field.start() for field in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", header[0])]
    keys = ("patient-treatment", "age-gender", "visit-column", "date-study-day", "predicted-fev1-litres",
            "cfb-predicted", "actual-fev1", "cfb-actual", "fev1-percent-predicted", "cfb-percent-predicted",
            "bronchodilator-administration")
    if len(starts) != len(keys):
        raise ValueError("Unexpected number of spirometry listing columns")
    lines = [header[0], *text[header.end():].splitlines()[1:6]]
    ends = [*starts[1:], None]
    for index, (key, start, end) in enumerate(zip(keys, starts, ends, strict=True), 1):
        label = " ".join(fragment for line in lines if (fragment := line[start:end].strip()))
        label = re.sub(r"\s*/\s*(?=Treatment|Gender|Study Day|Time of)", "/", label)
        entries.append((key, "listing_column", label, f"listing column {index}", None, arms))
    for key, kind, prefix in (("fev1-abbreviation", "footnote", "FEV1:"),
                              ("baseline-footnote", "footnote", "Day1 pre-bronchodilator"),
                              ("post-bronchodilator-note", "listing_selection_note", "Post Bronchodilator"),
                              ("study-day-footnote", "footnote", "If Date of assessment")):
        label = match(rf"^\s*-\s+({re.escape(prefix)}[^\n]+)", text)[1].strip().replace("readingis", "reading is")
        visit = "Day 1" if key == "baseline-footnote" else None
        entries.append((key, kind, label, key, visit, arms))
    return entries, population, "Spirometry (FEV1)", ["Visit", "Actual FEV1 (L)", *arms]


def figure_entries(text, arms):
    raw, population = match(r"^\s*(Mean .+? Count-time Profiles)\s+[—–-]\s+(Pharmacodynamic Analysis Set)", text).groups()
    # Tesseract recognizes the typography of this scanned confidence-interval label inconsistently.
    title = re.sub(r"\([£±]95% C[IT]\)", "(±95% CI)", raw)
    uncertainty = match(r"\((±95% CI)\)", title)[1]
    entries = [("title", "title", title, "figure title", None, arms),
               ("population", "population_label", population, "figure title suffix", None, arms),
               ("mean-ci", "figure_error_bar", uncertainty, "figure title uncertainty label", None, arms)]
    for key, pattern, location in (("time-axis", r"^\s*(Time \(h\))", "horizontal axis"),
                                    ("count-axis", r"^\s*(Mean Eosinophil Counts \(units\))", "vertical axis")):
        entries.append((key, "figure_axis", match(pattern, text)[1], location, None, arms))
    for arm, pattern in zip(arms, (r"ANB[O0]20", r"Placebo"), strict=True):
        count = match(rf"{pattern}\s+(\(n=xx\))", text)[1]
        entries.append((f"{arm.lower()}-legend", "figure_legend", f"{arm} {count}", "figure legend", None, [arm]))
    note = match(r"(Actual plot will have x- and y-axes and time points modified according to actual study data)", text)[1]
    entries.append(("illustrative-plot-note", "footnote", note, "programming note", None, arms))
    return entries, population, "Observed eosinophil count", ["Time (h)", "Mean Eosinophil Counts (units)", "Illustrative plot"]


READERS = {"table": table_entries, "listing": listing_entries, "figure": figure_entries}


def parse_pdf_shells(family, pdf, pdftotext="pdftotext"):
    if family["family_id"] != "NCT03469934":
        raise ValueError("PDF shell parsing supports the registered ANB020-004 layouts")
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != family["sap"]["source_pdf_sha256"]:
        raise ValueError("SAP and shell bundle checksum does not match the registered source")
    for shell in family["shells"]:
        if shell["authenticity"] != "authentic":
            continue
        page, last = shell["pdf_pages"]
        if page != last or shell["version"] != "1.0":
            raise ValueError("Expected a registered single-page PDF shell v1.0")
        page_args = ["-f", str(page), "-l", str(page)]
        if shell["type"] == "figure":
            raster = subprocess.check_output([
                "gs", "-q", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pnggray", "-r300",
                f"-dFirstPage={page}", f"-dLastPage={page}", "-sOutputFile=-", str(pdf.resolve()),
            ])
            text = subprocess.check_output(["tesseract", "stdin", "stdout", "--psm", "3"], input=raster).decode("utf-8")
        else:
            text = subprocess.check_output([pdftotext, *page_args, "-layout", str(pdf.resolve()), "-"], encoding="utf-8")
        entries, population, endpoint, nearby = READERS[shell["type"]](text, family["arms"])
        for key, kind, label, location, visit, treatments in entries:
            yield {"record_type": "component", "component_id": f"{shell['document_id']}:{key}",
                   "family_id": family["family_id"], "shell_id": shell["document_id"], "shell_version": shell["version"],
                   "locator": f"PDF page {page}, {location}", "kind": kind, "label": label,
                   "context": {"population": population, "endpoint": endpoint, "visit": visit,
                               "treatment_groups": treatments, "surrounding_labels": nearby}}
