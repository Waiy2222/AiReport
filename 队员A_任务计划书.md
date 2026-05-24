# 队员 A 专属任务计划书 — 资讯抓取模块

> 模块端口：`8001` | 数据库表：`raw_items` | 分支名：`module-a`

---

## 一、代码文件清单

---

### 文件 1：`module-a/scrapers/__init__.py`

**操作**：新建

**功能函数**：无（空文件，标记 scrapers 为 Python 包）

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-包导入 | `python -c "from scrapers import github"` | 不报 ImportError |

**测试方案**：

```bash
cd module-a
python -c "import scrapers; print('ok')"
```

**预期测试结果**：输出 `ok`，无报错。

---

### 文件 2：`module-a/scrapers/filters.py`

**操作**：新建

**说明**：统一的关键词过滤器，所有 scraper 共用，避免代码重复。

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `AI_KEYWORDS` | — | `list[str]` | 模块级常量：AI 领域关键词列表 |
| `filter_ai_keywords(text)` | `text: str` | `bool` | 检查文本是否匹配任一 AI 关键词（大小写不敏感） |
| `filter_items_by_title(items, field)` | `items: list[dict], field: str = "title"` | `list[dict]` | 批量过滤，保留 `item[field]` 含关键词的条目 |

**AI_KEYWORDS 内容**：
```python
AI_KEYWORDS = [
    "ai", "llm", "gpt", "claude", "gemini", "deepseek", "llama", "agent",
    "智能体", "大模型", "语言模型", "推理模型", "rag", "vector",
    "embedding", "transformer", "prompt", "fine-tuning", "rlhf",
    "open source", "开源", "nlp", "multimodal", "多模态", "diffusion",
    "stable diffusion", "mcp", "tool calling", "function calling",
    "langchain", "crewai", "autogpt", "vllm", "ollama", "chromadb",
    "huggingface", "pytorch", "tensorflow", "jax",
]
```

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-关键词匹配正确 | `filter_ai_keywords("DeepSeek-V4 released")` | `True` |
| D2-无关内容过滤 | `filter_ai_keywords("I built a toaster")` | `False` |
| D3-大小写不敏感 | `filter_ai_keywords("DEEPSEEK")` + `filter_ai_keywords("deepseek")` | 两者都 `True` |
| D4-中文匹配 | `filter_ai_keywords("开源大模型发布")` | `True` |
| D5-批量过滤 | 输入 10 条混合数据 | 正确分成 AI/非AI 两组 |

**测试方案**：

```bash
cd module-a
python -c "
from scrapers.filters import filter_ai_keywords, AI_KEYWORDS
print(f'Keywords count: {len(AI_KEYWORDS)}')

# D1-D4
tests = [
    ('DeepSeek-V4 released', True),
    ('I built a smart toaster', False),
    ('deepseek is great', True),
    ('开源大模型发布', True),
    ('My cat is cute', False),
    ('New MCP protocol announced', True),
    ('RAG pipeline optimization', True),
]
for text, expected in tests:
    result = filter_ai_keywords(text)
    status = 'PASS' if result == expected else 'FAIL'
    print(f'[{status}] \"{text[:40]}...\" → {result} (expected {expected})')
"
```

**预期测试结果**：全部 7 条 PASS。

---

### 文件 3：`module-a/scrapers/github.py`

**操作**：新建

**数据源**：`https://api.github.com/search/repositories`（公开，无 Token 限速 60 次/小时）

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `build_query(since)` | `since: datetime` | `str` | 构造搜索 query：`AI+Agent+LLM+created:>YYYY-MM-DD`，按 stars 降序 |
| `search_repos(since)` | `since: datetime` | `list[dict]` | 调 GitHub Search API，返回原始 items 列表 |
| `to_raw_items(items, batch_id)` | `items: list[dict], batch_id: uuid.UUID` | `list[dict]` | 将 GitHub repo 映射为 raw_items 行 dict，调用 `filters.filter_items_by_title` |
| `fetch_github(since, batch_id)` | `since: datetime, batch_id: uuid.UUID` | `list[dict]` | **主函数**：串联上述步骤，返回可入库的 dict 列表 |

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-Search API 可达 | `curl https://api.github.com/search/repositories?q=AI+Agent&sort=stars&per_page=5` | 返回 JSON，`items` 数组非空 |
| D2-关键词过滤正确 | 传入含非 AI 仓库的数据，检查返回值 | 非 AI 仓库被剔除，只保留匹配关键词的 |
| D3-字段映射完整 | 检查返回 dict 的 key | 必须包含 `source, title, url, content, author, published_at, batch_id, metadata` |
| D4-空结果处理 | 传入空 items 列表 | 返回空列表 `[]`，不抛异常 |
| D5-API 限速处理 | 连续调用 65 次（超过未认证限速） | 返回空列表 + 打 warning 日志，不崩溃 |
| D6-metadata JSON | 检查 metadata 字段 | 必须包含 `stars, forks, language, topics` 且为合法 JSON 兼容 dict |

