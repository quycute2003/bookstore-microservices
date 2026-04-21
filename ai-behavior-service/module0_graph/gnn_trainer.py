"""
================================================================
  MODULE 0 — GNN Trainer: Self-supervised Link Prediction
================================================================
Training loop cho HeteroGraphSAGE trên Knowledge Graph.

Phương pháp: Self-supervised Link Prediction
  - Positive edges: sample từ existing edges trong graph
  - Negative edges: random node pairs không có edge
  - Loss: BCEWithLogitsLoss trên dot-product similarity
  - Không cần labels → phù hợp cho product knowledge graph

Serialize:
  - gnn_weights.pth        — model state_dict
  - gnn_node_mapping.pkl   — {node_to_idx, idx_to_node}
  - gnn_metadata.json      — hyperparams, edge types, feature dims

Chạy standalone:
  cd ai-behavior-service
  python -m module0_graph.gnn_trainer
"""

from __future__ import annotations

import os
import json
import time
import pickle
import random
from typing import Dict, List, Tuple, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch_geometric.data import HeteroData

from .gnn_model import HeteroGraphSAGE, get_edge_types_from_data, get_node_feature_dims
from .gnn_dataset import (
    build_hetero_data, get_or_build_dataset,
    save_dataset, load_dataset,
    EDGE_TRIPLETS, ACTIVE_NODE_TYPES,
)

MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "models"
)

# Output files
GNN_WEIGHTS_PATH  = os.path.join(MODELS_DIR, "gnn_weights.pth")
GNN_MAPPING_PATH  = os.path.join(MODELS_DIR, "gnn_node_mapping.pkl")
GNN_METADATA_PATH = os.path.join(MODELS_DIR, "gnn_metadata.json")


# =============================================
# EDGE SAMPLING (cho link prediction)
# =============================================

def _sample_negative_edges(
    data: HeteroData,
    edge_type: Tuple[str, str, str],
    num_neg: int,
) -> torch.Tensor:
    """
    Sample negative edges cho 1 edge type.
    Random (src, dst) pairs mà KHÔNG tồn tại trong graph.

    Returns: Tensor shape (2, num_neg)
    """
    src_type, _, dst_type = edge_type
    num_src = data[src_type].x.shape[0]
    num_dst = data[dst_type].x.shape[0]

    if num_src == 0 or num_dst == 0:
        return torch.zeros(2, 0, dtype=torch.long)

    # Existing edges → set để check trùng
    if hasattr(data[edge_type], 'edge_index'):
        existing = set()
        ei = data[edge_type].edge_index
        for i in range(ei.shape[1]):
            existing.add((ei[0, i].item(), ei[1, i].item()))
    else:
        existing = set()

    neg_srcs, neg_dsts = [], []
    attempts = 0
    max_attempts = num_neg * 10  # Tránh infinite loop

    while len(neg_srcs) < num_neg and attempts < max_attempts:
        s = random.randint(0, num_src - 1)
        d = random.randint(0, num_dst - 1)
        if (s, d) not in existing:
            neg_srcs.append(s)
            neg_dsts.append(d)
            existing.add((s, d))  # Không repeat
        attempts += 1

    return torch.tensor([neg_srcs, neg_dsts], dtype=torch.long)


def _prepare_link_prediction_batch(
    data: HeteroData,
    neg_ratio: float = 1.0,
) -> List[Dict]:
    """
    Chuẩn bị positive + negative edges cho tất cả edge types.

    Returns list of {
        edge_type, pos_edge_index, neg_edge_index,
        src_type, dst_type
    }
    """
    batches = []

    for etype_tuple in data.edge_types:
        if not hasattr(data[etype_tuple], 'edge_index'):
            continue

        pos_ei = data[etype_tuple].edge_index
        num_pos = pos_ei.shape[1]
        if num_pos == 0:
            continue

        # Chỉ dùng edge types gốc (không dùng reverse để tránh data leak)
        src_type, ename, dst_type = etype_tuple
        if ename.startswith("rev_"):
            continue

        num_neg = max(1, int(num_pos * neg_ratio))
        neg_ei = _sample_negative_edges(data, etype_tuple, num_neg)

        batches.append({
            "edge_type": etype_tuple,
            "pos_edge_index": pos_ei,
            "neg_edge_index": neg_ei,
            "src_type": src_type,
            "dst_type": dst_type,
        })

    return batches


