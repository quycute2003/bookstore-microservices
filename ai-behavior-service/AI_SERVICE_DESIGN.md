# MỤC 2: THIẾT KẾ VÀ TRIỂN KHAI AI SERVICE

## 2.1. Tổng quan kiến trúc AI Service

AI Service (`ai-behavior-service`) là thành phần trí tuệ nhân tạo của hệ thống LUMIÈRE — nền tảng thương mại điện tử đa danh mục (sách, thời trang, điện tử, mỹ phẩm, đồ chơi, túi xách, giày, đồng hồ, quà tặng, văn phòng phẩm). Service được triển khai như một microservice độc lập sử dụng **FastAPI** (Python 3.11), chạy tại cổng `8020`.

Service tích hợp bốn module chính:

| Module | Tệp | Vai trò |
|--------|-----|---------|
| Module 1: Phân tích hành vi | `module1_behavior/` | Phân loại nhóm khách hàng bằng BiLSTM |
| Module 2: Knowledge Base | `module2_knowledge/` | Xây dựng và index kho tri thức sản phẩm |
| Module 3: RAG Pipeline | `module3_rag/` | Truy xuất – xếp hạng lại – sinh câu trả lời |
| Module 4: API | `module4_api/` | Giao tiếp REST, chat widget, xác thực |

**Luồng dữ liệu tổng quát:**

```
Người dùng duyệt web
    │ hành vi thực (click, view, search, add_to_cart)
    ▼
[API Gateway — Django Session]
    │ tích lũy behavior features qua /track/ (AJAX real-time)
    ▼
[Module 1] BiLSTM + Multi-Head Attention
    │ → phân loại 8 nhóm khách hàng
    │ → behavior_label + behavior_embedding (128-dim)
    ▼
[API Gateway /recommendations/]
    │ Tầng 1: content-based (viewed_types — loại SP đã xem gần nhất)
    │ Tầng 2: behavior-based sort (theo behavior_label)
    ▼
Homepage "Gợi Ý Riêng Cho Bạn" + Listing được cá nhân hóa
─────────────────────────────────────────────────────────────────
Luồng song song — Knowledge Graph:

[Product Service] ──────────────────────────────────────────────┐
    │ book, clothes, electronics, cosmetic, watch...             │
    ▼                                                            │
[Module 2] Knowledge Base                                        │
    │ chunk + embed (MiniLM-L12 384-dim) → FAISS index          │
    │ tokenize → BM25Okapi index                                 ▼
    │                                              [Neo4j Graph Database]
    │                                               Nodes: Book, Author,
    │                                               Brand, Category,
    │                                               User, UserSession,
    │                                               BehaviorType, Scenario
    │                                               Relationships:
    │                                               WRITTEN_BY, MADE_BY,
    │                                               IN_CATEGORY, SIMILAR_TO,
    │                                               HAD_SESSION, HAS_BEHAVIOR
    │                                                            │
    ▼                                                            │
[Module 3] RAG Pipeline ←────────────── Graph Retriever ────────┘
    │ FAISS top-10 + BM25 top-10
    │ → RRF (k=60) → unified top-10
    │ + Graph traversal (SIMILAR_TO, BELONGS_TO)
    ▼
[Cross-Encoder Reranker]
    │ mmarco-mMiniLMv2-L12-H384-v1 → top-3 docs
    ▼
[Gemini 2.5 Flash]
    │ system prompt cá nhân hóa theo behavior_label
    ▼
Chat Widget — câu trả lời thuần văn bản tiếng Việt
```

---

## 2.2. Module 1 – Phân tích hành vi khách hàng

### 2.2.1. Dữ liệu huấn luyện (`data_pipeline.py`)

Nhóm sinh bộ dữ liệu tổng hợp **500 người dùng** (`data/data_user500.csv`). Mỗi user có **10 sessions**, mỗi session có **10 features** tổng hợp từ hành vi thực tế.

**10 features mỗi session:**

