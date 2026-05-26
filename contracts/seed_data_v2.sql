-- ============================================================
-- AI 资讯早报/晚报智能体 · Phase 2 增量种子数据
-- 在 seed_data.sql 基础上补充
-- 运行前提：已执行 contracts/schema_v2.sql
-- ============================================================

-- ============================================================
-- Part 1: 测试用户订阅偏好（3 个测试用户，不同标签组合）
-- 假设 openid 对应微信测试号用户
-- ============================================================
INSERT INTO subscriptions (id, openid, subscribed, morning_enabled, evening_enabled, preferences, nickname)
VALUES
(
    'b0000001-0000-0000-0000-000000000001',
    'test_openid_user_001',
    true, true, true,
    '{"tags":["LLM","开源","Agent","Python"],"weight_map":{"LLM":1.0,"开源":0.9,"Agent":0.8,"Python":0.7}}',
    '小明'
),
(
    'b0000001-0000-0000-0000-000000000002',
    'test_openid_user_002',
    true, true, false,
    '{"tags":["AI产品","融资","AI政策"],"weight_map":{"AI产品":1.0,"融资":0.8,"AI政策":0.6}}',
    '小红'
),
(
    'b0000001-0000-0000-0000-000000000003',
    'test_openid_user_003',
    true, true, true,
    '{"tags":[],"weight_map":{}}',
    '新用户（默认）'
)
ON CONFLICT (openid) DO UPDATE SET
    preferences = EXCLUDED.preferences,
    nickname = EXCLUDED.nickname;

-- ============================================================
-- Part 2: 模拟用户行为数据（一周点击历史）
-- == 用户 001（小明 — LLM/开源/Agent/Python）==
-- 点击了 LLM、开源相关的资讯
-- ============================================================
INSERT INTO user_behavior (user_openid, briefing_id, item_index, item_title, item_url, item_tags, action)
SELECT
    'test_openid_user_001',
    b.id,
    idx,
    'mock_title_' || gen_random_uuid()::text,
    'https://example.com',
    tags,
    'click'
FROM briefings b,
LATERAL (
    VALUES
        (0, '["LLM","大模型"]'),
        (1, '["Agent","智能体"]'),
        (2, '["开源","Python"]'),
        (3, '["LLM","RAG"]'),
        (4, '["开源","Agent"]'),
        (5, '["LLM","多模态"]')
) AS t(idx, tags)
WHERE b.date >= CURRENT_DATE - INTERVAL '7 days'
  AND EXISTS (SELECT 1 FROM briefings LIMIT 1)
LIMIT 18;

-- 用户 001 的分享行为
INSERT INTO user_behavior (user_openid, briefing_id, item_index, item_title, item_url, item_tags, action)
SELECT
    'test_openid_user_001',
    b.id,
    0,
    'mock_title_' || gen_random_uuid()::text,
    'https://example.com',
    '["LLM","开源"]',
    'share'
FROM briefings b
WHERE b.date >= CURRENT_DATE - INTERVAL '7 days'
LIMIT 2;

-- == 用户 002（小红 — AI产品/融资/AI政策）==
INSERT INTO user_behavior (user_openid, briefing_id, item_index, item_title, item_url, item_tags, action)
SELECT
    'test_openid_user_002',
    b.id,
    idx,
    'mock_title_' || gen_random_uuid()::text,
    'https://example.com',
    tags,
    'click'
FROM briefings b,
LATERAL (
    VALUES
        (0, '["AI产品","商业化"]'),
        (1, '["融资","YC"]'),
        (2, '["AI政策","监管"]'),
        (3, '["AI产品","Agent"]'),
        (4, '["融资","估值"]'),
        (5, '["AI政策","欧盟"]')
) AS t(idx, tags)
WHERE b.date >= CURRENT_DATE - INTERVAL '7 days'
  AND EXISTS (SELECT 1 FROM briefings LIMIT 1)
LIMIT 12;

-- == 用户 003（新用户 — 无标签，只看不点）==
INSERT INTO user_behavior (user_openid, briefing_id, item_index, item_title, item_url, item_tags, action)
SELECT
    'test_openid_user_003',
    b.id,
    0,
    'mock_title_' || gen_random_uuid()::text,
    'https://example.com',
    '["LLM"]',
    'view'
FROM briefings b
WHERE b.date >= CURRENT_DATE - INTERVAL '3 days'
LIMIT 3;
