# 个性化简报按需生成 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户输入感兴趣的新闻种类，系统按需生成专属简报，支持自然语言+标签双输入，跳过AI评分/辩论/补充以提速至30-45秒。

**Architecture:** 在现有通用简报流程外新增按需生成路径：输入校验(敏感词+新闻相关性) → LLM兴趣解析 → 轻量流水线(跳过评分/辩论/补充) → 异步轮询 → 前端展示。前端新增可折叠输入面板，后端新增3个API端点。

**Tech Stack:** FastAPI + asyncpg + DeepSeek API + 微信小程序原生框架

## Global Constraints

- 专属简报跳过 AI评分/辩论/背景补充，保留时效性门禁/URL去重/语义去重/翻译/摘要/配图
- 前端轮询间隔2秒，最多90次(3分钟)
- 同一用户最多1个进行中任务，新提交取消旧任务
- 敏感词命中不透露具体词，统一返回中性提示
- 未登录时使用设备标识
- 专属简报与通用简报去重池完全独立

---

### Task 1: 数据库迁移 — briefings 表新增字段

**Files:**
- Modify: `module-c/backend/db.py`

**Interfaces:**
- Produces: `async def migrate_personalized_briefings(pool)` — 执行 ALTER TABLE 添加4个新列

- [ ] **Step 1: 在 db.py 末尾新增迁移函数**

```python
async def migrate_personalized_briefings(pool: asyncpg.Pool):
    """为 briefings 表添加个性化简报所需字段"""
    async with pool.acquire() as conn:
        # 检查并添加 requested_by 列
        col_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name='briefings' AND column_name='requested_by')"
        )
        if not col_exists:
            await conn.execute(
                "ALTER TABLE briefings ADD COLUMN requested_by VARCHAR"
            )
        
        # 检查并添加 interest_text 列
        col_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name='briefings' AND column_name='interest_text')"
        )
        if not col_exists:
            await conn.execute(
                "ALTER TABLE briefings ADD COLUMN interest_text TEXT"
            )
        
        # 检查并添加 interest_tags 列
        col_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name='briefings' AND column_name='interest_tags')"
        )
        if not col_exists:
            await conn.execute(
                "ALTER TABLE briefings ADD COLUMN interest_tags JSONB DEFAULT '[]'::jsonb"
            )
        
        # 检查并添加 is_personalized 列
        col_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name='briefings' AND column_name='is_personalized')"
        )
        if not col_exists:
            await conn.execute(
                "ALTER TABLE briefings ADD COLUMN is_personalized BOOLEAN DEFAULT false"
            )
        
        print("[db] Personalized briefing columns ready")
```

- [ ] **Step 2: 在 main.py startup 中调用迁移**

Read `module-c/backend/main.py:60-74` (startup 函数)，在 `_db_ok = True` 之后插入：

```python
async def startup():
    global _db_ok
    try:
        await init_db()
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        _db_ok = True
        # 新增：执行个性化简报迁移
        await migrate_personalized_briefings(pool)
        set_tags_db_pool(pool)
        set_trends_db_pool(pool)
        set_chat_db_pool(pool)
        print("[module-c] PostgreSQL connected")
    except Exception:
        _db_ok = False
        print("[module-c] PostgreSQL not available, using mock data")
```

并在 db.py 导入处确认 migrate 函数可被引用（在 main.py 的 db import 中补充）：

```python
# main.py 顶部 db import 行改为：
from db import get_pool, init_db, close_db, migrate_personalized_briefings
```

- [ ] **Step 3: 验证迁移**

```bash
cd d:/项目/ai报道后续修改/ai-news-briefing-agent/module-c/backend
python -c "
import asyncio, asyncpg
async def test():
    pool = await asyncpg.create_pool('postgresql://postgres:postgres@localhost:5432/ai_news')
    from db import migrate_personalized_briefings
    await migrate_personalized_briefings(pool)
    async with pool.acquire() as conn:
        cols = await conn.fetch(\"SELECT column_name FROM information_schema.columns WHERE table_name='briefings'\")
        print([c['column_name'] for c in cols])
    await pool.close()
asyncio.run(test())
"
```

---

### Task 2: 兴趣解析模块（新文件）

**Files:**
- Create: `module-b/ai/interest_parser.py`
- Create: `module-b/ai/sensitive_words.py`

**Interfaces:**
- Produces: `async def validate_input(text: str) -> dict` — 返回 `{valid: bool, error: str | None}`
- Produces: `async def parse_interests(text: str) -> dict` — 返回 `{tags: list[str], keywords: list[str]}`
- Produces: `def check_sensitive(text: str) -> str | None` — 返回命中的敏感词或 None

- [ ] **Step 1: 创建敏感词列表文件 `module-b/ai/sensitive_words.py`**

```python
"""敏感词库 — 独立文件便于维护和更新"""
import re

# 敏感词列表（示例，实际使用时扩展）
SENSITIVE_WORDS = [
    # 政治敏感类
    "习近平", "毛泽东", "邓小平", "江泽民", "胡锦涛", "温家宝",
    "六四", "天安门", "法轮功", "西藏独立", "新疆独立",
    "台独", "港独", "藏独", "疆独",
    # 色情暴力类
    "色情", "赌博", "博彩", "毒品",
    # 可继续扩展...
]

# 编译正则：忽略空格、符号分隔的绕过
def _build_pattern(words: list[str]) -> re.Pattern:
    escaped = [re.escape(w) for w in words]
    # 允许字符间插入空格或符号来绕过
    joined = "|".join(escaped)
    return re.compile(f"({joined})", re.IGNORECASE)

_SENSITIVE_RE = _build_pattern(SENSITIVE_WORDS)


def check_sensitive(text: str) -> str | None:
    """检查文本是否包含敏感词。
    
    Returns:
        命中的敏感词（遮蔽后），或 None 表示通过
    """
    # 去除空格和特殊符号做规范化匹配
    normalized = re.sub(r'[\s\-\_\.\,\;\:\!\?\@\#\$\%\^\&\*\(\)\[\]\{\}\|\\\/]', '', text)
    match = _SENSITIVE_RE.search(normalized)
    if match:
        return match.group(1)
    return None
```

