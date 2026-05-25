"""微信登录验证"""
import httpx

from config import settings


async def code_to_openid(js_code: str) -> str | None:
    """用微信 jscode2session 接口换 openid"""
    url = "https://api.weixin.qq.com/sns/jscode2session"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params={
            "appid": settings.WX_APPID,
            "secret": settings.WX_SECRET,
            "js_code": js_code,
            "grant_type": "authorization_code",
        }, timeout=10.0)
        data = resp.json()

    if "errcode" in data and data["errcode"] != 0:
        return None

    return data.get("openid")


def verify_token(authorization: str | None) -> str | None:
    """从 Authorization 头提取 openid（简化：直接传 openid 作为 token）"""
    if not authorization:
        return None

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        return None

    return token
