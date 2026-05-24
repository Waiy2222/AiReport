"""Pydantic 数据模型 — 请求/响应结构定义"""
from pydantic import BaseModel


class BriefingOut(BaseModel):
    id: str
    type: str
    date: str
    tl_dr: list[str]
    sections: list[dict]
    key_takeaways: list[str]
    generated_at: str


class BriefingListItem(BaseModel):
    id: str
    type: str
    date: str
    tl_dr: list[str]
    generated_at: str


class HistoryOut(BaseModel):
    page: int
    size: int
    total: int
    items: list[BriefingListItem]


class SubscribeRequest(BaseModel):
    openid: str
    morning_enabled: bool = True
    evening_enabled: bool = True


class UnsubscribeRequest(BaseModel):
    openid: str


class PushRequest(BaseModel):
    briefing_id: str


class PushResult(BaseModel):
    status: str
    total: int
    success: int
    failed: int
    detail: list[dict] = []
