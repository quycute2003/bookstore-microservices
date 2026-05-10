# Chương 3: AI Service cho tư vấn sản phẩm

## 3.1 Mục tiêu

Xây dựng hệ thống AI gợi ý sản phẩm dựa trên:

- Hành vi người dùng (click, search, add_to_cart, purchase, view, review_read, price_check)
- Quan hệ sản phẩm (similarity, category, author/brand)
- Ngữ cảnh truy vấn (chatbot tư vấn tự nhiên tiếng Việt)

**Output:**
- Danh sách sản phẩm đề xuất cá nhân hóa (homepage + listing)
- Chatbot tư vấn sản phẩm bằng tiếng Việt

---

## 3.2 Kiến trúc AI Service

AI Service được thiết kế như một microservice độc lập chạy tại cổng `8020` bằng **FastAPI**:

- **Input:** hành vi người dùng (session features), câu hỏi tự nhiên
- **Processing:**
  - BiLSTM phân loại nhóm hành vi (8 nhóm)
  - Knowledge Graph (Neo4j) ghi nhận tương tác và gợi ý
  - RAG Pipeline: Hybrid Search (FAISS + BM25) → Cross-Encoder → Gemini LLM
- **Output:** danh sách sản phẩm đề xuất / câu trả lời chatbot

```
Người dùng duyệt web
    │ click, view, search, add_to_cart (real-time)
    ▼
[API Gateway — /track/ endpoint]
    │ tích lũy session features + ghi vào Neo4j graph
    ├──► POST /interact  →  (:User)-[:VIEWED/:ADDED_TO_CART/:PURCHASED]→(:Product)
    ▼
[Module 1 — BiLSTM + Attention]
    │ → phân loại 8 nhóm khách hàng (behavior_label)
    ▼
[API Gateway — /recommendations/]
    ├── Tầng 1: GET /recommend (graph traversal + collaborative filtering)
    ├── Tầng 2: content-based (loại SP đã xem gần nhất)
    └── Tầng 3: behavior sort theo behavior_label
    ▼
Homepage "Gợi Ý Riêng Cho Bạn" + Listing cá nhân hóa
────────────────────────────────────────────────────────
Luồng chatbot song song:

Câu hỏi người dùng
    ▼
[Module 2] Hybrid Search: FAISS (vector) + BM25 (keyword) → RRF merge
    ▼
[Module 3] Cross-Encoder Reranker → top-3 documents
    ▼
[Gemini 2.5 Flash] system prompt cá nhân hóa theo behavior_label
    ▼
Câu trả lời tiếng Việt thuần văn bản
```

---

## 3.3 Thu thập dữ liệu

### 3.3.1 User Behavior Data

Dữ liệu được sinh bằng `module1_behavior/generate_data.py`. Mỗi event log gồm **14 cột**:

| Cột | Ý nghĩa | Ví dụ |
|-----|---------|-------|
| `user_id` | Mã người dùng | `user_042` |
| `product_id` | Mã sản phẩm (1–52) | `23` |
| `product_category` | Danh mục | `book` / `clothes` / `electronics` |
| `action` | Hành động | `view`, `click`, `add_to_cart`, `purchase`, `search`, `review_read`, `price_check`, `remove_from_cart` |
| `timestamp` | Thời điểm | `2024-03-12 10:05:00` |
| `session_id` | Mã phiên | `sess_user_042_2` |
| `segment` | Nhóm khách hàng | `researcher` |
| `device` | Thiết bị | `mobile` / `desktop` / `tablet` |
| `referrer` | Nguồn traffic | `social` / `email` / `organic_search` / `direct` |
| `duration_seconds` | Thời gian action (giây) | `147` |
| `scroll_depth` | Độ cuộn trang (%) | `72` |
| `price` | Giá sản phẩm (VNĐ) | `285000` |
| `quantity` | Số lượng | `2` |
| `coupon_used` | Có dùng coupon | `True` |

> **So với yêu cầu cơ bản** (4 cột: user_id, product_id, action, timestamp): nhóm bổ sung thêm 10 cột phản ánh ngữ cảnh thực tế (thiết bị, nguồn traffic, giá, thời gian) để dữ liệu huấn luyện gần với hành vi người dùng thật hơn.

### 3.3.2 Ví dụ dataset

**File:** `module1_behavior/generate_data.py` — dòng 56–211 (phân phối xác suất theo segment), dòng 263–355 (sinh event)

