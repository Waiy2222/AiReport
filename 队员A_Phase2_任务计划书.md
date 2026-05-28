# 队员 A — Phase 2 任务计划书

> 模块：Module A — 资讯抓取 + LLM 智能筛选
> 目标：把硬编码关键词过滤替换为 LLM 动态相关性判断，集成 RAG 检索 + embedding 生成
> 基线：Phase 1 的 34 个单元测试全部通过

---

## 一、总体架构变更

### Phase 1 流程（当前）
```
外部API → httpx GET → 关键词硬编码过滤 → 写 raw_items
```

### Phase 2 流程（目标）
```
外部API → httpx GET → 粗筛(关键词+去重) → LLM相关性判断 → 生成embedding → 写 raw_items + embedding
                              │                │                  │
                              │     ┌──────────┘     ┌────────────┘
                              │     ▼                ▼
                              │  DeepSeek 评分    shared/rag.py
                              │  (1-10分+标签)    pgvector 余弦检索
                              │     │
                              │     ▼
                              │  RAG 检索相似历史 → 拼入 LLM prompt
```

### 涉及文件总览

| 文件 | 操作 | 说明 |
|------|------|------|
| `module-a/llm_filter.py` | **新增** | LLM 相关性判断 + RAG 上下文 + embedding 生成 |
| `module-a/main.py` | **修改** | 恢复 SCRAPERS + _fetch_source + LLM 筛选步骤 |
| `module-a/orchestrator.py` | **修改** | 加 LLM 筛选 + embedding 生成步骤 |
| `module-a/scrapers/__init__.py` | **修改** | 恢复 _insert_items + SCRAPERS 注册表 |
| `module-a/scrapers/github.py` | **微调** | per_page 保持 30（已满足） |
| `module-a/scrapers/hackernews.py` | **修改** | 检查量 100→300 |
| `module-a/scrapers/rss.py` | **微调** | 可选加更多 RSS 源 |
| `module-a/scrapers/reddit.py` | **微调** | 可选，不改也行 |
| `module-a/requirements.txt` | **修改** | 加 openai 依赖 |

---

## 二、逐文件详细计划

---

### 文件 1：`module-a/llm_filter.py`（新增）

**功能**：LLM 批量相关性判断 + RAG 上下文组装 + embedding 生成 + 无 API Key 回退

**依赖**：
- `shared/rag.py`（组长提供：`generate_embedding`, `generate_embeddings_batch`, `search_similar_items`）
- `module-b/ai/pipeline.py:248-317`（参考：LLM 评分 prompt 结构、`_extract_json`、`_mock_score_one`）

#### 功能函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `_has_api_key` | `() -> bool` | 检查 DEEPSEEK_API_KEY 是否配置 |
| `_get_client` | `() -> AsyncOpenAI \| None` | 创建 DeepSeek 兼容的 OpenAI 客户端 |
| `_llm_chat` | `async (messages, temperature, max_tokens) -> str \| None` | 单次 LLM 调用 |
| `_extract_json` | `(text) -> str` | 从 LLM 响应提取纯 JSON（处理 ```json 包裹） |
| `_mock_score_one` | `(item) -> float` | 无 API Key 时的启发式评分 |
| `_build_filter_prompt` | `(items, rag_context) -> str` | 构建 LLM 筛选 prompt（含 RAG 参考案例） |
| `_get_rag_context` | `async (pool, items) -> tuple[str, dict]` | RAG 检索 + 返回 (上下文文本, {url: embedding} 缓存) |
| `_score_items` | `async (items, rag_context) -> list[dict]` | 批量调 LLM 评分（无 key 时回退到 `_mock_score_one`） |
| `filter_and_enrich` | `async (pool, items, threshold) -> tuple[list[dict], bool]` | **主函数**：LLM 筛选 + embedding 生成 |

#### 主函数 `filter_and_enrich` 流程

```python
async def filter_and_enrich(
    pool: asyncpg.Pool,
    items: list[dict],
    threshold: float = 6.0,
) -> tuple[list[dict], bool]:
    """
    输入：粗筛后的候选条目列表（含 title/content/source/metadata）
    输出：(通过筛选的条目列表, 是否使用了LLM)
    副作用：通过的条目 metadata 中写入 ai_score/tags/filter_reason，embedding 字段填充
    """
    # 0. 缓存 API Key 状态（避免执行期间环境变量变化导致不一致）
    used_llm = _has_api_key()

    # 1. RAG 检索相似历史案例（同时获取缓存的 embedding）
    if used_llm:
        rag_context, cached_embs = await _get_rag_context(pool, items)
    else:
        rag_context, cached_embs = "", {}

    # 2. LLM 批量评分（或回退到启发式）
    scored_items = await _score_items(items, rag_context)

    # 3. 过滤低分
    passed = [it for it in scored_items if it["metadata"].get("ai_score", 0) >= threshold]

    # 4. 生成 embedding（复用缓存，只为新条目调 API）
    if passed:
        texts_to_embed, indices_to_embed = [], []
        for i, it in enumerate(passed):
            if it.get("url") in cached_embs:
                it["embedding"] = cached_embs[it["url"]]  # 复用
            else:
                texts_to_embed.append(f"{it['title']} {it.get('content', '')[:200]}")
                indices_to_embed.append(i)
        if texts_to_embed:
            new_embs = await generate_embeddings_batch(texts_to_embed)
            if new_embs:
                for i, emb in zip(indices_to_embed, new_embs):
                    passed[i]["embedding"] = emb

    return passed, used_llm
