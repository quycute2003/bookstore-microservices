"""
================================================================
  MODULE 4 — FastAPI REST API  (v2.0 — with GNN endpoints)
================================================================
Endpoints:
  POST /analyze-behavior            — Phân tích hành vi → behavior profile + GNN embedding
  POST /chat                        — Chatbot RAG tư vấn (cá nhân hóa theo behavior)
  GET  /user/{user_id}/profile      — Lấy behavior profile đã lưu
  POST /feedback                    — Thu thập feedback
  GET  /health                      — Health check (bao gồm GNN status)

  [GNN endpoints — Phase 5]
  GET  /gnn/status                  — Kiểm tra GNN model đã sẵn sàng chưa
  POST /gnn/train                   — Trigger GNN training pipeline (admin)
  GET  /gnn/product/{id}/embedding  — GNN embedding của 1 product node
  GET  /gnn/product/{id}/similar    — Top-K sản phẩm tương tự (cosine sim)
  POST /gnn/user/embedding          — Lấy embedding cho user (cold-start aware)

  POST /clear-session/{user_id}     — Xóa session chat

Chạy standalone:
  cd ai-behavior-service
  uvicorn module4_api.main:app --host 0.0.0.0 --port 8020 --reload
"""

import os
import json
import time
import asyncio
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

load_dotenv()

# =============================================
# PYDANTIC MODELS (Request / Response)
# =============================================
class SessionData(BaseModel):
    click_count: int = 0
    view_count: int = 0
    purchase_count: int = 0
    time_on_page: float = 0.0
    cart_add_count: int = 0
    search_count: int = 0
    session_duration: float = 0.0
    avg_price_viewed: float = 0.0
    category_diversity: float = 0.0
    return_rate: float = 0.0


class AnalyzeBehaviorRequest(BaseModel):
    user_id: str
    sessions: List[SessionData] = Field(..., min_length=1)


class ChatRequest(BaseModel):
    user_id: str
    message: str


class FeedbackRequest(BaseModel):
    user_id: str
    message_id: Optional[str] = None
    rating: int  # 1-5
    comment: Optional[str] = None

    @field_validator("rating")
    @classmethod
    def check_rating(cls, v):
        if not 1 <= v <= 5:
            raise ValueError("Rating phải từ 1 đến 5")
        return v


class UserEmbeddingRequest(BaseModel):
    user_id: str
    sessions: Optional[List[SessionData]] = None


class GNNTrainRequest(BaseModel):
    epochs: int = Field(default=80, ge=10, le=500)
    hidden_channels: int = Field(default=128, ge=32, le=512)
    embedding_dim: int = Field(default=64, ge=16, le=256)
    force_rebuild_dataset: bool = False


# =============================================
# GLOBAL COMPONENTS (lazy load, thread-safe)
# =============================================
_components: Dict[str, Any] = {}
_gnn_training_status: Dict[str, Any] = {
    "is_training": False,
    "last_started_at": None,
    "last_finished_at": None,
    "last_error": None,
}


def get_behavior_model():
    """Lazy load LSTM behavior model (Module 1)."""
    if "model" not in _components:
        try:
            from module1_behavior.model_behavior import load_model
            model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
            if os.path.exists(os.path.join(model_path, "behavior_model.pth")):
                model, scaler = load_model(model_path)
                _components["model"] = model
                _components["scaler"] = scaler
                print("✅ LSTM Behavior model loaded!")
            else:
                print("🔄 LSTM model chưa có, đang train...")
                from module1_behavior.model_behavior import BehaviorModel, train_model, save_model
                from module1_behavior.data_pipeline import create_dataloaders
                train_loader, test_loader, scaler = create_dataloaders()
                model = BehaviorModel()
                model = train_model(model, train_loader, test_loader, epochs=30)
                save_model(model, scaler, model_path)
                _components["model"] = model
                _components["scaler"] = scaler
        except Exception as e:
            print(f"⚠️ Không load được LSTM model: {e}")
            _components["model"] = None
            _components["scaler"] = None

    return _components.get("model"), _components.get("scaler")


def get_chatbot():
    """Lazy load chatbot (Module 3 RAG)."""
    if "chatbot" not in _components:
        try:
            from module3_rag.chatbot import Chatbot
            _components["chatbot"] = Chatbot()
            print("✅ Chatbot loaded!")
        except Exception as e:
            print(f"⚠️ Không load được chatbot: {e}")
            _components["chatbot"] = None
    return _components.get("chatbot")


