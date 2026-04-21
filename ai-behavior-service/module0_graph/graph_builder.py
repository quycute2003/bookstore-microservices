"""
================================================================
  MODULE 0 — Knowledge Graph Builder
================================================================
Đọc dữ liệu từ knowledge_base/ và xây dựng đồ thị tri thức
dùng NetworkX. Mỗi node có type + properties; mỗi edge có type.

Cách dùng:
  from module0_graph import KnowledgeGraphBuilder
  G = KnowledgeGraphBuilder().build()

Node ID convention:
  book:{id}          e.g. "book:1"
  clothes:{id}       e.g. "clothes:3"
  author:{name}      e.g. "author:Leo Tolstoy"
  brand:{name}       e.g. "brand:Louis Vuitton"
  category:{name}    e.g. "category:Văn học nước ngoài"
  scenario:{type}    e.g. "scenario:impulse_buyer"
"""

import os
import json
import glob
import pickle
import networkx as nx

from .graph_schema import NodeType, EdgeType, BRAND_ALIASES, ALIAS_TO_BRAND

KB_DIR      = os.path.join(os.path.dirname(os.path.dirname(__file__)), "module2_knowledge", "knowledge_base")
GRAPH_CACHE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "knowledge_graph.pkl")


def _fmt_price(price) -> str:
    try:
        return f"{int(float(price)):,}".replace(",", ".") + " VNĐ"
    except (TypeError, ValueError):
        return str(price)


