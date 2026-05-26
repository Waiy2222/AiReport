# AI 资讯早报/晚报智能体 · Phase 2 计划书

> 日期：2026-05-26
> 团队：5 人（1 组长 + 4 组员）
> 原则：**组长搞定所有前置，组员拿到即可开工，互不等待**
> 基于：Phase 1 全部模块已完成（5 模块 + 57 测试通过）

---

## 一、Phase 2 要做什么

在 Phase 1 基础上新增以下能力：

1. **个性化推送**：用户选择偏好标签 → 智能体根据标签+行为自动匹配内容
2. **LLM 智能筛选**：Module A 用大模型替代硬编码关键词，动态判断资讯相关性
3. **RAG 记忆机制**：pgvector 存储历史案例，新资讯筛选时检索相似案例做参考
4. **每资讯配图**：简报中每条资讯配一张相关图片
5. **长图生成**：最终简报渲染为可分享的长图
6. **结构优化**：简报排版更清晰，分段更合理
7. **视频生成**：根据用户偏好搜集视频片段 → AI 剪辑 → 语音解说+字幕（统一生成，暂不推送）
8. **主攻微信**：先完成微信公众号全链路，其他平台接口保留

---

## 二、架构（新）

```
                              PostgreSQL (唯一的数据交汇点)
                                       │
  ┌────────┬────────┬────────┬────────┬┴───────┬────────────┐
  │        │        │        │        │        │            │
  ▼        ▼        ▼        ▼        ▼        ▼            ▼
raw_items briefs  publish  subscri  run_log  user_beh  videos
 (A)      (B/D)   _log(D)  ptions(C) (E)    avior(C)    (F)
                                       │
                              pgvector 扩展 (E 部署)
                              └─ embedding 列 (A 写, B/F 读)
```

```
  E 的定时器                           E 的 Dashboard
  (到点发 HTTP 请求)                    (读库展示 + 手动触发)
      │
      ├─→ A(:8001)  抓取资讯 → LLM筛选 → 写 raw_items + embedding
      │                                    │
      ├─→ B(:8002)  读 raw_items + 用户偏好 → AI加工+配图 → 写 briefings
      │                                    │
      ├─→ C(:8003)  读 briefings → 微信推送 + 用户标签管理
      │                                    │
      ├─→ D(:8004)  读 briefings → 微信公众号发布 + 长图生成
      │                                    │
      └─→ F(:8006)  读 briefings + raw_items → 视频生成 → 写 videos
                                           │
                                    PostgreSQL (唯一的数据交汇点)
```

---

## 三、组长前置任务（组长 D1-D2 完成，其他人拿到就能开工）

### 3.1 数据库扩展 (`contracts/schema_v2.sql`)