def get_cold_start_router():
    """Lazy load ColdStartRouter (Phase 3 — GNN + LSTM routing)."""
    if "cold_start_router" not in _components:
        try:
            from module0_graph.cold_start import ColdStartRouter
            router = ColdStartRouter()
            _components["cold_start_router"] = router
            print("✅ ColdStartRouter loaded!")
        except ImportError:
            # torch_geometric chưa install → GNN không available
            print("⚠️ torch_geometric chưa install → ColdStartRouter unavailable")
            _components["cold_start_router"] = None
        except Exception as e:
            print(f"⚠️ ColdStartRouter load error: {e}")
            _components["cold_start_router"] = None
    return _components.get("cold_start_router")


# =============================================
# AUTH & RATE LIMITING
# =============================================
from module4_api.auth import verify_api_key
from module4_api.rate_limiter import setup_rate_limiter


# =============================================
# FASTAPI APP
# =============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: preload LSTM model (GNN load lazy khi có request)."""
    print("🚀 AI Behavior Service v2.0 starting...")
    # Warm-up LSTM model
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, get_behavior_model)
    print("🚀 Service ready!")
    yield
    print("👋 AI Behavior Service shutting down...")


app = FastAPI(
    title="AI Behavior Analysis Service",
    description=(
        "Phân tích hành vi khách hàng và tư vấn cá nhân hóa bằng AI.\n\n"
        "- **Module 1**: LSTM phân loại hành vi\n"
        "- **Module 0 (Phase 2)**: GNN GraphSAGE embeddings\n"
        "- **Module 0 (Phase 3)**: Cold start routing\n"
        "- **Module 3**: RAG Chatbot"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
setup_rate_limiter(app)


# =============================================
# HELPER: GNN STATUS CHECK
# =============================================
def _gnn_ready() -> bool:
    """Kiểm tra nhanh GNN model files có tồn tại không."""
    try:
        from module0_graph.gnn_trainer import is_gnn_trained
        return is_gnn_trained()
    except ImportError:
        return False


# =============================================
# ENDPOINTS — CORE
# =============================================

@app.get("/health", tags=["Core"])
async def health_check():
    """Kiểm tra trạng thái service (bao gồm GNN availability)."""
    gnn_ready = _gnn_ready()
    return {
        "status": "healthy",
        "service": "ai-behavior-service",
        "version": "2.0.0",
        "timestamp": time.time(),
        "components": {
            "lstm_model": _components.get("model") is not None,
            "chatbot": _components.get("chatbot") is not None,
            "gnn_model": gnn_ready,
            "cold_start_router": _components.get("cold_start_router") is not None,
        },
    }


@app.post("/analyze-behavior", tags=["Core"])
async def analyze_behavior(
    req: AnalyzeBehaviorRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Phân tích hành vi khách hàng từ session data.

    Trả về:
    - `behavior_profile`: LSTM classification (label, confidence, probabilities, embedding)
    - `gnn_embedding`: GNN product-space embedding (nếu GNN đã train)
    - `user_type`: warm | cold_lstm | cold_mean (cold start status)
    """
    model, scaler = get_behavior_model()
    if model is None:
        raise HTTPException(500, "LSTM model chưa sẵn sàng. Vui lòng thử lại sau.")

    try:
        from module1_behavior.model_behavior import predict_behavior
        session_dicts = [s.model_dump() for s in req.sessions]
        lstm_result = predict_behavior(model, session_dicts, scaler)

        # --- Cache profile vào chatbot + cold start router ---
        chatbot = get_chatbot()
        if chatbot:
            chatbot.set_behavior_profile(req.user_id, lstm_result)

        router = get_cold_start_router()
        if router:
            router.set_behavior_profile(req.user_id, lstm_result)

        # --- GNN embedding (Phase 5) ---
        gnn_info = None
        if router and _gnn_ready():
            try:
                routing_result = router.get_embedding(
                    req.user_id, session_data=session_dicts
                )
                gnn_info = {
                    "source": routing_result.get("source"),
                    "user_type": routing_result.get("user_type"),
                    "embedding_dim": len(routing_result.get("embedding", [])),
                    # Không trả embedding thô (quá lớn) — dùng /gnn/user/embedding nếu cần
                }
            except Exception as e:
                gnn_info = {"source": "unavailable", "error": str(e)}

        response = {
            "user_id": req.user_id,
            "behavior_profile": lstm_result,
        }
        if gnn_info:
            response["gnn_info"] = gnn_info

        return response

    except Exception as e:
        raise HTTPException(500, f"Lỗi phân tích: {str(e)}")


@app.post("/chat", tags=["Core"])
async def chat(req: ChatRequest, api_key: str = Depends(verify_api_key)):
    """
    Chat với AI tư vấn viên.
    Response được cá nhân hóa dựa trên behavior profile (nếu có).
    """
    chatbot = get_chatbot()
    if chatbot is None:
        raise HTTPException(500, "Chatbot chưa sẵn sàng. Vui lòng thử lại sau.")

    try:
        result = chatbot.chat(req.user_id, req.message)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Lỗi chat: {str(e)}")


@app.get("/user/{user_id}/profile", tags=["Core"])
async def get_user_profile(user_id: str, api_key: str = Depends(verify_api_key)):
    """Lấy behavior profile đã lưu của user."""
    chatbot = get_chatbot()
    if chatbot is None:
        raise HTTPException(500, "Service chưa sẵn sàng.")

    profile = chatbot.profile_cache.get(user_id)
    if profile is None:
        raise HTTPException(404, f"Không tìm thấy profile cho user '{user_id}'")

    return {"user_id": user_id, "behavior_profile": profile}


@app.post("/feedback", tags=["Core"])
async def submit_feedback(req: FeedbackRequest, api_key: str = Depends(verify_api_key)):
    """Thu thập feedback từ khách hàng để cải thiện model."""
    feedback = {
        "user_id": req.user_id,
        "message_id": req.message_id,
        "rating": req.rating,
        "comment": req.comment,
        "timestamp": time.time(),
    }
    print(f"📝 Feedback: user={req.user_id}, rating={req.rating}, comment={req.comment}")
    return {"status": "success", "message": "Cảm ơn bạn đã góp ý!", "feedback": feedback}


@app.post("/clear-session/{user_id}", tags=["Core"])
async def clear_session(user_id: str, api_key: str = Depends(verify_api_key)):
    """Xóa session chat của user."""
    chatbot = get_chatbot()
    if chatbot:
        chatbot.clear_session(user_id)
    return {"status": "success", "message": f"Đã xóa session của {user_id}"}


# =============================================
# ENDPOINTS — GNN (Phase 5)
# =============================================

@app.get("/gnn/status", tags=["GNN"])
async def gnn_status():
    """
    Kiểm tra trạng thái GNN model.
    Không yêu cầu API key để dễ health-check từ DevOps.
    """
    ready = _gnn_ready()
    status_info: Dict[str, Any] = {
        "gnn_ready": ready,
        "torch_geometric_available": False,
    }

    # Kiểm tra torch_geometric install
    try:
        import torch_geometric
        status_info["torch_geometric_available"] = True
        status_info["torch_geometric_version"] = torch_geometric.__version__
    except ImportError:
        pass

    # Thêm training status
    status_info["training_status"] = {
        "is_training": _gnn_training_status["is_training"],
        "last_started_at": _gnn_training_status["last_started_at"],
        "last_finished_at": _gnn_training_status["last_finished_at"],
        "last_error": _gnn_training_status["last_error"],
    }

    # Nếu GNN đã train, thêm metadata
    if ready:
        try:
            import json as _json
            models_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
            meta_path = os.path.join(models_dir, "gnn_metadata.json")
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = _json.load(f)
            status_info["model_metadata"] = {
                "node_types": meta.get("node_types", []),
                "node_counts": meta.get("node_counts", {}),
                "embedding_dim": meta.get("embedding_dim"),
                "total_parameters": meta.get("total_parameters"),
                "trained_at": meta.get("trained_at"),
            }
        except Exception:
            pass

    return status_info


@app.post("/gnn/train", tags=["GNN"])
async def trigger_gnn_training(
    req: GNNTrainRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key),
):
    """
    Trigger GNN training pipeline (chạy background, non-blocking).

    - Nếu đang train → trả về 409 Conflict
    - Training chạy async, kiểm tra status qua GET /gnn/status
    """
    if _gnn_training_status["is_training"]:
        raise HTTPException(409, "GNN đang được train. Vui lòng chờ hoàn tất.")

    def _run_training():
        _gnn_training_status["is_training"] = True
        _gnn_training_status["last_started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _gnn_training_status["last_error"] = None
        try:
            from module0_graph.gnn_trainer import train_and_save_gnn
            from module0_graph.gnn_dataset import DATASET_CACHE
            import os

            # Force rebuild dataset nếu yêu cầu
            if req.force_rebuild_dataset and os.path.exists(DATASET_CACHE):
                os.remove(DATASET_CACHE)
                print("[GNN Train] Dataset cache cleared")

            # Clear GNN cache trong component map để reload sau khi train
            _components.pop("cold_start_router", None)

            train_and_save_gnn(
                epochs=req.epochs,
                hidden_channels=req.hidden_channels,
                embedding_dim=req.embedding_dim,
            )
            _gnn_training_status["last_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            print("[GNN Train] ✅ Hoàn thành!")
        except Exception as e:
            _gnn_training_status["last_error"] = str(e)
            print(f"[GNN Train] ❌ Lỗi: {e}")
        finally:
            _gnn_training_status["is_training"] = False

    background_tasks.add_task(_run_training)

    return {
        "status": "started",
        "message": "GNN training đang chạy background. Poll GET /gnn/status để kiểm tra.",
        "config": req.model_dump(),
    }


@app.get("/gnn/product/{product_id}/embedding", tags=["GNN"])
async def get_product_embedding(
    product_id: str,
    api_key: str = Depends(verify_api_key),
):
    """
    Lấy GNN embedding vector của 1 product node.

    `product_id` format:
    - Sách: `book:1`, `book:42`
    - Quần áo: `clothes:3`, `clothes:10`
    """
    if not _gnn_ready():
        raise HTTPException(
            503,
            "GNN model chưa được train. Gọi POST /gnn/train trước hoặc chờ training hoàn tất.",
        )

    router = get_cold_start_router()
    if router is None:
        raise HTTPException(503, "ColdStartRouter không khởi động được (torch_geometric chưa install?)")

    result = router.get_product_embedding(product_id)
    if result is None:
        raise HTTPException(
            404,
            f"Không tìm thấy product '{product_id}'. "
            "Format: 'book:{{id}}' hoặc 'clothes:{{id}}'",
        )

    return {
        "product_id": result["product_id"],
        "node_type": result["node_type"],
        "embedding": result["embedding"],
        "embedding_dim": len(result["embedding"]),
    }


@app.get("/gnn/product/{product_id}/similar", tags=["GNN"])
async def get_similar_products(
    product_id: str,
    top_k: int = Query(default=5, ge=1, le=20),
    api_key: str = Depends(verify_api_key),
):
    """
    Tìm top-K sản phẩm tương tự dựa trên cosine similarity của GNN embeddings.

    Returns danh sách sản phẩm tương tự trong cùng node type (book với book, clothes với clothes).
    """
    if not _gnn_ready():
        raise HTTPException(
            503,
            "GNN model chưa được train. Gọi POST /gnn/train trước.",
        )

    router = get_cold_start_router()
    if router is None:
        raise HTTPException(503, "ColdStartRouter không khởi động được.")

    similar = router.get_similar_products(product_id, top_k=top_k)
    if not similar and not router.get_product_embedding(product_id):
        raise HTTPException(404, f"Không tìm thấy product '{product_id}'.")

    return {
        "source_product": product_id,
        "top_k": top_k,
        "similar_products": similar,
        "count": len(similar),
    }


@app.post("/gnn/user/embedding", tags=["GNN"])
async def get_user_embedding(
    req: UserEmbeddingRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Lấy embedding cho user — cold-start aware.

    Logic routing:
    - **warm** (đã có behavior profile) → dùng LSTM embedding từ cache
    - **cold_lstm** (chưa có profile, nhưng gửi sessions) → chạy LSTM inference
    - **cold_mean** (hoàn toàn mới, không có gì) → mean product embedding

    Response bao gồm `source` để client biết chất lượng embedding.
    """
    router = get_cold_start_router()

    if router is None:
        # Fallback nếu GNN không available: dùng LSTM trực tiếp
        if req.sessions:
            model, scaler = get_behavior_model()
            if model:
                from module1_behavior.model_behavior import predict_behavior
                session_dicts = [s.model_dump() for s in req.sessions]
                result = predict_behavior(model, session_dicts, scaler)
                return {
                    "user_id": req.user_id,
                    "source": "lstm_only",
                    "user_type": "cold_lstm",
                    "embedding": result["embedding"],
                    "embedding_dim": len(result["embedding"]),
                    "behavior_label": result["label"],
                    "confidence": result["confidence"],
                    "note": "GNN unavailable (torch_geometric not installed)",
                }
        raise HTTPException(503, "Embedding service không sẵn sàng.")

    session_dicts = [s.model_dump() for s in req.sessions] if req.sessions else None
    result = router.get_embedding(req.user_id, session_data=session_dicts)

    return {
        "user_id": req.user_id,
        "source": result["source"],
        "user_type": result["user_type"],
        "embedding": result["embedding"],
        "embedding_dim": len(result["embedding"]),
        "behavior_label": result.get("behavior_label", "unknown"),
        "confidence": result.get("confidence", 0.0),
    }


# =============================================
# CHẠY TRỰC TIẾP
# =============================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AI_SERVICE_PORT", "8020"))
    uvicorn.run("module4_api.main:app", host="0.0.0.0", port=port, reload=True)