| Feature | Ý nghĩa |
|---------|---------|
| `click_count` | Số lần click |
| `view_count` | Số lần xem sản phẩm |
| `purchase_count` | Số lần mua |
| `time_on_page` | Thời gian trên trang (phút) |
| `cart_add_count` | Số lần thêm vào giỏ |
| `search_count` | Số lần tìm kiếm |
| `session_duration` | Thời lượng phiên (phút) |
| `avg_price_viewed` | Giá trung bình sản phẩm đã xem (nghìn VNĐ) |
| `category_diversity` | Mức độ đa dạng danh mục (0–1) |
| `return_rate` | Tỉ lệ đổi trả (0–1) |

**8 nhóm khách hàng (8 classes):**

| ID | Nhóm | Đặc trưng hành vi |
|----|------|-------------------|
| 0 | `impulse_buyer` | Mua nhanh ở session đầu, return_rate tăng dần |
| 1 | `researcher` | Search nhiều → giảm, cart_add tăng, purchase chỉ cuối |
| 2 | `loyal_customer` | Purchase tăng đều qua sessions, duration dài hơn dần |
| 3 | `price_sensitive` | Mua ở session giữa (khi tìm được giá tốt) |
| 4 | `window_shopper` | View tăng dần, purchase gần bằng 0 |
| 5 | `brand_loyal` | Variance giảm qua sessions, price ổn định cao |
| 6 | `deal_hunter` | Burst mạnh ở 3 sale-sessions cố định, im lặng còn lại |
| 7 | `gift_buyer` | Search giảm, price tăng, purchase chỉ xuất hiện cuối |

**Điểm quan trọng — Temporal Pattern:** Không giống các cách sinh data thông thường (sample độc lập từng session), bộ dữ liệu này thiết kế để mỗi nhóm có **progression rõ ràng theo thời gian** giữa các sessions. Điều này tạo ra temporal dependency thực sự, giúp LSTM/BiLSTM có lợi thế vượt trội so với RNN.

Ví dụ `researcher`: session đầu search nhiều (search_count cao), session giữa bắt đầu add to cart, session cuối mới purchase. Đây chính xác là pattern mà BiLSTM có thể học được nhờ bidirectional context.

**Augmentation** (`AugmentedBehaviorDataset`) — áp dụng trên training để chống overfitting:

| Kỹ thuật | Tham số |
|---------|---------|
| Gaussian noise | σ = 0.08, cộng vào toàn bộ features |
| Feature masking | Mask ngẫu nhiên 12% features (set về 0) |
| Session jitter | Swap 2 session liền kề với xác suất 30% |
| Temporal scaling | Scale mỗi session × U(0.88, 1.12) |

---

### 2.2.2. So sánh ba kiến trúc (`compare_models.py`)

#### a) Kiến trúc ba mô hình

**Mô hình 1 – Vanilla RNN:**
```
Input(B, T=10, F=10)
→ Linear(10→64) + BatchNorm + ReLU + Dropout(0.20)
→ RNN(tanh, 2 layers, hidden=128)
→ Global Average Pooling (trung bình toàn bộ hidden states)
→ LayerNorm
→ Classifier: Linear(128→64) + ReLU + Dropout + Linear(64→8)
```

**Mô hình 2 – LSTM:**
```
Input(B, T=10, F=10)
→ Linear(10→64) + BatchNorm + ReLU + Dropout(0.30)
→ LSTM(2 layers, hidden=128, unidirectional)
→ Global Average Pooling
→ LayerNorm
→ Classifier: Linear(128→64) + GELU + Dropout + Linear(64→8)
```

**Mô hình 3 – BiLSTM + Attention Pooling:**
```
Input(B, T=10, F=10)
→ Linear(10→64) + BatchNorm + ReLU + Dropout(0.50)
→ BiLSTM(2 layers, hidden=128, bidirectional) → (B, T, 256)
→ Attention Pooling:
      score = softmax(tanh(Linear(256→1)))   → (B, T, 1)
      pooled = Σ score_t × h_t               → (B, 256)
→ LayerNorm
→ Classifier: Linear(256→128) + GELU + Dropout(0.50) + Dropout(0.25) + Linear(128→8)
```

