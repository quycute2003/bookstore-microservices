"""
================================================================
  MODULE 0 — GNN Dataset Builder
================================================================
Chuyển NetworkX DiGraph thành PyG HeteroData.

Điểm kỹ thuật quan trọng:
  - String node IDs (book:1, brand:Louis Vuitton) phải được map
    sang integer indices trước khi tạo edge_index tensor.
  - node_to_idx dict PHẢI được serialize cùng model weights để
    inference sau này dùng đúng mapping (không rebuild lại).
  - Thêm reverse edges để SAGEConv aggregate cả 2 chiều.
"""

from __future__ import annotations

import os
import pickle
from typing import Optional

import numpy as np
import torch
from torch_geometric.data import HeteroData

from .graph_builder import KnowledgeGraphBuilder
from .graph_schema import NodeType, EdgeType

MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "models"
)
DATASET_CACHE = os.path.join(MODELS_DIR, "gnn_dataset.pkl")

# Node types đưa vào GNN (bỏ Scenario vì quá sparse)
ACTIVE_NODE_TYPES = [
    NodeType.BOOK,
    NodeType.CLOTHES,
    NodeType.AUTHOR,
    NodeType.BRAND,
    NodeType.CATEGORY,
]

# (src_type, edge_type, dst_type) — chỉ các edge có semantic rõ ràng
EDGE_TRIPLETS = [
    (NodeType.BOOK,    EdgeType.WRITTEN_BY,  NodeType.AUTHOR),
    (NodeType.BOOK,    EdgeType.IN_CATEGORY, NodeType.CATEGORY),
    (NodeType.CLOTHES, EdgeType.MADE_BY,     NodeType.BRAND),
    (NodeType.CLOTHES, EdgeType.IN_CATEGORY, NodeType.CATEGORY),
    (NodeType.BOOK,    EdgeType.SIMILAR,     NodeType.BOOK),
    (NodeType.CLOTHES, EdgeType.SIMILAR,     NodeType.CLOTHES),
]


# =============================================
# NODE TEXT EXTRACTION (dùng để embed features)
# =============================================

def _node_text(node_id: str, data: dict) -> str:
    """Chuyển node thành string để sentence-transformer embed."""
    ntype = data.get("node_type", "")
    if ntype == NodeType.BOOK:
        parts = [
            data.get("title", ""),
            data.get("author", ""),
            data.get("category", ""),
            data.get("description", "")[:200],
        ]
    elif ntype == NodeType.CLOTHES:
        parts = [
            data.get("name", ""),
            data.get("brand", ""),
            data.get("color", ""),
            data.get("category", ""),
            data.get("description", "")[:200],
        ]
    elif ntype == NodeType.AUTHOR:
        parts = [data.get("name", ""), "tác giả"]
    elif ntype == NodeType.BRAND:
        aliases = data.get("aliases", [])
        if isinstance(aliases, str):
            aliases = []
        parts = [data.get("name", "")] + aliases + ["thương hiệu thời trang"]
    elif ntype == NodeType.CATEGORY:
        parts = [data.get("name", ""), data.get("description", "")]
    else:
        parts = [node_id]
    return " ".join(p for p in parts if p).strip()


# =============================================
# BUILD HETERODATA
# =============================================