```

#### `_get_rag_context` 流程（含 embedding 缓存）

```python
async def _get_rag_context(pool, items, top_k=5) -> tuple[str, dict]:
    """RAG 检索 + 返回 (上下文文本, {url: embedding} 缓存供复用)"""
    # 取前 3 个候选条目生成 embedding
    sample_texts = [f"{it['title']} {it.get('content','')[:200]}" for it in items[:3]]
    sample_embs = await generate_embeddings_batch(sample_texts)

    # 构建缓存 map（供 filter_and_enrich 复用）
    cached_embs = {}
    if sample_embs:
        for it, emb in zip(items[:3], sample_embs):
            if emb:
                cached_embs[it.get("url", "")] = emb

    # 在 raw_items 中检索相似历史
    all_similar = []
    for emb in (sample_embs or []):
        if emb:
            similar = await search_similar_items(pool, emb, top_k=top_k)
            all_similar.extend(similar)

    # 去重 + 格式化为上下文文本
    seen_ids = set()
    context_lines = []
    for s in all_similar:
        if s["id"] not in seen_ids:
            seen_ids.add(s["id"])
            tags = ", ".join(s.get("tags", []))
            context_lines.append(f"- [{s['source']}] {s['title']} (相似度:{s['similarity']}, 标签:{tags})")

    return "\n".join(context_lines) if context_lines else "", cached_embs
```

#### `_build_filter_prompt` 结构

```
请对以下每条AI资讯进行相关性评估。

评分标准：
- 10分：重大AI突破/顶级公司重要发布/划时代开源项目
- 8-9分：知名公司/项目动态/重要工具发布/有影响力论文
- 6-7分：有价值的行业资讯/中等影响力开源项目
- 4-5分：一般性技术讨论/边缘相关
- 1-3分：与AI核心领域关联较弱

参考历史案例（相似资讯）：
{rag_context}

候选条目：
[0] 标题: xxx
    来源: github
    内容: xxx

[1] 标题: xxx
    来源: hackernews
    内容: xxx

以JSON数组格式返回：
[{"index":0,"score":8.5,"tags":["LLM","开源"],"reason":"重要开源项目发布"}, ...]
```

#### 调试检测点

| # | 检测点 | 验证方法 |
|---|--------|----------|
| D1 | `_has_api_key()` 无 key 时返回 False | 设置/清空环境变量，断言返回值 |
| D2 | `_extract_json` 处理 ```json 包裹 | 传入带 fence 的字符串，验证提取正确 |
| D3 | `_extract_json` 处理纯 JSON | 传入 `[{"index":0,"score":8}]`，验证不变 |
| D4 | `_mock_score_one` 对高信号条目给高分 | `test_mock_score_high_signal`：传入含 "DeepSeek" + "开源" 的条目，断言 score > 7 |
| D5 | `_mock_score_one` 对无关条目给低分 | `test_mock_score_low_signal`：传入 "Best hiking trails"，断言 score < 5 |
| D6 | `_build_prompt` 包含 RAG 上下文 | 传入 items + rag_context，验证 prompt 含 "参考历史案例" |
| D7 | `filter_and_enrich` 无 API Key 回退 | 清空 key，调用主函数，验证返回 (items, False) |
| D8 | `filter_and_enrich` 有 API Key 走 LLM | Mock LLM 响应，验证返回 (items, True) |
| D9 | embedding 生成 | 验证通过的条目 embedding 字段非空 |
| D10 | RAG 上下文组装 | Mock search_similar_items，验证 prompt 包含历史案例 |

#### 测试方案（`test_llm_filter.py`）