- [ ] **Step 2: 创建兴趣解析模块 `module-b/ai/interest_parser.py`**

```python
"""兴趣解析 — 敏感词过滤 + 新闻相关性判断 + LLM标签提取"""
import json
import logging
from .client import get_client, DEEPSEEK_MODEL
from .sensitive_words import check_sensitive

logger = logging.getLogger(__name__)

# 与 tags.py 中的标签映射保持一致
_ALL_TAGS = [
    "LLM", "Agent", "开源", "AI编程", "AI产品", "AI安全", "AI政策",
    "多模态", "RAG", "基础设施", "芯片", "机器人", "自动驾驶",
    "融资", "医疗", "Python", "科技", "体育", "时事", "工具",
    "推理", "MoE", "行业", "全球",
]

_TAG_PROMPT = """你是一个新闻兴趣解析器。用户描述了他们感兴趣的新闻类型。
请从可用标签列表中选出最匹配的标签（不超过5个），并提取2-3个补充关键词。

可用标签：{available_tags}

用户输入：{user_input}

返回JSON：
{{"tags": ["匹配的标签1", "匹配的标签2"], "keywords": ["关键词1", "关键词2"]}}

规则：
- 只选择与用户描述直接相关的标签
- 如果没有匹配的标签，tags 返回空数组
- keywords 用于模糊匹配，可包含标签列表外的词"""

_NEWS_CHECK_PROMPT = """判断以下用户输入是否在描述对某类新闻/资讯的兴趣。

用户输入：{user_input}

返回JSON：{{"is_news_interest": true/false, "reason": "简短原因"}}

是新闻兴趣的例子：
- "我想看AI相关的新闻"
- "自动驾驶最新进展"
- "科技公司动态"

不是新闻兴趣的例子：
- "今天天气怎么样"
- "帮我写代码"
- "讲个笑话"
- "作业帮帮忙"
- 闲聊、问候、无关话题

规则：只要用户在表达想了解某领域的新闻/资讯/动态/进展，就算新闻兴趣。"""


async def validate_input(text: str) -> dict:
    """第一道校验：敏感词 + 新闻相关性。
    
    Returns:
        {"valid": bool, "error": str | None}
    """
    if not text or not text.strip():
        return {"valid": False, "error": "请输入你感兴趣的新闻领域"}
    
    text = text.strip()
    
    # 1. 敏感词检查
    hit = check_sensitive(text)
    if hit:
        logger.warning("Sensitive word detected in interest input")
        return {"valid": False, "error": "请输入有效的新闻兴趣"}
    
    # 2. 新闻相关性判断（轻量 LLM，~50 tokens）
    try:
        client = get_client()
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{
                "role": "system",
                "content": _NEWS_CHECK_PROMPT.format(user_input=text[:200]),
            }],
            temperature=0,
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content.strip())
        
        if not result.get("is_news_interest", True):
            return {
                "valid": False,
                "error": "请输入你感兴趣的新闻领域，比如"AI 编程工具"、"自动驾驶"、"科技公司动态"",
            }
    except Exception as e:
        logger.warning("News relevance check failed, allowing through: %s", e)
        # 校验失败不阻塞用户，直接放行
    
    return {"valid": True, "error": None}


async def parse_interests(text: str) -> dict:
    """LLM 解析用户自然语言 → 标签 + 关键词。
    
    Returns:
        {"tags": list[str], "keywords": list[str]}
    """
    try:
        client = get_client()
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{
                "role": "system",
                "content": _TAG_PROMPT.format(
                    available_tags=", ".join(_ALL_TAGS),
                    user_input=text[:300],
                ),
            }],
            temperature=0.2,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content.strip())
        
        # 过滤只保留已知标签
        known_tags = [t for t in result.get("tags", []) if t in _ALL_TAGS]
        keywords = result.get("keywords", [])[:3]
        
        return {"tags": known_tags, "keywords": keywords}
    except Exception as e:
        logger.error("Interest parsing failed: %s", e)
        return {"tags": [], "keywords": []}
```

- [ ] **Step 3: 验证 interest_parser 可导入**

```bash
cd d:/项目/ai报道后续修改/ai-news-briefing-agent
python -c "from module_b.ai.interest_parser import validate_input, parse_interests, check_sensitive; print('OK')"
```

（注意：module-b 目录名含连字符，import 需要用 importlib 或调整 sys.path）

---

### Task 3: 轻量版个性化流水线

**Files:**
- Modify: `module-b/pipeline.py`

**Interfaces:**
- Produces: `async def run_personalized_pipeline(pool, briefing_type, briefing_date, filter_tags, openid, interest_text, interest_tags, passed_items) -> dict`
- Consumes: 复用现有的 `summarize`, `semantic_dedup`, `url_dedup`, `match_images_for_briefing`, `_translate_items`, `_insert_briefing`

- [ ] **Step 1: 在 pipeline.py 末尾新增轻量版流水线函数**