```python
# generate_data.py — dòng 56–76: xác suất action theo từng nhóm khách hàng
SEGMENT_ACTION_PROBS = {
    'impulse_buyer': {
        'view': 0.12, 'click': 0.22, 'add_to_cart': 0.26, 'purchase': 0.22,
        'search': 0.06, 'review_read': 0.03, 'price_check': 0.03, 'remove_from_cart': 0.06,
    },
    'researcher': {
        'view': 0.18, 'click': 0.14, 'add_to_cart': 0.08, 'purchase': 0.04,
        'search': 0.16, 'review_read': 0.27, 'price_check': 0.10, 'remove_from_cart': 0.03,
    },
    # ... 6 nhóm còn lại
}
```

```python
# generate_data.py — dòng 347–356: sinh dataset 500 users → CSV
def generate_dataset(n_users=500, output_path='data/data_user500.csv'):
    records = []
    for i in range(1, n_users + 1):
        user_id = f"user_{i:03d}"
        segment = random.choices(SEGMENTS, weights=SEGMENT_WEIGHTS)[0]
        records.extend(generate_user_events(user_id, segment))
    df = pd.DataFrame(records).sort_values('timestamp').reset_index(drop=True)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    return df
```

> **Điểm thêm so với yêu cầu:** mỗi nhóm có phân phối xác suất riêng (không random đều), device và referrer cũng có trọng số theo nhóm (ví dụ: `impulse_buyer` → 62% mobile, 40% từ social media; `researcher` → 70% desktop, 52% từ organic search).

---

## 3.4 Mô hình LSTM (Sequence Modeling)

### 3.4.1 Ý tưởng

Thay vì dự đoán sản phẩm tiếp theo, nhóm sử dụng LSTM để **phân loại nhóm hành vi khách hàng** từ chuỗi session — từ đó cá nhân hóa giao diện và chatbot theo từng nhóm. Input là chuỗi session features (không phải chuỗi sản phẩm đơn lẻ), giúp mô hình học được pattern dài hạn của người dùng.

### 3.4.2 Model chi tiết

Nhóm so sánh 3 kiến trúc trong `module1_behavior/compare_models.py`. Model tốt nhất là **BiLSTM + Attention Pooling**:

**File:** `module1_behavior/compare_models.py` — dòng 179–252

```python
# compare_models.py — dòng 179–252: BiLSTM + Attention Pooling
class BiLSTMModel(nn.Module):
    def __init__(self, input_dim=10, hidden_dim=128, num_layers=2,
                 num_classes=8, dropout=0.5):
        super().__init__()
        # Feature projection
        self.proj = nn.Sequential(
            nn.Linear(input_dim, 64), nn.BatchNorm1d(64),
            nn.ReLU(), nn.Dropout(dropout),
        )
        # Bidirectional LSTM — học cả forward và backward context
        self.lstm = nn.LSTM(64, hidden_dim, num_layers=num_layers,
                            batch_first=True, bidirectional=True,
                            dropout=dropout if num_layers > 1 else 0)
        # Attention Pooling — học session nào quan trọng hơn
        self.attn = nn.Linear(hidden_dim * 2, 1)
        self.norm = nn.LayerNorm(hidden_dim * 2)
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim), nn.GELU(),
            nn.Dropout(dropout), nn.Dropout(dropout / 2),
            nn.Linear(hidden_dim, num_classes),
        )

    def forward(self, x):
        B, T, F = x.shape
        x = self.proj(x.reshape(B * T, F)).reshape(B, T, -1)
        out, _ = self.lstm(x)                         # (B, T, 256)
        score = torch.softmax(self.attn(out), dim=1)  # (B, T, 1)
        pooled = (score * out).sum(dim=1)             # (B, 256)
        return self.classifier(self.norm(pooled))
```

**Model production** dùng trong API (`module1_behavior/model_behavior.py` dòng 35–120): kiến trúc tương tự nhưng thêm Multi-Head Self-Attention (4 heads) và trả thêm **behavior embedding 128-dim** làm context cho RAG.

> **So với yêu cầu cơ bản** (LSTM 1 layer, hidden=64, output=100 sản phẩm): nhóm dùng BiLSTM 2 layers + Attention Pooling, output 8 nhóm hành vi thay vì next-product. Lý do: phân loại nhóm hành vi cho phép cá nhân hóa toàn bộ trải nghiệm (listing, homepage, chatbot prompt) thay vì chỉ gợi ý 1 sản phẩm kế tiếp.

### 3.4.3 Training

**File:** `module1_behavior/compare_models.py` — dòng 257–340

