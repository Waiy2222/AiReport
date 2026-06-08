"""信源自扩展 Agent — 监测标签覆盖率，自动搜索推荐新 RSS 信源

自主决策链路：
  检查覆盖率 → 发现某标签连续3天 < 2条
    → Agent 搜索 "RAG retrieval augmented generation RSS feed"
      → 找到候选源 → Agent 逐个评估（请求首页 → LLM 判断质量）
        → 推荐 Top 2 → 写入 recommended_sources 表
"""

import json
import logging
import os
import re
import time
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DeepSeek / LLM 配置
# ---------------------------------------------------------------------------
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-chat"

# 覆盖率阈值：标签近 3 天文章数低于此值触发搜索
COVERAGE_THRESHOLD = 2
# 近 N 天的窗口
COVERAGE_DAYS = 3


def _has_api_key() -> bool:
    key = os.getenv("DEEPSEEK_API_KEY", "")
    return bool(key and key.startswith("sk-"))


def _get_client():
    if not _has_api_key():
        return None
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


async def _llm_chat(
    messages: list[dict], temperature: float = 0.3, max_tokens: int = 2000
) -> str | None:
    """单次 LLM 调用，返回 content 或 None"""
    client = _get_client()
    if client is None:
        return None
    try:
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    except Exception:
        logger.warning("LLM call failed", exc_info=True)
        return None


def _extract_json(text: str) -> str:
    """从 LLM 响应提取纯 JSON"""
    t = text.strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", t, re.DOTALL)
        if m:
            return m.group(1).strip()
    if t and t[0] in ("{", "["):
        if t.endswith("```"):
            t = t[:-3].strip()
        return t
    candidates = []
    for prefix in ("{", "["):
        idx = t.find(prefix)
        if idx >= 0:
            close = "}" if prefix == "{" else "]"
            depth = 0
            end = idx
            for i, ch in enumerate(t[idx:], start=idx):
                if ch == prefix:
                    depth += 1
                elif ch == close:
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if depth == 0:
                candidates.append(t[idx : end + 1])
    if candidates:
        candidates.sort(key=len, reverse=True)
        return candidates[0]
    return t


# ---------------------------------------------------------------------------
# 覆盖率检查
# ---------------------------------------------------------------------------


async def check_coverage(pool) -> list[dict]:
    """检查各标签近 3 天的覆盖率，返回覆盖不足的标签列表。

    查询 raw_items 中每个标签近 COVERAGE_DAYS 天的文章数。
    返回 [{tag, label_zh, count, days_under_threshold}]。

    参数:
        pool: asyncpg 连接池。为 None 时返回 mock 数据。
    """
    if pool is None:
        logger.warning("[source_agent] pool=None, returning mock coverage data")
        return _mock_check_coverage()

    cutoff = date.today() - timedelta(days=COVERAGE_DAYS)
    logger.info(f"[source_agent] 检查覆盖率，cutoff={cutoff}, threshold={COVERAGE_THRESHOLD}")

    # 先获取所有活跃标签
    tags = await pool.fetch(
        "SELECT tag, label_zh, description FROM tag_catalog ORDER BY sort_order"
    )

    under_tags = []
    for row in tags:
        tag = row["tag"]
        label_zh = row["label_zh"]

        # 统计该标签近 N 天出现在 raw_items.metadata->tags 中的文章数
        # raw_items 的 tag 存储在 metadata JSONB 的 "tags" 键中
        count = await pool.fetchval(
            """SELECT COUNT(*) FROM raw_items
               WHERE fetched_at >= $1
                 AND metadata->'tags' ? $2""",
            cutoff,
            tag,
        )

        if count < COVERAGE_THRESHOLD:
            # 检查连续不足天数
            days_under = 1
            for d in range(1, COVERAGE_DAYS + 1):
                day_cutoff = date.today() - timedelta(days=d)
                day_count = await pool.fetchval(
                    """SELECT COUNT(*) FROM raw_items
                       WHERE fetched_at::date = $1
                         AND metadata->'tags' ? $2""",
                    day_cutoff,
                    tag,
                )
                if day_count < COVERAGE_THRESHOLD:
                    days_under = d
                else:
                    break

            under_tags.append(
                {
                    "tag": tag,
                    "label_zh": label_zh or tag,
                    "count": count,
                    "days_under_threshold": days_under,
                    "threshold": COVERAGE_THRESHOLD,
                }
            )
            logger.info(
                f"[source_agent] 覆盖不足: tag={tag}, count={count}, "
                f"连续不足天数={days_under}"
            )
        else:
            logger.debug(f"[source_agent] 覆盖充足: tag={tag}, count={count}")

    logger.info(
        f"[source_agent] 覆盖检查完成: 总标签={len(tags)}, 不足={len(under_tags)}"
    )
    return under_tags


