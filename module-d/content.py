"""简报内容拆解 — 从 briefings 表数据生成标题/导语/正文/Markdown/HTML"""
import logging
from uuid import UUID
from typing import Any

logger = logging.getLogger(__name__)


def extract_title(briefing: dict) -> str:
    """根据 type + date 生成标题"""
    type_map = {"morning": "AI 资讯早报", "evening": "AI 资讯晚报"}
    prefix = type_map.get(briefing.get("type", ""), "AI 资讯简报")
    date_str = briefing.get("date", "")
    return f"{prefix} {date_str}"


def extract_intro(briefing: dict) -> list[str]:
    """从 tl_dr 取前 3 条作为导语"""
    tl_dr = briefing.get("tl_dr", [])
    if not tl_dr:
        return []
    return tl_dr[:3]


def extract_body(briefing: dict, max_items: int = 15) -> list[dict]:
    """从 sections 展开所有 items，按 score 降序截取"""
    sections = briefing.get("sections", [])
    if not sections:
        return []

    all_items: list[dict] = []
    for section in sections:
        items = section.get("items", [])
        for item in items:
            item_copy = dict(item)
            item_copy["_section_title"] = section.get("title", "")
            all_items.append(item_copy)

    # 按 score 降序（无 score 的排最后）
    all_items.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)

    return all_items[:max_items]


def format_markdown(briefing: dict) -> str:
    """生成 Markdown 全文（用于知乎/CSDN）"""
    title = extract_title(briefing)
    lines = [f"# {title}", ""]

    # 导语
    intro = extract_intro(briefing)
    if intro:
        for point in intro:
            lines.append(f"> {point}")
        lines.append("")

    # 正文 sections
    sections = briefing.get("sections", [])
    for section in sections:
        section_title = section.get("title", "")
        if section_title:
            lines.append(f"## {section_title}")
            lines.append("")

        items = section.get("items", [])
        for item in items:
            item_title = item.get("title", "")
            summary = item.get("summary", "")
            url = item.get("url", "")
            score = item.get("score", "")
            tags = item.get("tags", [])

            tag_str = " ".join(f"`{t}`" for t in tags) if tags else ""
            score_str = f"**评分：{score}/10**" if score else ""

            # 标题 + 链接
            if url:
                lines.append(f"- [{item_title}]({url})")
            else:
                lines.append(f"- **{item_title}**")

            # 摘要
            if summary:
                lines.append(f"  {summary}")

            # 标签 + 评分
            extra = " | ".join(filter(None, [tag_str, score_str]))
            if extra:
                lines.append(f"  _{extra}_")

            lines.append("")

    # key_takeaways
    takeaways = briefing.get("key_takeaways", [])
    if takeaways:
        lines.append("---")
        lines.append("")
        lines.append("## 💡 关键趋势")
        lines.append("")
        for t in takeaways:
            lines.append(f"- {t}")
        lines.append("")

    return "\n".join(lines)


def format_html(briefing: dict) -> str:
    """生成 HTML 全文（用于微信公众号预览）"""
    title = extract_title(briefing)
    sections_data = briefing.get("sections", [])
    takeaways = briefing.get("key_takeaways", [])

    parts = [f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title></head><body>"]

    # 标题
    parts.append(f"<h1>{title}</h1>")

    # 导语
    intro = extract_intro(briefing)
    if intro:
        parts.append("<blockquote>")
        for point in intro:
            parts.append(f"<p>{point}</p>")
        parts.append("</blockquote>")

    # sections
    for section in sections_data:
        section_title = section.get("title", "")
        if section_title:
            parts.append(f"<h2>{section_title}</h2>")

        items = section.get("items", [])
        for item in items:
            item_title = item.get("title", "")
            summary = item.get("summary", "")
            url = item.get("url", "")
            score = item.get("score", "")
            tags = item.get("tags", [])

            parts.append("<div class='card'>")
            if url:
                parts.append(f"<h3><a href='{url}'>{item_title}</a></h3>")
            else:
                parts.append(f"<h3>{item_title}</h3>")

            if score:
                parts.append(f"<span class='score'>{score}/10</span>")

            if summary:
                parts.append(f"<p>{summary}</p>")

            if tags:
                tag_html = "".join(f"<span class='tag'>{t}</span>" for t in tags)
                parts.append(f"<div class='tags'>{tag_html}</div>")

            parts.append("</div>")

    # takeaways
    if takeaways:
        parts.append("<h2>关键趋势</h2><ul>")
        for t in takeaways:
            parts.append(f"<li>{t}</li>")
        parts.append("</ul>")

    parts.append("</body></html>")
    return "\n".join(parts)


async def get_briefing(pool, briefing_id: UUID) -> dict | None:
    """从 DB 读取完整简报数据"""
    from asyncpg import Pool

    row = await pool.fetchrow(
        "SELECT * FROM briefings WHERE id=$1", briefing_id
    )
    if not row:
        return None
    return dict(row)