```python
# compare_models.py — dòng 257–310: training loop với AMP + early stopping
def train_one_model(model, train_loader, val_loader, cfg, epochs=80, device="cpu"):
    criterion = nn.CrossEntropyLoss(label_smoothing=cfg["label_smoothing"])
    optimizer = optim.Adam(model.parameters(),
                           lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-5)
    scaler = torch.cuda.amp.GradScaler(enabled=(device == "cuda"))

    best_f1, patience_count = 0.0, 0
    for epoch in range(epochs):
        model.train()
        for X_b, y_b in train_loader:
            X_b, y_b = X_b.to(device), y_b.to(device)
            optimizer.zero_grad()
            with torch.cuda.amp.autocast(enabled=(device == "cuda")):
                logits = model(X_b)
                loss = criterion(logits, y_b)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
        scheduler.step()
        # Early stopping theo val F1 (patience=20)
        ...
```

> **So với yêu cầu cơ bản** (CrossEntropyLoss + Adam đơn giản): nhóm thêm Mixed Precision AMP (~2× nhanh khi có GPU), CosineAnnealing LR, Gradient Clipping, Early Stopping patience=20, và Label Smoothing 0.1 cho BiLSTM. Ngoài ra mỗi model có dropout/lr/weight_decay khác nhau thay vì uniform config.

---

## 3.5 Knowledge Graph với Neo4j

### 3.5.1 Mô hình đồ thị

**File:** `module0_graph/graph_schema.py` — dòng 8–32

```python
# graph_schema.py — dòng 8–32
class NodeType:
    BOOK      = "Book"
    CLOTHES   = "Clothes"
    PRODUCT   = "Product"   # electronics, furniture, ...
    AUTHOR    = "Author"
    BRAND     = "Brand"
    CATEGORY  = "Category"
    USER      = "User"      # node người dùng thực

class EdgeType:
    # Knowledge edges
    WRITTEN_BY    = "WRITTEN_BY"    # Book → Author
    IN_CATEGORY   = "IN_CATEGORY"   # Product → Category
    MADE_BY       = "MADE_BY"       # Clothes → Brand
    SIMILAR       = "SIMILAR"       # Product → Product
    # User interaction edges (trọng số theo mức độ tương tác)
    VIEWED        = "VIEWED"        # User → Product  (weight=1)
    ADDED_TO_CART = "ADDED_TO_CART" # User → Product  (weight=3)
    PURCHASED     = "PURCHASED"     # User → Product  (weight=5)
```

> **So với yêu cầu cơ bản** (Node: User, Product; Edge: BUY, VIEW, SIMILAR): nhóm bổ sung thêm node Author, Brand, Category, Clothes để phục vụ Knowledge Graph cho chatbot. Edge tương tác có **weight** (1/3/5) và thuộc tính `count` + `last_seen` để ghi nhận tần suất thay vì chỉ có/không.

### 3.5.2 Ví dụ Cypher — ghi nhận tương tác

**File:** `module0_graph/user_interaction.py` — dòng 127–136

```python
# user_interaction.py — dòng 127–136: MERGE User + Product + interaction edge
s.run(f"""
    MERGE (u:User {{id: $uid}})
    MERGE (p:Product {{id: $pid}})
      ON CREATE SET p.type = $ptype, p.name = $pname
      ON MATCH  SET p.name = CASE WHEN $pname <> '' THEN $pname ELSE p.name END
    MERGE (u)-[r:{edge_type}]->(p)
      ON CREATE SET r.weight = $w, r.count = 1,        r.last_seen = $ts
      ON MATCH  SET r.count  = r.count + 1, r.last_seen = $ts
""", uid=user_id, pid=product_id, ptype=product_type,
     pname=product_name, w=weight, ts=int(time.time()))
```

> `MERGE` thay vì `CREATE` để không tạo trùng — mỗi lần user xem lại sản phẩm thì `count` tăng lên, không tạo edge mới.

### 3.5.3 Truy vấn gợi ý

**File:** `module0_graph/user_interaction.py` — dòng 160–185

```python
# user_interaction.py — dòng 160–185: 2 bước gợi ý
# Bước 1: lịch sử trực tiếp
MATCH (u:User {id: $uid})-[r]->(p:Product)
RETURN p.id, type(r) AS rel, r.weight, r.count

# Bước 2: collaborative filtering 1-hop
MATCH (u:User {id: $uid})-[r1]->(p1:Product)<-[r2]-(u2:User)-[r3]->(p2:Product)
WHERE u2.id <> $uid AND NOT p2.id IN $seen
RETURN p2.id, sum(r1.weight * r3.weight) AS collab_score
ORDER BY collab_score DESC LIMIT 50
```

> **So với yêu cầu cơ bản** (MATCH đơn giản 1 hop): nhóm thêm **collaborative filtering** — tìm user2 có hành vi tương tự, lấy sản phẩm của user2 chưa từng thấy. Score cuối = `(direct_score + 0.5 × collab_score) × behavior_boost`.

