"""
================================================================
  MODULE 1 — generate_data.py
  Bước 1 trong pipeline dữ liệu: sinh raw event logs
================================================================

Pipeline dữ liệu 2 bước:
  Bước 1 (file này) : sinh event-level logs
                      → data/data_user500.csv
                      Format: 14 cột (xem COLUMNS bên dưới)

  Bước 2 (data_pipeline.py): event logs → session-aggregated features
                               → BehaviorDataset → BiLSTM training

Các cột trong CSV:
  user_id, product_id, product_category, action, timestamp,
  session_id, segment,
  device, referrer, duration_seconds, scroll_depth,
  price, quantity, coupon_used

Điểm khác biệt so với yêu cầu cơ bản:
  [+] 8 loại hành vi (thay vì 3: view/click/add_to_cart)
  [+] 8 nhóm khách hàng với phân phối xác suất riêng
  [+] device — mobile/desktop/tablet theo từng segment
  [+] referrer — 6 nguồn traffic (social, email, direct, ...)
  [+] duration_seconds — thời gian trên action (realistic range)
  [+] scroll_depth — % cuộn trang (view/review_read có ý nghĩa)
  [+] price — giá sản phẩm theo category (VND)
  [+] quantity — số lượng (add_to_cart/purchase)
  [+] coupon_used — có dùng coupon không (purchase only)
  [+] product_category — book/clothes/electronics/other
  [+] Temporal structure: session ordering theo thời gian thực
  [+] to_session_features(): cầu nối sang data_pipeline.py

Chạy standalone:
  cd ai-behavior-service
  python -m module1_behavior.generate_data
"""

import os
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

np.random.seed(42)
random.seed(42)

# ── 8 loại hành vi ────────────────────────────────────────────
ACTIONS = [
    'view', 'click', 'add_to_cart', 'purchase',
    'search', 'review_read', 'price_check', 'remove_from_cart',
]

# ── Xác suất action theo segment ──────────────────────────────
SEGMENT_ACTION_PROBS = {
    'impulse_buyer': {
        'view': 0.12, 'click': 0.22, 'add_to_cart': 0.26, 'purchase': 0.22,
        'search': 0.06, 'review_read': 0.03, 'price_check': 0.03, 'remove_from_cart': 0.06,
    },
    'researcher': {
        'view': 0.18, 'click': 0.14, 'add_to_cart': 0.08, 'purchase': 0.04,
        'search': 0.16, 'review_read': 0.27, 'price_check': 0.10, 'remove_from_cart': 0.03,
    },
    'loyal_customer': {
        'view': 0.14, 'click': 0.18, 'add_to_cart': 0.22, 'purchase': 0.27,
        'search': 0.08, 'review_read': 0.04, 'price_check': 0.04, 'remove_from_cart': 0.03,
    },
    'price_sensitive': {
        'view': 0.18, 'click': 0.14, 'add_to_cart': 0.12, 'purchase': 0.05,
        'search': 0.14, 'review_read': 0.05, 'price_check': 0.27, 'remove_from_cart': 0.05,
    },
    'window_shopper': {
        'view': 0.38, 'click': 0.24, 'add_to_cart': 0.12, 'purchase': 0.02,
        'search': 0.12, 'review_read': 0.07, 'price_check': 0.03, 'remove_from_cart': 0.02,
    },
    'brand_loyal': {
        'view': 0.10, 'click': 0.20, 'add_to_cart': 0.18, 'purchase': 0.25,
        'search': 0.05, 'review_read': 0.12, 'price_check': 0.05, 'remove_from_cart': 0.05,
    },
    'deal_hunter': {
        'view': 0.15, 'click': 0.18, 'add_to_cart': 0.20, 'purchase': 0.12,
        'search': 0.18, 'review_read': 0.05, 'price_check': 0.10, 'remove_from_cart': 0.02,
    },
    'gift_buyer': {
        'view': 0.20, 'click': 0.15, 'add_to_cart': 0.15, 'purchase': 0.18,
        'search': 0.14, 'review_read': 0.12, 'price_check': 0.04, 'remove_from_cart': 0.02,
    },
}

