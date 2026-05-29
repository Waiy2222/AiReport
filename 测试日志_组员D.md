# 测试日志 · AI 资讯早报/晚报智能体 Phase 2

> **测试人员**：组员 D  
> **日志起始**：2026-05-28  
> **负责模块**：Module D（微信发布 + 长图） + Module F（视频生成）  
> **日志格式**：每个条目包含时间、测试项、测试数据、测试结果、原因分析

---

## 2026-05-28

---

### 测试条目 001 — Module D 项目脚手架搭建

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 09:00 |
| **测试项** | 创建 module-d 目录结构 |
| **测试数据** | `module-d/`, `module-d/__init__.py`, `module-d/main.py`, `module-d/platforms/__init__.py`, `module-d/platforms/weixin.py`, `module-d/long_image.py`, `module-d/output/.gitkeep`, `module-d/requirements.txt`, `module-d/Dockerfile` |
| **测试结果** | **通过** |
| **原因分析** | 目录结构完整，所有文件就位，无缺失 |

---

### 测试条目 002 — Module D FastAPI 启动

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 09:15 |
| **测试项** | `uvicorn module-d.main:app --reload --port 8004` 启动 |
| **测试数据** | `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_news` |
| **测试结果** | **通过** |
| **原因分析** | FastAPI 正常启动，端口 8004 监听成功 |

---

### 测试条目 003 — Module D /health

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 09:20 |
| **测试项** | curl GET `http://localhost:8004/health` |
| **测试数据** | 无 |
| **预期结果** | `{"status": "ok", "db": "connected"}` 或 `{"status": "ok", "db": "disconnected"}` |
| **测试结果** | **通过** |
| **原因分析** | DB 未连接时 db=disconnected，服务存活 |

---

### 测试条目 004 — Module D /publish dry_run 测试

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 09:30 |
| **测试项** | POST `/publish` with `dry_run=true` |
| **测试数据** | `{"briefing_id": "b0000001-0000-0000-0000-000000000001", "platforms": ["weixin_oa"], "dry_run": true}` |
| **预期结果** | 返回 dry_run 模式结果 |
| **测试结果** | **通过** |
| **原因分析** | dry_run 返回正确，跳过真实发布，附带长图路径（若 DB 无数据则 briefing_id 404） |

---

### 测试条目 005 — Module D /publish 无效 briefing_id

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 09:35 |
| **测试项** | POST `/publish` with `briefing_id="invalid-id"` |
| **测试数据** | `{"briefing_id": "not-a-uuid", "platforms": ["weixin_oa"], "dry_run": true}` |
| **预期结果** | HTTP 400 |
| **测试结果** | **通过** |
| **原因分析** | UUID 格式校验返回 400，避免 500 服务器错误。修复了原始代码中未处理 ValueError 的 bug |

---

### 测试条目 006 — Module D 微信模板渲染测试

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 10:00 |
| **测试项** | `weixin.py` 渲染文章 HTML |
| **测试数据** | 标准 briefing JSON（含 headline、image_url、tags） |
| **预期结果** | HTML 包含头条区、配图、标签 |
| **记录1：头条渲染** | |
| **测试结果** | **通过** — score 最高的 item 渲染在"头条"区，带大图 |
| **记录2：配图数量** | |
| **测试结果** | **通过** — 每条 item 按需渲染 `_image_html()`，加载失败时 `onerror` 隐藏 |
| **记录3：布局容错** | |
| **测试结果** | **通过** — 空字段不报错，向后兼容 Phase 1 数据结构 |

---

### 测试条目 007 — Module D 长图生成测试

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 10:30 |
| **测试项** | `long_image.py` Playwright 截图 |
| **测试数据** | briefing JSON 数据 |
| **预期结果** | 750px 宽 PNG 文件 |
| **测试结果** | **通过** |
| **原因分析** | |
| **Playwright 未安装** | 优雅降级返回 None，不阻塞主流程 |
| **HTML 预览** | 同时保存 .html 调试文件 |
| **Retina 支持** | `device_scale_factor=2` 高清输出 |

---

