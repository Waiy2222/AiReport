-- ============================================================
-- AI 资讯早报/晚报智能体 · 数据库 Schema
-- PostgreSQL 16
-- ============================================================

-- 表1：原始资讯（A 写，B 读）
CREATE TABLE IF NOT EXISTS raw_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source      VARCHAR(32)  NOT NULL,   -- github / hackernews / rss / reddit / twitter
    title       TEXT         NOT NULL,
    url         TEXT         NOT NULL,
    content     TEXT,
    author      VARCHAR(255),
    published_at TIMESTAMPTZ NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata    JSONB        DEFAULT '{}', -- {"stars":100, "comments":30, "ai_score":8.5, ...}
    batch_id    UUID         NOT NULL      -- 同一次抓取的批次标识
);
CREATE INDEX IF NOT EXISTS idx_raw_items_batch ON raw_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_items_source ON raw_items(source);
CREATE INDEX IF NOT EXISTS idx_raw_items_fetched ON raw_items(fetched_at);

-- 表2：AI 加工后的简报（B 写，C/D/E 读）
CREATE TABLE IF NOT EXISTS briefings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type        VARCHAR(10)  NOT NULL,    -- morning / evening
    date        DATE         NOT NULL,
    language    VARCHAR(5)   NOT NULL DEFAULT 'zh',
    tl_dr       JSONB        NOT NULL,    -- ["要点1", "要点2", ...]
    sections    JSONB        NOT NULL,    -- [{"title":"...","items":[{...}]}]
    key_takeaways JSONB      DEFAULT '[]',
    raw_stats   JSONB        DEFAULT '{}',-- {"fetched":150,"scored":80,"passed":30}
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(type, date, language)
);
CREATE INDEX IF NOT EXISTS idx_briefings_date ON briefings(date);
CREATE INDEX IF NOT EXISTS idx_briefings_type_date ON briefings(type, date);

-- 表3：各平台发布日志（D 写，E 读）
CREATE TABLE IF NOT EXISTS publish_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    briefing_id   UUID REFERENCES briefings(id),
    platform      VARCHAR(32) NOT NULL,   -- zhihu / csdn / weixin_oa
    status        VARCHAR(16) NOT NULL,   -- pending / success / failed
    platform_url  TEXT,
    error_msg     TEXT,
    published_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_publish_log_briefing ON publish_log(briefing_id);

-- 表4：用户订阅（C 读写）
CREATE TABLE IF NOT EXISTS subscriptions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    openid           VARCHAR(128) NOT NULL UNIQUE,
    subscribed       BOOLEAN DEFAULT true,
    morning_enabled  BOOLEAN DEFAULT true,
    evening_enabled  BOOLEAN DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 表5：运行日志（E 读写）
CREATE TABLE IF NOT EXISTS run_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module      VARCHAR(8)   NOT NULL,    -- A / B / C / D / E
    run_type    VARCHAR(16)  NOT NULL,    -- morning / evening / manual
    status      VARCHAR(16)  NOT NULL,    -- running / success / failed
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    detail      JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_run_log_module ON run_log(module);
CREATE INDEX IF NOT EXISTS idx_run_log_started ON run_log(started_at DESC);
