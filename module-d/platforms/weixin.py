"""微信公众号草稿+发布逻辑.

HTML 模板样式源自 ai-trend-publish 的 "default" 主题 —
绿色 WeChat 品牌色系，适配微信后台富文本编辑器。
"""
import os

import httpx

WEIXIN_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WEIXIN_DRAFT_ADD_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
WEIXIN_PUBLISH_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/submit"

WECHAT_ERROR_MAP = {
    40001: "invalid credential (appsecret may be wrong)",
    40014: "invalid access_token",
    42001: "access_token expired, need to refresh",
    45009: "API call frequency limit reached",
    48001: "API function not authorized for this account",
    -1: "system error, retry recommended",
}


def _check_credentials() -> tuple[str, str] | None:
    """Return (appid, secret) if env vars are set, else None."""
    appid = os.getenv("WEIXIN_OA_APPID", "").strip()
    secret = os.getenv("WEIXIN_OA_SECRET", "").strip()
    if not appid or not secret:
        return None
    return appid, secret


def _render_wechat_error(resp_json: dict) -> str:
    """Render a human-readable error from a WeChat API JSON response."""
    errcode = resp_json.get("errcode", -1)
    errmsg = resp_json.get("errmsg", "unknown error")
    hint = WECHAT_ERROR_MAP.get(errcode, "")
    if hint:
        return f"[{errcode}] {errmsg} — {hint}"
    return f"[{errcode}] {errmsg}"


