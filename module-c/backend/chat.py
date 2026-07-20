"""聊天对话 API 路由"""
import sys
import os
import importlib.util

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ── 加载 chat_agent 模块 ──
_chat_agent = None


def _load_chat_agent():
    global _chat_agent
    if _chat_agent is not None:
        return _chat_agent
    agent_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "module-b", "ai", "chat_agent.py",
    )
    if not os.path.exists(agent_path):
        return None
    spec = importlib.util.spec_from_file_location("chat_agent", agent_path)
    _chat_agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_chat_agent)
    return _chat_agent


# ── 存会话的 db_pool 引用，由 main.py 注入 ──
_db_pool = None


def set_db_pool(pool):
    global _db_pool
    _db_pool = pool


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500, description="用户问题")


class ChatResponse(BaseModel):
    reply: str
    sources: list[dict] = []


@router.post("/send", response_model=ChatResponse)
async def chat_send(req: ChatRequest, request: Request):
    """发送消息，返回 AI 回复 + 新闻来源"""
    agent = _load_chat_agent()
    if agent is None:
        return ChatResponse(
            reply="抱歉，AI 服务暂时不可用，请稍后再试。",
            sources=[],
        )

    # 从 app.state 获取当前会话的历史（纯内存）
    history = getattr(request.app.state, "chat_history", None)
    if history is None:
        history = []
        request.app.state.chat_history = history

    result = await agent.chat(
        query=req.message,
        history=history,
        db_pool=_db_pool,
    )

    # 更新会话历史
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": result["reply"]})
    if len(history) > 40:  # 20 轮对话 = 40 条消息
        history[:] = history[-40:]

    return ChatResponse(reply=result["reply"], sources=result.get("sources", []))


@router.get("/suggestions")
async def chat_suggestions():
    """返回推荐话题"""
    return {
        "suggestions": [
            "今日AI领域有哪些大事？",
            "最近有哪些重要的开源项目发布？",
            "今天科技行业有什么重要新闻？",
            "最近AI融资方面有什么动向？",
            "有没有关于AI安全的新闻？",
        ]
    }
