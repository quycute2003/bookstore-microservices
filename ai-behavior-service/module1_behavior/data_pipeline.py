"""
================================================================
  MODULE 1 — Data Pipeline: Tiền xử lý & sinh dữ liệu hành vi
================================================================
Sinh dữ liệu tổng hợp (synthetic) cho 8 nhóm khách hàng:
  0: impulse_buyer    — Mua sắm bốc đồng
  1: researcher       — Nghiên cứu kỹ trước khi mua
  2: loyal_customer   — Khách hàng trung thành
  3: price_sensitive  — Nhạy cảm về giá
  4: window_shopper   — Chỉ xem, ít mua
  5: brand_loyal      — Trung thành với thương hiệu cụ thể
  6: deal_hunter      — Săn sale & khuyến mãi
  7: gift_buyer       — Mua quà tặng

Chạy standalone (sinh CSV):
  cd ai-behavior-service
  python -m module1_behavior.data_pipeline
"""

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import StandardScaler
import os

# =============================================
# ĐỊNH NGHĨA NHÃN NHÓM HÀNH VI (8 classes)
# =============================================
BEHAVIOR_LABELS = {
    0: "impulse_buyer",
    1: "researcher",
    2: "loyal_customer",
    3: "price_sensitive",
    4: "window_shopper",
    5: "brand_loyal",
    6: "deal_hunter",
    7: "gift_buyer",
}

NUM_CLASSES = len(BEHAVIOR_LABELS)

LABEL_DESCRIPTIONS = {
    "impulse_buyer":   "Khách mua nhanh, ít cân nhắc, bị thu hút bởi khuyến mãi",
    "researcher":      "Xem nhiều, so sánh kỹ, đọc review trước khi quyết định",
    "loyal_customer":  "Quay lại thường xuyên, mua đều đặn, ít đổi trả",
    "price_sensitive": "Tìm giá tốt nhất, hay dùng mã giảm giá, so sánh giá",
    "window_shopper":  "Xem nhiều nhưng mua rất ít, chỉ lướt qua",
    "brand_loyal":     "Trung thành với 1 brand, mua lặp lại cùng loại hàng",
    "deal_hunter":     "Săn sale, mua số lượng lớn khi có promotion",
    "gift_buyer":      "Mua quà tặng: session ngắn, giá cao, ít đổi trả",
}

# Cấu hình kích thước dữ liệu
NUM_FEATURES = 10      # Số features mỗi session
NUM_SESSIONS = 10      # Số session mỗi user (cho LSTM)

FEATURE_NAMES = [
    "click_count",        # Số lần click
    "view_count",         # Số lần xem sản phẩm
    "purchase_count",     # Số lần mua
    "time_on_page",       # Thời gian trên trang (phút)
    "cart_add_count",     # Số lần thêm vào giỏ
    "search_count",       # Số lần tìm kiếm
    "session_duration",   # Thời lượng phiên (phút)
    "avg_price_viewed",   # Giá trung bình sản phẩm đã xem (nghìn VNĐ)
    "category_diversity", # Đa dạng thể loại (0-1)
    "return_rate",        # Tỷ lệ đổi trả (0-1)
]