# ── Device: mobile / desktop / tablet ─────────────────────────
# Impulse & window_shopper dùng mobile nhiều hơn
# Researcher & gift_buyer dùng desktop nhiều hơn
SEGMENT_DEVICE_WEIGHTS = {
    'impulse_buyer':  {'mobile': 0.62, 'desktop': 0.28, 'tablet': 0.10},
    'researcher':     {'mobile': 0.20, 'desktop': 0.70, 'tablet': 0.10},
    'loyal_customer': {'mobile': 0.42, 'desktop': 0.42, 'tablet': 0.16},
    'price_sensitive':{'mobile': 0.50, 'desktop': 0.40, 'tablet': 0.10},
    'window_shopper': {'mobile': 0.65, 'desktop': 0.25, 'tablet': 0.10},
    'brand_loyal':    {'mobile': 0.45, 'desktop': 0.45, 'tablet': 0.10},
    'deal_hunter':    {'mobile': 0.55, 'desktop': 0.35, 'tablet': 0.10},
    'gift_buyer':     {'mobile': 0.35, 'desktop': 0.55, 'tablet': 0.10},
}

# ── Referrer: nguồn traffic ────────────────────────────────────
# direct / organic_search / paid_search / social / email / recommendation
REFERRERS = ['direct', 'organic_search', 'paid_search', 'social', 'email', 'recommendation']
SEGMENT_REFERRER_WEIGHTS = {
    # social + recommendation → impulse buy
    'impulse_buyer':  [0.12, 0.10, 0.10, 0.40, 0.05, 0.23],
    # organic search → research phase
    'researcher':     [0.10, 0.52, 0.13, 0.10, 0.05, 0.10],
    # direct → already knows the site
    'loyal_customer': [0.52, 0.15, 0.05, 0.10, 0.10, 0.08],
    # search engine + email deals
    'price_sensitive':[0.10, 0.33, 0.22, 0.10, 0.15, 0.10],
    # social media browsing
    'window_shopper': [0.10, 0.15, 0.05, 0.52, 0.05, 0.13],
    # direct / brand bookmark
    'brand_loyal':    [0.42, 0.20, 0.05, 0.15, 0.10, 0.08],
    # email promotions, deals
    'deal_hunter':    [0.10, 0.20, 0.10, 0.15, 0.37, 0.08],
    # search + recommendation
    'gift_buyer':     [0.18, 0.30, 0.10, 0.15, 0.15, 0.12],
}

# ── Duration (seconds) theo action — (mean, std) ──────────────
ACTION_DURATION = {
    'view':              (55,  30),
    'click':             (8,   4),
    'add_to_cart':       (12,  6),
    'purchase':          (120, 50),   # checkout flow
    'search':            (18,  8),
    'review_read':       (150, 70),   # đọc review lâu nhất
    'price_check':       (25,  12),
    'remove_from_cart':  (8,   4),
}

# Hệ số nhân duration theo segment (researcher đọc lâu hơn, impulse_buyer nhanh hơn)
SEGMENT_DURATION_MULTIPLIER = {
    'impulse_buyer':  0.65,
    'researcher':     1.55,
    'loyal_customer': 0.90,
    'price_sensitive':1.20,
    'window_shopper': 1.30,
    'brand_loyal':    0.95,
    'deal_hunter':    1.05,
    'gift_buyer':     1.15,
}

# ── Scroll depth (%) — chỉ có nghĩa với view & review_read ────
# Researcher và window_shopper cuộn nhiều hơn
SEGMENT_SCROLL_MEAN = {
    'impulse_buyer':  35,
    'researcher':     78,
    'loyal_customer': 55,
    'price_sensitive':52,
    'window_shopper': 70,
    'brand_loyal':    58,
    'deal_hunter':    50,
    'gift_buyer':     65,
}

# ── Product catalog ────────────────────────────────────────────
# Khớp với 52 sản phẩm trong product-service:
#   1–28  : sách
#   29–38 : thời trang
#   39–52 : điện tử & khác
PRODUCT_IDS = list(range(1, 53))

def _product_category(pid: int) -> str:
    if pid <= 28:
        return 'book'
    if pid <= 38:
        return 'clothes'
    return 'electronics'

