# ================================================================
#  AI Behavior Service — Dockerfile
#  Install thứ tự QUAN TRỌNG cho PyTorch Geometric (CPU-only):
#    1. torch (base)
#    2. torch-scatter
#    3. torch-sparse
#    4. torch-geometric
#  Dùng pre-built CPU wheels từ data.pyg.org để tránh compile C++.
# ================================================================

FROM python:3.11-slim

# --- System dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ----------------------------------------------------------------
# BƯỚC 1: Cài torch TRƯỚC (phải có trước khi cài PyG extensions)
# ----------------------------------------------------------------
RUN pip install --no-cache-dir \
    "torch==2.2.2+cpu" \
    "torchvision==0.17.2+cpu" \
    --index-url https://download.pytorch.org/whl/cpu

# ----------------------------------------------------------------
# BƯỚC 2: Cài torch-scatter và torch-sparse từ PyG wheel servers
#         phải match đúng torch version (torch-2.2.2+cpu → cp311-cpu)
# ----------------------------------------------------------------
RUN pip install --no-cache-dir \
    torch-scatter \
    torch-sparse \
    --find-links https://data.pyg.org/whl/torch-2.2.2+cpu.html

# ----------------------------------------------------------------
# BƯỚC 3: Cài torch-geometric (sau khi scatter + sparse đã có)
# ----------------------------------------------------------------
RUN pip install --no-cache-dir \
    torch-geometric \
    --find-links https://data.pyg.org/whl/torch-2.2.2+cpu.html

# ----------------------------------------------------------------
# BƯỚC 4: Cài các dependencies còn lại (numpy, fastapi, ...)
#         Copy requirements KHÔNG chứa torch/pyg (đã cài ở trên)
# ----------------------------------------------------------------
COPY requirements-base.txt .
RUN pip install --no-cache-dir -r requirements-base.txt

# --- Copy source code ---
COPY . .

# --- Tạo thư mục models ---
RUN mkdir -p models

# --- Expose port ---
EXPOSE 8020

# ----------------------------------------------------------------
# STARTUP:
#   - GNN train tự động ở background nếu chưa có weights
#   - API bắt đầu ngay (models load lazy khi request đầu tiên)
# ----------------------------------------------------------------
CMD ["python", "-m", "uvicorn", "module4_api.main:app", \
     "--host", "0.0.0.0", "--port", "8020", "--workers", "1"]