class BehaviorDataGenerator:
    """
    Sinh dữ liệu hành vi tổng hợp cho 8 nhóm khách hàng.
    Mỗi user gồm nhiều sessions, mỗi session có 10 features.
    """

    def __init__(self, num_users_per_class=63, num_sessions=NUM_SESSIONS, seed=42):
        # 63 × 8 = 504 ≈ 500 users (lấy chẵn 500 sau)
        self.num_users_per_class = num_users_per_class
        self.num_sessions = num_sessions
        np.random.seed(seed)

    def _t(self, s):
        """Normalized session progress: 0.0 (session đầu) → 1.0 (session cuối)."""
        return s / max(self.num_sessions - 1, 1)

    def _gen_impulse_buyer(self, n):
        """
        Bốc đồng: mua ngay ở session đầu, sau đó return tăng dần.
        Temporal: purchase_count cao → giảm; return_rate thấp → tăng.
        """
        data = np.zeros((n, self.num_sessions, NUM_FEATURES))
        for i in range(n):
            for s in range(self.num_sessions):
                t = self._t(s)
                data[i, s] = [
                    np.random.randint(15, 40),
                    np.random.randint(5, 15),
                    max(1, int(np.random.randint(4, 9) * (1 - 0.5 * t))),   # purchase: giảm dần
                    np.random.uniform(0.5, 3.0),
                    max(1, int(np.random.randint(5, 12) * (1 - 0.4 * t))),  # cart_add: giảm
                    np.random.randint(1, 5),
                    np.random.uniform(5, 15),
                    np.random.uniform(100, 500),
                    np.random.uniform(0.3, 0.8),
                    np.random.uniform(0.05, 0.15) + 0.2 * t,                # return: tăng dần
                ]
        return data

    def _gen_researcher(self, n):
        """
        Nghiên cứu: search nhiều → thu hẹp → quyết mua cuối.
        Temporal: search cao → giảm; cart_add thấp → tăng; purchase 0 → xuất hiện.
        """
        data = np.zeros((n, self.num_sessions, NUM_FEATURES))
        for i in range(n):
            for s in range(self.num_sessions):
                t = self._t(s)
                data[i, s] = [
                    np.random.randint(20, 50),
                    np.random.randint(15, 40),
                    1 if t > 0.8 else 0,                                     # purchase: chỉ cuối
                    np.random.uniform(5, 15),
                    max(1, int(np.random.randint(1, 4) + 5 * t)),            # cart_add: tăng dần
                    max(2, int(np.random.randint(12, 22) * (1 - 0.6 * t))), # search: giảm dần
                    np.random.uniform(20, 60),
                    np.random.uniform(100, 800) * (1 - 0.3 * t),            # thu hẹp giá mục tiêu
                    max(0.2, np.random.uniform(0.7, 0.95) - 0.5 * t),       # diversity: giảm (focus)
                    np.random.uniform(0.02, 0.08),
                ]
        return data

    def _gen_loyal_customer(self, n):
        """
        Trung thành: purchase tăng đều qua các session, pattern ổn định.
        Temporal: purchase_count tăng nhẹ; session_duration tăng (quen hơn).
        """
        data = np.zeros((n, self.num_sessions, NUM_FEATURES))
        for i in range(n):
            base_click    = np.random.randint(10, 20)
            base_purchase = np.random.randint(1, 3)
            for s in range(self.num_sessions):
                t = self._t(s)
                data[i, s] = [
                    base_click + np.random.randint(-3, 4),
                    np.random.randint(8, 20),
                    base_purchase + int(3 * t) + np.random.randint(-1, 2),  # purchase: tăng dần
                    np.random.uniform(3, 8),
                    np.random.randint(2, 6),
                    np.random.randint(3, 8),
                    np.random.uniform(10, 20) + 10 * t,                      # duration: tăng (quen)
                    np.random.uniform(150, 400),
                    np.random.uniform(0.2, 0.5),
                    np.random.uniform(0.01, 0.05),
                ]
        return data

    def _gen_price_sensitive(self, n):
        """
        Nhạy cảm giá: add→remove nhiều lần, chỉ mua khi giá thấp nhất.
        Temporal: cart_add cao nhưng fluctuate; purchase chỉ xuất hiện ở session giữa.
        """
        data = np.zeros((n, self.num_sessions, NUM_FEATURES))
        for i in range(n):
            for s in range(self.num_sessions):
                t = self._t(s)
                # Mua ở session giữa khi tìm được giá tốt
                is_buy_session = 0.3 < t < 0.7
                data[i, s] = [
                    np.random.randint(15, 35),
                    np.random.randint(10, 30),
                    np.random.randint(1, 3) if is_buy_session else 0,
                    np.random.uniform(3, 10),
                    np.random.randint(8, 18),                                # cart_add cao liên tục
                    max(5, int(np.random.randint(15, 25) * (1 - 0.4 * t))), # search: nhiều ban đầu
                    np.random.uniform(15, 40),
                    np.random.uniform(50, 200),
                    np.random.uniform(0.6, 0.95),
                    np.random.uniform(0.05, 0.2),
                ]
        return data

    def _gen_window_shopper(self, n):
        """
        Chỉ lướt: view tăng dần nhưng không bao giờ mua nhiều.
        Temporal: view_count tăng nhẹ qua sessions; purchase vẫn gần 0.
        """
        data = np.zeros((n, self.num_sessions, NUM_FEATURES))
        for i in range(n):
            for s in range(self.num_sessions):
                t = self._t(s)
                data[i, s] = [
                    np.random.randint(3, 10),
                    min(40, int(np.random.randint(10, 20) + 15 * t)),        # view: tăng dần
                    1 if (t > 0.9 and np.random.random() < 0.2) else 0,     # purchase: gần 0
                    np.random.uniform(1, 4),
                    np.random.randint(0, 2),
                    np.random.randint(1, 5),
                    np.random.uniform(3, 12),
                    np.random.uniform(100, 600),
                    min(1.0, np.random.uniform(0.4, 0.7) + 0.2 * t),        # diversity: tăng
                    np.random.uniform(0.0, 0.05),
                ]
        return data

    def _gen_brand_loyal(self, n):
        """
        Brand loyal: pattern siêu ổn định + avg_price không đổi, purchase đều.
        Temporal: variance giảm dần (ngày càng consistent hơn).
        """
        data = np.zeros((n, self.num_sessions, NUM_FEATURES))
        for i in range(n):
            base_price = np.random.uniform(300, 900)
            for s in range(self.num_sessions):
                t = self._t(s)
                noise_scale = max(0.1, 1 - t * 0.7)   # variance giảm → pattern rõ hơn
                data[i, s] = [
                    int(np.random.randint(8, 20) * noise_scale + 12 * (1 - noise_scale)),
                    np.random.randint(5, 12),
                    np.random.randint(2, 5),
                    np.random.uniform(2, 6),
                    np.random.randint(2, 5),
                    max(1, int(np.random.randint(1, 5) * noise_scale)),      # search: giảm dần
                    np.random.uniform(5, 15),
                    base_price + np.random.uniform(-50, 50) * noise_scale,   # price: ổn định hơn
                    max(0.05, np.random.uniform(0.05, 0.25) * noise_scale),  # diversity: giảm
                    np.random.uniform(0.02, 0.08),
                ]
        return data

    def _gen_deal_hunter(self, n):
        """
        Săn sale: burst mua khi có sale, im lặng khi không. Pattern chu kỳ.
        Temporal: sale_burst xen kẽ với low-activity sessions.
        """
        data = np.zeros((n, self.num_sessions, NUM_FEATURES))
        for i in range(n):
            # Cố định vị trí sale sessions cho từng user
            sale_sessions = set(np.random.choice(self.num_sessions, size=3, replace=False))
            for s in range(self.num_sessions):
                is_sale = s in sale_sessions
                data[i, s] = [
                    np.random.randint(30, 55) if is_sale else np.random.randint(5, 15),
                    np.random.randint(15, 35) if is_sale else np.random.randint(3, 10),
                    np.random.randint(5, 12) if is_sale else 0,              # purchase: chỉ khi sale
                    np.random.uniform(4, 12),
                    np.random.randint(12, 22) if is_sale else np.random.randint(2, 6),
                    np.random.randint(15, 28) if is_sale else np.random.randint(5, 12),
                    np.random.uniform(20, 50) if is_sale else np.random.uniform(5, 15),
                    np.random.uniform(40, 150),
                    np.random.uniform(0.7, 1.0) if is_sale else np.random.uniform(0.3, 0.6),
                    np.random.uniform(0.08, 0.25),
                ]
        return data

    def _gen_gift_buyer(self, n):
        """
        Mua quà: search → narrow down → mua nhanh, session ngắn, giá cao.
        Temporal: search giảm; purchase xuất hiện ở session cuối; price tăng (chọn xịn hơn).
        """
        data = np.zeros((n, self.num_sessions, NUM_FEATURES))
        for i in range(n):
            for s in range(self.num_sessions):
                t = self._t(s)
                data[i, s] = [
                    np.random.randint(5, 15),
                    max(2, int(np.random.randint(5, 12) * (1 - 0.5 * t))),  # view: giảm (focus)
                    1 if t > 0.7 else 0,                                      # purchase: chỉ cuối
                    np.random.uniform(1, 4),
                    np.random.randint(1, 4),
                    max(1, int(np.random.randint(5, 10) * (1 - 0.6 * t))),  # search: giảm
                    np.random.uniform(3, 10),
                    np.random.uniform(300, 800) + 500 * t,                    # price: tăng (chọn xịn)
                    np.random.uniform(0.3, 0.7),
                    np.random.uniform(0.01, 0.06),
                ]
        return data

    def generate(self):
        """
        Sinh toàn bộ dataset.
        Returns: X shape (n_total, num_sessions, num_features), y shape (n_total,)
        """
        generators = [
            self._gen_impulse_buyer,
            self._gen_researcher,
            self._gen_loyal_customer,
            self._gen_price_sensitive,
            self._gen_window_shopper,
            self._gen_brand_loyal,
            self._gen_deal_hunter,
            self._gen_gift_buyer,
        ]

        X_list, y_list = [], []
        for label, gen_fn in enumerate(generators):
            X_class = gen_fn(self.num_users_per_class)
            y_class = np.full(self.num_users_per_class, label)
            X_list.append(X_class)
            y_list.append(y_class)

        X = np.concatenate(X_list, axis=0)
        y = np.concatenate(y_list, axis=0)

        # Giữ đúng 500 users
        if len(X) > 500:
            X, y = X[:500], y[:500]

        # Trộn dữ liệu
        idx = np.random.permutation(len(X))
        return X[idx], y[idx]

    def export_csv(self, output_path="data/data_user500.csv"):
        """
        Xuất dataset ra file CSV.
        Mỗi dòng = 1 session của 1 user (long format).
        Columns: user_id, session_id, behavior_label, feature1, ..., feature10
        """
        X, y = self.generate()
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

        rows = []
        for user_idx in range(len(X)):
            user_id = f"user_{user_idx + 1:03d}"
            label_id = int(y[user_idx])
            label_name = BEHAVIOR_LABELS[label_id]

            for session_idx in range(self.num_sessions):
                session_features = X[user_idx, session_idx]
                row = {
                    "user_id":           user_id,
                    "session_id":        session_idx + 1,
                    "behavior_label":    label_name,
                    "behavior_id":       label_id,
                }
                for feat_name, feat_val in zip(FEATURE_NAMES, session_features):
                    row[feat_name] = round(float(feat_val), 4)
                rows.append(row)

        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"✅ Exported {len(X)} users × {self.num_sessions} sessions = {len(df)} rows")
        print(f"   → {output_path}")
        print("\n📊 Distribution:")
        dist = df.drop_duplicates("user_id")["behavior_label"].value_counts()
        for label, count in dist.items():
            print(f"   {label:20s}: {count} users")
        return df


