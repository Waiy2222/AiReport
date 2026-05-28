"""微信订阅消息批量推送（Phase 2 更新：支持按用户标签个性化推送）"""
import json
import os
import httpx

from config import settings

# access_token 缓存
_token_cache: dict = {"value": None, "expires_at": 0}


async def get_access_token() -> str:
    """获取并缓存微信小程序 access_token（2小时有效）"""
    import time

    global _token_cache
    now = time.time()

    if _token_cache["value"] and now < _token_cache["expires_at"] - 300:
        return _token_cache["value"]

    url = "https://api.weixin.qq.com/cgi-bin/token"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params={
            "grant_type": "client_credential",
            "appid": settings.WX_APPID,
            "secret": settings.WX_SECRET,
        }, timeout=10.0)
        data = resp.json()

    if "errcode" in data and data["errcode"] != 0:
        raise RuntimeError(f"获取 access_token 失败: {data}")

    _token_cache["value"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 7200)
    return _token_cache["value"]


async def send_subscribe_message(
    openid: str,
    briefing: dict,
    access_token: str,
) -> dict:
    """发送单条订阅消息"""
    url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={access_token}"

    title = briefing["tl_dr"][0] if briefing["tl_dr"] else "AI资讯简报"
    btype = "早报" if briefing["type"] == "morning" else "晚报"

    body = {
        "touser": openid,
        "template_id": settings.WX_TEMPLATE_ID,
        "page": f"/pages/detail/detail?id={briefing['id']}",
        "data": {
            "thing1": {"value": title[:20]},
            "thing2": {"value": btype},
            "date3": {"value": str(briefing["date"])},
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=body, timeout=10.0)
        result = resp.json()

    return {
        "openid": openid,
        "result": "success" if result.get("errcode") == 0 else "failed",
        "errcode": result.get("errcode"),
        "errmsg": result.get("errmsg", ""),
    }


def filter_briefing_by_tags(briefing: dict, user_tags: list[str]) -> dict:
    """按用户标签过滤简报内容

    - 有标签：只保留 items 中 tags 与用户标签有交集的条目
    - 无标签（冷启动）：返回完整简报
    - 过滤后无匹配：返回完整简报（兜底）
    """
    if not user_tags:
        return briefing

    tag_set = set(user_tags)
    filtered_sections = []

    for section in briefing.get("sections", []):
        matched_items = []
        for item in section.get("items", []):
            item_tags = set(item.get("tags", []))
            if item_tags & tag_set:
                matched_items.append(item)

        if matched_items:
            filtered_sections.append({
                **section,
                "items": matched_items,
            })

    if not filtered_sections:
        # 兜底：无匹配则返回完整简报
        return briefing

    return {
        **briefing,
        "sections": filtered_sections,
    }


async def batch_push(briefing: dict, targets: list[dict]) -> dict:
    """批量推送给所有目标用户（Phase 2：支持个性化过滤）"""
    try:
        token = await get_access_token()
    except Exception as e:
        return {
            "status": "error",
            "briefing_id": str(briefing.get("id", "")),
            "total": len(targets),
            "success": 0,
            "failed": len(targets),
            "personalized": 0,
            "default_fallback": len(targets),
            "detail": [{"openid": "N/A", "result": "token_error", "errmsg": str(e)}],
        }

    results = []
    success = 0
    failed = 0
    personalized = 0
    default_fallback = 0

    for t in targets:
        openid = t["openid"]
        user_tags = t.get("tags", [])

        # 按标签过滤简报
        if user_tags:
            personalized_briefing = filter_briefing_by_tags(briefing, user_tags)
            personalized += 1
        else:
            # 冷启动：推默认综合简报
            personalized_briefing = briefing
            default_fallback += 1

        try:
            r = await send_subscribe_message(openid, personalized_briefing, token)
            if r["result"] == "success":
                success += 1
            else:
                failed += 1
            results.append(r)
        except Exception as e:
            failed += 1
            results.append({"openid": openid, "result": "error", "errmsg": str(e)})

    return {
        "status": "ok",
        "briefing_id": str(briefing.get("id", "")),
        "total": len(targets),
        "success": success,
        "failed": failed,
        "personalized": personalized,
        "default_fallback": default_fallback,
        "detail": results,
    }
