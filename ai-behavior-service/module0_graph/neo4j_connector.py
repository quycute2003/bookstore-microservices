"""
================================================================
  MODULE 0 — Neo4j Connector
================================================================
Kết nối Neo4j qua Bolt protocol. Nếu Neo4j chưa sẵn sàng
(đang khởi động, chưa deploy), tự động báo lỗi để
GraphRetriever fallback về NetworkX.

Sử dụng:
  from module0_graph.neo4j_connector import Neo4jConnector
  conn = Neo4jConnector()           # raises if unavailable
  conn.push_graph(nx_graph)         # push NetworkX → Neo4j
  results = conn.query_related(["brand:Louis Vuitton"], hops=2)
"""

from __future__ import annotations

import os
import time
import networkx as nx
from typing import List, Dict, Any, Optional

from .graph_schema import NodeType, BRAND_ALIASES

# =============================================
# CẤU HÌNH — đọc từ env (inject bởi docker-compose)
# =============================================
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://neo4j:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "lumiere123")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def _fmt_price(price) -> str:
    try:
        return f"{int(float(price)):,}".replace(",", ".") + " VNĐ"
    except (TypeError, ValueError):
        return str(price)


class Neo4jConnector:
    """
    Wrapper quanh neo4j Python driver.
    - Thử kết nối một lần khi khởi tạo; raise nếu fail.
    - GraphRetriever dùng try/except để fallback về NetworkX.
    """

    def __init__(
        self,
        uri: str = NEO4J_URI,
        user: str = NEO4J_USER,
        password: str = NEO4J_PASSWORD,
        database: str = NEO4J_DATABASE,
        connect_timeout: int = 5,      # giây chờ Bolt handshake
    ):
        from neo4j import GraphDatabase, exceptions as neo4j_exc

        self._database = database
        try:
            self._driver = GraphDatabase.driver(
                uri,
                auth=(user, password),
                connection_timeout=connect_timeout,
                max_connection_lifetime=300,
            )
            # Verify connectivity — sẽ raise nếu Neo4j chưa lên
            self._driver.verify_connectivity()
            print(f"[Neo4j] Connected: {uri}")
        except neo4j_exc.ServiceUnavailable as e:
            raise ConnectionError(f"[Neo4j] Unavailable ({uri}): {e}") from e
        except Exception as e:
            raise ConnectionError(f"[Neo4j] Connect error: {e}") from e

    def close(self):
        self._driver.close()

    # ------------------------------------------------------------------
    # SCHEMA SETUP
    # ------------------------------------------------------------------

    def create_constraints(self):
        """Tạo uniqueness constraints cho node_id."""
        constraints = [
            "CREATE CONSTRAINT book_id IF NOT EXISTS FOR (n:Book) REQUIRE n.node_id IS UNIQUE",
            "CREATE CONSTRAINT clothes_id IF NOT EXISTS FOR (n:Clothes) REQUIRE n.node_id IS UNIQUE",
            "CREATE CONSTRAINT author_id IF NOT EXISTS FOR (n:Author) REQUIRE n.node_id IS UNIQUE",
            "CREATE CONSTRAINT brand_id IF NOT EXISTS FOR (n:Brand) REQUIRE n.node_id IS UNIQUE",
            "CREATE CONSTRAINT category_id IF NOT EXISTS FOR (n:Category) REQUIRE n.node_id IS UNIQUE",
            "CREATE CONSTRAINT scenario_id IF NOT EXISTS FOR (n:Scenario) REQUIRE n.node_id IS UNIQUE",
        ]
        with self._driver.session(database=self._database) as session:
            for cql in constraints:
                try:
                    session.run(cql)
                except Exception:
                    pass  # Constraint đã tồn tại → bỏ qua

    # ------------------------------------------------------------------
    # PUSH NETWORKX GRAPH → NEO4J
    # ------------------------------------------------------------------

    def push_graph(self, G: nx.DiGraph, batch_size: int = 100):
        """
        Đẩy toàn bộ NetworkX graph vào Neo4j.
        Dùng MERGE để idempotent — có thể chạy lại nhiều lần.
        """
        self.create_constraints()

        # --- Nodes ---
        node_batch: List[Dict] = []
        for node_id, data in G.nodes(data=True):
            ntype = data.get("node_type", "Unknown")
            props = {k: v for k, v in data.items()
                     if k != "node_type" and isinstance(v, (str, int, float, bool, list))}
            props["node_id"] = node_id
            node_batch.append({"ntype": ntype, "props": props})

            if len(node_batch) >= batch_size:
                self._push_nodes_batch(node_batch)
                node_batch = []
        if node_batch:
            self._push_nodes_batch(node_batch)

        # --- Edges ---
        edge_batch: List[Dict] = []
        for src, dst, data in G.edges(data=True):
            etype = data.get("edge_type", "RELATED")
            edge_batch.append({"src": src, "dst": dst, "etype": etype})

            if len(edge_batch) >= batch_size:
                self._push_edges_batch(edge_batch)
                edge_batch = []
        if edge_batch:
            self._push_edges_batch(edge_batch)

        n_nodes = G.number_of_nodes()
        n_edges = G.number_of_edges()
        print(f"[Neo4j] Pushed: {n_nodes} nodes, {n_edges} edges")

    def _push_nodes_batch(self, batch: List[Dict]):
        """Merge nhiều node cùng lúc."""
        with self._driver.session(database=self._database) as session:
            for item in batch:
                ntype = item["ntype"]
                props = item["props"]
                # Dynamic label không được Cypher hỗ trợ trực tiếp
                # → dùng APOC nếu có, ngược lại merge theo ntype
                cql = (
                    f"MERGE (n:{ntype} {{node_id: $node_id}}) "
                    f"SET n += $props"
                )
                session.run(cql, node_id=props["node_id"], props=props)

    def _push_edges_batch(self, batch: List[Dict]):
        """Merge nhiều edge cùng lúc."""
        with self._driver.session(database=self._database) as session:
            for item in batch:
                src, dst, etype = item["src"], item["dst"], item["etype"]
                cql = (
                    "MATCH (a {node_id: $src}), (b {node_id: $dst}) "
                    f"MERGE (a)-[r:{etype}]->(b)"
                )
                try:
                    session.run(cql, src=src, dst=dst)
                except Exception:
                    pass  # Bỏ qua edge nếu node chưa tồn tại

    # ------------------------------------------------------------------
    # QUERY: Multi-hop traversal
    # ------------------------------------------------------------------

    def query_related(
        self,
        seed_node_ids: List[str],
        hops: int = 2,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Tìm các node liên quan đến seed nodes trong vòng `hops` bước.
        Trả về list of {node_id, node_type, props, hop_distance}.
        """
        if not seed_node_ids:
            return []

        cql = (
            "UNWIND $seeds AS seed_id "
            "MATCH (seed {node_id: seed_id}) "
            f"MATCH path = (seed)-[*1..{hops}]-(related) "
            "WHERE related.node_id IS NOT NULL "
            "WITH related, min(length(path)) AS hop "
            "RETURN related.node_id AS node_id, "
            "       labels(related)[0] AS node_type, "
            "       properties(related) AS props, "
            "       hop "
            "ORDER BY hop ASC "
            f"LIMIT {limit}"
        )

        results = []
        with self._driver.session(database=self._database) as session:
            for record in session.run(cql, seeds=seed_node_ids):
                results.append({
                    "node_id":   record["node_id"],
                    "node_type": record["node_type"],
                    "props":     dict(record["props"]),
                    "hop":       record["hop"],
                })
        return results

    def is_graph_populated(self) -> bool:
        """Kiểm tra xem đã có dữ liệu trong Neo4j chưa."""
        with self._driver.session(database=self._database) as session:
            result = session.run("MATCH (n) RETURN count(n) AS cnt LIMIT 1")
            return result.single()["cnt"] > 0

    # ------------------------------------------------------------------
    # CONTEXT MANAGER
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