def _mock_check_coverage() -> list[dict]:
    """无 DB 时返回 mock 覆盖率数据"""
    return [
        {
            "tag": "RAG",
            "label_zh": "RAG",
            "count": 1,
            "days_under_threshold": 3,
            "threshold": COVERAGE_THRESHOLD,
        },
        {
            "tag": "AI安全",
            "label_zh": "AI安全",
            "count": 0,
            "days_under_threshold": 3,
            "threshold": COVERAGE_THRESHOLD,
        },
    ]


# ---------------------------------------------------------------------------
# 信源搜索（LLM 驱动）
# ---------------------------------------------------------------------------


async def search_sources(tag: str, label_zh: str = "") -> list[dict]:
    """LLM 自主搜索该领域的 RSS 源。

    参数:
        tag: 标签名（如 "RAG"）
        label_zh: 中文标签名（如 "RAG"）

    返回: [{name, url, rss_url, description}] 候选源列表
    """
    display = label_zh or tag
    prompt = f"""你是一个 AI 资讯领域的研究员。用户需要为「{display}」这个主题寻找高质量的 RSS 信息源。

请推荐 5-8 个和「{display}」领域相关的优质 RSS/Atom 订阅源。要求：
1. 优先推荐活跃更新的知名技术博客、开源项目发布页、技术社区
2. 每个源提供：name（名称）、url（主页）、rss_url（RSS/Atom 地址，如可推断）、description（一句话描述）
3. 确保推荐的信源真实存在、广为人知
4. 避免推荐需要付费订阅或 API Key 的源
5. 优先英文源（该领域英文资源最丰富），也可以包含中文源

请以 JSON 数组格式返回，每个元素格式：
{{"name": "源名称", "url": "https://...", "rss_url": "https://.../rss 或 null", "description": "一句话描述"}}

只返回 JSON 数组，不要其他文字。"""

    messages = [
        {
            "role": "system",
            "content": "你是一个专业的技术信息源研究员，熟知各类技术博客、开源社区和 RSS 订阅源。只返回 JSON 数组。",
        },
        {"role": "user", "content": prompt},
    ]

    raw = await _llm_chat(messages, temperature=0.7, max_tokens=2000)

    if raw is None:
        logger.warning(f"[source_agent] LLM 未返回结果，使用 mock 搜索: tag={tag}")
        return _mock_search_sources(tag)

    try:
        json_str = _extract_json(raw)
        sources = json.loads(json_str)
        if isinstance(sources, list):
            # 规范化
            result = []
            for s in sources:
                if isinstance(s, dict) and s.get("url"):
                    result.append(
                        {
                            "name": s.get("name", ""),
                            "url": s["url"],
                            "rss_url": s.get("rss_url"),
                            "description": s.get("description", ""),
                        }
                    )
            logger.info(
                f"[source_agent] 搜索完成: tag={tag}, 候选源={len(result)}"
            )
            return result
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"[source_agent] JSON 解析失败: {e}, raw={raw[:200]}")

    return _mock_search_sources(tag)