class BehaviorDataset(Dataset):
    """PyTorch Dataset — chuẩn hóa features bằng StandardScaler."""

    def __init__(self, X, y, scaler=None, fit_scaler=True):
        n, s, f = X.shape
        X_flat = X.reshape(-1, f)

        if fit_scaler:
            self.scaler = StandardScaler()
            X_flat = self.scaler.fit_transform(X_flat)
        else:
            self.scaler = scaler
            X_flat = self.scaler.transform(X_flat)

        X_scaled = X_flat.reshape(n, s, f)
        self.X = torch.FloatTensor(X_scaled)
        self.y = torch.LongTensor(y)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


class AugmentedBehaviorDataset(Dataset):
    """
    Dataset với augmentation để chống overfitting trên data synthetic nhỏ.

    Augmentation áp dụng khi training:
      1. Gaussian noise      — thêm nhiễu N(0, noise_std) vào features
      2. Feature masking     — zero out ngẫu nhiên mask_prob % features
      3. Session jitter      — shuffle nhẹ thứ tự sessions (swap 2 session liền kề)
      4. Temporal scaling    — scale session values ×U(0.9, 1.1) per session
    """

    def __init__(self, X, y, scaler=None, fit_scaler=True,
                 noise_std=0.08, mask_prob=0.12, jitter_prob=0.3,
                 augment=True):
        n, s, f = X.shape
        X_flat = X.reshape(-1, f)

        if fit_scaler:
            self.scaler = StandardScaler()
            X_flat = self.scaler.fit_transform(X_flat)
        else:
            self.scaler = scaler
            X_flat = self.scaler.transform(X_flat)

        X_scaled = X_flat.reshape(n, s, f)
        self.X = torch.FloatTensor(X_scaled)
        self.y = torch.LongTensor(y)

        self.augment   = augment
        self.noise_std = noise_std
        self.mask_prob = mask_prob
        self.jitter_prob = jitter_prob

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        x = self.X[idx].clone()   # (sessions, features)
        y = self.y[idx]

        if self.augment:
            # 1. Gaussian noise
            x = x + torch.randn_like(x) * self.noise_std

            # 2. Feature masking — zero out random features
            mask = torch.rand(x.shape) > self.mask_prob
            x = x * mask.float()

            # 3. Session jitter — swap 2 session liền kề ngẫu nhiên
            if torch.rand(1).item() < self.jitter_prob and x.shape[0] > 2:
                i = torch.randint(0, x.shape[0] - 1, (1,)).item()
                x[[i, i + 1]] = x[[i + 1, i]]

            # 4. Temporal scaling per session
            scale = torch.FloatTensor(x.shape[0], 1).uniform_(0.88, 1.12)
            x = x * scale

        return x, y