# Giá theo category (VND) — (min, max)
CATEGORY_PRICE_RANGE = {
    'book':        (79_000,    450_000),
    'clothes':     (350_000, 5_500_000),
    'electronics': (299_000, 18_000_000),
}

# ── Coupon: chỉ áp dụng cho purchase ──────────────────────────
SEGMENT_COUPON_PROB = {
    'impulse_buyer':  0.06,
    'researcher':     0.08,
    'loyal_customer': 0.12,
    'price_sensitive':0.42,
    'window_shopper': 0.04,
    'brand_loyal':    0.10,
    'deal_hunter':    0.52,
    'gift_buyer':     0.15,
}

# ── Quantity (add_to_cart / purchase) ─────────────────────────
SEGMENT_QUANTITY_WEIGHTS = {
    'impulse_buyer':  [0.70, 0.22, 0.08],   # mostly 1
    'researcher':     [0.80, 0.15, 0.05],
    'loyal_customer': [0.60, 0.30, 0.10],
    'price_sensitive':[0.75, 0.20, 0.05],
    'window_shopper': [0.85, 0.12, 0.03],
    'brand_loyal':    [0.65, 0.25, 0.10],
    'deal_hunter':    [0.55, 0.30, 0.15],   # mua nhiều khi có deal
    'gift_buyer':     [0.45, 0.38, 0.17],   # mua cho nhiều người
}

# ── Phân phối segment ─────────────────────────────────────────
SEGMENTS = list(SEGMENT_ACTION_PROBS.keys())
SEGMENT_WEIGHTS = [0.15, 0.15, 0.15, 0.15, 0.12, 0.12, 0.08, 0.08]


# ─────────────────────────────────────────────────────────────
def _pick(mapping: dict, segment: str) -> str:
    keys = list(mapping[segment].keys())
    wts  = list(mapping[segment].values())
    return random.choices(keys, weights=wts)[0]


def _duration(action: str, segment: str) -> int:
    mean, std = ACTION_DURATION[action]
    multiplier = SEGMENT_DURATION_MULTIPLIER[segment]
    val = np.random.normal(mean * multiplier, std)
    return max(1, int(val))


def _scroll(action: str, segment: str) -> int:
    if action not in ('view', 'review_read'):
        return 0
    mean  = SEGMENT_SCROLL_MEAN[segment]
    # review_read → cuộn nhiều hơn view
    boost = 15 if action == 'review_read' else 0
    val   = np.random.normal(mean + boost, 12)
    return int(np.clip(val, 5, 100))