def _mock_search_sources(tag: str) -> list[dict]:
    """无 LLM 时的 mock 搜索 — 返回常见 AI 领域的知名 RSS 源"""
    mock_db = {
        "LLM": [
            {
                "name": "Hugging Face Blog",
                "url": "https://huggingface.co/blog",
                "rss_url": "https://huggingface.co/blog/feed.xml",
                "description": "Hugging Face 官方博客，大模型与开源 AI 前沿",
            },
            {
                "name": "The Sequence (Substack)",
                "url": "https://thesequence.substack.com",
                "rss_url": "https://thesequence.substack.com/feed",
                "description": "深度解析大模型技术的周刊",
            },
        ],
        "Agent": [
            {
                "name": "LangChain Blog",
                "url": "https://blog.langchain.dev",
                "rss_url": "https://blog.langchain.dev/rss/",
                "description": "LangChain 官方博客，AI Agent 框架动态",
            },
            {
                "name": "AutoGPT Blog",
                "url": "https://auto-gpt.ai/blog",
                "rss_url": None,
                "description": "AutoGPT 项目官方动态",
            },
        ],
        "RAG": [
            {
                "name": "LlamaIndex Blog",
                "url": "https://blog.llamaindex.ai",
                "rss_url": "https://blog.llamaindex.ai/feed",
                "description": "LlamaIndex 官方博客，RAG 技术前沿",
            },
        ],
        "开源": [
            {
                "name": "GitHub Trending RSS",
                "url": "https://github.com/trending",
                "rss_url": "https://rsshub.app/github/trending/daily",
                "description": "GitHub 每日热门开源项目",
            },
        ],
        "科技": [
            {
                "name": "TechCrunch RSS",
                "url": "https://techcrunch.com",
                "rss_url": "https://techcrunch.com/feed/",
                "description": "TechCrunch 科技新闻",
            },
        ],
        "AI编程": [
            {
                "name": "GitHub Copilot Blog",
                "url": "https://github.blog/copilot/",
                "rss_url": "https://github.blog/copilot/feed/",
                "description": "GitHub Copilot 与 AI 编程工具动态",
            },
        ],
    }

    # 通用回退
    generic = [
        {
            "name": "Hacker News",
            "url": "https://news.ycombinator.com",
            "rss_url": "https://hnrss.org/frontpage",
            "description": "技术社区热门讨论",
        },
        {
            "name": f"Reddit r/{tag}",
            "url": f"https://www.reddit.com/r/{tag}/",
            "rss_url": f"https://www.reddit.com/r/{tag}/.rss",
            "description": f"Reddit {tag} 社区",
        },
    ]

    result = mock_db.get(tag, generic)
    logger.info(f"[source_agent] mock 搜索: tag={tag}, 候选源={len(result)}")
    return result


# ---------------------------------------------------------------------------
# 信源评估
# ---------------------------------------------------------------------------


async def evaluate_source(url: str, tag: str, label_zh: str = "") -> dict:
    """评估信源质量（可靠性 + 更新频率 + 内容匹配度）。

    参数:
        url: 信源主页 URL
        tag: 关联标签
        label_zh: 标签中文名

    返回: {name, url, rss_url, quality_score, relevance_score,
            freshness_score, authority_score, accessible, summary}
    """
    display = label_zh or tag

    # 1. 尝试访问信源主页
    accessible = False
    homepage_text = ""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AiReport/2.0; RSS Source Evaluator)"
                },
                follow_redirects=True,
            )
            if resp.status_code < 400:
                accessible = True
                # 仅取前 3000 字符供 LLM 评估
                homepage_text = resp.text[:3000]
    except Exception as e:
        logger.info(f"[source_agent] 信源不可访问: url={url}, error={e}")

    # 2. LLM 评估质量
    quality_scores = await _llm_evaluate(url, tag, display, accessible, homepage_text)

    if quality_scores is None:
        # LLM 不可用时的回退评分
        quality_scores = _heuristic_evaluate(tag, accessible, homepage_text)

    quality_scores["accessible"] = accessible
    return quality_scores


async def _llm_evaluate(
    url: str, tag: str, display: str, accessible: bool, homepage_text: str
) -> dict | None:
    """使用 LLM 评估信源质量"""

    prompt = f"""请评估以下信息源对于「{display}」主题的质量。每个维度 1-5 分：

- 信息源 URL: {url}
- 可访问性: {'可正常访问' if accessible else '无法访问'}
- 首页预览: {homepage_text[:1500] if homepage_text else '无法获取'}

评估维度：
1. 内容相关性 (relevance_score)：文章是否真的和「{display}」相关？1=完全无关，5=高度相关
2. 更新频率 (freshness_score)：最近是否有新内容？1=长期未更新，5=每日更新
3. 权威性 (authority_score)：是否知名网站/博客/社区？1=个人小站，5=行业权威

请以 JSON 格式返回：
{{"relevance_score": 4, "freshness_score": 3, "authority_score": 4, "summary": "一句话评估总结"}}

只返回 JSON，不要其他文字。"""

    messages = [
        {
            "role": "system",
            "content": "你是一个信息源质量评估专家。只返回 JSON 格式的评分。",
        },
        {"role": "user", "content": prompt},
    ]

    raw = await _llm_chat(messages, temperature=0.3, max_tokens=500)
    if raw is None:
        return None

    try:
        json_str = _extract_json(raw)
        scores = json.loads(json_str)
        return {
            "relevance_score": max(1, min(5, int(scores.get("relevance_score", 3)))),
            "freshness_score": max(1, min(5, int(scores.get("freshness_score", 3)))),
            "authority_score": max(1, min(5, int(scores.get("authority_score", 3)))),
            "summary": scores.get("summary", ""),
        }
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"[source_agent] 评估 JSON 解析失败: {e}")
        return None


