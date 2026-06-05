"""摘要生成 V7 — 内置标签清洗 + 代码分组建 section + LLM 专做头条"""
import asyncio
import json
import logging
import re
from .client import get_client, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)

# 标题相似度阈值（中文 2-gram Jaccard）
_TITLE_DUP_THRESHOLD = 0.30


def _tokenize_title(title: str) -> set[str]:
    """中文 2-gram + 英文分词"""
    clean = re.sub(r'[，。、；：？！\s\n\r·"\'「」『』【】《》（）\(\)\[\]{}]', '', title)
    tokens = set()
    for i in range(len(clean) - 1):
        tokens.add(clean[i:i+2])
    tokens.update(title.lower().split())
    return {t for t in tokens if not t.isdigit()}


def _is_title_dup(title: str, existing_titles: list[str]) -> bool:
    """检查标题是否与已有标题重复（中文 Jaccard 相似度）"""
    t1 = _tokenize_title(title)
    if not t1:
        return False
    for existing in existing_titles:
        t2 = _tokenize_title(existing)
        if not t2:
            continue
        overlap = len(t1 & t2)
        union = len(t1 | t2)
        if union > 0 and overlap / union > _TITLE_DUP_THRESHOLD:
            return True
    return False

_SECTION_LABELS = {
    "LLM": "大模型前沿", "Agent": "智能体动态", "开源": "开源工具",
    "工具": "开发者工具", "科技": "科技产业", "行业": "行业观察",
    "全球": "全球视野", "体育": "体育赛事", "安全": "安全快讯",
    "芯片": "硬件动态", "机器人": "机器人", "自动驾驶": "自动驾驶",
    "融资": "投融资", "医疗": "医疗健康",
}
_AI_TAGS = {"LLM", "Agent", "开源", "工具"}
_ALLOWED_TAGS = set(_SECTION_LABELS.keys())

_KEYWORD_MAP = [
    (re.compile(r"LLM|大模型|GPT|Claude|Gemini|模型|transformer", re.I), "LLM"),
    (re.compile(r"agent|智能体|代理|自主", re.I), "Agent"),
    (re.compile(r"开源|open.source|github|repo|gitlab", re.I), "开源"),
    (re.compile(r"工具|tool|插件|plugin|sdk|cli|api|框架|平台", re.I), "工具"),
    (re.compile(r"芯片|chip|nvidia|intel|amd|半导体|gpu|cpu|处理器", re.I), "芯片"),
    (re.compile(r"机器人|robot|automation|人形|机械", re.I), "机器人"),
    (re.compile(r"自动驾驶|self.driv|autonomous|无人驾驶", re.I), "自动驾驶"),
    (re.compile(r"融资|IPO|上市|投资|估值|b轮|a轮|天使轮|pre|种子轮|亿元|万美元", re.I), "融资"),
    (re.compile(r"体育|sport|nba|nfl|nhl|足球|篮球|比赛|赛事|冠军|联赛|决赛|锦标赛", re.I), "体育"),
    (re.compile(r"安全|security|漏洞|攻击|黑客|隐私|泄露|恶意|木马|勒索", re.I), "安全"),
    (re.compile(r"医疗|健康|health|药物|临床|医学|医院|治疗|疾病", re.I), "医疗"),
    (re.compile(r"国际|外交|贸易|制裁|关税|出口|进口|全球|world", re.I), "全球"),
    (re.compile(r"政策|监管|法规|政府|法院|法案|条例|规定|合规|审查", re.I), "行业"),
    (re.compile(r"科技|tech|AI|人工智能|发布|推出|发布|亮相|上线", re.I), "科技"),
    (re.compile(r"汽车|新能源|电动|ev|车展|汽车|充电|续航", re.I), "行业"),
    (re.compile(r"手机|数码|电子|消费|app|ios|android|鸿蒙|安卓", re.I), "工具"),
]


def _ensure_tags(items: list[dict]) -> list[dict]:
    """确保每条 item 都有标签。缺失时用关键词匹配兜底。"""
    for it in items:
        if it.get("tags") and len(it["tags"]) > 0:
            # 清洗: 只保留白名单中的标签
            it["tags"] = [t for t in it["tags"] if t in _ALLOWED_TAGS][:2]
        if not it.get("tags"):
            # 关键词匹配
            text = (it.get("title", "") + " " + (it.get("content") or ""))[:300]
            matched = []
            for pattern, tag in _KEYWORD_MAP:
                if pattern.search(text):
                    matched.append(tag)
                if len(matched) >= 2:
                    break
            if not matched:
                matched = ["科技"]
            it["tags"] = matched[:2]
    return items