def _price(product_id: int) -> int:
    cat = _product_category(product_id)
    lo, hi = CATEGORY_PRICE_RANGE[cat]
    # Giá có bậc thang (không random đều)
    raw = np.random.lognormal(
        mean=np.log((lo + hi) / 2),
        sigma=0.35,
    )
    return int(np.clip(raw, lo, hi) // 1000 * 1000)   # làm tròn nghìn đồng


def _quantity(action: str, segment: str) -> int:
    if action not in ('add_to_cart', 'purchase'):
        return 0
    weights = SEGMENT_QUANTITY_WEIGHTS[segment]
    return random.choices([1, 2, 3], weights=weights)[0]


def _coupon(action: str, segment: str) -> bool:
    if action != 'purchase':
        return False
    return random.random() < SEGMENT_COUPON_PROB[segment]


# ─────────────────────────────────────────────────────────────
def generate_user_events(user_id: str, segment: str) -> list[dict]:
    """
    Sinh chuỗi sự kiện có thuộc tính đầy đủ cho 1 user.
    Mỗi user có 2–5 sessions, mỗi session 3–8 actions.
    """
    probs = SEGMENT_ACTION_PROBS[segment]
    acts  = list(probs.keys())
    wts   = list(probs.values())

    # Giờ vào phụ thuộc segment:
    # impulse_buyer & window_shopper → tối (19-23h)
    # researcher & gift_buyer → giờ hành chính (9-18h)
    if segment in ('impulse_buyer', 'window_shopper'):
        hour_range = (19, 23)
    elif segment in ('researcher', 'gift_buyer'):
        hour_range = (9, 18)
    else:
        hour_range = (8, 22)

    base_time = datetime(2024, 1, 1) + timedelta(
        days=random.randint(0, 364),
        hours=random.randint(*hour_range),
        minutes=random.randint(0, 59),
    )

    n_sessions = random.randint(2, 5)
    session_starts = sorted([
        base_time + timedelta(days=random.randint(0, 45))
        for _ in range(n_sessions)
    ])

    # Chọn device & referrer 1 lần / user (nhất quán trong session)
    device_keys   = list(SEGMENT_DEVICE_WEIGHTS[segment].keys())
    device_vals   = list(SEGMENT_DEVICE_WEIGHTS[segment].values())
    user_device   = random.choices(device_keys, weights=device_vals)[0]

    rows = []
    for s_idx, s_start in enumerate(session_starts):
        n_actions      = random.randint(3, 8)
        focus_products = random.sample(PRODUCT_IDS, k=min(4, len(PRODUCT_IDS)))
        current_time   = s_start

        # Referrer có thể thay đổi giữa sessions
        referrer = random.choices(
            REFERRERS,
            weights=SEGMENT_REFERRER_WEIGHTS[segment],
        )[0]

        for _ in range(n_actions):
            action = random.choices(acts, weights=wts)[0]
            product_id = (
                random.choice(focus_products)
                if random.random() < 0.7
                else random.choice(PRODUCT_IDS)
            )

            dur      = _duration(action, segment)
            scroll   = _scroll(action, segment)
            price    = _price(product_id)
            qty      = _quantity(action, segment)
            coupon   = _coupon(action, segment)

            rows.append({
                'user_id':          user_id,
                'product_id':       product_id,
                'product_category': _product_category(product_id),
                'action':           action,
                'timestamp':        current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'session_id':       f"sess_{user_id}_{s_idx + 1}",
                'segment':          segment,
                'device':           user_device,
                'referrer':         referrer,
                'duration_seconds': dur,
                'scroll_depth':     scroll,
                'price':            price,
                'quantity':         qty,
                'coupon_used':      coupon,
            })
            current_time += timedelta(seconds=dur + random.randint(10, 120))

    return rows


# ─────────────────────────────────────────────────────────────
def generate_dataset(n_users: int = 500, output_path: str = 'data/data_user500.csv') -> pd.DataFrame:
    """Sinh toàn bộ event-level dataset và xuất ra CSV."""
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)

    records = []
    for i in range(1, n_users + 1):
        user_id = f"user_{i:03d}"
        segment = random.choices(SEGMENTS, weights=SEGMENT_WEIGHTS)[0]
        records.extend(generate_user_events(user_id, segment))

    df = pd.DataFrame(records).sort_values('timestamp').reset_index(drop=True)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    return df