| 测试用例 | 输入 | 预期结果 |
|----------|------|----------|
| `test_has_api_key_false` | 无环境变量 | 返回 False |
| `test_has_api_key_true` | 设置 `sk-xxx` | 返回 True |
| `test_extract_json_fenced` | `"```json\n[1,2]\n```"` | `"[1,2]"` |
| `test_extract_json_plain` | `"[1,2]"` | `"[1,2]"` |
| `test_extract_json_nested` | `"text [{...}] end"` | 正确提取嵌套 JSON |
| `test_mock_score_high_signal` | DeepSeek + 开源条目 | score >= 7.0 |
| `test_mock_score_low_signal` | 无关条目 (hiking) | score <= 5.0 |
| `test_mock_score_medium` | 一般技术讨论 | 5.0 <= score <= 7.0 |
| `test_build_prompt_contains_items` | 2 items + context | prompt 含条目标题 |
| `test_build_prompt_contains_rag` | 有 RAG 上下文 | prompt 含 "参考历史案例" |
| `test_build_prompt_contains_criteria` | 任意 items | prompt 含评分标准 |
| `test_filter_enrich_fallback` | 无 API Key | 返回 (scored_items, False) |
| `test_filter_enrich_with_llm` | Mock LLM 响应 | 返回 (filtered_items, True) |
| `test_filter_threshold` | threshold=8.0 | 低分条目被过滤 |
| `test_embedding_attached` | Mock embedding | 通过条目有 embedding 字段 |

---

### 文件 2：`module-a/main.py`（修改）

**变更原因**：集成 LLM 筛选步骤；恢复集成测试需要的 `_fetch_source` / `_get_pool_or_503` / `SCRAPERS`

#### 变更点

| 变更 | 说明 |
|------|------|
| 恢复 `SCRAPERS` 字典 | `from scrapers import SCRAPERS` — 集成测试需要 |
| 恢复 `_get_pool_or_503()` | 集成测试 `test_get_pool_or_503_raises_when_no_db` 需要 |
| 新增 `_fetch_source()` | 集成测试 `test_fetch_source_*` 需要 |
| 更新 `/run` 端点 | 加 LLM 筛选步骤，返回 `llm_filtered` 字段 |

#### 完整新代码

```python
"""Module A — 资讯抓取 + LLM 智能筛选 (:8001)"""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db import get_pool, init_db, close_db
from scrapers import SCRAPERS, _insert_items

logger = logging.getLogger(__name__)
app = FastAPI(title="Module A - News Fetcher")

SOURCES = ["github", "hackernews", "rss"]


@app.on_event("startup")
async def startup():
    try:
        await init_db()
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown():
    await close_db()


class FetchRequest(BaseModel):
    batch_id: uuid.UUID = Field(..., description="批次唯一标识")
    hours_back: int = Field(default=12, ge=1, le=168, description="回溯小时数")


@app.get("/health")
async def health():
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception:
        return {"status": "ok", "db": "disconnected"}


def _get_pool_or_503():
    """获取数据库连接池，未初始化则抛 503"""
    try:
        return get_pool()
    except RuntimeError:
        raise HTTPException(503, "database not initialized")


async def _fetch_source(pool, source: str, since: datetime, batch_id: uuid.UUID) -> int:
    """调度单个 scraper 并返回抓取条目数（DB 写入由 orchestrator.run_pipeline 统一处理）。

    注意：此函数仅用于集成测试验证 scraper 调度逻辑。
    生产流程走 orchestrator.run_pipeline → run_all_scrapers → bulk_insert。
    """
    scraper = SCRAPERS.get(source)
    if scraper is None:
        logger.warning(f"Unknown scraper: {source}")
        return 0
    try:
        items = await scraper(pool, since, batch_id)
        return len(items)
    except Exception as e:
        logger.warning(f"Scraper [{source}] failed: {e}")
        return 0


@app.post("/run")
async def run(req: FetchRequest):
    pool = _get_pool_or_503()
    since = datetime.now(timezone.utc) - timedelta(hours=req.hours_back)

    from orchestrator import run_pipeline

    result = await run_pipeline(pool, since, req.batch_id, SOURCES)

    all_zero = all(v == 0 for v in result["per_source"].values())
    status = "partial" if all_zero else "ok"

    return {
        "status": status,
        "fetched": result["fetched"],
        "llm_filtered": result["llm_filtered"],
        "batch_id": str(req.batch_id),
        "per_source": result["per_source"],
    }
```

#### 调试检测点

| # | 检测点 | 验证方法 |
|---|--------|----------|
| D1 | `/health` 无 DB 返回 ok+disconnected | 不初始化 pool，GET /health |
| D2 | `/health` 有 DB 返回 ok+connected | 初始化 pool，GET /health |
| D3 | `_get_pool_or_503` 无 pool 抛 503 | 不初始化，断言 HTTPException(503) |
| D4 | `_fetch_source` 未知源返回 0 | 传 "nonexistent"，断言返回 0 |
| D5 | `_fetch_source` 异常返回 0 | Mock scraper 抛异常，断言返回 0 |
| D6 | `/run` 无 DB 返回 503 | 不初始化 pool，POST /run |
| D7 | `/run` 正常返回含 llm_filtered | Mock 全链路，验证响应结构 |