def build_hetero_data(
    G=None,
    embed_model=None,
) -> tuple[HeteroData, dict[str, dict[str, int]], dict[str, dict[int, str]]]:
    """
    Xây dựng PyG HeteroData từ NetworkX graph.

    Returns
    -------
    data       : HeteroData — sẵn sàng đưa vào GNN
    node_to_idx: {node_type: {string_id -> int_idx}}
    idx_to_node: {node_type: {int_idx -> string_id}}
    """
    if G is None:
        G = KnowledgeGraphBuilder.get_or_build()

    # ---- Step 1: Build integer index mapping ----
    node_to_idx: dict[str, dict[str, int]] = {nt: {} for nt in ACTIVE_NODE_TYPES}
    idx_to_node: dict[str, dict[int, str]] = {nt: {} for nt in ACTIVE_NODE_TYPES}

    for node_id, data in G.nodes(data=True):
        ntype = data.get("node_type")
        if ntype not in node_to_idx:
            continue
        idx = len(node_to_idx[ntype])
        node_to_idx[ntype][node_id] = idx
        idx_to_node[ntype][idx]  = node_id

    print("[GNN] Node counts:", {nt: len(m) for nt, m in node_to_idx.items()})

    # ---- Step 2: Compute initial node features (sentence transformer) ----
    if embed_model is None:
        from sentence_transformers import SentenceTransformer
        embed_model_name = os.getenv(
            "EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        print(f"[GNN] Loading embed model: {embed_model_name}")
        embed_model = SentenceTransformer(embed_model_name)

    data_obj = HeteroData()

    for ntype in ACTIVE_NODE_TYPES:
        mapping = idx_to_node[ntype]
        if not mapping:
            continue
        # Lấy nodes theo đúng thứ tự idx tăng dần
        ordered_ids = [mapping[i] for i in range(len(mapping))]
        texts = [_node_text(nid, G.nodes[nid]) for nid in ordered_ids]
        feats = embed_model.encode(texts, batch_size=32, show_progress_bar=False)
        data_obj[ntype].x = torch.tensor(feats, dtype=torch.float)
        # Lưu string IDs để debug/lookup
        data_obj[ntype].node_ids = ordered_ids

    feat_dim = next(iter(data_obj.node_types))
    print(f"[GNN] Feature dim: {data_obj[feat_dim].x.shape[1]}")

    # ---- Step 3: Build edge_index tensors ----
    for src_type, etype, dst_type in EDGE_TRIPLETS:
        srcs, dsts = [], []
        for src, dst, edata in G.edges(data=True):
            if edata.get("edge_type") != etype:
                continue
            sn = G.nodes[src].get("node_type")
            dn = G.nodes[dst].get("node_type")
            if sn != src_type or dn != dst_type:
                continue
            si = node_to_idx.get(src_type, {}).get(src)
            di = node_to_idx.get(dst_type, {}).get(dst)
            if si is not None and di is not None:
                srcs.append(si)
                dsts.append(di)

        if not srcs:
            continue

        edge_key = (src_type, etype, dst_type)
        data_obj[edge_key].edge_index = torch.tensor(
            [srcs, dsts], dtype=torch.long
        )

        # Reverse edge — quan trọng để SAGEConv aggregate cả 2 chiều
        rev_key = (dst_type, f"rev_{etype}", src_type)
        data_obj[rev_key].edge_index = torch.tensor(
            [dsts, srcs], dtype=torch.long
        )

    print(f"[GNN] Edge types (incl. reverse): {data_obj.edge_types}")
    return data_obj, node_to_idx, idx_to_node


# =============================================
# CACHE HELPERS
# =============================================

def save_dataset(data_obj, node_to_idx, idx_to_node, path=DATASET_CACHE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(
            {"data": data_obj, "node_to_idx": node_to_idx, "idx_to_node": idx_to_node},
            f,
        )
    print(f"[GNN] Dataset saved → {path}")


def load_dataset(path=DATASET_CACHE):
    with open(path, "rb") as f:
        bundle = pickle.load(f)
    return bundle["data"], bundle["node_to_idx"], bundle["idx_to_node"]


def get_or_build_dataset(G=None, embed_model=None):
    """Load từ cache nếu có; ngược lại build mới."""
    if os.path.exists(DATASET_CACHE):
        print("[GNN] Loading cached dataset...")
        return load_dataset()
    data_obj, n2i, i2n = build_hetero_data(G, embed_model)
    save_dataset(data_obj, n2i, i2n)
    return data_obj, n2i, i2n
