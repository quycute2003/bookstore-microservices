"""
================================================================
  MODULE 0 — GNN Model: HeteroGraphSAGE
================================================================
GraphSAGE cho heterogeneous graph (Book, Clothes, Author, Brand, Category).

Kiến trúc:
  HeteroConv(SAGEConv) × 2 layers
    → ReLU + Dropout giữa các layer
    → Per-node-type projection head → embedding_dim
    → encode() trả dict {node_type: Tensor[num_nodes, emb_dim]}

Điểm kỹ thuật:
  - Dùng HeteroConv với SAGEConv cho mỗi edge type (incl. reverse)
  - Tự động detect feature dim & edge types từ HeteroData
  - Projection head riêng cho mỗi node type
  - encode_node() lấy embedding cho 1 node cụ thể (dùng khi inference)
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Tuple, Optional

from torch_geometric.data import HeteroData
from torch_geometric.nn import SAGEConv, HeteroConv


# =============================================
# UTILITY
# =============================================

def get_edge_types_from_data(data: HeteroData) -> List[Tuple[str, str, str]]:
    """Trích xuất tất cả edge types từ HeteroData object."""
    return list(data.edge_types)


def get_node_feature_dims(data: HeteroData) -> Dict[str, int]:
    """Trả về {node_type: feature_dim} từ HeteroData."""
    dims = {}
    for ntype in data.node_types:
        if hasattr(data[ntype], 'x') and data[ntype].x is not None:
            dims[ntype] = data[ntype].x.shape[1]
    return dims


# =============================================
# HETEROGRAPHSAGE MODEL
# =============================================

class HeteroGraphSAGE(nn.Module):
    """
    GraphSAGE cho heterogeneous Knowledge Graph.

    ┌──────────────────────────────────────────────────┐
    │  Input: HeteroData với node features (x)         │
    │  Layer 1: HeteroConv(SAGEConv) → hidden_dim      │
    │  ReLU + Dropout                                   │
    │  Layer 2: HeteroConv(SAGEConv) → hidden_dim      │
    │  ReLU + Dropout                                   │
    │  Projection: Linear(hidden → embedding_dim)       │
    │  Output: dict {node_type: Tensor}                 │
    └──────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        node_types: List[str],
        edge_types: List[Tuple[str, str, str]],
        in_channels_dict: Dict[str, int],
        hidden_channels: int = 128,
        embedding_dim: int = 64,
        num_layers: int = 2,
        dropout: float = 0.3,
    ):
        """
        Parameters
        ----------
        node_types      : Danh sách node types (e.g. ["Book", "Author", ...])
        edge_types      : Danh sách (src, edge_name, dst) tuples
        in_channels_dict: {node_type: feature_dim} — dim của sentence-transformer features
        hidden_channels : Kích thước hidden layers
        embedding_dim   : Kích thước embedding output
        num_layers      : Số lượng GNN layers
        dropout         : Dropout rate
        """
        super().__init__()

        self.node_types = node_types
        self.edge_types = edge_types
        self.hidden_channels = hidden_channels
        self.embedding_dim = embedding_dim
        self.num_layers = num_layers
        self.dropout = dropout

        # --- Input projection: khác nhau vì feature dim có thể khác nhau ---
        self.input_projections = nn.ModuleDict()
        for ntype in node_types:
            in_dim = in_channels_dict.get(ntype, hidden_channels)
            self.input_projections[ntype] = nn.Linear(in_dim, hidden_channels)

        # --- GNN Layers: HeteroConv wrapping SAGEConv ---
        self.convs = nn.ModuleList()
        for i in range(num_layers):
            conv_dict = {}
            for e_type in edge_types:
                # Key cho HeteroConv là tuple (src, edge, dst)
                conv_dict[e_type] = SAGEConv(
                    hidden_channels, hidden_channels
                )
            self.convs.append(HeteroConv(conv_dict, aggr="mean"))

        # --- Layer Norms (per layer, per node type) ---
        self.norms = nn.ModuleList()
        for _ in range(num_layers):
            norm_dict = nn.ModuleDict()
            for ntype in node_types:
                norm_dict[ntype] = nn.LayerNorm(hidden_channels)
            self.norms.append(norm_dict)

        # --- Projection heads: mỗi node type có projection riêng ---
        self.projection_heads = nn.ModuleDict()
        for ntype in node_types:
            self.projection_heads[ntype] = nn.Sequential(
                nn.Linear(hidden_channels, embedding_dim),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(embedding_dim, embedding_dim),
            )

    def forward(self, x_dict: Dict[str, torch.Tensor],
                edge_index_dict: Dict[Tuple, torch.Tensor]) -> Dict[str, torch.Tensor]:
        """
        Forward pass — trả về hidden representations (chưa project).

        Parameters
        ----------
        x_dict          : {node_type: Tensor[num_nodes, in_dim]}
        edge_index_dict : {(src, edge, dst): Tensor[2, num_edges]}

        Returns
        -------
        h_dict : {node_type: Tensor[num_nodes, hidden_channels]}
        """
        # Input projection
        h_dict = {}
        for ntype in self.node_types:
            if ntype in x_dict:
                h_dict[ntype] = F.relu(self.input_projections[ntype](x_dict[ntype]))

        # Message passing layers
        for i, conv in enumerate(self.convs):
            h_new = conv(h_dict, edge_index_dict)

            # Apply norm + residual + activation
            for ntype in h_new:
                h_residual = h_dict.get(ntype)
                h_new[ntype] = self.norms[i][ntype](h_new[ntype])
                if h_residual is not None and h_residual.shape == h_new[ntype].shape:
                    h_new[ntype] = h_new[ntype] + h_residual  # Residual connection
                h_new[ntype] = F.relu(h_new[ntype])
                h_new[ntype] = F.dropout(
                    h_new[ntype], p=self.dropout, training=self.training
                )

            h_dict = h_new

        return h_dict

    def encode(self, data: HeteroData) -> Dict[str, torch.Tensor]:
        """
        Encode toàn bộ graph → embeddings cho tất cả node types.

        Returns
        -------
        emb_dict : {node_type: Tensor[num_nodes, embedding_dim]}
        """
        x_dict = {ntype: data[ntype].x for ntype in data.node_types
                   if hasattr(data[ntype], 'x') and data[ntype].x is not None}
        edge_index_dict = {etype: data[etype].edge_index for etype in data.edge_types
                           if hasattr(data[etype], 'edge_index')}

        h_dict = self.forward(x_dict, edge_index_dict)

        # Apply projection heads
        emb_dict = {}
        for ntype, h in h_dict.items():
            if ntype in self.projection_heads:
                emb_dict[ntype] = self.projection_heads[ntype](h)

        return emb_dict

    def encode_node(
        self, data: HeteroData, node_type: str, node_idx: int
    ) -> torch.Tensor:
        """
        Lấy embedding cho 1 node cụ thể.

        Parameters
        ----------
        data      : HeteroData (full graph)
        node_type : Loại node (e.g. "Book")
        node_idx  : Integer index trong data[node_type].x

        Returns
        -------
        Tensor shape (embedding_dim,)
        """
        emb_dict = self.encode(data)
        if node_type not in emb_dict:
            raise ValueError(f"Node type '{node_type}' not found in embeddings")
        if node_idx >= emb_dict[node_type].shape[0]:
            raise IndexError(
                f"node_idx={node_idx} out of range for "
                f"{node_type} (size={emb_dict[node_type].shape[0]})"
            )
        return emb_dict[node_type][node_idx]

    @classmethod
    def from_hetero_data(
        cls,
        data: HeteroData,
        hidden_channels: int = 128,
        embedding_dim: int = 64,
        num_layers: int = 2,
        dropout: float = 0.3,
    ) -> "HeteroGraphSAGE":
        """
        Factory method: tự động detect cấu trúc từ HeteroData.
        """
        node_types = list(data.node_types)
        edge_types = get_edge_types_from_data(data)
        in_channels_dict = get_node_feature_dims(data)

        # Chỉ giữ edge types mà cả src và dst đều có features
        valid_edge_types = []
        for src, etype, dst in edge_types:
            if src in in_channels_dict and dst in in_channels_dict:
                valid_edge_types.append((src, etype, dst))

        # Chỉ giữ node types có features
        valid_node_types = [nt for nt in node_types if nt in in_channels_dict]

        return cls(
            node_types=valid_node_types,
            edge_types=valid_edge_types,
            in_channels_dict=in_channels_dict,
            hidden_channels=hidden_channels,
            embedding_dim=embedding_dim,
            num_layers=num_layers,
            dropout=dropout,
        )