def _heuristic_evaluate(
    tag: str, accessible: bool, homepage_text: str
) -> dict:
    """无 LLM 时的启发式评分"""
    # 基于可访问性和首页基础信息进行启发式评分
    if not accessible:
        return {
            "relevance_score": 3,
            "freshness_score": 2,
            "authority_score": 3,
            "summary": "无法访问，基于域名启发式评估",
        }

    # 基础启发式：检查是否有 RSS 相关标记
    has_blog = any(
        kw in homepage_text.lower()
        for kw in ["blog", "news", "article", "post", "feed", "rss"]
    )
    has_tech = any(
        kw in homepage_text.lower()
        for kw in ["ai", "ml", "github", "python", "code", "tech", "data"]
    )

    relevance = 4 if has_tech else 3
    freshness = 4 if has_blog else 3
    authority = 3  # 默认中等

    return {
        "relevance_score": relevance,
        "freshness_score": freshness,
        "authority_score": authority,
        "summary": "基于首页特征启发式评估",
    }


# ---------------------------------------------------------------------------
# 主入口：recommend_sources
# ---------------------------------------------------------------------------


async def recommend_sources(pool=None) -> list[dict]:
    """主入口：检测覆盖率 → 搜索 → 评估 → 推荐 → 写入数据库

    参数:
        pool: asyncpg 连接池。如果为 None，自动从 module-a/db.py 获取。

    返回: [{tag, name, url, rss_url, quality_score, ...}] 推荐信源列表
    """
    if pool is None:
        from db import get_pool as _get_pool

        pool = _get_pool()

    # Step 1: 检查覆盖率
    logger.info("[source_agent] === 开始信源自扩展检查 ===")
    under_tags = await check_coverage(pool)

    if not under_tags:
        logger.info("[source_agent] 所有标签覆盖充足，无需搜索新信源")
        return []

    # 只对连续 3 天不足的标签进行搜索（避免临时波动）
    target_tags = [t for t in under_tags if t["days_under_threshold"] >= COVERAGE_DAYS]
    if not target_tags:
        logger.info(
            "[source_agent] 有覆盖不足但未连续3天，跳过搜索: "
            + ", ".join(f"{t['tag']}({t['days_under_threshold']}天)" for t in under_tags)
        )
        return []

    logger.info(
        f"[source_agent] === 开始搜索 {len(target_tags)} 个不足标签 ==="
    )

    all_recommendations = []

    for ut in target_tags:
        tag = ut["tag"]
        label_zh = ut["label_zh"]

        # Step 2: 搜索候选源
        logger.info(f"[source_agent] 搜索标签 '{tag}' 的信源...")
        candidates = await search_sources(tag, label_zh)
        if not candidates:
            logger.warning(f"[source_agent] 标签 '{tag}' 未找到候选源")
            continue

        # 去重：检查是否已有相同 URL 的推荐（pending/approved 状态）
        existing_urls = set()
        existing_rows = await pool.fetch(
            "SELECT url FROM recommended_sources WHERE tag = $1", tag
        )
        for r in existing_rows:
            existing_urls.add(r["url"])

        new_candidates = [c for c in candidates if c["url"] not in existing_urls]
        if len(new_candidates) < len(candidates):
            logger.info(
                f"[source_agent] 标签 '{tag}': "
                f"去重 {len(candidates) - len(new_candidates)} 个已有推荐"
            )

        if not new_candidates:
            logger.info(f"[source_agent] 标签 '{tag}' 所有候选源已存在推荐列表中")
            continue

        # Step 3: 逐个评估质量
        logger.info(
            f"[source_agent] 评估标签 '{tag}' 的 {len(new_candidates)} 个候选源..."
        )
        evaluated = []
        for c in new_candidates:
            result = await evaluate_source(c["url"], tag, label_zh)
            quality = round(
                (
                    result.get("relevance_score", 3)
                    + result.get("freshness_score", 3)
                    + result.get("authority_score", 3)
                )
                / 3,
                1,
            )
            evaluated.append(
                {
                    "tag": tag,
                    "name": c["name"],
                    "url": c["url"],
                    "rss_url": c.get("rss_url"),
                    "quality_score": quality,
                    "relevance_score": result.get("relevance_score"),
                    "freshness_score": result.get("freshness_score"),
                    "authority_score": result.get("authority_score"),
                    "accessible": result.get("accessible", False),
                    "summary": result.get("summary", ""),
                }
            )

        # Step 4: 推荐 Top 2（按综合评分）
        evaluated.sort(key=lambda x: x["quality_score"], reverse=True)
        top_2 = evaluated[:2]

        # Step 5: 写入数据库
        for rec in top_2:
            await pool.execute(
                """INSERT INTO recommended_sources
                   (tag, name, url, rss_url, quality_score, relevance_score,
                    freshness_score, authority_score, status)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending')""",
                rec["tag"],
                rec["name"],
                rec["url"],
                rec["rss_url"],
                rec["quality_score"],
                rec["relevance_score"],
                rec["freshness_score"],
                rec["authority_score"],
            )
            logger.info(
                f"[source_agent] 写入推荐: tag={rec['tag']}, "
                f"name={rec['name']}, score={rec['quality_score']}"
            )

        all_recommendations.extend(top_2)

    logger.info(
        f"[source_agent] === 信源自扩展完成: "
        f"推荐 {len(all_recommendations)} 个新信源 ==="
    )
    return all_recommendations


