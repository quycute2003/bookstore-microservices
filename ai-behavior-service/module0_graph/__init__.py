"""
================================================================
  MODULE 0 — Graph Knowledge Base
================================================================
Xây dựng Knowledge Graph từ sản phẩm, danh mục, tác giả, thương hiệu
và kịch bản hành vi. Hỗ trợ truy vấn đa bước (multi-hop) để
cung cấp ngữ cảnh phong phú hơn cho RAG pipeline.

Cấu trúc graph:
  Book ──WRITTEN_BY──> Author
  Book ──IN_CATEGORY──> Category
  Clothes ──MADE_BY──> Brand
  Clothes ──IN_CATEGORY──> Category
  Category ──SUITS──> Scenario
  Author ──SAME_FIELD──> Author  (cùng thể loại)
  Brand ──ALIAS──> Brand         (LV <-> Louis Vuitton)

GNN (Phase 2):
  HeteroGraphSAGE — GraphSAGE trên heterogeneous graph
  GNNTrainer      — Self-supervised link prediction training
  load_gnn_model  — Load trained model + node mapping

Cold Start (Phase 3):
  ColdStartRouter — Route GNN / LSTM / mean fallback cho mỗi user
"""
from .graph_builder import KnowledgeGraphBuilder
from .graph_retriever import GraphRetriever

__all__ = ["KnowledgeGraphBuilder", "GraphRetriever"]

# --- Neo4j (Phase 1) ---
try:
    from .neo4j_connector import Neo4jConnector
    __all__.append("Neo4jConnector")
except ImportError:
    # neo4j driver chưa install → bỏ qua, vẫn dùng NetworkX
    pass

# --- GNN GraphSAGE (Phase 2) ---
try:
    from .gnn_model import HeteroGraphSAGE
    from .gnn_trainer import GNNTrainer, load_gnn_model, is_gnn_trained
    __all__.extend(["HeteroGraphSAGE", "GNNTrainer", "load_gnn_model", "is_gnn_trained"])
except ImportError:
    # torch_geometric chưa install → bỏ qua
    pass

# --- Cold Start Router (Phase 3) ---
try:
    from .cold_start import ColdStartRouter
    __all__.append("ColdStartRouter")
except ImportError:
    pass
