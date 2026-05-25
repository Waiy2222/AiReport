"""微信订阅消息批量推送"""
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


async def batch_push(briefing: dict, targets: list[dict]) -> dict:
    """批量推送给所有目标用户"""
    try:
        token = await get_access_token()
    except Exception as e:
        return {
            "status": "error",
            "briefing_id": str(briefing["id"]),
            "total": len(targets),
            "success": 0,
            "failed": len(targets),
            "detail": [{"openid": "N/A", "result": "token_error", "errmsg": str(e)}],
        }

    results = []
    success = 0
    failed = 0

    for t in targets:
        try:
            r = await send_subscribe_message(t["openid"], briefing, token)
            if r["result"] == "success":
                success += 1
            else:
                failed += 1
            results.append(r)
        except Exception as e:
            failed += 1
            results.append({"openid": t["openid"], "result": "error", "errmsg": str(e)})

    return {
        "status": "ok",
        "briefing_id": str(briefing["id"]),
        "total": len(targets),
        "success": success,
        "failed": failed,
        "detail": results,
    }