**测试方案**：

```bash
# 单元测试：直接调函数
cd module-a
python -c "
import asyncio
from datetime import datetime, timezone, timedelta
from scrapers.github import fetch_github

async def test():
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    items = await fetch_github(since, 'a0000000-0000-0000-0000-000000000099')
    print(f'Fetched: {len(items)}')
    for item in items[:3]:
        print(f'  [{item[\"source\"]}] {item[\"title\"][:60]}... (stars={item[\"metadata\"].get(\"stars\")})')

asyncio.run(test())
"
```

**预期测试结果**：
- 输出 `Fetched: N`（N > 0）
- 每条显示 `[github]` 前缀
- 标题含 AI/Agent/LLM 相关词汇
- metadata 中有 stars 字段

---

### 文件 3：`module-a/scrapers/hackernews.py`

**操作**：新建

**数据源**：`https://hacker-news.firebaseio.com/v0/`（公开，无需认证）

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_top_stories(limit)` | `limit: int = 100` | `list[int]` | 获取前 N 条热门 story ID |
| `get_item(item_id)` | `item_id: int` | `dict` | 获取单条 story 详情 |
| `fetch_items_concurrent(item_ids, concurrency)` | `item_ids: list[int], concurrency: int = 20` | `list[dict]` | 并发获取详情，`asyncio.Semaphore` 限流 |
| `to_raw_items(items, batch_id)` | `items: list[dict], batch_id: uuid.UUID` | `list[dict]` | 将 HN item 映射为 raw_items 行 dict，调用 `filters.filter_items_by_title` |
| `fetch_hackernews(since, batch_id)` | `since: datetime, batch_id: uuid.UUID` | `list[dict]` | **主函数** |

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-topstories API 可达 | `curl https://hacker-news.firebaseio.com/v0/topstories.json` | 返回 JSON 数组，长度 ≥ 100 |
| D2-单条获取正确 | 取第一个 ID 调 `/item/{id}.json` | 返回含 `title, url, by, time, score` 字段的 dict |
| D3-并发获取性能 | 记录 100 条并发获取耗时 | ≤ 5 秒（20 并发） |
| D4-关键词过滤精确 | 准备含 "Show HN: I built a toaster" 的假数据 | 该条被过滤掉（不含 AI 关键词） |
| D5-HN 时间戳转换 | 检查 `published_at` 字段 | Unix timestamp 正确转为 ISO 8601 UTC |
| D6-空 topstories | API 异常时返回空列表 | 不抛异常，返回 `[]` |
| D7-score 字段 | 检查 metadata | `metadata.score` 等于 HN 的 score 字段 |

**测试方案**：

```bash
cd module-a
python -c "
import asyncio
from datetime import datetime, timezone, timedelta
from scrapers.hackernews import fetch_hackernews

async def test():
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    items = await fetch_hackernews(since, 'a0000000-0000-0000-0000-000000000099')
    print(f'HN fetched: {len(items)}')
    for item in items[:5]:
        print(f'  [{item[\"source\"]}] {item[\"title\"][:60]}...')
    # 验证时间过滤
    old = [i for i in items if i['published_at'] < since]
    print(f'Before since (should be 0): {len(old)}')

asyncio.run(test())
"
```

**预期测试结果**：
- `HN fetched: N`（N ≥ 5，HN 首页通常有 5+ AI 相关）
- 所有条目的 `published_at` ≥ `since`
- `Before since` 输出 0

---

### 文件 4：`module-a/scrapers/rss.py`

**操作**：新建

**数据源**：

| 编号 | 源名 | RSS URL |
|------|------|---------|
| 0 | ArXiv AI | `https://arxiv.org/rss/cs.AI` |
| 1 | 机器之心 | `https://www.jiqizhixin.com/rss` |
| 2 | 量子位 | `https://www.qbitai.com/feed` |
| 3 | HuggingFace Blog | `https://huggingface.co/blog/feed.xml` |
| 4 | TechCrunch AI | `https://techcrunch.com/category/artificial-intelligence/feed/` |

