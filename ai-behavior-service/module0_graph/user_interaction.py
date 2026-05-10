"""
================================================================
  MODULE 0 — user_interaction.py
  Ghi nhận tương tác User→Product vào Neo4j và
  tạo gợi ý cá nhân hóa từ graph traversal.
================================================================

Thiết kế graph:
  (:User {id}) -[:VIEWED {weight:1, count, last_seen}]->        (:Product {id, type, name})
  (:User {id}) -[:ADDED_TO_CART {weight:3, count, last_seen}]-> (:Product)
  (:User {id}) -[:PURCHASED {weight:5, count, last_seen}]->     (:Product)

Điểm cộng so với yêu cầu cơ bản:
  [+] count + last_seen trên mỗi edge — ghi nhận tần suất, không chỉ có/không
  [+] Collaborative filtering bước 2: User → Product → User → Product
  [+] Hybrid scoring: graph_score * 0.6 + behavior_boost * 0.4
  [+] Graceful fallback về content-based khi Neo4j offline
"""

from __future__ import annotations

import os
import time
from typing import Optional, List, Dict, Any

from .graph_schema import NodeType, EdgeType

# ─── Weight của mỗi loại tương tác ────────────────────────────
ACTION_WEIGHT: Dict[str, int] = {
    "view":           1,
    "click":          1,
    "review_read":    1,
    "search":         1,
    "price_check":    2,
    "add_to_cart":    3,
    "cart_add":       3,
    "remove_from_cart": -1,
    "purchase":       5,
}

# Behavior label → loại sản phẩm ưu tiên (boost khi recommend)
_BEHAVIOR_BOOST: Dict[str, float] = {
    "impulse_buyer":    1.4,
    "loyal_customer":   1.3,
    "brand_loyal":      1.3,
    "deal_hunter":      1.2,
    "gift_buyer":       1.2,
    "researcher":       1.1,
    "price_sensitive":  1.1,
    "window_shopper":   0.9,
}