---

## 3.6 RAG (Retrieval-Augmented Generation)

### 3.6.1 Pipeline

**File:** `module3_rag/rag_pipeline.py`

```
Câu hỏi người dùng
    ▼ [1] Mở rộng query (brand alias: "LV" → "Louis Vuitton LV")
    ▼ [2] Hybrid Retrieve
          FAISS vector search top-20 + BM25 keyword search top-20
          → RRF merge → top-10 unified
    ▼ [3] Cross-Encoder Rerank
          mmarco-mMiniLMv2-L12-H384-v1 score từng cặp (query, doc)
          → top-3 docs
    ▼ [4] Build context + behavior profile
    ▼ [5] Gemini 2.5 Flash sinh câu trả lời tiếng Việt
```

### 3.6.2 Vector Database — Hybrid Search với RRF

**File:** `module2_knowledge/kb_builder.py` — dòng 336–357

```python
# kb_builder.py — dòng 336–357: Hybrid FAISS + BM25 với RRF
def hybrid_search(self, query: str, top_k=10, alpha=0.7):
    expanded_query = expand_query(query)           # brand alias expansion
    vec_results  = self.search_vector(expanded_query, top_k=top_k * 2)  # FAISS
    bm25_results = self.search_bm25(expanded_query, top_k=top_k * 2)    # BM25

    # Reciprocal Rank Fusion (k=60, Robertson et al. 2009)
    rrf = {}
    k = 60
    for rank, (doc, _) in enumerate(vec_results):
        rrf[doc.doc_id] = rrf.get(doc.doc_id, 0) + alpha / (k + rank + 1)
    for rank, (doc, _) in enumerate(bm25_results):
        rrf[doc.doc_id] = rrf.get(doc.doc_id, 0) + (1 - alpha) / (k + rank + 1)

    sorted_ids = sorted(rrf, key=rrf.get, reverse=True)[:top_k]
    return [(doc_map[did], rrf[did]) for did in sorted_ids if did in doc_map]
```

> **So với yêu cầu cơ bản** (FAISS hoặc ChromaDB): nhóm kết hợp cả hai — FAISS tốt với ngữ nghĩa/đồng nghĩa, BM25 tốt với tên riêng/mã sản phẩm. RRF merge không cần normalize score khác scale.

### 3.6.3 Cross-Encoder Reranker

**File:** `module3_rag/rag_pipeline.py` — dòng 31–47

```python
# rag_pipeline.py — dòng 31–47: rerank bằng cross-encoder đa ngôn ngữ
class CrossEncoderReranker:
    def __init__(self):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")

    def rerank(self, query, documents, top_k=5):
        pairs = [(query, doc.content) for doc in documents]
        scores = self.model.predict(pairs)
        ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in ranked[:top_k]]
```

> **So với yêu cầu cơ bản** (chỉ retrieve rồi generate): nhóm thêm bước rerank bằng cross-encoder. Bi-encoder (embedding) encode query và doc độc lập nên kém chính xác hơn; cross-encoder encode cả cặp (query, doc) cùng lúc → self-attention thấy toàn bộ tương tác → chính xác hơn đáng kể ở bước cuối.

---

## 3.7 Kết hợp Hybrid Model

Ba thành phần được tích hợp trong `api-gateway/api_gateway/views.py` (hàm `recommendations_view`):

```
final_score = graph_score × behavior_boost        (Tầng 1 — Neo4j)
            + content_boost (viewed_types)         (Tầng 2 — Content-based)
            + behavior_sort (behavior_label)       (Tầng 3 — LSTM)
```

| Thành phần | Đóng góp | File |
|-----------|----------|------|
| **BiLSTM** | Phân loại behavior_label → điều chỉnh thứ tự hiển thị và system prompt chatbot | `module1_behavior/compare_models.py` |
| **Graph (Neo4j)** | Sản phẩm từ lịch sử tương tác + collaborative filtering lên đầu | `module0_graph/user_interaction.py` |
| **RAG** | Câu trả lời chatbot từ knowledge base, cá nhân hóa theo behavior | `module3_rag/rag_pipeline.py` |

---

## 3.8 Hai dạng AI Service

### 3.8.1 Recommendation List

**Use cases:** khi load homepage, khi xem listing

**File:** `module4_api/main.py` — dòng 656–700