```sql
-- Phase 1 的 5 张表不变
-- 新增 3 张表 + 扩展现有表

-- 1. raw_items 加 embedding 列（RAG 记忆）
ALTER TABLE raw_items ADD COLUMN embedding vector(1536);

-- 2. subscriptions 加偏好字段
ALTER TABLE subscriptions ADD COLUMN preferences JSONB DEFAULT '{"tags":[]}';
ALTER TABLE subscriptions ADD COLUMN user_openid TEXT UNIQUE;

-- 3. 新增：用户行为表
CREATE TABLE user_behavior (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_openid TEXT NOT NULL,
  briefing_id UUID REFERENCES briefings(id),
  item_index INT,
  item_url TEXT,
  action TEXT,  -- 'click' | 'view' | 'share'
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 4. 新增：视频表
CREATE TABLE videos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type TEXT,  -- 'ai_agent_weekly' etc.
  date DATE,
  title TEXT,
  script TEXT,
  output_path TEXT,
  duration_seconds INT,
  status TEXT DEFAULT 'pending',  -- pending | processing | done | failed
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 5. pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3.2 假数据脚本 (`contracts/seed_data_v2.sql`)

- Phase 1 的假数据全部保留
- 新增 subscriptions 假数据（3 个测试用户，不同标签组合）
- 新增 user_behavior 假数据（模拟一周的点击历史）
- raw_items 补充 embedding 假向量（随机向量）

### 3.3 新项目脚手架

```
project/
├── contracts/
│   ├── schema.sql           # Phase 1（不改）
│   ├── schema_v2.sql        # Phase 2 增量
│   ├── seed_data.sql        # Phase 1（不改）
│   ├── seed_data_v2.sql     # Phase 2 增量
│   └── api-spec.yaml        # 更新接口定义
│
├── shared/
│   ├── db.py                # 已有（不改）
│   └── rag.py               # 新增：embedding 生成 + RAG 检索工具函数
│
├── module-a/                # 组员 A 改
│   ├── scrapers/            # 加 LLM 筛选逻辑
│   └── ...（已有）
│
├── module-b/                # 组员 B 改
│   ├── ai/pipeline.py       # 加配图 + 用户偏好上下文
│   ├── ai/render_longimage.py  # 新增：长图渲染
│   └── ...（已有）
│
├── module-c/                # 组员 C 改
│   ├── backend/
│   │   ├── weixin_oa.py     # 新增：公众号消息回调
│   │   ├── tags.py          # 新增：标签 CRUD API
│   │   └── ...（已有）
│   └── h5/                   # 新增：极简 H5 标签选择页
│       └── preferences.html
│
├── module-d/                # 组员 D 改
│   ├── platforms/weixin.py  # 更新模板（配图+长图）
│   └── longimage.py         # 新增：Playwright 截图
│
├── module-e/                # 组长自己
│   ├── pipeline.py          # 更新调度（加 F 触发）
│   └── dashboard/           # 更新面板
│
├── module-f/                # 新增：视频生成（组长建骨架，组员 D 填逻辑）
│   ├── main.py
│   ├── gemini_client.py     # Gemini API 封装
│   ├── video_search.py      # 素材搜索 + 下载
│   ├── editor.py            # FFmpeg 剪辑拼接
│   ├── tts.py               # Edge TTS 语音合成
│   ├── subtitle.py          # Whisper 字幕
│   └── requirements.txt
│
├── docker-compose.yml       # 更新：加 module-f + pgvector 配置
└── nginx.conf               # 更新：加 :8006 路由
```

**组长 D1 交付后，所有人做的事情完全一样：**

```bash
git pull
docker run -d --name my-pg-v2 -p 5432:5432 \
  -e POSTGRES_PASSWORD=test pgvector/pgvector:pg16
psql -h localhost -U postgres -f contracts/schema.sql
psql -h localhost -U postgres -f contracts/schema_v2.sql
psql -h localhost -U postgres -f contracts/seed_data_v2.sql
cd module-你负责的字母
uvicorn main:app --reload --port 800X
# 开工写代码
```

---

## 四、组员任务

---

## 组员 A — Module A LLM 智能筛选

**你要做的事**：把硬编码关键词过滤替换为 LLM 动态相关性判断，并集成 RAG 检索。

### 现状问题

```python
# 当前的硬编码关键词（github.py / hackernews.py）
AI_KEYWORDS = ("ai", "llm", "gpt", ...)
# 问题：遗漏相关资讯、命中无关资讯
```

### 新流程

```
外部API → httpx GET → 粗筛(去重/去噪) → LLM相关性判断 → INSERT raw_items
                              │                │
                              │     ┌──────────┘
                              │     ▼
                              │  DeepSeek 判断每条：
                              │  - 与AI/智能体相关度 (1-10)
                              │  - 匹配哪些用户标签
                              │  - 参考 RAG 检索的相似历史案例
                              │     │
                              │     ▼
                              │  生成 embedding → 存 pgvector
