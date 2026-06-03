-- ============================================================
-- AI 资讯早报/晚报智能体 · Phase 3 增量 Schema
-- 在 schema.sql + schema_v2.sql 基础上扩展
-- 运行前提：已执行 contracts/schema.sql 和 contracts/schema_v2.sql
-- ============================================================

-- 1. 新增：推荐信源表（module-a source_agent 写入，module-c/backend + module-e Dashboard 读取）
CREATE TABLE IF NOT EXISTS recommended_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tag             VARCHAR(32) NOT NULL,
    name            TEXT NOT NULL,
    url             TEXT NOT NULL,
    rss_url         TEXT,
    quality_score   DECIMAL(2,1),       -- 综合评分 1-5
    relevance_score DECIMAL(2,1),       -- 相关性
    freshness_score DECIMAL(2,1),       -- 更新频率
    authority_score DECIMAL(2,1),       -- 权威性
    status          VARCHAR(16) DEFAULT 'pending',  -- pending/approved/rejected
    discovered_at   TIMESTAMPTZ DEFAULT now(),
    approved_at     TIMESTAMPTZ,
    FOREIGN KEY (tag) REFERENCES tag_catalog(tag)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_rs_tag ON recommended_sources(tag);
CREATE INDEX IF NOT EXISTS idx_rs_status ON recommended_sources(status);
CREATE INDEX IF NOT EXISTS idx_rs_discovered ON recommended_sources(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_rs_quality ON recommended_sources(quality_score DESC);

-- 表注释
COMMENT ON TABLE recommended_sources IS 'Agent 自主发现并推荐的 RSS 信源';
COMMENT ON COLUMN recommended_sources.quality_score IS '综合评分 1-5（相关性+更新频率+权威性加权）';
COMMENT ON COLUMN recommended_sources.status IS 'pending=待审核 / approved=已通过 / rejected=已拒绝';