# =============================================
# TRAINING LOOP
# =============================================

class GNNTrainer:
    """
    Self-supervised trainer cho HeteroGraphSAGE.

    Sử dụng link prediction loss:
      - Positive: dot(emb_src, emb_dst) cho existing edges → label 1
      - Negative: dot(emb_src, emb_dst) cho random pairs → label 0
      - Loss: BCEWithLogitsLoss
    """

    def __init__(
        self,
        hidden_channels: int = 128,
        embedding_dim: int = 64,
        num_layers: int = 2,
        dropout: float = 0.3,
        lr: float = 0.005,
        weight_decay: float = 1e-4,
        neg_ratio: float = 1.0,
    ):
        self.hidden_channels = hidden_channels
        self.embedding_dim = embedding_dim
        self.num_layers = num_layers
        self.dropout = dropout
        self.lr = lr
        self.weight_decay = weight_decay
        self.neg_ratio = neg_ratio

        self.model: Optional[HeteroGraphSAGE] = None
        self.optimizer = None
        self.criterion = nn.BCEWithLogitsLoss()

    def _init_model(self, data: HeteroData):
        """Khởi tạo model từ HeteroData structure."""
        self.model = HeteroGraphSAGE.from_hetero_data(
            data,
            hidden_channels=self.hidden_channels,
            embedding_dim=self.embedding_dim,
            num_layers=self.num_layers,
            dropout=self.dropout,
        )
        self.optimizer = optim.Adam(
            self.model.parameters(),
            lr=self.lr,
            weight_decay=self.weight_decay,
        )

    def _link_prediction_loss(
        self,
        emb_dict: Dict[str, torch.Tensor],
        batch: Dict,
    ) -> torch.Tensor:
        """
        Tính link prediction loss cho 1 edge type.

        Dot product giữa src & dst embeddings:
          positive edges → target 1
          negative edges → target 0
        """
        src_type = batch["src_type"]
        dst_type = batch["dst_type"]

        src_emb = emb_dict.get(src_type)
        dst_emb = emb_dict.get(dst_type)

        if src_emb is None or dst_emb is None:
            return torch.tensor(0.0)

        # Positive edges
        pos_ei = batch["pos_edge_index"]
        pos_src = src_emb[pos_ei[0]]  # (num_pos, emb_dim)
        pos_dst = dst_emb[pos_ei[1]]  # (num_pos, emb_dim)
        pos_score = (pos_src * pos_dst).sum(dim=1)  # dot product
        pos_label = torch.ones_like(pos_score)

        # Negative edges
        neg_ei = batch["neg_edge_index"]
        if neg_ei.shape[1] > 0:
            # Clamp indices to valid range
            neg_src_idx = neg_ei[0].clamp(0, src_emb.shape[0] - 1)
            neg_dst_idx = neg_ei[1].clamp(0, dst_emb.shape[0] - 1)
            neg_src = src_emb[neg_src_idx]
            neg_dst = dst_emb[neg_dst_idx]
            neg_score = (neg_src * neg_dst).sum(dim=1)
            neg_label = torch.zeros_like(neg_score)

            # Concat
            all_scores = torch.cat([pos_score, neg_score])
            all_labels = torch.cat([pos_label, neg_label])
        else:
            all_scores = pos_score
            all_labels = pos_label

        return self.criterion(all_scores, all_labels)

    def train(
        self,
        data: HeteroData,
        epochs: int = 100,
        log_every: int = 10,
    ) -> HeteroGraphSAGE:
        """
        Training loop chính.

        Parameters
        ----------
        data      : HeteroData từ build_hetero_data()
        epochs    : Số epochs
        log_every : In log mỗi N epochs

        Returns
        -------
        Trained HeteroGraphSAGE model
        """
        if self.model is None:
            self._init_model(data)

        print(f"\n🚀 GNN Training ({epochs} epochs)")
        print(f"   Hidden: {self.hidden_channels} | Embedding: {self.embedding_dim}")
        print(f"   Layers: {self.num_layers} | Dropout: {self.dropout}")
        print(f"   LR: {self.lr} | Neg ratio: {self.neg_ratio}")
        total_params = sum(p.numel() for p in self.model.parameters())
        print(f"   Parameters: {total_params:,}")
        print("-" * 60)

        start_time = time.time()

        for epoch in range(epochs):
            self.model.train()
            self.optimizer.zero_grad()

            # Forward pass → embeddings
            emb_dict = self.model.encode(data)

            # Link prediction loss across all edge types
            batches = _prepare_link_prediction_batch(data, self.neg_ratio)
            total_loss = torch.tensor(0.0)
            num_batches = 0

            for batch in batches:
                loss = self._link_prediction_loss(emb_dict, batch)
                total_loss = total_loss + loss
                num_batches += 1

            if num_batches > 0:
                total_loss = total_loss / num_batches

            total_loss.backward()
            self.optimizer.step()

            if (epoch + 1) % log_every == 0 or epoch == 0:
                elapsed = time.time() - start_time
                print(
                    f"  Epoch {epoch+1:4d}/{epochs} | "
                    f"Loss={total_loss.item():.6f} | "
                    f"Time={elapsed:.1f}s"
                )

        elapsed_total = time.time() - start_time
        print("-" * 60)
        print(f"✅ GNN Training hoàn tất! ({elapsed_total:.1f}s)")

        return self.model

    # ------------------------------------------------------------------
    # SERIALIZE / DESERIALIZE
    # ------------------------------------------------------------------

    def save(
        self,
        node_to_idx: Dict[str, Dict[str, int]],
        idx_to_node: Dict[str, Dict[int, str]],
        data: HeteroData,
        models_dir: str = MODELS_DIR,
    ):
        """
        Serialize model + mapping + metadata.

        QUAN TRỌNG: node_to_idx PHẢI được serialize cùng weights
        để inference dùng đúng mapping gốc (không rebuild).
        """
        os.makedirs(models_dir, exist_ok=True)

        # 1. Model weights
        weights_path = os.path.join(models_dir, "gnn_weights.pth")
        torch.save(self.model.state_dict(), weights_path)
        print(f"  💾 Weights → {weights_path}")

        # 2. Node mapping (pickle vì keys phức tạp)
        mapping_path = os.path.join(models_dir, "gnn_node_mapping.pkl")
        with open(mapping_path, "wb") as f:
            pickle.dump({
                "node_to_idx": node_to_idx,
                "idx_to_node": idx_to_node,
            }, f)
        print(f"  💾 Node mapping → {mapping_path}")

        # 3. Metadata (JSON human-readable)
        metadata = {
            "hidden_channels": self.hidden_channels,
            "embedding_dim": self.embedding_dim,
            "num_layers": self.num_layers,
            "dropout": self.dropout,
            "node_types": self.model.node_types,
            "edge_types": [list(et) for et in self.model.edge_types],
            "in_channels_dict": get_node_feature_dims(data),
            "node_counts": {nt: len(m) for nt, m in node_to_idx.items() if m},
            "total_parameters": sum(p.numel() for p in self.model.parameters()),
            "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        metadata_path = os.path.join(models_dir, "gnn_metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"  💾 Metadata → {metadata_path}")

        print(f"  ✅ GNN model saved ({metadata['total_parameters']:,} params)")