def _escape_html(text: str) -> str:
    """Escape &, <, > for safe HTML embedding."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── WeChat HTML template (ported from ai-trend-publish "default" theme) ─────

_CSS_RESET = (
    "max-width:100%;margin:0 auto;padding:22px 16px;"
    "font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Segoe UI',sans-serif;"
    "line-height:1.75;color:#333;background:#fff"
)

# Green brand palette
_C_GREEN = "#07c160"
_C_DARK = "#163325"
_C_MUTED = "#8a9a91"
_C_BG_GREEN = "#f4fbf7"
_C_BORDER_GREEN = "#dcefe4"
_C_LIGHT_BORDER = "#e4f3e9"


def _image_html(image_url: str) -> str:
    """Phase 2: 渲染图片 HTML，加载失败时不破坏布局"""
    if not image_url:
        return ""
    return (
        f'<div style="margin:12px 0 0;border-radius:8px;overflow:hidden;'
        f'background:#f0f0f0;line-height:0;">'
        f'<img src="{_escape_html(image_url)}" alt="" style="width:100%;'
        f'display:block;" '
        f'onerror="this.style.display=\'none\';'
        f'this.parentElement.style.display=\'none\'" />'
        f'</div>'
    )


def render_briefing_html(briefing) -> str:
    """Render a briefing dict into WeChat-compatible styled HTML.

    briefing fields used: type, date, tl_dr, sections, key_takeaways.
    Each section item uses: title, summary, score, source, url, image_url, tags.
    Phase 2: 新增 headline 头条区 + 每条 item 配图 + tags 标签显示
    """
    type_label = "AI资讯早报" if briefing["type"] == "morning" else "AI资讯晚报"
    date_str = _escape_html(str(briefing["date"]))
    tl_dr = briefing.get("tl_dr") or []
    sections = briefing.get("sections") or []
    takeaways = briefing.get("key_takeaways") or []

    # Phase 2: 提取头条（sections 中 score 最高的 item）
    headline_item = None
    all_items = []
    for sec in sections:
        for item in sec.get("items", []):
            all_items.append(item)
    if all_items:
        all_items.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)
        headline_item = all_items[0]

    parts: list[str] = []

    # ── Outer wrapper ──────────────────────────────────────────────────
    parts.append(f'<section style="{_CSS_RESET}">')

    # ── Header card ────────────────────────────────────────────────────
    parts.append(
        f'<section style="margin:0 0 28px;padding:20px 18px;'
        f'background:linear-gradient(180deg,{_C_BG_GREEN},#fff);'
        f'border-radius:14px;border:1px solid {_C_BORDER_GREEN};'
        f'border-left:5px solid {_C_GREEN};'
        f'box-shadow:0 6px 16px rgba(7,193,96,0.07);">'
        f'<p style="margin:0 0 6px;color:{_C_MUTED};font-size:12px;'
        f'font-weight:700;line-height:1.2;letter-spacing:0.08em;">'
        f'AI BRIEFING</p>'
        f'<p style="margin:0;font-size:21px;font-weight:800;'
        f'color:{_C_DARK};line-height:1.35;">'
        f'{type_label} | {date_str}</p>'
        f'</section>'
    )

    # ── Phase 2: Headline（头条大图区） ──────────────────────────────
    if headline_item:
        hl_title = _escape_html(headline_item.get("title", ""))
        hl_summary = _escape_html(headline_item.get("summary", ""))
        hl_url = _escape_html(headline_item.get("url", ""))
        hl_image = headline_item.get("image_url", "")

        hl_parts = [
            f'<section style="margin:0 0 28px;border-radius:14px;'
            f'overflow:hidden;border:1px solid {_C_BORDER_GREEN};">'
        ]
        # 头条大图
        if hl_image:
            hl_parts.append(
                f'<div style="line-height:0;background:#e8e8e8;">'
                f'<img src="{hl_image}" alt="" style="width:100%;display:block;" '
                f'onerror="this.style.display=\'none\'" />'
                f'</div>'
            )
        # 头条文字
        hl_parts.append(
            f'<div style="padding:18px 16px;background:#fff;">'
            f'<div style="display:inline-block;background:{_C_GREEN};color:#fff;'
            f'font-size:11px;font-weight:700;padding:2px 10px;border-radius:10px;'
            f'margin-bottom:10px;">头条</div>'
            f'<h2 style="margin:0 0 8px;color:{_C_DARK};font-size:20px;'
            f'font-weight:800;line-height:1.4;">{hl_title}</h2>'
            f'<p style="margin:0;color:#555;font-size:14px;line-height:1.8;">{hl_summary}</p>'
        )
        if hl_url:
            hl_parts.append(
                f'<p style="margin:10px 0 0;"><a href="{hl_url}" '
                f'style="color:{_C_GREEN};text-decoration:none;font-size:14px;">'
                f'阅读原文 &rarr;</a></p>'
            )
        hl_parts.append("</div></section>")
        parts.append("\n".join(hl_parts))

    # ── TL;DR — table-of-contents style list ───────────────────────────
    if tl_dr:
        parts.append(
            f'<section style="margin:0 0 28px;padding:18px 16px;'
            f'background:{_C_BG_GREEN};border-radius:12px;'
            f'border:1px solid {_C_BORDER_GREEN};">'
            f'<p style="margin:0 0 14px;padding-bottom:10px;'
            f'border-bottom:1px solid {_C_BORDER_GREEN};'
            f'color:{_C_DARK};font-size:17px;font-weight:800;line-height:1.4;">'
            f'今日要闻</p>'
        )
        for i, point in enumerate(tl_dr):
            parts.append(
                f'<section style="margin:8px 0;padding:12px 14px;'
                f'background:#fff;border-radius:8px;'
                f'border:1px solid {_C_LIGHT_BORDER};'
                f'border-left:4px solid {_C_GREEN};color:#333;'
                f'font-size:14px;line-height:1.6;">'
                f'<span style="display:inline-block;color:{_C_GREEN};'
                f'font-weight:700;margin-right:8px;">'
                f'{str(i + 1).zfill(2)}</span>'
                f'<span>{_escape_html(point)}</span>'
                f'</section>'
            )
        parts.append("</section>")

    # ── Section / item body（Phase 2: 带图片 + 标签） ─────────────────
    for section in sections:
        sec_title = _escape_html(section.get("title", ""))
        if sec_title:
            parts.append(
                f'<section style="margin:36px 0 20px;">'
                f'<h2 style="margin:0;color:{_C_DARK};font-size:19px;'
                f'font-weight:800;padding-left:12px;'
                f'border-left:4px solid {_C_GREEN};">'
                f'{sec_title}</h2>'
                f'</section>'
            )

        for j, item in enumerate(section.get("items", [])):
            item_title = _escape_html(item.get("title", ""))
            summary = _escape_html(item.get("summary", ""))
            source = _escape_html(item.get("source", ""))
            url = _escape_html(item.get("url", ""))
            score = item.get("score", 0)
            tags = item.get("tags", [])
            image_url = item.get("image_url", "")

            # Item header
            parts.append(
                f'<section style="margin:24px 0 0;">'
                f'<section style="padding:16px 14px;'
                f'background:linear-gradient(90deg,'
                f'rgba(7,193,96,0.08),rgba(7,193,96,0.02));'
                f'border-left:4px solid {_C_GREEN};border-radius:10px;">'
                f'<p style="margin:0 0 6px;color:{_C_GREEN};font-size:12px;'
                f'font-weight:800;letter-spacing:0.06em;">'
                f'NO.{str(j + 1).zfill(2)}</p>'
                f'<h3 style="margin:0;color:{_C_DARK};font-size:18px;'
                f'font-weight:800;line-height:1.45;">{item_title}</h3>'
            )

            # Meta line
            meta_parts = []
            if source:
                meta_parts.append(f"来源：{source}")
            if score:
                meta_parts.append(f"评分：{score}")
            meta_line = " | ".join(meta_parts)
            if meta_line:
                parts.append(
                    f'<p style="margin:8px 0 0;color:{_C_MUTED};'
                    f'font-size:13px;line-height:1.4;">{meta_line}</p>'
                )
            parts.append("</section>")

            # Content body
            parts.append(
                f'<section style="padding:0 2px 0 4px;">'
            )
            if summary:
                parts.append(
                    f'<p style="margin:16px 0 0;color:#555;font-size:15px;'
                    f'line-height:1.9;text-align:left;">{summary}</p>'
                )

            # Phase 2: 图片
            parts.append(_image_html(image_url))

            # Phase 2: 标签
            if tags:
                tag_html = "".join(
                    f'<span style="display:inline-block;background:#eef4ff;'
                    f'color:#2d6cc9;font-size:12px;padding:1px 10px;'
                    f'border-radius:10px;margin-right:4px;'
                    f'margin-top:8px;">{_escape_html(t)}</span>'
                    for t in tags[:4]
                )
                parts.append(f'<div style="margin-top:4px;">{tag_html}</div>')

            if url:
                parts.append(
                    f'<p style="margin:12px 0 0;">'
                    f'<a href="{url}" style="color:{_C_GREEN};'
                    f'text-decoration:none;font-size:14px;'
                    f'border-bottom:1px solid {_C_GREEN};">'
                    f'阅读原文 &rarr;</a></p>'
                )
            parts.append("</section></section>")

            # Separator between items
            if j < len(section.get("items", [])) - 1:
                parts.append(
                    f'<section style="margin:24px auto 0;width:50%;'
                    f'height:1px;background:linear-gradient(90deg,'
                    f'rgba(7,193,96,0),rgba(7,193,96,0.30),'
                    f'rgba(7,193,96,0));font-size:0;line-height:0;">'
                    f'&nbsp;</section>'
                )

    # ── Key Takeaways ──────────────────────────────────────────────────
    if takeaways:
        parts.append(
            f'<section style="margin:38px 0 0;padding:20px 16px;'
            f'background:{_C_BG_GREEN};border-radius:12px;'
            f'border:1px solid {_C_BORDER_GREEN};">'
            f'<h2 style="margin:0 0 14px;color:{_C_DARK};font-size:18px;'
            f'font-weight:800;">核心要点</h2>'
        )
        for i, point in enumerate(takeaways, 1):
            parts.append(
                f'<p style="margin:8px 0;color:#333;font-size:15px;'
                f'line-height:1.8;">'
                f'<span style="color:{_C_GREEN};font-weight:700;">'
                f'{i}.</span> {_escape_html(point)}</p>'
            )
        parts.append("</section>")

    parts.append("</section>")
    return "\n".join(parts)


# ── WeChat API helpers ─────────────────────────────────────────────────────

async def _get_access_token(
    client: httpx.AsyncClient, appid: str, secret: str
) -> str:
    """Step 1: Get access_token from WeChat API."""
    resp = await client.get(
        WEIXIN_TOKEN_URL,
        params={
            "grant_type": "client_credential",
            "appid": appid,
            "secret": secret,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if "errcode" in data and data["errcode"] != 0:
        raise RuntimeError(_render_wechat_error(data))
    return data["access_token"]


async def _create_draft(
    client: httpx.AsyncClient, access_token: str, title: str, content_html: str
) -> str:
    """Step 2: Create a draft and return the media_id."""
    resp = await client.post(
        WEIXIN_DRAFT_ADD_URL,
        params={"access_token": access_token},
        json={
            "articles": [
                {
                    "title": title,
                    "content": content_html,
                    "content_source_url": "",
                    "need_open_comment": 1,
                    "only_fans_can_comment": 0,
                }
            ]
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode", 0) != 0:
        raise RuntimeError(_render_wechat_error(data))
    return data["media_id"]


async def _publish_draft(
    client: httpx.AsyncClient, access_token: str, media_id: str
) -> dict:
    """Step 3: Publish the draft and return the result."""
    resp = await client.post(
        WEIXIN_PUBLISH_URL,
        params={"access_token": access_token},
        json={"media_id": media_id},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode", 0) != 0:
        raise RuntimeError(_render_wechat_error(data))
    publish_id = data.get("publish_id", "")
    return {"url": f"https://mp.weixin.qq.com/s/{publish_id}"}


# ── Public API ──────────────────────────────────────────────────────────────

async def publish(client: httpx.AsyncClient, title: str, content: str) -> dict:
    """Publish an article to WeChat Official Account via draft workflow.

    Args:
        client: httpx.AsyncClient instance.
        title: Article title (plain text).
        content: **Pre-rendered HTML** — call :func:`render_briefing_html`
                 first to convert a briefing dict into WeChat-compatible HTML.

    Returns:
        ``{"url": "https://mp.weixin.qq.com/s/..."}`` on success,
        ``{"error": "..."}`` on failure.
    """
    creds = _check_credentials()
    if creds is None:
        return {"error": "API credentials not configured"}

    appid, secret = creds
    try:
        access_token = await _get_access_token(client, appid, secret)
        media_id = await _create_draft(client, access_token, title, content)
        result = await _publish_draft(client, access_token, media_id)
        return result

    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
    except httpx.RequestError as e:
        return {"error": f"Request failed: {e}"}
    except RuntimeError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}
