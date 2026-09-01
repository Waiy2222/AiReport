# 本地开发环境要求

> 最后更新: 2026-06-17
> 
> 本文档仅覆盖**本地开发**。生产部署用 `deploy.sh`（Docker Compose 一键部署）。

## 硬件

| 项目 | 最低 | 推荐 |
|------|------|------|
| CPU | 4 核 | 8 核+ |
| 内存 | 8 GB | 16 GB+ |
| 磁盘 | 30 GB 可用 | 50 GB+ SSD |

## 必须安装

| 软件 | 版本 | 用途 | 安装 |
|------|------|------|------|
| **Python** | 3.11 ~ 3.12 | 全部模块 | [python.org](https://www.python.org/downloads/) |
| **Docker Desktop** | 最新 | PostgreSQL + pgvector 容器 | [docker.com](https://docs.docker.com/get-docker/) |
| **Git** | 2.40+ | 版本管理 | [git-scm.com](https://git-scm.com/downloads) |
| **Git Bash** | — | Windows 下执行 shell 脚本 | 随 Git 附带 |

## 可选安装（仅本地视频模块 F 需要）

| 软件 | 用途 |
|------|------|
| **FFmpeg** 5+ | 视频剪辑、转码、字幕合成 |
| **Playwright Chromium** | 长图 PNG 渲染（模块 B/D 也需要） |

```bash
# Playwright 浏览器安装
playwright install chromium
```

## Python 包

各模块独立 `requirements.txt`，按需安装：

```bash
pip install -r module-a/requirements.txt
pip install -r module-b/requirements.txt
pip install -r module-c/backend/requirements.txt
pip install -r module-e/requirements.txt

# 可选
pip install -r module-d/requirements.txt
pip install -r module-f/requirements.txt
```

核心依赖（所有模块共用）:
```
fastapi>=0.115    uvicorn[standard]    asyncpg>=0.30
httpx>=0.27       pydantic>=2.10
```

各模块额外依赖:

| 模块 | 额外包 |
|------|--------|
| A | `feedparser` (RSS), `openai` (LLM) |
| B | `openai`, `jinja2` (模板), `playwright` (长图) |
| C | `pytest`, `pytest-asyncio` (测试) |
| D | `Pillow`, `qrcode`, `playwright` |
| E | `apscheduler` (定时), `aiofiles` |
| F | `openai`, `edge-tts`, `openai-whisper`, `yt-dlp`, `google-generativeai` |

## 外部 API Key

配置在项目根目录 `.env` 文件中（从 `.env.example` 复制）。

| 服务 | 环境变量 | 必须 | 说明 |
|------|---------|------|------|
| **DeepSeek API** | `DEEPSEEK_API_KEY` | ✅ 必须 | LLM 调用，所有 AI 功能依赖此 Key |
| Unsplash | `UNSPLASH_ACCESS_KEY` | 可选 | 配图搜索，无则用 Pexels 兜底 |
| Pexels | `PEXELS_API_KEY` | 可选 | 视频模块素材搜索 |
| 微信小程序 | `WECHAT_APPID` / `WECHAT_SECRET` | 可选 | 小程序订阅消息推送 |
| 微信公众号 | `WEIXIN_OA_APPID` / `WEIXIN_OA_SECRET` | 可选 | 公众号消息推送 |
| 知乎 | `ZHIHU_CLIENT_ID` / `ZHIHU_CLIENT_SECRET` | 可选 | 知乎发布 |
| CSDN | `CSDN_USERNAME` / `CSDN_PASSWORD` | 可选 | CSDN 发布 |
| 阿里云百炼 | `BAILIAN_API_KEY` | 可选 | 视频理解 |
| Bilibili | `BILIBILI_COOKIE` | 可选 | B站视频素材搜索 |

```bash
# 最小 .env 配置（本地能跑通全链路）
cp .env.example .env
# 编辑 .env，至少填入：
#   DEEPSEEK_API_KEY=sk-your-key
#   DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

## 数据库

- **PostgreSQL 16** + **pgvector** 扩展
- Docker 镜像: `pgvector/pgvector:pg16`
- 默认端口: `5432`
- 默认数据库: `ai_news`
- 默认账号: `postgres` / `postgres`

```bash
# 启动
docker compose up -d postgres

# 检查
docker ps --filter "name=postgres"   # 状态应为 healthy
```

## 端口占用

启动前确保以下端口未被占用：

| 端口 | 模块 | 说明 |
|------|------|------|
| 5432 | PostgreSQL | 数据库 |
| 8001 | A | 资讯抓取 |
| 8002 | B | AI 内容加工 |
| 8003 | C | 微信小程序后端 |
| 8005 | E | 调度 + Dashboard |

模块 D (:8004) 和 F (:8006) 按需启动。

```bash
# Windows 端口检查
netstat -ano | grep -E "5432|8001|8002|8003|8005"
```

## 微信小程序开发者工具

项目的小程序源码在 `module-c/miniprogram/` 目录。

- 下载: [微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)
- 导入项目: 选择 `module-c/` 目录（`project.config.json` 所在目录）
- AppID: 在 `project.config.json` 中配置，或使用测试号
- 后端 API: 小程序请求 `module-c` 的 API（默认 `localhost:8003`），需在小程序工具中勾选"不校验合法域名"

```bash
# 启动后端
cd module-c/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8003 --log-level warning
```

## 环境检查脚本

```bash
echo "=== Python ==="
python --version

echo "=== Docker ==="
docker info > /dev/null 2>&1 && echo "Docker OK" || echo "Docker 未运行!"

echo "=== PostgreSQL ==="
docker ps --filter "name=postgres" --format "table {{.Names}}\t{{.Status}}"

echo "=== 端口 ==="
netstat -ano | grep -E ":5432|:8001|:8002|:8003|:8005" | grep LISTENING || echo "端口空闲"

echo "=== .env ==="
test -f .env && echo ".env 存在" || echo "缺少 .env，请从 .env.example 复制并配置"
```

## 微信小程序标签说明

小程序使用的标签体系（14 标签）来自模块 B 摘要引擎：

| 标签 key | 小程序显示名 | 所属分类 |
|----------|-------------|---------|
| LLM | 大模型 | AI核心 |
| Agent | 智能体 | AI核心 |
| 开源 | 开源项目 | AI核心 |
| 工具 | 开发工具 | AI核心 |
| 芯片 | 芯片硬件 | AI核心 |
| 机器人 | 机器人 | AI核心 |
| 自动驾驶 | 自动驾驶 | AI核心 |
| 科技 | 科技动态 | 产业 |
| 融资 | 融资并购 | 产业 |
| 行业 | 行业观察 | 产业 |
| 医疗 | 医疗健康 | 产业 |
| 全球 | 全球视野 | 综合 |
| 安全 | AI安全 | 综合 |
| 体育 | 体育赛事 | 综合 |

用户可在小程序「我的」页面选择兴趣标签，首页按标签过滤简报内容。