def load_gnn_model(
    models_dir: str = MODELS_DIR,
    device: str = "cpu",
) -> Tuple[HeteroGraphSAGE, Dict, Dict, Dict]:
    """
    Load GNN model + mapping đầy đủ.

    Returns
    -------
    model       : HeteroGraphSAGE (eval mode)
    node_to_idx : {node_type: {string_id → int_idx}}
    idx_to_node : {node_type: {int_idx → string_id}}
    metadata    : dict with hyperparams
    """
    # 1. Metadata
    metadata_path = os.path.join(models_dir, "gnn_metadata.json")
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # 2. Node mapping
    mapping_path = os.path.join(models_dir, "gnn_node_mapping.pkl")
    with open(mapping_path, "rb") as f:
        mapping_bundle = pickle.load(f)
    node_to_idx = mapping_bundle["node_to_idx"]
    idx_to_node = mapping_bundle["idx_to_node"]

    # 3. Reconstruct model architecture
    node_types = metadata["node_types"]
    edge_types = [tuple(et) for et in metadata["edge_types"]]
    in_channels_dict = metadata["in_channels_dict"]

    model = HeteroGraphSAGE(
        node_types=node_types,
        edge_types=edge_types,
        in_channels_dict=in_channels_dict,
        hidden_channels=metadata["hidden_channels"],
        embedding_dim=metadata["embedding_dim"],
        num_layers=metadata["num_layers"],
        dropout=metadata["dropout"],
    )

    # 4. Load weights
    weights_path = os.path.join(models_dir, "gnn_weights.pth")
    state_dict = torch.load(weights_path, map_location=device, weights_only=True)
    model.load_state_dict(state_dict)
    model.eval()

    print(f"[GNN] Model loaded: {metadata['total_parameters']:,} params")
    print(f"[GNN] Node types: {node_types}")
    print(f"[GNN] Trained at: {metadata.get('trained_at', 'unknown')}")

    return model, node_to_idx, idx_to_node, metadata


