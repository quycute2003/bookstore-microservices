"""
================================================================
  USER KB GRAPH — Xây dựng Neo4j Knowledge Graph từ user data
================================================================
Graph schema:
  (:User {user_id, behavior_label, total_sessions})
    -[:HAS_BEHAVIOR]->(:BehaviorType {name, description, avg_metrics...})
    -[:HAD_SESSION]->(:Session {user_id, session_id, features...})

  (:BehaviorType)-[:SIMILAR_TO {similarity}]->(:BehaviorType)
  (:Session)-[:BELONGS_TO]->(:User)

Chạy standalone:
  cd ai-behavior-service
  python -m module0_graph.user_kb_builder

Hoặc xem trong Neo4j Browser (http://localhost:7474):
  MATCH (n) RETURN n LIMIT 100
================================================================
"""

import os
import json
import numpy as np
import pandas as pd
from pathlib import Path

# =============================================
# NEO4J CONNECTOR
# =============================================
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    print("⚠️  neo4j driver chưa install — chỉ build NetworkX fallback")

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://neo4j:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Mô tả hành vi (khớp với data_pipeline.py)
BEHAVIOR_DESCRIPTIONS = {
    "impulse_buyer":   "Khách mua nhanh, ít cân nhắc, bị thu hút bởi khuyến mãi",
    "researcher":      "Xem nhiều, so sánh kỹ, đọc review trước khi quyết định",
    "loyal_customer":  "Quay lại thường xuyên, mua đều đặn, ít đổi trả",
    "price_sensitive": "Tìm giá tốt nhất, hay dùng mã giảm giá, so sánh giá",
    "window_shopper":  "Xem nhiều nhưng mua rất ít, chỉ lướt qua",
    "brand_loyal":     "Trung thành với 1 brand, mua lặp lại cùng loại hàng",
    "deal_hunter":     "Săn sale, mua số lượng lớn khi có promotion",
    "gift_buyer":      "Mua quà tặng: session ngắn, giá cao, ít đổi trả",
}

# Các cặp behavior có liên quan (cho edge SIMILAR_TO)
BEHAVIOR_SIMILARITIES = [
    ("impulse_buyer",   "deal_hunter",     0.65),  # cùng mua nhanh khi kích thích
    ("impulse_buyer",   "gift_buyer",      0.50),  # cùng quyết nhanh
    ("researcher",      "price_sensitive", 0.60),  # cùng search nhiều, cân nhắc kỹ
    ("loyal_customer",  "brand_loyal",     0.80),  # cùng tính trung thành cao
    ("price_sensitive", "deal_hunter",     0.70),  # cùng tìm giá rẻ
    ("window_shopper",  "researcher",      0.45),  # cùng browse nhiều
]


