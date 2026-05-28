"""HTML → 长图渲染 — Jinja2 + Playwright 无头浏览器截图"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
OUTPUT_DIR = Path(__file__).parent.parent / "longimage_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def _render_html(briefing: dict, briefing_type: str, briefing_date: str, raw_stats: dict) -> str:
    """用 Jinja2 渲染简报 HTML"""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("briefing_long.html")

    final_count = raw_stats.get("final_count", 0) if isinstance(raw_stats, dict) else 0

    return template.render(
        briefing_type=briefing_type,
        briefing_date=briefing_date,
        headline=briefing.get("headline", {}),
        tl_dr=briefing.get("tl_dr", []),
        sections=briefing.get("sections", []),
        key_takeaways=briefing.get("key_takeaways", []),
        final_count=final_count,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


async def render_longimage(briefing: dict, briefing_type: str, briefing_date: str, raw_stats: dict) -> bytes:
    """渲染长图 PNG，返回 bytes"""
    html = _render_html(briefing, briefing_type, briefing_date, raw_stats)

    temp_name = f"briefing_{uuid.uuid4().hex[:8]}.html"
    temp_path = OUTPUT_DIR / temp_name
    temp_path.write_text(html, encoding="utf-8")

    browser = None
    try:
        from playwright.async_api import async_playwright

        pw = await async_playwright().__aenter__()
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 750, "height": 600})
        await page.goto(f"file://{temp_path}", wait_until="networkidle")
        body_height = await page.evaluate("document.body.scrollHeight")
        await page.set_viewport_size({"width": 750, "height": body_height})
        screenshot = await page.screenshot(full_page=True, type="png")
        return screenshot
    finally:
        if browser:
            await browser.close()
        if temp_path.exists():
            temp_path.unlink()
