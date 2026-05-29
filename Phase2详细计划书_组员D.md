# AI 资讯早报/晚报智能体 · Phase 2 详细计划书（组员 D）

> **角色**：组员 D  
> **负责模块**：Module D（微信发布 + 长图） + Module F（视频生成）  
> **日期**：2026-05-28  
> **基线**：Phase 1 全部模块已完成（5 模块 + 57 测试通过）  
> **前置依赖**：组长交付 `contracts/schema_v2.sql`、`shared/rag.py`、`docker-compose.yml` 更新

---

## 一、项目框架全景分析

### 1.1 整体架构

```
PostgreSQL (pgvector/pg16) ←── 唯一数据交汇点
        │
   ┌────┼────┬────┬────┬────┬────┐
   A    B    C    D    E    F    │
 :8001 :8002 :8003 :8004 :8005 :8006
 抓取  加工  推送  发布  调度  视频
```

### 1.2 Phase 1 现有模块清单

| 模块 | 端口 | 现有文件 | 职责 |
|------|------|---------|------|
| A | 8001 | main.py, db.py, orchestrator.py, scrapers/{github,hackernews,rss,reddit,filters} | 资讯抓取 + 关键词过滤 |
| B | 8002 | main.py, db.py, pipeline.py, ai/{pipeline,analyzer,dedup,enricher,summarizer,client,prompts} | AI评分/去重/摘要/简报生成 |
| C | 8003 | backend/{main,db,models,auth,config,push,mock_data}, miniprogram/** | 小程序后端 + 订阅推送 |
| D | — | **不存在** | 多平台发布（Phase 2 新建） |
| E | 8005 | **不存在** | 调度 + Dashboard（Phase 2 新建） |
| F | 8006 | **不存在** | 视频生成（Phase 2 新建） |

### 1.3 Phase 2 组员 D 负责范围

根据计划书，组员 D 负责两个子模块：

1. **Module D**（`module-d/`）：微信发布模板更新 + 长图生成
2. **Module F**（`module-f/`）：视频生成全链路（含素材搜索、Gemini分析、DeepSeek脚本、FFmpeg剪辑、TTS配音、Whisper字幕）

---

## 二、文件级详细计划

---

### 文件 1：`module-d/main.py`

#### 功能说明
FastAPI 应用入口，提供健康检查、发布接口。

#### 函数清单

| 函数 | 类型 | 说明 |
|------|------|------|
| `startup()` | event | 初始化 DB 连接池 |
| `shutdown()` | event | 关闭 DB 连接池 |
| `health()` | GET /health | 健康检查，返回 `{"status":"ok","db":"connected/disconnected"}` |
| `publish(req)` | POST /publish | 接收发布请求，执行多平台发布 + 长图输出 |

#### 调试检测点

| # | 检测点 | 方法 | 预期 |
|---|--------|------|------|
| DB-1 | `init_db()` 成功时 `get_pool()` 返回非空 | 调用 `get_pool()` | `Pool` 对象 |
| DB-2 | `init_db()` 失败（无 PG）时优雅降级 | 捕获 `Exception` 不崩溃 | 服务仍可启动，/health 显示 db: disconnected |
| API-1 | `POST /publish` 收到无效 `briefing_id` | 传入非法 UUID | 返回 400 |
| API-2 | `POST /publish` dry_run=True | 调用接口 | 返回模拟发布结果，不实际发送 |
| API-3 | `POST /publish` 长图输出 | dry_run 成功后检查 output/ | PNG 文件存在 |

#### 测试方案

| 测试项 | 输入 | 操作 |
|--------|------|------|
| T1 健康检查 | `GET /health` | curl 验证返回 `{"status":"ok"}` |
| T2 无效参数 | `POST /publish` body: `{"briefing_id": "bad-uuid"}` | 验证 400 错误 |
| T3 Dry-run 发布 | `POST /publish` body: `{"briefing_id": "b0000001-...", "platforms":["weixin_oa"], "dry_run":true}` | 验证返回 dry_run 结果 |
| T4 真实发布（mock） | `POST /publish` body: `{"briefing_id": "b0000001-...", "platforms":["weixin_oa"]}` | 验证 publish_log 写入 |

#### 预期测试结果

```
T1 → {"status": "ok", "db": "connected"} / {"status": "ok", "db": "disconnected"}
T2 → HTTP 422 / 400（取决于验证逻辑）
T3 → {"status": "dry_run", "briefing_id": "b0000001-...", "platforms": ["weixin_oa"], "longimage": "output/xxx.png"}
T4 → {"status": "ok", "results": {"weixin_oa": {"status": "success"}}}
```

---

### 文件 2：`module-d/platforms/weixin.py`

#### 功能说明
微信公众号 HTML 模板渲染，支持配图 + 新结构。

#### 函数清单

| 函数 | 类型 | 说明 |
|------|------|------|
| `render_article(briefing, dry_run=False)` | public | 渲染公众号文章 HTML |
| `_render_headline(item)` | private | 渲染头条区域（大图 + 标题 + 摘要） |
| `_render_tldr(items)` | private | 渲染 TL;DR 要点列表 |
| `_render_section(section)` | private | 渲染每个主题分区（含图片） |
| `_render_takeaways(items)` | private | 渲染核心洞察区域 |
| `_fallback_image(tags)` | private | 标签匹配默认配图 URL |
| `publish_weixin_oa(briefing_id, dry_run=False)` | public | 调用微信发布 API（或模拟） |

#### HTML 模板结构

```
┌─────────────────────────────────┐
│  头条区域（大标题 + 大图 + 摘要）  │
├─────────────────────────────────┤
│  TL;DR 核心要点（5-10条）         │
├─────────────────────────────────┤
│  ┌─ 分区 1 ──────────────────┐  │
│  │  标题: 大模型开源动态       │  │
│  │  ┌─ item ──────────────┐  │  │
│  │  │ [img] 标题 + 摘要    │  │  │
│  │  └─────────────────────┘  │  │
│  │  ┌─ item ──────────────┐  │  │
│  │  │ [img] 标题 + 摘要    │  │  │
│  │  └─────────────────────┘  │  │
│  └───────────────────────────┘  │
├─────────────────────────────────┤
│  核心洞察（3-5条）               │
├─────────────────────────────────┤
│  底部：生成时间 + 版权信息        │
└─────────────────────────────────┘
```

#### 调试检测点

| # | 检测点 | 方法 | 预期 |
|---|--------|------|------|
| HTML-1 | 头条区域渲染 | 检查 HTML 包含 `<h1>` 和头条大图 `<img>` | 存在且正确 |
| HTML-2 | 每条 item 配图 | 检查 HTML 中 `<img>` 数量 = item 数量 | 图片不缺失 |
| HTML-3 | 图片加载失败布局容错 | 在 `<img>` 上设置 `onerror` / `loading="lazy"` | 布局不坍塌 |
| HTML-4 | dry_run 模式输出 HTML 文件 | `dry_run=True` | `output/dry_run_xxx.html` 文件生成 |
| HTML-5 | 标签匹配默认配图 | 无 OG / Unsplash 图片时 | 返回分类默认图 URL |

#### 测试方案

| 测试项 | 输入 | 操作 |
|--------|------|------|
| T1 头条渲染 | seed_data 中的 briefing | 检查是否生成 `<h1>` 标签 |
| T2 配图完整性 | briefing 中 10 条 item | 验证 10 个 `<img>` 标签 |
| T3 布局容错 | 拼接无效图片 URL | 页面布局不破碎 |
| T4 默认配图回退 | 空 tags 数组 | 返回 `default.png` |

#### 预期测试结果

```
T1 → HTML 中 <h1>DeepSeek-V4 技术报告...</h1> 存在
T2 → HTML 中 <img> 标签 count = 10
T3 → HTML 中包含 onerror 处理或 loading="lazy"
T4 → tags=[] 时返回 default_image_url
```

---

### 文件 3：`module-d/long_image.py`

#### 功能说明
独立长图生成，读取 briefing JSON → 渲染 HTML → Playwright 截图 → 输出 PNG。

#### 函数清单

| 函数 | 类型 | 说明 |
|------|------|------|
| `render_briefing_html(briefing)` | public | 将 briefing JSON 渲染为长图专用 HTML |
| `capture_screenshot(html_content, output_path, width=750)` | public | Playwright 无头浏览器截图 |
| `generate_long_image(briefing_id, pool)` | public | 全流程：读取 → 渲染 → 截图 → 保存 |
| `_build_longimage_template(items)` | private | 构建长图 HTML 模板字符串 |

#### 渲染技术栈
- **HTML 渲染**：Python 字符串模板（避免额外依赖） 或 Jinja2（如果已安装）
- **截图引擎**：Playwright（`playwright install chromium`）
- **输出尺寸**：750px 宽（微信朋友圈最优尺寸），高度自适应

#### 调试检测点

| # | 检测点 | 方法 | 预期 |
|---|--------|------|------|
| SS-1 | Playwright 截图引擎可用 | `playwright install chromium` | 安装成功 |
| SS-2 | 长图宽度 | 检查输出 PNG | width=750px |
| SS-3 | 长图包含全部内容 | 对比 HTML 和截图 | 内容完整无截断 |
| SS-4 | 无 DB 时的 mock 模式 | DB 不可用 | 使用 mock_data 降级 |

#### 测试方案

| 测试项 | 输入 | 操作 |
|--------|------|------|
| T1 长图生成 | `briefing_id="b0000001-..."` | 调用 `generate_long_image()` |
| T2 图片尺寸 | 输出 PNG | `file` / `identify` 验证 750px |
| T3 内容完整性 | 对比 HTML 截图 | 所有文字可见 |
| T4 异常 briefing | `briefing_id="不存在"` | 返回 404 |

#### 预期测试结果

```
T1 → PNG 文件生成在 output/longimage_{briefing_id}.png
T2 → 图片宽度 750px，高度 >= 2000px（取决于内容量）
T3 → 截图包含全部标题、摘要、图片
T4 → 返回 {"error": "briefing not found"} / 404
```

---

### 文件 4：`module-f/main.py`

#### 功能说明
Module F（视频生成模块）FastAPI 入口。

#### 函数清单

| 函数 | 类型 | 说明 |
|------|------|------|
| `startup()` | event | 初始化 DB + 创建 output/downloads 目录 |
| `shutdown()` | event | 关闭 DB |
| `health()` | GET /health | 健康检查 |
| `generate(req)` | POST /generate | 触发视频生成（异步），返回 video_id |
| `get_status(video_id)` | GET /status/{video_id} | 查询视频生成状态 |
| `list_videos(limit, offset)` | GET /videos | 视频列表 |

#### 调试检测点

| # | 检测点 | 方法 | 预期 |
|---|--------|------|------|
| F-API-1 | POST /generate 返回 video_id | curl 调用 | `{"status":"processing","video_id":"xxx"}` |
| F-API-2 | GET /status 查询进度 | curl 调用 | `{"status":"processing/done/failed", ...}` |
| F-API-3 | GET /videos 分页 | curl 调用 | 返回列表 + total 计数 |
| F-API-4 | output 目录自动创建 | 启动时 | 目录存在 |
| F-API-5 | 视频状态持久化到 DB | 查 videos 表 | 记录存在 |

#### 测试方案

| 测试项 | 输入 | 操作 |
|--------|------|------|
| T1 健康检查 | `GET /health` | curl 验证 |
| T2 触发生成 | `POST /generate {"type":"ai_agent_weekly","date":"2026-05-28"}` | 返回 video_id |
| T3 状态查询 | `GET /status/{video_id}` | 轮询状态 |
| T4 视频列表 | `GET /videos` | 返回列表 |
| T5 无效参数 | `POST /generate {}` | 返回 422 |

#### 预期测试结果

```
T1 → {"status": "ok", "db": "connected"}
T2 → {"status": "processing", "video_id": "生成UUID", "message": "Video generation started"}
T3 → {"status": "pending/processing/done/failed", "video_id": "...", "created_at": "..."}
T4 → {"total": N, "videos": [...]}
T5 → HTTP 422 验证错误
```

---

### 文件 5：`module-f/gemini_client.py`

#### 功能说明
Gemini 2.5 Pro API 封装，用于视频素材分析 + 内容理解。

#### 函数清单

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_gemini_client()` | public | 初始化 Gemini 客户端 |
| `analyze_video_content(video_path)` | public | 分析视频片段内容 |
| `summarize_transcript(transcript)` | public | 对语音转写文本做摘要 |
| `select_best_clips(video_segments, description)` | public | 根据描述选择最优片段 |
| `has_api_key()` | public | 检查 API Key 是否配置 |

#### 调试检测点

| # | 检测点 | 方法 | 预期 |
|---|--------|------|------|
| GM-1 | Gemini API 可用 | `has_api_key()` | True/False |
| GM-2 | API Key 缺失时优雅降级 | `has_api_key()` 为 False | 提示配置，不崩溃 |
| GM-3 | 视频分析返回结构化结果 | 传入 mock 视频路径 | 返回帧描述列表 |

#### 测试方案

| 测试项 | 输入 | 操作 |
|--------|------|------|
| T1 API Key 检测 | 无环境变量 | 返回 False |
| T2 Mock 分析 | mock 数据 | 返回合法格式 |
| T3 API 调用 | 配置了 Key | 返回非空结果 |

#### 预期测试结果

```
T1 → has_api_key() = False（无 GEMINI_API_KEY 时）
T2 → 返回 {"clips": [...], "description": "..."} 格式
T3 → 返回实际 Gemini API 响应
```

---

### 文件 6：`module-f/video_search.py`

#### 功能说明
YouTube/素材网站搜索 + 视频下载。

#### 函数清单

| 函数 | 类型 | 说明 |
|------|------|------|
| `search_materials(topic, max_results=5)` | public | 搜索 AI/Agent 相关视频素材 |
| `download_video(url, output_dir)` | public | 下载视频到本地 |
| `extract_audio(video_path, output_path)` | public | 提取视频中的音频 |
| `get_video_metadata(url)` | public | 获取视频元数据（时长、分辨率等） |
| `cleanup_downloads(keep_last_n=10)` | public | 清理旧下载文件 |

#### 调试检测点

| # | 检测点 | 方法 | 预期 |
|---|--------|------|------|
| VS-1 | 素材搜索返回结果 | mock 搜索 | 返回结果列表 |
| VS-2 | 搜索结果格式 | 检查返回值 | 包含 url, title, duration 字段 |
| VS-3 | 下载目录创建 | 检查文件系统 | downloads/ 存在 |
| VS-4 | 下载超时处理 | 无效 URL | 超时抛出异常被捕获 |

#### 测试方案

| 测试项 | 输入 | 操作 |
|--------|------|------|
| T1 搜索函数 | topic="AI agent" | 返回 5 条结果 |
| T2 下载失败 | 无效 URL | 异常处理正常 |
| T3 音频提取 | mock 视频文件 | .wav 文件生成 |

#### 预期测试结果

```
T1 → [{"url": "...", "title": "...", "duration": 120, "source": "youtube"}, ...]
T2 → 返回 None，记录 warning 日志，不崩溃
T3 → output/audio_xxx.wav 文件存在
```

---

### 文件 7：`module-f/editor.py`

#### 功能说明
FFmpeg 视频剪辑、拼接、合成（Python subprocess）。

#### 函数清单

| 函数 | 类型 | 说明 |
|------|------|------|
| `check_ffmpeg()` | public | 检查 FFmpeg 是否已安装 |
| `concat_clips(clip_paths, output_path)` | public | 拼接多个视频片段 |
| `add_text_overlay(video_path, text, position, output_path)` | public | 添加文字叠加 |
| `compose_final_video(audio_path, video_path, subtitle_path, output_path)` | public | 合成最终视频（音频+视频+字幕） |
| `trim_video(input_path, start, duration, output_path)` | public | 裁剪视频片段 |
| `resize_video(input_path, width, height, output_path)` | public | 调整视频尺寸 |
| `get_video_info(path)` | public | 获取视频编码/时长/分辨率信息 |

#### 调试检测点

| # | 检测点 | 方法 | 预期 |
|---|--------|------|------|
| FF-1 | FFmpeg 可用 | subprocess `ffmpeg -version` | 返回版本信息 |
| FF-2 | FFmpeg 不可用时降级 | 捕获 `FileNotFoundError` | 返回错误信息不崩溃 |
| FF-3 | 拼接成功 | 两个小 mp4 拼接 | 输出视频时长 = 两个之和 |
| FF-4 | 合成完整视频 | audio + video + subtitle | 合成成功 |

#### 测试方案

| 测试项 | 输入 | 操作 |
|--------|------|------|
| T1 FFmpeg 检测 | 系统调用 | 返回版本 |
| T2 片段拼接 | 2 个 5s 片段 | 生成 10s 视频 |
| T3 最终合成 | 音频+视频+字幕 | 合成成功 |
| T4 错误输入 | 不存在文件 | 返回错误 |

#### 预期测试结果

```
T1 → {"available": true, "version": "ffmpeg version 6.x ..."}
T2 → 输出文件存在，时长 10s
T3 → 输出文件存在，包含视频轨+音频轨+字幕轨
T4 → 返回 {"error": "ffmpeg failed", "stderr": "..."}
```

---

### 文件 8：`module-f/tts.py`

#### 功能说明
Edge TTS 语音合成，生成解说音频。

#### 函数清单

| 函数 | 类型 | 说明 |
|------|------|------|
| `synthesize(text, output_path, voice="zh-CN-XiaoxiaoNeural")` | public | 文本 → 语音 |
| `synthesize_long_text(text, output_path, max_chars=3000)` | public | 长文本分片合成后拼接 |
| `list_voices(language="zh-CN")` | public | 列出可用中文语音 |
| `adjust_speed(audio_path, speed, output_path)` | public | 调整语速 |

#### 调试检测点

| # | 检测点 | 方法 | 预期 |
|---|--------|------|------|
| TTS-1 | Edge TTS 可用 | `pip install edge-tts` | 安装成功 |
| TTS-2 | 中文语音合成 | 输入中文文本 | 输出 .mp3 文件 |
| TTS-3 | 长文本分片 | 5000 字文本 | 自动分片合成并拼接 |
| TTS-4 | 语速调节 | 1.2x 速度 | 输出时长 ≈ 原时长 / 1.2 |

#### 测试方案

| 测试项 | 输入 | 操作 |
|--------|------|------|
| T1 短文本合成 | "今日AI资讯简报" | 输出 mp3 |
| T2 长文本合成 | 5000 字脚本 | 输出完整 mp3 |
| T3 语速调节 | 1.5x | 时长减少 ~33% |

#### 预期测试结果

```
T1 → output/tts_xxx.mp3，时长 ≈ 3-5 秒
T2 → output/tts_xxx.mp3，时长 ≈ 3-5 分钟
T3 → output/tts_speed_xxx.mp3，时长为原 2/3 左右
```

---

### 文件 9：`module-f/subtitle.py`

#### 功能说明
Whisper 语音识别生成字幕。

#### 函数清单

| 函数 | 类型 | 说明 |
|------|------|------|
| `transcribe(audio_path, model_size="base")` | public | 语音 → 文本 |
| `generate_srt(segments, output_path)` | public | 生成 .srt 字幕文件 |
| `generate_ass(segments, output_path, style=None)` | public | 生成 .ass 字幕文件（带样式） |
| `align_subtitles(segments, text)` | public | 用参考文本对齐时间戳 |

#### 调试检测点

| # | 检测点 | 方法 | 预期 |
|---|--------|------|------|
| WH-1 | Whisper 可用 | `pip install openai-whisper` | 安装成功 |
| WH-2 | 中文转写 | 中文音频输入 | 返回中文文本 |
| WH-3 | SRT 格式正确 | 检查 SRT 文件 | 符合字幕标准格式 |
| WH-4 | 时间戳对齐 | 检查每个 segment | start < end |

#### 测试方案

| 测试项 | 输入 | 操作 |
|--------|------|------|
| T1 中文语音转写 | TTS 输出音频 | 返回文本 |
| T2 SRT 字幕生成 | segments 列表 | 标准 SRT 文件 |
| T3 ASS 字幕生成 | segments + 样式 | 带样式的 ASS 文件 |

#### 预期测试结果

```
T1 → {"text": "今日AI资讯简报...", "segments": [{"start":0.0, "end":3.5, "text":"..."}]}
T2 → 标准 SRT：序号 + 时间轴 + 文本
T3 → ASS 文件：包含字体/颜色/位置样式
```

---

### 文件 10：`module-f/pipeline.py`

#### 功能说明
视频生成全流程串联：搜索 → 分析 → 脚本 → 配音 → 字幕 → 剪辑 → 合成。

#### 函数清单

| 函数 | 类型 | 说明 |
|------|------|------|
| `generate_video(video_id, video_type, date, pool)` | public | 视频生成主流程 |
| `_step_search_materials(topic)` | private | 步骤1：搜索素材 |
| `_step_analyze_clips(materials)` | private | 步骤2：Gemini 分析片段 |
| `_step_write_script(clips, topic)` | private | 步骤3：DeepSeek 写脚本 |
| `_step_synthesize_tts(script)` | private | 步骤4：TTS 配音 |
| `_step_generate_subtitle(audio_path)` | private | 步骤5：Whisper 字幕 |
| `_step_edit_video(clips, audio_path, subtitle_path)` | private | 步骤6：FFmpeg 剪辑合成 |
| `_update_status(pool, video_id, status, **kwargs)` | private | 更新视频状态到 DB |

#### 完整流程

```
        ┌─────────────┐
        │  start      │
        │  status=    │
        │  processing │
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │ ① 搜素材    │ yt-dlp / YouTube API
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │ ② Gemini    │ 分析视频内容
        │ 分析片段    │ 选出最优片段
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │ ③ DeepSeek  │ 写解说脚本
        │ 写脚本      │ + AI 资讯摘要
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │ ④ Edge TTS  │ 文本→语音合成
        │ 配音        │
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │ ⑤ Whisper   │ 语音→字幕文件
        │ 字幕生成    │
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │ ⑥ FFmpeg    │ 剪辑拼接合成
        │ 剪辑合成    │
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │  finish     │
        │  status=    │
        │  done/failed│
        └─────────────┘
```

#### 调试检测点

| # | 检测点 | 方法 | 预期 |
|---|--------|------|------|
| PL-1 | 全流程串联 | 运行 pipeline | 每一步状态正确 |
| PL-2 | 状态持久化 | 每步更新 videos 表 | `status` 字段正确变化 |
| PL-3 | 步骤失败不阻断 | 步骤3 失败 | 步骤4 仍可运行 |
| PL-4 | 最终输出文件 | pipeline 完成 | output/ 目录有视频 |
| PL-5 | 10-20 分钟耗时 | 计时 | 在预期时间内 |

#### 测试方案

| 测试项 | 输入 | 操作 |
|--------|------|------|
| T1 空数据降级 | 无素材搜索结果 | 返回错误，status=failed |
| T2 Mock 模式 | 所有步骤用 mock | 生成 mock 视频文件 |
| T3 部分失败 | 步骤2 失败 | 跳过步骤2，继续执行 |
| T4 正常流程（全 mock） | 全 mock 数据 | 完整流程通过 |

#### 预期测试结果

```
T1 → videos 表 status=failed, error_msg="No materials found"
T2 → output/mock_video_xxx.mp4 存在
T3 → 继续执行，输出中不包含 Gemini 分析部分
T4 → status=done, output_path="output/video_xxx.mp4", duration_seconds=300-600
```

---

### 文件 11：`module-d/output/`（目录）

#### 功能说明
长图输出目录，存放所有生成的长图 PNG 文件。

#### 文件命名规范
- 长图：`longimage_{briefing_id[:8]}.png`（如 `longimage_b0000001.png`）
- Dry-run HTML：`dry_run_{briefing_id[:8]}.html`

---

### 文件 12：`module-f/output/` 和 `module-f/downloads/`（目录）

#### 功能说明
- `output/`：最终视频 + 中间产物（音频、字幕）
- `downloads/`：下载的原始素材

#### 文件命名规范
- 最终视频：`ai_agent_weekly_{date}.mp4`
- 音频：`tts_{video_id[:8]}.mp3`
- 字幕：`subtitle_{video_id[:8]}.srt`

---

## 三、总文件目录

```
project/
├── module-d/                          # 组员 D：微信发布 + 长图
│   ├── __init__.py                    # 模块初始化
│   ├── main.py                        # FastAPI 应用入口
│   ├── db.py                          # (复用 shared/db.py 或独立)
│   ├── platforms/
│   │   ├── __init__.py
│   │   └── weixin.py                  # 微信模板渲染 + 发布
│   ├── long_image.py                  # 独立长图生成（Playwright 截图）
│   ├── output/                        # 长图输出目录
│   │   └── .gitkeep
│   ├── requirements.txt               # playwright, jinja2（可选）
│   └── Dockerfile                     # 容器构建
│
├── module-f/                          # 组员 D：视频生成
│   ├── __init__.py                    # 模块初始化
│   ├── main.py                        # FastAPI 入口
│   ├── gemini_client.py               # Gemini API 封装
│   ├── video_search.py                # 素材搜索 + 下载（yt-dlp）
│   ├── editor.py                      # FFmpeg 剪辑编辑
│   ├── tts.py                         # Edge TTS 语音合成
│   ├── subtitle.py                    # Whisper 字幕生成
│   ├── pipeline.py                    # 全流程串联
│   ├── output/                        # 视频输出目录
│   │   └── .gitkeep
│   ├── downloads/                     # 素材下载目录
│   │   └── .gitkeep
│   ├── requirements.txt               # edge-tts, openai-whisper, yt-dlp, google-generativeai
│   └── Dockerfile                     # 容器构建（注意 Whisper 模型体积）
│
├── contracts/                         # (组长交付，组员 D 只需 pull)
│   ├── schema.sql                     # Phase 1（不改）
│   ├── schema_v2.sql                  # Phase 2 增量
│   ├── seed_data.sql                  # Phase 1（不改）
│   ├── seed_data_v2.sql               # Phase 2 增量
│   └── api-spec.yaml                  # 接口定义
│
├── shared/                            # (组长交付)
│   ├── db.py                          # 通用 DB 连接
│   └── rag.py                         # RAG 工具函数
│
├── docker-compose.yml                 # 更新版（含 module-d + module-f）
├── nginx.conf                         # 更新版（含 :8006 路由）
└── .env.example                       # 环境变量模板
```

---

## 四、依赖安装清单

### Module D

```bash
pip install fastapi uvicorn asyncpg httpx pydantic
pip install playwright
playwright install chromium
```

### Module F

```bash
pip install fastapi uvicorn asyncpg pydantic httpx
pip install google-generativeai
pip install edge-tts
pip install openai-whisper
pip install yt-dlp
# 系统依赖：FFmpeg（apt install ffmpeg / brew install ffmpeg / choco install ffmpeg）
```

---

## 五、验收汇总

### Module D 验收指令

```bash
# 1. 健康检查
curl http://localhost:8004/health

# 2. 微信发布（dry-run）
curl -X POST http://localhost:8004/publish \
  -H "Content-Type: application/json" \
  -d '{"briefing_id": "b0000001-0000-0000-0000-000000000001", "platforms": ["weixin_oa"], "dry_run": true}'

# 3. 真实发布（mock）
curl -X POST http://localhost:8004/publish \
  -H "Content-Type: application/json" \
  -d '{"briefing_id": "b0000001-0000-0000-0000-000000000001", "platforms": ["weixin_oa"]}'

# 4. 检查输出长图
ls -la module-d/output/
```

### Module F 验收指令

```bash
# 1. 健康检查
curl http://localhost:8006/health

# 2. 触发视频生成
curl -X POST http://localhost:8006/generate \
  -H "Content-Type: application/json" \
  -d '{"type": "ai_agent_weekly", "date": "2026-05-28"}'

# 3. 查询状态
curl http://localhost:8006/status/{video_id}

# 4. 视频列表
curl http://localhost:8006/videos

# 5. 检查输出
ls -la module-f/output/
```

---

## 六、注意事项

1. **不要调别人的 API**。只读写数据库，不知道其他模块的 IP 和端口。
2. **用 seed_data 开发**。本地 PostgreSQL（pgvector 版），数据已包含 3 期简报。
3. **先写死、再配置化**。API Key 放 `.env`，不用硬编码。
4. **dry-run 优先**。Module D 先确认本地 HTML/长图输出正常，再尝试真发。
5. **视频不和文档抢资源**。视频独立触发，建议错开早晚报时间。
6. **版权标注**。视频片尾标注素材来源 + 非商用声明。
7. **每天 commit**。分支命名：`phase2-module-d`。
8. **所有接口必须包含 /health**，返回 `{"status": "ok"}`。
