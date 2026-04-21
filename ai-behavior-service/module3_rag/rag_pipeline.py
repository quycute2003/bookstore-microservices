"""
================================================================
  MODULE 3 — RAG Pipeline: Retriever + Reranker + Generator
================================================================
Pipeline: Query → Hybrid Retrieve → Cross-Encoder Rerank
          → Augment (behavior profile) → Gemini Generate

Chạy standalone:
  cd ai-behavior-service
  python -m module3_rag.rag_pipeline
"""

import os
import json
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

# GraphRetriever — import lazy để không fail nếu module0_graph chưa sẵn sàng
try:
    from module0_graph import GraphRetriever as _GraphRetriever
    _GRAPH_AVAILABLE = True
except Exception:
    _GraphRetriever = None
    _GRAPH_AVAILABLE = False

# =============================================
# RERANKER (Cross-Encoder)
# =============================================
class CrossEncoderReranker:
    """Rerank kết quả retrieval bằng cross-encoder đa ngôn ngữ."""

    def __init__(self, model_name=None):
        from sentence_transformers import CrossEncoder
        # Fix C: dùng cross-encoder đa ngôn ngữ (hỗ trợ tiếng Việt)
        # Mặc định: mmarco-mMiniLMv2-L12-H384-v1 (~117MB, hỗ trợ 100+ ngôn ngữ)
        if model_name is None:
            model_name = os.getenv(
                "RERANKER_MODEL",
                "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
            )
        print(f"🔄 Loading reranker: {model_name}")
        self.model = CrossEncoder(model_name)
        print("✅ Reranker loaded!")

    def rerank(self, query: str, documents, top_k=5):
        """
        Rerank documents theo relevance score.
        Args:
            query: câu hỏi
            documents: list of (Document, score) từ retriever
            top_k: số kết quả trả về
        Returns: list of (Document, rerank_score)
        """
        if not documents:
            return []

        pairs = [(query, doc.content) for doc, _ in documents]
        scores = self.model.predict(pairs)

        # Ghép score mới với document
        scored = list(zip([d for d, _ in documents], scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored[:top_k]


# =============================================
# LLM GENERATOR (Google Gemini)
# =============================================
class GeminiGenerator:
    """Sinh câu trả lời bằng Google Gemini API."""

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY", "")
        self.model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2048"))

        if api_key and api_key != "your_gemini_api_key_here":
            from google import genai
            self.client = genai.Client(api_key=api_key)
            self.available = True
            print(f"✅ Gemini (genai SDK) ready: {self.model_name}")
        else:
            self.client = None
            self.available = False
            print("⚠️  Gemini API key chưa cấu hình → dùng mock response")

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Gọi Gemini API (bản google-genai SDK mới) hoặc trả mock response."""
        if not self.available:
            return self._mock_response(prompt)

        try:
            # Cấu trúc mới của google-genai SDK
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "system_instruction": system_prompt,
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                }
            )
            return self._clean_response(response.text)
        except Exception as e:
            print(f"⚠️ Gemini (genai SDK) error: {e}")
            return self._mock_response(prompt)

    def _clean_response(self, text: str) -> str:
        """Lọc bỏ các định dạng Markdown như **, __, #, v.v. để text sạch 100%."""
        import re
        # Xóa bold/italic (**text**, __text__, *text*, _text_)
        text = re.sub(r'(\*\*|__|\*|_)', '', text)
        # Xóa headers (# Header)
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
        # Xóa list markers (1. , - , * ) ở đầu dòng nếu muốn cực sạch,
        # nhưng thường giữ lại bullet points cũng ổn. Ở đây em xóa luôn cho "thuần"
        # text = re.sub(r'^\s*[-*+]\s+', '• ', text, flags=re.MULTILINE)
        return text.strip()

    def _mock_response(self, prompt: str) -> str:
        """Mock response khi chưa có API key."""
        return (
            "🤖 [Mock Response - Cần cấu hình GOOGLE_API_KEY]\n\n"
            "Xin chào! Tôi là trợ lý tư vấn AI của BookStore. "
            "Hiện tại tôi đang chạy ở chế độ demo. "
            "Để có câu trả lời thực, vui lòng thêm Gemini API key vào file .env.\n\n"
            f"Câu hỏi của bạn: {prompt[:200]}..."
        )


# =============================================
# RAG PIPELINE
# =============================================
class RAGPipeline:
    """
    Pipeline RAG hoàn chỉnh:
    1. Hybrid Retrieve (FAISS + BM25)
    2. Cross-Encoder Rerank
    3. Augment với behavior profile
    4. Generate bằng Gemini
    """

    def __init__(self, kb_builder=None, use_graph: bool = True):
        # Retriever (KB)
        if kb_builder is None:
            from module2_knowledge.kb_builder import KnowledgeBaseBuilder, INDEX_DIR
            self.kb = KnowledgeBaseBuilder()
            index_path = INDEX_DIR
            if os.path.exists(os.path.join(index_path, "faiss_index")):
                self.kb.load_index(index_path)
            else:
                print("⚠️ Chưa có index, đang build...")
                self.kb.build_index()
                self.kb.save_index(index_path)
        else:
            self.kb = kb_builder

        # Graph Retriever (Module 0)
        self.graph_retriever = None
        if use_graph and _GRAPH_AVAILABLE:
            try:
                self.graph_retriever = _GraphRetriever()
                print("✅ Graph Retriever (Module 0) ready!")
            except Exception as e:
                print(f"⚠️ Graph Retriever không khởi động được: {e}")

        # Reranker
        self.reranker = CrossEncoderReranker()

        # Generator
        self.generator = GeminiGenerator()

    def _build_system_prompt(self, behavior_profile: Optional[Dict] = None) -> str:
        """Tạo system prompt với behavior profile."""
        base = (
            "Bạn là trợ lý tư vấn AI của LUMIÈRE (BookStore & Fashion) — thương hiệu sách và thời trang luxury.\n"
            "QUY TẮC PHẢN HỒI (RẤT QUAN TRỌNG):\n"
            "1. KHÔNG sử dụng định dạng Markdown (như **, __, #, v.v.). Trả lời bằng VĂN BẢN THUẦN (Plain Text).\n"
            "2. Trả lời bằng tiếng Việt, giọng điệu thanh lịch, đẳng cấp và hiếu khách.\n"
            "3. ƯU TIÊN sử dụng thông tin trong Context bên dưới. Nếu Context có BẤT KỲ sản phẩm nào "
            "liên quan đến câu hỏi (cùng thương hiệu, cùng loại, cùng từ khoá), hãy LIỆT KÊ và GIỚI THIỆU chúng "
            "một cách nhiệt tình. Lưu ý: 'LV' = 'Louis Vuitton', 'YSL' = 'Yves Saint Laurent', "
            "'Dior' = 'Christian Dior' — coi như cùng một thương hiệu.\n"
            "4. CHỈ trả lời 'LUMIÈRE hiện chưa có thông tin về vấn đề này' khi Context HOÀN TOÀN KHÔNG "
            "nhắc tới chủ đề/thương hiệu/sản phẩm mà khách hỏi. Nếu có dù chỉ 1 sản phẩm liên quan, "
            "TUYỆT ĐỐI KHÔNG được dùng câu fallback này.\n"
            "5. KHÔNG BỊA thông tin sản phẩm, giá cả. Giá luôn đi kèm đơn vị VNĐ và format có dấu chấm ngàn.\n"
            "6. Gợi ý sản phẩm dựa trên hành vi khách hàng (nếu có thông tin).\n"
            "7. LUÔN LUÔN kết thúc câu phản hồi một cách trọn vẹn, không được dừng lại giữa chừng.\n"
        )

        if behavior_profile:
            label = behavior_profile.get("label", "unknown")
            confidence = behavior_profile.get("confidence", 0)

            # Load chiến lược tư vấn theo nhóm
            scenario_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "module2_knowledge", "knowledge_base", "scenarios", f"{label}.json"
            )
            strategy = ""
            if os.path.exists(scenario_path):
                with open(scenario_path, 'r', encoding='utf-8') as f:
                    scenario = json.load(f)
                    s = scenario.get("consultation_strategy", {})
                    strategy = (
                        f"\nChiến lược tư vấn cho nhóm này:\n"
                        f"- Tone: {s.get('tone', '')}\n"
                        f"- Approach: {s.get('approach', '')}\n"
                        f"- Tránh: {s.get('avoid', '')}\n"
                    )

            base += (
                f"\n--- THÔNG TIN KHÁCH HÀNG ---\n"
                f"Nhóm hành vi: {label} (độ tin cậy: {confidence:.0%})\n"
                f"{strategy}"
            )

        return base

    def _build_context(self, retrieved_docs) -> str:
        """Ghép nội dung documents thành context string.
        Phân biệt rõ nguồn Graph (multi-hop) vs Vector KB (FAISS+BM25).
        """
        context_parts = []
        for i, (doc, score) in enumerate(retrieved_docs):
            source = doc.metadata.get("source", "unknown")
            doc_type = doc.metadata.get("type", "")
            if doc_type == "graph":
                label = f"Graph KB [{doc.metadata.get('node_id', source)}]"
            else:
                label = f"Vector KB [{source}]"
            context_parts.append(f"[Nguồn {i+1}: {label}]\n{doc.content}")
        return "\n\n---\n\n".join(context_parts)

    def query(self, user_message: str, behavior_profile: Optional[Dict] = None,
              conversation_history: List[Dict] = None, top_k_retrieve=20,
              top_k_rerank=5) -> Dict:
        """
        Chạy RAG pipeline hoàn chỉnh.

        Args:
            user_message: câu hỏi của user
            behavior_profile: dict từ Module 1 (label, confidence, embedding...)
            conversation_history: list of {role, content}
            top_k_retrieve: số docs retrieve ban đầu
            top_k_rerank: số docs sau rerank

        Returns:
            dict: {answer, sources, behavior_label}
        """
        # 1. Retrieve — Hybrid (FAISS + BM25)
        retrieved = self.kb.hybrid_search(user_message, top_k=top_k_retrieve)

        # 1b. Graph Retrieval (Module 0) — merge trước khi rerank
        if self.graph_retriever is not None:
            try:
                graph_docs = self.graph_retriever.retrieve(user_message, top_k=8)
                # Merge: thêm graph docs chưa có trong retrieved (dedup by doc_id)
                # GraphDocument.doc_id = md5(content) — không trùng với vector KB
                # vì graph dùng prefix "[Graph]" trong content
                existing_ids = {d.doc_id for d, _ in retrieved}
                for gdoc, gscore in graph_docs:
                    if gdoc.doc_id not in existing_ids:
                        # Graph docs được boost nhẹ vì mang multi-hop context
                        retrieved.append((gdoc, gscore))
                        existing_ids.add(gdoc.doc_id)
            except Exception as e:
                print(f"⚠️ Graph retrieve error: {e}")

        # 2. Rerank
        reranked = self.reranker.rerank(user_message, retrieved, top_k=top_k_rerank)

        # 3. Build context
        context = self._build_context(reranked)

        # 4. Build prompt
        system_prompt = self._build_system_prompt(behavior_profile)

        # Conversation history
        history_text = ""
        if conversation_history:
            last_5 = conversation_history[-10:]  # 5 lượt = 10 messages
            for msg in last_5:
                role = "Khách" if msg["role"] == "user" else "Tư vấn viên"
                history_text += f"{role}: {msg['content']}\n"

        user_prompt = (
            f"--- CONTEXT TỪ CƠ SỞ TRI THỨC ---\n{context}\n\n"
        )
        if history_text:
            user_prompt += f"--- LỊCH SỬ HỘI THOẠI ---\n{history_text}\n\n"
        user_prompt += f"--- CÂU HỎI HIỆN TẠI ---\nKhách: {user_message}\n\nTư vấn viên:"

        # 5. Generate
        answer = self.generator.generate(user_prompt, system_prompt)

        # 6. Return
        sources = [doc.metadata.get("source", "?") for doc, _ in reranked]
        return {
            "answer": answer,
            "sources": list(set(sources)),
            "behavior_label": behavior_profile.get("label") if behavior_profile else None,
            "num_retrieved": len(retrieved),
            "num_reranked": len(reranked),
        }


# =============================================
# CHẠY STANDALONE
# =============================================
if __name__ == "__main__":
    print("=" * 60)
    print("  MODULE 3 — RAG Pipeline Test")
    print("=" * 60)

    pipeline = RAGPipeline()

    # Test 1: Không có behavior profile
    print("\n📝 Test 1: Query chung")
    result = pipeline.query("Có sách nào về lập trình Python không?")
    print(f"  Answer: {result['answer'][:300]}...")
    print(f"  Sources: {result['sources']}")

    # Test 2: Với behavior profile (impulse buyer)
    print("\n📝 Test 2: Với behavior profile (impulse_buyer)")
    profile = {"label": "impulse_buyer", "confidence": 0.85}
    result = pipeline.query("Gợi ý sách hay đi!", behavior_profile=profile)
    print(f"  Answer: {result['answer'][:300]}...")

    # Test 3: Thời trang
    print("\n📝 Test 3: Hỏi về thời trang")
    result = pipeline.query("Áo Gucci có bao nhiêu tiền?")
    print(f"  Answer: {result['answer'][:300]}...")

    print("\n✅ RAG Pipeline OK!")