# =============================================
# STANDALONE TEST
# =============================================
if __name__ == "__main__":
    print("=" * 60)
    print("  GNN Model — Structure Test")
    print("=" * 60)

    # Tạo dummy HeteroData
    data = HeteroData()
    data["Book"].x = torch.randn(10, 384)      # 10 books, 384-dim features
    data["Author"].x = torch.randn(5, 384)      # 5 authors
    data["Category"].x = torch.randn(3, 384)    # 3 categories

    data["Book", "WRITTEN_BY", "Author"].edge_index = torch.tensor(
        [[0, 1, 2, 3], [0, 1, 2, 3]], dtype=torch.long
    )
    data["Author", "rev_WRITTEN_BY", "Book"].edge_index = torch.tensor(
        [[0, 1, 2, 3], [0, 1, 2, 3]], dtype=torch.long
    )
    data["Book", "IN_CATEGORY", "Category"].edge_index = torch.tensor(
        [[0, 1, 2, 3, 4], [0, 0, 1, 1, 2]], dtype=torch.long
    )
    data["Category", "rev_IN_CATEGORY", "Book"].edge_index = torch.tensor(
        [[0, 0, 1, 1, 2], [0, 1, 2, 3, 4]], dtype=torch.long
    )

    model = HeteroGraphSAGE.from_hetero_data(data)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"\n🧠 Model parameters: {total_params:,}")
    print(f"   Node types: {model.node_types}")
    print(f"   Edge types: {model.edge_types}")
    print(f"   Hidden dim: {model.hidden_channels}")
    print(f"   Embedding dim: {model.embedding_dim}")

    # Forward pass
    model.eval()
    with torch.no_grad():
        emb_dict = model.encode(data)
    for ntype, emb in emb_dict.items():
        print(f"   {ntype}: {emb.shape}")

    # Single node
    node_emb = model.encode_node(data, "Book", 0)
    print(f"\n   Book[0] embedding: {node_emb.shape}")
    print("   ✅ Model structure OK!")