def create_dataloaders(num_users_per_class=63, batch_size=32, test_ratio=0.2,
                       seed=42, augment=True):
    """Tạo DataLoader với augmentation cho training, không augment cho test."""
    generator = BehaviorDataGenerator(num_users_per_class=num_users_per_class, seed=seed)
    X, y = generator.generate()

    n = len(X)
    n_test = int(n * test_ratio)
    X_train, X_test = X[:n-n_test], X[n-n_test:]
    y_train, y_test = y[:n-n_test], y[n-n_test:]

    if augment:
        train_ds = AugmentedBehaviorDataset(X_train, y_train, fit_scaler=True, augment=True)
        test_ds  = AugmentedBehaviorDataset(X_test,  y_test,
                                             scaler=train_ds.scaler, fit_scaler=False,
                                             augment=False)
    else:
        train_ds = BehaviorDataset(X_train, y_train, fit_scaler=True)
        test_ds  = BehaviorDataset(X_test, y_test, scaler=train_ds.scaler, fit_scaler=False)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                              pin_memory=torch.cuda.is_available())
    test_loader  = DataLoader(test_ds,  batch_size=batch_size, shuffle=False,
                              pin_memory=torch.cuda.is_available())

    print(f"✅ Dataset: Train={len(train_ds)} | Test={len(test_ds)} | Augment={augment}")
    print(f"   Shape: ({NUM_SESSIONS} sessions, {NUM_FEATURES} features)")
    for k, v in BEHAVIOR_LABELS.items():
        print(f"   {k}: {v} — train={(y_train==k).sum()}, test={(y_test==k).sum()}")

    return train_loader, test_loader, train_ds.scaler


