# 队员 D 专属任务计划书 — 多平台发布模块

> 模块端口：`8004` | 数据库表：`briefings`(读) + `publish_log`(写) | 分支名：`module-d`

---

## 一、代码文件清单

---

### 文件 1：`module-d/main.py`（修改）

**操作**：修改现有骨架，填充发布流水线

**现有内容（不动）**：
- `/health` 端点
- `startup/shutdown` 事件
- `PublishRequest` 模型
- `PLATFORMS` 常量

**需要修改的部分**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `health()` | 无 | `dict` | 不动 |
| `publish(req)` | `req: PublishRequest` | `dict` | 验证简报存在 → 调用 orchestrator 并发发布 → 返回各平台结果 |
| `_publish_to(...)` | `pool, briefing_id, platform` | `dict` | 替换为真正的发布逻辑 |

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-`/health` 正常 | `curl http://localhost:8004/health` | `{"status":"ok","db":"connected"}` |
| D2-`/publish` 接收正确参数 | `curl -X POST ... -d '{"briefing_id":"valid-uuid","platforms":["zhihu"]}'` | 返回各平台结果数组 |
| D3-简报不存在返回 404 | 传入不存在的 briefing_id | HTTP 404, `{"detail":"briefing not found"}` |
| D4-非法 platform 返回 400 | `platforms: ["unsupported"]` | HTTP 400 |
| D5-无 DB 时 `/health` | 关掉 PostgreSQL 后访问 | `{"status":"ok","db":"disconnected"}` |
| D6-空 platforms 使用默认值 | `{"briefing_id":"...","platforms":[]}` | 使用 `["zhihu","csdn","weixin_oa"]` |

**测试方案**：

```bash
# 1. 健康检查
curl -s http://localhost:8004/health | python -m json.tool

# 2. 发布请求（使用 seed_data 中的简报 ID）
BRIEFING_ID="b0000001-0000-0000-0000-000000000001"
curl -s -X POST http://localhost:8004/publish \
  -H "Content-Type: application/json" \
  -d "{\"briefing_id\": \"$BRIEFING_ID\", \"platforms\": [\"zhihu\", \"csdn\", \"weixin_oa\"]}" | python -m json.tool

# 3. 404 测试
curl -s -X POST http://localhost:8004/publish \
  -H "Content-Type: application/json" \
  -d '{"briefing_id": "00000000-0000-0000-0000-000000000000", "platforms": ["zhihu"]}' | python -m json.tool

# 4. 非法 platform
curl -s -X POST http://localhost:8004/publish \
  -H "Content-Type: application/json" \
  -d '{"briefing_id": "b0000001-0000-0000-0000-000000000001", "platforms": ["unknown"]}' | python -m json.tool

# 5. 验证 publish_log 写入
PGPASSWORD=postgres psql -h localhost -U postgres -d ai_news \
  -c "SELECT platform, status, created_at FROM publish_log ORDER BY created_at DESC LIMIT 10;"
```

**预期测试结果**：

```json
// /health
{"status": "ok", "db": "connected"}

// /publish — 正常
{
  "briefing_id": "b0000001-...-000000000001",
  "results": [
    {"platform": "zhihu", "status": "pending", "url": null, "error": null},
    {"platform": "csdn", "status": "pending", "url": null, "error": null},
    {"platform": "weixin_oa", "status": "pending", "url": null, "error": null}
  ]
}

// 404
{"detail": "briefing not found"}

// 400 — 非法 platform
{"detail": "unsupported platform: unknown"}
```

---

### 文件 2：`module-d/content.py`（新建）

**操作**：新建 — 从 briefings 表拆解出标题、导语、正文

