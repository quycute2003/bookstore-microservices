"""
================================================================
  MODULE 0 — Graph Retriever  (Neo4j primary / NetworkX fallback)
================================================================
Chiến lược backend:
  1. Thử kết nối Neo4j khi khởi tạo.
  2. Nếu Neo4j sẵn sàng: push graph (lần đầu) rồi dùng Cypher.
  3. Nếu Neo4j chưa lên (startup 30s, chưa deploy): dùng NetworkX BFS.
  4. Sau mỗi lần request thất bại trên Neo4j, retry lần sau.
"""

from __future__ import annotations

import os
import re
import time
from typing import List, Tuple, Optional

import networkx as nx

from .graph_schema import (
    NodeType, EdgeType,
    BRAND_ALIASES, ALIAS_TO_BRAND, resolve_brand,
)
from .graph_builder import KnowledgeGraphBuilder, KB_DIR, GRAPH_CACHE


# =============================================
# DOCUMENT (tương thích với KnowledgeBaseBuilder)
# =============================================
class GraphDocument:
    """Giả lập Document của kb_builder để tương thích với reranker."""

    def __init__(self, content: str, node_id: str, node_type: str, score: float = 1.0):
        import hashlib
        self.content  = content
        self.node_id  = node_id
        self.node_type = node_type
        self.doc_id   = "graph_" + hashlib.md5(content.encode()).hexdigest()[:10]
        self.metadata = {
            "source":  f"graph/{node_type}/{node_id}",
            "type":    "graph",
            "node_id": node_id,
        }
        self._score = score