```python
async def run_personalized_pipeline(
    pool: asyncpg.Pool,
    briefing_type: str,
    briefing_date: str,
    filter_tags: list[str],
    openid: str,
    interest_text: str,
    interest_tags: list[str],
    passed_items: list[dict],
) -> dict:
    """轻量版专属简报流水线 — 跳过 AI评分/辩论/补充，预计30-45秒。
    
    与 run_pipeline 的区别：
    - 不调用 batch_score（复用现有 ai_score）
    - 不调用 run_debate（耗时大户）
    - 不调用 enrich（LLM 背景补充）
    - 不做跨天去重（专属简报独立去重池）
    """
    import uuid
    from datetime import datetime, timezone, timedelta
    
    stats = {
        "fetched": len(passed_items),
        "passed": len(passed_items),
        "dedup_url_removed": 0,
        "dedup_semantic_removed": 0,
        "aged_out": 0,
        "final_count": 0,
        "personalized": True,
        "interest_tags": interest_tags,
    }
    
    if not passed_items:
        async with pool.acquire() as conn:
            briefing = {"tl_dr": [], "sections": [], "key_takeaways": []}
            briefing_id = await _insert_briefing(conn, briefing_type, briefing_date, briefing, stats)
        return {"briefing_id": briefing_id, "stats": stats, "briefing": briefing}
    
    # ① 时效性门禁（保留）
    now = datetime.now(timezone.utc)
    MIN_FRESH_ITEMS = 8
    AGENCY_FALLBACKS = [36, 48, 72]
    fresh_passed = None
    used_age_hours = AGENCY_FALLBACKS[0]
    for age_hours in AGENCY_FALLBACKS:
        age_cutoff = now - timedelta(hours=age_hours)
        fresh_passed = [
            it for it in passed_items
            if _get_published_at(it) is None or _get_published_at(it) >= age_cutoff
        ]
        used_age_hours = age_hours
        if len(fresh_passed) >= MIN_FRESH_ITEMS:
            break
    stats["aged_out"] = len(passed_items) - len(fresh_passed)
    stats["freshness_hours"] = used_age_hours
    passed = fresh_passed
    
    if not passed:
        async with pool.acquire() as conn:
            briefing = {"tl_dr": [], "sections": [], "key_takeaways": []}
            briefing_id = await _insert_briefing(conn, briefing_type, briefing_date, briefing, stats)
        return {"briefing_id": briefing_id, "stats": stats, "briefing": briefing}
    
    # ② URL 精确去重（保留）
    before_url = len(passed)
    passed = url_dedup(passed)
    stats["dedup_url_removed"] = before_url - len(passed)
    
    # ③ AI 语义去重（保留）
    before_semantic = len(passed)
    passed = await semantic_dedup(passed)
    stats["dedup_semantic_removed"] = before_semantic - len(passed)
    
    # ④ 标签预过滤（核心步骤）
    if filter_tags:
        passed = _filter_items_by_tags(passed, filter_tags)
    
    if not passed:
        async with pool.acquire() as conn:
            briefing = {"tl_dr": [], "sections": [], "key_takeaways": []}
            briefing_id = await _insert_briefing(conn, briefing_type, briefing_date, briefing, stats)
        return {"briefing_id": briefing_id, "stats": stats, "briefing": briefing}
    
    # ⑤ 翻译（保留）
    passed = await _translate_items(passed)
    
    # ⑥ 摘要 + 标签生成（核心，保留）
    briefing = await summarize(passed, briefing_type)
    
    # ⑦ LLM 摘要后兜底过滤（保留）
    if filter_tags:
        briefing = _filter_by_tags(briefing, filter_tags)
    
    # ⑧ 配图匹配（保留）
    briefing = await match_images_for_briefing(briefing)
    
    stats["final_count"] = sum(len(s.get("items", [])) for s in briefing.get("sections", []))
    stats["urls"] = [it.get("url", "") for s in briefing.get("sections", []) for it in s.get("items", []) if it.get("url")]
    
    # ⑨ 写入 briefings 表（带个性化标记）
    async with pool.acquire() as conn:
        briefing_id = await _insert_personalized_briefing(
            conn, briefing_type, briefing_date, briefing, stats,
            openid=openid, interest_text=interest_text, interest_tags=interest_tags,
        )
    
    return {"briefing_id": briefing_id, "stats": stats, "briefing": briefing}


async def _insert_personalized_briefing(
    conn, briefing_type: str, briefing_date: str,
    briefing: dict, stats: dict,
    openid: str, interest_text: str, interest_tags: list[str],
) -> uuid.UUID:
    """写入个性化简报 — 仅 INSERT（不做 upsert），每条都是新的"""
    briefing_id = uuid.uuid4()
    headline = briefing.get("headline", {})
    merged_stats = dict(stats)
    if headline:
        merged_stats["headline"] = headline
    
    await conn.execute(
        """INSERT INTO briefings (id, type, date, tl_dr, sections, key_takeaways, raw_stats,
           requested_by, interest_text, interest_tags, is_personalized)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, true)""",
        briefing_id,
        briefing_type,
        briefing_date,
        json.dumps(briefing.get("tl_dr", []), ensure_ascii=False),
        json.dumps(briefing.get("sections", []), ensure_ascii=False),
        json.dumps(briefing.get("key_takeaways", []), ensure_ascii=False),
        json.dumps(merged_stats, ensure_ascii=False),
        openid,
        interest_text,
        json.dumps(interest_tags, ensure_ascii=False),
    )
    return briefing_id
```

- [ ] **Step 2: 验证 pipeline 函数可导入**

```bash
cd d:/项目/ai报道后续修改/ai-news-briefing-agent
python -c "
import sys, os
sys.path.insert(0, '.')
# 验证语法正确
exec(open('module-b/pipeline.py').read())
print('Syntax OK')
"
```

---

### Task 4: 后端请求/响应模型

**Files:**
- Modify: `module-c/backend/models.py`

