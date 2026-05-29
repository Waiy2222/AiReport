"""长图生成 — 读取 briefing JSON → 渲染 HTML → Playwright 截图 → 输出 PNG

用法（被 main.py 的 /publish 端点调用）:
    from long_image import generate_long_image
    path = await generate_long_image(briefing, "output/longimage_xxx.png")
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 长图专用 CSS（750px 宽度优化，微信分享最佳尺寸） ──
_LONGIMAGE_CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei",
                 "Noto Sans SC", sans-serif;
    background: #fff; color: #1a1a1a; line-height: 1.7;
    width: 750px; padding: 32px 28px;
}
/* 头部 */
.header { text-align: center; padding-bottom: 24px; border-bottom: 3px solid #07c160; }
.header .badge {
    display: inline-block; background: #07c160; color: #fff;
    font-size: 13px; font-weight: 700; padding: 3px 14px; border-radius: 12px;
    letter-spacing: 0.1em; margin-bottom: 10px;
}
.header h1 { font-size: 26px; font-weight: 800; color: #163325; margin-bottom: 4px; }
.header .date { font-size: 14px; color: #8a9a91; }

/* TL;DR */
.tldr { margin: 20px 0; padding: 18px 20px; background: #f4fbf7; border-radius: 12px; }
.tldr h2 { font-size: 17px; color: #163325; margin-bottom: 12px; }
.tldr .item {
    padding: 8px 0 8px 16px; border-left: 3px solid #07c160; margin-bottom: 8px;
    font-size: 14px; color: #333; line-height: 1.5;
}
.tldr .item:last-child { margin-bottom: 0; }
.tldr .num {
    display: inline-block; color: #07c160; font-weight: 700; margin-right: 6px;
}

/* 分区 */
.section { margin: 28px 0 0; }
.section-title {
    font-size: 20px; font-weight: 800; color: #163325;
    padding-left: 14px; border-left: 5px solid #07c160; margin-bottom: 16px;
}

/* 条目卡片（带图） */
.item-card {
    display: flex; gap: 14px; padding: 16px;
    background: #fafafa; border-radius: 10px; margin-bottom: 12px;
    border: 1px solid #eee;
}
.item-card .img-wrap {
    flex-shrink: 0; width: 120px; height: 90px;
    background: #e8e8e8; border-radius: 8px; overflow: hidden;
}
.item-card .img-wrap img {
    width: 100%; height: 100%; object-fit: cover;
}
.item-card .img-wrap .fallback {
    width: 100%; height: 100%; display: flex; align-items: center;
    justify-content: center; font-size: 28px; color: #ccc;
}
.item-card .content { flex: 1; min-width: 0; }
.item-card .content .title {
    font-size: 16px; font-weight: 700; color: #1a1a1a;
    margin-bottom: 4px; line-height: 1.4;
}
.item-card .content .summary {
    font-size: 13px; color: #666; line-height: 1.6;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
}
.item-card .content .meta {
    font-size: 12px; color: #999; margin-top: 4px;
}
.item-card .content .meta .score {
    display: inline-block; background: #f04e3c; color: #fff;
    padding: 0 6px; border-radius: 8px; font-weight: 600; margin-right: 6px;
}
.item-card .content .meta .tag {
    display: inline-block; background: #eef4ff; color: #2d6cc9;
    padding: 0 8px; border-radius: 10px; margin-right: 4px;
}

/* 核心洞察 */
.takeaways { margin: 28px 0 0; padding: 20px; background: #f4fbf7; border-radius: 12px; }
.takeaways h2 { font-size: 17px; color: #163325; margin-bottom: 12px; }
.takeaways .item {
    padding: 6px 0 6px 20px; position: relative;
    font-size: 14px; color: #333; line-height: 1.6;
}
.takeaways .item::before {
    content: ""; position: absolute; left: 0; top: 13px;
    width: 8px; height: 8px; background: #07c160; border-radius: 50%;
}

/* 底部 */
.footer {
    text-align: center; padding-top: 20px; margin-top: 28px;
    border-top: 1px solid #e0e0e0; font-size: 12px; color: #aaa;
}
"""