def preprocess_single_user(session_data, scaler):
    """
    Tiền xử lý dữ liệu 1 user để dự đoán realtime.
    Args: session_data — list of dict hoặc np.ndarray
    Returns: torch.Tensor shape (1, NUM_SESSIONS, NUM_FEATURES)
    """
    if isinstance(session_data, list):
        X = np.array([[
            s.get("click_count", 0), s.get("view_count", 0),
            s.get("purchase_count", 0), s.get("time_on_page", 0),
            s.get("cart_add_count", 0), s.get("search_count", 0),
            s.get("session_duration", 0), s.get("avg_price_viewed", 0),
            s.get("category_diversity", 0), s.get("return_rate", 0),
        ] for s in session_data])
    else:
        X = np.array(session_data)

    # Padding nếu chưa đủ sessions
    if len(X) < NUM_SESSIONS:
        pad = np.zeros((NUM_SESSIONS - len(X), NUM_FEATURES))
        X = np.concatenate([pad, X], axis=0)
    elif len(X) > NUM_SESSIONS:
        X = X[-NUM_SESSIONS:]

    X_scaled = scaler.transform(X)
    return torch.FloatTensor(X_scaled).unsqueeze(0)


# =============================================
# CHẠY STANDALONE ĐỂ EXPORT CSV
# =============================================
if __name__ == "__main__":
    print("=" * 60)
    print("  MODULE 1 — Data Pipeline: Sinh & Xuất CSV")
    print("=" * 60)

    generator = BehaviorDataGenerator(num_users_per_class=63, seed=42)
    df = generator.export_csv("data/data_user500.csv")

    print("\n📋 20 dòng đầu tiên:")
    print(df.head(20).to_string(index=False))

    print("\n📊 Thống kê features:")
    print(df[FEATURE_NAMES].describe().round(2).to_string())
    print("\n✅ Done! File saved: data/data_user500.csv")