**Interfaces:**
- Produces: `GenerateRequest`, `GenerateResponse`, `TaskStatusResponse`, `MyBriefingItem`, `MyBriefingsResponse`

- [ ] **Step 1: 在 models.py 末尾新增模型类**

```python
# ── 个性化简报模型 ────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    openid: str = "anonymous"
    interest_text: str = Field(min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list)
    type: str = Field(default="morning", description="morning / evening")


class GenerateResponse(BaseModel):
    task_id: str
    status: str = "processing"
    valid: bool = True
    error: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # "processing" | "completed" | "failed"
    briefing_id: str | None = None
    error: str | None = None


class MyBriefingItem(BaseModel):
    id: str
    type: str
    date: str
    interest_text: str | None = None
    interest_tags: list[str] = Field(default_factory=list)
    sections: list[dict] = Field(default_factory=list)
    generated_at: str


class MyBriefingsResponse(BaseModel):
    page: int
    size: int
    total: int
    items: list[MyBriefingItem]
```

- [ ] **Step 2: 验证模型语法**

```bash
cd d:/项目/ai报道后续修改/ai-news-briefing-agent/module-c/backend
python -c "from models import GenerateRequest, GenerateResponse, TaskStatusResponse; print('OK')"
```

---

### Task 5: 后端 API 端点

**Files:**
- Modify: `module-c/backend/main.py`

**Interfaces:**
- Consumes: `validate_input`, `parse_interests` from interest_parser; `run_personalized_pipeline` from pipeline; `GenerateRequest`, etc. from models
- Produces: `POST /api/briefings/generate`, `GET /api/briefings/generate/{task_id}`, `GET /api/briefings/my`

- [ ] **Step 1: 在 main.py 添加 import 和任务存储**

在 main.py 文件顶部区域（其他 import 之后）添加：

```python
# ── 个性化简报：import 与任务存储 ────────────────────────────────
import asyncio
from datetime import datetime, timezone
from models import GenerateRequest, GenerateResponse, TaskStatusResponse, MyBriefingsResponse, MyBriefingItem

# 内存任务存储：task_id → {status, briefing_id, error, created_at}
_task_store: dict[str, dict] = {}

# 用户级任务锁：openid → task_id（同一用户只能有一个进行中任务）
_user_tasks: dict[str, str] = {}

# 延迟导入 interest_parser 和 pipeline（startup 时确认可用）
_interest_parser = None
_pipeline_module = None
```

- [ ] **Step 2: 在 startup 中加载模块**

在 `startup()` 函数末尾（`_db_ok = True` 之后）添加：

```python
    # 加载个性化简报依赖
    global _interest_parser, _pipeline_module
    try:
        import importlib.util
        _ip_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "module-b", "ai", "interest_parser.py",
        )
        if os.path.exists(_ip_path):
            spec = importlib.util.spec_from_file_location("interest_parser", _ip_path)
            _interest_parser = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_interest_parser)
        
        _pl_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "module-b", "pipeline.py",
        )
        if os.path.exists(_pl_path):
            spec2 = importlib.util.spec_from_file_location("pipeline_mod", _pl_path)
            _pipeline_module = importlib.util.module_from_spec(spec2)
            spec2.loader.exec_module(_pipeline_module)
        
        print("[module-c] Personalized briefing modules loaded")
    except Exception as e:
        print(f"[module-c] Personalized briefing modules not available: {e}")
```

- [ ] **Step 3: 实现 POST /api/briefings/generate**

```python
@app.post("/api/briefings/generate", response_model=GenerateResponse)
async def generate_briefing(req: GenerateRequest):
    """触发个性化简报生成"""
    if _interest_parser is None or _pipeline_module is None:
        raise HTTPException(503, "Personalized briefing service not available")
    
    # ① 输入校验：敏感词 + 新闻相关性
    validation = await _interest_parser.validate_input(req.interest_text)
    if not validation["valid"]:
        return GenerateResponse(
            task_id="",
            status="rejected",
            valid=False,
            error=validation["error"],
        )
    
    # ② LLM 兴趣解析
    parsed = await _interest_parser.parse_interests(req.interest_text)
    
    # ③ 合并：LLM 解析的标签 + 用户手动选择的标签
    all_tags = list(set(parsed.get("tags", []) + req.tags))
    
    if not all_tags:
        return GenerateResponse(
            task_id="",
            status="rejected",
            valid=False,
            error="未能从你的描述中识别出新闻领域，请尝试用更具体的词汇描述",
        )
    
    # ④ 用户级并发控制：取消旧任务
    task_id = str(uuid.uuid4())
    old_task_id = _user_tasks.get(req.openid)
    if old_task_id and old_task_id in _task_store and _task_store[old_task_id]["status"] == "processing":
        _task_store[old_task_id]["status"] = "cancelled"
        _task_store[old_task_id]["error"] = "Replaced by newer request"
    _user_tasks[req.openid] = task_id
    
    # ⑤ 存入任务记录
    _task_store[task_id] = {
        "status": "processing",
        "briefing_id": None,
        "error": None,
        "created_at": datetime.now(timezone.utc),
    }
    
    # ⑥ 启动后台生成任务
    pool = _db()
    briefing_date = datetime.now().strftime("%Y-%m-%d")
    
    asyncio.create_task(
        _run_personalized_generation(
            task_id=task_id,
            pool=pool,
            briefing_type=req.type,
            briefing_date=briefing_date,
            filter_tags=all_tags,
            openid=req.openid,
            interest_text=req.interest_text,
            interest_tags=all_tags,
        )
    )
    
    return GenerateResponse(task_id=task_id, status="processing", valid=True)
```

- [ ] **Step 4: 实现后台生成函数**

