"""HTML 模板渲染 — 微信公众号文章风格（移动端适配 + 深色模式）"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── CSS 样式（内嵌，微信公众号不支持外链） ──
_CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #f5f5f5; color: #333; line-height: 1.8; padding: 16px;
    max-width: 680px; margin: 0 auto;
}
h1 { font-size: 22px; color: #1a1a1a; margin: 20px 0 12px; font-weight: 700; }
h2 {
    font-size: 18px; color: #2d6cc9; margin: 24px 0 12px; padding-left: 10px;
    border-left: 4px solid #2d6cc9;
}
h3 { font-size: 16px; margin-bottom: 6px; }
h3 a { color: #1a1a1a; text-decoration: none; }
h3 a:hover { color: #2d6cc9; }
blockquote {
    background: #eef4ff; border-left: 4px solid #2d6cc9; margin: 12px 0; padding: 12px 16px;
    border-radius: 4px; font-size: 14px; color: #555;
}
blockquote p { margin: 4px 0; }
.card {
    background: #fff; border-radius: 10px; padding: 16px; margin-bottom: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.score {
    display: inline-block; background: #f04e3c; color: #fff; font-size: 12px;
    font-weight: 600; padding: 1px 8px; border-radius: 10px; margin-bottom: 6px;
}
.tags { margin-top: 8px; }
.tag {
    display: inline-block; background: #eef4ff; color: #2d6cc9; font-size: 12px;
    padding: 2px 10px; border-radius: 12px; margin-right: 6px; margin-bottom: 4px;
}
.meta { font-size: 12px; color: #999; margin-top: 8px; }
ul { padding-left: 20px; margin: 8px 0; }
li { margin: 4px 0; }
hr { border: none; border-top: 1px solid #e0e0e0; margin: 24px 0; }
.footer { font-size: 13px; color: #888; text-align: center; margin-top: 32px; padding-top: 16px; border-top: 1px solid #e0e0e0; }

/* 深色模式 */
@media (prefers-color-scheme: dark) {
    body { background: #1a1a1a; color: #e0e0e0; }
    h1 { color: #f0f0f0; }
    h3 a { color: #e0e0e0; }
    .card { background: #2a2a2a; box-shadow: 0 1px 4px rgba(0,0,0,0.3); }
    blockquote { background: #2a3555; }
    .tag { background: #2a3555; }
    hr { border-top-color: #333; }
}
"""


def _render_header(type_: str, date: str) -> str:
    """渲染头部"""
    type_map = {"morning": "☀️ AI 资讯早报", "evening": "🌙 AI 资讯晚报"}
    title = type_map.get(type_, "AI 资讯简报")
    return f"<h1>{title}</h1><p class='meta'>{date}</p>"


def _render_intro(intro_items: list[str]) -> str:
    """渲染导语区块"""
    if not intro_items:
        return ""
    parts = ["<blockquote>"]
    for item in intro_items:
        parts.append(f"<p>{item}</p>")
    parts.append("</blockquote>")
    return "\n".join(parts)


def _render_section(section: dict) -> str:
    """渲染单个分类区块"""
    section_title = section.get("title", "")
    items = section.get("items", [])

    parts = []
    if section_title:
        parts.append(f"<h2>{section_title}</h2>")

    for item in items:
        parts.append(_render_item(item))

    return "\n".join(parts)


def _render_item(item: dict) -> str:
    """渲染单条资讯卡片"""
    item_title = item.get("title", "")
    summary = item.get("summary", "")
    url = item.get("url", "")
    score = item.get("score", "")
    tags = item.get("tags", [])

    parts = ['<div class="card">']

    # 评分 badge
    if score:
        parts.append(f'<span class="score">{score}/10</span>')

    # 标题 + 链接
    if url:
        parts.append(f'<h3><a href="{url}">{item_title}</a></h3>')
    else:
        parts.append(f"<h3>{item_title}</h3>")

    # 摘要
    if summary:
        parts.append(f"<p>{summary}</p>")

    # 标签
    if tags:
        tag_html = "".join(f'<span class="tag">{t}</span>' for t in tags)
        parts.append(f'<div class="tags">{tag_html}</div>')

    parts.append("</div>")
    return "\n".join(parts)


def _render_footer(key_takeaways: list[str]) -> str:
    """渲染底部关键趋势"""
    if not key_takeaways:
        return ""
    parts = ["<hr>", "<h2>💡 关键趋势</h2>", "<ul>"]
    for t in key_takeaways:
        parts.append(f"<li>{t}</li>")
    parts.append("</ul>")
    return "\n".join(parts)


def render_article(briefing: dict) -> str:
    """渲染完整微信公众号文章 HTML"""
    from content import extract_intro

    type_ = briefing.get("type", "")
    date = str(briefing.get("date", ""))
    sections = briefing.get("sections", [])
    takeaways = briefing.get("key_takeaways", [])
    intro_items = extract_intro(briefing)

    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        "<title>AI 资讯简报</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
    ]

    parts.append(_render_header(type_, date))
    parts.append(_render_intro(intro_items))

    for section in sections:
        parts.append(_render_section(section))

    parts.append(_render_footer(takeaways))
    parts.append('<p class="footer">由 AI 资讯简报智能体自动生成</p>')
    parts.append("</body></html>")

    return "\n".join(parts)
