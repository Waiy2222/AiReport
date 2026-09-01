"""摘要生成 V8 — 内置标签清洗 + 代码分组建 section + LLM 专做头条 + 个性化支持"""
import asyncio
import json
import logging
import re
from .client import get_client, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)

_TITLE_DUP_THRESHOLD = 0.30


def _tokenize_title(title: str) -> set[str]:
    clean = re.sub(r'[，。、；：？！\s\n\r·"\'「」『』【】《》（）\(\)\[\]{}]', '', title)
    tokens = set()
    for i in range(len(clean) - 1):
        tokens.add(clean[i:i+2])
    tokens.update(title.lower().split())
    return {t for t in tokens if not t.isdigit()}


def _is_title_dup(title: str, existing_titles: list[str]) -> bool:
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
    "电子竞技": "电子竞技", "绘画": "绘画艺术", "登山": "登山户外",
    "影视": "影视推荐", "音乐": "音乐产业", "咖啡": "咖啡烘焙",
    "美食": "美食旅游", "创业": "创业农业",
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
    (re.compile(r"融资|IPO|上市|投资|估值|b轮|a轮|亿元|万美元", re.I), "融资"),
    (re.compile(r"sport|nba|nfl|nhl|足球|篮球|网球|棒球|橄榄球|斯诺克|田径|游泳|体操|乒乓球|羽毛球|排球|冬奥|奥运", re.I), "体育"),
    (re.compile(r"安全|security|漏洞|攻击|黑客|隐私", re.I), "安全"),
    (re.compile(r"医疗|健康|health|药物|临床|医学", re.I), "医疗"),
    (re.compile(r"国际|外交|贸易|全球|world", re.I), "全球"),
    (re.compile(r"政策|监管|法规|政府|法案|合规", re.I), "行业"),
    (re.compile(r"科技|tech|AI|人工智能|发布", re.I), "科技"),
    # 用户兴趣
    (re.compile(r"电竞|电子竞技|英雄联盟|DOTA2|王者荣耀|LPL|LCK|Valorant|esports", re.I), "电子竞技"),
    (re.compile(r"绘画|艺术|插画|画廊|美术|展览|数字艺术|当代艺术", re.I), "绘画"),
    (re.compile(r"登山|徒步|户外|攀岩|越野|探险|极限运动|滑雪|冲浪", re.I), "登山"),
    (re.compile(r"电影|电视剧|影视|纪录片|票房|电影节|动画", re.I), "影视"),
    (re.compile(r"音乐|演唱会|音乐节|专辑|流行音乐|摇滚|嘻哈|电子音乐", re.I), "音乐"),
    (re.compile(r"咖啡|烘焙|甜点|面包|下午茶|精品咖啡|蛋糕", re.I), "咖啡"),
    (re.compile(r"美食|旅游|旅行|自驾|酒店|米其林|探店|攻略", re.I), "美食"),
    (re.compile(r"创业|农业|乡村|智慧农业|电商|新农人|有机|农产品", re.I), "创业"),
    (re.compile(r"环保|环境|碳中和|气候|新能源|绿色|可持续发展", re.I), "行业"),
    (re.compile(r"书法|书法艺术|毛笔|碑帖|书法展|国画|篆刻", re.I), "绘画"),
]


def _ensure_tags(items: list[dict]) -> list[dict]:
    for it in items:
        if it.get("tags") and len(it["tags"]) > 0:
            it["tags"] = [t for t in it["tags"] if t in _ALLOWED_TAGS][:2]
        if not it.get("tags"):
            text = (it.get("title", "") + " " + (it.get("content") or ""))[:300]
            matched = []
            for pattern, tag in _KEYWORD_MAP:
                if pattern.search(text):
                    matched.append(tag)
                if len(matched) >= 2:
                    break
            it["tags"] = matched[:2] if matched else []
    return items


def _build_sections(items: list[dict]) -> list[dict]:
    by_tag: dict[str, list[dict]] = {}
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    dup_count = 0

    for it in sorted(items, key=lambda x: x.get("ai_score", 0), reverse=True):
        url = it.get("url", "")
        title = it.get("title", "")
        if url and url in seen_urls:
            dup_count += 1
            continue
        if _is_title_dup(title, seen_titles):
            dup_count += 1
            continue
        if url:
            seen_urls.add(url)
        seen_titles.append(title)

        tags = it.get("tags", [])
        if not tags:
            continue
        # 优先使用 _force_tag（由 _distribute_interest_tags 分配）
        force_tag = it.get("_force_tag")
        if force_tag and force_tag in _ALLOWED_TAGS:
            primary = force_tag
        else:
            ai_tags = [t for t in tags if t in _AI_TAGS]
            non_ai_tags = [t for t in tags if t not in _AI_TAGS]
            primary = (non_ai_tags or ai_tags)[0]

        if primary not in by_tag:
            by_tag[primary] = []
        if len(by_tag[primary]) < 8:
            by_tag[primary].append(it)

    if dup_count > 0:
        logger.info("Section dedup: removed %d duplicate items", dup_count)

    groups = [(tag, its) for tag, its in by_tag.items() if tag not in _AI_TAGS]
    ai_groups = [(tag, its) for tag, its in by_tag.items() if tag in _AI_TAGS]
    groups += ai_groups[:2]
    groups = groups[:12]

    sections = []
    for tag, its in groups:
        if not its:
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
        sections.append({"section_title": label, "tag": tag, "items": items})
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