```python
async def _run_personalized_generation(
    task_id: str,
    pool,
    briefing_type: str,
    briefing_date: str,
    filter_tags: list[str],
    openid: str,
    interest_text: str,
    interest_tags: list[str],
):
    """后台执行个性化简报生成，完成后更新 _task_store"""
    try:
        # 查找最新 batch 的 raw_items
        async with pool.acquire() as conn:
            latest_batch = await conn.fetchval(
                "SELECT batch_id FROM raw_items ORDER BY fetched_at DESC LIMIT 1"
            )
            if not latest_batch:
                _task_store[task_id]["status"] = "failed"
                _task_store[task_id]["error"] = "暂无新闻数据，请稍后再试"
                return
            
            # 读取 raw_items
            rows = await conn.fetch(
                "SELECT id, source, title, url, content, author, published_at, metadata, batch_id "
                "FROM raw_items WHERE batch_id = $1",
                latest_batch,
            )
        
        items = [dict(r) for r in rows]
        
        if not items:
            _task_store[task_id]["status"] = "failed"
            _task_store[task_id]["error"] = "暂无新闻数据，请稍后再试"
            return
        
        # 同步 metadata 中的 tags 到 item 顶层
        for it in items:
            meta = it.get("metadata")
            if isinstance(meta, str):
                try:
                    import json as _json
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}
            if not isinstance(meta, dict):
                meta = {}
            if not it.get("tags") and meta.get("tags"):
                it["tags"] = meta["tags"]
            if not it.get("ai_score") and meta.get("ai_score"):
                it["ai_score"] = float(meta["ai_score"])
            it["metadata"] = meta
        
        # 运行轻量流水线
        result = await _pipeline_module.run_personalized_pipeline(
            pool=pool,
            briefing_type=briefing_type,
            briefing_date=briefing_date,
            filter_tags=filter_tags,
            openid=openid,
            interest_text=interest_text,
            interest_tags=interest_tags,
            passed_items=items,
        )
        
        _task_store[task_id]["status"] = "completed"
        _task_store[task_id]["briefing_id"] = str(result["briefing_id"])
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        _task_store[task_id]["status"] = "failed"
        _task_store[task_id]["error"] = str(e)[:200]
```

- [ ] **Step 5: 实现 GET /api/briefings/generate/{task_id}**

```python
@app.get("/api/briefings/generate/{task_id}", response_model=TaskStatusResponse)
async def get_generation_status(task_id: str):
    """轮询个性化简报生成状态"""
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    
    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        briefing_id=task.get("briefing_id"),
        error=task.get("error"),
    )
```

- [ ] **Step 6: 实现 GET /api/briefings/my**

```python
@app.get("/api/briefings/my", response_model=MyBriefingsResponse)
async def get_my_briefings(
    openid: str = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """获取用户的专属简报历史"""
    try:
        pool = _db()
        offset = (page - 1) * size
        
        total = await pool.fetchval(
            "SELECT COUNT(*) FROM briefings WHERE requested_by = $1 AND is_personalized = true",
            openid,
        )
        
        rows = await pool.fetch(
            """SELECT id, type, date, interest_text, interest_tags, sections, generated_at
               FROM briefings
               WHERE requested_by = $1 AND is_personalized = true
               ORDER BY date DESC, generated_at DESC
               OFFSET $2 LIMIT $3""",
            openid, offset, size,
        )
        
        items = [
            MyBriefingItem(
                id=str(r["id"]),
                type=r["type"],
                date=str(r["date"]),
                interest_text=r["interest_text"],
                interest_tags=_parse_json_field(r["interest_tags"]),
                sections=_normalize_sections(r["sections"]),
                generated_at=r["generated_at"].isoformat(),
            )
            for r in rows
        ]
        
        return MyBriefingsResponse(page=page, size=size, total=total or 0, items=items)
    except RuntimeError:
        # Mock 模式返回空
        return MyBriefingsResponse(page=page, size=size, total=0, items=[])
```

- [ ] **Step 7: 启动后端验证 API**

```bash
cd d:/项目/ai报道后续修改/ai-news-briefing-agent/module-c/backend
python main.py &
sleep 3
# 测试 generate 端点
curl -X POST http://localhost:8003/api/briefings/generate \
  -H "Content-Type: application/json" \
  -d '{"openid":"test","interest_text":"AI编程工具","tags":[],"type":"morning"}'
```

---

### Task 6: 前端 API 工具函数

**Files:**
- Modify: `module-c/miniprogram/utils/api.js`

**Interfaces:**
- Produces: `generateBriefing(openid, interestText, tags, type)` → `Promise<{task_id, status, valid, error}>`
- Produces: `getGenerateStatus(taskId)` → `Promise<{status, briefing_id, error}>`
- Produces: `getMyBriefings(openid, page, size)` → `Promise<{page, size, total, items}>`

- [ ] **Step 1: 在 api.js 的 module.exports 中添加3个新方法**

在 `module-c/miniprogram/utils/api.js` 的 `module.exports` 对象末尾（在 chatSend 之后）添加：

```javascript
  // 个性化简报
  generateBriefing(openid, interestText, tags, type) {
    return request("/api/briefings/generate", "POST", {
      openid: openid || "anonymous",
      interest_text: interestText,
      tags: tags || [],
      type: type || "morning",
    });
  },

  getGenerateStatus(taskId) {
    return request(`/api/briefings/generate/${encodeURIComponent(taskId)}`);
  },

  getMyBriefings(openid, page, size) {
    const p = page || 1;
    const s = size || 20;
    return request(`/api/briefings/my?openid=${encodeURIComponent(openid || 'anonymous')}&page=${p}&size=${s}`);
  },
```

- [ ] **Step 2: 验证语法**

