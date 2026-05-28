"""Pydantic 数据模型 — 请求/响应结构定义"""
from __future__ import annotations

from pydantic import BaseModel, Field


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
    briefing_id: str | None = None
    type: str | None = None  # morning / evening，不传 briefing_id 时取最新


class PushResult(BaseModel):
    status: str
    total: int
    success: int
    failed: int
    personalized: int = 0
    default_fallback: int = 0
    detail: list[dict] = []


# ── Phase 2 新增模型 ──────────────────────────────────────────────


class PreferencesRequest(BaseModel):
    openid: str
    tags: list[str] = Field(default_factory=list)


class PreferencesResponse(BaseModel):
    openid: str
    tags: list[str]


class BehaviorRequest(BaseModel):
    openid: str
    briefing_id: str
    action: str = Field(description="click / view / share / dismiss")
    item_index: int | None = None
    item_title: str | None = None
    item_url: str | None = None
    item_tags: list[str] = Field(default_factory=list)


class TagItem(BaseModel):
    tag: str
    label_zh: str
    description: str = ""


class TagsResponse(BaseModel):
    tags: list[TagItem]


class UserClickSummary(BaseModel):
    briefing_id: str
    item_title: str
    action: str
    created_at: str


class UserProfile(BaseModel):
    openid: str
    tags: list[str]
    recent_clicks: list[UserClickSummary]
    weight_map: dict[str, float]