#### b) Cấu hình per-model (chống overfitting)

Cấu hình khác nhau theo từng model thay vì dùng uniform — đây là điểm then chốt:

| Config | RNN | LSTM | BiLSTM |
|--------|-----|------|--------|
| Dropout | 0.20 | 0.30 | 0.50 |
| Learning rate | 1e-3 | 1e-3 | 5e-4 |
| Weight decay | 1e-4 | 1e-4 | 5e-4 |
| Label smoothing | 0.0 | 0.0 | 0.10 |
| Augmentation | ✓ | ✓ | ✓ |

**Lý do:** BiLSTM có nhiều tham số nhất (≈ 200K) trên dataset nhỏ (500 users) → cần regularization nặng hơn. RNN đơn giản nhất → regularization nhẹ để không underfitting.

#### c) Kỹ thuật training

- **Split 70/15/15**: Train / Validation / Test (cố định seed=42)
- **GPU Mixed Precision (AMP)**: `torch.cuda.amp.autocast` + `GradScaler` khi CUDA available (~2× nhanh hơn)
- **Cosine Annealing LR**: `CosineAnnealingLR(T_max=80, eta_min=1e-5)` thay StepLR
- **Early Stopping**: patience=20 epochs, restore best weights theo val F1
- **Selective augmentation**: tất cả model đều dùng augmented dataloader

#### d) Phát hiện và xử lý Overfitting

**Vấn đề ban đầu:** Dữ liệu synthetic không có temporal dependency (mỗi session sample độc lập) → RNN thắng BiLSTM vì ít tham số hơn, regularization nhẹ hơn.

**Giải pháp gốc rễ:** Thêm temporal progression vào data generator (xem 2.2.1) để BiLSTM có thực sự có gì để học từ thứ tự session.

**Theo dõi overfitting** (`check_overfitting()`):

| Mức Gap (val_loss − train_loss) | Đánh giá |
|----------------------------------|---------|
| < 0.15 | ✓ Tốt |
| 0.15 – 0.30 | ~ Chấp nhận |
| ≥ 0.30 | ✗ Overfit |

#### e) Kết quả thực nghiệm

5 biểu đồ được sinh tự động sau training:
1. **Training curves**: train_loss vs val_loss theo epoch (3 model)
2. **Metrics comparison**: Accuracy / F1 / AUC bar chart
3. **Confusion matrix**: per-class performance
4. **ROC curve**: One-vs-Rest AUC từng class
5. **Radar chart**: so sánh tổng thể 5 chỉ số

---

### 2.2.3. Model production (`model_behavior.py`)

Model được triển khai trong service là `BehaviorModel` — kiến trúc BiLSTM với Multi-Head Attention (khác so với Attention Pooling trong compare_models):

```
Input (B, T=10, F=10)
    │
    ▼  Feature Projection
    │  Linear(10→64) + BatchNorm + ReLU + Dropout(0.3)
    │  → (B, T, 64)
    ▼  Bi-LSTM (2 layers, hidden=128, bidirectional)
    │  → (B, T, 256)
    ▼  Multi-Head Self-Attention (4 heads, 256-dim) + Residual + LayerNorm
    │  → (B, T, 256)
    ▼  Global Average Pooling
    │  → (B, 256)
    ▼  Behavior Embedding Head
    │  Linear(256→128) + ReLU + Dropout
    │  → (B, 128)  ← BEHAVIOR EMBEDDING (dùng làm context trong RAG)
    ▼  Classifier
    │  Linear(128→64) + ReLU + Dropout + Linear(64→8)
    │  → (B, 8)   ← LOGITS (phân loại 8 nhóm)
```

**Behavior Embedding (128-dim)** được trả về cùng với prediction, phục vụ làm context bổ sung khi chatbot cần cá nhân hóa câu trả lời.

---

## 2.3. Module 2 – Knowledge Base (`module2_knowledge/kb_builder.py`)

