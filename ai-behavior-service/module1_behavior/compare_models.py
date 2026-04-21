"""
================================================================
  MODULE 1 — So sánh 3 mô hình: RNN vs LSTM vs BiLSTM
================================================================
Anti-overfitting — áp dụng khác nhau theo model:
  RNN    : dropout=0.20, wd=1e-4, không augment  (baseline nhẹ)
  LSTM   : dropout=0.30, wd=1e-4, không augment  (baseline TB)
  BiLSTM : dropout=0.50, wd=5e-4, augment=True,  (full reg)
            label_smoothing=0.1, Attention Pooling

Key architectural improvements vs last version:
  [A] Global Average Pooling cho RNN/LSTM (thay last hidden)
  [B] Attention Pooling cho BiLSTM
  [C] LayerNorm trước classifier (tất cả model)
  [D] GELU thay ReLU cho LSTM/BiLSTM
  [E] Selective augmentation — chỉ BiLSTM train trên aug_loader

Chạy: python -m module1_behavior.compare_models
"""

import os, time, json, warnings
warnings.filterwarnings("ignore")

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import (
    accuracy_score, f1_score, roc_auc_score,
    classification_report, confusion_matrix,
)
from sklearn.preprocessing import label_binarize
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from module1_behavior.data_pipeline import (
    BEHAVIOR_LABELS, NUM_FEATURES, NUM_CLASSES,
    BehaviorDataset, AugmentedBehaviorDataset,
)
from torch.utils.data import DataLoader

# ─────────────────────────────────────────────────────────────
# PER-MODEL CONFIG — điểm khác biệt chính so với bạn bè
# ─────────────────────────────────────────────────────────────
MODEL_CFG = {
    "RNN": {
        "dropout": 0.20, "lr": 1e-3, "weight_decay": 1e-4,
        "label_smoothing": 0.0, "augment": True,
    },
    "LSTM": {
        "dropout": 0.30, "lr": 1e-3, "weight_decay": 1e-4,
        "label_smoothing": 0.0, "augment": True,
    },
    "BiLSTM": {
        "dropout": 0.50, "lr": 5e-4, "weight_decay": 5e-4,
        "label_smoothing": 0.10, "augment": True,
    },
}

COLORS = {"RNN": "#E74C3C", "LSTM": "#F39C12", "BiLSTM": "#27AE60"}


# =============================================
# [A] RNN — GAP + LayerNorm
# =============================================
class RNNModel(nn.Module):
    """
    Vanilla RNN — Global Average Pooling thay last-hidden.
    [A] GAP: trung bình toàn bộ hidden states → ổn định hơn last-step
    [C] LayerNorm trước classifier → chuẩn hoá phân phối
    """
    def __init__(self, input_dim=NUM_FEATURES, hidden_dim=128,
                 num_classes=NUM_CLASSES, dropout=0.20):
        super().__init__()
        self.name = "RNN"
        self.fc_input = nn.Linear(input_dim, 64)
        self.bn = nn.BatchNorm1d(64)
        self.drop = nn.Dropout(dropout)

        self.rnn = nn.RNN(
            input_size=64, hidden_size=hidden_dim, num_layers=2,
            batch_first=True, dropout=dropout, nonlinearity="tanh",
        )
        self.norm = nn.LayerNorm(hidden_dim)          # [C]
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim, 64), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(64, num_classes),
        )

    def forward(self, x):
        b, t, f = x.shape
        x_proj = self.drop(torch.relu(self.bn(self.fc_input(x.reshape(-1, f)))))
        x_proj = x_proj.reshape(b, t, -1)
        out, _ = self.rnn(x_proj)
        pooled = out.mean(dim=1)                      # [A] GAP
        return self.classifier(self.norm(pooled))


