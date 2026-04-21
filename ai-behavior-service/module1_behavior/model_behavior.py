"""
================================================================
  MODULE 1 — Model Behavior: LSTM + Attention phân loại hành vi
================================================================

Kiến trúc:
  Input (10 features x 10 sessions)
    → Linear(10, 64) + BatchNorm + ReLU
    → Bi-LSTM(64, 128) → 256-dim per timestep
    → Multi-Head Attention (4 heads)
    → Global Average Pooling
    → Behavior Embedding (128-dim)
    → Classification Head → 5 classes

Chạy standalone:
  cd ai-behavior-service
  python -m module1_behavior.model_behavior
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import os
import json
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, classification_report
from sklearn.preprocessing import StandardScaler

from module1_behavior.data_pipeline import (
    create_dataloaders, preprocess_single_user,
    BEHAVIOR_LABELS, NUM_FEATURES, NUM_SESSIONS, NUM_CLASSES
)


class BehaviorModel(nn.Module):
    """
    Mạng LSTM + Multi-Head Attention phân loại hành vi khách hàng.

    Layer-by-layer:
    ┌─────────────────────────────────────────────┐
    │ 1. Feature Projection: Linear(10→64) + BN   │
    │ 2. Bi-LSTM: (64→128×2=256) per timestep     │
    │ 3. Multi-Head Attention: 4 heads, 256-dim    │
    │ 4. Global Average Pooling → 256              │
    │ 5. Embedding Head: 256→128                   │
    │ 6. Classifier: 128→5                         │
    └─────────────────────────────────────────────┘
    """

    def __init__(self, input_dim=NUM_FEATURES, hidden_dim=128,
                 embedding_dim=128, num_classes=NUM_CLASSES, num_heads=4, dropout=0.3):
        super().__init__()

        # 1. Chiếu features thô sang không gian ẩn
        self.fc_input = nn.Linear(input_dim, 64)
        self.bn_input = nn.BatchNorm1d(64)
        self.relu = nn.ReLU()
        self.drop_input = nn.Dropout(dropout)

        # 2. Bi-LSTM: học pattern tuần tự giữa các sessions
        self.lstm = nn.LSTM(
            input_size=64, hidden_size=hidden_dim,
            num_layers=2, batch_first=True,
            bidirectional=True, dropout=dropout,
        )

        # 3. Multi-Head Attention: tập trung vào sessions quan trọng
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_dim * 2, num_heads=num_heads,
            dropout=dropout, batch_first=True,
        )
        self.attn_norm = nn.LayerNorm(hidden_dim * 2)

        # 4. Behavior Embedding Head
        self.embedding_head = nn.Sequential(
            nn.Linear(hidden_dim * 2, embedding_dim),
            nn.ReLU(), nn.Dropout(dropout),
        )

        # 5. Classification Head
        self.classifier = nn.Sequential(
            nn.Linear(embedding_dim, 64), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(64, num_classes),
        )

    def forward(self, x, return_embedding=False):
        """
        x: (batch, seq_len, features)
        Returns: logits (batch, num_classes), [embedding (batch, emb_dim)]
        """
        batch_size, seq_len, feat_dim = x.shape

        # 1. Feature Projection (reshape cho BatchNorm1d)
        x_flat = x.reshape(-1, feat_dim)
        x_proj = self.drop_input(self.relu(self.bn_input(self.fc_input(x_flat))))
        x_proj = x_proj.reshape(batch_size, seq_len, -1)

        # 2. Bi-LSTM
        lstm_out, _ = self.lstm(x_proj)

        # 3. Self-Attention + Residual
        attn_out, _ = self.attention(lstm_out, lstm_out, lstm_out)
        attn_out = self.attn_norm(attn_out + lstm_out)

        # 4. Global Average Pooling
        pooled = attn_out.mean(dim=1)

        # 5. Embedding
        embedding = self.embedding_head(pooled)

        # 6. Classification
        logits = self.classifier(embedding)

        if return_embedding:
            return logits, embedding
        return logits

    def get_embedding(self, x):
        """Chỉ trả về behavior embedding vector."""
        _, emb = self.forward(x, return_embedding=True)
        return emb


def train_model(model, train_loader, test_loader, epochs=50, lr=0.001, device='cpu'):
    """Training loop hoàn chỉnh với metrics logging."""
    model = model.to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=15, gamma=0.5)

    print(f"\n🚀 Training ({epochs} epochs, device={device})")
    print("-" * 60)

    for epoch in range(epochs):
        model.train()
        total_loss = 0
        all_preds, all_labels = [], []

        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            logits = model(X_batch)
            loss = criterion(logits, y_batch)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            all_preds.extend(logits.argmax(dim=1).cpu().numpy())
            all_labels.extend(y_batch.cpu().numpy())

        scheduler.step()
        train_loss = total_loss / len(train_loader)
        train_acc = accuracy_score(all_labels, all_preds)

        if (epoch + 1) % 10 == 0 or epoch == 0:
            test_acc, test_f1, _, _ = evaluate_model(model, test_loader, device)
            print(f"  Epoch {epoch+1:3d}/{epochs} | Loss={train_loss:.4f} | "
                  f"Train Acc={train_acc:.4f} | Test Acc={test_acc:.4f} | F1={test_f1:.4f}")

    print("-" * 60)
    print("✅ Training hoàn tất!")
    return model


def evaluate_model(model, test_loader, device='cpu'):
    """Đánh giá: Accuracy, F1, AUC, Classification Report."""
    model.eval()
    all_preds, all_labels, all_probs = [], [], []

    with torch.no_grad():
        for X_batch, y_batch in test_loader:
            logits = model(X_batch.to(device))
            probs = torch.softmax(logits, dim=1)
            all_preds.extend(logits.argmax(dim=1).cpu().numpy())
            all_labels.extend(y_batch.numpy())
            all_probs.extend(probs.cpu().numpy())

    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)
    all_probs = np.array(all_probs)

    acc = accuracy_score(all_labels, all_preds)
    f1 = f1_score(all_labels, all_preds, average='macro')
    try:
        auc = roc_auc_score(all_labels, all_probs, multi_class='ovr', average='macro')
    except Exception:
        auc = 0.0

    report = classification_report(
        all_labels, all_preds,
        target_names=[BEHAVIOR_LABELS[i] for i in range(NUM_CLASSES)],
        zero_division=0
    )
    return acc, f1, auc, report


def save_model(model, scaler, path="models"):
    """Lưu model weights + scaler parameters."""
    os.makedirs(path, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(path, "behavior_model.pth"))

    scaler_params = {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}
    with open(os.path.join(path, "scaler_params.json"), "w") as f:
        json.dump(scaler_params, f)

    print(f"💾 Đã lưu model → {path}/behavior_model.pth")


def load_model(path="models", device='cpu'):
    """Load model + scaler đã lưu."""
    model = BehaviorModel()
    model.load_state_dict(
        torch.load(os.path.join(path, "behavior_model.pth"), map_location=device, weights_only=True)
    )
    model.eval()

    with open(os.path.join(path, "scaler_params.json"), "r") as f:
        sp = json.load(f)

    scaler = StandardScaler()
    scaler.mean_ = np.array(sp["mean"])
    scaler.scale_ = np.array(sp["scale"])
    scaler.var_ = scaler.scale_ ** 2
    scaler.n_features_in_ = len(scaler.mean_)

    return model, scaler


def predict_behavior(model, session_data, scaler, device='cpu'):
    """
    Dự đoán nhóm hành vi cho 1 user.
    Returns: dict {label, label_id, confidence, probabilities, embedding}
    """
    model.eval()
    X = preprocess_single_user(session_data, scaler).to(device)

    with torch.no_grad():
        logits, embedding = model(X, return_embedding=True)
        probs = torch.softmax(logits, dim=1)[0]
        pred_id = probs.argmax().item()

    return {
        "label": BEHAVIOR_LABELS[pred_id],
        "label_id": pred_id,
        "confidence": round(probs[pred_id].item(), 4),
        "probabilities": {
            BEHAVIOR_LABELS[i]: round(probs[i].item(), 4)
            for i in range(NUM_CLASSES)
        },
        "embedding": embedding[0].cpu().numpy().tolist(),
    }


# =============================================
# CHẠY STANDALONE: train + evaluate + demo
# =============================================
if __name__ == "__main__":
    print("=" * 60)
    print("  MODULE 1 — Training & Evaluation")
    print("=" * 60)

    # 1. Tạo dữ liệu
    train_loader, test_loader, scaler = create_dataloaders(num_users_per_class=63)

    # 2. Khởi tạo model
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = BehaviorModel()
    total_params = sum(p.numel() for p in model.parameters())
    print(f"\n🧠 Model: {total_params:,} parameters | Device: {device}")

    # 3. Training
    model = train_model(model, train_loader, test_loader, epochs=50, device=device)

    # 4. Đánh giá chi tiết
    print("\n📊 KẾT QUẢ ĐÁNH GIÁ:")
    print("=" * 60)
    acc, f1, auc, report = evaluate_model(model, test_loader, device)
    print(f"  Accuracy:   {acc:.4f}")
    print(f"  F1 (macro): {f1:.4f}")
    print(f"  AUC (macro): {auc:.4f}")
    print(f"\n{report}")

    # 5. Lưu model
    save_model(model, scaler)

    # 6. Demo dự đoán
    print("\n🔮 DEMO DỰ ĐOÁN:")
    print("-" * 60)
    sample = [{"click_count": 30, "view_count": 8, "purchase_count": 6,
               "time_on_page": 1.2, "cart_add_count": 9, "search_count": 2,
               "session_duration": 8, "avg_price_viewed": 300,
               "category_diversity": 0.5, "return_rate": 0.2}] * 10

    result = predict_behavior(model, sample, scaler, device)
    print(f"  Nhóm: {result['label']} ({result['confidence']:.2%})")
    print(f"  Embedding dim: {len(result['embedding'])}")
    for g, p in result['probabilities'].items():
        print(f"    {g:20s}: {p:.4f} {'█' * int(p * 30)}")
