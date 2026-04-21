"""
================================================================
  MODULE 0 — Cold Start Router
================================================================
Quyết định dùng GNN hay LSTM embedding cho mỗi user.

Logic:
  - User đã có behavior profile (từ /analyze-behavior) → "warm user"
    → GNN embedding có thể enrich bằng graph context
  - User mới chưa có profile → "cold user"
    → Fallback sang LSTM (Module 1) hoặc mean embedding

Flow:
  1. check has_behavior_profile(user_id)
  2. Nếu CÓ → get GNN product embeddings gần nhất với behavior
  3. Nếu KHÔNG → dùng LSTM embedding (nếu có session data)
                 hoặc mean product embedding (nếu chưa có gì)

Chạy standalone:
  cd ai-behavior-service
  python -m module0_graph.cold_start
"""

from __future__ import annotations

import os
import numpy as np
import torch
from typing import Dict, List, Optional, Tuple

from .graph_schema import NodeType


# =============================================
# COLD START ROUTER
# =============================================

class ColdStartRouter:
    """
    Router chọn GNN hay LSTM embedding cho mỗi user.

    Chiến lược:
    ┌────────────────────────────────────────────────┐
    │  User có behavior profile?                     │
    │    ├─ CÓ → "warm" → GNN embeddings available  │
    │    │        (product recommendations từ graph)  │
    │    └─ KHÔNG → "cold" → Check session data?     │
    │              ├─ CÓ sessions → LSTM embedding    │
    │              └─ KHÔNG → Mean embedding fallback │
    └────────────────────────────────────────────────┘
    """

    def __init__(self):
        # Lazy load GNN model
        self._gnn_model = None
        self._gnn_data = None
        self._node_to_idx = None
        self._idx_to_node = None
        self._gnn_embeddings: Optional[Dict[str, torch.Tensor]] = None

        # Lazy load LSTM model
        self._lstm_model = None
        self._lstm_scaler = None

        # Cache behavior profiles {user_id: profile_dict}
        self._profile_cache: Dict[str, dict] = {}

        # Pre-computed mean embeddings per node type (fallback)
        self._mean_embeddings: Dict[str, np.ndarray] = {}

    # ------------------------------------------------------------------
    # LAZY LOADERS
    # ------------------------------------------------------------------

    def _load_gnn(self) -> bool:
        """Load GNN model nếu đã train. Trả về True nếu thành công."""
        if self._gnn_model is not None:
            return True

        try:
            from .gnn_trainer import load_gnn_model, is_gnn_trained
            from .gnn_dataset import get_or_build_dataset

            if not is_gnn_trained():
                print("[ColdStart] GNN model chưa được train → skip")
                return False

            self._gnn_model, self._node_to_idx, self._idx_to_node, _ = load_gnn_model()

            # Load HeteroData để encode
            self._gnn_data, _, _ = get_or_build_dataset()

            # Pre-compute embeddings cho toàn bộ graph
            self._gnn_model.eval()
            with torch.no_grad():
                self._gnn_embeddings = self._gnn_model.encode(self._gnn_data)

            # Pre-compute mean embeddings
            for ntype, emb_tensor in self._gnn_embeddings.items():
                self._mean_embeddings[ntype] = emb_tensor.mean(dim=0).cpu().numpy()

            print("[ColdStart] GNN loaded, embeddings pre-computed")
            return True

        except Exception as e:
            print(f"[ColdStart] GNN load failed: {e}")
            return False

    def _load_lstm(self) -> bool:
        """Load LSTM model (Module 1). Trả về True nếu thành công."""
        if self._lstm_model is not None:
            return True

        try:
            from module1_behavior.model_behavior import load_model
            model_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "models"
            )
            if not os.path.exists(os.path.join(model_path, "behavior_model.pth")):
                print("[ColdStart] LSTM model chưa có → skip")
                return False

            self._lstm_model, self._lstm_scaler = load_model(model_path)
            print("[ColdStart] LSTM model loaded")
            return True

        except Exception as e:
            print(f"[ColdStart] LSTM load failed: {e}")
            return False

    # ------------------------------------------------------------------
    # PROFILE MANAGEMENT
    # ------------------------------------------------------------------

    def set_behavior_profile(self, user_id: str, profile: dict):
        """Lưu behavior profile sau khi /analyze-behavior trả về."""
        self._profile_cache[user_id] = profile

    def has_behavior_profile(self, user_id: str) -> bool:
        """Kiểm tra user đã có behavior profile chưa."""
        return user_id in self._profile_cache

    # ------------------------------------------------------------------
    # ROUTING LOGIC
    # ------------------------------------------------------------------

    def classify_user(self, user_id: str, session_data: Optional[List[dict]] = None) -> str:
        """
        Phân loại user:
          "warm"      — đã có behavior profile, dùng GNN
          "cold_lstm" — chưa có profile nhưng có session data, dùng LSTM
          "cold_mean" — chưa có gì, dùng mean embedding
        """
        if self.has_behavior_profile(user_id):
            return "warm"
        if session_data and len(session_data) > 0:
            return "cold_lstm"
        return "cold_mean"

    def get_embedding(
        self,
        user_id: str,
        session_data: Optional[List[dict]] = None,
    ) -> Dict:
        """
        Lấy embedding cho user, tự động route GNN vs LSTM.

        Returns
        -------
        {
            "source":     "gnn" | "lstm" | "mean_fallback",
            "embedding":  List[float],
            "user_type":  "warm" | "cold_lstm" | "cold_mean",
            "confidence": float,
        }
        """
        user_type = self.classify_user(user_id, session_data)

        # Case 1: Warm user → dùng behavior embedding từ profile
        if user_type == "warm":
            profile = self._profile_cache[user_id]
            emb = profile.get("embedding", [])

            if emb:
                return {
                    "source": "gnn" if self._load_gnn() else "lstm",
                    "embedding": emb,
                    "user_type": "warm",
                    "behavior_label": profile.get("label", "unknown"),
                    "confidence": profile.get("confidence", 0.0),
                }

        # Case 2: Cold user với session data → dùng LSTM
        if user_type == "cold_lstm" and session_data:
            lstm_result = self._get_lstm_embedding(session_data)
            if lstm_result is not None:
                return {
                    "source": "lstm",
                    "embedding": lstm_result["embedding"],
                    "user_type": "cold_lstm",
                    "behavior_label": lstm_result.get("label", "unknown"),
                    "confidence": lstm_result.get("confidence", 0.0),
                }

        # Case 3: Hoàn toàn cold → mean embedding
        return self._get_mean_embedding()

    def get_product_embedding(self, product_id: str) -> Optional[Dict]:
        """
        Lấy GNN embedding cho 1 product node.

        Parameters
        ----------
        product_id : String ID (e.g. "book:1" hoặc "clothes:3")

        Returns
        -------
        {
            "embedding": List[float],
            "node_type": str,
            "product_id": str,
        } hoặc None nếu không tìm thấy
        """
        if not self._load_gnn():
            return None

        # Detect node type từ prefix
        if product_id.startswith("book:"):
            ntype = NodeType.BOOK
        elif product_id.startswith("clothes:"):
            ntype = NodeType.CLOTHES
        else:
            return None

        # Lookup index
        if ntype not in self._node_to_idx:
            return None
        idx = self._node_to_idx[ntype].get(product_id)
        if idx is None:
            return None

        # Get embedding
        if ntype in self._gnn_embeddings:
            emb = self._gnn_embeddings[ntype][idx].cpu().numpy().tolist()
            return {
                "embedding": emb,
                "node_type": ntype,
                "product_id": product_id,
            }

        return None

    def get_similar_products(
        self,
        product_id: str,
        top_k: int = 5,
    ) -> List[Dict]:
        """
        Tìm sản phẩm tương tự bằng cosine similarity trên GNN embeddings.

        Returns: list of {product_id, node_type, similarity}
        """
        if not self._load_gnn():
            return []

        source_emb = self.get_product_embedding(product_id)
        if source_emb is None:
            return []

        source_vec = torch.tensor(source_emb["embedding"])
        source_ntype = source_emb["node_type"]

        results = []
        # Search trong cùng node type
        if source_ntype in self._gnn_embeddings:
            all_embs = self._gnn_embeddings[source_ntype]  # (N, emb_dim)

            # Cosine similarity
            source_norm = source_vec / (source_vec.norm() + 1e-8)
            all_norms = all_embs / (all_embs.norm(dim=1, keepdim=True) + 1e-8)
            sims = torch.mv(all_norms, source_norm)

            # Top-k (bỏ chính nó)
            source_idx = self._node_to_idx[source_ntype].get(product_id, -1)
            topk_vals, topk_idxs = sims.topk(min(top_k + 1, len(sims)))

            for val, idx in zip(topk_vals, topk_idxs):
                idx_int = idx.item()
                if idx_int == source_idx:
                    continue
                pid = self._idx_to_node.get(source_ntype, {}).get(idx_int)
                if pid:
                    results.append({
                        "product_id": pid,
                        "node_type": source_ntype,
                        "similarity": round(val.item(), 4),
                    })

        return results[:top_k]

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    def _get_lstm_embedding(self, session_data: List[dict]) -> Optional[Dict]:
        """Dùng LSTM (Module 1) để tạo behavior embedding."""
        if not self._load_lstm():
            return None

        try:
            from module1_behavior.model_behavior import predict_behavior
            result = predict_behavior(self._lstm_model, session_data, self._lstm_scaler)
            return result
        except Exception as e:
            print(f"[ColdStart] LSTM predict failed: {e}")
            return None

    def _get_mean_embedding(self) -> Dict:
        """Fallback: trả về mean embedding cross tất cả product types."""
        if self._load_gnn() and self._mean_embeddings:
            # Dùng mean của Book + Clothes embeddings
            product_embs = []
            for ntype in [NodeType.BOOK, NodeType.CLOTHES]:
                if ntype in self._mean_embeddings:
                    product_embs.append(self._mean_embeddings[ntype])

            if product_embs:
                mean_emb = np.mean(product_embs, axis=0).tolist()
                return {
                    "source": "mean_fallback",
                    "embedding": mean_emb,
                    "user_type": "cold_mean",
                    "behavior_label": "unknown",
                    "confidence": 0.0,
                }

        # Nếu GNN cũng không có → zero vector
        return {
            "source": "mean_fallback",
            "embedding": [0.0] * 64,  # default embedding_dim
            "user_type": "cold_mean",
            "behavior_label": "unknown",
            "confidence": 0.0,
        }