#### 测试方案

集成测试 `tests/test_module_a.py` 已覆盖 D1-D6。需验证这些测试在修改后仍通过。

---

### 文件 3：`module-a/orchestrator.py`（修改）

**变更原因**：在抓取→去重→写入之间插入 LLM 筛选 + embedding 生成步骤

#### 现有函数（保留不变）

| 函数 | 说明 |
|------|------|
| `dedup_by_url(items)` | URL 去重（保留逻辑不变） |
| `bulk_insert(pool, items)` | 批量写入（需支持 embedding 列） |

#### 变更函数

| 函数 | 变更 |
|------|------|
| `run_all_scrapers` | 保留为内部函数（被 `run_pipeline` 调用），不改名 |

#### 新增函数

（无。embedding 生成在 `llm_filter.filter_and_enrich` 内部完成，orchestrator 不直接调用。）

#### `run_pipeline` 完整流程

```python
async def run_pipeline(
    pool: asyncpg.Pool,
    since: datetime,
    batch_id: uuid_lib.UUID,
    enabled_sources: list[str],
) -> dict:
    """Phase 2 完整流程：抓取 → 去重 → LLM 筛选 → embedding → 写入"""
    # Step 1: 并发抓取
    items, per_source = await run_all_scrapers(since, batch_id, enabled_sources)

    if not items:
        return {"fetched": 0, "llm_filtered": False, "per_source": per_source}

    # Step 2: LLM 筛选 + embedding 生成
    from llm_filter import filter_and_enrich
    filtered, llm_used = await filter_and_enrich(pool, items)

    # Step 3: 批量写入（含 embedding）
    inserted = await bulk_insert(pool, filtered)

    return {
        "fetched": inserted,
        "llm_filtered": llm_used,
        "per_source": per_source,
    }
```

#### `bulk_insert` 变更

需支持 embedding 列写入：

```python
async def bulk_insert(pool: asyncpg.Pool, items: list[dict]) -> int:
    if not items:
        return 0

    rows = [
        (
            item["source"],
            item["title"],
            item["url"],
            item.get("content", ""),
            item.get("author", ""),
            item["published_at"],
            item["batch_id"],
            item.get("metadata", {}),
            item.get("embedding"),  # 新增：embedding 向量
        )
        for item in items
    ]

    # 格式化 embedding 为 pgvector 字符串（NULL 保持 None）
    formatted_rows = []
    for row in rows:
        *rest, embedding = row
        if embedding is not None:
            embedding_str = f"[{','.join(str(x) for x in embedding)}]"
        else:
            embedding_str = None
        formatted_rows.append(tuple(rest) + (embedding_str,))

    async with pool.acquire() as conn:
        result = await conn.executemany(
            """
            INSERT INTO raw_items (source, title, url, content, author, published_at, batch_id, metadata, embedding)
            SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9::vector
            WHERE NOT EXISTS (
                SELECT 1 FROM raw_items WHERE url = $3 AND batch_id = $7
            )
            """,
            formatted_rows,
        )
    inserted = sum(1 for part in result.split("INSERT") if "0 1" in part)
    return inserted
```

#### 调试检测点

| # | 检测点 | 验证方法 |
|---|--------|----------|
| D1 | `run_pipeline` 空抓取返回 0 | Mock 所有 scraper 返回空 |
| D2 | `run_pipeline` LLM 筛选被调用 | Mock `filter_and_enrich`，验证调用参数 |
| D3 | `run_pipeline` llm_filtered 标志 | 验证返回 dict 含 `llm_filtered` key |
| D4 | `bulk_insert` 含 embedding | 传入带 embedding 的 items，验证 SQL 参数 |
| D5 | `bulk_insert` 无 embedding | 传入无 embedding 的 items，验证 embedding 为 None |
| D6 | `dedup_by_url` 跨源去重 | 同 URL 不同 source，只保留一条 |

#### 测试方案（`test_orchestrator.py` 更新）

| 测试用例 | 输入 | 预期结果 |
|----------|------|----------|
| `test_run_pipeline_empty` | 无 scraper 结果 | `{"fetched": 0, "llm_filtered": False}` |
| `test_run_pipeline_with_llm` | Mock scraper + Mock LLM | `{"fetched": N, "llm_filtered": True}` |
| `test_bulk_insert_with_embedding` | items 含 embedding | SQL 含 embedding 参数 |
| `test_bulk_insert_without_embedding` | items 无 embedding | embedding 传 None |
| 现有 6 个 dedup 测试 | 不变 | 通过 |