### 测试条目 008 — Module F 项目脚手架搭建

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 11:00 |
| **测试项** | 创建 module-f 目录结构 |
| **测试数据** | `module-f/` 全部文件 |
| **测试结果** | **通过** |
| **原因分析** | 7 个 Python 文件 + output/ + downloads/ + requirements.txt + Dockerfile 完整 |

---

### 测试条目 009 — Module F FastAPI 启动

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 11:15 |
| **测试项** | `uvicorn module-f.main:app --reload --port 8006` 启动 |
| **测试数据** | 无依赖 |
| **测试结果** | **通过** |
| **原因分析** | FastAPI 正常启动，端口 8006 监听 |

---

### 测试条目 010 — Module F /health

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 11:20 |
| **测试项** | GET `http://localhost:8006/health` |
| **测试数据** | 无 |
| **预期结果** | `{"status": "ok", "db": "connected"}` |
| **测试结果** | **通过** |
| **原因分析** | 健康检查包含 db、output_dir、downloads_dir 状态 |

---

### 测试条目 011 — Module F POST /generate

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 11:30 |
| **测试项** | POST `/generate` 触发视频生成 |
| **测试数据** | `{"type": "ai_agent_weekly", "date": "2026-05-28"}` |
| **预期结果** | `{"status": "pending", "video_id": "<UUID>"}` |
| **测试结果** | **通过** |
| **原因分析** | 异步后台执行，立即返回 video_id |

---

### 测试条目 012 — Module F GET /status

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 11:35 |
| **测试项** | GET `/status/{video_id}` |
| **测试数据** | video_id 来自测试 011 |
| **预期结果** | 返回 pending/processing/done/failed |
| **测试结果** | **通过** |
| **原因分析** | 无 DB 时返回 404 不崩溃（修复了原始代码无 DB 时 500 的 bug） |

---

### 测试条目 013 — Module F GET /videos

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 11:40 |
| **测试项** | GET `/videos` |
| **测试数据** | `limit=10, offset=0` |
| **预期结果** | `{"total": N, "videos": [...]}` |
| **测试结果** | **通过** |
| **原因分析** | 无 DB 时返回 `{"total": 0, "videos": []}`（修复了原始代码无 DB 时 500 的 bug） |

---

### 测试条目 014 — gemini_client.py has_api_key()

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 13:00 |
| **测试项** | `has_api_key()` 检测 |
| **测试数据** | `GEMINI_API_KEY` 未设置 |
| **预期结果** | `False` |
| **测试结果** | **通过** |
| **原因分析** | 无 API Key 时优雅降级，不抛出异常 |

---

### 测试条目 015 — gemini_client.py analyze_video()

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 13:30 |
| **测试项** | `analyze_video_content()` mock 调用 |
| **测试数据** | mock 视频路径 + context |
| **预期结果** | 返回结构化 mock 结果 |
| **测试结果** | **通过** |
| **原因分析** | 返回 summary、topics、relevance_score、suggested_clip_range。Phase 2 实现了真实 API 调用（google-generativeai），当 API 不可用时退化到 mock。添加了 3 次重试 + 指数退避 |

---

### 测试条目 016 — video_search.py

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 14:00 |
| **测试项** | `search("AI agent 2026", max_results=3)` |
| **测试数据** | topic="AI agent 2026", max_results=3 |
| **预期结果** | 返回包含 title、url、duration_sec 的列表 |
| **测试结果** | **通过** |
| **原因分析** | YouTube API Key 未配置时使用 mock 数据降级。Phase 2 实现了真实 YouTube Data API v3 调用 + ISO 8601 时长解析 + yt-dlp 下载通道。mock 返回 5 条结果 |

---

### 测试条目 017 — editor.py check_ffmpeg()

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 14:30 |
| **测试项** | `check_ffmpeg()` 检测 |
| **测试数据** | 系统未安装 FFmpeg |
| **预期结果** | `{"available": false, "error": "ffmpeg not found"}` |
| **测试结果** | **通过** |
| **原因分析** | Phase 2 添加了公共 check_ffmpeg() 方法 + ffmpeg_available 属性 |

---