# =============================================
# [A][C][D] LSTM — GAP + LayerNorm + GELU
# =============================================
class LSTMModel(nn.Module):
    """
    LSTM unidirectional — GAP + LayerNorm + GELU.
    [D] GELU thay ReLU: smoother gradient, tốt hơn cho sequence model
    """
    def __init__(self, input_dim=NUM_FEATURES, hidden_dim=128,
                 num_classes=NUM_CLASSES, dropout=0.30):
        super().__init__()
        self.name = "LSTM"
        self.fc_input = nn.Linear(input_dim, 64)
        self.bn = nn.BatchNorm1d(64)
        self.drop = nn.Dropout(dropout)

        self.lstm = nn.LSTM(
            input_size=64, hidden_size=hidden_dim, num_layers=2,
            batch_first=True, bidirectional=False, dropout=dropout,
        )
        self.norm = nn.LayerNorm(hidden_dim)          # [C]
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim, 64), nn.GELU(),     # [D]
            nn.Dropout(dropout), nn.Linear(64, num_classes),
        )

    def forward(self, x):
        b, t, f = x.shape
        x_proj = self.drop(torch.relu(self.bn(self.fc_input(x.reshape(-1, f)))))
        x_proj = x_proj.reshape(b, t, -1)
        out, _ = self.lstm(x_proj)
        pooled = out.mean(dim=1)                      # [A] GAP
        return self.classifier(self.norm(pooled))


# =============================================
# [B][C][D] BiLSTM — Attention Pooling + LayerNorm + GELU
# =============================================
class BiLSTMModel(nn.Module):
    """
    BiLSTM + Attention Pooling — model mạnh nhất với full regularization.

    [B] Attention Pooling: học trọng số tầm quan trọng từng session
        (thay mean pooling — biết session nào quan trọng hơn)
    [C] LayerNorm trước classifier
    [D] GELU activation
    Training dùng:
        dropout=0.5, wd=5e-4, label_smoothing=0.1, augment=True
    """
    def __init__(self, input_dim=NUM_FEATURES, hidden_dim=128,
                 embedding_dim=128, num_classes=NUM_CLASSES,
                 num_heads=4, dropout=0.50):
        super().__init__()
        self.name = "BiLSTM"

        self.fc_input = nn.Linear(input_dim, 64)
        self.bn_input = nn.BatchNorm1d(64)
        self.drop_input = nn.Dropout(dropout)

        self.lstm = nn.LSTM(
            input_size=64, hidden_size=hidden_dim, num_layers=2,
            batch_first=True, bidirectional=True, dropout=dropout,
        )
        lstm_out = hidden_dim * 2   # bidirectional → 256

        # [B] Attention Pooling — học trọng số từng timestep
        self.attn_proj = nn.Linear(lstm_out, 1)
        self.norm = nn.LayerNorm(lstm_out)            # [C]

        self.classifier = nn.Sequential(
            nn.Linear(lstm_out, embedding_dim), nn.GELU(),  # [D]
            nn.Dropout(dropout),
            nn.Dropout(dropout * 0.5),                      # double dropout
            nn.Linear(embedding_dim, num_classes),
        )

    def forward(self, x, return_embedding=False):
        b, t, f = x.shape
        x_proj = self.drop_input(
            torch.relu(self.bn_input(self.fc_input(x.reshape(-1, f))))
        )
        x_proj = x_proj.reshape(b, t, -1)

        out, _ = self.lstm(x_proj)                            # (B, T, 256)
        # [B] Attention weights
        scores  = self.attn_proj(torch.tanh(out)).squeeze(-1) # (B, T)
        weights = torch.softmax(scores, dim=-1).unsqueeze(-1) # (B, T, 1)
        pooled  = (weights * out).sum(dim=1)                  # (B, 256)

        normed = self.norm(pooled)
        logits = self.classifier(normed)

        if return_embedding:
            return logits, normed
        return logits

    def get_embedding(self, x):
        _, emb = self.forward(x, return_embedding=True)
        return emb