**背景**：briefings 表 `sections` 字段为 JSONB 结构：
```json
[
  {
    "title": "大模型开源动态",
    "items": [
      {"title": "Meta开源Llama-4-R1", "summary": "...", "score": 9.5, "url": "...", "source": "github", "tags": ["LLM","开源","推理"]}
    ]
  }
]
```

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `extract_title(briefing)` | `briefing: dict` | `str` | 根据 type+date 生成标题（如"AI 资讯早报 2026-05-24"） |
| `extract_intro(briefing)` | `briefing: dict` | `str` | 从 tl_dr 取前 3 条作为导语 |
| `extract_body(briefing, max_items)` | `briefing: dict, max_items=15` | `list[dict]` | 从 sections 展开所有 items，按 score 降序截取 |
| `format_markdown(briefing)` | `briefing: dict` | `str` | 生成 Markdown 全文（用于知乎/CSDN） |
| `format_html(briefing)` | `briefing: dict` | `str` | 生成 HTML 全文（用于微信公众号） |
| `get_briefing(pool, briefing_id)` | `pool, briefing_id: UUID` | `dict \| None` | 从 DB 读取完整简报数据 |

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-标题生成 | `extract_title({"type":"morning","date":"2026-05-24"})` | `"AI资讯早报 2026-05-24"` |
| D2-导语提取 | 传入 seed_data 中的简报 | 返回 tl_dr 前 3 条字符串列表 |
| D3-正文展开 | 传入完整 briefing 数据 | 展开 sections→items，结果按 score 降序 |
| D4-Markdown 格式 | `format_markdown(seed_data_briefing)` | 含 `# 标题`、`## 分类`、`- [标题](url)` 等 |
| D5-HTML 格式 | `format_html(seed_data_briefing)` | 含 `<h1>`、`<h2>`、`<ul>` 等标签 |
| D6-空数据处理 | 传入空的 sections | 返回空列表，不抛异常 |
| D7-分数排序正确 | 构造乱序 items | 按 score 从高到低排列 |
| D8-数据库读取 | 传入 DB 中存在的 briefing_id | 返回完整 dict 包含所有字段 |

**测试方案**：

```bash
cd module-d
python -c "
from content import extract_title, extract_intro, extract_body, format_markdown

# D1: 标题生成
title = extract_title({'type': 'morning', 'date': '2026-05-24'})
print(f'[D1] Title: {title}')
assert '早报' in title, f'D1 FAIL: {title}'

# D2-D3: 用 seed_data 的假数据测试
import json
sample_briefing = {
    'id': 'b0000001-0000-0000-0000-000000000001',
    'type': 'morning',
    'date': '2026-05-24',
    'tl_dr': json.loads('[\"DeepSeek-V4技术报告引发关注\",\"Meta开源Llama-4-R1\",\"Anthropic发布Claude Opus 4.7\"]'),
    'sections': json.loads('[{\"title\":\"大模型开源动态\",\"items\":[{\"title\":\"Meta开源Llama-4-R1\",\"summary\":\"Meta发布Llama-4-R1...\",\"score\":9.5,\"url\":\"https://github.com/meta-llama/llama4\",\"tags\":[\"LLM\",\"开源\"]}]},{\"title\":\"Agent框架\",\"items\":[{\"title\":\"CrewAI v1.0\",\"summary\":\"CrewAI v1.0发布...\",\"score\":8.0,\"url\":\"https://github.com/crewAIInc/crewAI\",\"tags\":[\"Agent\"]}]}]'),
    'key_takeaways': json.loads('[\"开源模型与闭源差距缩小\"]'),
}

intro = extract_intro(sample_briefing)
print(f'[D2] Extracted {len(intro)} intro items')

body = extract_body(sample_briefing)
print(f'[D3] Body items: {len(body)}')

md = format_markdown(sample_briefing)
print(f'[D4] Markdown length: {len(md)} chars')
print(md[:500])
"
```

**预期测试结果**：
- D1: 标题含"早报"或"晚报"
- D2: 3 条导语
- D3: items 按 score 降序排列
- D4: Markdown 含标题、分类、列表

---

### 文件 3：`module-d/renderer.py`（新建）

**操作**：新建 — HTML 模板渲染（给微信公众号使用）

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `render_article(briefing)` | `briefing: dict` | `str` | 渲染完整微信公众号文章 HTML |
| `_render_header(type, date)` | `type: str, date: str` | `str` | 渲染头部：标题 + 日期 + 导语 |
| `_render_section(section)` | `section: dict` | `str` | 渲染单个分类区块 |
| `_render_item(item)` | `item: dict` | `str` | 渲染单条资讯卡片 |
| `_render_footer(key_takeaways)` | `key_takeaways: list` | `str` | 渲染底部总结 |

