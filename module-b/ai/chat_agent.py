"""新闻对话 Agent — 检索简报库 + 实时抓取 + DeepSeek 生成回答"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta

# 确保 module-b/ai 在 sys.path 中（兼容 importlib 导入和直接运行）
_cur_dir = os.path.dirname(os.path.abspath(__file__))
if _cur_dir not in sys.path:
    sys.path.insert(0, _cur_dir)

from client import get_client, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)

# 对话历史上限
MAX_HISTORY = 20

# 婉拒模板
REJECT_MESSAGE = "抱歉，我是新闻助手，只能回答新闻相关的问题哦～"

# 检索最低条数阈值（不足时触发实时抓取）
MIN_RESULTS = 3

CHAT_SYSTEM_PROMPT = """你是一个专业的AI新闻助手，运行在微信小程序中。你的职责是根据已有的新闻数据回答用户的问题。

## 核心规则
1. 只回答与新闻相关的问题。如果用户的问题与新闻无关（闲聊、技术咨询、编程问题、个人建议等），礼貌回复："抱歉，我是新闻助手，只能回答新闻相关的问题哦～"
2. 回答必须基于下方提供的新闻素材，不要编造不存在的信息。
3. 每条回答必须注明信息来源（新闻标题）。
4. 如果新闻素材中没有相关内容，诚实告知："我目前没有找到与您问题相关的新闻，请换个话题试试～"
5. 回答简洁有力，200字以内。
6. 使用中文回答。

## 当前时间
{current_time}
"""


async def extract_keywords(query: str) -> list[str]:
    """从用户问题中提取搜索关键词"""
    client = get_client()
    prompt = f"""从以下用户问题中提取 2-5 个搜索关键词，用于检索新闻数据库。
只返回关键词，用逗号分隔，不要解释。

用户问题: {query}

关键词:"""

    try:
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=50,
        )
        text = resp.choices[0].message.content.strip()
        keywords = [kw.strip() for kw in text.replace("；", ",").replace("、", ",").split(",") if kw.strip()]
        return keywords[:5]
    except Exception as e:
        logger.warning("Keyword extraction failed: %s", e)
        # 回退：直接用原始问题分词
        return [query[:30]]


async def _search_briefings(db_pool, keywords: list[str], days: int = 7) -> list[dict]:
    """从 briefings 表中检索相关新闻，返回去重后的新闻条目列表"""
    cutoff = datetime.now() - timedelta(days=days)
    results = []
    seen_urls = set()

    for kw in keywords:
        try:
            rows = await db_pool.fetch(
                """SELECT sections, date, type FROM briefings
                   WHERE date >= $1
                   AND tl_dr::text ILIKE $2
                   ORDER BY date DESC LIMIT 10""",
                cutoff.date(),
                f"%{kw}%",
            )
        except Exception as e:
            logger.warning("DB search failed for keyword '%s': %s", kw, e)
            continue

        for row in rows:
            sections = row["sections"]
            if isinstance(sections, str):
                try:
                    sections = json.loads(sections)
                except (json.JSONDecodeError, TypeError):
                    continue

            for section in (sections or []):
                for item in (section.get("items") or []):
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append({
                            "title": item.get("title", ""),
                            "content": (item.get("content") or "")[:200],
                            "url": url,
                            "source": item.get("source", ""),
                            "tags": item.get("tags", []),
                            "score": item.get("score", 0),
                            "date": str(row["date"]),
                        })

        if len(results) >= 10:
            break

    return results


async def _fetch_live(keywords: list[str]) -> list[dict]:
    """调 module-a 的 RSS scraper 按关键词实时抓取"""
    import importlib.util

    agent_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "module-a", "scrapers", "rss.py",
    )

    if not os.path.exists(agent_path):
        logger.warning("RSS scraper not found at %s", agent_path)
        return []

    try:
        spec = importlib.util.spec_from_file_location("rss_scraper", agent_path)
        rss_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rss_module)

        # 使用 RSS scraper 的 fetch_rss 函数，抓取最近 24 小时的新闻
        since = datetime.now() - timedelta(hours=24)
        items = await rss_module.fetch_rss(since, None)

        # 按关键词过滤
        results = []
        for item in items:
            text = (item.get("title", "") + " " + item.get("content", "")).lower()
            if any(kw.lower() in text for kw in keywords):
                results.append({
                    "title": item.get("title", ""),
                    "content": (item.get("content") or "")[:200],
                    "url": item.get("url", ""),
                    "source": item.get("source", ""),
                    "tags": item.get("tags", []),
                })

        return results[:10]
    except Exception as e:
        logger.warning("Live fetch failed: %s", e)
        return []


async def _check_news_relevance(query: str) -> bool:
    """快速检测用户问题是否与新闻相关"""
    client = get_client()
    prompt = f"""判断以下用户输入是否与"新闻"相关（询问新闻事件、行业动态、科技进展、公司动向等）。