# =============================================
# TRAINING LOOP — AMP + early stopping
# =============================================
def train_one_model(model, train_loader, val_loader,
                    cfg: dict, epochs=80, device="cpu"):
    model = model.to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=cfg["label_smoothing"])
    optimizer = optim.Adam(model.parameters(),
                           lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-5)

    use_amp = (device != "cpu") and torch.cuda.is_available()
    scaler  = torch.cuda.amp.GradScaler(enabled=use_amp)

    history    = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": [], "val_f1": []}
    best_f1    = 0.0
    best_state = None
    no_improve = 0
    patience   = 20

    n_params = sum(p.numel() for p in model.parameters())
    print(f"\n{'='*60}")
    print(f"  {model.name} | {n_params:,} params | device={device}")
    print(f"  dropout={cfg['dropout']} | wd={cfg['weight_decay']} "
          f"| ls={cfg['label_smoothing']} | aug={cfg['augment']}")
    print(f"{'='*60}")

    start = time.time()
    for epoch in range(epochs):
        # ── TRAIN ──
        model.train()
        t_loss, t_preds, t_labels = 0.0, [], []
        for X_b, y_b in train_loader:
            X_b, y_b = X_b.to(device), y_b.to(device)
            optimizer.zero_grad()
            with torch.cuda.amp.autocast(enabled=use_amp):
                logits = model(X_b)
                loss   = criterion(logits, y_b)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
            t_loss += loss.item()
            t_preds.extend(logits.argmax(1).cpu().numpy())
            t_labels.extend(y_b.cpu().numpy())

        scheduler.step()
        train_loss = t_loss / len(train_loader)
        train_acc  = accuracy_score(t_labels, t_preds)

        # ── VALIDATE ──
        model.eval()
        v_loss, v_preds, v_labels = 0.0, [], []
        with torch.no_grad():
            for X_b, y_b in val_loader:
                X_b, y_b = X_b.to(device), y_b.to(device)
                logits = model(X_b)
                v_loss += criterion(logits, y_b).item()
                v_preds.extend(logits.argmax(1).cpu().numpy())
                v_labels.extend(y_b.cpu().numpy())

        val_loss = v_loss / len(val_loader)
        val_acc  = accuracy_score(v_labels, v_preds)
        val_f1   = f1_score(v_labels, v_preds, average="macro", zero_division=0)

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_acc"].append(train_acc)
        history["val_acc"].append(val_acc)
        history["val_f1"].append(val_f1)

        if (epoch + 1) % 10 == 0 or epoch == 0:
            gap = val_loss - train_loss
            flag = " ⚠ overfit" if gap > 0.30 else (" ~ ok" if gap > 0.15 else "")
            print(f"  Ep {epoch+1:3d}/{epochs} | tLoss={train_loss:.3f} vLoss={val_loss:.3f}"
                  f" | tAcc={train_acc:.3f} vAcc={val_acc:.3f} F1={val_f1:.3f}{flag}")

        # Early stopping theo val F1
        if val_f1 > best_f1 + 1e-4:
            best_f1    = val_f1
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                print(f"  ⏹ Early stop ep {epoch+1} | best F1={best_f1:.4f}")
                break

    if best_state:
        model.load_state_dict({k: v.to(device) for k, v in best_state.items()})

    elapsed = time.time() - start
    print(f"  ✅ Done ({elapsed:.1f}s) | Best Val F1={best_f1:.4f}")

    acc, f1, auc, report = _evaluate_full(model, val_loader, device)
    return model, history, {"name": model.name, "acc": acc, "f1": f1,
                             "auc": auc, "report": report, "params": n_params,
                             "time": elapsed}


def _evaluate_full(model, loader, device):
    model.eval()
    all_preds, all_labels, all_probs = [], [], []
    with torch.no_grad():
        for X_b, y_b in loader:
            logits = model(X_b.to(device))
            probs  = torch.softmax(logits, 1)
            all_preds.extend(logits.argmax(1).cpu().numpy())
            all_labels.extend(y_b.numpy())
            all_probs.extend(probs.cpu().numpy())
    y_true = np.array(all_labels)
    y_pred = np.array(all_preds)
    y_prob = np.array(all_probs)
    acc = accuracy_score(y_true, y_pred)
    f1  = f1_score(y_true, y_pred, average="macro", zero_division=0)
    try:
        auc = roc_auc_score(y_true, y_prob, multi_class="ovr", average="macro")
    except Exception:
        auc = 0.0
    label_names = [BEHAVIOR_LABELS[i] for i in range(NUM_CLASSES)]
    report = classification_report(y_true, y_pred, target_names=label_names, zero_division=0)
    return acc, f1, auc, report