def is_gnn_trained(models_dir: str = MODELS_DIR) -> bool:
    """Kiểm tra xem GNN model đã được train và lưu chưa."""
    return all(
        os.path.exists(os.path.join(models_dir, f))
        for f in ["gnn_weights.pth", "gnn_node_mapping.pkl", "gnn_metadata.json"]
    )


# =============================================
# FULL PIPELINE: Build dataset → Train → Save
# =============================================

def train_and_save_gnn(
    epochs: int = 100,
    hidden_channels: int = 128,
    embedding_dim: int = 64,
    log_every: int = 10,
) -> Tuple[HeteroGraphSAGE, Dict, Dict]:
    """
    Pipeline đầy đủ: build dataset → train GNN → serialize.

    Returns: (model, node_to_idx, idx_to_node)
    """
    print("=" * 60)
    print("  GNN GraphSAGE — Full Training Pipeline")
    print("=" * 60)

    # Step 1: Build HeteroData
    print("\n📦 Step 1: Building HeteroData from Knowledge Graph...")
    data, node_to_idx, idx_to_node = get_or_build_dataset()

    print(f"   Node types: {list(data.node_types)}")
    for nt in data.node_types:
        if hasattr(data[nt], 'x'):
            print(f"   {nt}: {data[nt].x.shape}")
    print(f"   Edge types: {len(data.edge_types)}")

    # Step 2: Train
    print("\n🏋️ Step 2: Training GNN...")
    trainer = GNNTrainer(
        hidden_channels=hidden_channels,
        embedding_dim=embedding_dim,
    )
    model = trainer.train(data, epochs=epochs, log_every=log_every)

    # Step 3: Save
    print("\n💾 Step 3: Serializing model + mapping...")
    trainer.save(node_to_idx, idx_to_node, data)

    # Step 4: Verify roundtrip
    print("\n🔍 Step 4: Verifying serialize/deserialize...")
    model_loaded, n2i_loaded, i2n_loaded, meta = load_gnn_model()

    # Compare embeddings
    model.eval()
    model_loaded.eval()
    with torch.no_grad():
        emb_original = model.encode(data)
        emb_loaded = model_loaded.encode(data)

    for ntype in emb_original:
        if ntype in emb_loaded:
            diff = (emb_original[ntype] - emb_loaded[ntype]).abs().max().item()
            print(f"   {ntype}: max diff = {diff:.8f} {'✅' if diff < 1e-5 else '❌'}")

    # Verify mapping
    assert node_to_idx == n2i_loaded, "node_to_idx mismatch!"
    print("   Mapping roundtrip: ✅")

    print("\n" + "=" * 60)
    print("  ✅ GNN Pipeline Complete!")
    print("=" * 60)

    return model, node_to_idx, idx_to_node


# =============================================
# STANDALONE RUN
# =============================================
if __name__ == "__main__":
    train_and_save_gnn(epochs=80, log_every=10)