```

### 你要写的文件

```
module-a/
├── scrapers/
│   ├── github.py           # 增大 per_page (10→30)，加 LLM 筛选调用
│   ├── hackernews.py       # 增大检查量 (150→300)，加 LLM 筛选调用
│   ├── rss.py              # 加更多 RSS 源
│   ├── reddit.py           # 已有，加 LLM 筛选
│   └── __init__.py         # 已有
├── llm_filter.py           # 新增：LLM 相关性判断 + RAG 上下文拼接
└── main.py                 # 更新：/run 增加 LLM 筛选步骤
```

### 你要实现的功能

1. `llm_filter.py` — LLM 批量相关性判断
   - 输入：粗筛后的候选条目列表 + 历史 RAG 参考案例
   - 调 DeepSeek，prompt 中带相关性标准
   - 输出：每条的相关度评分(1-10) + 匹配标签 + 筛选理由
   - 无 API Key 时回退到原有关键词逻辑
2. 调大抓取量：GitHub `per_page=30`，HN 检查前 300 条
3. 生成 embedding：筛选通过的条目调 embedding API（可用 DeepSeek 或 text-embedding-3-small），写 raw_items.embedding
4. RAG 检索：新资讯 embedding → 在 raw_items 中检索最相似的 5 条历史资讯 → 拼进 LLM 筛选 prompt
5. `/health` + `/run` 保持兼容

### 验收方式

```bash
curl -X POST http://localhost:8001/run \
  -H "Content-Type: application/json" \
  -d '{"batch_id": "test-v2-001", "hours_back": 24}'
# 返回 {"status": "ok", "fetched": 25, "llm_filtered": true}
# 查数据库：每条 raw_items 的 metadata 含 ai_score + tags + filter_reason
# 查数据库：embedding 列非空
```

### 参考代码

- `module-b/ai/pipeline.py:252-291` — 现有 LLM 评分 prompt 结构，复用
- `shared/rag.py` — 组长提供的 embedding 生成和 RAG 检索函数

---

## 组员 B — Module B 结构优化 + 配图 + 长图生成

**你要做的事**：优化简报结构，每条资讯配图，最终输出长图。

### 你要写的文件

```
module-b/
├── ai/
│   ├── pipeline.py            # 更新 prompt：结构优化 + 用户偏好上下文
│   ├── image_matcher.py       # 新增：为每条资讯匹配图片
│   ├── render_longimage.py    # 新增：HTML → 长图渲染
│   └── __init__.py            # 已有
├── templates/
│   └── briefing_long.html     # 新增：长图 HTML 模板
└── main.py                    # 更新：/run 增加配图步骤 + /longimage 接口
```

### 你要实现的功能

#### B1 — 结构优化
- 更新 Step 6 (生成简报) 的 prompt，新的输出结构更清晰：
  - `headline`: 本期头条（1 条重点推荐）
  - `tl_dr`: 5-10 条核心要点
  - `sections`: 按主题分组，每组含 `section_title` + `items[]`
  - 每条 item 含 `title, summary, score, url, source, tags, image_keywords`
  - `key_takeaways`: 3-5 条关键洞察

#### B2 — 每资讯配图
- `image_matcher.py`：
  1. 从原文提取 OG 图（优先）
  2. 失败则用 DeepSeek 输出的 `image_keywords` 搜 Unsplash API
  3. 再失败则用分类默认配图
- 图片 URL 写入 briefing JSON 每条 item 的 `image_url` 字段

#### B3 — 长图生成
- `render_longimage.py`：
  - 读取最终 briefing JSON
  - 用 Jinja2 渲染 `briefing_long.html` 模板
  - Playwright 无头浏览器截图 → 输出 PNG 长图
  - 图片宽度 750px（微信朋友圈最优尺寸）
- `GET /longimage/{briefing_id}` 返回长图文件

### 验收方式

```bash
# 配图验证
curl -X POST http://localhost:8002/run \
  -H "Content-Type: application/json" \
  -d '{"type": "morning", "date": "2026-05-26", "batch_id": "test-v2-001"}'
# 检查返回的 briefings JSON 每条 item 有 image_url

# 长图验证
curl http://localhost:8002/longimage/{briefing_id}
# 返回 PNG 文件，尺寸 750 × N，包含全部简报内容
```

### 参考代码

- `ai-trend-publish/src/features/weixin-article/rendering/` — HTML 模板结构
- Unsplash API: `https://api.unsplash.com/search/photos?query=...`
- Playwright: `pip install playwright && playwright install chromium`

---

## 组员 C — 微信公众号 + 用户偏好系统

**你要做的事**：接入微信公众号消息回调，用户通过关键词/H5 选择标签，存储偏好并驱动个性化推送。