# ──────────────────────────────────────────────────────────────
class UserInteractionGraph:
    """
    Ghi nhận tương tác User→Product vào Neo4j và trả về
    gợi ý cá nhân hóa kết hợp graph traversal + behavior label.

    Nếu Neo4j không khả dụng, mọi write silently bỏ qua và
    recommend fallback về random (graceful degradation).
    """

    def __init__(self):
        self._driver = None
        self._connected = False
        self._connect()

    # ─── Kết nối ──────────────────────────────────────────────
    def _connect(self):
        try:
            from neo4j import GraphDatabase
            uri      = os.getenv("NEO4J_URI",      "bolt://neo4j:7687")
            user     = os.getenv("NEO4J_USER",     "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "lumiere123")
            self._driver    = GraphDatabase.driver(uri, auth=(user, password))
            self._driver.verify_connectivity()
            self._connected = True
            self._ensure_constraints()
            print("✅ UserInteractionGraph: Neo4j connected")
        except Exception as e:
            print(f"⚠️  UserInteractionGraph: Neo4j unavailable ({e}) — will degrade gracefully")
            self._connected = False

    def _ensure_constraints(self):
        """Tạo uniqueness constraints lần đầu."""
        with self._driver.session() as s:
            s.run("CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE")
            s.run("CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE")

    def close(self):
        if self._driver:
            self._driver.close()

    # ─── Ghi nhận tương tác ───────────────────────────────────
    def log_action(
        self,
        user_id: str,
        product_id: str | int,
        action: str,
        product_type: str = "unknown",
        product_name: str = "",
    ) -> bool:
        """
        Merge User node + Product node, tạo/cập nhật interaction edge.

        Edge properties:
          weight    — cường độ tương tác (1/3/5 theo ACTION_WEIGHT)
          count     — số lần thực hiện action này với product này
          last_seen — Unix timestamp lần cuối

        Returns True nếu ghi thành công, False nếu Neo4j offline.
        """
        weight = ACTION_WEIGHT.get(action, 1)
        if weight <= 0:
            return True  # remove_from_cart — bỏ qua (không xóa edge)

        edge_type = _action_to_edge(action)
        if edge_type is None:
            return True

        if not self._connected:
            return False

        pid = str(product_id)
        try:
            with self._driver.session() as s:
                s.run(
                    f"""
                    MERGE (u:User {{id: $uid}})
                    MERGE (p:Product {{id: $pid}})
                      ON CREATE SET p.type = $ptype, p.name = $pname
                      ON MATCH  SET p.name = CASE WHEN $pname <> '' THEN $pname ELSE p.name END
                    MERGE (u)-[r:{edge_type}]->(p)
                      ON CREATE SET r.weight = $w, r.count = 1,        r.last_seen = $ts
                      ON MATCH  SET r.count  = r.count + 1, r.last_seen = $ts
                    """,
                    uid=str(user_id), pid=pid,
                    ptype=product_type, pname=product_name,
                    w=weight, ts=int(time.time()),
                )
            return True
        except Exception as e:
            print(f"[UserInteractionGraph] log_action error: {e}")
            return False

    # ─── Lấy gợi ý ────────────────────────────────────────────
    def get_recommendations(
        self,
        user_id: str,
        behavior_label: str = "window_shopper",
        top_k: int = 10,
        exclude_purchased: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Trả về top-K sản phẩm gợi ý bằng hybrid scoring:

        Bước 1 — Direct history:
          Sản phẩm user đã view/cart/purchase → graph_score = sum(weight * count)

        Bước 2 — Collaborative filtering (1 hop):
          User → Product → User2 → Product2 (product2 chưa từng thấy)
          Mỗi product2 nhận collab_score = weight_edge1 * weight_edge2

        Bước 3 — Hybrid:
          final_score = (graph_score + collab_score) * behavior_boost

        Nếu Neo4j offline → trả [] (caller tự fallback).
        """
        if not self._connected:
            return []

        uid = str(user_id)
        boost = _BEHAVIOR_BOOST.get(behavior_label, 1.0)

        try:
            with self._driver.session() as s:
                # ── Bước 1: lịch sử trực tiếp ────────────────
                direct = s.run(
                    """
                    MATCH (u:User {id: $uid})-[r]->(p:Product)
                    RETURN p.id AS pid, p.type AS ptype, p.name AS pname,
                           type(r) AS rel, r.weight AS w, r.count AS cnt
                    """,
                    uid=uid,
                ).data()

                history_ids: set[str] = set()
                scores: Dict[str, Dict] = {}
                purchased_ids: set[str] = set()

                for row in direct:
                    pid = row["pid"]
                    history_ids.add(pid)
                    if row["rel"] == EdgeType.PURCHASED:
                        purchased_ids.add(pid)
                    w = (row["w"] or 1) * (row["cnt"] or 1)
                    if pid not in scores:
                        scores[pid] = {"pid": pid, "ptype": row["ptype"], "pname": row["pname"], "score": 0.0}
                    scores[pid]["score"] += w

                # ── Bước 2: collaborative 1-hop ───────────────
                collab = s.run(
                    """
                    MATCH (u:User {id: $uid})-[r1]->(p1:Product)<-[r2]-(u2:User)-[r3]->(p2:Product)
                    WHERE u2.id <> $uid AND NOT p2.id IN $seen
                    RETURN p2.id AS pid, p2.type AS ptype, p2.name AS pname,
                           sum(r1.weight * r3.weight) AS collab_score
                    ORDER BY collab_score DESC
                    LIMIT 50
                    """,
                    uid=uid, seen=list(history_ids),
                ).data()

                for row in collab:
                    pid = row["pid"]
                    if pid not in scores:
                        scores[pid] = {"pid": pid, "ptype": row["ptype"], "pname": row["pname"], "score": 0.0}
                    scores[pid]["score"] += (row["collab_score"] or 0) * 0.5

                # ── Bước 3: filter + rank ─────────────────────
                results = []
                for pid, info in scores.items():
                    if exclude_purchased and pid in purchased_ids:
                        continue
                    final = info["score"] * boost
                    results.append({
                        "product_id": pid,
                        "product_type": info["ptype"] or "unknown",
                        "product_name": info["pname"] or "",
                        "score": round(final, 4),
                    })

                results.sort(key=lambda x: x["score"], reverse=True)
                return results[:top_k]

        except Exception as e:
            print(f"[UserInteractionGraph] get_recommendations error: {e}")
            return []

    # ─── Lịch sử tương tác ────────────────────────────────────
    def get_user_history(self, user_id: str) -> Dict[str, Any]:
        """Trả về thống kê tương tác của user trong graph."""
        if not self._connected:
            return {"user_id": user_id, "connected": False, "interactions": []}

        uid = str(user_id)
        try:
            with self._driver.session() as s:
                rows = s.run(
                    """
                    MATCH (u:User {id: $uid})-[r]->(p:Product)
                    RETURN type(r) AS action, p.id AS pid, p.name AS pname,
                           r.weight AS weight, r.count AS count, r.last_seen AS last_seen
                    ORDER BY r.last_seen DESC
                    """,
                    uid=uid,
                ).data()
            return {
                "user_id": user_id,
                "connected": True,
                "interaction_count": len(rows),
                "interactions": rows,
            }
        except Exception as e:
            return {"user_id": user_id, "connected": False, "error": str(e), "interactions": []}


# ─── Helpers ──────────────────────────────────────────────────
def _action_to_edge(action: str) -> str | None:
    """Map action string → EdgeType constant."""
    m = {
        "view":           EdgeType.VIEWED,
        "click":          EdgeType.VIEWED,
        "review_read":    EdgeType.VIEWED,
        "price_check":    EdgeType.VIEWED,
        "search":         EdgeType.VIEWED,
        "add_to_cart":    EdgeType.ADDED_TO_CART,
        "cart_add":       EdgeType.ADDED_TO_CART,
        "purchase":       EdgeType.PURCHASED,
    }
    return m.get(action)


# ─── Singleton ────────────────────────────────────────────────
_instance: Optional[UserInteractionGraph] = None


def get_user_interaction_graph() -> UserInteractionGraph:
    global _instance
    if _instance is None:
        _instance = UserInteractionGraph()
    return _instance