### 2.3.1. Kiến trúc Hybrid Search

Knowledge Base được xây dựng từ các file JSON trong `knowledge_base/` (sản phẩm, danh mục, thương hiệu, scenarios). Hỗ trợ **Hybrid Search**: kết hợp vector search và keyword search.

```
Tài liệu JSON
    │ load + chunk (CHUNK_SIZE=500 chars, CHUNK_OVERLAP=50)
    ▼
[Embedding] sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (384-dim)
    │
    ├──► FAISS Index (L2) — lưu vào models/faiss_index
    └──► BM25Okapi Index — lưu vào models/bm25_index.pkl
```

**Embedding model:** `paraphrase-multilingual-MiniLM-L12-v2` — hỗ trợ tiếng Việt, 384 chiều, nhẹ (~120MB).

### 2.3.2. Query Expansion — Brand Aliases

Xử lý alias thương hiệu trước khi search để tránh miss do viết tắt:

```python
BRAND_ALIASES = {
    "Louis Vuitton": ["LV"],
    "Yves Saint Laurent": ["YSL", "Saint Laurent"],
    "Christian Dior": ["Dior", "CD"],
    ...
}
```

Khi người dùng hỏi "túi LV", query được mở rộng thành "Louis Vuitton LV" trước khi embedding và BM25 search.

### 2.3.3. Hybrid Search với RRF

Kết hợp FAISS và BM25 bằng **Reciprocal Rank Fusion (RRF)**:

$$\text{RRF\_score}(d) = \sum_{i \in \{faiss, bm25\}} \frac{1}{60 + \text{rank}_i(d)}$$

k = 60 là hằng số chuẩn (Robertson et al., 2009). Score càng cao → document càng relevant. Hai danh sách được merge và sort theo RRF score trước khi đưa vào reranker.

| Phương pháp | Mạnh với | Yếu với |
|-------------|----------|---------|
| FAISS (vector) | Ngữ nghĩa, đồng nghĩa | Tên riêng, mã sản phẩm |
| BM25 (keyword) | Từ khóa chính xác, tên sản phẩm | Đồng nghĩa, ngữ cảnh |
| **RRF** | **Coverage tốt nhất cả hai** | — |

---

## 2.4. Module 3 – RAG Pipeline (`module3_rag/rag_pipeline.py`)

### 2.4.1. Kiến trúc tổng thể

```
Query người dùng
    │
    ▼ [1] Hybrid Retrieve
    │   FAISS top-10 + BM25 top-10 → RRF → top-10 unified
    │
    ▼ [2] Graph Retriever (optional, nếu module0_graph available)
    │   Neo4j: traverse SIMILAR_TO, BELONGS_TO từ entity được nhắc
    │
    ▼ [3] Cross-Encoder Reranker
    │   Model: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
    │   Score từng cặp (query, doc) → sort → top-3
    │
    ▼ [4] Augment Context với Behavior Profile
    │   Thêm behavior_label + confidence vào system prompt
    │
    ▼ [5] Gemini 2.5 Flash Generate
         System prompt cá nhân hóa → câu trả lời thuần văn bản tiếng Việt
```

### 2.4.2. Cross-Encoder Reranker

**Tại sao cần reranker sau hybrid search?**

Bi-encoder (embedding model) encode query và document độc lập → nhanh nhưng thiếu cross-attention. Cross-encoder encode cặp (query, doc) cùng lúc → BERT self-attention thấy toàn bộ tương tác → chính xác hơn đáng kể, phù hợp cho bước rerank (chỉ chạy trên top-k nhỏ).