class UserKBBuilder:
    """
    Đọc data_user500.csv và xây dựng Knowledge Graph trong Neo4j.
    """

    def __init__(self, csv_path="data/data_user500.csv"):
        self.csv_path = csv_path
        self.driver   = None

    def load_data(self):
        """Đọc CSV và tổng hợp thống kê per user."""
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(
                f"Không tìm thấy {self.csv_path}. "
                "Hãy chạy: python -m module1_behavior.data_pipeline trước."
            )
        df = pd.read_csv(self.csv_path, encoding="utf-8-sig")
        print(f"✅ Loaded {len(df)} rows from {self.csv_path}")
        print(f"   Users: {df['user_id'].nunique()} | Behaviors: {df['behavior_label'].nunique()}")
        return df

    def _compute_user_stats(self, df):
        """Tổng hợp thống kê trung bình mỗi user (dùng làm node properties)."""
        feature_cols = [
            "click_count", "view_count", "purchase_count", "time_on_page",
            "cart_add_count", "search_count", "session_duration",
            "avg_price_viewed", "category_diversity", "return_rate",
        ]
        stats = (
            df.groupby(["user_id", "behavior_label", "behavior_id"])[feature_cols]
            .mean()
            .round(3)
            .reset_index()
        )
        stats["total_sessions"] = df.groupby("user_id")["session_id"].count().values
        return stats

    def _compute_behavior_stats(self, df):
        """Tổng hợp thống kê trung bình mỗi behavior type."""
        feature_cols = [
            "click_count", "view_count", "purchase_count", "time_on_page",
            "cart_add_count", "search_count", "session_duration",
            "avg_price_viewed", "category_diversity", "return_rate",
        ]
        stats = (
            df.groupby("behavior_label")[feature_cols]
            .mean()
            .round(3)
            .reset_index()
        )
        stats["user_count"] = df.groupby("behavior_label")["user_id"].nunique().values
        return stats

    def connect_neo4j(self):
        """Kết nối Neo4j."""
        if not NEO4J_AVAILABLE:
            return False
        try:
            self.driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            self.driver.verify_connectivity()
            print(f"[Neo4j] Connected: {NEO4J_URI}")
            return True
        except Exception as e:
            print(f"[Neo4j] Không kết nối được: {e}")
            return False

    def clear_user_graph(self, session):
        """Xóa các node User/BehaviorType/Session cũ (nếu có)."""
        session.run("MATCH (n:User) DETACH DELETE n")
        session.run("MATCH (n:BehaviorType) DETACH DELETE n")
        session.run("MATCH (n:UserSession) DETACH DELETE n")
        print("[Neo4j] Đã xóa graph user cũ")

    def push_behavior_types(self, session, behavior_stats):
        """Tạo node BehaviorType."""
        for _, row in behavior_stats.iterrows():
            name = row["behavior_label"]
            props = {
                "name":             name,
                "description":      BEHAVIOR_DESCRIPTIONS.get(name, ""),
                "user_count":       int(row["user_count"]),
                "avg_click":        float(row["click_count"]),
                "avg_view":         float(row["view_count"]),
                "avg_purchase":     float(row["purchase_count"]),
                "avg_price":        float(row["avg_price_viewed"]),
                "avg_return_rate":  float(row["return_rate"]),
                "avg_search":       float(row["search_count"]),
            }
            session.run(
                "MERGE (b:BehaviorType {name: $name}) SET b += $props",
                name=name, props=props
            )
        print(f"[Neo4j] Pushed {len(behavior_stats)} BehaviorType nodes")

    def push_similarity_edges(self, session):
        """Tạo edge SIMILAR_TO giữa các BehaviorType."""
        for src, dst, sim in BEHAVIOR_SIMILARITIES:
            session.run("""
                MATCH (a:BehaviorType {name: $src})
                MATCH (b:BehaviorType {name: $dst})
                MERGE (a)-[r:SIMILAR_TO]->(b)
                SET r.similarity = $sim
                MERGE (b)-[r2:SIMILAR_TO]->(a)
                SET r2.similarity = $sim
            """, src=src, dst=dst, sim=sim)
        print(f"[Neo4j] Pushed {len(BEHAVIOR_SIMILARITIES)} SIMILAR_TO edges")

    def push_users(self, session, user_stats, batch_size=50):
        """Tạo node User + edge HAS_BEHAVIOR."""
        total = 0
        rows = user_stats.to_dict("records")

        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            for row in batch:
                user_id = row["user_id"]
                label   = row["behavior_label"]
                props   = {
                    "user_id":        user_id,
                    "behavior_label": label,
                    "behavior_id":    int(row["behavior_id"]),
                    "total_sessions": int(row["total_sessions"]),
                    "avg_click":      float(row["click_count"]),
                    "avg_view":       float(row["view_count"]),
                    "avg_purchase":   float(row["purchase_count"]),
                    "avg_price":      float(row["avg_price_viewed"]),
                    "avg_return":     float(row["return_rate"]),
                }
                session.run(
                    "MERGE (u:User {user_id: $user_id}) SET u += $props",
                    user_id=user_id, props=props
                )
                session.run("""
                    MATCH (u:User {user_id: $user_id})
                    MATCH (b:BehaviorType {name: $label})
                    MERGE (u)-[:HAS_BEHAVIOR]->(b)
                """, user_id=user_id, label=label)
                total += 1

        print(f"[Neo4j] Pushed {total} User nodes + HAS_BEHAVIOR edges")

    def push_sessions(self, session, df, sample_per_user=3):
        """
        Tạo node UserSession (lấy mẫu 3 sessions/user để tránh quá nhiều nodes).
        """
        feature_cols = [
            "click_count", "view_count", "purchase_count", "time_on_page",
            "cart_add_count", "search_count", "session_duration",
            "avg_price_viewed", "category_diversity", "return_rate",
        ]
        total = 0
        for user_id, group in df.groupby("user_id"):
            sample = group.head(sample_per_user)
            for _, row in sample.iterrows():
                node_id = f"{user_id}_s{int(row['session_id'])}"
                props = {k: float(row[k]) for k in feature_cols}
                props["node_id"]   = node_id
                props["user_id"]   = user_id
                props["session_id"] = int(row["session_id"])

                session.run(
                    "MERGE (s:UserSession {node_id: $node_id}) SET s += $props",
                    node_id=node_id, props=props
                )
                session.run("""
                    MATCH (u:User {user_id: $user_id})
                    MATCH (s:UserSession {node_id: $node_id})
                    MERGE (u)-[:HAD_SESSION]->(s)
                """, user_id=user_id, node_id=node_id)
                total += 1

        print(f"[Neo4j] Pushed {total} UserSession nodes + HAD_SESSION edges")

    def build(self, push_sessions=True):
        """Luồng chính: đọc CSV → build graph."""
        print("\n" + "=" * 60)
        print("  USER KB GRAPH — Building Neo4j Knowledge Graph")
        print("=" * 60)

        # Load data
        df          = self.load_data()
        user_stats  = self._compute_user_stats(df)
        behav_stats = self._compute_behavior_stats(df)

        print(f"\n  Users:         {len(user_stats)}")
        print(f"  BehaviorTypes: {len(behav_stats)}")
        print(f"  Sessions(total): {len(df)}")

        # Connect & push
        if not self.connect_neo4j():
            print("\n⚠️  Neo4j không available. Lưu stats ra JSON thay thế.")
            self._save_json_fallback(user_stats, behav_stats)
            return

        with self.driver.session() as sess:
            self.clear_user_graph(sess)
            self.push_behavior_types(sess, behav_stats)
            self.push_similarity_edges(sess)
            self.push_users(sess, user_stats)
            if push_sessions:
                self.push_sessions(sess, df, sample_per_user=3)

        # Stats
        with self.driver.session() as sess:
            n_nodes = sess.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            n_edges = sess.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            print(f"\n[Neo4j] ✅ Graph built: {n_nodes} nodes, {n_edges} edges")

        self.driver.close()
        print("\n✅ User KB Graph complete!")

    def _save_json_fallback(self, user_stats, behav_stats):
        """Fallback khi Neo4j không available."""
        os.makedirs("data", exist_ok=True)
        behav_stats.to_json("data/behavior_stats.json", orient="records",
                            force_ascii=False, indent=2)
        user_stats.head(20).to_json("data/user_stats_sample.json",
                                    orient="records", force_ascii=False, indent=2)
        print("  💾 data/behavior_stats.json")
        print("  💾 data/user_stats_sample.json (20 dòng mẫu)")


# =============================================
# STANDALONE
# =============================================
if __name__ == "__main__":
    builder = UserKBBuilder(csv_path="data/data_user500.csv")
    builder.build(push_sessions=True)
