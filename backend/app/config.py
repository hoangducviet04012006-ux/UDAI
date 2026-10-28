import os

from dotenv import load_dotenv
from pydantic import BaseModel

# =====================================================================
# Đường dẫn theo cấu trúc mới:
#   BASE_DIR    = <root>              (chứa backend/, frontend/, database/, docs/, tests/)
#   BACKEND_DIR = <root>/backend
# =====================================================================
APP_DIR = os.path.dirname(os.path.abspath(__file__))   # <root>/backend/app
BACKEND_DIR = os.path.dirname(APP_DIR)                 # <root>/backend
BASE_DIR = os.path.dirname(BACKEND_DIR)                # <root>

# Nạp biến môi trường từ root .env hoặc backend/.env (nếu có)
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

# CSDL SQLite demo nằm trong database/ và dùng ĐƯỜNG DẪN TUYỆT ĐỐI:
# chạy lệnh từ backend/, tests/ hay gốc dự án đều trỏ đúng MỘT file CSDL duy nhất.
DEFAULT_SQLITE_PATH = os.path.join(BASE_DIR, "database", "baohanh_ai.db").replace("\\", "/")


class Settings(BaseModel):
    app_name: str = "BaoHanhAI - Hệ thống Quản lý Bảo hành Sản phẩm"
    app_version: str = "3.0.0 (KT2 + KT3)"
    database_url: str = os.getenv("DATABASE_URL") or f"sqlite:///{DEFAULT_SQLITE_PATH}"
    debug: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

    # ------------------------------------------------------------------
    # KT3 - Cấu hình AI Provider cho AI-01 (Phân loại lỗi bảo hành)
    # ------------------------------------------------------------------
    # ai_provider:
    #   "mock"  -> RuleBasedMockProvider (mặc định, chạy offline 100%, không cần API key)
    #   "auto"  -> Dùng provider thật nếu có API key, ngược lại tự động fallback về mock
    #   "openai"/"openai_compatible" -> OpenAICompatibleProvider (cần API key)
    # TUYỆT ĐỐI không hard-code API key trong source code; chỉ đọc từ biến môi trường.
    ai_provider: str = os.getenv("AI_PROVIDER", "mock")
    ai_model: str = os.getenv("AI_MODEL", "gpt-4o-mini")
    ai_api_key: str = os.getenv("AI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    ai_base_url: str = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
    ai_timeout_seconds: float = float(os.getenv("AI_TIMEOUT_SECONDS", "30"))
    # Ngưỡng confidence tối đa khi AI không chọn được nhãn (guardrail KT3)
    ai_max_confidence_when_null: float = float(os.getenv("AI_MAX_CONFIDENCE_WHEN_NULL", "0.40"))

    # ------------------------------------------------------------------
    # Đợt 7 - Xác thực (Auth) & Phân quyền theo vai trò (RBAC)
    # ------------------------------------------------------------------
    # auth_secret_key: khóa bí mật để ký token (HMAC-SHA256).
    #   * CHỈ đọc từ biến môi trường AUTH_SECRET_KEY; giá trị mặc định dưới đây
    #     là khóa dùng cho môi trường phát triển/demo (chạy offline, không có .env).
    #   * Môi trường thật BẮT BUỘC khai báo AUTH_SECRET_KEY riêng và không commit.
    auth_secret_key: str = os.getenv("AUTH_SECRET_KEY") or "baohanhai-dev-only-secret-change-me"
    # Thời hạn của phiên đăng nhập (phút). Mặc định 8 giờ = 1 ca làm việc.
    auth_token_ttl_minutes: int = int(os.getenv("AUTH_TOKEN_TTL_MINUTES", "480"))
    # Số vòng lặp PBKDF2-HMAC-SHA256 khi băm mật khẩu (tăng = chậm hơn cho kẻ dò).
    auth_pbkdf2_iterations: int = int(os.getenv("AUTH_PBKDF2_ITERATIONS", "120000"))

    # ------------------------------------------------------------------
    # KT4 (P0) - Chatbot hỗ trợ bảo hành (LangChain RAG + LangGraph Agent)
    # ------------------------------------------------------------------
    # Đây chỉ là NỀN TẢNG cấu hình cho module chatbot (/api/v1/chatbot).
    # Nguyên tắc giữ nguyên của dự án:
    #   * OFFLINE-FIRST: mặc định provider "mock" + embedding "hash" => không cần API key.
    #   * API key CHỈ đọc từ biến môi trường (AI_API_KEY/OPENAI_API_KEY), không hard-code.
    #   * CHATBOT_ENABLED=false => router chatbot trả 503; KHÔNG ảnh hưởng KT2/KT3.
    # Router hỗ trợ dùng enabled/provider/max_turns/max_context_chars. Các thiết lập embedding,
    # vector và prompt phía dưới là nền tảng cũ, chưa được module này sử dụng.
    # Xác minh mã bí mật luôn bắt buộc, không cho phép tắt bằng cấu hình.
    chatbot_enabled: bool = os.getenv("CHATBOT_ENABLED", "True").lower() in ("true", "1", "yes")
    chatbot_provider: str = os.getenv("CHATBOT_PROVIDER", os.getenv("AI_PROVIDER", "mock"))
    chatbot_embedding_provider: str = os.getenv("CHATBOT_EMBEDDING_PROVIDER", "hash")
    chatbot_embedding_model: str = os.getenv("CHATBOT_EMBEDDING_MODEL", "text-embedding-3-small")
    # Số đoạn tài liệu (chunk) truy hồi cho mỗi câu hỏi
    chatbot_top_k: int = int(os.getenv("CHATBOT_TOP_K", "4"))
    # Giới hạn hội thoại nhằm kiểm soát chi phí/thời gian phản hồi
    chatbot_max_turns: int = int(os.getenv("CHATBOT_MAX_TURNS", "20"))
    chatbot_max_context_chars: int = int(os.getenv("CHATBOT_MAX_CONTEXT_CHARS", "6000"))
    # Bắt buộc xác minh chủ sở hữu (logic BR4) trước khi trả thông tin phiếu/serial
    chatbot_require_owner_verification: bool = os.getenv(
        "CHATBOT_REQUIRE_OWNER_VERIFICATION", "True"
    ).lower() in ("true", "1", "yes")
    # Thư mục knowledge base (markdown) và vector store cục bộ (KHÔNG commit vector store)
    chatbot_kb_dir: str = os.getenv("CHATBOT_KB_DIR") or os.path.join(BASE_DIR, "database", "knowledge")
    chatbot_vector_dir: str = os.getenv("CHATBOT_VECTOR_DIR") or os.path.join(BASE_DIR, "database", "vectorstore")
    # Phiên bản prompt lưu vào chat_messages.prompt_version để truy vết / đánh giá
    chatbot_prompt_version: str = os.getenv("CHATBOT_PROMPT_VERSION", "chatbot_v1")

settings = Settings()
