"""CSDN article publishing via MetaWeblog API (XML-RPC).

CSDN does not expose a public REST API.  The stable, officially-supported
programmatic interface is the MetaWeblog XML-RPC endpoint.
"""

import os
import xml.etree.ElementTree as ET

import httpx

CSDN_METAWEBLOG_URL = "https://write.blog.csdn.net/xmlrpc/index"


def _check_credentials() -> tuple[str, str] | None:
    username = os.getenv("CSDN_USERNAME", "").strip()
    password = os.getenv("CSDN_PASSWORD", "").strip()
    if not username or not password:
        return None
    return username, password


# ── XML-RPC request builder ──────────────────────────────────────────────────

def _text_elem(tag: str, text: str) -> str:
    safe = text.replace("&", "&amp;").replace("<", "&lt;")
    return f"<{tag}><string>{safe}</string></{tag}>"


def _build_newpost_xml(
    username: str,
    password: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
) -> str:
    """Build a metaWeblog.newPost XML-RPC request body.

    Reference: https://xmlrpc.com/metaWeblogApi
    """
    # Build categories array
    cats_xml = ""
    if tags:
        cat_elems = "".join(
            f"<value><string>{t}</string></value>" for t in tags
        )
        cats_xml = (
            "<member><name>categories</name>"
            f"<value><array><data>{cat_elems}</data></array></value>"
            "</member>"
        )

    return (
        '<?xml version="1.0"?>'
        "<methodCall>"
        "<methodName>metaWeblog.newPost</methodName>"
        "<params>"
        f"<param>{_text_elem('value', username)}</param>"          # blogid
        f"<param>{_text_elem('value', username)}</param>"          # username
        f"<param>{_text_elem('value', password)}</param>"          # password
        "<param><value><struct>"
        f"<member>{_text_elem('name', 'title')}{_text_elem('value', title)}</member>"
        f"<member>{_text_elem('name', 'description')}{_text_elem('value', content)}</member>"
        f"{cats_xml}"
        "</struct></value></param>"
        "<param><value><boolean>1</boolean></value></param>"       # publish immediately
        "</params>"
        "</methodCall>"
    )


# ── Public API ───────────────────────────────────────────────────────────────

async def publish(
    client: httpx.AsyncClient,
    title: str,
    content: str,
    tags: list[str] | None = None,
) -> dict:
    """Publish an article to CSDN via MetaWeblog XML-RPC.

    Returns ``{"url": "https://blog.csdn.net/..."}`` on success,
    or ``{"error": "..."}`` on failure.
    """
    creds = _check_credentials()
    if creds is None:
        return {"error": "CSDN credentials not configured "
                         "(CSDN_USERNAME + CSDN_PASSWORD)"}

    username, password = creds
    xml_body = _build_newpost_xml(username, password, title, content, tags)

    try:
        resp = await client.post(
            CSDN_METAWEBLOG_URL,
            content=xml_body,
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
    except httpx.RequestError as e:
        return {"error": f"Request failed: {e}"}

    # Parse XML-RPC response
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return {"error": f"Invalid XML response: {resp.text[:300]}"}

    # Check for fault response
    fault = root.find(".//fault/value/struct")
    if fault is not None:
        code_el = fault.find(".//member[name='faultCode']/value/int")
        msg_el = fault.find(".//member[name='faultString']/value/string")
        code = code_el.text if code_el is not None else "?"
        msg = msg_el.text if msg_el is not None else "unknown error"
        return {"error": f"CSDN fault [{code}]: {msg}"}

    # Success — extract post ID from params/param/value/string
    post_id_el = root.find(".//params/param/value/string")
    if post_id_el is not None and post_id_el.text:
        post_id = post_id_el.text.strip()
        if post_id:
            return {
                "url": f"https://blog.csdn.net/{username}/article/details/{post_id}"
            }
        return {"error": "CSDN returned empty post ID"}

    return {"error": f"Unexpected XML-RPC response: {resp.text[:300]}"}