Model `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (~117MB) được huấn luyện trên MS MARCO đa ngôn ngữ, hỗ trợ tiếng Việt tốt.

### 2.4.3. Cá nhân hóa câu trả lời theo hành vi

System prompt gửi đến Gemini được điều chỉnh theo `behavior_label`:

```
impulse_buyer   → nhanh gọn, highlight khuyến mãi, tạo urgency
researcher      → chi tiết, so sánh specs, dẫn review
loyal_customer  → ấm áp, nhắc lại lịch sử, đề xuất loyalty
price_sensitive → nhấn mạnh giá trị/km/combo tiết kiệm
window_shopper  → tạo FOMO, limited stock
brand_loyal     → nhấn mạnh thương hiệu quen thuộc
deal_hunter     → highlight flash sale, bundle deals
gift_buyer      → gợi ý quà tặng cao cấp, packaging, gift wrap
```

### 2.4.4. Quy tắc phản hồi Gemini

- Không dùng Markdown (**, ##, *) — plain text hoàn toàn
- Tiếng Việt, giọng thanh lịch đẳng cấp
- Ưu tiên thông tin từ context truy xuất được
- Không bịa giá, tên sản phẩm
- Nhận biết brand alias: LV = Louis Vuitton, YSL = Yves Saint Laurent, Dior = Christian Dior

---

## 2.5. Module 4 – API Service (`module4_api/main.py`)

### 2.5.1. FastAPI Endpoints

| Endpoint | Method | Auth | Vai trò |
|----------|--------|------|---------|
| `/health` | GET | Không | Health check + component status |
| `/analyze-behavior` | POST | API Key | Nhận session data → behavior label + embedding |
| `/chat` | POST | API Key | Gửi message → RAG → câu trả lời |
| `/user/{user_id}/profile` | GET | API Key | Lấy behavior profile đã cache |
| `/feedback` | POST | API Key | Thu thập feedback người dùng |
| `/clear-session/{user_id}` | POST | API Key | Xóa conversation history |
| `/gnn/status` | GET | Không | Kiểm tra GNN model |
| `/gnn/train` | POST | API Key | Trigger GNN training (background) |
| `/gnn/product/{id}/similar` | GET | API Key | Top-K sản phẩm tương tự |

### 2.5.2. Xác thực

API Key được xác thực qua header `X-API-Key`. Default key: `bookstore-ai-secret-key-2024` (cấu hình qua env `API_KEY`).

API Gateway tự động inject key khi proxy tới ai-behavior-service:
```python
# api-gateway/views.py — universal_proxy
if service_name == 'ai-behavior':
    headers['X-API-Key'] = AI_BEHAVIOR_KEY
```

### 2.5.3. Lazy Loading & Startup

Model được load lazy (lần đầu có request) để tránh timeout. Tại startup, LSTM model được warm-up:

```python
@asynccontextmanager
async def lifespan(app):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, get_behavior_model)  # warm-up LSTM
    yield
```

---

## 2.6. Tích hợp vào E-commerce (API Gateway)

### 2.6.1. Thu thập hành vi từ session thực

**Django session** tích lũy hành vi người dùng qua mỗi request:

```
_update_behavior(request, action, product)
    │
    ├── 'view'     → view_count++, click_count++, cập nhật avg_price, category_diversity
    ├── 'search'   → search_count++
    ├── 'cart_add' → cart_add_count++
    └── 'purchase' → purchase_count++
    
    Đồng thời lưu:
    - _prices[]        → tính avg_price_viewed
    - _cats[]          → tính category_diversity  
    - _viewed_types[]  → content-based boosting (LRU, tối đa 10)