# ---------------------------------------------------------------------------
# 辅助：获取信源健康度（供 API 使用）
# ---------------------------------------------------------------------------


async def get_sources_health(pool) -> list[dict]:
    """获取每个标签的信源健康度（覆盖率 + 推荐数量）。

    返回: [{tag, label_zh, count, health, recommendations_pending}]
        health: "green" (>=5), "yellow" (2-4), "red" (<2)
    """
    if pool is None:
        logger.warning("[source_agent] pool=None, returning mock health data")
        return _mock_sources_health()

    cutoff = date.today() - timedelta(days=COVERAGE_DAYS)

    tags = await pool.fetch("SELECT tag, label_zh FROM tag_catalog ORDER BY sort_order")

    # 批量获取所有 tag 的覆盖率
    result = []
    for row in tags:
        tag = row["tag"]
        label_zh = row["label_zh"]

        count = await pool.fetchval(
            """SELECT COUNT(*) FROM raw_items
               WHERE fetched_at >= $1 AND metadata->'tags' ? $2""",
            cutoff,
            tag,
        )

        # 健康度分档
        if count >= 5:
            health = "green"
        elif count >= 2:
            health = "yellow"
        else:
            health = "red"

        # 待审推荐数
        pending = await pool.fetchval(
            "SELECT COUNT(*) FROM recommended_sources WHERE tag=$1 AND status='pending'",
            tag,
        )

        result.append(
            {
                "tag": tag,
                "label_zh": label_zh or tag,
                "count": count,
                "health": health,
                "coverage_threshold": COVERAGE_THRESHOLD,
                "coverage_days": COVERAGE_DAYS,
                "recommendations_pending": pending or 0,
            }
        )

    return result


def _mock_sources_health() -> list[dict]:
    """无 DB 时返回 mock 健康度数据"""
    return [
        {"tag": "LLM", "label_zh": "大模型", "count": 8, "health": "green",
         "coverage_threshold": COVERAGE_THRESHOLD, "coverage_days": COVERAGE_DAYS,
         "recommendations_pending": 0},
        {"tag": "Agent", "label_zh": "智能体", "count": 6, "health": "green",
         "coverage_threshold": COVERAGE_THRESHOLD, "coverage_days": COVERAGE_DAYS,
         "recommendations_pending": 1},
        {"tag": "RAG", "label_zh": "RAG", "count": 1, "health": "red",
         "coverage_threshold": COVERAGE_THRESHOLD, "coverage_days": COVERAGE_DAYS,
         "recommendations_pending": 2},
        {"tag": "开源", "label_zh": "开源", "count": 4, "health": "yellow",
         "coverage_threshold": COVERAGE_THRESHOLD, "coverage_days": COVERAGE_DAYS,
         "recommendations_pending": 0},
    ]