class KnowledgeGraphBuilder:
    """
    Xây dựng Knowledge Graph từ các file JSON trong knowledge_base/:
      - products/books_catalog.json
      - products/clothes_catalog.json
      - products/categories.json
      - scenarios/*.json
    """

    def __init__(self):
        self.G: nx.DiGraph = nx.DiGraph()

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def build(self, kb_dir: str = KB_DIR) -> nx.DiGraph:
        """Build đồ thị đầy đủ từ tất cả dữ liệu KB."""
        self._load_categories(kb_dir)
        self._load_books(kb_dir)
        self._load_clothes(kb_dir)
        self._load_scenarios(kb_dir)
        self._add_cross_edges()
        print(
            f"[Graph] Built: {self.G.number_of_nodes()} nodes, "
            f"{self.G.number_of_edges()} edges"
        )
        return self.G

    def save(self, path: str = GRAPH_CACHE):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.G, f)
        print(f"[Graph] Saved → {path}")

    def load(self, path: str = GRAPH_CACHE) -> nx.DiGraph:
        with open(path, "rb") as f:
            self.G = pickle.load(f)
        print(
            f"[Graph] Loaded: {self.G.number_of_nodes()} nodes, "
            f"{self.G.number_of_edges()} edges"
        )
        return self.G

    @classmethod
    def get_or_build(cls, kb_dir: str = KB_DIR, cache: str = GRAPH_CACHE) -> nx.DiGraph:
        """Load từ cache nếu có và KB chưa thay đổi; ngược lại build mới và cache lại."""
        builder = cls()
        if os.path.exists(cache):
            # Kiểm tra cache có còn hợp lệ không (KB data chưa thay đổi)
            if not builder._is_cache_stale(kb_dir, cache):
                return builder.load(cache)
            print("[Graph] KB đã thay đổi → rebuild graph cache...")
            os.remove(cache)
            # Xóa cả GNN dataset cache vì graph thay đổi
            gnn_cache = os.path.join(os.path.dirname(cache), "gnn_dataset.pkl")
            if os.path.exists(gnn_cache):
                os.remove(gnn_cache)
                print("[Graph] GNN dataset cache cũ đã xóa → sẽ rebuild cùng graph.")
        G = builder.build(kb_dir)
        builder.save(cache)
        builder._save_kb_hash(kb_dir, cache)
        return G

    @staticmethod
    def _kb_hash(kb_dir: str) -> str:
        """Tính MD5 hash của tất cả JSON files trong knowledge_base/products/."""
        import hashlib
        h = hashlib.md5()
        products_dir = os.path.join(kb_dir, "products")
        for fname in sorted(["books_catalog.json", "clothes_catalog.json", "categories.json"]):
            fpath = os.path.join(products_dir, fname)
            if os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    h.update(f.read())
        return h.hexdigest()

    @staticmethod
    def _hash_file(cache: str) -> str:
        return cache + ".hash"

    def _is_cache_stale(self, kb_dir: str, cache: str) -> bool:
        """Trả về True nếu KB data đã thay đổi so với lúc build cache."""
        hash_file = self._hash_file(cache)
        if not os.path.exists(hash_file):
            return True  # Không có hash file → coi như stale
        with open(hash_file, "r") as f:
            saved = f.read().strip()
        return saved != self._kb_hash(kb_dir)

    def _save_kb_hash(self, kb_dir: str, cache: str):
        """Lưu hash của KB data hiện tại cùng với cache."""
        hash_file = self._hash_file(cache)
        with open(hash_file, "w") as f:
            f.write(self._kb_hash(kb_dir))


    # ------------------------------------------------------------------
    # INTERNAL LOADERS
    # ------------------------------------------------------------------

    def _add_node(self, node_id: str, node_type: str, **props):
        self.G.add_node(node_id, node_type=node_type, **props)

    def _add_edge(self, src: str, dst: str, edge_type: str, **props):
        self.G.add_edge(src, dst, edge_type=edge_type, **props)

    def _load_categories(self, kb_dir: str):
        path = os.path.join(kb_dir, "products", "categories.json")
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            categories = json.load(f)
        for cat in categories:
            nid = f"category:{cat['name']}"
            self._add_node(
                nid,
                NodeType.CATEGORY,
                id=cat["id"],
                name=cat["name"],
                description=cat.get("description", ""),
                product_type=cat.get("type", ""),
                label=cat["name"],
            )

    def _load_books(self, kb_dir: str):
        path = os.path.join(kb_dir, "products", "books_catalog.json")
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            books = json.load(f)

        for book in books:
            bid = f"book:{book['id']}"
            category = book.get("category", "")
            author_name = book.get("author", "")

            self._add_node(
                bid,
                NodeType.BOOK,
                id=book["id"],
                title=book["title"],
                author=author_name,
                category=category,
                price=book.get("price", 0),
                price_fmt=_fmt_price(book.get("price", 0)),
                stock=book.get("stock", 0),
                description=book.get("description", ""),
                label=book["title"],
            )

            # Book -> Category
            cat_id = f"category:{category}"
            if self.G.has_node(cat_id):
                self._add_edge(bid, cat_id, EdgeType.IN_CATEGORY)

            # Author node
            if author_name:
                aid = f"author:{author_name}"
                if not self.G.has_node(aid):
                    self._add_node(aid, NodeType.AUTHOR, name=author_name, label=author_name)
                self._add_edge(bid, aid, EdgeType.WRITTEN_BY)

        # SAME_AUTHOR edges (books by the same author)
        author_books: dict[str, list[str]] = {}
        for nid, data in self.G.nodes(data=True):
            if data.get("node_type") == NodeType.BOOK:
                a = data.get("author", "")
                if a:
                    author_books.setdefault(a, []).append(nid)
        for book_list in author_books.values():
            for i, b1 in enumerate(book_list):
                for b2 in book_list[i + 1:]:
                    self._add_edge(b1, b2, EdgeType.SAME_AUTHOR)
                    self._add_edge(b2, b1, EdgeType.SAME_AUTHOR)

    def _load_clothes(self, kb_dir: str):
        path = os.path.join(kb_dir, "products", "clothes_catalog.json")
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            clothes = json.load(f)

        for item in clothes:
            cid = f"clothes:{item['id']}"
            brand_name = item.get("brand", "")
            category = item.get("category", "Thời Trang Hàng Hiệu")

            self._add_node(
                cid,
                NodeType.CLOTHES,
                id=item["id"],
                name=item["name"],
                brand=brand_name,
                size=item.get("size", ""),
                color=item.get("color", ""),
                category=category,
                price=item.get("price", 0),
                price_fmt=_fmt_price(item.get("price", 0)),
                stock=item.get("stock", 0),
                description=item.get("description", ""),
                label=item["name"],
            )

            # Clothes -> Category
            cat_id = f"category:{category}"
            if self.G.has_node(cat_id):
                self._add_edge(cid, cat_id, EdgeType.IN_CATEGORY)

            # Brand node (canonical name)
            canon_brand = ALIAS_TO_BRAND.get(brand_name.lower(), brand_name)
            if canon_brand:
                brid = f"brand:{canon_brand}"
                if not self.G.has_node(brid):
                    aliases = BRAND_ALIASES.get(canon_brand, [])
                    self._add_node(
                        brid,
                        NodeType.BRAND,
                        name=canon_brand,
                        aliases=aliases,
                        label=canon_brand,
                    )
                    # Alias edges: brand -> alias strings stored as meta, not extra nodes
                self._add_edge(cid, brid, EdgeType.MADE_BY)

        # SAME_BRAND edges
        brand_items: dict[str, list[str]] = {}
        for nid, data in self.G.nodes(data=True):
            if data.get("node_type") == NodeType.CLOTHES:
                b = data.get("brand", "")
                if b:
                    brand_items.setdefault(b, []).append(nid)
        for item_list in brand_items.values():
            for i, c1 in enumerate(item_list):
                for c2 in item_list[i + 1:]:
                    self._add_edge(c1, c2, EdgeType.SAME_BRAND)
                    self._add_edge(c2, c1, EdgeType.SAME_BRAND)

    def _load_scenarios(self, kb_dir: str):
        pattern = os.path.join(kb_dir, "scenarios", "*.json")
        for fp in glob.glob(pattern):
            try:
                with open(fp, encoding="utf-8") as f:
                    sc = json.load(f)
            except Exception:
                continue

            sid = f"scenario:{sc.get('behavior_type', os.path.basename(fp))}"
            self._add_node(
                sid,
                NodeType.SCENARIO,
                behavior_type=sc.get("behavior_type", ""),
                display_name=sc.get("display_name", ""),
                characteristics=sc.get("characteristics", []),
                label=sc.get("display_name", sc.get("behavior_type", "")),
            )

            # Link recommended products back to categories
            rec = sc.get("recommended_products", {})
            for book_title in rec.get("books", []):
                # Find book node by title prefix match
                for nid, data in self.G.nodes(data=True):
                    if data.get("node_type") == NodeType.BOOK:
                        if book_title.lower() in data.get("title", "").lower():
                            self._add_edge(sid, nid, EdgeType.SUITS)
                            break
            for cloth_name in rec.get("clothes", []):
                for nid, data in self.G.nodes(data=True):
                    if data.get("node_type") == NodeType.CLOTHES:
                        if cloth_name.lower() in data.get("name", "").lower():
                            self._add_edge(sid, nid, EdgeType.SUITS)
                            break

    def _add_cross_edges(self):
        """Thêm SIMILAR edges giữa sản phẩm cùng danh mục."""
        category_products: dict[str, list[str]] = {}
        for nid, data in self.G.nodes(data=True):
            if data.get("node_type") in (NodeType.BOOK, NodeType.CLOTHES):
                cat = data.get("category", "")
                if cat:
                    category_products.setdefault(cat, []).append(nid)
        for prod_list in category_products.values():
            for i, p1 in enumerate(prod_list[:10]):   # Giới hạn để tránh tổ hợp lớn
                for p2 in prod_list[i + 1: i + 4]:   # Mỗi node chỉ kết nối 3 láng giềng
                    if not self.G.has_edge(p1, p2):
                        self._add_edge(p1, p2, EdgeType.SIMILAR)
                    if not self.G.has_edge(p2, p1):
                        self._add_edge(p2, p1, EdgeType.SIMILAR)


# =============================================
# STANDALONE RUN
# =============================================
if __name__ == "__main__":
    builder = KnowledgeGraphBuilder()
    G = builder.build()
    builder.save()

    print("\n--- Node sample ---")
    for nid, data in list(G.nodes(data=True))[:5]:
        print(f"  {nid}: {data.get('node_type')} | {data.get('label')}")

    print("\n--- Edge sample ---")
    for src, dst, data in list(G.edges(data=True))[:8]:
        print(f"  {src} --[{data.get('edge_type')}]--> {dst}")