# =============================================
# OVERFITTING ANALYSIS
# =============================================
def check_overfitting(histories: dict):
    print(f"\n{'='*60}")
    print("  PHÂN TÍCH OVERFITTING (val_loss - train_loss cuối)")
    print(f"{'='*60}")
    print(f"  {'Model':<10} {'Train Loss':>11} {'Val Loss':>10} {'Gap':>8}  Đánh giá")
    print(f"  {'-'*55}")
    for name, hist in histories.items():
        tl  = hist["train_loss"][-1]
        vl  = hist["val_loss"][-1]
        gap = vl - tl
        status = "✓ Tốt" if gap < 0.15 else ("~ Chấp nhận" if gap < 0.30 else "✗ Overfit")
        print(f"  {name:<10} {tl:>11.4f} {vl:>10.4f} {gap:>8.4f}  {status}")


# =============================================
# PLOTS
# =============================================
def plot_training_curves(histories, save_dir):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Training Curves — RNN vs LSTM vs BiLSTM\n"
                 "(BiLSTM: dropout=0.5, wd=5e-4, label_smoothing=0.1, augment)",
                 fontsize=12, fontweight="bold")
    for name, hist in histories.items():
        c  = COLORS[name]
        ep = range(1, len(hist["train_loss"]) + 1)
        axes[0].plot(ep, hist["train_loss"], color=c, lw=2, label=f"{name} train")
        axes[0].plot(ep, hist["val_loss"],   color=c, lw=2, ls="--", label=f"{name} val")
        axes[1].plot(ep, hist["val_acc"],    color=c, lw=2, label=name)
    axes[0].set_title("Loss (train vs val) — gap nhỏ = ít overfit")
    axes[0].set_xlabel("Epoch"); axes[0].set_ylabel("Loss")
    axes[0].legend(fontsize=8); axes[0].grid(alpha=0.3)
    axes[1].set_title("Validation Accuracy")
    axes[1].set_xlabel("Epoch"); axes[1].set_ylabel("Accuracy")
    axes[1].legend(fontsize=9); axes[1].grid(alpha=0.3); axes[1].set_ylim(0, 1.05)
    plt.tight_layout()
    path = os.path.join(save_dir, "01_training_curves.png")
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  💾 {path}")


def plot_metrics_comparison(all_metrics, save_dir):
    names = [m["name"] for m in all_metrics]
    accs  = [m["acc"]  for m in all_metrics]
    f1s   = [m["f1"]   for m in all_metrics]
    aucs  = [m["auc"]  for m in all_metrics]
    x, w  = np.arange(len(names)), 0.25

    fig, ax = plt.subplots(figsize=(10, 6))
    for i, (vals, label, color) in enumerate([
        (accs, "Accuracy", "#3498DB"),
        (f1s,  "F1 (macro)", "#E67E22"),
        (aucs, "AUC (macro)", "#9B59B6"),
    ]):
        bars = ax.bar(x + (i - 1) * w, vals, w, label=label, color=color, alpha=0.85)
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
                    f"{bar.get_height():.3f}", ha="center", va="bottom", fontsize=9)

    best_idx = int(np.argmax(f1s))
    ax.axvspan(x[best_idx] - 0.45, x[best_idx] + 0.45, alpha=0.08,
               color=COLORS[names[best_idx]])
    ax.set_xticks(x); ax.set_xticklabels(names, fontsize=13, fontweight="bold")
    ax.set_ylabel("Score"); ax.set_ylim(0, 1.12)
    ax.set_title(f"🏆 So sánh 3 mô hình — Best: {names[best_idx]}", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11); ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(save_dir, "02_metrics_comparison.png")
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  💾 {path}")