def _build_sections(items: list[dict]) -> list[dict]:
    """按标签分组建 section，每个 item 只归入一个最匹配的 section"""
    by_tag: dict[str, list[dict]] = {}
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    dup_count = 0

    for it in sorted(items, key=lambda x: x.get("ai_score", 0), reverse=True):
        url = it.get("url", "")
        title = it.get("title", "")

        # ① URL 精确去重
        if url and url in seen_urls:
            dup_count += 1
            continue

        # ② 标题相似度去重
        if _is_title_dup(title, seen_titles):
            dup_count += 1
            logger.info("Section dedup: dropped '%s'", title[:50])
            continue

        if url:
            seen_urls.add(url)
        seen_titles.append(title)

        # ③ 选择最佳归属：优先非AI标签，每个item只进一个section
        tags = it.get("tags", [])
        if not tags:
            continue
        ai_tags = [t for t in tags if t in _AI_TAGS]
        non_ai_tags = [t for t in tags if t not in _AI_TAGS]
        # 优先非AI标签（避免所有新闻都堆到Agent/LLM里）
        primary = (non_ai_tags or ai_tags)[0]

        if primary not in by_tag:
            by_tag[primary] = []
        if len(by_tag[primary]) < 4:  # 每个section最多4条
            by_tag[primary].append(it)

    if dup_count > 0:
        logger.info("Section dedup: removed %d duplicate items", dup_count)

    groups = [(tag, its) for tag, its in by_tag.items() if tag not in _AI_TAGS]
    ai_groups = [(tag, its) for tag, its in by_tag.items() if tag in _AI_TAGS]
    groups += ai_groups[:2]
    groups = groups[:12]  # 尽量多覆盖标签（原来6→8→12）

    sections = []
    for tag, its in groups:
        if not its:  # 0条新闻的section不展示
            continue
        label = _SECTION_LABELS.get(tag, tag)
        items = []
        for it in its:
            items.append({
                "title": it["title"],
                "summary": (it.get("content") or "")[:100],
                "url": it.get("url", ""),
                "source": it.get("source", ""),
                "tags": it.get("tags", []),
                "score": it.get("ai_score", 0),
                "image_keywords": "",
            })
        sections.append({"section_title": label, "items": items})
    return sections


async def _call_llm(system: str, user: str) -> dict | None:
    try:
        resp = await get_client().chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning("LLM failed: %s", str(e)[:80])
        return None


async def summarize(items: list[dict], briefing_type: str) -> dict:
    """V7: 内置标签清洗 → 分组建 section → LLM 生成头条"""
    if not items:
        return {"headline": {}, "tl_dr": [], "sections": [], "key_takeaways": []}

    # ① 确保每条 item 都有标签（关键词匹配兜底）
    items = _ensure_tags(items)

    # ② 按标签分组构建 sections
    sections = _build_sections(items)
    if not sections:
        return {"headline": {}, "tl_dr": ["暂无资讯"], "sections": [], "key_takeaways": []}

    tag_names = [s["section_title"] for s in sections]
    total = sum(len(s["items"]) for s in sections)
    logger.info("Summarize: %d items → %d sections [%s] (%d items)",
                len(items), len(sections), ", ".join(tag_names), total)

    # ③ LLM 生成头条 + 趋势
    flat = []
    for sec in sections:
        for it in sec["items"]:
            flat.append(it)

    type_label = "早报" if briefing_type == "morning" else "晚报"
    hl_input = "\n".join(
        f"- {it['title']} ({','.join(it.get('tags',[]))})"
        for it in flat[:10]
    )

    result = await _call_llm(
        "你是科技资讯编辑。输出中文JSON。",
        f"{type_label}新闻：\n{hl_input}\n\n输出JSON: {{\"headline\":{{\"title\":\"\",\"summary\":\"\"}},\"tl_dr\":[\"要点1\",\"要点2\",\"要点3\"],\"key_takeaways\":[\"趋势1\",\"趋势2\"]}}",
    )

    if result:
        return {
            "headline": result.get("headline", {}),
            "tl_dr": result.get("tl_dr", []),
            "sections": sections,
            "key_takeaways": result.get("key_takeaways", []),
        }

    return {
        "headline": {"title": flat[0]["title"][:60] if flat else "", "summary": ""},
        "tl_dr": [it["title"][:60] for it in flat[:3]],
        "sections": sections,
        "key_takeaways": [],
    }