# =============================================
# GRAPH RETRIEVER
# =============================================
class GraphRetriever:
    """
    Truy vấn Knowledge Graph và trả về (GraphDocument, score).
    Tự động chọn Neo4j hoặc NetworkX backend.
    """

    CATEGORY_KEYWORDS = {
        "văn học": "Văn học nước ngoài",
        "tiểu thuyết": "Văn học nước ngoài",
        "văn học trong nước": "Văn học trong nước",
        "khoa học": "Khoa học - Công nghệ",
        "lập trình": "Khoa học - Công nghệ",
        "công nghệ": "Khoa học - Công nghệ",
        "python": "Khoa học - Công nghệ",
        "kinh tế": "Kinh tế - Kinh doanh",
        "kinh doanh": "Kinh tế - Kinh doanh",
        "khởi nghiệp": "Kinh tế - Kinh doanh",
        "kỹ năng": "Kỹ năng sống",
        "phát triển bản thân": "Kỹ năng sống",
        "tâm lý": "Tâm lý học",
        "lịch sử": "Lịch sử - Địa lý",
        "địa lý": "Lịch sử - Địa lý",
        "thiếu nhi": "Thiếu nhi",
        "thời trang": "Thời Trang Hàng Hiệu",
        "hàng hiệu": "Thời Trang Hàng Hiệu",
        "luxury": "Thời Trang Hàng Hiệu",
        "áo": "Thời Trang Hàng Hiệu",
        "jacket": "Thời Trang Hàng Hiệu",
        "hoodie": "Thời Trang Hàng Hiệu",
    }

    def __init__(self, G: Optional[nx.DiGraph] = None):
        # 1. Load / build NetworkX graph (luôn có, dù Neo4j không lên)
        if G is None:
            G = KnowledgeGraphBuilder.get_or_build()
        self._nx_graph: nx.DiGraph = G

        # 2. Thử kết nối Neo4j
        self._neo4j = None
        self._last_neo4j_attempt = 0.0
        self._neo4j_retry_interval = 30   # giây
        self._try_connect_neo4j(push_if_empty=True)

    # ------------------------------------------------------------------
    # NEO4J CONNECTION MANAGEMENT
    # ------------------------------------------------------------------

    def _try_connect_neo4j(self, push_if_empty: bool = False) -> bool:
        """
        Thử kết nối Neo4j. Trả về True nếu thành công.
        Không raise — mọi lỗi đều được xử lý nội bộ.
        """
        now = time.time()
        if self._neo4j is not None:
            return True
        if now - self._last_neo4j_attempt < self._neo4j_retry_interval:
            return False   # Chưa đến thời điểm retry

        self._last_neo4j_attempt = now
        try:
            from .neo4j_connector import Neo4jConnector
            conn = Neo4jConnector()
            # Lần đầu: push graph nếu Neo4j còn trống
            if push_if_empty and not conn.is_graph_populated():
                print("[Graph] Neo4j trống — đang push Knowledge Graph...")
                conn.push_graph(self._nx_graph)
            self._neo4j = conn
            print("[Graph] Backend: Neo4j")
            return True
        except Exception as e:
            print(f"[Graph] Neo4j unavailable → dùng NetworkX fallback. ({e})")
            return False

    # ------------------------------------------------------------------
    # PUBLIC
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 10) -> List[Tuple[GraphDocument, float]]:
        """
        Trả về (GraphDocument, score).
        Ưu tiên Neo4j; fallback NetworkX nếu Neo4j lỗi.
        """
        # Retry kết nối Neo4j mỗi 30 giây
        if self._neo4j is None:
            self._try_connect_neo4j(push_if_empty=True)

        seed_node_ids = self._extract_seed_nodes(query)
        if not seed_node_ids:
            return []

        if self._neo4j is not None:
            try:
                return self._retrieve_neo4j(seed_node_ids, top_k)
            except Exception as e:
                print(f"[Graph] Neo4j query error → fallback NetworkX: {e}")
                self._neo4j = None   # Reset để retry sau

        return self._retrieve_networkx(seed_node_ids, top_k)

    # ------------------------------------------------------------------
    # BACKEND: NEO4J
    # ------------------------------------------------------------------

    def _retrieve_neo4j(
        self, seed_node_ids: List[str], top_k: int
    ) -> List[Tuple[GraphDocument, float]]:
        raw = self._neo4j.query_related(seed_node_ids, hops=2, limit=top_k * 3)

        results: List[Tuple[GraphDocument, float]] = []
        seen_ids: set = set()
        for item in raw:
            node_id   = item["node_id"]
            node_type = item["node_type"]
            props     = item["props"]
            hop       = item["hop"]

            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)

            # score: hop 1 → 1.0, hop 2 → 0.6, ...
            score = round(1.0 * (0.6 ** (hop - 1)), 4)

            doc = self._props_to_document(node_id, node_type, props, score)
            if doc:
                results.append((doc, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # BACKEND: NETWORKX
    # ------------------------------------------------------------------

    def _retrieve_networkx(
        self, seed_node_ids: List[str], top_k: int
    ) -> List[Tuple[GraphDocument, float]]:
        G = self._nx_graph
        visited: dict[str, float] = {}
        queue = [(nid, 1.0) for nid in seed_node_ids if G.has_node(nid)]

        while queue:
            node_id, score = queue.pop(0)
            if node_id in visited:
                continue
            visited[node_id] = score

            next_score = round(score * 0.6, 4)
            if next_score < 0.1:
                continue
            for nb in list(G.successors(node_id)) + list(G.predecessors(node_id)):
                if nb not in visited:
                    queue.append((nb, next_score))

        results: List[Tuple[GraphDocument, float]] = []
        for node_id, score in visited.items():
            data     = G.nodes[node_id]
            ntype    = data.get("node_type", "")
            props    = dict(data)
            doc      = self._props_to_document(node_id, ntype, props, score)
            if doc:
                results.append((doc, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # ENTITY EXTRACTION (dùng chung cho cả hai backend)
    # ------------------------------------------------------------------

    def _extract_seed_nodes(self, query: str) -> List[str]:
        G = self._nx_graph
        seeds: set[str] = set()
        q_lower = query.lower()
        tokens = re.split(r"[\s,!?;:()/]+", q_lower)

        # 1. Brand / alias
        for tok in tokens:
            canon = resolve_brand(tok)
            if canon:
                brid = f"brand:{canon}"
                if G.has_node(brid):
                    seeds.add(brid)
                    for pred in G.predecessors(brid):
                        if G.nodes[pred].get("node_type") == NodeType.CLOTHES:
                            seeds.add(pred)

        # 2. Category keywords
        for kw, cat_name in self.CATEGORY_KEYWORDS.items():
            if kw in q_lower:
                cat_id = f"category:{cat_name}"
                if G.has_node(cat_id):
                    seeds.add(cat_id)

        # 3. Author name exact match
        for nid, data in G.nodes(data=True):
            if data.get("node_type") == NodeType.AUTHOR:
                name = data.get("name", "").lower()
                if name and name in q_lower:
                    seeds.add(nid)

        # 4. Direct product title/name match
        for nid, data in G.nodes(data=True):
            ntype = data.get("node_type")
            if ntype == NodeType.BOOK:
                title = data.get("title", "").lower()
                if title and len(title) > 4 and title in q_lower:
                    seeds.add(nid)
            elif ntype == NodeType.CLOTHES:
                name = data.get("name", "").lower()
                if name and len(name) > 4 and name in q_lower:
                    seeds.add(nid)

        return list(seeds)

    # ------------------------------------------------------------------
    # NODE → DOCUMENT  (chung cho cả hai backend)
    # ------------------------------------------------------------------

    def _props_to_document(
        self, node_id: str, node_type: str, props: dict, score: float
    ) -> Optional[GraphDocument]:
        if node_type == NodeType.BOOK:
            content = self._fmt_book(props)
        elif node_type == NodeType.CLOTHES:
            content = self._fmt_clothes(props)
        elif node_type == NodeType.BRAND:
            content = self._fmt_brand(node_id, props)
        elif node_type == NodeType.CATEGORY:
            content = self._fmt_category(node_id, props)
        elif node_type == NodeType.AUTHOR:
            content = self._fmt_author(node_id, props)
        else:
            return None   # Scenario nodes không hiển thị cho user

        if not content or len(content.strip()) < 10:
            return None
        return GraphDocument(content, node_id, node_type, score)

    def _fmt_book(self, p: dict) -> str:
        lines = [f"[Graph] Sản phẩm sách: {p.get('title', '')}"]
        if p.get("author"):
            lines.append(f"Tác giả: {p['author']}")
        if p.get("category"):
            lines.append(f"Thể loại: {p['category']}")
        if p.get("price_fmt"):
            lines.append(f"Giá: {p['price_fmt']}")
        elif p.get("price"):
            lines.append(f"Giá: {self._fmt_price(p['price'])}")
        if p.get("stock") is not None:
            lines.append(f"Tồn kho: {p['stock']} cuốn")
        if p.get("description"):
            lines.append(f"Mô tả: {p['description']}")
        return "\n".join(lines)

    def _fmt_clothes(self, p: dict) -> str:
        brand = p.get("brand", "")
        aliases = BRAND_ALIASES.get(brand, [])
        brand_display = f"{brand} ({', '.join(aliases)})" if aliases else brand
        lines = [f"[Graph] Sản phẩm thời trang: {p.get('name', '')}"]
        if brand:
            lines.append(f"Thương hiệu: {brand_display}")
        if p.get("category"):
            lines.append(f"Danh mục: {p['category']}")
        if p.get("size"):
            lines.append(f"Size: {p['size']}")
        if p.get("color"):
            lines.append(f"Màu sắc: {p['color']}")
        if p.get("price_fmt"):
            lines.append(f"Giá: {p['price_fmt']}")
        elif p.get("price"):
            lines.append(f"Giá: {self._fmt_price(p['price'])}")
        if p.get("stock") is not None:
            lines.append(f"Tồn kho: {p['stock']} sản phẩm")
        if p.get("description"):
            lines.append(f"Mô tả: {p['description']}")
        return "\n".join(lines)

    def _fmt_brand(self, node_id: str, p: dict) -> str:
        brand_name = p.get("name", "")
        aliases = p.get("aliases", [])
        if isinstance(aliases, str):
            aliases = []

        # Lấy sản phẩm từ NetworkX (dùng làm nguồn bổ sung)
        products = []
        G = self._nx_graph
        if G.has_node(node_id):
            for pred in G.predecessors(node_id):
                pdata = G.nodes[pred]
                if pdata.get("node_type") == NodeType.CLOTHES:
                    pname  = pdata.get("name", "")
                    pprice = pdata.get("price_fmt", "")
                    products.append(f"{pname} ({pprice})")

        lines = [f"[Graph] Thương hiệu: {brand_name}"]
        if aliases:
            lines.append(f"Tên khác / viết tắt: {', '.join(aliases)}")
        if products:
            lines.append("Sản phẩm đang có: " + "; ".join(products))
        return "\n".join(lines)

    def _fmt_category(self, node_id: str, p: dict) -> str:
        name = p.get("name", "")
        desc = p.get("description", "")
        G = self._nx_graph
        products = []
        if G.has_node(node_id):
            for pred in G.predecessors(node_id):
                pdata = G.nodes[pred]
                ptype = pdata.get("node_type")
                if ptype == NodeType.BOOK:
                    products.append(pdata.get("title", ""))
                elif ptype == NodeType.CLOTHES:
                    products.append(pdata.get("name", ""))

        lines = [f"[Graph] Danh mục: {name}"]
        if desc:
            lines.append(f"Mô tả: {desc}")
        if products:
            lines.append("Sản phẩm trong danh mục: " + "; ".join(products[:8]))
        return "\n".join(lines)

    def _fmt_author(self, node_id: str, p: dict) -> str:
        name = p.get("name", "")
        G = self._nx_graph
        books = []
        if G.has_node(node_id):
            for pred in G.predecessors(node_id):
                bdata = G.nodes[pred]
                if bdata.get("node_type") == NodeType.BOOK:
                    title = bdata.get("title", "")
                    price = bdata.get("price_fmt", "")
                    books.append(f"{title} ({price})")
        if not books:
            return ""
        lines = [f"[Graph] Tác giả: {name}"]
        lines.append("Tác phẩm: " + "; ".join(books))
        return "\n".join(lines)

    @staticmethod
    def _fmt_price(price) -> str:
        try:
            return f"{int(float(price)):,}".replace(",", ".") + " VNĐ"
        except (TypeError, ValueError):
            return str(price)


# =============================================
# STANDALONE TEST
# =============================================
if __name__ == "__main__":
    retriever = GraphRetriever()

    tests = [
        "áo LV giá bao nhiêu",
        "sách tâm lý học hay nhất",
        "áo khoác Gucci",
        "sách lập trình Python",
        "YSL có sản phẩm gì",
        "sách của Leo Tolstoy",
    ]

    backend = "Neo4j" if retriever._neo4j else "NetworkX"
    print(f"\n=== Backend: {backend} ===")

    for q in tests:
        print(f"\n--- Query: '{q}' ---")
        results = retriever.retrieve(q, top_k=3)
        if not results:
            print("  (no graph results)")
        for doc, score in results:
            print(f"  [{score:.2f}] {doc.node_type}/{doc.node_id}")
            print(f"    {doc.content[:100].replace(chr(10), ' ')}")