### 你要写的文件

```
module-c/
├── backend/
│   ├── main.py              # 更新：加 /weixin/callback 路由
│   ├── weixin_oa.py         # 新增：公众号消息回调处理
│   ├── tags.py              # 新增：标签 CRUD API
│   ├── push.py              # 更新：按用户标签匹配推送
│   └── db.py                # 已有（不改）
└── h5/
    └── preferences.html     # 新增：极简标签选择页
```

### 你要实现的功能

#### C1 — 公众号接入
- `POST /weixin/callback` 接收微信服务器回调
- 验证签名、处理消息事件（关注/取关/文字消息）
- **关键：微信回调 5 秒超时** → 收到消息立即返回空，异步处理

#### C2 — 标签选择
- 用户关注公众号 → 自动回复引导文字
- 用户回复 `订阅` → 返回标签列表模板消息
- 用户回复 `订阅 LLM 开源 Agent` → 解析标签 → 写入 subscriptions
- 用户回复 `偏好` → 返回 H5 链接，可视化勾选标签
- 菜单按钮 `偏好设置` → 跳转 H5 页面

#### C3 — 标签体系
```
LLM / 开源 / Python / AI安全 / Agent /
AI产品 / RAG / 多模态 / AI编程 / AI政策 / 融资
```

#### C4 — 用户行为追踪
- `POST /api/behavior` 接收小程序/公众号的点击事件
- 写入 user_behavior 表
- `GET /api/user/{openid}/profile` 返回用户画像（标签+近期点击摘要）

#### C5 — 个性化推送
- `POST /push` 更新：按 `briefing_id` 推送时，根据每个用户的 `preferences.tags` 做内容过滤/排序
- 冷启动兜底：无标签用户推默认综合简报

### 验收方式

```bash
# 标签接口
curl -X GET "http://localhost:8003/api/tags"
# 返回可用标签列表

curl -X POST http://localhost:8003/api/user/preferences \
  -H "Content-Type: application/json" \
  -d '{"openid":"test_user_001", "tags":["LLM","开源","Agent"]}'
# 返回 {"status":"ok"}

curl -X GET "http://localhost:8003/api/user/test_user_001/profile"
# 返回 {"tags":["LLM","开源","Agent"], "recent_clicks":[...]}

# 模拟微信回调
curl -X POST "http://localhost:8003/weixin/callback?signature=test&timestamp=1&nonce=1&echostr=echo"
# 返回 echo (验证通过)
```

### 注意事项
- 微信回调必须异步处理，5 秒内返回
- H5 页面部署在 module-c 内部，通过 nginx 暴露
- 测试时用微信公众平台测试号（无需正式认证）

---

## 组员 D — 微信发布更新 + 视频生成 (Module F)

**你要做的事**：更新微信 HTML 模板支持配图，实现长图分享，搭建 Module F 视频生成链路。

### 你要写的文件

```
module-d/
├── platforms/
│   └── weixin.py            # 更新：HTML 模板含配图 + 新结构
├── long_image.py            # 新增：独立长图生成（给分享用）
└── main.py                  # 更新：/publish 增加长图输出

module-f/                     # 新增模块（组长建骨架）
├── main.py                   # FastAPI /health, /generate
├── gemini_client.py          # Gemini 2.5 Pro API 封装
├── video_search.py           # 素材搜索(youtube-dl) + 下载
├── editor.py                 # FFmpeg 剪辑拼接
├── tts.py                    # Edge TTS 语音合成
├── subtitle.py               # Whisper 字幕生成
└── pipeline.py               # 视频生成全流程串联
```

### 你要实现的功能

#### D1 — 微信 HTML 模板更新
- 每条 item 的 `image_url` 渲染为 `<img>` 标签
- 新的分段结构：头条 → TL;DR → 分组资讯（带图） → 核心洞察
- 配图容错：图片加载失败不破坏布局

#### D2 — 长图输出
- `long_image.py`：读取 briefing JSON → 渲染 → Playwright 截图
- `/publish` 时同步输出长图文件
- 长图存入 `module-d/output/` 目录

