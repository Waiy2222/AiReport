# AI 资讯早报/晚报智能体

> 🤖 全自动 AI 新闻聚合 · 智能加工 · 多端分发系统

## 项目简介

AI 资讯早报/晚报智能体是一个**全自动化 AI 新闻流水线**，每日定时从多个信源抓取 AI 领域最新资讯，经过 LLM 评分、14 标签分类、多智能体辩论、语义去重、配图匹配等 10 道工序，生成结构化早晚报，通过**微信小程序**、公众号、知乎、CSDN 等多渠道分发。

### 核心能力

- **多源聚合**: GitHub Trending、Hacker News、20+ RSS 源
- **AI 深度加工**: LLM 评分 → 去重 → 三方辩论 → 摘要 → 配图 → 长图
- **14 标签全覆盖**: 大模型 / 智能体 / 开源 / 芯片 / 机器人 / 自动驾驶 / 融资 / 医疗等
- **三方辩论系统**: 技术 / 商业 / 社会三维度 AI 辩论
- **智能配图**: Pexels / Unsplash 4 级降级匹配
- **微信小程序**: 5 页面（首页/详情/历史/趋势/我的），标签+个性化偏好
- **Dashboard 管控**: 调度管理、运行监控、信源健康度
- **视频生成**（本地）: AI 视频周报

## 架构总览

```
                    ┌──────────────────────────┐
                    │   PostgreSQL (pgvector)   │
                    │       :5432               │
                    └──────┬───────────────────┘
                           │
  ┌────────────┬───────────┼───────────┬──────────────┬──────────────┐
  │            │           │           │              │              │
  ▼            ▼           ▼           ▼              ▼              ▼
Module A    Module B    Module C    Module D      Module E      Module F
:8001       :8002       :8003       :8004         :8005         :8006
抓取+筛选   AI加工+    小程序后端  多平台发布    调度管理      视频生成
           长图渲染    +公众号                    +Dashboard    (本地)
```

### 流水线流程

```
① 抓取 (A) → ② LLM评分 (B) → ③ 三方辩论 (B) → ④ URL去重 (B)
→ ⑤ 语义去重 (B) → ⑥ 标签匹配 (B) → ⑦ 翻译 (B)
→ ⑧ LLM摘要+Agent质检 (B) → ⑨ 配图匹配 (B) → ⑩ 写入DB (B)
→ ⑪ 推送 (C) + 发布 (D)
```

## 快速开始

### 1. 环境准备

```bash
# 确保已安装：Python 3.11+, Docker Desktop, Git
# 详细环境要求见 ENVIRONMENT.md

git clone <repo-url>
cd ai-news-briefing-agent

# 配置 API Key
cp .env.example .env
# 编辑 .env，至少填入 DEEPSEEK_API_KEY
```

### 2. 安装 Python 依赖

```bash
pip install -r module-a/requirements.txt
pip install -r module-b/requirements.txt
pip install -r module-c/backend/requirements.txt
pip install -r module-e/requirements.txt
```

### 3. 启动 PostgreSQL

```bash
docker compose up -d postgres
# 确认 healthy
docker ps --filter "name=postgres"
```

### 4. 启动各模块（4 个终端）

**终端 1: 模块 A (抓取, :8001)**
```bash
cd module-a
export PYTHONPATH="../:../shared"
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news"
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --log-level warning
```

**终端 2: 模块 B (AI加工, :8002)**
```bash
cd module-b
export PYTHONPATH="../:../shared"
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news"
python -m uvicorn main:app --host 0.0.0.0 --port 8002 --log-level warning
```

**终端 3: 模块 C (小程序后端, :8003)**
```bash
cd module-c/backend
export PYTHONPATH="../../:../../shared"
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news"
python -m uvicorn main:app --host 0.0.0.0 --port 8003 --log-level warning
```

**终端 4: 模块 E (Dashboard+调度, :8005)**
```bash
cd module-e
export PYTHONPATH="../:../shared"
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news"
export A_URL="http://localhost:8001/run"
export B_URL="http://localhost:8002/run-b"
export C_URL="http://localhost:8003/push"
python -m uvicorn main:app --host 0.0.0.0 --port 8005 --log-level warning
```

