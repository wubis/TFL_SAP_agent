import io
import os
import zipfile
from pathlib import Path

import pytest

from traceability.dev_shells import docx_tables, header_columns
from traceability.hybrid import HybridIndex, query_text, reciprocal_rank_fusion, retrieve_hybrid
from traceability.retrieval import Passage

from conftest import METHOD, OTHER_VISIT, POPULATION, SAP_ID, SAP_VERSION, entry

VOCABULARY = {"lsmean": ("least", "squares", "ls"), "population": ("fas", "randomized", "analysis"),
              "week12": ("12",), "week24": ("24",)}


def toy_embed(texts):
    """A fictional embedder: one dimension per concept, so a paraphrase lands near its meaning."""
    vectors = []
    for text in texts:
        words = text.casefold().replace("(", " ").replace(")", " ").replace(",", " ").split()
        vectors.append([float(sum(word in terms for word in words)) + 0.01 for terms in VOCABULARY.values()])
    return vectors


def passages():
    return [Passage(item[0], item[1], item[1] + 1, item[2], item[3], "pdf_text") for item in (POPULATION, METHOD, OTHER_VISIT)]


def test_reciprocal_rank_fusion_rewards_agreement():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]], k=1)
    assert [item for item, _ in fused] == ["a", "b", "c", "d"]
    assert fused[0][1] == pytest.approx(1 / 2 + 1 / 3) and fused[3][1] == pytest.approx(1 / 4)


def test_hybrid_search_reports_both_ranks_and_keeps_bm25_evidence():
    component = entry("ls-mean", "table_row", "Change from baseline, LS mean (SE)")["component"]
    assert query_text(component).startswith("Change from baseline, LS mean (SE). Primary endpoint. Full Analysis Set")
    results = HybridIndex(passages(), toy_embed).search(component, 3)
    assert results[0]["passage_id"] == METHOD[0]
    assert {result["passage_id"] for result in results} == {POPULATION[0], METHOD[0], OTHER_VISIT[0]}
    assert all(result["bm25_rank"] and result["dense_rank"] for result in results)


def test_retrieve_hybrid_matches_the_retrieval_result_shape():
    family = {"family_id": "TEST", "sap": {"document_id": SAP_ID, "version": SAP_VERSION},
              "shells": [{"document_id": "TEST-TABLE-1", "authenticity": "authentic", "linked_sap_id": SAP_ID}]}
    pages = [(item[1], item[1] + 1, f"{item[2]}\n\n{item[3]}\n", "pdf_text") for item in (POPULATION, METHOD, OTHER_VISIT)]
    component = entry("ls-mean", "table_row", "Change from baseline, LS mean (SE)")["component"]
    result = list(retrieve_hybrid(family, [component], pages, toy_embed, 2))[0]
    assert set(result) == {"component_id", "sap_id", "sap_version", "shell_id", "constructed_shell", "candidates"}
    assert len(result["candidates"]) == 2 and {"passage_id", "page", "pdf_page", "section", "text", "extraction", "score"} <= set(result["candidates"][0])


def test_embedder_returning_too_few_vectors_is_refused():
    with pytest.raises(ValueError, match="different number of vectors"):
        HybridIndex(passages(), lambda texts: [[1.0]])


def test_embedder_with_separate_query_and_passage_encoders():
    class Paired:
        def passages(self, pairs):
            assert all(isinstance(pair, tuple) and len(pair) == 2 for pair in pairs)
            return toy_embed([f"{section} {text}" for section, text in pairs])

        def query(self, text):
            return toy_embed([text])[0]

    component = entry("ls-mean", "table_row", "Change from baseline, LS mean (SE)")["component"]
    assert HybridIndex(passages(), Paired()).search(component, 1)[0]["passage_id"] == METHOD[0]


def test_mismatched_embedding_dimensions_are_refused():
    ragged = lambda texts: [[1.0, 0.0]] + [[1.0, 0.0, 0.0] for _ in texts[1:]]
    with pytest.raises(ValueError, match="different or zero length"):
        HybridIndex(passages(), ragged)
    calls = []
    shrinking = lambda texts: calls.append(1) or [[1.0, 0.0, 0.0][:3 if len(calls) == 1 else 2] for _ in texts]
    index = HybridIndex(passages(), shrinking)
    with pytest.raises(ValueError, match="query vector has 2 dimensions and the passages have 3"):
        index.search(entry("ls-mean", "table_row", "Change from baseline, LS mean (SE)")["component"], 2)


def test_stacked_header_separates_group_leaf_and_single_columns():
    lines = ["                      Result at Week 12        Difference (95% CI)   P-value",
             "                  Treatment A   Treatment B     for A versus",
             "                    (N=)          (N=)               B*"]
    groups, leaves, singles = header_columns(lines)
    assert groups == [("Result at Week 12", ["Treatment A (N=)", "Treatment B (N=)"])]
    assert leaves == ["Treatment A (N=)", "Treatment B (N=)", "Difference (95% CI) for A versus B*"]
    assert singles == ["P-value"]


def test_docx_tables_reads_cells_without_extra_packages(tmp_path):
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    cell = lambda text: f"<w:tc><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc>"
    body = f"<w:tbl><w:tr>{cell('Table 1. Fictional')}</w:tr><w:tr>{cell('')}{cell('Arm A')}{cell('Arm B')}</w:tr></w:tbl>"
    path = tmp_path / "shell.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>')
    assert list(docx_tables(path)) == [[["Table 1. Fictional"], ["", "Arm A", "Arm B"]]]


@pytest.mark.skipif("TRACEABILITY_SOURCES" not in os.environ, reason="needs the original source documents")
@pytest.mark.parametrize("family_id, pdf, shell_file", [
    ("ISRCTN12368131", "april.pdf", None), ("NCT02128555", "tarva_sap.pdf", "tarva_s4.docx")])
def test_readers_reproduce_the_benchmark_inventory(family_id, pdf, shell_file):
    import json
    from traceability.dev_shells import parse_family_shells
    from traceability.retrieval import ROOT, select_family
    sources = Path(os.environ["TRACEABILITY_SOURCES"])
    family = select_family(json.loads((ROOT / "data/source-manifest.json").read_text()), family_id)
    parsed = parse_family_shells(family, sources / pdf, sources / shell_file if shell_file else None)
    inventory = [json.loads(line) for line in (ROOT / f"benchmark/development/{family_id}/components.jsonl").read_text().splitlines()]
    key = lambda record: record["component_id"]
    strip = lambda record: {name: record[name] for name in ("component_id", "kind", "label", "context")}
    assert sorted(map(strip, parsed), key=key) == sorted(map(strip, inventory), key=key)