def _render_longimage_html(briefing: dict) -> str:
    """将 briefing JSON 渲染为长图专用 HTML"""
    type_label = "早报" if briefing.get("type") == "morning" else "晚报"
    date_str = str(briefing.get("date", ""))
    tl_dr = briefing.get("tl_dr") or []
    sections = briefing.get("sections") or []
    takeaways = briefing.get("key_takeaways") or []

    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        f"<style>{_LONGIMAGE_CSS}</style>",
        "</head><body>",
    ]

    # ── Header ──
    parts.append('<div class="header">')
    parts.append(f'<div class="badge">AI {type_label}</div>')
    parts.append(f"<h1>AI 资讯{type_label}</h1>")
    parts.append(f'<div class="date">{date_str}</div>')
    parts.append("</div>")

    # ── TL;DR ──
    if tl_dr:
        parts.append('<div class="tldr"><h2>📋 今日要闻</h2>')
        for i, point in enumerate(tl_dr):
            parts.append(
                f'<div class="item"><span class="num">{str(i+1).zfill(2)}</span>'
                f"{point}</div>"
            )
        parts.append("</div>")

    # ── Sections ──
    for section in sections:
        sec_title = section.get("title", "")
        parts.append(f'<div class="section"><div class="section-title">{sec_title}</div>')

        for item in section.get("items", []):
            item_title = item.get("title", "")
            summary = item.get("summary", "")
            url = item.get("url", "")
            score = item.get("score", "")
            tags = item.get("tags", [])
            image_url = item.get("image_url", "")

            parts.append('<div class="item-card">')

            # 图片区域
            parts.append('<div class="img-wrap">')
            if image_url:
                parts.append(f'<img src="{image_url}" alt="" onerror="this.style.display=\'none\'" />')
            else:
                parts.append('<div class="fallback">📄</div>')
            parts.append("</div>")

            # 文字内容
            parts.append('<div class="content">')
            if url:
                parts.append(f'<div class="title">{item_title}</div>')
            else:
                parts.append(f'<div class="title">{item_title}</div>')

            if summary:
                parts.append(f'<div class="summary">{summary}</div>')

            # Meta
            meta_parts = []
            if score:
                meta_parts.append(f'<span class="score">{score}</span>')
            for tag in tags[:3]:
                meta_parts.append(f'<span class="tag">{tag}</span>')
            if meta_parts:
                parts.append(f'<div class="meta">{" ".join(meta_parts)}</div>')

            parts.append("</div></div>")  # end content, end item-card

        parts.append("</div>")  # end section

    # ── Takeaways ──
    if takeaways:
        parts.append('<div class="takeaways"><h2>💡 核心洞察</h2>')
        for point in takeaways:
            parts.append(f'<div class="item">{point}</div>')
        parts.append("</div>")

    # ── Footer ──
    parts.append('<div class="footer">由 AI 资讯简报智能体自动生成 · 仅供参考</div>')
    parts.append("</body></html>")

    return "\n".join(parts)


async def generate_long_image(briefing: dict, output_path: str) -> str | None:
    """全流程：渲染 HTML → Playwright 截图 → 保存 PNG

    Args:
        briefing: 从 DB 读取的简报 dict
        output_path: PNG 输出路径（如 "output/longimage_xxx.png"）

    Returns:
        成功时返回 output_path，失败时返回 None（非阻塞）
    """
    html_content = _render_longimage_html(briefing)

    # 保存 HTML 预览（便于调试）
    html_path = Path(output_path).with_suffix(".html")
    try:
        html_path.write_text(html_content, encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to save HTML preview: {e}")

    # Playwright 截图
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page(
                viewport={"width": 750, "height": 800},
                device_scale_factor=2,
            )
            await page.set_content(html_content, wait_until="networkidle")
            # 获取实际内容高度，截取完整长图
            body_height = await page.evaluate("document.body.scrollHeight")
            await page.set_viewport_size({"width": 750, "height": int(body_height) + 50})
            await page.screenshot(
                path=output_path,
                full_page=True,
                type="png",
            )
            await browser.close()

        file_size = Path(output_path).stat().st_size
        logger.info(
            f"Long image saved: {output_path} "
            f"({body_height:.0f}px x 750px, {file_size / 1024:.0f} KB)"
        )
        return output_path

    except ImportError:
        logger.warning(
            "playwright not installed. Install with: "
            "pip install playwright && playwright install chromium"
        )
        return None
    except Exception as e:
        logger.warning(f"Playwright screenshot failed: {e}")
        return None
