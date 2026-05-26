-- ============================================================
-- AI 璧勮��鏃╂姤/鏅氭姤鏅鸿兘浣� 路 鏁版嵁搴� Schema
-- PostgreSQL 16
-- ============================================================

-- 琛�1锛氬師濮嬭祫璁�锛圓 鍐欙紝B 璇伙級
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
    batch_id    UUID         NOT NULL      -- 鍚屼竴娆℃姄鍙栫殑鎵规�℃爣璇�
);
CREATE INDEX IF NOT EXISTS idx_raw_items_batch ON raw_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_items_source ON raw_items(source);
CREATE INDEX IF NOT EXISTS idx_raw_items_fetched ON raw_items(fetched_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_items_url ON raw_items(url);

-- 琛�2锛欰I 鍔犲伐鍚庣殑绠�鎶ワ紙B 鍐欙紝C/D/E 璇伙級
CREATE TABLE IF NOT EXISTS briefings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type        VARCHAR(10)  NOT NULL,    -- morning / evening
    date        DATE         NOT NULL,
    language    VARCHAR(5)   NOT NULL DEFAULT 'zh',
    tl_dr       JSONB        NOT NULL,    -- ["瑕佺偣1", "瑕佺偣2", ...]
    sections    JSONB        NOT NULL,    -- [{"title":"...","items":[{...}]}]
    key_takeaways JSONB      DEFAULT '[]',
    raw_stats   JSONB        DEFAULT '{}',-- {"fetched":150,"scored":80,"passed":30}
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(type, date, language)
);
CREATE INDEX IF NOT EXISTS idx_briefings_date ON briefings(date);
CREATE INDEX IF NOT EXISTS idx_briefings_type_date ON briefings(type, date);

-- 琛�3锛氬悇骞冲彴鍙戝竷鏃ュ織锛圖 鍐欙紝E 璇伙級
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

-- 琛�4锛氱敤鎴疯�㈤槄锛圕 璇诲啓锛�
CREATE TABLE IF NOT EXISTS subscriptions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    openid           VARCHAR(128) NOT NULL UNIQUE,
    subscribed       BOOLEAN DEFAULT true,
    morning_enabled  BOOLEAN DEFAULT true,
    evening_enabled  BOOLEAN DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 琛�5锛氳繍琛屾棩蹇楋紙E 璇诲啓锛�
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