def _build_interest_sections(items: list[dict], interest_tags: list[str]) -> list[dict]:
    """个性化简报：用用户兴趣关键词直接分组，不经过14标签体系"""
    by_keyword: dict[str, list[dict]] = {t: [] for t in interest_tags}
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    unmatched: list[dict] = []

    for it in sorted(items, key=lambda x: x.get("ai_score", 0), reverse=True):
        url = it.get("url", "")
        title = it.get("title", "")
        if url and url in seen_urls:
            continue
        if _is_title_dup(title, seen_titles):
            continue
        if url:
            seen_urls.add(url)
        seen_titles.append(title)

        text = (title + " " + (it.get("content") or "")).lower()
        # 找最佳匹配的兴趣关键词
        best_kw, best_score = None, 0
        for kw in interest_tags:
            if kw.lower() in text:
                score = len(kw)  # 更长关键词匹配更精准
                if score > best_score:
                    best_kw, best_score = kw, score
        if best_kw and len(by_keyword[best_kw]) < 8:
            by_keyword[best_kw].append(it)
        else:
            unmatched.append(it)

    # 未匹配的按标题关键词二次分配
    for it in unmatched:
        text = (it.get("title", "") + " " + (it.get("content") or "")).lower()
        for kw in interest_tags:
            if len(by_keyword[kw]) < 6:
                # 宽松匹配：2-gram
                for i in range(len(kw) - 1):
                    if kw[i:i+2] in text:
                        by_keyword[kw].append(it)
                        break
                else:
                    continue
                break

    sections = []
    for kw in interest_tags:
        its = by_keyword[kw]
        if len(its) >= 2:
            sections.append({"section_title": kw, "tag": kw, "items": its})

    logger.info("Interest sections: %d keywords → %d sections (%d unmatched)",
                len(interest_tags), len(sections), len(unmatched))
    return sections


def _distribute_interest_tags(items: list[dict], interest_tags: list[str]):
    """个性化简报：为无标签item按兴趣分配标签，确保每个兴趣都有内容。"""
    if not interest_tags or len(interest_tags) <= 1:
        return

    tag_counts = {t: 0 for t in interest_tags}
    untagged = []
    for it in items:
        item_tags = set(it.get("tags", []))
        matched = False
        for t in interest_tags:
            if t in item_tags:
                tag_counts[t] += 1
                matched = True
        if not matched:
            untagged.append(it)

    if not untagged:
        return

    for it in untagged:
        min_tag = min(tag_counts, key=tag_counts.get)
        it["_force_tag"] = min_tag
        tag_counts[min_tag] += 1

    logger.info("Distributed %d untagged items across interests: %s",
                len(untagged), {t: c for t, c in tag_counts.items()})


async def summarize(items: list[dict], briefing_type: str,
                    interest_tags: list[str] | None = None,
                    interest_text: str = "") -> dict:
    """V8: 内置标签清洗 → 分组建 section → LLM 生成头条（支持个性化兴趣覆盖）"""
    if not items:
        return {"headline": {}, "tl_dr": [], "sections": [], "key_takeaways": []}

    # 个性化简报：直接用用户兴趣关键词分组，不走14标签体系
    if interest_tags and len(interest_tags) >= 2:
        sections = _build_interest_sections(items, interest_tags)
    else:
        # 通用简报：走传统标签体系
        items = _ensure_tags(items)
        sections = _build_sections(items)
    if not sections:
        return {"headline": {}, "tl_dr": ["暂无资讯"], "sections": [], "key_takeaways": []}

    tag_names = [s["section_title"] for s in sections]
    total = sum(len(s["items"]) for s in sections)
    logger.info("Summarize: %d items -> %d sections [%s] (%d items)",
                len(items), len(sections), ", ".join(tag_names), total)

    # LLM 生成头条 + TL;DR
    flat = []
    for sec in sections:
        for it in sec["items"]:
            flat.append(it)

    type_label = "早报" if briefing_type == "morning" else "晚报"
    hl_input = "\n".join(f"- {it['title'][:50]}" for it in flat[:8])

    interest_hint = ""
    if interest_tags:
        interest_hint = f"\n用户兴趣：{'、'.join(interest_tags)}"

    result = await _call_llm(
        "你是新闻编辑。输出中文JSON。",
        f"{type_label}：\n{hl_input}\n{interest_hint}\nJSON: {{\"headline\":{{\"title\":\"\",\"summary\":\"\"}},\"tl_dr\":[],\"key_takeaways\":[]}}",
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