**模板风格**：
- 移动端适配（微信内嵌浏览器）
- 卡片式布局
- 标签用圆角彩色 badge
- 关键数据（score）用醒目颜色
- 深色模式兼容（CSS prefers-color-scheme）

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-整体渲染无异常 | `render_article(seed_data_briefing)` | 返回合法 HTML 字符串 |
| D2-标题正确 | 检查 `<h1>` 内容 | 包含"AI 资讯"字样 |
| D3-分类区块 | 检查 `<h2>` 数量 | 等于 sections 数量 |
| D4-卡片布局 | 检查 `.card` 或类似 class | 每个 item 有独立容器 |
| D5-标签渲染 | 检查 `badge` 或标签元素 | 标签以彩色圆角样式渲染 |
| D6-空数据渲染 | 空 sections | 返回最小 HTML，不抛异常 |
| D7-H5 兼容检查 | 检查 viewport meta | `<meta name="viewport" content="width=device-width">` |
| D8-深色模式 | 检查 CSS media query | 有 `prefers-color-scheme: dark` 样式 |

**测试方案**：

```bash
cd module-d
python -c "
from renderer import render_article, _render_header, _render_section, _render_item, _render_footer
import json

sample_briefing = {
    'type': 'morning',
    'date': '2026-05-24',
    'tl_dr': json.loads('[\"要点1\",\"要点2\",\"要点3\"]'),
    'sections': json.loads('[{\"title\":\"大模型开源动态\",\"items\":[{\"title\":\"Meta开源Llama-4-R1\",\"summary\":\"Meta发布Llama-4-R1...\",\"score\":9.5,\"url\":\"https://github.com/meta-llama/llama4\",\"source\":\"github\",\"tags\":[\"LLM\",\"开源\",\"推理\"]}]},{\"title\":\"Agent框架\",\"items\":[{\"title\":\"CrewAI v1.0\",\"summary\":\"CrewAI v1.0正式发布...\",\"score\":8.0,\"url\":\"https://github.com/crewAIInc/crewAI\",\"source\":\"github\",\"tags\":[\"Agent\",\"框架\",\"开源\"]}]}]'),
    'key_takeaways': json.loads('[\"开源模型与闭源差距缩小至0.3%\"]'),
}

html = render_article(sample_briefing)

# 写入文件用浏览器查看
with open('/tmp/test_article.html', 'w', encoding='utf-8') as f:
    f.write(html)
print(f'[D1] HTML length: {len(html)} chars')
print(f'[D2] Has h1: {chr(60).__add__(\"h1\") in html}')  # <h1
print(f'[D3] Section count: {html.count(chr(60).__add__(\"h2\"))}')
print(f'[D4] Has card class: {\"card\" in html.lower() or \"item\" in html.lower()}')
print(f'[D5] Viewport: {\"viewport\" in html}')
print(f'[D6] Dark mode: {\"prefers-color-scheme\" in html}')

# 保存到文件查看
with open('test_output.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('HTML saved to test_output.html')
"
```

**预期测试结果**：
- D1: HTML 长度 > 500 chars
- D2: 含 `<h1>` 标签
- D3: `<h2>` 数量 = sections 数
- D4: 含卡片 class
- D5: 含 viewport meta
- D6: 含深色模式 CSS

---

### 文件 4：`module-d/platforms/__init__.py`（新建）

**操作**：新建 — 空文件，标记 platforms 为 Python 包

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-包导入 | `python -c "from platforms import weixin_oa"` | 不报 ImportError |

**测试方案**：

```bash
cd module-d
touch platforms/__init__.py
python -c "import platforms; print('ok')"
```

**预期测试结果**：输出 `ok`。

---

### 文件 5：`module-d/platforms/weixin_oa.py`（新建）

**操作**：新建 — 微信公众号发布