**依赖**：`feedparser`（需添加到 `requirements.txt`）

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `RSS_SOURCES` | — | `list[dict]` | 模块级常量：RSS 源列表 `[{name, url}]` |
| `fetch_single_rss(source)` | `source: dict` | `list[dict]` | 抓取单个 RSS 源，解析条目，失败返回空列表 |
| `to_raw_items(entries, source_name, batch_id)` | `entries: list, source_name: str, batch_id: uuid.UUID` | `list[dict]` | RSS entry → raw_items dict，调用 `filters.filter_items_by_title` |
| `fetch_rss(since, batch_id)` | `since: datetime, batch_id: uuid.UUID` | `list[dict]` | **主函数**：`asyncio.gather` 并发抓取所有源 |

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-每个 RSS 源可达 | 逐个 curl 上述 5 个 URL | 返回 XML，HTTP 200 |
| D2-feedparser 解析 | `feedparser.parse(url)` 后检查 `len(entries)` | entries 非空 |
| D3-并发隔离 | 修改 `RSS_SOURCES` 加入一个无效 URL | 有效源正常返回，无效源被跳过，总数不变 |
| D4-时间过滤 | 准备一条 `published` 早于 `since` 的条目 | 该条目不出现在返回值中 |
| D5-HTTP 超时处理 | 对一个慢速源设 10s 超时 | 超时后返回空列表，不阻塞其他源 |
| D6-空 RSS 源 | 模拟返回 0 条内容 | 正常返回 `[]` |
| D7-字符编码 | 检查中文 RSS（机器之心/量子位）的 title | 中文无乱码 |

**测试方案**：

```bash
cd module-a
# 先确认 feedparser 已安装
pip install feedparser

python -c "
import asyncio
from datetime import datetime, timezone, timedelta
from scrapers.rss import fetch_rss, RSS_SOURCES

async def test():
    print(f'RSS sources: {len(RSS_SOURCES)}')
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    items = await fetch_rss(since, 'a0000000-0000-0000-0000-000000000099')
    print(f'RSS fetched: {len(items)}')
    # 按源统计
    from collections import Counter
    c = Counter(i['source'] for i in items)
    for src, cnt in c.items():
        print(f'  {src}: {cnt}')

asyncio.run(test())
"
```

**预期测试结果**：
- RSS 源数：5
- 每个源返回 ≥ 0 条
- ArXiv AI 通常有 10-30 条
- 若某源连接失败，输出 warning 日志，不中断

---

### 文件 5：`module-a/scrapers/reddit.py`

**操作**：新建（可选 P1）

**数据源**：Reddit JSON API `https://www.reddit.com/r/{subreddit}/new.json`

**子版块**：`MachineLearning`, `artificial`, `LocalLLaMA`, `OpenSource`

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `SUBREDDITS` | — | `list[str]` | 模块常量 |
| `fetch_subreddit(name, since)` | `name: str, since: datetime` | `list[dict]` | 抓取单个子版块新帖 |
| `to_raw_items(posts, batch_id)` | `posts: list[dict], batch_id: uuid.UUID` | `list[dict]` | Reddit post → raw_items dict，调用 `filters.filter_items_by_title` |
| `fetch_reddit(since, batch_id)` | `since: datetime, batch_id: uuid.UUID` | `list[dict]` | **主函数** |

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-API 可达 | `curl -H "User-Agent: AiReport/1.0" https://www.reddit.com/r/MachineLearning/new.json` | 返回 JSON |
| D2-User-Agent 头 | 不加 UA 头发请求 | 返回 429 或空 |
| D3-关键词过滤 | 检查返回数据 | 不含 "toaster"/"bicycle" 等无关帖 |
| D4-ups 字段 | 检查 metadata | `metadata.ups` 有值 |
| D5-限速处理 | 快速连续请求 | 不崩溃，返回空列表 |

**测试方案**：

```bash
cd module-a
python -c "
import asyncio
from datetime import datetime, timezone, timedelta
from scrapers.reddit import fetch_reddit

async def test():
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    items = await fetch_reddit(since, 'a0000000-0000-0000-0000-000000000099')
    print(f'Reddit fetched: {len(items)}')
    for item in items[:3]:
        print(f'  [{item[\"source\"]}] {item[\"title\"][:60]}... (ups={item[\"metadata\"].get(\"ups\")})')

asyncio.run(test())
"
```

**预期测试结果**：成功返回 AI 相关帖子列表；若被限速则返回空列表不崩溃。

---

### 文件 6：`module-a/orchestrator.py`