只回复 "YES" 或 "NO"，不要解释。

用户输入: {query}

相关性:"""

    try:
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=5,
        )
        result = resp.choices[0].message.content.strip().upper()
        return "YES" in result
    except Exception:
        return True  # API 失败默认放行，由后续 prompt 兜底


async def chat(query: str, history: list[dict], db_pool=None) -> dict:
    """主入口：处理用户消息，返回 AI 回复 + 新闻来源

    Args:
        query: 用户问题
        history: 对话历史 [{"role": "user"/"assistant", "content": "..."}]
        db_pool: 数据库连接池（可为 None，跳过 DB 检索）

    Returns:
        {"reply": "AI 回复", "sources": [{"title":"...","url":"...","source":"..."}]}
    """
    # ① 非新闻检测
    is_news = await _check_news_relevance(query)
    if not is_news:
        return {"reply": REJECT_MESSAGE, "sources": []}

    # ② 提取关键词
    keywords = await extract_keywords(query)
    logger.info("Chat keywords for '%s': %s", query[:50], keywords)

    # ③ 检索简报库
    sources = []
    if db_pool:
        try:
            sources = await _search_briefings(db_pool, keywords)
        except Exception as e:
            logger.warning("DB search failed: %s", e)

    # ④ 结果不足 → 实时抓取
    if len(sources) < MIN_RESULTS:
        logger.info("Only %d results from DB, fetching live...", len(sources))
        live_sources = await _fetch_live(keywords)
        seen_urls = {s.get("url") for s in sources}
        for ls in live_sources:
            if ls.get("url") not in seen_urls:
                sources.append(ls)
                seen_urls.add(ls.get("url"))

    # ⑤ 无结果时直接返回
    if not sources:
        return {
            "reply": "我目前没有找到与您问题相关的新闻，请换个话题试试～",
            "sources": [],
        }

    # ⑥ 组装上下文
    sources_text = "\n\n".join(
        f"[{i+1}] {s['title']}\n   来源: {s.get('source', '未知')}\n   日期: {s.get('date', '未知')}\n   摘要: {s.get('content', '')[:150]}"
        for i, s in enumerate(sources[:15])
    )

    # ⑦ 截断历史
    recent_history = history[-MAX_HISTORY:] if len(history) > MAX_HISTORY else history

    # ⑧ 构建 messages
    messages = [
        {
            "role": "system",
            "content": CHAT_SYSTEM_PROMPT.format(
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M")
            ),
        },
    ]
    # 注入历史
    for h in recent_history:
        messages.append({"role": h["role"], "content": h["content"]})
    # 注入新闻素材 + 用户问题
    messages.append({
        "role": "user",
        "content": f"""## 相关新闻素材
{sources_text}

## 用户问题
{query}

请基于上述新闻素材回答用户问题，并引用具体新闻来源。""",
    })

    # ⑨ 调用 DeepSeek 生成回答
    client = get_client()
    try:
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=400,
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Chat generation failed: %s", e)
        reply = "抱歉，AI 服务暂时不可用，请稍后再试。"

    # ⑩ 构建返回
    return {
        "reply": reply,
        "sources": [
            {"title": s["title"], "url": s.get("url", ""), "source": s.get("source", "")}
            for s in sources[:10]
        ],
    }
