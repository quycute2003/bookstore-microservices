"""
================================================================
  MODULE 2 — Knowledge Base Builder
================================================================
Load, chunk, embed và index documents cho RAG pipeline.
Hỗ trợ hybrid search: FAISS (vector) + BM25 (keyword).

Chạy standalone:
  cd ai-behavior-service
  python -m module2_knowledge.kb_builder
"""

import os
import json
import glob
import hashlib
import pickle
import numpy as np
from typing import List, Tuple

import faiss
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

# =============================================
# CẤU HÌNH
# =============================================
EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
CHUNK_SIZE = 500       # Ký tự tối đa mỗi chunk
CHUNK_OVERLAP = 50     # Ký tự overlap giữa các chunk
KB_DIR = os.path.join(os.path.dirname(__file__), "knowledge_base")
INDEX_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")

# =============================================
# BRAND ALIASES (Fix B - query expansion)
# =============================================
# Map canonical brand name -> list of aliases/acronyms
BRAND_ALIASES = {
    "Louis Vuitton": ["LV"],
    "Yves Saint Laurent": ["YSL", "Saint Laurent"],
    "Christian Dior": ["Dior", "CD"],
    "Gucci": ["GG"],
    "Chanel": ["CC"],
    "Hermes": ["Hermès"],
    "Balenciaga": ["BLCG"],
    "Versace": [],
    "Prada": [],
    "Burberry": [],
}

# Reverse lookup: alias (lowercase) -> canonical brand
_ALIAS_TO_BRAND = {}
for _canon, _aliases in BRAND_ALIASES.items():
    _ALIAS_TO_BRAND[_canon.lower()] = _canon
    for _a in _aliases:
        _ALIAS_TO_BRAND[_a.lower()] = _canon


def expand_query(query: str) -> str:
    """
    Mở rộng query bằng cách thêm các alias/canonical name của brand.
    Ví dụ: 'áo LV' -> 'áo LV Louis Vuitton'
    Giữ nguyên query gốc và thêm các từ mở rộng vào cuối.
    """
    if not query:
        return query
    tokens = query.lower().split()
    extras = set()
    for tok in tokens:
        # Strip punctuation
        clean = tok.strip(".,!?:;'\"()[]{}")
        if clean in _ALIAS_TO_BRAND:
            canon = _ALIAS_TO_BRAND[clean]
            extras.add(canon)
            for a in BRAND_ALIASES.get(canon, []):
                extras.add(a)
    if extras:
        return query + " " + " ".join(extras)
    return query


def _format_price(price, currency="VND") -> str:
    """Format giá tiền VND với dấu chấm ngàn."""
    try:
        p = int(float(price))
        return f"{p:,}".replace(",", ".") + f" {currency}"
    except (TypeError, ValueError):
        return f"{price} {currency}"


def _format_item(item, source: str) -> str:
    """
    Convert JSON item thành natural text để retrieval tốt hơn.
    Tự động detect loại (book / clothes / category / scenario) dựa trên schema.
    """
    if not isinstance(item, dict):
        return json.dumps(item, ensure_ascii=False)

    # ---- Book (có title + author) ----
    if "title" in item and "author" in item:
        lines = [f"Sản phẩm sách: {item['title']}"]
        lines.append(f"Tác giả: {item['author']}")
        if "category" in item:
            lines.append(f"Thể loại: {item['category']}")
        if "price" in item:
            lines.append(f"Giá: {_format_price(item['price'], item.get('currency', 'VND'))}")
        if "stock" in item:
            lines.append(f"Tồn kho: còn {item['stock']} cuốn")
        if "description" in item:
            lines.append(f"Mô tả: {item['description']}")
        return "\n".join(lines)

    # ---- Clothes / fashion item (có name + brand hoặc price) ----
    if "name" in item and ("brand" in item or ("price" in item and "size" in item)):
        brand = item.get("brand", "")
        name = item["name"]
        aliases = BRAND_ALIASES.get(brand, [])
        brand_display = brand
        if aliases:
            brand_display = f"{brand} ({', '.join(aliases)})"
        lines = [f"Sản phẩm thời trang: {name}"]
        if brand:
            # Lặp brand + alias để BM25 match được cả canonical lẫn acronym
            lines.append(f"Thương hiệu: {brand_display}")
            if aliases:
                lines.append(f"Từ khoá thương hiệu: {brand} " + " ".join(aliases))
        if "category" in item:
            lines.append(f"Danh mục: {item['category']}")
        if "size" in item:
            lines.append(f"Size: {item['size']}")
        if "color" in item:
            lines.append(f"Màu sắc: {item['color']}")
        if "price" in item:
            lines.append(f"Giá: {_format_price(item['price'], item.get('currency', 'VND'))}")
        if "stock" in item:
            lines.append(f"Tồn kho: còn {item['stock']} sản phẩm")
        if "description" in item:
            lines.append(f"Mô tả: {item['description']}")
        return "\n".join(lines)

    # ---- Category (name + description + type) ----
    if "name" in item and "description" in item and "type" in item:
        t = "sách" if item["type"] == "book" else "thời trang"
        return f"Danh mục {t}: {item['name']}. Mô tả: {item['description']}"

    # ---- Behavior scenario (có behavior_type) ----
    if "behavior_type" in item:
        parts = [f"Nhóm hành vi khách hàng: {item.get('display_name', item['behavior_type'])}"]
        if "characteristics" in item:
            parts.append("Đặc điểm: " + "; ".join(item["characteristics"]))
        strat = item.get("consultation_strategy", {})
        if strat:
            if "tone" in strat:
                parts.append(f"Tone tư vấn: {strat['tone']}")
            if "approach" in strat:
                parts.append(f"Cách tiếp cận: {strat['approach']}")
            if "key_phrases" in strat:
                parts.append("Câu nói gợi ý: " + "; ".join(strat["key_phrases"]))
            if "avoid" in strat:
                parts.append(f"Cần tránh: {strat['avoid']}")
        rec = item.get("recommended_products", {})
        if rec:
            if rec.get("books"):
                parts.append("Sách gợi ý: " + "; ".join(rec["books"]))
            if rec.get("clothes"):
                parts.append("Thời trang gợi ý: " + "; ".join(rec["clothes"]))
        return "\n".join(parts)

    # ---- Fallback: keep as JSON ----
    return json.dumps(item, ensure_ascii=False, indent=2)