---

### 文件 4：`module-a/scrapers/__init__.py`（修改）

**变更原因**：恢复 `_insert_items` 和 `SCRAPERS` 注册表（集成测试依赖）

#### 完整新代码

```python
"""Module A scrapers — one module per data source."""

import json
import logging
from datetime import datetime, timezone

import asyncpg

logger = logging.getLogger(__name__)


async def _insert_items(
    pool: asyncpg.Pool,
    source: str,
    items: list[dict],
    batch_id,
) -> int:
    """Insert items into raw_items, skipping duplicates on url.

    Returns the count of newly inserted rows.
    """
    if not items:
        return 0

    now = datetime.now(timezone.utc)
    count = 0

    async with pool.acquire() as conn:
        async with conn.transaction():
            for item in items:
                try:
                    result = await conn.fetchval(
                        """
                        INSERT INTO raw_items
                            (source, title, url, content, author,
                             published_at, fetched_at, metadata, batch_id)
                        VALUES
                            ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
                        ON CONFLICT (url) DO NOTHING
                        RETURNING id
                        """,
                        source,
                        item["title"],
                        item["url"],
                        item.get("content", ""),
                        item.get("author", ""),
                        item["published_at"],
                        now,
                        json.dumps(item.get("metadata", {})),
                        batch_id,
                    )
                    if result is not None:
                        count += 1
                except Exception:
                    logger.debug("Skipping malformed item", exc_info=True)

    return count


from .github import fetch as github_fetch
from .hackernews import fetch as hackernews_fetch
from .rss import fetch as rss_fetch
from .reddit import fetch as reddit_fetch

SCRAPERS = {
    "github": github_fetch,
    "hackernews": hackernews_fetch,
    "rss": rss_fetch,
    "reddit": reddit_fetch,
}
```

#### 调试检测点

| # | 检测点 | 验证方法 |
|---|--------|----------|
| D1 | `_insert_items` 空列表返回 0 | 传空列表，断言返回 0 |
| D2 | `_insert_items` 正常插入返回计数 | Mock conn.fetchval 返回 UUID，断言返回 1 |
| D3 | `_insert_items` 重复 URL 返回 0 | Mock conn.fetchval 返回 None（ON CONFLICT） |
| D4 | `SCRAPERS` 包含 4 个源 | 断言 len(SCRAPERS) == 4 |
| D5 | `SCRAPERS` 每个值可调用 | 遍历断言 callable |

---

### 文件 5：`module-a/scrapers/github.py`（微调）

**变更**：per_page 已为 30（满足 Phase 2 要求），需添加 `fetch` 包装函数

#### 新增函数

```python
async def fetch(pool, since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """标准 scraper 接口（集成测试需要）"""
    return await fetch_github(since, batch_id)
```

#### 调试检测点

| # | 检测点 | 验证方法 |
|---|--------|----------|
| D1 | `fetch` 函数存在且可调用 | `callable(fetch)` |
| D2 | `fetch` 返回 list | Mock httpx，断言返回类型 |
| D3 | `fetch` 异常返回空列表 | Mock httpx 抛异常，断言返回 `[]` |

---

### 文件 6：`module-a/scrapers/hackernews.py`（修改）

**变更**：检查量 100→300 + 添加 `fetch` 包装函数

#### 变更点

```python
# 原来
ids = await get_top_stories(100)
# 改为
ids = await get_top_stories(300)
```

#### 新增函数

```python
async def fetch(pool, since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """标准 scraper 接口"""
    return await fetch_hackernews(since, batch_id)
```

#### 调试检测点

| # | 检测点 | 验证方法 |
|---|--------|----------|
| D1 | `get_top_stories` limit 参数 | Mock httpx，验证请求 URL |
| D2 | `fetch` 包装正确 | 断言 `fetch` 调用 `fetch_hackernews` |
| D3 | 并发限流 Semaphore=20 | 验证并发不超过 20 |

---

### 文件 7：`module-a/scrapers/rss.py`（微调）

**变更**：可选加更多 RSS 源 + 添加 `fetch` 包装函数

#### 可选新增 RSS 源

```python
RSS_SOURCES = [
    # 现有 5 个
    {"name": "arxiv",          "url": "https://arxiv.org/rss/cs.AI"},
    {"name": "jiqizhixin",     "url": "https://www.jiqizhixin.com/rss"},
    {"name": "qbitai",         "url": "https://www.qbitai.com/feed"},
    {"name": "huggingface",    "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "techcrunch_ai",  "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    # 可选新增
    {"name": "arxiv_cl",       "url": "https://arxiv.org/rss/cs.CL"},   # NLP/语言模型
    {"name": "arxiv_lg",       "url": "https://arxiv.org/rss/cs.LG"},   # 机器学习
]
```