### 5. 触发生成

```bash
# 早报
curl -X POST "http://localhost:8005/admin/trigger?type=morning"

# 晚报
curl -X POST "http://localhost:8005/admin/trigger?type=evening"
```

Dashboard 地址: http://localhost:8005/dashboard

### 6. 视频生成 (模块 F, 本地)

模块 F (:8006) 负责 AI 视频周报，**仅本地运行**，需单独启动：

```bash
cd module-f
export PYTHONPATH="../:../shared"
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news"
export DEEPSEEK_API_KEY="sk-你的DeepSeek密钥"
python -m uvicorn main:app --host 0.0.0.0 --port 8006 --log-level warning
```

**触发：**

```bash
curl -X POST "http://localhost:8006/generate" \
  -H "Content-Type: application/json" \
  -d '{"type":"ai_agent_weekly"}'
```

**查进度：** `curl http://localhost:8006/status/{video_id}`　|　**视频列表：** `curl http://localhost:8006/videos`

### 7. 一键脚本

> 需在 **Git Bash** 下运行（PowerShell 自带的 WSL bash 不可用）。

```bash
cd /d/项目/ai报道后续修改/ai-news-briefing-agent
bash start_all.sh          # 后台启动全部模块 (A~E, :8001~8005)
bash rerun.sh both         # 改代码后重跑（清缓存+重启B+触发早晚报）
```

## 微信小程序

小程序源码在 `module-c/miniprogram/`，用**微信开发者工具**打开 `module-c/` 目录即可。

| 页面 | 路径 | 功能 |
|------|------|------|
| 首页 | `pages/index/` | 早报/晚报 Tab 切换，头条+分区展示 |
| 详情 | `pages/detail/` | 单条新闻完整内容 |
| 历史 | `pages/history/` | 历史简报列表+搜索 |
| 趋势 | `pages/trends/` | 趋势仪表盘 |
| 我的 | `pages/mine/` | 兴趣标签选择+信源健康度+订阅设置 |

- 后端 API: `localhost:8003`
- 开发时需在微信开发者工具中勾选「不校验合法域名」

## 标签体系（14 标签）

与微信小程序首页展示的 section 标签完全一致：

| 标签 key | 小程序显示名 | 分类 |
|----------|-------------|------|
| LLM | 大模型前沿 | AI核心 |
| Agent | 智能体动态 | AI核心 |
| 开源 | 开源工具 | AI核心 |
| 工具 | 开发者工具 | AI核心 |
| 芯片 | 硬件动态 | AI核心 |
| 机器人 | 机器人 | AI核心 |
| 自动驾驶 | 自动驾驶 | AI核心 |
| 科技 | 科技产业 | 产业 |
| 融资 | 投融资 | 产业 |
| 行业 | 行业观察 | 产业 |
| 医疗 | 医疗健康 | 产业 |
| 全球 | 全球视野 | 综合 |
| 安全 | 安全快讯 | 综合 |
| 体育 | 体育赛事 | 综合 |

## 定时调度

模块 E 内置 APScheduler，默认每天 2 次自动运行：

| 任务 | 时间 | 环境变量 |
|------|------|---------|
| 早报 | 08:00 | `MORNING_TIME` |
| 晚报 | 20:00 | `EVENING_TIME` |

`SCHEDULE_ENABLED=true` 启用，`SCHEDULE_ENABLED=false` 关闭。

## API 端点

### Dashboard (:8005)
| 端点 | 方法 | 说明 |
|------|------|------|
| `/admin/overview` | GET | 运行总览 |
| `/admin/trigger?type=morning\|evening&tags=` | POST | 手动触发（支持标签过滤） |
| `/admin/schedule` | GET | 定时任务状态 |
| `/preview/{briefing_id}` | GET | 简报 HTML 预览 |
| `/longimage/{briefing_id}` | GET | 长图 PNG 下载 |