**数据源**：微信公众号素材管理 API + 发布能力 API

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_access_token(appid, secret)` | `appid, secret: str` | `str \| None` | 获取微信全局 access_token |
| `upload_image(token, file_path)` | `token: str, file_path: str` | `str \| None` | 上传封面图到微信素材库 |
| `create_draft(token, content, title)` | `token, content, title: str` | `str \| None` | 创建草稿，返回 media_id |
| `publish_draft(token, media_id)` | `token, media_id: str` | `str \| None` | 发布草稿，返回 msg_id |
| `publish(pool, briefing_id, briefing)` | `pool, briefing_id: UUID, briefing: dict` | `dict` | **主函数**：串行完成 get_token → upload → draft → publish |
| `dry_run(briefing)` | `briefing: dict` | `str` | 只生成 HTML，不调用任何 API，返回 HTML 字符串 |

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-dry_run 返回 HTML | `dry_run(seed_data_briefing)` | 返回含 `<!DOCTYPE html>` 的字符串 |
| D2-dry_run 不调外部 API | 无网络环境下调用 dry_run | 正常运行，不抛 ConnectionError |
| D3-access_token 获取 | 使用测试公众号凭据 | 返回 token 字符串（或 mock） |
| D4-图片上传 | 验证图片文件存在 | 返回 media_id（或 mock） |
| D5-草稿创建 | 验证发布的 content | media_id 有效 |
| D6-发布结果写入 DB | 成功后在 publish_log 查询 | status='success', platform_url 有值 |
| D7-发布失败写入 DB | 模拟 API 错误 | status='failed', error_msg 有值 |
| D8-凭据为空跳过 | 环境变量未配置时 | 返回 `{"status":"failed","error":"missing credentials"}` |

**测试方案**（dry-run 模式优先）：

```bash
cd module-d
python -c "
from platforms.weixin_oa import dry_run
import json, asyncio

