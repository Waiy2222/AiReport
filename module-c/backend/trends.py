"""趋势数据 API 端点 — Phase 3 组员1 (V3: 按日总结事件 + AI 点评)

路由（在 main.py 中注册）：
- GET /api/trends/weekly     — 近 7 天每日事件时间线 + AI 点评
- GET /api/trends/tag/{tag}  — 单标签 7 天频次曲线
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

import httpx
from fastapi import APIRouter, HTTPException

# 加载项目根目录 .env
_ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["trends"])

# 数据库连接池（由 main.py startup 设置）
_db_pool = None

# 简单缓存：避免短时间内重复计算趋势
_cache: dict = {"ts": None, "data": None}
_CACHE_TTL = 300  # 5 分钟内返回缓存

# tag → 中文标签映射（与 module-b 14标签体系对齐）
_TAG_LABELS = {
    "LLM": "大模型", "Agent": "智能体", "开源": "开源项目",
    "工具": "开发工具", "科技": "科技动态", "行业": "行业观察",
    "全球": "全球视野", "体育": "体育赛事", "安全": "AI安全",
    "芯片": "芯片硬件", "机器人": "机器人", "自动驾驶": "自动驾驶",
    "融资": "融资并购", "医疗": "医疗健康",
}

# 中文星期映射
_WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def set_db_pool(pool):
    global _db_pool
    _db_pool = pool


# ── GET /api/trends/weekly ──────────────────────────────────────────


@router.get("/trends/weekly")
async def get_weekly_trends():
    """返回近 7 天每日事件时间线。从简报数据提取真实事件，按日分组。"""
    # 缓存：5分钟内重复请求直接返回
    now = datetime.now()
    if _cache["ts"] and _cache["data"] and (now - _cache["ts"]).seconds < _CACHE_TTL:
        return _cache["data"]

    today = date.today()
    start = today - timedelta(days=6)

    try:
        result = await _build_daily_timeline(start, today)
        _cache["ts"] = now
        _cache["data"] = result
        return result
    except Exception:
        logger.exception("get_weekly_trends failed, using mock fallback")
        return _mock_daily_timeline(today, start)


async def _build_daily_timeline(start: date, today: date) -> dict:
    """从 DB 简报中提取近 7 天每日头条事件"""
    if _db_pool is None:
        return _mock_daily_timeline(today, start)

    rows = await _db_pool.fetch(
        """SELECT id, type, date, sections, raw_stats
           FROM briefings
           WHERE date >= $1 AND date <= $2 AND language = 'zh'
           ORDER BY date DESC, type ASC""",
        start, today,
    )

    if not rows:
        return _mock_daily_timeline(today, start)

    # 按日期分组：合并每天早报+晚报的 items
    daily_events = defaultdict(list)
    for r in rows:
        day = r["date"].isoformat()
        sections = r["sections"]
        if isinstance(sections, str):
            sections = json.loads(sections)
        if not isinstance(sections, list):
            continue

        for section in sections:
            for item in (section.get("items") or []):
                if not item.get("title"):
                    continue
                daily_events[day].append({
                    "title": item.get("title", ""),
                    "summary": item.get("summary", "")[:120],
                    "source": item.get("source", ""),
                    "url": item.get("url", ""),
                    "score": item.get("score", 0),
                    "tags": item.get("tags", []),
                    "image_url": item.get("image_url", ""),
                })

    # 构建时间线：每天最多取 4 条头条
    timeline = []
    all_tags = []
    for i in range(6, -1, -1):
        day = (start + timedelta(days=i)).isoformat()
        events = sorted(daily_events.get(day, []), key=lambda x: x["score"], reverse=True)[:4]
        if events:
            for e in events:
                all_tags.extend(e.get("tags", []))
            d = date.fromisoformat(day)
            day_label = "今天" if d == today else "昨天" if d == today - timedelta(days=1) else _WEEKDAY_ZH[d.weekday()]
            date_display = f"{d.month}月{d.day}日"
            timeline.append({
                "date": day,
                "day_label": day_label,
                "date_display": date_display,
                "event_count": len(daily_events.get(day, [])),
                "ai_summary": "",  # 先占位，下面填充
                "events": events,
            })

    # 计算热门标签
    tag_counts = defaultdict(int)
    for t in all_tags:
        tag_counts[t] += 1
    hot_tags = sorted(
        [{"tag": t, "label_zh": _TAG_LABELS.get(t, t), "count": c}
         for t, c in tag_counts.items()],
        key=lambda x: x["count"], reverse=True,
    )[:8]

    # 为最近3天（timeline 按最新在前排序）生成 AI 点评（并行加速）
    commentary_tasks = []
    for i in range(min(3, len(timeline))):
        day = timeline[i]
        day_tags = list(set(t for e in day["events"] for t in e.get("tags", [])))
        commentary_tasks.append(
            _ai_commentary(day["day_label"], day["date_display"], day["events"], day_tags)
        )
    commentaries = await asyncio.gather(*commentary_tasks)
    for i in range(min(3, len(timeline))):
        day = timeline[i]
        commentary = commentaries[i] if i < len(commentaries) else ""
        day["ai_summary"] = commentary
        logger.info("Commentary for %s: %s...", day["date_display"], commentary[:80] if commentary else "(empty)")

    # 生成周综述
    weekly_commentary = await _weekly_overview(timeline, hot_tags)

    return {
        "period": f"{start.isoformat()} ~ {today.isoformat()}",
        "daily_timeline": timeline,
        "hot_tags": hot_tags,
        "weekly_commentary": weekly_commentary,
        "total_events": sum(len(d.get("events", [])) for d in timeline),
        "generated_at": datetime.utcnow().isoformat() + "+00:00",
    }


def _generate_day_summary(day: str, events: list[dict]) -> str:
    """基于当天头条生成简短摘要（规则引擎）"""
    if not events:
        return ""
    top_tags = defaultdict(int)
    for e in events:
        for t in e.get("tags", []):
            top_tags[t] += 1
    hot = [t for t, _ in sorted(top_tags.items(), key=lambda x: -x[1])[:3]]
    top = events[0]
    title = top.get("title", "")[:50]
    tag_str = "、".join(hot) if hot else ""
    return f"今日焦点：{title}" + (f"（热门标签：{tag_str}）" if tag_str else "")


# DeepSeek API 配置（与 module-b 共用同一 API Key）
_DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
_DEEPSEEK_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")


async def _ai_commentary(day_label: str, date_display: str, events: list[dict], all_tags: list[str]) -> str:
    """调用 DeepSeek 为某一天生成 1-2 句趋势点评"""
    if not _DEEPSEEK_KEY or not events:
        return _generate_day_summary("", events)

    titles = "\n".join(f"- {e['title'][:60]}" for e in events[:6])
    tags_str = "、".join(all_tags[:8]) if all_tags else "综合"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_DEEPSEEK_URL}/chat/completions",
                headers={"Authorization": f"Bearer {_DEEPSEEK_KEY}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "你是AI/科技媒体主编。只点评AI、大模型、智能体、开源、芯片、机器人等科技领域。完全忽略体育、娱乐、社会新闻。用1-2句话洞察科技行业的真正信号，不是罗列新闻。"},
                        {"role": "user", "content": f"{date_display}（{day_label}）科技事件：\n{titles}\n\n只选1-2条最值得关注的AI/科技事件点评（忽略体育和娱乐）："},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 100,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("AI commentary failed: %s", str(e)[:60])

    return _generate_day_summary("", events)


async def _weekly_overview(timeline: list[dict], hot_tags: list[dict]) -> str:
    """生成一周趋势总评"""
    if not _DEEPSEEK_KEY or not timeline:
        return ""

    days_summary = "\n".join(
        f"{d['date_display']}: {d['event_count']}条新闻, 焦点: {d['ai_summary'][:50]}"
        for d in timeline[-3:]
    )
    tags_str = "、".join(f"{t['label_zh']}({t['count']})" for t in hot_tags[:5])

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_DEEPSEEK_URL}/chat/completions",
                headers={"Authorization": f"Bearer {_DEEPSEEK_KEY}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "你是AI/科技媒体主编。只分析AI、大模型、智能体、芯片、机器人等科技领域的趋势。完全忽略体育、娱乐、消费类新闻。"},
                        {"role": "user", "content": f"本周AI/科技热点：{tags_str}\n近三天：\n{days_summary}\n\n用2-3句话总结本周AI/科技领域的核心变化："},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 150,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("Weekly overview failed: %s", str(e)[:60])

    return ""


# ── GET /api/trends/tag/{tag} ───────────────────────────────────────


@router.get("/trends/tag/{tag}")
async def get_tag_trend(tag: str):
    """返回单标签的 7 天频次曲线。"""
    days = 7
    today = date.today()
    start = today - timedelta(days=days - 1)
    dates = [(start + timedelta(days=i)).strftime("%m-%d") for i in range(days)]

    # 尝试从 DB 获取真实数据
    if _db_pool:
        try:
            rows = await _db_pool.fetch(
                """SELECT date, sections FROM briefings
                   WHERE date >= $1 AND date <= $2 AND language = 'zh'
                   ORDER BY date ASC""",
                start, today,
            )
            chart = [0] * days
            date_index = {(start + timedelta(days=i)).isoformat(): i for i in range(days)}
            for r in rows:
                di = date_index.get(r["date"].isoformat())
                if di is None:
                    continue
                sections = r["sections"]
                if isinstance(sections, str):
                    sections = json.loads(sections)
                for section in sections:
                    for item in (section.get("items") or []):
                        if tag in (item.get("tags") or []):
                            chart[di] += 1

            if sum(chart) == 0:
                raise HTTPException(404, f"tag '{tag}' not found in recent briefings")

            return {
                "tag": tag,
                "label_zh": _TAG_LABELS.get(tag, tag),
                "chart": chart,
                "dates": dates,
            }
        except HTTPException:
            raise
        except Exception:
            logger.exception("get_tag_trend DB query failed, using mock")

    # Mock 回退
    mock_charts = {
        "LLM": [5, 6, 7, 8, 9, 10, 11],
        "Agent": [3, 4, 5, 7, 8, 10, 11],
        "多模态": [4, 5, 5, 6, 7, 8, 10],
        "RAG": [5, 5, 4, 3, 3, 2, 2],
    }
    if tag in mock_charts:
        return {
            "tag": tag,
            "label_zh": _TAG_LABELS.get(tag, tag),
            "chart": mock_charts[tag],
            "dates": dates,
        }
    raise HTTPException(404, f"tag '{tag}' not found")


# ── Mock (fallback when no DB) ──────────────────────────────────────


def _mock_daily_timeline(today: date, start: date) -> dict:
    """内置 mock 数据：按日总结事件，不依赖 trend_agent。"""
    def _make_events(days_ago: int, titles: list[str]) -> list[dict]:
        d = today - timedelta(days=days_ago)
        return [
            {"title": t, "summary": t, "source": "AI早报", "url": "",
             "score": 8.0, "tags": ["LLM", "AI"],
             "image_url": ""}
            for t in titles
        ]

    mock_data = [
        (0, ["OpenAI CFO 透露 AI 硬件设备年底发布", "字节 AI 公布 2026 四大战略：追赶世界模型", "英伟达发布完全开放全模态物理 AI 模型 Cosmos 3", "AI 编程工具遭黑客利用，伪造网站传播木马"]),
        (1, ["谷歌发布 Gemini 3，多模态能力全面升级", "微软 Copilot 整合 GPT-5，企业版定价公布", "特斯拉 FSD V14 获中国监管部门批准"]),
        (2, ["Claude 4 发布，长上下文突破 500K tokens", "开源模型 Llama 4 发布，性能对标 GPT-5", "全球 AI 安全峰会在巴黎召开，28国签署协议"]),
        (3, ["AI 代理框架 AutoGPT v2 发布，支持多模态任务", "百度文心一言 App 月活突破 5000 万", "欧盟 AI 法案正式生效，全球首个全面监管框架"]),
        (4, ["Mistral 发布 MoE 新模型，推理速度提升 3 倍", "国内 AI 芯片公司壁仞科技完成 20 亿融资", "DeepMind AlphaFold 4 破解蛋白质动态折叠"]),
        (5, ["苹果 WWDC 重点：设备端 AI Siri 3.0", "NVIDIA 黄仁勋台北演讲：AI 工厂时代来临"]),
        (6, ["HuggingFace 推出 AI 伦理评估排行榜", "中国信通院发布 AI 安全白皮书 2026"]),
    ]

    timeline = []
    for days_ago, titles in mock_data:
        d = today - timedelta(days=days_ago)
        events = _make_events(days_ago, titles)
        day_label = "今天" if days_ago == 0 else "昨天" if days_ago == 1 else _WEEKDAY_ZH[d.weekday()]
        timeline.append({
            "date": d.isoformat(),
            "day_label": day_label,
            "date_display": f"{d.month}月{d.day}日",
            "event_count": len(events),
            "ai_summary": _generate_day_summary(d.isoformat(), events),
            "events": events,
        })

    hot_tags = [
        {"tag": "LLM", "label_zh": "大模型", "count": 28},
        {"tag": "Agent", "label_zh": "智能体", "count": 15},
        {"tag": "开源", "label_zh": "开源", "count": 12},
        {"tag": "基础设施", "label_zh": "基础设施", "count": 9},
        {"tag": "多模态", "label_zh": "多模态", "count": 8},
        {"tag": "AI安全", "label_zh": "AI安全", "count": 6},
        {"tag": "芯片", "label_zh": "芯片", "count": 5},
        {"tag": "机器人", "label_zh": "机器人", "count": 4},
    ]

    return {
        "period": f"{start.isoformat()} ~ {today.isoformat()}",
        "daily_timeline": timeline,
        "hot_tags": hot_tags,
        "total_events": sum(len(d.get("events", [])) for d in timeline),
        "generated_at": datetime.utcnow().isoformat() + "+00:00",
    }


# ── GET /api/trends/tag/{tag} ───────────────────────────────────────


@router.get("/trends/tag/{tag}")
async def get_tag_trend(tag: str):
    """返回单标签的 7 天频次曲线。"""
    days = 7
    today = date.today()
    start = today - timedelta(days=days - 1)
    dates = [(start + timedelta(days=i)).strftime("%m-%d") for i in range(days)]

    # 尝试从 DB 获取真实数据
    if _db_pool:
        try:
            rows = await _db_pool.fetch(
                """SELECT date, sections FROM briefings
                   WHERE date >= $1 AND date <= $2 AND language = 'zh'
                   ORDER BY date ASC""",
                start, today,
            )
            chart = [0] * days
            date_index = {(start + timedelta(days=i)).isoformat(): i for i in range(days)}
            for r in rows:
                di = date_index.get(r["date"].isoformat())
                if di is None:
                    continue
                sections = r["sections"]
                if isinstance(sections, str):
                    sections = json.loads(sections)
                for section in sections:
                    for item in (section.get("items") or []):
                        if tag in (item.get("tags") or []):
                            chart[di] += 1

            # 检查标签是否存在
            if sum(chart) == 0:
                raise HTTPException(404, f"tag '{tag}' not found in recent briefings")

            return {
                "tag": tag,
                "label_zh": _TAG_LABELS.get(tag, tag),
                "chart": chart,
                "dates": dates,
            }
        except HTTPException:
            raise
        except Exception:
            logger.exception("get_tag_trend DB query failed, using mock")

    # Mock 回退
    mock_charts = {
        "LLM": [5, 6, 7, 8, 9, 10, 11],
        "Agent": [3, 4, 5, 7, 8, 10, 11],
        "多模态": [4, 5, 5, 6, 7, 8, 10],
        "RAG": [5, 5, 4, 3, 3, 2, 2],
    }
    if tag in mock_charts:
        return {
            "tag": tag,
            "label_zh": _TAG_LABELS.get(tag, tag),
            "chart": mock_charts[tag],
            "dates": dates,
        }
    raise HTTPException(404, f"tag '{tag}' not found")