```bash
cd d:/项目/ai报道后续修改/ai-news-briefing-agent/module-c/miniprogram/utils
node -c api.js && echo "Syntax OK"
```

---

### Task 7: 首页 — 可折叠输入面板 + 轮询 + 展示

**Files:**
- Modify: `module-c/miniprogram/pages/index/index.wxml`
- Modify: `module-c/miniprogram/pages/index/index.js`
- Modify: `module-c/miniprogram/pages/index/index.wxss`

- [ ] **Step 1: 修改 index.wxml — 在 tab-bar 和 loading 之间插入输入面板**

在 `index.wxml` 的 `</view>` (tab-bar 结尾) 和 `<!-- 加载中 -->` 之间插入：

```xml
  <!-- 个性化兴趣输入面板 -->
  <view class="interest-panel {{interestPanelExpanded ? 'expanded' : ''}}">
    <view class="interest-toggle" bindtap="onToggleInterestPanel">
      <text class="interest-toggle-text">
        {{interestPanelExpanded ? '收起定制面板 ▴' : '✨ 定制你的专属简报 ▾'}}
      </text>
    </view>
    <view class="interest-body" wx:if="{{interestPanelExpanded}}">
      <textarea
        class="interest-textarea"
        placeholder="输入你感兴趣的新闻领域，如：AI编程工具、自动驾驶最新进展..."
        value="{{interestText}}"
        bindinput="onInterestInput"
        maxlength="200"
        auto-height
      />
      <view class="quick-tags-row" wx:if="{{quickTags.length > 0}}">
        <text
          wx:for="{{quickTags}}"
          wx:key="tag"
          class="quick-tag {{item.selected ? 'selected' : ''}}"
          data-tag="{{item.tag}}"
          bindtap="onQuickTagTap"
        >{{item.label_zh}}</text>
      </view>
      <button
        class="generate-btn"
        bindtap="onGenerateBriefing"
        disabled="{{generating || !interestText}}"
      >{{generating ? '⏳ 生成中...' : '🔍 生成我的简报'}}</button>
    </view>
  </view>

  <!-- 生成状态提示 -->
  <view class="generating-overlay" wx:if="{{generating}}">
    <view class="generating-card">
      <view class="generating-spinner"></view>
      <text class="generating-text">正在为你精选新闻…</text>
      <text class="generating-hint">预计需要 30-45 秒，请耐心等待</text>
      <text class="generating-elapsed">{{pollCount * 2}} 秒</text>
      <button class="cancel-btn" bindtap="onCancelGeneration">取消</button>
    </view>
  </view>

  <!-- 个性化标记 -->
  <view wx:if="{{isPersonalized && briefing}}" class="personalized-banner">
    🔍 按你的兴趣生成：<text class="fw600">{{personalizedTags.join('、')}}</text>
  </view>
```

- [ ] **Step 2: 修改 index.js — 新增数据和交互逻辑**

在 `Page({ data: { ... } })` 中新增字段：

```javascript
    // 个性化简报
    interestPanelExpanded: false,
    interestText: "",
    quickTags: [],
    selectedQuickTags: [],
    generating: false,
    taskId: null,
    pollTimer: null,
    pollCount: 0,
    MAX_POLLS: 90,
    isPersonalized: false,
    personalizedTags: [],
```

在 methods 区域新增以下方法（放在 `onMiniImageError` 之后）：

```javascript
  onToggleInterestPanel() {
    const expanded = !this.data.interestPanelExpanded;
    this.setData({ interestPanelExpanded: expanded });
    if (expanded && this.data.quickTags.length === 0) {
      this._loadQuickTags();
    }
  },

  async _loadQuickTags() {
    try {
      const data = await api.getTags();
      const allTags = (data.tags || []).map(t => ({ ...t, selected: false }));
      // 从全局活跃标签中筛出有新闻的，取前8个
      const activeSet = getApp().globalData.activeTagSet || {};
      const hasActive = Object.keys(activeSet).length > 0;
      const available = hasActive
        ? allTags.filter(t => activeSet[t.tag])
        : allTags;
      this.setData({ quickTags: available.slice(0, 8) });
    } catch (e) {
      // 标签加载失败不阻塞
    }
  },

  onQuickTagTap(e) {
    const tag = e.currentTarget.dataset.tag;
    const quickTags = this.data.quickTags.map(t => {
      if (t.tag === tag) t.selected = !t.selected;
      return t;
    });
    const selectedQuickTags = quickTags.filter(t => t.selected).map(t => t.tag);
    this.setData({ quickTags, selectedQuickTags });
  },

  onInterestInput(e) {
    this.setData({ interestText: e.detail.value });
  },

  async onGenerateBriefing() {
    const { interestText, selectedQuickTags, generating } = this.data;
    if (generating || !interestText.trim()) return;

    this.setData({ generating: true, pollCount: 0 });

    try {
      const openid = getApp().globalData.openid || "anonymous";
      const resp = await api.generateBriefing(
        openid,
        interestText.trim(),
        selectedQuickTags,
        this.data.currentTab
      );

      if (!resp.valid) {
        wx.showToast({ title: resp.error || "输入无效", icon: "none", duration: 2500 });
        this.setData({ generating: false });
        return;
      }

      this.setData({ taskId: resp.task_id });
      this._startPolling();
    } catch (e) {
      console.error("Generate briefing failed:", e);
      wx.showToast({ title: "提交失败，请重试", icon: "none" });
      this.setData({ generating: false });
    }
  },

  _startPolling() {
    const poll = () => {
      if (this.data.pollCount >= this.data.MAX_POLLS) {
        this.setData({ generating: false });
        wx.showToast({ title: "生成超时，请稍后重试", icon: "none" });
        return;
      }

      api.getGenerateStatus(this.data.taskId).then(status => {
        const count = this.data.pollCount + 1;
        this.setData({ pollCount: count });

        if (status.status === "completed" && status.briefing_id) {
          this.setData({ generating: false, interestPanelExpanded: false });
          // 获取并展示专属简报
          api.getBriefingDetail(status.briefing_id).then(briefing => {
            this._displayPersonalizedBriefing(briefing);
          }).catch(() => {
            wx.showToast({ title: "获取简报失败", icon: "none" });
          });
        } else if (status.status === "failed") {
          this.setData({ generating: false });
          wx.showToast({ title: status.error || "生成失败，请重试", icon: "none" });
        } else if (status.status === "cancelled") {
          this.setData({ generating: false });
        } else {
          // 继续轮询
          this.data.pollTimer = setTimeout(poll, 2000);
        }
      }).catch(() => {
        if (this.data.pollCount < 10) {
          this.data.pollTimer = setTimeout(poll, 2000);
        } else {
          this.setData({ generating: false });
          wx.showToast({ title: "网络异常，请重试", icon: "none" });
        }
      });
    };

    poll();
  },

  _displayPersonalizedBriefing(briefing) {
    // 复用现有展示逻辑，但标记为个性化
    const tags = briefing.interest_tags || [];
    const expanded = {};
    (briefing.sections || []).forEach((s, i) => { expanded[i] = i < 2; });
    const totalItems = (briefing.sections || []).reduce((sum, s) => sum + (s.items || []).length, 0);

    this.setData({
      briefing,
      dateText: formatFullDate(briefing.date),
      totalItems,
      sectionsExpanded: expanded,
      loading: false,
      isPersonalized: true,
      personalizedTags: tags,
    });
    wx.pageScrollTo({ scrollTop: 0 });
  },

  onCancelGeneration() {
    if (this.data.pollTimer) {
      clearTimeout(this.data.pollTimer);
    }
    this.setData({ generating: false });
  },
```