# 从 DB 读取一份简报做 dry-run
async def test():
    from db import init_db, get_pool, close_db
    await init_db()
    pool = get_pool()
    row = await pool.fetchrow('SELECT * FROM briefings LIMIT 1')
    if row:
        briefing = dict(row)
        html = dry_run(briefing)
        print(f'[D1] HTML generated: {len(html)} chars')
        print(f'[D1] DOCTYPE: {html[:50]}...')
        with open('weixin_dry_run.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print('Dry-run HTML saved to weixin_dry_run.html')
    else:
        print('No briefing found in DB, run seed_data.sql first')
    await close_db()

asyncio.run(test())
"
```

**预期测试结果**：
- dry_run 返回完整 HTML 文档
- HTML 开头为 `<!DOCTYPE html>` 或 `<html>`
- 文件保存后可本地浏览器打开预览

---

### 文件 6：`module-d/platforms/zhihu.py`（新建）

**操作**：新建 — 知乎专栏/文章发布

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_token(client_id, secret)` | `client_id, secret: str` | `str \| None` | 获取知乎 access_token |
| `publish_article(token, title, content)` | `token, title, content: str` | `str \| None` | 发布知乎文章，返回 article_id |
| `publish(pool, briefing_id, briefing)` | `pool, briefing_id: UUID, briefing: dict` | `dict` | **主函数** |
| `dry_run(briefing)` | `briefing: dict` | `str` | 只生成 Markdown，不调 API |

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-dry_run 返回 Markdown | `dry_run(seed_data_briefing)` | 返回 Markdown 字符串 |
| D2-知乎格式适配 | 检查 Markdown 语法 | 使用知乎支持的 Markdown 子集 |
| D3-凭据为空跳过 | 环境变量未配置 | 返回 `{"status":"failed","error":"missing"}` |
| D4-发布结果写入 DB | 发布后查 publish_log | 记录 status + platform_url |

**测试方案**：

```bash
cd module-d
python -c "
from platforms.zhihu import dry_run
import json

sample = {
    'type': 'morning',
    'date': '2026-05-24',
    'tl_dr': ['DeepSeek-V4技术报告', 'Meta开源Llama-4-R1'],
    'sections': [
        {'title': '大模型动态', 'items': [
            {'title': 'Meta Llama-4-R1', 'summary': '推理增强模型', 'score': 9.5, 'url': 'https://github.com/meta-llama/llama4', 'tags': ['LLM']}
        ]}
    ],
    'key_takeaways': ['开源模型进步'],
}

md = dry_run(sample)
print(f'[D1] Markdown length: {len(md)} chars')
print('---MARKDOWN---')
print(md[:800])
print('---END---')

# 说明：知乎 Markdown 应避免复杂表格/HTML，使用纯 Markdown 语法
assert '#' in md, '[D2] No title found'
assert '[' in md, '[D2] No links found'
print('[D2] Contains Markdown title and links')
"
```

**预期测试结果**：
- D1: 返回 Markdown 字符串
- D2: 含 `#` 标题、`-` 列表、`[text](url)` 链接

---

### 文件 7：`module-d/platforms/csdn.py`（新建）

**操作**：新建 — CSDN 文章发布

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `publish_article(token, title, content)` | `token, title, content: str` | `str \| None` | 发布 CSDN 文章，返回 article_id |
| `publish(pool, briefing_id, briefing)` | `pool, briefing_id: UUID, briefing: dict` | `dict` | **主函数** |
| `dry_run(briefing)` | `briefing: dict` | `str` | 只生成 Markdown，不调 API |

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-dry_run 返回 Markdown | `dry_run(seed_data_briefing)` | 返回 Markdown 字符串 |
| D2-CSDN 格式适配 | 检查 Markdown 格式 | 使用 CSDN 支持的 Markdown（支持代码块/表格） |
| D3-凭据为空跳过 | 环境变量未配置 | 返回 `{"status":"failed","error":"missing"}` |
| D4-发布结果写入 DB | 发布后查 publish_log | 记录 status + platform_url + error_msg |

**测试方案**：

```bash
cd module-d
python -c "
from platforms.csdn import dry_run
import json

sample = {
    'type': 'morning',
    'date': '2026-05-24',
    'tl_dr': ['DeepSeek-V4技术报告', 'Meta开源Llama-4-R1'],
    'sections': [
        {'title': '大模型动态', 'items': [
            {'title': 'Meta Llama-4-R1', 'summary': '推理增强模型', 'score': 9.5, 'url': 'https://github.com/meta-llama/llama4', 'tags': ['LLM']}
        ]}
    ],
    'key_takeaways': ['开源模型进步'],
}

md = dry_run(sample)
print(f'[D1] Markdown length: {len(md)} chars')
print('---MARKDOWN---')
print(md[:800])
print('---END---')
"
```

**预期测试结果**：
- D1: 返回 Markdown 字符串
- 含 CSDN 兼容的 Markdown 语法

---

### 文件 8：`module-d/orchestrator.py`（新建）

**操作**：新建 — 多平台并发发布 + 失败隔离

**功能函数**：

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `publish_all(pool, briefing_id, briefing, platforms)` | `pool, briefing_id: UUID, briefing: dict, platforms: list[str]` | `list[dict]` | 并发执行各平台发布，单平台失败不影响其他 |
| `_publish_one(pool, briefing_id, briefing, platform)` | ... | `dict` | 调用对应平台的 `publish()`，超时/异常保护 |
| `write_log(pool, briefing_id, platform, status, url, error)` | ... | `None` | 写 publish_log 表 |

**并发控制**：
- 使用 `asyncio.gather` 并发发布
- 每个平台设 60s 超时（`asyncio.wait_for`）
- 单平台失败只影响该平台状态，不影响其他平台

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-并发执行 | 3 个平台同时发布 | 总耗时 ≈ 最慢平台耗时 |
| D2-单平台失败隔离 | 模拟 CSDN 抛异常 | zhihu 和 weixin_oa 正常返回，CSDN 标记 failed |
| D3-发布日志写入 | 发布后查 publish_log | 每个平台一条记录 |
| D4-空平台列表 | `platforms=[]` | 返回空 results 列表 |
| D5-重复发布 | 对同一简报重复发布 | 正确写入多条记录（每次独立） |
| D6-超时保护 | 模拟某平台耗时 120s | 超时后标记 failed，不阻塞其他 |

**测试方案**：

```bash
cd module-d
python -c "
import asyncio
from orchestrator import publish_all, write_log

async def test():
    from db import init_db, get_pool, close_db
    await init_db()
    pool = get_pool()
    briefing_id = 'b0000001-0000-0000-0000-000000000001'
    briefing = {'type': 'morning'}  # mock

    # D1-D2: 并发发布
    results = await publish_all(pool, briefing_id, briefing, ['zhihu', 'csdn', 'weixin_oa'])
    print(f'[D1] Results: {len(results)} platforms')
    for r in results:
        print(f'  [{r[\"platform\"]}] {r[\"status\"]}')

    # D3: 检查 publish_log
    rows = await pool.fetch(
        'SELECT platform, status FROM publish_log WHERE briefing_id=$1 ORDER BY created_at',
        briefing_id
    )
    print(f'[D3] Publish log entries: {len(rows)}')

    await close_db()

asyncio.run(test())
"
```

**预期测试结果**：
- D1: 返回 3 条结果
- D2: 各平台独立状态
- D3: publish_log 有对应记录

---

### 文件 9：`module-d/requirements.txt`（修改）

**操作**：修改 — 增加微信发布等依赖

**现有依赖**：
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
asyncpg==0.30.0
httpx==0.28.1
pydantic==2.10.4
```

**新增依赖**：
```
# 微信公众号发布所需（图片处理、二维码）
Pillow==11.1.0
qrcode==7.4.2
```

**调试检测点**：

| 检测点 | 验证方法 | 预期结果 |
|--------|----------|----------|
| D1-全部安装成功 | `pip install -r requirements.txt` | 无报错 |

**测试方案**：
```bash
cd module-d
pip install -r requirements.txt
python -c "import fastapi, asyncpg, httpx, PIL; print('all ok')"
```

**预期测试结果**：输出 `all ok`。

---

## 二、总文件目录

```
project/
│
├── contracts/                          # [组长维护，队员只读]
│   ├── schema.sql                      # 数据库建表 DDL（5 张表）
│   ├── seed_data.sql                   # 假数据（briefings 有 3 期，publish_log 有 5 条）
│   └── api-spec.yaml                   # 接口契约
│
├── module-a/                           # [队员 A 负责] 资讯抓取
├── module-b/                           # [队员 B 负责] AI 内容加工
├── module-c/                           # [队员 C 负责] 微信小程序
├── module-d/                           # ★ 队员 D 工作区
│   ├── main.py                         # [修改] /health + /publish 入口
│   ├── db.py                           # [不动] PostgreSQL 连接池
│   ├── content.py                      # [新建] 简报拆解（标题/导语/正文/MD/HTML）
│   ├── renderer.py                     # [新建] HTML 模板渲染（公众号文章）
│   ├── orchestrator.py                 # [新建] 多平台并发发布 + 失败隔离
│   ├── requirements.txt                # [修改] 增加 Pillow/qrcode
│   ├── Dockerfile                      # [不动] 容器化
│   │
│   └── platforms/                      # [新建目录]
│       ├── __init__.py                 # [新建] 空文件
│       ├── weixin_oa.py                # [新建] 微信公众号发布（含 dry_run）
│       ├── zhihu.py                    # [新建] 知乎发布（含 dry_run）
│       └── csdn.py                     # [新建] CSDN 发布（含 dry_run）
│
├── module-e/                           # [组长负责] 调度 + Dashboard
│
├── docker-compose.yml                  # [组长维护] 7 容器编排
├── nginx.conf                          # [组长维护] 网关路由
└── .env.example                        # [组长维护] 环境变量模板
```

---

## 三、队员 D 开发顺序建议

```
Step 1: platforms/__init__.py       (1 分钟)
Step 2: content.py                  (2-3 小时，核心逻辑：拆解简报为各格式)
Step 3: renderer.py                 (2-3 小时，HTML 模板设计 + CSS)
Step 4: platforms/weixin_oa.py      (3-4 小时，微信公众号发布，先做 dry_run)
Step 5: platforms/zhihu.py          (1-2 小时，知乎发布，先做 dry_run)
Step 6: platforms/csdn.py           (1-2 小时，CSDN 发布，先做 dry_run)
Step 7: orchestrator.py             (1-2 小时，并发发布 + publish_log 写入)
Step 8: main.py 集成                 (1 小时，替换 _publish_to 骨架)
Step 9: 全链路自测 + publish_log 验证 (1 小时)
```

**核心原则**：
1. **先 dry-run 再真发**：所有平台先实现 `dry_run()`，确认内容正确后再接入真实 API
2. **环境变量管理 API Key**：所有凭据从 `.env` 读取，代码中不硬写
3. **单平台失败不连锁**：A 平台挂了不影响 B/C 平台
4. **publish_log 务必写入**：每次发布尝试（无论成败）都要写 publish_log
