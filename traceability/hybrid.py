"""Hybrid SAP retrieval: BM25 and embedding rankings combined by reciprocal rank fusion.

The output has the same shape as the BM25 retrieval command, so the same scorer compares them.

    python3 -m traceability.hybrid --family NCT03469934 --pdf SAP_001.pdf --ocr \
      --components benchmark/development/NCT03469934/components.jsonl \
      --embedder fastembed:BAAI/bge-small-en-v1.5 --top-k 10 > /tmp/hybrid-retrieval.jsonl

The embedding model is a choice the team still has to make. Two local loaders are provided, and any
callable that maps a list of strings to a list of vectors can be passed to HybridIndex.
"""

import argparse
import json
import math
import subprocess
from dataclasses import asdict
from pathlib import Path

from jsonschema import Draft202012Validator

from traceability.retrieval import (BM25, ROOT, component_query, extract_pages, read_components, segment_pages,
                                    select_family)


def reciprocal_rank_fusion(rankings, k=60):
    """Combine ranked ID lists. An item's score is the sum of 1 / (k + rank) over the lists that contain it."""
    scores = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], str(pair[0])))


def unit(vector):
    vector = [float(value) for value in vector]
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length else vector


def query_text(component):
    context = component["context"]
    parts = [component["label"], context["endpoint"], context["population"], context["visit"],
             *context["treatment_groups"], *context["surrounding_labels"]]
    return ". ".join(dict.fromkeys(part for part in parts if part))


class MedCPT:
    """MedCPT has one encoder for queries and another for passages. Both run locally with transformers.

    The article encoder takes a title and a text. The SAP section heading stands in for the title.
    """

    def __init__(self, owner="ncbi"):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.torch = torch
        self.names = {role: f"{owner}/MedCPT-{role}-Encoder" for role in ("Query", "Article")}
        self.tokenizers = {role: AutoTokenizer.from_pretrained(name) for role, name in self.names.items()}
        self.models = {role: AutoModel.from_pretrained(name).eval() for role, name in self.names.items()}

    def encode(self, role, inputs, max_length):
        vectors = []
        with self.torch.no_grad():
            for start in range(0, len(inputs), 16):
                batch = self.tokenizers[role](inputs[start:start + 16], truncation=True, padding=True,
                                              return_tensors="pt", max_length=max_length)
                vectors.extend(self.models[role](**batch).last_hidden_state[:, 0, :].tolist())
        return vectors

    def passages(self, pairs):
        return self.encode("Article", [list(pair) for pair in pairs], 512)

    def query(self, text):
        return self.encode("Query", [text], 64)[0]


def load_embedder(spec):
    """Return an embedder for 'fastembed:MODEL', 'sentence-transformers:MODEL', or 'medcpt:OWNER'. All run locally."""
    kind, _, name = spec.partition(":")
    if not name:
        raise ValueError("Give the embedder as LIBRARY:MODEL, for example fastembed:BAAI/bge-small-en-v1.5 or medcpt:ncbi")
    try:
        if kind == "medcpt":
            return MedCPT(name)
        if kind == "fastembed":
            from fastembed import TextEmbedding
            model = TextEmbedding(name)
            return lambda texts: [list(vector) for vector in model.embed(list(texts))]
        if kind == "sentence-transformers":
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(name)
            return lambda texts: [list(vector) for vector in model.encode(list(texts))]
    except ImportError as exc:
        raise ValueError(f"Install {kind} to use this embedder") from exc
    raise ValueError("Unknown embedder library. Use fastembed, sentence-transformers, or medcpt")


class HybridIndex:
    def __init__(self, passages, embed):
        self.bm25 = BM25(passages)
        # An embedder is one callable for everything, or an object with separate passage and query encoders.
        paired = hasattr(embed, "passages")
        self.embed_query = embed.query if paired else (lambda text: embed([text])[0])
        self.by_id = {passage.passage_id: passage for passage in self.bm25.passages}
        if paired:
            texts = [(passage.section or "", passage.text) for passage in self.bm25.passages]
            vectors = [unit(vector) for vector in embed.passages(texts)]
        else:
            texts = [f"{passage.section or ''} {passage.text}".strip() for passage in self.bm25.passages]
            vectors = [unit(vector) for vector in embed(texts)]
        if len(vectors) != len(texts):
            raise ValueError("The embedder returned a different number of vectors than passages")
        self.dimensions = len(vectors[0])
        if not self.dimensions or any(len(vector) != self.dimensions for vector in vectors):
            raise ValueError("The embedder returned vectors of different or zero length")
        if not all(math.isfinite(value) for vector in vectors for value in vector):
            raise ValueError("The embedder returned a vector with a missing or infinite value")
        self.vectors = dict(zip(self.by_id, vectors, strict=True))

    def dense_ranking(self, text, depth):
        query = unit(self.embed_query(text))
        if not all(math.isfinite(value) for value in query):
            raise ValueError("The query vector has a missing or infinite value")
        if len(query) != self.dimensions:
            raise ValueError(f"The query vector has {len(query)} dimensions and the passages have {self.dimensions}")
        scored = sorted(((sum(a * b for a, b in zip(query, vector, strict=True)), passage_id)
                         for passage_id, vector in self.vectors.items()), key=lambda pair: (-pair[0], pair[1]))
        return [passage_id for _, passage_id in scored[:depth]]

    def search(self, component, limit, depth=50):
        sparse = [passage["passage_id"] for passage in self.bm25.search(component_query(component), depth)]
        dense = self.dense_ranking(query_text(component), depth)
        results = []
        for passage_id, score in reciprocal_rank_fusion([sparse, dense])[:limit]:
            results.append({**asdict(self.by_id[passage_id]), "score": score,
                            "bm25_rank": sparse.index(passage_id) + 1 if passage_id in sparse else None,
                            "dense_rank": dense.index(passage_id) + 1 if passage_id in dense else None})
        return results


def retrieve_hybrid(family, components, pages, embed, limit):
    sap = family["sap"]
    shells = {shell["document_id"]: shell for shell in family["shells"]}
    index = HybridIndex(segment_pages(sap["document_id"], pages), embed)
    for component in components:
        shell = shells.get(component["shell_id"])
        if component["family_id"] != family["family_id"] or shell is None or shell["linked_sap_id"] != sap["document_id"]:
            raise ValueError(f"Component {component['component_id']} does not match the selected SAP")
        yield {"component_id": component["component_id"], "sap_id": sap["document_id"], "sap_version": sap["version"],
               "shell_id": component["shell_id"], "constructed_shell": shell["authenticity"] == "constructed",
               "candidates": index.search(component, limit)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--family", required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--embedder", required=True, help="LIBRARY:MODEL, for example fastembed:BAAI/bge-small-en-v1.5")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--ocr", action="store_true")
    args = parser.parse_args()
    try:
        manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "schemas/traceability.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator({"$ref": "#/$defs/component", "$defs": schema["$defs"]})
        family = select_family(manifest, args.family)
        components = list(read_components(args.components))
        if not components or args.top_k < 1 or not all(validator.is_valid(component) for component in components):
            raise ValueError("Expected schema-valid component records and a positive top-k")
        pages = extract_pages(family["sap"], args.pdf, ocr=args.ocr)
        from traceability.provenance import run_settings
        settings = run_settings("hybrid_retrieval", method="BM25 and embedding ranks, reciprocal rank fusion",
                                embedder=args.embedder, top_k=args.top_k, ocr=args.ocr)
        for result in retrieve_hybrid(family, components, pages, load_embedder(args.embedder), args.top_k):
            print(json.dumps({**result, "run_settings": settings}, ensure_ascii=False))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