### 小程序后端 (:8003)
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/briefings/latest?type=` | GET | 最新简报 |
| `/api/briefings/history` | GET | 历史简报 |
| `/api/briefings/{id}` | GET | 简报详情 |
| `/api/tags` | GET | 标签列表 |
| `/api/user/preferences` | GET/POST | 用户偏好 |
| `/api/sources/health` | GET | 信源健康度 |
| `/api/behavior` | POST | 用户行为上报 |

## 项目目录

```
ai-news-briefing-agent/
├── .env.example          # 环境变量模板
├── docker-compose.yml    # Docker 编排
├── deploy.sh             # 生产部署脚本
├── start_all.sh          # 本地一键启动
├── rerun.sh              # 代码修改后重跑
├── ENVIRONMENT.md        # 环境要求说明
├── contracts/            # DB Schema + API 规范
├── shared/               # 共享模块 (db, rag)
├── module-a/             # 资讯抓取
│   ├── main.py           # FastAPI (:8001)
│   ├── orchestrator.py   # 抓取编排
│   └── scrapers/         # GitHub/HN/RSS 抓取器
├── module-b/             # AI 内容加工 ⭐
│   ├── main.py           # FastAPI (:8002)
│   ├── pipeline.py       # 10 步流水线
│   └── ai/
│       ├── analyzer.py       # AI 评分
│       ├── dedup.py          # URL + 语义去重
│       ├── debute_agent.py   # 三方辩论
│       ├── summarizer.py     # 摘要 + 标签清洗 + Agent 质检
│       ├── image_matcher.py  # 配图匹配
│       ├── prompts.py        # Prompt 模板
│       └── render_longimage.py # 长图渲染
├── module-c/             # 小程序后端
│   ├── backend/          # FastAPI (:8003)
│   ├── miniprogram/      # 小程序源码
│   │   └── pages/        # 5 页面
│   └── h5/               # H5 页面
├── module-d/             # 多平台发布 (:8004)
├── module-e/             # 调度 + Dashboard (:8005)
│   ├── pipeline.py       # 全链路编排
│   └── dashboard/        # Dashboard 前后端
└── module-f/             # 视频生成 (本地, :8006)
```

## 常见问题

### 端口被占用
```bash
netstat -ano | grep ":8002" | grep LISTENING
taskkill //F //PID <PID>
```

### 改代码不生效
Python `.pyc` 缓存 → 删 `__pycache__` + 重启：
```bash
cd module-b
python -c "import shutil,os;[shutil.rmtree(os.path.join(r,d),ignore_errors=True) for r,ds,fs in os.walk('.') for d in ds if d=='__pycache__']"
```

### 模块 E 调用返回 502
未设 `A_URL`/`B_URL` → 默认连 Docker 域名。本地必须置 `export A_URL="http://localhost:8001/run"` 等。

### ModuleNotFoundError: No module named 'db'
从根目录启动了 → 必须 `cd` 到模块目录启动。

### 小程序连不上后端
- 确认模块 C 运行在 `:8003`
- 打开「不校验合法域名」
- 确认 `api.js` 中 baseUrl 是 `http://localhost:8003`

## 技术栈

| 层 | 技术 |
|------|------|
| 后端 | FastAPI (异步), Python 3.12 |
| 数据库 | PostgreSQL 16 + pgvector |
| AI/LLM | DeepSeek API (via openai SDK) |
| 容器 | Docker + Docker Compose |
| 小程序 | 微信小程序原生框架 |
| 前端 | Dashboard (HTML/CSS/JS), H5 |
| 视频 | FFmpeg, Edge-TTS, Whisper |
| 调度 | APScheduler |
| 代理 | Nginx |

## 贡献者

- **队长**: 架构设计 + 模块B核心 + 模块E调度
- **队员A**: 模块A 资讯抓取
- **队员C**: 模块C 微信小程序
- **队员D**: 模块D 多平台发布
- **组员1**: 趋势仪表盘 + 视频模块F
- **组员2**: 信源自主扩展


