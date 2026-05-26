-- ============================================================
-- AI 资讯早报/晚报智能体 · Phase 2 增量 Schema
-- 在 schema.sql 基础上扩展
-- 运行前提：已执行 contracts/schema.sql
-- ============================================================

-- 1. 启用 pgvector 扩展（RAG 记忆机制）
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. raw_items 加 embedding 列
ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS embedding vector(1536);
CREATE INDEX IF NOT EXISTS idx_raw_items_embedding
    ON raw_items USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 3. subscriptions 加偏好字段
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS preferences JSONB DEFAULT '{}';
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS nickname TEXT;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ;

COMMENT ON COLUMN subscriptions.preferences IS
    '{"tags":["LLM","开源"],"weight_map":{"LLM":1.0,"开源":0.8}}';

-- 4. 新增：用户行为追踪表（C 模块读写）
CREATE TABLE IF NOT EXISTS user_behavior (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_openid     TEXT NOT NULL,
    briefing_id     UUID REFERENCES briefings(id),
    item_index      INT,
    item_title      TEXT,
    item_url        TEXT,
    item_tags       JSONB DEFAULT '[]',
    action          VARCHAR(16) NOT NULL,  -- click / view / share / dismiss
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ub_openid ON user_behavior(user_openid);
CREATE INDEX IF NOT EXISTS idx_ub_briefing ON user_behavior(briefing_id);
CREATE INDEX IF NOT EXISTS idx_ub_action ON user_behavior(action);
CREATE INDEX IF NOT EXISTS idx_ub_created ON user_behavior(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ub_openid_created ON user_behavior(user_openid, created_at DESC);

-- 5. 新增：视频表（F 模块读写，E 模块读取状态）
CREATE TABLE IF NOT EXISTS videos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type            VARCHAR(32) NOT NULL,      -- ai_agent_weekly
    date            DATE NOT NULL,
    title           TEXT,
    script          TEXT,
    output_path     TEXT,
    duration_seconds INT,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
        -- pending / processing / done / failed
    metadata        JSONB DEFAULT '{}',
        -- {"material_count":5,"model":"gemini-2.5-pro","tts":"edge-tts"}
    error_msg       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    UNIQUE(type, date)
);
CREATE INDEX IF NOT EXISTS idx_videos_date ON videos(date DESC);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);

-- 6. 新增：用户标签字典表（可选，供 H5 页面展示可用标签列表）
CREATE TABLE IF NOT EXISTS tag_catalog (
    tag         VARCHAR(32) PRIMARY KEY,
    category    VARCHAR(16),          -- topic / language / domain
    label_zh    TEXT,
    description TEXT,
    sort_order  INT DEFAULT 0
);

-- 预置标签
INSERT INTO tag_catalog (tag, category, label_zh, description, sort_order) VALUES
    ('LLM',       'topic', '大模型', 'LLM/ChatGPT/Claude/Gemini等', 1),
    ('开源',      'topic', '开源项目', '开源框架、工具、模型', 2),
    ('Python',    'topic', 'Python', 'Python生态/AI开发', 3),
    ('AI安全',    'topic', 'AI安全', '对齐/红队/鲁棒性', 4),
    ('Agent',     'topic', '智能体', 'AI Agent/多Agent协作', 5),
    ('AI产品',    'topic', 'AI产品', 'AI应用/商业化/SaaS', 6),
    ('RAG',       'topic', 'RAG', '检索增强生成', 7),
    ('多模态',    'topic', '多模态', '视觉/语音/视频理解', 8),
    ('AI编程',    'topic', 'AI编程', 'Copilot/IDE/代码生成', 9),
    ('AI政策',    'topic', 'AI政策', '监管/合规/政策/伦理', 10),
    ('融资',      'topic', '融资并购', 'AI创投/融资/acquisition', 11),
    ('基础设施',  'topic', '基础设施', 'GPU/推理/部署/向量数据库', 12)
ON CONFLICT (tag) DO NOTHING;