def plot_confusion_matrix(model, loader, device, save_dir):
    model.eval()
    preds, labels = [], []
    with torch.no_grad():
        for X_b, y_b in loader:
            preds.extend(model(X_b.to(device)).argmax(1).cpu().numpy())
            labels.extend(y_b.numpy())
    cm = confusion_matrix(labels, preds)
    label_names = [BEHAVIOR_LABELS[i] for i in range(NUM_CLASSES)]

    fig, ax = plt.subplots(figsize=(11, 9))
    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    plt.colorbar(im, ax=ax)
    ax.set_xticks(range(NUM_CLASSES)); ax.set_yticks(range(NUM_CLASSES))
    ax.set_xticklabels(label_names, rotation=30, ha="right", fontsize=10)
    ax.set_yticklabels(label_names, fontsize=10)
    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=12,
                    color="white" if cm[i, j] > thresh else "black")
    ax.set_ylabel("Thực tế"); ax.set_xlabel("Dự đoán")
    ax.set_title("🎯 Confusion Matrix — BiLSTM (Model Tốt Nhất)", fontsize=14, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(save_dir, "03_confusion_matrix.png")
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  💾 {path}")


def plot_roc_curves(model, loader, device, save_dir):
    from sklearn.metrics import roc_curve, auc
    model.eval()
    all_labels, all_probs = [], []
    with torch.no_grad():
        for X_b, y_b in loader:
            all_probs.extend(torch.softmax(model(X_b.to(device)), 1).cpu().numpy())
            all_labels.extend(y_b.numpy())
    y_bin = label_binarize(np.array(all_labels), classes=list(range(NUM_CLASSES)))
    all_probs = np.array(all_probs)

    fig, ax = plt.subplots(figsize=(10, 8))
    colors = plt.cm.Set1(np.linspace(0, 0.9, NUM_CLASSES))
    for i in range(NUM_CLASSES):
        fpr, tpr, _ = roc_curve(y_bin[:, i], all_probs[:, i])
        ax.plot(fpr, tpr, color=colors[i], lw=2,
                label=f"{BEHAVIOR_LABELS[i]} (AUC={auc(fpr, tpr):.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=1)
    ax.set_xlabel("False Positive Rate"); ax.set_ylabel("True Positive Rate")
    ax.set_title("📊 ROC Curve per Class — BiLSTM", fontsize=14, fontweight="bold")
    ax.legend(loc="lower right", fontsize=10); ax.grid(alpha=0.3)
    plt.tight_layout()
    path = os.path.join(save_dir, "04_roc_curve.png")
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  💾 {path}")


def plot_radar(all_metrics, save_dir):
    keys    = ["acc", "f1", "auc"]
    labels  = ["Accuracy", "F1-macro", "AUC-ROC"]
    N       = len(keys)
    angles  = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist() + [0]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
    ax.set_title("Radar Chart — Performance Comparison", fontsize=12,
                 fontweight="bold", pad=20)
    for m in all_metrics:
        vals = [m[k] for k in keys] + [m[keys[0]]]
        ax.plot(angles, vals, "o-", lw=2, label=m["name"], color=COLORS[m["name"]])
        ax.fill(angles, vals, alpha=0.12, color=COLORS[m["name"]])
    ax.set_thetagrids(np.degrees(angles[:-1]), labels)
    ax.set_ylim(0, 1); ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.grid(True)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=11)
    plt.tight_layout()
    path = os.path.join(save_dir, "05_radar_chart.png")
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  💾 {path}")


# =============================================
# MAIN
# =============================================
if __name__ == "__main__":
    EPOCHS    = 80
    PLOTS_DIR = "plots"
    MODEL_DIR = "models"
    os.makedirs(PLOTS_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\n{'='*60}")
    print("  SO SÁNH 3 MÔ HÌNH: RNN / LSTM / BiLSTM")
    print(f"  Device: {device}")
    if device == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
    print(f"{'='*60}")

    # ── Tạo raw data ──
    from module1_behavior.data_pipeline import BehaviorDataGenerator
    gen = BehaviorDataGenerator(num_users_per_class=63, seed=42)
    X, y = gen.generate()

    n = len(X)
    n_test = int(n * 0.15)
    n_val  = int(n * 0.15)
    idx    = np.random.RandomState(42).permutation(n)
    train_idx = idx[:n - n_test - n_val]
    val_idx   = idx[n - n_test - n_val : n - n_test]
    test_idx  = idx[n - n_test:]

    X_train, y_train = X[train_idx], y[train_idx]
    X_val,   y_val   = X[val_idx],   y[val_idx]
    X_test,  y_test  = X[test_idx],  y[test_idx]
    print(f"\n  Split 70/15/15: Train={len(X_train)} | Val={len(X_val)} | Test={len(X_test)}")

    # ── Datasets — base (không aug) và aug (chỉ cho BiLSTM) ──
    base_train_ds = BehaviorDataset(X_train, y_train, fit_scaler=True)
    aug_train_ds  = AugmentedBehaviorDataset(
        X_train, y_train, scaler=base_train_ds.scaler, fit_scaler=False, augment=True
    )
    val_ds  = BehaviorDataset(X_val,  y_val,  scaler=base_train_ds.scaler, fit_scaler=False)
    test_ds = BehaviorDataset(X_test, y_test, scaler=base_train_ds.scaler, fit_scaler=False)

    base_loader = DataLoader(base_train_ds, batch_size=32, shuffle=True,
                             pin_memory=(device == "cuda"))
    aug_loader  = DataLoader(aug_train_ds,  batch_size=32, shuffle=True,
                             pin_memory=(device == "cuda"))
    val_loader  = DataLoader(val_ds,  batch_size=32, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=32, shuffle=False)

    # ── Khởi tạo 3 model với per-model dropout ──
    models_def = {
        "RNN":    RNNModel(dropout=MODEL_CFG["RNN"]["dropout"]),
        "LSTM":   LSTMModel(dropout=MODEL_CFG["LSTM"]["dropout"]),
        "BiLSTM": BiLSTMModel(dropout=MODEL_CFG["BiLSTM"]["dropout"]),
    }
    print("\n  [Architecture]")
    for name, m in models_def.items():
        n_p = sum(p.numel() for p in m.parameters())
        cfg = MODEL_CFG[name]
        print(f"  {name:<8}: {n_p:>8,} params | dropout={cfg['dropout']} "
              f"wd={cfg['weight_decay']} aug={cfg['augment']}")

    # ── Train cả 3 ──
    histories, all_metrics, trained = {}, [], {}
    for name, model in models_def.items():
        cfg    = MODEL_CFG[name]
        loader = aug_loader if cfg["augment"] else base_loader   # [E] selective aug
        m, hist, metrics = train_one_model(
            model, loader, val_loader, cfg, EPOCHS, device
        )
        histories[name] = hist
        all_metrics.append(metrics)
        trained[name] = m
        print(f"\n  {name} → Acc={metrics['acc']:.4f} F1={metrics['f1']:.4f} AUC={metrics['auc']:.4f}")

    # ── Overfitting analysis ──
    check_overfitting(histories)

    # ── Evaluate trên test set ──
    print(f"\n{'='*60}")
    print("  KẾT QUẢ TEST SET")
    print(f"{'='*60}")
    test_results = []
    for name, m in trained.items():
        acc, f1, auc, report = _evaluate_full(m, test_loader, device)
        test_results.append({"name": name, "acc": acc, "f1": f1, "auc": auc})
        print(f"\n  [{name}] Acc={acc:.4f} | F1={f1:.4f} | AUC={auc:.4f}")
        print(f"\n{report}")

    # ── Chọn best model ──
    best_m   = max(all_metrics, key=lambda m: m["f1"])
    best_name = best_m["name"]
    best_model = trained[best_name]
    print(f"\n{'='*60}")
    print(f"  🏆 Best model: {best_name} (Val F1={best_m['f1']:.4f})")
    print(f"{'='*60}")

    # ── Lưu model tốt nhất ──
    torch.save(best_model.state_dict(), os.path.join(MODEL_DIR, "model_best.pth"))
    meta = {
        "model_name": best_name, "f1_macro": round(best_m["f1"], 4),
        "accuracy": round(best_m["acc"], 4), "auc_macro": round(best_m["auc"], 4),
        "epochs": EPOCHS, "num_classes": NUM_CLASSES,
        "behavior_labels": BEHAVIOR_LABELS,
        "anti_overfitting": MODEL_CFG[best_name],
    }
    with open(os.path.join(MODEL_DIR, "model_best_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"  💾 models/model_best.pth + model_best_meta.json")

    # ── Plots ──
    print(f"\n  📊 Đang vẽ plots → {PLOTS_DIR}/")
    plot_training_curves(histories, PLOTS_DIR)
    plot_metrics_comparison(all_metrics, PLOTS_DIR)
    plot_confusion_matrix(best_model, test_loader, device, PLOTS_DIR)
    plot_roc_curves(best_model, test_loader, device, PLOTS_DIR)
    plot_radar(all_metrics, PLOTS_DIR)

    print(f"\n✅ Xong! Plots: {PLOTS_DIR}/")
    print("  01_training_curves.png  — Loss & Accuracy qua epochs")
    print("  02_metrics_comparison.png — Bar chart Acc/F1/AUC")
    print("  03_confusion_matrix.png — Best model")
    print("  04_roc_curve.png        — ROC per class")
    print("  05_radar_chart.png      — Radar so sánh 3 model")
