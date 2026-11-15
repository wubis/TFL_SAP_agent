"""Shared fixtures. Every shell label and SAP sentence here is fictional and written for the tests."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SAP_ID, SAP_VERSION = "TEST-SAP-v1", "1"
POPULATION = ("TEST-SAP-v1:p4:1", 4, "4.1 Analysis populations",
              "The Full Analysis Set (FAS) includes all randomized participants who received at least one dose.")
METHOD = ("TEST-SAP-v1:p9:1", 9, "7.2 Primary endpoint analysis",
          "Change from baseline at Week 12 will be analyzed with an ANCOVA model. "
          "Least squares means and standard errors will be presented by treatment group, using the FAS.")
OTHER_VISIT = ("TEST-SAP-v1:p11:1", 11, "7.4 Secondary endpoint analysis",
               "Change from baseline at Week 24 will be summarized with means and standard deviations.")


def passage(item, score=1.0):
    passage_id, page, section, text = item
    return {"passage_id": passage_id, "page": page, "pdf_page": page + 1, "section": section,
            "text": text, "extraction": "pdf_text", "score": score}


def entry(key, kind, label, assessment=None, constructed=False):
    component_id = f"TEST-TABLE-1:{key}"
    component = {
        "record_type": "component", "component_id": component_id, "family_id": "TEST",
        "shell_id": "TEST-TABLE-1", "shell_version": "1.0", "locator": f"fictional shell, {key}",
        "kind": kind, "label": label,
        "context": {"population": "Full Analysis Set", "endpoint": "Primary endpoint", "visit": "Week 12",
                    "treatment_groups": ["Treatment A", "Treatment B"], "surrounding_labels": ["Statistic"]},
    }
    retrieval = {"component_id": component_id, "sap_id": SAP_ID, "sap_version": SAP_VERSION,
                 "shell_id": "TEST-TABLE-1", "constructed_shell": constructed,
                 "candidates": [passage(METHOD, 3.0), passage(POPULATION, 2.0), passage(OTHER_VISIT, 1.0)]}
    pending = {"status": "needs_review", "rationale": "Contextual evidence has yet to be assessed.",
               "evidence": [], "convention_ids": [],
               "open_questions": ["Which candidate passages, if any, support this component?"]}
    mapping = {"record_type": "mapping", "mapping_id": f"run1:{component_id}", "component_id": component_id,
               "sap_id": SAP_ID, "sap_version": SAP_VERSION, "assessment": assessment or pending}
    return {"component": component, "retrieval": retrieval, "mapping": mapping}


def cited(item, quote):
    passage_id, page, section, _ = item
    return {"passage_id": passage_id, "page": page, "section": section, "quote": quote, "extraction": "pdf_text"}


@pytest.fixture
def entries():
    supported = {
        "status": "supported", "rationale": "Population and method both apply at Week 12.",
        "evidence": [cited(POPULATION, "includes all randomized participants who received at least one dose"),
                     cited(METHOD, "Least squares means and standard errors will be presented by treatment group, using the FAS.")],
        "convention_ids": [], "open_questions": [],
    }
    return [entry("ls-mean", "table_row", "Change from baseline, LS mean (SE)", supported),
            entry("population", "population_label", "Full Analysis Set"),
            entry("dash-note", "footnote", "Use an em dash for a cell that does not apply.", constructed=True)]


@pytest.fixture
def run_file(tmp_path, entries):
    path = tmp_path / "run.jsonl"
    path.write_text("".join(json.dumps(item) + "\n" for item in entries), encoding="utf-8")
    return path