同时修改 `onShow` 清除旧标签更新逻辑中的问题（已经存在 personalized 状态时不要被覆盖）：

```javascript
  onShow() {
    // 如果是显示个性化简报，不要被通用简报刷新
    if (this.data.isPersonalized && this.data.briefing) return;
    
    const tags = getApp().globalData.userTags || wx.getStorageSync("userTags") || [];
    if (tags.join(",") !== (this.data.activeTags || []).join(",")) {
      this.setData({ activeTags: tags });
      const type = this.data.currentTab;
      this.fetchLatest(type);
    }
  },
```

- [ ] **Step 3: 修改 index.wxss — 添加样式**

在 `index.wxss` 末尾添加：

```css
/* ── 个性化输入面板 ── */
.interest-panel {
  margin: 12rpx 24rpx;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16rpx;
  overflow: hidden;
  transition: all 0.3s;
}

.interest-toggle {
  padding: 20rpx 28rpx;
}

.interest-toggle-text {
  color: #fff;
  font-size: 28rpx;
  font-weight: 600;
}

.interest-body {
  padding: 0 28rpx 28rpx;
}

.interest-textarea {
  width: 100%;
  min-height: 120rpx;
  background: rgba(255,255,255,0.15);
  border-radius: 12rpx;
  padding: 20rpx;
  color: #fff;
  font-size: 28rpx;
  box-sizing: border-box;
}

.interest-textarea::placeholder {
  color: rgba(255,255,255,0.5);
}

.quick-tags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  margin-top: 16rpx;
}

.quick-tag {
  padding: 8rpx 20rpx;
  background: rgba(255,255,255,0.15);
  color: #fff;
  border-radius: 24rpx;
  font-size: 24rpx;
  border: 1rpx solid rgba(255,255,255,0.3);
}

.quick-tag.selected {
  background: #fff;
  color: #667eea;
  font-weight: 600;
}

.generate-btn {
  margin-top: 20rpx;
  width: 100%;
  background: #fff;
  color: #667eea;
  font-weight: 700;
  font-size: 30rpx;
  border-radius: 12rpx;
  padding: 16rpx 0;
}

.generate-btn[disabled] {
  background: rgba(255,255,255,0.3);
  color: rgba(255,255,255,0.6);
}

/* ── 生成中蒙层 ── */
.generating-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.generating-card {
  background: #fff;
  border-radius: 20rpx;
  padding: 60rpx 40rpx;
  width: 500rpx;
  text-align: center;
}

.generating-spinner {
  width: 60rpx;
  height: 60rpx;
  margin: 0 auto 24rpx;
  border: 4rpx solid #eee;
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.generating-text {
  display: block;
  font-size: 32rpx;
  font-weight: 600;
  color: #333;
  margin-bottom: 12rpx;
}

.generating-hint {
  display: block;
  font-size: 24rpx;
  color: #999;
  margin-bottom: 8rpx;
}

.generating-elapsed {
  display: block;
  font-size: 24rpx;
  color: #4a90d9;
  margin-bottom: 24rpx;
}

.cancel-btn {
  background: #f0f0f0;
  color: #999;
  font-size: 26rpx;
  padding: 12rpx 40rpx;
  border-radius: 8rpx;
}

/* ── 个性化标记 ── */
.personalized-banner {
  margin: 0 24rpx 16rpx;
  padding: 16rpx 24rpx;
  background: #f0f4ff;
  border-left: 6rpx solid #667eea;
  border-radius: 8rpx;
  font-size: 26rpx;
  color: #555;
}

.fw600 {
  font-weight: 600;
  color: #333;
}
```

- [ ] **Step 4: 语法检查**