```python
# main.py — dòng 656–700
@app.get("/recommend")
async def graph_recommend(
    user_id: str = Query(...),
    top_k: int = Query(default=10, ge=1, le=50),
    behavior_label: str = Query(default="window_shopper"),
    exclude_purchased: bool = Query(default=True),
    api_key: str = Depends(verify_api_key),
):
    graph = get_user_interaction_graph()
    recs  = graph.get_recommendations(
        user_id=user_id,
        behavior_label=behavior_label,
        top_k=top_k,
        exclude_purchased=exclude_purchased,
    )
    return {"user_id": user_id, "recommendations": recs, "count": len(recs)}
```

**Ghi nhận tương tác — File:** `module4_api/main.py` — dòng 625–653

```python
# main.py — dòng 625–653
@app.post("/interact")
async def log_interaction(req: InteractRequest, api_key: str = Depends(verify_api_key)):
    # action → edge type: view=VIEWED(w=1), add_to_cart=ADDED_TO_CART(w=3), purchase=PURCHASED(w=5)
    stored = graph.log_action(
        user_id=req.user_id, product_id=req.product_id,
        action=req.action, product_type=req.product_type,
    )
    return {"status": "ok", "stored": stored}
```

**Output ví dụ:**
```json
{
  "user_id": "user_42",
  "behavior_label": "researcher",
  "recommendations": [
    {"product_id": "book_15", "score": 4.32},
    {"product_id": "electronics_40", "score": 2.18}
  ],
  "count": 2,
  "source": "graph"
}
```

### 3.8.2 Chatbot tư vấn

**Input:** `"tôi cần laptop gaming giá rẻ"`

**Pipeline:** NLP query expansion → Hybrid Retrieve → Cross-Encoder Rerank → Gemini sinh trả lời cá nhân hóa theo behavior_label

**File:** `module4_api/main.py` — dòng 305–321

```python
# main.py — dòng 305–321
@app.post("/chat")
async def chat(req: ChatRequest, api_key: str = Depends(verify_api_key)):
    chatbot = get_chatbot()
    result  = chatbot.chat(req.user_id, req.message)
    return result
```

**Output ví dụ** (behavior_label = `price_sensitive`):
```
"Bạn có thể tham khảo Laptop ASUS VivoBook 15 giá 12.990.000đ —
cấu hình Core i5 Gen 12, RAM 8GB phù hợp học tập và làm việc.
Hiện có combo với túi chống sốc giảm thêm 500.000đ."
```

---

## 3.9 Triển khai AI Service

### 3.9.1 Tech stack

| Thành phần | Công nghệ | Ghi chú |
|-----------|-----------|---------|
| Deep Learning | PyTorch — BiLSTM + Attention | So sánh RNN / LSTM / BiLSTM |
| GPU Training | Mixed Precision AMP | `autocast` + `GradScaler` (~2× nhanh) |
| Data Augmentation | 4 kỹ thuật | Gaussian noise, masking, jitter, scaling |
| Embedding | MiniLM-L12-v2 multilingual | 384-dim, hỗ trợ tiếng Việt |
| Vector Search | FAISS (L2 index) | |
| Keyword Search | BM25Okapi (rank_bm25) | |
| Hybrid Fusion | RRF k=60 | Robertson et al. 2009 |
| Reranker | cross-encoder/mmarco-mMiniLMv2 | 117MB, 100+ ngôn ngữ |
| LLM | Google Gemini 2.5 Flash | google-genai SDK |
| Graph Database | Neo4j 5 Community | bolt://neo4j:7687 |
| API Framework | FastAPI | Port 8020 |
| Behavior Tracking | Django Session + /track/ AJAX | Real-time, non-blocking |

### 3.9.2 Kiến trúc triển khai

- AI Service chạy độc lập trong Docker container (`ai-behavior-service`)
- Giao tiếp với API Gateway qua REST (xác thực bằng `X-API-Key`)
- API Gateway tự động inject key khi proxy sang AI Service (`api-gateway/api_gateway/views.py` dòng 479)
- Neo4j chạy container riêng, kết nối qua bolt protocol
- Model files lưu tại volume `/app/models/` (persist qua restart)

---

## 3.10 Kết luận

- BiLSTM + Attention phân loại hành vi tốt hơn LSTM/RNN nhờ temporal patterns trong dữ liệu và bidirectional context
- Knowledge Graph ghi nhận lịch sử tương tác thực giúp gợi ý chính xác hơn content-based đơn thuần
- Hybrid Search (FAISS + BM25 + RRF) + Cross-Encoder Reranker cho chatbot hiểu cả ngữ nghĩa lẫn từ khóa chính xác
- Hệ thống có **graceful degradation**: Neo4j offline → fallback content-based; model chưa train → fallback random sort
- Phù hợp hệ e-commerce đa danh mục hiện đại với khả năng cá nhân hóa thực sự từ hành vi người dùng