**操作**：新建

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `SCRAPER_TIMEOUT` | — | `int` | 模块常量：单个 scraper 超时秒数（默认 60） |
| `run_all_scrapers(since, batch_id, enabled_sources)` | `since: datetime, batch_id: uuid.UUID, enabled_sources: list[str]` | `tuple[list[dict], dict]` | 并发执行所有 scraper（`asyncio.wait_for` 超时保护），返回 `(全部 items, 各源统计)` |
| `dedup_by_url(items)` | `items: list[dict]` | `list[dict]` | 按 URL 去重，保留先出现的（跨源去重） |
| `bulk_insert(pool, items)` | `pool: asyncpg.Pool, items: list[dict]` | `int` | 批量 INSERT 到 raw_items（`INSERT ... WHERE NOT EXISTS` 防重复） |

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-并发执行 | 3 个 scraper 同时跑 | 总耗时 ≈ 最慢那个的耗时，非三者之和 |
| D2-单源失败隔离 | 模拟 github 抛异常 | hackernews + rss 正常返回，github 统计为 0 |
| D3-URL 去重（同源） | 构造 3 条同 URL 的数据 | 返回去重后只有 1 条 |
| D4-URL 去重（跨源） | GitHub 和 HN 包含同一 URL | 保留先出现的，后出现的被去重 |
| D5-批量插入 | INSERT 30 条 | 30 条全部入库，耗时 < 100ms |
| D6-重复插入幂等 | 对同一批数据调两次 `bulk_insert` | 第二次 INSERT 0 行（`WHERE NOT EXISTS` 生效） |
| D7-空结果处理 | 所有 scraper 返回空列表 | 返回 `([], {})`，insert 0 行 |
| D8-统计字典正确 | 检查返回的 stats dict | key 为 source 名，value 为整数 |
| D9-单源超时 | `asyncio.wait_for` 设 2s，源耗时 5s | 该源返回空列表，不阻塞其他源 |

**测试方案**：

```bash
cd module-a
python -c "
import asyncio
from datetime import datetime, timezone, timedelta
from orchestrator import run_all_scrapers

async def test():
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    items, stats = await run_all_scrapers(
        since,
        'a0000000-0000-0000-0000-000000000099',
        ['github', 'hackernews', 'rss']
    )
    print(f'Total items: {len(items)}')
    print(f'Stats: {stats}')
    # 验证去重
    urls = [i['url'] for i in items]
    print(f'Unique URLs: {len(set(urls))} / {len(urls)}')

asyncio.run(test())
"
```

**预期测试结果**：
- `Total items` > 0
- `Stats` 各 key 的 value 之和 = `Total items`
- Unique URLs = Total items（无重复 URL）

---

### 文件 7：`module-a/main.py`（修改）

**操作**：修改现有骨架

**现有内容（不动）**：
- `/health` 端点 — 第 34-42 行
- `startup/shutdown` 事件 — 第 16-25 行
- `FetchRequest` 模型 — 第 29-31 行

**需要修改的部分**：

| 行号 | 当前内容 | 修改为 |
|------|----------|--------|
| 13 | `SOURCES = ["github", "hackernews", "rss"]` | 不变（已完成修复） |
| 46-66 | `/run` 端点逻辑 | 调用 `orchestrator.run_all_scrapers` + 写库 |
| 69-71 | `_fetch_source` 占位函数 | 替换为 `_do_fetch` 真正实现 |

**修改后的函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `health()` | 无 | `dict` | 不动 |
| `run(req)` | `req: FetchRequest` | `dict` | 调用 orchestrator → 写入 DB → 返回统计 |
| `_do_fetch(pool, since, batch_id, sources)` | `pool, since: datetime, batch_id: uuid.UUID, sources: list[str]` | `tuple[int, dict]` | 核心：调 orchestrator + bulk insert |

**FetchRequest 模型优化**：`batch_id` 类型从 `str` 改为 `UUID`（`from pydantic import UUID`），让 Pydantic 在请求层就拦截非法 UUID 输入，返回 422 而非 500。

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-`/health` 正常 | `curl http://localhost:8001/health` | `{"status":"ok","db":"connected"}` |
| D2-`/run` 正常流程 | `curl -X POST ... -d '{"batch_id":"uuid","hours_back":24}'` | 返回 `{"status":"ok","fetched":N,...}` |
| D3-batch_id 校验 | 传入 `"batch_id": "not-a-uuid"` | 返回 HTTP 422（Pydantic 自动校验）或 400 |
| D4-无 DB 时 `/health` | 关掉 PostgreSQL 后访问 `/health` | 返回 `{"status":"ok","db":"disconnected"}` |
| D5-数据库写入验证 | `/run` 后查库 | `SELECT count(*) FROM raw_items WHERE batch_id = '<返回的batch_id>'` 等于 fetched 值 |
| D6-partial 状态 | 只启用 1 个 source，另一个失效 | status 可为 "ok"（只要有结果 > 0 就算 ok） |