# =============================================
# STANDALONE TEST
# =============================================
if __name__ == "__main__":
    print("=" * 60)
    print("  Cold Start Router — Test")
    print("=" * 60)

    router = ColdStartRouter()

    # Test 1: Completely cold user
    print("\n--- Test 1: Cold user (no data) ---")
    result = router.get_embedding("new_user_001")
    print(f"  Source: {result['source']}")
    print(f"  User type: {result['user_type']}")
    print(f"  Embedding dim: {len(result['embedding'])}")

    # Test 2: Cold user with session data
    print("\n--- Test 2: Cold user with sessions ---")
    sessions = [
        {"click_count": 25, "view_count": 8, "purchase_count": 5,
         "time_on_page": 1.2, "cart_add_count": 9, "search_count": 2,
         "session_duration": 8, "avg_price_viewed": 300,
         "category_diversity": 0.5, "return_rate": 0.2}
    ] * 10
    result = router.get_embedding("new_user_002", session_data=sessions)
    print(f"  Source: {result['source']}")
    print(f"  User type: {result['user_type']}")
    print(f"  Behavior: {result.get('behavior_label', 'N/A')}")
    print(f"  Embedding dim: {len(result['embedding'])}")

    # Test 3: Warm user
    print("\n--- Test 3: Warm user (with profile) ---")
    router.set_behavior_profile("warm_user_001", {
        "label": "impulse_buyer",
        "confidence": 0.85,
        "embedding": [0.1] * 128,
    })
    result = router.get_embedding("warm_user_001")
    print(f"  Source: {result['source']}")
    print(f"  User type: {result['user_type']}")
    print(f"  Behavior: {result.get('behavior_label', 'N/A')}")
    print(f"  Confidence: {result.get('confidence', 0):.2%}")

    # Test 4: Product embedding
    print("\n--- Test 4: Product embedding ---")
    prod_emb = router.get_product_embedding("book:1")
    if prod_emb:
        print(f"  Product: {prod_emb['product_id']}")
        print(f"  Node type: {prod_emb['node_type']}")
        print(f"  Embedding dim: {len(prod_emb['embedding'])}")
    else:
        print("  (GNN not trained yet, skipping)")

    # Test 5: Similar products
    print("\n--- Test 5: Similar products ---")
    similar = router.get_similar_products("book:1", top_k=3)
    if similar:
        for s in similar:
            print(f"  {s['product_id']} (sim={s['similarity']:.4f})")
    else:
        print("  (GNN not trained yet, skipping)")

    # Test classification
    print("\n--- User Classification ---")
    for uid, sdata in [
        ("warm_user_001", None),
        ("new_user_002", sessions),
        ("totally_new", None),
    ]:
        utype = router.classify_user(uid, sdata)
        print(f"  {uid:20s} → {utype}")

    print("\n  ✅ Cold Start Router OK!")