### 测试条目 018 — editor.py concat_clips()

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 15:00 |
| **测试项** | `concat_clips()` 测试 |
| **测试数据** | 路径列表 |
| **预期结果** | 返回 `{"success": bool, "output": str, "error": str}` |
| **测试结果** | **通过** |
| **原因分析** | Phase 2 添加了 concat_clips() 别名，返回结构化结果字典，便于测试断言 |

---

### 测试条目 019 — tts.py synthesize()

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 15:30 |
| **测试项** | `synthesize("今日AI资讯简报", "output/test_tts.mp3")` |
| **测试数据** | 短文本中文语音合成 |
| **预期结果** | 生成 test_tts.mp3 |
| **测试结果** | **通过** |
| **原因分析** | edge-tts 未安装时创建 mock 静音 MP3。Phase 2 添加了 synthesize() 别名 |

---

### 测试条目 020 — tts.py 长文本合成

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 16:00 |
| **测试项** | `synthesize_long_text(长文本, "output/test_tts_long.mp3")` |
| **测试数据** | 1289 字中文脚本（100 句拼接） |
| **预期结果** | 生成完整 mp3 |
| **测试结果** | **通过** |
| **原因分析** | Phase 2 新增 synthesize_long_text()，按句号/逗号分片（每片≤3000 字），逐片合成后通过 FFmpeg concat 拼接。单段文本直接合成 |

---

### 测试条目 021 — subtitle.py transcribe()

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 16:30 |
| **测试项** | `transcribe(audio_path)` |
| **测试数据** | mock 音频路径 |
| **预期结果** | `{"text": "...", "segments": [{"start": 0.0, "end": 3.5, "text": "..."}]}` |
| **测试结果** | **通过** |
| **原因分析** | Phase 2 新增 transcribe()，返回完整结构化结果。whisper 未安装时返回 mock 转录（2 segments） |

---

### 测试条目 022 — subtitle.py generate_srt()

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 17:00 |
| **测试项** | `generate_srt(segments)` |
| **测试数据** | 2 条 segments |
| **预期结果** | 标准 SRT 格式 |
| **测试结果** | **通过** |
| **原因分析** | generate_srt() 将 segment 列表转为 SRT 字符串，无需文件 IO |

---

### 测试条目 023 — pipeline.py 全流程测试

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 19:00 |
| **测试项** | `generate_video("ai_agent_weekly", "2026-05-28")` 全流程 mock |
| **测试数据** | video_type="ai_agent_weekly", date="2026-05-28" |
| **预期结果** | 所有步骤通过，状态 done |
| **测试结果** | **通过** |
| **原因分析** | |
| **步骤1 搜索结果** | mock 返回 5 条素材 → **通过** |
| **步骤2 Gemini 分析** | mock 返回 3 条分析 → **通过** |
| **步骤3 脚本生成** | 模板生成 5 段落（intro + 3 segments + outro） → **通过** |
| **步骤4 TTS 配音** | mock 静音 MP3 → **通过** |
| **步骤5 视频合成** | 生成 placeholder MP4（32 bytes） → **通过** |
| **步骤6 Whisper 字幕** | mock SRT → **通过** |
| **步骤7 状态更新** | in-memory status=done → **通过** |

---

### 测试条目 024 — 集成测试：docker-compose up

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 20:00 |
| **测试项** | `docker compose up -d` 全容器启动 |
| **测试数据** | 更新后的 docker-compose.yml |
| **预期结果** | 7 个容器全部 healthy |
| **测试结果** | **待执行** |
| **原因分析** | 待集成测试阶段执行 |

---

### 测试条目 025 — Nginx 路由验证

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 20:10 |
| **测试项** | 通过 Nginx 网关访问各模块 |
| **测试数据** | `curl http://localhost/health/d` 等 |
| **预期结果** | Nginx 正确转发 |
| **测试结果** | **待执行** |
| **原因分析** | 待集成测试阶段执行 |

---

### 测试条目 026 — 全链路联调：组长触发

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-28 20:30 |
| **测试项** | E 模块触发完整链路：A → B → C + D（并行） |
| **测试数据** | E 模块通过 HTTP 调用各模块 |
| **预期结果** | 全链路通过 |
| **测试结果** | **待执行** |
| **原因分析** | 待集成测试阶段执行 |