# ─────────────────────────────────────────────────────────────
def to_session_features(df: pd.DataFrame) -> tuple:
    """
    BƯỚC CẦU NỐI: Event logs → Session features cho BiLSTM.

    Aggregation map (10 features, khớp với NUM_FEATURES trong data_pipeline.py):
      click_count       = count(action == 'click')
      view_count        = count(action == 'view')
      purchase_count    = count(action == 'purchase')
      time_on_page      = sum(duration_seconds) / 60  [phút]
      cart_add_count    = count(action == 'add_to_cart')
      search_count      = count(action == 'search')
      session_duration  = (max_time - min_time).seconds / 60
      avg_price_viewed  = mean(price) khi action == 'view'
      category_diversity = nunique(product_id) / total_products
      return_rate       = count(remove_from_cart) / max(1, count(add_to_cart))

    Returns: X (n_users, n_sessions, 10), y (n_users,)
    """
    from module1_behavior.data_pipeline import BEHAVIOR_LABELS, NUM_SESSIONS, NUM_FEATURES

    label_map = {v: k for k, v in BEHAVIOR_LABELS.items()}
    users     = df['user_id'].unique()
    X_list, y_list = [], []

    for uid in users:
        udf     = df[df['user_id'] == uid]
        segment = udf['segment'].iloc[0]
        label   = label_map.get(segment, 0)

        sessions_feats = []
        for _, sdf in udf.groupby('session_id'):
            acts  = sdf['action'].tolist()
            t_min = pd.to_datetime(sdf['timestamp']).min()
            t_max = pd.to_datetime(sdf['timestamp']).max()
            dur   = (t_max - t_min).seconds / 60.0

            n_add = acts.count('add_to_cart')
            n_rm  = acts.count('remove_from_cart')

            view_prices = sdf.loc[sdf['action'] == 'view', 'price']
            avg_price   = float(view_prices.mean()) if len(view_prices) > 0 else 0.0

            time_on_page = sdf['duration_seconds'].sum() / 60.0

            feat = [
                acts.count('click'),
                acts.count('view'),
                acts.count('purchase'),
                time_on_page,
                n_add,
                acts.count('search'),
                max(dur, 1.0),
                avg_price / 1_000_000,          # chuẩn hoá về đơn vị triệu VNĐ
                sdf['product_id'].nunique() / len(PRODUCT_IDS),
                n_rm / max(1, n_add),
            ]
            sessions_feats.append(feat)

        if len(sessions_feats) < NUM_SESSIONS:
            pad = [[0.0] * NUM_FEATURES] * (NUM_SESSIONS - len(sessions_feats))
            sessions_feats = pad + sessions_feats
        else:
            sessions_feats = sessions_feats[:NUM_SESSIONS]

        X_list.append(sessions_feats)
        y_list.append(label)

    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.int64)


# ── CHẠY STANDALONE ───────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("  BƯỚC 1: Sinh event-level dataset (14 cột)")
    print("=" * 65)

    df = generate_dataset(n_users=500, output_path='data/data_user500.csv')

    print(f"\n  Tổng rows          : {len(df):,}")
    print(f"  Số users           : {df['user_id'].nunique()}")
    print(f"  Số loại action     : {df['action'].nunique()} → {sorted(df['action'].unique())}")
    print(f"  Số products        : {df['product_id'].nunique()}")
    print(f"  Cột                : {list(df.columns)}")

    print(f"\n  Phân bố segment:")
    for seg, cnt in df.groupby('segment')['user_id'].nunique().items():
        print(f"    {seg:<20}: {cnt} users")

    print(f"\n  Phân bố device:")
    for dev, cnt in df['device'].value_counts().items():
        print(f"    {dev:<12}: {cnt:>5} events ({cnt/len(df)*100:.1f}%)")

    print(f"\n  Phân bố referrer:")
    for ref, cnt in df['referrer'].value_counts().items():
        print(f"    {ref:<20}: {cnt:>5} events ({cnt/len(df)*100:.1f}%)")

    print(f"\n  Phân bố action:")
    for act, cnt in df['action'].value_counts().items():
        print(f"    {act:<20}: {cnt:>5} ({cnt/len(df)*100:.1f}%)")

    print(f"\n  Thống kê duration_seconds:")
    print(f"    mean={df['duration_seconds'].mean():.1f}s  "
          f"median={df['duration_seconds'].median():.1f}s  "
          f"max={df['duration_seconds'].max()}s")

    print(f"\n  Giá trung bình theo category:")
    for cat, grp in df[df['action'] == 'view'].groupby('product_category')['price']:
        print(f"    {cat:<12}: {grp.mean():>12,.0f} VNĐ")

    print(f"\n  Tỷ lệ dùng coupon (khi purchase): "
          f"{df[df['action']=='purchase']['coupon_used'].mean()*100:.1f}%")

    print(f"\n  5 dòng đầu:")
    print(df.head(5).to_string(index=False))
    print(f"\n  Đã lưu: data/data_user500.csv")

    print("\n" + "=" * 65)
    print("  BƯỚC CẦU NỐI: Event logs → Session features")
    print("=" * 65)
    X, y = to_session_features(df)
    print(f"  X shape: {X.shape}  (users, sessions, features)")
    print(f"  y shape: {y.shape}")
    print(f"  avg_price feature mean: {X[:,:,7].mean():.4f} (triệu VNĐ)")
    print(f"  Sẵn sàng đưa vào data_pipeline.py → BiLSTM training")
