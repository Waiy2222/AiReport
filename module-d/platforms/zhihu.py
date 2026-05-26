"""知乎专栏发布逻辑."""
import asyncio
import os

import httpx

ZHIHU_TOKEN_URL = "https://api.zhihu.com/v4/oauth/token"
ZHIHU_ARTICLES_URL = "https://api.zhihu.com/v4/articles"
MAX_RETRIES = 3


def _check_credentials() -> tuple[str, str] | None:
    """Return (client_id, client_secret) if env vars are set, else None."""
    client_id = os.getenv("ZHIHU_CLIENT_ID", "").strip()
    client_secret = os.getenv("ZHIHU_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


async def _get_access_token(
    client: httpx.AsyncClient, client_id: str, client_secret: str
) -> str:
    """Obtain OAuth2 access token from Zhihu API."""
    resp = await client.post(
        ZHIHU_TOKEN_URL,
        json={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"]


async def _create_article(
    client: httpx.AsyncClient, access_token: str, title: str, content: str
) -> dict:
    """POST to Zhihu articles endpoint with retry on rate limits."""
    headers = {"Authorization": f"Bearer {access_token}"}
    last_status = None
    last_body = None

    for attempt in range(MAX_RETRIES + 1):
        resp = await client.post(
            ZHIHU_ARTICLES_URL,
            headers=headers,
            json={"title": title, "content": content},
        )
        last_status = resp.status_code
        try:
            last_body = resp.json()
        except Exception:
            last_body = resp.text

        if resp.status_code == 429:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"error": "Rate limited after max retries"}

        if resp.status_code >= 400:
            err_msg = last_body.get("error", {}).get("message", str(last_body)) if isinstance(last_body, dict) else str(last_body)
            return {"error": f"HTTP {resp.status_code}: {err_msg}"}

        # Success (2xx)
        return {"url": last_body.get("url", "")}

    return {"error": f"HTTP {last_status}: {last_body}"}


async def publish(client: httpx.AsyncClient, title: str, content: str) -> dict:
    """
    Publish an article to Zhihu.

    Returns {"url": "https://zhuanlan.zhihu.com/p/..."} on success,
    or {"error": "..."} on failure.
    """
    creds = _check_credentials()
    if creds is None:
        return {"error": "API credentials not configured"}

    client_id, client_secret = creds
    try:
        access_token = await _get_access_token(client, client_id, client_secret)
        result = await _create_article(client, access_token, title, content)
        return result
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
    except httpx.RequestError as e:
        return {"error": f"Request failed: {e}"}
    except Exception as e:
        return {"error": str(e)}