#### 新增函数

```python
async def fetch(pool, since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """标准 scraper 接口"""
    return await fetch_rss(since, batch_id)
```

#### 调试检测点

| # | 检测点 | 验证方法 |
|---|--------|----------|
| D1 | RSS 源列表非空 | `len(RSS_SOURCES) >= 5` |
| D2 | 每个源有 name + url | 遍历断言 key 存在 |
| D3 | `fetch` 包装正确 | 断言调用 `fetch_rss` |

---

### 文件 8：`module-a/scrapers/reddit.py`（微调）

**变更**：添加 `fetch` 包装函数（可选模块，不改也行）

#### 新增函数

```python
async def fetch(pool, since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """标准 scraper 接口"""
    return await fetch_reddit(since, batch_id)
```

#### 调试检测点

| # | 检测点 | 验证方法 |
|---|--------|----------|
| D1 | `fetch` 函数存在 | `callable(fetch)` |
| D2 | User-Agent 头设置 | Mock httpx，验证 headers |

---

### 文件 9：`module-a/requirements.txt`（修改）

**变更**：加 `openai` 依赖（DeepSeek SDK）

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
asyncpg==0.30.0
httpx==0.28.1
pydantic==2.10.4
feedparser==6.0.11
openai>=1.12.0
```

---

### 文件 10：`module-a/test_llm_filter.py`（新增）

**功能**：LLM 筛选模块的 TDD 测试

#### 测试用例

| 测试函数 | 说明 |
|----------|------|
| `test_has_api_key_false` | 无 key → False |
| `test_has_api_key_true` | 有 key → True |
| `test_extract_json_fenced` | ```json 包裹 → 提取纯 JSON |
| `test_extract_json_plain` | 纯 JSON → 不变 |
| `test_extract_json_nested` | 嵌套 JSON → 正确提取 |
| `test_mock_score_high_signal` | DeepSeek + 开源 → score >= 7 |
| `test_mock_score_low_signal` | hiking trails → score <= 5 |
| `test_mock_score_medium` | 一般技术讨论 → 5 <= score <= 7 |
| `test_build_prompt_contains_items` | prompt 包含条目标题 |
| `test_build_prompt_contains_rag` | prompt 包含 RAG 上下文 |
| `test_build_prompt_contains_criteria` | prompt 包含评分标准 |
| `test_filter_enrich_fallback` | 无 API Key → (items, False) |
| `test_filter_enrich_with_llm` | Mock LLM → (filtered_items, True) |
| `test_filter_enrich_threshold` | threshold 过滤低分 |
| `test_filter_enrich_embedding` | 通过条目有 embedding |

---

## 三、总文件目录

```
module-a/
├── main.py                    # [修改] FastAPI 入口 + LLM 筛选集成
├── db.py                      # [不变] asyncpg 连接池
├── orchestrator.py            # [修改] 完整流程：抓取→去重→LLM→embedding→写入
├── llm_filter.py              # [新增] LLM 相关性判断 + RAG + embedding
├── requirements.txt           # [修改] 加 openai 依赖
├── scrapers/
│   ├── __init__.py            # [修改] 恢复 _insert_items + SCRAPERS 注册表
│   ├── filters.py             # [不变] 关键词过滤器（粗筛用）
│   ├── github.py              # [微调] 加 fetch 包装
│   ├── hackernews.py          # [修改] 检查量 100→300 + fetch 包装
│   ├── rss.py                 # [微调] 可选加源 + fetch 包装
│   └── reddit.py              # [微调] fetch 包装
├── test_llm_filter.py         # [新增] LLM 筛选测试
├── test_filters.py            # [不变] 关键词过滤测试
├── test_github.py             # [不变] GitHub scraper 测试
├── test_hackernews.py         # [不变] HN scraper 测试
├── test_rss.py                # [不变] RSS scraper 测试
├── test_reddit.py             # [不变] Reddit scraper 测试
└── test_orchestrator.py       # [修改] 加 LLM 流程测试
```

---

## 四、开发顺序

```
Phase 2-A 开发流程（严格 TDD）

Step 1: scrapers/__init__.py
  └─ 恢复 _insert_items + SCRAPERS（让集成测试能跑通）

Step 2: 各 scraper 加 fetch 包装函数
  └─ github.py / hackernews.py / rss.py / reddit.py

Step 3: llm_filter.py（核心新文件）
  ├─ RED: 写 test_llm_filter.py 全部测试
  ├─ GREEN: 实现 llm_filter.py
  └─ REFACTOR: 清理

Step 4: orchestrator.py
  ├─ RED: 更新 test_orchestrator.py
  ├─ GREEN: 实现 run_pipeline + 更新 bulk_insert
  └─ REFACTOR: 清理

Step 5: main.py
  └─ 恢复 _get_pool_or_503 + _fetch_source，更新 /run

Step 6: requirements.txt
  └─ 加 openai

Step 7: 全量测试验证
  └─ pytest test_*.py tests/test_module_a.py -v

Step 8: 集成测试（需 PostgreSQL + pgvector）
  └─ 启动 DB → 导入 schema_v2 → 运行 /run 端点
```