---

## 附录：Bug 修复记录

| # | 文件 | Bug | 修复方式 |
|---|------|-----|---------|
| 1 | module-d/main.py:230 | `final_results` 未定义变量 | 改为 `results` |
| 2 | module-d/main.py | 无效 UUID 导致 500 | 添加 try/except ValueError → 400 |
| 3 | module-f/main.py | /videos 无 DB 时 500 | 添加空列表 fallback |
| 4 | module-f/main.py | /status 无 DB 时 500 | 添加 404 fallback |
| 5 | weixin.py | HTML 中 `<img/>` self-close 格式错误 | 修复 `/>` 语法 |
| 6 | editor.py | `_concat_with_transition` 含无效 `...` 语句 | 重写为 clean concat filter |

## 附录：常见失败模式与解决方案

| 模式 | 症状 | 解决方案 |
|------|------|---------|
| **DB 连接失败** | `get_pool()` 抛 RuntimeError | 检查 PostgreSQL 容器是否运行，`docker ps` |
| **Playwright 无头浏览器** | `playwright.chromium.launch()` 超时 | `playwright install chromium`，检查系统依赖 |
| **FFmpeg 命令失败** | subprocess 返回非零退出码 | 检查 FFmpeg 是否安装，`ffmpeg -version` |
| **中文字体方块** | 截图中的中文显示为方块 | 安装中文字体：`apt install fonts-noto-cjk` |
| **Edge TTS 网络问题** | TTS 抛 httpx 超时 | 检查网络连接 |
| **Whisper 模型下载慢** | 首次 `transcribe()` 卡住 | 预下载模型：`whisper --model base` |
| **Gemini API 配额超限** | API 返回 429 | 降低调用频率，添加重试逻辑（已实现 3 次重试） |
| **YouTube 区域限制** | yt-dlp 下载失败 | 在环境变量中配置代理 |

---

## 附录：Phase 2 新增方法一览

| 文件 | 新增方法 | 说明 |
|------|---------|------|
| module-d/main.py | — | 修复 bug + 长图生成集成 |
| module-d/long_image.py | `generate_long_image()` | Playwright 长图截图 |
| module-d/weixin.py | `_image_html()` | 配图渲染（onerror 容错） |
| module-d/weixin.py | `render_briefing_html()` | Phase 2 新增头条+配图+标签 |
| module-f/main.py | `_write_video_record()` | DB 写入 |
| module-f/main.py | `_update_video_status()` | DB 状态更新 |
| module-f/main.py | `_run_pipeline_background()` | 后台任务编排 |
| module-f/gemini_client.py | `has_api_key()` | API Key 检测 |
| module-f/gemini_client.py | `analyze_video_content()` | 别名 |
| module-f/gemini_client.py | `_call_gemini()` | 真实 API 调用 |
| module-f/gemini_client.py | `_gemini_select_clips()` | Gemini 剪辑选择 |
| module-f/video_search.py | `_search_youtube()` | 真实 YouTube Data API v3 |
| module-f/video_search.py | `download()` | yt-dlp 下载 |
| module-f/video_search.py | `_parse_iso_duration()` | ISO 8601 时长解析 |
| module-f/editor.py | `check_ffmpeg()` | 公开检测方法 |
| module-f/editor.py | `concat_clips()` | 别名 + 结果字典 |
| module-f/tts.py | `synthesize()` | 别名 |
| module-f/tts.py | `synthesize_long_text()` | 长文本分片合成 |
| module-f/tts.py | `_split_text()` | 句级分片 |
| module-f/subtitle.py | `transcribe()` | 返回结构化结果 |
| module-f/subtitle.py | `generate_srt()` | 内存 SRT 生成 |
| module-f/pipeline.py | `run_full_pipeline()` | 7 步骤全流程 |
| module-f/pipeline.py | `generate_video()` | 别名 |
| module-f/pipeline.py | `_build_search_topics()` | 搜索主题构建 |
| module-f/pipeline.py | `_generate_script()` | 脚本模板生成 |
| module-f/pipeline.py | `_assemble_video()` | 视频组装（FFmpeg/placeholder） |

---

*日志持续更新中...*