#### D3 — Module F 视频生成
- `POST /generate` 接收 `{type, date}`，触发视频生成
- 流程：搜素材 → Gemini 分析片段 → DeepSeek 写脚本 → FFmpeg 剪辑 → Edge TTS 配音 → Whisper 字幕 → 合成
- 所有素材来源在片尾标注
- 输出存本地 `module-f/output/` 目录
- 暂不推送，仅本地生成

**视频主题：AI/智能体领域**

#### D4 — 成本与耗时
- API 成本 ~$0.3-0.5/期
- 处理耗时 10-20 分钟/期
- 统一生成一期，不做逐用户差异化

### 验收方式

```bash
# 微信发布（dry-run）
curl -X POST http://localhost:8004/publish \
  -H "Content-Type: application/json" \
  -d '{"briefing_id": "假简报ID", "platforms": ["weixin_oa"], "dry_run": true}'
# 检查输出的 HTML：每条资讯有图片，结构正确

# 视频生成
curl -X POST http://localhost:8006/generate \
  -H "Content-Type: application/json" \
  -d '{"type": "ai_agent_weekly", "date": "2026-05-26"}'
# 返回 {"status":"processing", "video_id":"xxx"}
# 等待 10-20 分钟后检查 output/ 目录

# 查视频状态
curl http://localhost:8006/status/{video_id}
```

### 参考代码
- Gemini API: `google-generativeai` Python SDK
- Edge TTS: `pip install edge-tts`
- Whisper: `pip install openai-whisper`
- FFmpeg: 系统安装 `ffmpeg`，Python `subprocess` 调用
- Module B 的 `render_longimage.py` — 长图逻辑可参考

---

## 组员 E（组长）— Contracts + RAG 基础设施 + 调度更新 + Dashboard

**你要做的事**：交付 Phase 2 contracts、pgvector 部署、RAG 工具函数、更新调度器和 Dashboard、Module F 骨架。

### 你要写的文件

```
contracts/
├── schema_v2.sql             # 增量 DDL（3 新表 + 扩展现有表 + pgvector）
├── seed_data_v2.sql          # 增量假数据
└── api-spec.yaml             # 更新接口定义

shared/
├── rag.py                    # 新增：embedding 生成 + RAG 检索函数
└── db.py                     # 更新：加 pgvector 连接支持

module-e/
├── pipeline.py               # 更新：调度加入 Module F 触发
├── dashboard/
│   ├── backend/dashboard.py  # 更新：加视频状态、用户行为统计
│   └── frontend/             # 更新：新面板
└── main.py                   # 更新：/admin/trigger 支持新链路

module-f/                      # 新增骨架
├── main.py                    # FastAPI 骨架：/health, /generate, /status/{id}
├── requirements.txt           # google-generativeai, edge-tts, openai-whisper, yt-dlp
└── Dockerfile

docker-compose.yml             # 更新：pgvector 镜像 + module-f 容器
nginx.conf                     # 更新：:8006 路由
```

### E1 — Contracts（D1 交付，所有人阻塞项）
- [ ] `schema_v2.sql` — 3 张新表 + 扩展现有表 + pgvector
- [ ] `seed_data_v2.sql` — 3 用户假偏好 + 1 周假行为数据
- [ ] `api-spec.yaml` — 更新接口签名

### E2 — RAG 基础设施
- [ ] `shared/rag.py`：
  - `generate_embedding(text) → list[float]` — 调 embedding API
  - `search_similar_items(embedding, top_k=5) → list[dict]` — pgvector 余弦检索
  - 批处理 `generate_embeddings_batch(texts) → list[list[float]]`
- [ ] Docker Compose 用 `pgvector/pgvector:pg16` 镜像替代原 postgres 镜像

### E3 — 调度器更新
- [ ] 新调度链：A/run → B/run → C/push + D/publish（并行）
- [ ] 视频独立触发：`POST /admin/trigger-video`（手动，不与早晚报自动绑定）
- [ ] 错误隔离：视频失败不影响文档推送

### E4 — Dashboard 更新
- [ ] 用户行为概览：标签分布饼图、活跃用户数
- [ ] 视频状态面板：最近视频列表、生成状态
- [ ] 运行记录增加视频项