async def get_recommendations(pool, status: str = "pending") -> list[dict]:
    """获取推荐信源列表。

    参数:
        pool: asyncpg 连接池。为 None 时返回 mock 数据。
        status: 筛选状态 (pending/approved/rejected)，默认 pending

    返回: [{id, tag, name, url, rss_url, quality_score, ...}]
    """
    if pool is None:
        logger.warning("[source_agent] pool=None, returning mock recommendations")
        return _mock_recommendations(status)

    rows = await pool.fetch(
        """SELECT r.*, tc.label_zh AS tag_label
           FROM recommended_sources r
           LEFT JOIN tag_catalog tc ON r.tag = tc.tag
           WHERE r.status = $1
           ORDER BY r.quality_score DESC, r.discovered_at DESC""",
        status,
    )

    return [_row_to_dict(r) for r in rows]


def _mock_recommendations(status: str = "pending") -> list[dict]:
    """无 DB 时返回 mock 推荐数据"""
    if status != "pending":
        return []
    return [
        {
            "id": "mock-001",
            "tag": "RAG",
            "tag_label": "RAG",
            "name": "LlamaIndex Blog",
            "url": "https://blog.llamaindex.ai",
            "rss_url": "https://blog.llamaindex.ai/feed",
            "quality_score": 4.0,
            "relevance_score": 5,
            "freshness_score": 4,
            "authority_score": 4,
            "status": "pending",
            "discovered_at": date.today().isoformat(),
            "approved_at": None,
        },
        {
            "id": "mock-002",
            "tag": "RAG",
            "tag_label": "RAG",
            "name": "LangChain Blog",
            "url": "https://blog.langchain.dev",
            "rss_url": "https://blog.langchain.dev/rss/",
            "quality_score": 3.7,
            "relevance_score": 4,
            "freshness_score": 4,
            "authority_score": 3,
            "status": "pending",
            "discovered_at": date.today().isoformat(),
            "approved_at": None,
        },
    ]


async def approve_source(pool, source_id: str) -> dict | None:
    """通过推荐信源（将 status 改为 approved）。pool 为 None 时返回 None。"""
    if pool is None:
        logger.warning("[source_agent] pool=None, approve_source not available")
        return None

    from uuid import UUID

    try:
        sid = UUID(source_id)
    except ValueError:
        return None

    row = await pool.fetchrow(
        """UPDATE recommended_sources
           SET status = 'approved', approved_at = now()
           WHERE id = $1 AND status = 'pending'
           RETURNING *""",
        sid,
    )

    if row is None:
        return None

    # 同时将 rss_url 加入 module-a 的 RSS 抓取列表（如果 rss_url 存在且不在列表中）
    if row["rss_url"]:
        existing = await pool.fetchval(
            "SELECT COUNT(*) FROM recommended_sources WHERE rss_url=$1 AND id!=$2",
            row["rss_url"],
            sid,
        )
        if not existing:
            logger.info(
                f"[source_agent] 新 RSS 源已通过: {row['name']} -> {row['rss_url']}"
            )

    return _row_to_dict(row)


def _row_to_dict(row) -> dict:
    """将 asyncpg Row 转为字典"""
    return {
        "id": str(row["id"]),
        "tag": row["tag"],
        "tag_label": row["tag_label"] if "tag_label" in row.keys() else None,
        "name": row["name"],
        "url": row["url"],
        "rss_url": row["rss_url"],
        "quality_score": float(row["quality_score"]) if row["quality_score"] else None,
        "relevance_score": (
            float(row["relevance_score"]) if row["relevance_score"] else None
        ),
        "freshness_score": (
            float(row["freshness_score"]) if row["freshness_score"] else None
        ),
        "authority_score": (
            float(row["authority_score"]) if row["authority_score"] else None
        ),
        "status": row["status"],
        "discovered_at": (
            row["discovered_at"].isoformat() if row["discovered_at"] else None
        ),
        "approved_at": (
            row["approved_at"].isoformat() if row["approved_at"] else None
        ),
    }