**测试方案**：

```bash
# 1. 健康检查
curl -s http://localhost:8001/health | python -m json.tool

# 2. 触发抓取
BATCH_ID="a0000000-0000-0000-0000-000000000099"
curl -s -X POST http://localhost:8001/run \
  -H "Content-Type: application/json" \
  -d "{\"batch_id\": \"$BATCH_ID\", \"hours_back\": 24}" | python -m json.tool

# 3. 验证入库
PGPASSWORD=postgres psql -h localhost -U postgres -d ai_news \
  -c "SELECT source, count(*) FROM raw_items WHERE batch_id = '$BATCH_ID' GROUP BY source;"

# 4. 验证字段完整性
PGPASSWORD=postgres psql -h localhost -U postgres -d ai_news \
  -c "SELECT source, title, url, published_at, metadata IS NOT NULL as has_metadata FROM raw_items WHERE batch_id = '$BATCH_ID' LIMIT 5;"
```

**预期测试结果**：

```json
// /health
{"status": "ok", "db": "connected"}

// /run
{
  "status": "ok",
  "fetched": 35,
  "batch_id": "a0000000-0000-0000-0000-000000000099",
  "per_source": {
    "github": 12,
    "hackernews": 8,
    "rss": 15
  }
}

// SQL 验证
// source   | count
// ----------+-------
// github    |    12
// hackernews|     8
// rss       |    15
// (3 rows)

// 字段完整性：每行 has_metadata 为 true
```

---

### 文件 8：`module-a/requirements.txt`（修改）

**操作**：追加依赖

**新增内容**：
```
feedparser==6.0.11
```

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-全部安装成功 | `pip install -r requirements.txt` | 无报错 |

**测试方案**：
```bash
cd module-a
pip install -r requirements.txt
python -c "import fastapi, asyncpg, httpx, feedparser; print('all ok')"
```

**预期测试结果**：输出 `all ok`。

---

## 二、总文件目录

```
project/
│
├── contracts/                          # [组长维护，队员只读]
│   ├── schema.sql                      # 数据库建表 DDL
│   ├── seed_data.sql                   # 假数据（已修复 batch_id UUID）
│   └── api-spec.yaml                   # 接口契约
│
├── module-a/                           # ★ 队员 A 工作区
│   ├── main.py                         # [修改] FastAPI 入口：/health + /run
│   ├── db.py                           # [不动] PostgreSQL 连接池
│   ├── requirements.txt                # [修改] 增加 feedparser 依赖
│   ├── Dockerfile                      # [不动] 容器化
│   │
│   ├── orchestrator.py                 # [新建] 并发调度 + 去重 + 批量写库
│   │
│   └── scrapers/                       # [新建目录]
│       ├── __init__.py                 # [新建] 空文件
│       ├── filters.py                  # [新建] 共享关键词过滤器
│       ├── github.py                   # [新建] GitHub Search API
│       ├── hackernews.py               # [新建] Hacker News API
│       ├── rss.py                      # [新建] RSS 多源并发
│       └── reddit.py                   # [新建] Reddit API（可选 P1）
│
├── module-b/                           # [队员 B 负责]
├── module-c/                           # [队员 C 负责]
├── module-d/                           # [队员 D 负责]
├── module-e/                           # [组长负责]
│
├── docker-compose.yml                  # [组长维护] 7 容器编排
├── nginx.conf                          # [组长维护] 网关路由（已修复 /health）
└── .env.example                        # [组长维护] 环境变量模板
```

---

## 三、队员 A 开发顺序建议

```
Step 1: scrapers/__init__.py        (1 分钟)
Step 2: scrapers/filters.py         (30 分钟，所有 scraper 依赖它)
Step 3: scrapers/github.py          (2-3 小时，先通一个源)
Step 4: scrapers/rss.py             (1-2 小时，验证并发模式)
Step 5: scrapers/hackernews.py      (1-2 小时)
Step 6: orchestrator.py             (1-2 小时，串联 + 去重 + 超时 + 写库)
Step 7: 修改 main.py                (30 分钟，接入 orchestrator，改 UUID 类型)
Step 8: scrapers/reddit.py          (可选，1-2 小时)
Step 9: 全链路自测                   (1 小时)
```

每个 Step 完成后立即跑对应文件的**调试检测点**和**测试方案**，确认通过再进入下一步。