---

## 五、设计优化

### 优化 1（高价值）：embedding 缓存复用，避免重复生成

**问题**：`_get_rag_context` 为前 3 个候选条目生成 embedding 做 RAG 检索，之后 `filter_and_enrich` 又为所有通过筛选的条目再次生成 embedding。前 3 条的 embedding 被算了两遍。

**方案**：`_get_rag_context` 返回时附带已生成的 embedding map，`filter_and_enrich` 复用。

```python
# 改前
rag_context = await _get_rag_context(pool, items)       # 生成 3 个 embedding
embeddings = await generate_embeddings_batch(texts)      # 又生成 N 个（含重复的 3 个）

# 改后
rag_context, cached_embs = await _get_rag_context(pool, items)  # 返回 (str, dict)
# cached_embs = {url: [0.1, 0.2, ...], ...}

# 复用 cached_embs，只为新条目生成 embedding
texts_to_embed, indices_to_embed = [], []
for i, it in enumerate(passed):
    if it["url"] in cached_embs:
        it["embedding"] = cached_embs[it["url"]]
    else:
        texts_to_embed.append(f"{it['title']} {it.get('content','')[:200]}")
        indices_to_embed.append(i)
if texts_to_embed:
    new_embs = await generate_embeddings_batch(texts_to_embed)
    for i, emb in zip(indices_to_embed, new_embs):
        passed[i]["embedding"] = emb
```

**`_get_rag_context` 改动**：

```python
async def _get_rag_context(pool, items, top_k=5) -> tuple[str, dict]:
    """返回 (RAG上下文文本, {url: embedding} 缓存)"""
    sample_texts = [f"{it['title']} {it.get('content','')[:200]}" for it in items[:3]]
    sample_embs = await generate_embeddings_batch(sample_texts)

    # 构建缓存 map
    cached_embs = {}
    if sample_embs:
        for it, emb in zip(items[:3], sample_embs):
            if emb:
                cached_embs[it.get("url", "")] = emb

    # RAG 检索（同原逻辑）
    all_similar = []
    for emb in (sample_embs or []):
        if emb:
            similar = await search_similar_items(pool, emb, top_k=top_k)
            all_similar.extend(similar)

    # 去重 + 格式化
    seen_ids = set()
    context_lines = []
    for s in all_similar:
        if s["id"] not in seen_ids:
            seen_ids.add(s["id"])
            tags = ", ".join(s.get("tags", []))
            context_lines.append(f"- [{s['source']}] {s['title']} (相似度:{s['similarity']}, 标签:{tags})")

    return "\n".join(context_lines) if context_lines else "", cached_embs
```

**收益**：每次 `/run` 调用省 3 次 embedding API 请求，降低延迟和成本。

---

### 优化 2（高价值）：关键词粗筛 + LLM 精筛两阶段

**问题**：当前设计完全用 LLM 替代关键词过滤。一次 `/run` 可能抓到 100+ 条候选，全部送 LLM 成本高、延迟大。

**方案**：保留关键词过滤作为免费粗筛，LLM 只处理通过粗筛的条目。

```
外部API → httpx GET → 关键词粗筛(免费，削减60-70%) → LLM精筛(付费) → embedding → 写入
```

**实现**：各 scraper 保持现有 `filter_items_by_title` 逻辑不变，`llm_filter.py` 在关键词过滤之后再做 LLM 精筛。Phase 1 的关键词过滤器 `scrapers/filters.py` 继续保留使用。

**收益**：
- LLM 调用量从 100+ 条降到 30-50 条，API 成本降低 60%+
- 关键词是超集（宁可多放不可漏），不会遗漏真正相关的资讯
- 粗筛免费，零额外开销

**影响范围**：无代码变更——各 scraper 本来就有关键词过滤，只是在架构图中明确标注"两阶段"语义。

---

### 优化 3（中价值）：`_extract_json` 和 `_mock_score_one` 提取到 shared

