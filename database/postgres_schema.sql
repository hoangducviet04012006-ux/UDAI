-- ====================================================================
-- BaoHanhAI - Database Schema for PostgreSQL (16 Tables, 30 Foreign Keys)
-- Designed according to BaoHanhAI_BaoCao_KT1_KT2 Specification
--   * KT1-KT3 : 11 bang CORE (19 FK) - khong thay doi
--   * KT4 (P1): 5 bang nen tang chatbot RAG/Agent (11 FK) - xem cuoi file
-- ====================================================================

-- 1. Table: service_centers (Trung tâm xử lý)
CREATE TABLE IF NOT EXISTS service_centers (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(150) UNIQUE NOT NULL,
    address VARCHAR(255),
    phone VARCHAR(20),
    email VARCHAR(100) UNIQUE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. Table: error_categories (Danh mục lỗi)
CREATE TABLE IF NOT EXISTS error_categories (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. Table: users (Tài khoản / RBAC)
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('MANAGER', 'RECEPTIONIST', 'TECHNICIAN')),
    service_center_id BIGINT REFERENCES service_centers(id) ON DELETE SET NULL, -- FK 1
    email VARCHAR(100) UNIQUE,
    phone VARCHAR(20),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 4. Table: customers (Khách hàng)
CREATE TABLE IF NOT EXISTS customers (
    id BIGSERIAL PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE,
    address VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 5. Table: products (Model sản phẩm)
CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    brand VARCHAR(50),
    category VARCHAR(50),
    warranty_duration_months INT NOT NULL CHECK (warranty_duration_months > 0),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 6. Table: product_instances (Sản phẩm theo serial)
CREATE TABLE IF NOT EXISTS product_instances (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE RESTRICT, -- FK 2
    customer_id BIGINT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT, -- FK 3
    serial_number VARCHAR(100) UNIQUE NOT NULL,
    purchase_date DATE NOT NULL,
    warranty_end_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('ACTIVE', 'EXPIRED')),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 7. Table: warranty_tickets (Phiếu bảo hành)
CREATE TABLE IF NOT EXISTS warranty_tickets (
    id BIGSERIAL PRIMARY KEY,
    ticket_code VARCHAR(30) UNIQUE NOT NULL,
    product_instance_id BIGINT NOT NULL REFERENCES product_instances(id) ON DELETE RESTRICT, -- FK 4
    customer_id BIGINT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT, -- FK 5
    service_center_id BIGINT NOT NULL REFERENCES service_centers(id) ON DELETE RESTRICT, -- FK 6
    created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT, -- FK 7
    issue_description TEXT NOT NULL,
    device_condition TEXT,
    accessories_accompanying TEXT,
    error_category_id BIGINT REFERENCES error_categories(id) ON DELETE SET NULL, -- FK 8
    status VARCHAR(20) NOT NULL CHECK (status IN ('RECEIVED', 'INSPECTING', 'REPAIRING', 'COMPLETED', 'REJECTED', 'RETURNED')) DEFAULT 'RECEIVED',
    
    -- Phân công kỹ thuật viên phụ trách
    assigned_technician_id BIGINT REFERENCES users(id) ON DELETE SET NULL, -- FK
    assigned_at TIMESTAMPTZ,

    -- Chẩn đoán & điều kiện bảo hành
    diagnosis_note TEXT,
    diagnosis_by BIGINT REFERENCES users(id) ON DELETE SET NULL, -- FK 11
    diagnosis_at TIMESTAMPTZ,
    is_warranty_eligible BOOLEAN,
    warranty_check_note TEXT,

    -- Nghiệp vụ sửa chữa & kiểm tra sau sửa
    repair_content TEXT,
    repair_parts TEXT,
    repair_note TEXT,
    repair_by BIGINT REFERENCES users(id) ON DELETE SET NULL, -- FK 12
    repair_at TIMESTAMPTZ,
    repair_test_passed BOOLEAN,
    repair_test_note TEXT,

    -- Nhánh từ chối bảo hành
    rejection_reason TEXT,
    rejection_proposed_by BIGINT REFERENCES users(id) ON DELETE SET NULL, -- FK 9
    rejection_proposed_at TIMESTAMPTZ,
    rejection_proposal_note TEXT,
    rejection_reviewed_by BIGINT REFERENCES users(id) ON DELETE SET NULL, -- FK 10
    rejection_reviewed_at TIMESTAMPTZ,
    rejection_review_status VARCHAR(20) CHECK (rejection_review_status IN ('PENDING', 'APPROVED', 'DECLINED')),

    -- Bàn giao trả máy & Đóng phiếu
    completed_at TIMESTAMPTZ,
    handed_over_by BIGINT REFERENCES users(id) ON DELETE SET NULL, -- FK 13
    handed_over_at TIMESTAMPTZ,
    handover_note TEXT,
    resolution VARCHAR(20) CHECK (resolution IS NULL OR resolution IN ('COMPLETED', 'REJECTED')),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 8. Table: technician_assignments (Phân công kỹ thuật viên)
CREATE TABLE IF NOT EXISTS technician_assignments (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES warranty_tickets(id) ON DELETE CASCADE, -- FK 11
    technician_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT, -- FK 12
    assigned_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT, -- FK 13
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

-- 9. Table: ticket_status_history (Lịch sử trạng thái)
CREATE TABLE IF NOT EXISTS ticket_status_history (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES warranty_tickets(id) ON DELETE CASCADE, -- FK 14
    from_status VARCHAR(20) CHECK (from_status IS NULL OR from_status IN ('RECEIVED', 'INSPECTING', 'REPAIRING', 'COMPLETED', 'REJECTED', 'RETURNED')),
    to_status VARCHAR(20) NOT NULL CHECK (to_status IN ('RECEIVED', 'INSPECTING', 'REPAIRING', 'COMPLETED', 'REJECTED', 'RETURNED')),
    changed_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT, -- FK 15
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 10. Table: repair_logs (Nhật ký sửa chữa)
CREATE TABLE IF NOT EXISTS repair_logs (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES warranty_tickets(id) ON DELETE CASCADE, -- FK 16
    technician_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT, -- FK 17
    action_description TEXT NOT NULL,
    parts_used TEXT,
    labor_hours NUMERIC(5, 2),
    logged_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 11. Table: ai_results (Kết quả AI)
CREATE TABLE IF NOT EXISTS ai_results (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES warranty_tickets(id) ON DELETE CASCADE, -- FK 18
    ai_function VARCHAR(50) NOT NULL,
    input_data JSONB,
    output_data JSONB,
    confidence_score NUMERIC(5, 4),
    reviewed_by BIGINT REFERENCES users(id) ON DELETE SET NULL, -- FK 19
    review_status VARCHAR(20) CHECK (review_status IN ('PENDING', 'APPROVED', 'REJECTED')) DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_product_instances_serial ON product_instances(serial_number);
CREATE INDEX IF NOT EXISTS idx_warranty_tickets_status ON warranty_tickets(status);
CREATE INDEX IF NOT EXISTS idx_warranty_tickets_serial ON warranty_tickets(product_instance_id);
CREATE INDEX IF NOT EXISTS idx_technician_assignments_active ON technician_assignments(ticket_id) WHERE completed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_status_history_ticket ON ticket_status_history(ticket_id);

-- ====================================================================
-- KT4 (P1) - SCHEMA CHATBOT (nen tang cho LangChain RAG + LangGraph Agent)
-- --------------------------------------------------------------------
-- 5 bang MOI, KHONG sua/xoa cot cua 11 bang CORE o tren => giu nguyen ERD KT1.
--   * chat_messages.content CHI luu ban da khu PII (sanitize_pii cua KT3).
--   * Chatbot khong tu quyet dinh bao hanh: moi de xuat nhan loi nam o trang thai
--     de xuat (chat_handoffs.ai_suggested_category_id) cho nhan vien duyet.
-- ====================================================================

-- 12. Table: kb_documents (Tai lieu tri thuc phuc vu RAG)
CREATE TABLE IF NOT EXISTS kb_documents (
    id BIGSERIAL PRIMARY KEY,
    doc_code VARCHAR(50) UNIQUE NOT NULL,          -- VD: BH-POLICY-01
    title VARCHAR(200) NOT NULL,
    doc_type VARCHAR(30) NOT NULL CHECK (doc_type IN ('POLICY','FAQ','MANUAL','BR_RULE','PROCESS')),
    source_ref VARCHAR(255),
    language VARCHAR(10) DEFAULT 'vi',
    content TEXT NOT NULL,
    checksum VARCHAR(64) NOT NULL,                 -- sha256(content): tranh nhung lai chunk cu
    version VARCHAR(20) DEFAULT '1.0',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 13. Table: kb_chunks (Doan tai lieu da chia nho - don vi truy hoi cua RAG)
CREATE TABLE IF NOT EXISTS kb_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE, -- FK 20
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    embedding JSONB,                               -- fallback khi vector store chay in-memory
    chunk_metadata JSONB,                          -- heading/section/source_ref cho trich dan
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_kb_chunk UNIQUE (document_id, chunk_index)
);

-- 14. Table: chat_sessions (Phien hoi thoai voi chatbot)
CREATE TABLE IF NOT EXISTS chat_sessions (
    id BIGSERIAL PRIMARY KEY,
    session_code VARCHAR(30) UNIQUE NOT NULL,      -- CS-YYYYMMDD-XXXX
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,               -- FK 21
    customer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL,       -- FK 22
    ticket_id BIGINT REFERENCES warranty_tickets(id) ON DELETE SET NULL,  -- FK 23
    channel VARCHAR(20) NOT NULL DEFAULT 'WEB',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','CLOSED','ESCALATED')),
    title VARCHAR(200),
    locale VARCHAR(10) DEFAULT 'vi',
    turn_count INTEGER NOT NULL DEFAULT 0,
    last_intent VARCHAR(50),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ
);

-- 15. Table: chat_messages (Tung luot tin nhan, da khu PII)
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE, -- FK 24
    turn_index INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('USER','ASSISTANT','SYSTEM','TOOL')),
    content TEXT NOT NULL,
    intent VARCHAR(50),
    tool_name VARCHAR(50),
    tool_args JSONB,
    retrieved_chunk_ids JSONB,
    citations JSONB,
    confidence NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence BETWEEN 0 AND 1)),
    guardrail_flags JSONB,
    pii_redacted BOOLEAN NOT NULL DEFAULT FALSE,
    provider VARCHAR(50),
    prompt_version VARCHAR(20),
    latency_ms INTEGER,
    token_usage JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_chat_turn UNIQUE (session_id, turn_index)
);

-- 16. Table: chat_handoffs (Ban giao nhan vien - human-in-the-loop)
CREATE TABLE IF NOT EXISTS chat_handoffs (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,  -- FK 25
    message_id BIGINT REFERENCES chat_messages(id) ON DELETE SET NULL,          -- FK 26
    ticket_id BIGINT REFERENCES warranty_tickets(id) ON DELETE SET NULL,        -- FK 27
    reason VARCHAR(200) NOT NULL,
    priority VARCHAR(10) NOT NULL DEFAULT 'NORMAL' CHECK (priority IN ('LOW','NORMAL','HIGH')),
    ai_suggested_category_id BIGINT REFERENCES error_categories(id) ON DELETE SET NULL, -- FK 28
    ai_confidence NUMERIC(5,4),
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','ASSIGNED','RESOLVED','CANCELLED')),
    assigned_to BIGINT REFERENCES users(id) ON DELETE SET NULL,   -- FK 29
    resolved_by BIGINT REFERENCES users(id) ON DELETE SET NULL,   -- FK 30
    resolution_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ
);

-- Indices cho chatbot (KT4)
CREATE INDEX IF NOT EXISTS idx_kb_chunks_document ON kb_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_status ON chat_sessions(status);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_ticket ON chat_sessions(ticket_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, turn_index);
CREATE INDEX IF NOT EXISTS idx_chat_handoffs_status ON chat_handoffs(status);

-- Trợ lý bảo hành: mã tra cứu chỉ lưu SHA-256; không lưu mã gốc.
CREATE TABLE IF NOT EXISTS ticket_lookup_credentials (
    ticket_id BIGINT PRIMARY KEY REFERENCES warranty_tickets(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMP NOT NULL
);