```bash
cd d:/项目/ai报道后续修改/ai-news-briefing-agent/module-c/miniprogram
node -c pages/index/index.js && echo "JS OK"
```

---

### Task 8: 历史页 — 专属简报筛选

**Files:**
- Modify: `module-c/miniprogram/pages/history/history.js`
- Modify: `module-c/miniprogram/pages/history/history.wxml`

- [ ] **Step 1: 修改 history.js — 新增专属/通用筛选**

在 `data` 区域新增：

```javascript
    // 个性化筛选
    briefType: "",    // "" | "personalized" | "general"
```

在 methods 区域新增筛选切换方法：

```javascript
  onFilterBriefType(e) {
    const t = e.currentTarget.dataset.btype;
    const newType = this.data.briefType === t ? "" : t;
    this.setData({ briefType: newType, page: 1, list: [], noMore: false });
    this._fetchByType(newType);
  },

  async _fetchByType(briefType) {
    if (briefType === "personalized") {
      // 切换到专属简报数据源
      this.setData({ loading: true });
      try {
        const openid = getApp().globalData.openid || "anonymous";
        const data = await api.getMyBriefings(openid, this.data.page, this.data.size);
        const items = (data.items || []).map(item => ({
          ...item,
          dateText: formatDate(item.date),
          timeAgoText: timeAgo(item.generated_at),
          isPersonalized: true,
          interestText: item.interest_text || "",
          interestTags: item.interest_tags || [],
        }));
        this.setData({
          list: items,
          total: data.total,
          loading: false,
          noMore: items.length >= data.total,
        });
      } catch (e) {
        console.error("fetch my briefings failed:", e);
        this.setData({ loading: false });
      }
    } else {
      // 恢复通用简报列表
      this.setData({ page: 1, list: [], noMore: false });
      this.fetchList();
    }
  },
```

修改 `fetchList` 方法，当 `briefType === "personalized"` 时走专属接口：

```javascript
  async fetchList(overrides = {}) {
    if (this.data.briefType === "personalized") {
      return this._fetchByType("personalized");
    }
    // ... 原有逻辑不变
  },
```

- [ ] **Step 2: 修改 history.wxml — 添加筛选按钮和差异化卡片**

在筛选区域（onClearFilters 按钮附近）添加专属/通用筛选按钮：

```xml
  <!-- 简报类型筛选 -->
  <view class="filter-row" style="margin-top: 16rpx;">
    <text class="filter-label">类型：</text>
    <text
      class="filter-chip {{briefType === 'personalized' ? 'active' : ''}}"
      data-btype="personalized"
      bindtap="onFilterBriefType"
    >我的专属</text>
    <text
      class="filter-chip {{briefType === 'general' ? 'active' : ''}}"
      data-btype="general"
      bindtap="onFilterBriefType"
    >通用简报</text>
  </view>
```

在列表卡片中，如果是专属简报，显示兴趣描述：

```xml
  <!-- 在现有的卡片内容区域（每个 list item 循环内），标题下方添加 -->
  <view wx:if="{{item.isPersonalized}}" class="personalized-card-tag">
    🔍 {{item.interestText || '自定义兴趣'}}
  </view>
```

- [ ] **Step 3: 语法检查**

```bash
cd d:/项目/ai报道后续修改/ai-news-briefing-agent/module-c/miniprogram
node -c pages/history/history.js && echo "JS OK"
```

---

### Task 9: 端到端集成测试

**Files:**
- 无新增文件

- [ ] **Step 1: 启动后端并测试全流程**

```bash
# 终端1：启动后端
cd d:/项目/ai报道后续修改/ai-news-briefing-agent/module-c/backend
python main.py

# 终端2：测试 API
# 1. 提交生成请求
curl -s -X POST http://localhost:8003/api/briefings/generate \
  -H "Content-Type: application/json" \
  -d '{"openid":"test_user","interest_text":"AI编程工具和开源大模型","tags":["开源"],"type":"morning"}'

# 预期返回：{"task_id":"...","status":"processing","valid":true}

# 2. 轮询状态（用返回的 task_id 替换）
curl -s http://localhost:8003/api/briefings/generate/<TASK_ID>

# 预期返回：{"task_id":"...","status":"completed","briefing_id":"...","error":null}

# 3. 获取专属简报详情
curl -s http://localhost:8003/api/briefings/<BRIEFING_ID>

# 4. 验证敏感词拦截
curl -s -X POST http://localhost:8003/api/briefings/generate \
  -H "Content-Type: application/json" \
  -d '{"openid":"test","interest_text":"六四事件","tags":[],"type":"morning"}'

# 预期返回：{"task_id":"","status":"rejected","valid":false,"error":"请输入有效的新闻兴趣"}

# 5. 获取专属简报历史
curl -s "http://localhost:8003/api/briefings/my?openid=test_user&page=1&size=10"
```

- [ ] **Step 2: 验证前端编译**

在微信开发者工具中打开 `module-c/miniprogram`，检查：
- 首页可折叠面板展开/收起正常
- 输入兴趣文本+提交后显示加载蒙层
- 生成完成后展示专属简报
- 历史页"我的专属"筛选可用
- 专属简报卡片显示兴趣描述

---

## Task Dependency Order

```
Task 1 (DB) ──┐
Task 2 (Parser) ──┤
Task 3 (Pipeline) ─┤
Task 4 (Models) ──┤
                  ├── Task 5 (API) ── Task 6 (Frontend API) ── Task 7 (Index) ── Task 9 (E2E)
                  │                                              └─ Task 8 (History) ──┘
                  └── Task 9 (Sensitive config)
```

Tasks 1-4 可并行执行；Task 5 依赖 1-4；Task 6 依赖 5；Tasks 7-8 依赖 6；Task 9 收尾验证。