class Document:
    """Đại diện cho 1 đoạn văn bản đã chunk."""
    def __init__(self, content: str, metadata: dict):
        self.content = content
        self.metadata = metadata
        self.doc_id = hashlib.md5(content.encode()).hexdigest()[:12]


class KnowledgeBaseBuilder:
    """
    Xây dựng Knowledge Base cho RAG:
    1. Load documents (JSON + Markdown)
    2. Chunk (semantic chunking với overlap)
    3. Embed (sentence-transformers multilingual)
    4. Index (FAISS + BM25)
    """

    def __init__(self, embedding_model_name=EMBEDDING_MODEL_NAME):
        print(f"🔄 Loading embedding model: {embedding_model_name}")
        self.embed_model = SentenceTransformer(embedding_model_name)
        self.embed_dim = self.embed_model.get_sentence_embedding_dimension()
        print(f"✅ Model loaded! dim={self.embed_dim}")

        self.documents: List[Document] = []
        self.faiss_index = None
        self.bm25_index = None

    def load_documents(self, kb_dir=KB_DIR) -> List[Document]:
        """Load tất cả files JSON và Markdown từ knowledge_base/."""
        documents = []

        # Load JSON — format thành natural text thay vì json.dumps
        for jf in glob.glob(os.path.join(kb_dir, "**/*.json"), recursive=True):
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                rel = os.path.relpath(jf, kb_dir)
                if isinstance(data, list):
                    for item in data:
                        documents.append(Document(
                            content=_format_item(item, rel),
                            metadata={"source": rel, "type": "json"}
                        ))
                elif isinstance(data, dict):
                    documents.append(Document(
                        content=_format_item(data, rel),
                        metadata={"source": rel, "type": "json"}
                    ))
            except Exception as e:
                print(f"  ⚠️ Lỗi đọc {jf}: {e}")

        # Load Markdown
        for mf in glob.glob(os.path.join(kb_dir, "**/*.md"), recursive=True):
            try:
                with open(mf, 'r', encoding='utf-8') as f:
                    content = f.read()
                rel = os.path.relpath(mf, kb_dir)
                documents.append(Document(
                    content=content,
                    metadata={"source": rel, "type": "markdown"}
                ))
            except Exception as e:
                print(f"  ⚠️ Lỗi đọc {mf}: {e}")

        print(f"📂 Loaded {len(documents)} documents")
        return documents

    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """Chunk documents theo đoạn văn, ưu tiên ranh giới tự nhiên."""
        chunks = []
        for doc in documents:
            content = doc.content.strip()
            if len(content) <= CHUNK_SIZE:
                chunks.append(doc)
                continue

            # Tách theo đoạn văn
            paragraphs = content.split('\n\n')
            current = ""
            for para in paragraphs:
                if len(current) + len(para) + 2 <= CHUNK_SIZE:
                    current += ("\n\n" + para if current else para)
                else:
                    if current:
                        chunks.append(Document(current.strip(), {**doc.metadata, "chunk": True}))
                    if len(para) > CHUNK_SIZE:
                        # Cắt đoạn dài theo câu
                        for i in range(0, len(para), CHUNK_SIZE - CHUNK_OVERLAP):
                            piece = para[i:i + CHUNK_SIZE]
                            if piece.strip():
                                chunks.append(Document(piece.strip(), {**doc.metadata, "chunk": True}))
                        current = ""
                    else:
                        current = para
            if current.strip():
                chunks.append(Document(current.strip(), {**doc.metadata, "chunk": True}))

        print(f"✂️  Chunked {len(documents)} docs → {len(chunks)} chunks")
        return chunks

    def build_index(self, kb_dir=KB_DIR):
        """Pipeline: Load → Chunk → Embed → Index."""
        raw_docs = self.load_documents(kb_dir)
        self.documents = self.chunk_documents(raw_docs)

        # Embeddings
        print(f"🔄 Embedding {len(self.documents)} chunks...")
        texts = [d.content for d in self.documents]
        embeddings = self.embed_model.encode(texts, show_progress_bar=True, batch_size=32)
        embeddings = np.array(embeddings).astype('float32')

        # FAISS index (cosine similarity)
        faiss.normalize_L2(embeddings)
        self.faiss_index = faiss.IndexFlatIP(self.embed_dim)
        self.faiss_index.add(embeddings)
        print(f"📊 FAISS: {self.faiss_index.ntotal} vectors")

        # BM25 index
        tokenized = [t.lower().split() for t in texts]
        self.bm25_index = BM25Okapi(tokenized)
        print(f"📊 BM25: {len(tokenized)} documents")

        return self

    def save_index(self, path=INDEX_DIR):
        """Lưu FAISS + BM25 + documents ra disk."""
        os.makedirs(path, exist_ok=True)
        faiss.write_index(self.faiss_index, os.path.join(path, "faiss_index"))
        data = {
            "documents": [(d.content, d.metadata) for d in self.documents],
            "bm25_corpus": [d.content.lower().split() for d in self.documents],
        }
        with open(os.path.join(path, "kb_data.pkl"), "wb") as f:
            pickle.dump(data, f)
        print(f"💾 Index saved → {path}/")

    def load_index(self, path=INDEX_DIR):
        """Load FAISS + BM25 + documents từ disk."""
        self.faiss_index = faiss.read_index(os.path.join(path, "faiss_index"))
        with open(os.path.join(path, "kb_data.pkl"), "rb") as f:
            data = pickle.load(f)
        self.documents = [Document(c, m) for c, m in data["documents"]]
        self.bm25_index = BM25Okapi(data["bm25_corpus"])
        print(f"📂 Index loaded: {self.faiss_index.ntotal} vectors")
        return self

    def search_vector(self, query: str, top_k=10) -> List[Tuple[Document, float]]:
        """Tìm kiếm theo vector similarity (cosine)."""
        vec = self.embed_model.encode([query]).astype('float32')
        faiss.normalize_L2(vec)
        scores, indices = self.faiss_index.search(vec, top_k)
        return [(self.documents[i], float(s)) for s, i in zip(scores[0], indices[0]) if i < len(self.documents)]

    def search_bm25(self, query: str, top_k=10) -> List[Tuple[Document, float]]:
        """Tìm kiếm theo keyword BM25."""
        tokens = query.lower().split()
        scores = self.bm25_index.get_scores(tokens)
        top_idx = np.argsort(scores)[::-1][:top_k]
        return [(self.documents[i], float(scores[i])) for i in top_idx if scores[i] > 0]

    def hybrid_search(self, query: str, top_k=10, alpha=0.7) -> List[Tuple[Document, float]]:
        """
        Hybrid search: FAISS + BM25 với Reciprocal Rank Fusion (RRF).
        alpha: trọng số cho vector search (1-alpha cho BM25).
        Tự động mở rộng query với brand aliases (LV -> Louis Vuitton, ...).
        """
        # Fix B: expand query với brand aliases trước khi search
        expanded_query = expand_query(query)
        vec_results = self.search_vector(expanded_query, top_k=top_k * 2)
        bm25_results = self.search_bm25(expanded_query, top_k=top_k * 2)

        # RRF scoring
        rrf = {}
        k = 60
        for rank, (doc, _) in enumerate(vec_results):
            rrf[doc.doc_id] = rrf.get(doc.doc_id, 0) + alpha / (k + rank + 1)
        for rank, (doc, _) in enumerate(bm25_results):
            rrf[doc.doc_id] = rrf.get(doc.doc_id, 0) + (1 - alpha) / (k + rank + 1)

        doc_map = {d.doc_id: d for d, _ in vec_results + bm25_results}
        sorted_ids = sorted(rrf, key=rrf.get, reverse=True)[:top_k]
        return [(doc_map[did], rrf[did]) for did in sorted_ids if did in doc_map]


# =============================================
# CHẠY STANDALONE
# =============================================
if __name__ == "__main__":
    print("=" * 60)
    print("  MODULE 2 — Knowledge Base Builder")
    print("=" * 60)

    kb = KnowledgeBaseBuilder()
    kb.build_index()
    kb.save_index()

    # Test search
    print("\n🔍 Test hybrid search: 'sách lập trình Python'")
    results = kb.hybrid_search("sách lập trình Python", top_k=3)
    for i, (doc, score) in enumerate(results):
        print(f"  [{i+1}] Score={score:.4f} | {doc.metadata.get('source', '?')}")
        print(f"      {doc.content[:120]}...")

    print("\n🔍 Test: 'chính sách đổi trả quần áo hàng hiệu'")
    results = kb.hybrid_search("chính sách đổi trả quần áo hàng hiệu", top_k=3)
    for i, (doc, score) in enumerate(results):
        print(f"  [{i+1}] Score={score:.4f} | {doc.metadata.get('source', '?')}")
        print(f"      {doc.content[:120]}...")

    print("\n✅ Knowledge Base ready!")