```

### 2.6.2. Endpoint `/track/` (AJAX từ frontend)

Frontend gọi `/track/` khi:
- User click sản phẩm trên listing/homepage
- User thêm vào giỏ hàng
- User tìm kiếm (Enter trong search bar)

```javascript
// listing.html — track function
const _actionMap = {
    'product_click': 'view',
    'add_to_cart':   'cart_add',
    'search':        'search',
};
fetch('/track/', { method: 'POST', body: JSON.stringify({action, product}) });
```

### 2.6.3. Cá nhân hóa listing (`/listing/`)

Thay vì random shuffle, sản phẩm được sắp xếp theo behavior label:

| Behavior Label | Thứ tự sắp xếp |
|----------------|----------------|
| `price_sensitive`, `deal_hunter` | Giá tăng dần |
| `researcher` | Sách lên đầu, loại khác theo sau |
| `gift_buyer` | Giá giảm dần (premium trước) |
| `brand_loyal` | Nhóm theo brand, rồi theo type |
| Còn lại | Random shuffle |

### 2.6.4. Cá nhân hóa homepage (`/recommendations/`)

Section "Gợi Ý Riêng Cho Bạn" trên homepage gọi `/recommendations/` — kết hợp hai tầng:

**Tầng 1 — Content-based (viewed_types):**
- Sản phẩm cùng loại với 3 loại đã xem gần nhất được ưu tiên lên đầu
- Ví dụ: xem electronics → electronics lên trước

**Tầng 2 — Behavior-based (behavior_label):**
- Trong mỗi nhóm (đã xem / chưa xem), áp dụng behavior sort

```python
if viewed_types:
    recent  = set(viewed_types[-3:])
    primary   = _sort_by_behavior([p for p in products if p['type'] in recent], label)
    secondary = _sort_by_behavior([p for p in products if p['type'] not in recent], label)
    result = primary + secondary
```

**Cập nhật reason text theo behavior:**

| Label | Text hiển thị |
|-------|--------------|
| `impulse_buyer` | "Gợi ý hot dành riêng cho bạn!" |
| `researcher` | "Sách bạn có thể muốn đọc tiếp" |
| `price_sensitive` | "Giá tốt nhất hôm nay cho bạn" |
| `gift_buyer` | "Quà tặng cao cấp cho người thân" |
| _(chưa đủ data)_ | "Gợi ý hôm nay dành riêng cho bạn!" |

### 2.6.5. Tìm kiếm từ homepage

Search bar trên homepage redirect tới `/listing/?q=<query>`. Listing page:
1. Đọc `?q=` từ URL params khi load
2. Track search behavior → `/track/`
3. Filter products theo tên, tác giả, brand, type_label
4. Search bar inline hỗ trợ real-time filtering

---

## 2.7. Knowledge Graph với Neo4j

Neo4j được tích hợp làm graph database cho knowledge base và product relationships. Graph hiện có **2.095 nodes** và **2.224 relationships** (theo Neo4j Browser).

**Node labels:**
`Author`, `BehaviorType`, `Book`, `Brand`, `Category`, `Clothes`, `Scenario`, `User`, `UserSession`

**Relationship types:**
`HAD_SESSION`, `HAS_BEHAVIOR`, `IN_CATEGORY`, `MADE_BY`, `SAME_AUTHOR`, `SIMILAR`, `SIMILAR_TO`, `WRITTEN_BY`

---

## 2.8. Tóm tắt công nghệ sử dụng

| Thành phần | Công nghệ | Chi tiết |
|-----------|-----------|---------|
| Deep Learning | PyTorch | BiLSTM + Multi-Head Attention |
| Model so sánh | RNN / LSTM / BiLSTM | 3 kiến trúc, per-model config |
| GPU Training | Mixed Precision AMP | autocast + GradScaler |
| Early Stopping | Patience=20 | Restore best val F1 |
| Data Augmentation | 4 kỹ thuật | Noise, masking, jitter, scaling |
| Embedding Model | MiniLM-L12-v2 multilingual | 384-dim, hỗ trợ tiếng Việt |
| Vector Search | FAISS | L2 index |
| Keyword Search | BM25Okapi (rank_bm25) | Tokenize regex |
| Hybrid Fusion | RRF (k=60) | Kết hợp FAISS + BM25 |
| Reranker | cross-encoder/mmarco-mMiniLMv2 | Cross-Encoder đa ngôn ngữ |
| LLM | Google Gemini 2.5 Flash | google-genai SDK |
| Graph Database | Neo4j 5 Community | bolt://neo4j:7687 |
| API Framework | FastAPI | Port 8020 |
| Session Store | Django Session (PostgreSQL) | Behavior accumulation |
| Behavior Tracking | Django + /track/ AJAX | Real-time, non-blocking |
| Cá nhân hóa | 2 tầng: content + behavior | viewed_types + behavior_label |