### E5 — Module F 骨架
- [ ] 标准 FastAPI 骨架（`/health`, `/generate`, `/status/{id}`）
- [ ] 各文件函数签名 + 空实现
- [ ] Dockerfile + requirements.txt

### E6 — 优化建议落地
- [ ] pgvector 兼容性验证（PG 16 + pgvector 版本组合测试）
- [ ] 微信回调异步处理提示（组员 C 文档中注明）
- [ ] 冷启动兜底逻辑：默认标签 `["AI", "LLM", "开源"]`，新用户无标签时推综合简报

### 验收方式

```bash
docker compose up -d
docker compose ps  # 7 个容器全部 healthy（+module-f + pgvector）
curl http://localhost/admin/trigger?type=morning  # 手动触发全链路
curl http://localhost/admin/trigger-video          # 手动触发视频生成
# 打开 http://localhost/admin 看 Dashboard
```

---

## 五、各模块接口速查（Phase 2 更新）

| 模块 | 端口 | 业务入口 | 新增入口 | 读表 | 写表 |
|------|------|---------|---------|------|------|
| A | 8001 | `POST /run` | — | raw_items (RAG) | raw_items + embedding |
| B | 8002 | `POST /run` | `GET /longimage/{id}` | raw_items + subscriptions | briefings |
| C | 8003 | `POST /push` | `POST /weixin/callback`, `GET/POST /api/user/preferences` | briefings + subscriptions | subscriptions + user_behavior |
| D | 8004 | `POST /publish` | — | briefings | publish_log |
| E | 8005 | `POST /admin/trigger` | `POST /admin/trigger-video` | 全部 | run_log |
| F | 8006 | `POST /generate` | `GET /status/{id}` | raw_items + briefings | videos |

每个模块还必须实现 `GET /health`，返回 `{"status": "ok"}`。

---

## 六、时间线

```
          D1        D2       D3    D4    D5    D6    D7    D8    D9    D10
组长 ── [contracts + RAG交付]
        然后组长继续写调度器更新 + Dashboard + Module F 骨架

A  ──── [等组长D2交付]──████████████████──── 完成自测
B  ──── [等组长D2交付]──████████████████████── 完成自测
C  ──── [等组长D2交付]──████████████████──── 完成自测
D  ──── [等组长D2交付]──████████████████████── 完成自测
         │
         └── D 在完成 D1-D2 后继续 Module F（+3 天）

D10 ── 全员联调，docker compose up
```

**唯一的等待：所有人等组长 D1-D2 交付 contracts + RAG 工具 + 脚手架。之后 4 人完全并行。**

---

## 七、你需要准备的账号

| 谁 | 申请什么 | 去哪里申请 |
|----|----------|-----------|
| 组长 | pgvector Docker 镜像 | 公开镜像，无需申请 |
| 组长 | Embedding API Key | 复用 DeepSeek 或 OpenAI |
| A | GitHub Token（扩大额度） | github.com/settings/tokens |
| C | 微信公众号测试号 | mp.weixin.qq.com/debug/cgi-bin/sandbox |
| D | Gemini API Key | aistudio.google.com |
| D | Unsplash API Key（配图用） | unsplash.com/developers |
| 全员 | DeepSeek API Key | 已有 |

---

## 八、注意事项

1. **不要调别人的 API**。不知道别人的 IP 和端口。只读写数据库。
2. **用 seed_data 开发**。本地自己的 PostgreSQL（pgvector 版），数据够用。
3. **先写死、再配置化**。API Key 先写 .env，别写在代码里。
4. **dry-run 优先**。D 模块和 F 模块先做本地输出，确认无误再真发/真推。
5. **视频不和文档抢资源**。视频独立触发，错开早晚报时间（建议 10:00 / 22:00）。
6. **冷启动兜底**。无标签用户推默认综合简报，不要返回空白。
7. **微信 5 秒超时**。C 模块的回调处理必须异步。
8. **版权标注**。视频片尾标注素材来源 + 非商用声明。
9. **每天 commit**。分支命名：`phase2-module-a`, `phase2-module-b`, 等。