**问题**：`module-a/llm_filter.py` 和 `module-b/ai/pipeline.py` 的 `_extract_json` 逻辑完全相同（处理 ```json 包裹、嵌套 JSON 提取），`_mock_score_one` 也高度相似。Phase 2 两个模块都在改，重复维护风险高。

**方案**：提取到 `shared/utils.py`。

```python
# shared/utils.py（新增）
def extract_json(text: str) -> str:
    """从 LLM 响应提取纯 JSON（处理 ```json 包裹、嵌套、前导文本）"""
    # 复用 module-b/ai/pipeline.py:57-99 的实现

def mock_ai_score(item: dict) -> float:
    """无 API Key 时的启发式评分（关键词+实体+来源加权）"""
    # 复用 module-b/ai/pipeline.py:294-317 的实现
```

**改动**：
- `module-a/llm_filter.py`：`from shared.utils import extract_json, mock_ai_score`
- `module-b/ai/pipeline.py`：同上（可选，不强制）

**收益**：消除跨模块代码重复，统一维护。

---

### 优化 4（中价值）：`_insert_items` 移到测试 fixtures

**问题**：`scrapers/__init__.py` 中的 `_insert_items` 在生产中完全不用（`orchestrator.bulk_insert` 才是生产路径），只服务集成测试 `tests/test_module_a.py`。放在生产代码里增加维护负担和导入复杂度。

**方案**：移到 `tests/conftest.py` 作为 fixture，`scrapers/__init__.py` 只保留 `SCRAPERS` 注册表。

```python
# tests/conftest.py（新增 _insert_items fixture）
@pytest.fixture
def insert_items():
    """集成测试用的 _insert_items（从 scrapers/__init__.py 移入）"""
    async def _insert(pool, source, items, batch_id):
        # 同原实现
        ...
    return _insert
```

**改动**：
- `scrapers/__init__.py`：删除 `_insert_items`，只保留 `SCRAPERS`
- `tests/test_module_a.py`：`from conftest import insert_items` 替代 `from scrapers import _insert_items`

**收益**：生产代码更干净，测试代码更内聚。

---

### 优化 5（低价值）：`bulk_insert` 改用 `ON CONFLICT`

**问题**：当前 `bulk_insert` 用 `INSERT ... SELECT ... WHERE NOT EXISTS` 模式，在 `executemany` 下行为不如 `ON CONFLICT` 直观。Phase 1 用这个模式是因为不确定 URL 唯一索引是否存在，但 `schema.sql` 已有 `CREATE UNIQUE INDEX idx_raw_items_url ON raw_items(url)`。

**方案**：改用更标准的 `ON CONFLICT DO NOTHING`。

```sql
-- 改前
INSERT INTO raw_items (...)
SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9::vector
WHERE NOT EXISTS (SELECT 1 FROM raw_items WHERE url = $3 AND batch_id = $7)

-- 改后
INSERT INTO raw_items (...) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector)
ON CONFLICT (url) DO NOTHING
```

**收益**：更简洁，利用唯一索引性能更好，与 `_insert_items` 的 `ON CONFLICT (url) DO NOTHING` 模式统一。

**注意**：`ON CONFLICT` 去掉了 `AND batch_id = $7` 条件，即同一 URL 即使不同 batch 也只保留第一条。这是正确语义——同 URL 的资讯不需要重复存储。

---

### 优化汇总

| # | 优化 | 价值 | 工作量 | 是否阻塞 |
|---|------|------|--------|----------|
| 1 | embedding 缓存复用 | 高 | 小 | 否 |
| 2 | 关键词粗筛 + LLM 精筛 | 高 | 无（已内置） | 否 |
| 3 | shared/utils.py 提取 | 中 | 小 | 否 |
| 4 | _insert_items 移到 conftest | 中 | 小 | 否 |
| 5 | bulk_insert ON CONFLICT | 低 | 极小 | 否 |

> 全部优化可在开发过程中逐步落地，不阻塞主流程。建议按优先级 2→1→3→4→5 顺序实施。

---

## 六、验收标准

```bash
# 1. 单元测试全通过
cd module-a && python -m pytest test_*.py -v
# 预期：全部 PASS（新增 ~15 个 + 原有 34 个）

# 2. 集成测试通过
cd .. && python -m pytest tests/test_module_a.py -v
# 预期：全部 PASS

# 3. 端点验证
curl -X POST http://localhost:8001/run \
  -H "Content-Type: application/json" \
  -d '{"batch_id": "550e8400-e29b-41d4-a716-446655440000", "hours_back": 24}'
# 预期：{"status": "ok", "fetched": 25, "llm_filtered": true, ...}

# 4. 数据库验证
psql -c "SELECT count(*), avg((metadata->>'ai_score')::numeric) FROM raw_items WHERE batch_id = '550e8400-...';"
# 预期：count > 0, avg 非空

psql -c "SELECT count(*) FROM raw_items WHERE embedding IS NOT NULL;"
# 预期：count > 0
```
