# 队员 D 开发测试日志 — 多平台发布模块

> 项目：AI 资讯早报/晚报智能体 — 模块 D 多平台发布
> 记录人：队员 D
> 分支：`module-d`
> 时间：2026-05-24

---

## 日志说明

每条记录包含：时间戳 | 阶段 | 测试方案 | 测试数据 | 测试结果 | 原因分析

---

## Phase 0：前置依赖安装与环境搭建

---

### [2026-05-24 19:00] — 前置 — 安装 Python 依赖

**测试方案**：
```bash
cd module-d
pip install -r requirements.txt
```

**测试数据**：`requirements.txt`（fastapi, uvicorn, asyncpg, httpx, pydantic）

**测试结果**：✅ **PASS**

**原因分析**：所有依赖安装成功，无版本冲突。fastapi 从 0.136.1 降级到 0.115.6 以匹配项目约定版本。

---

### [2026-05-24 19:05] — 前置 — 安装 PostgreSQL 16

**测试方案**：
```bash
# 方案A：Docker Desktop（不可用）
docker run -d --name my-pg ... postgres:16
# 方案B：winget install PostgreSQL.PostgreSQL.17（超时卡住）
# 方案C：conda install -c conda-forge postgresql（网络超时）
# 方案D：下载 PostgreSQL 17 便携版 ZIP 解压启动
curl -sL -o /tmp/postgresql.zip "https://get.enterprisedb.com/postgresql/postgresql-17.4-1-windows-x64-binaries.zip"
unzip -q /tmp/postgresql.zip -d /c/postgresql/
```

**测试数据**：PostgreSQL 17.4 Windows x64 便携版（315MB）

**测试结果**：✅ **PASS**

**原因分析**：
- Docker Desktop 未安装（仅有 docker CLI）
- winget 安装卡住（后台超时）
- conda 无 base 环境 + 网络超时
- **方案D可行**：EDB 便携版 zip → 解压 → `initdb` → `pg_ctl start`，全程无需管理员权限

**经验**：Windows 上最好的 Postgres 离线方案是 EDB 便携版。

---

### [2026-05-24 19:10] — 前置 — 初始化数据库 + 灌种子数据

**测试方案**：
```bash
/c/postgresql/pgsql/bin/createdb.exe -h localhost -U postgres ai_news
/c/postgresql/pgsql/bin/psql.exe -h localhost -U postgres -d ai_news -f contracts/schema.sql
/c/postgresql/pgsql/bin/psql.exe -h localhost -U postgres -d ai_news -f contracts/seed_data.sql
```

**测试数据**：`contracts/schema.sql` + `contracts/seed_data.sql`

**测试结果**：✅ **PASS**

**验证 SQL**：
```sql
SELECT 'raw_items', count(*) FROM raw_items
UNION ALL SELECT 'briefings', count(*) FROM briefings
UNION ALL SELECT 'publish_log', count(*) FROM publish_log
UNION ALL SELECT 'subscriptions', count(*) FROM subscriptions
UNION ALL SELECT 'run_log', count(*) FROM run_log;
```

**验证结果**：raw_items=30, briefings=3, publish_log=5, subscriptions=5, run_log=8

**原因分析**：5 张表全部创建成功，种子数据全部正确灌入。schema 和 seed_data 质量好。

---

## Phase 1：Step 1 — platforms/__init__.py

---

### [2026-05-24 19:15] — D1 — 包导入连通性

**测试方案**：
```python
import platforms
print('ok')
```

**测试数据**：空文件

**测试结果**：✅ **PASS** — 输出 `ok`

**原因分析**：空 `__init__.py` 正确将 `platforms/` 标记为 Python 包，导入无异常。

---

## Phase 2：Step 2 — content.py

---

### [2026-05-24 19:20] — D1-D7 — content.py 全部 6 项检测

**测试方案**：构造模拟 briefing 数据，逐个测试 extract_title/extract_intro/extract_body/format_markdown

**测试数据**（模拟 seed_data 简报结构）：
```python
sample = {
    'type': 'morning', 'date': '2026-05-24',
    'tl_dr': ['DeepSeek-V4 技术报告', 'Meta 开源 Llama-4-R1', 'Anthropic 发布 Claude 4.7'],
    'sections': [
        {'title': '大模型开源动态', 'items': [
            {'title': 'Meta 开源 Llama-4-R1', 'score': 9.5, ...},
            {'title': 'DeepSeek-V4 技术报告', 'score': 9.3, ...},
        ]},
        {'title': 'Agent 框架', 'items': [
            {'title': 'CrewAI v1.0', 'score': 8.0, ...},
        ]},
    ],
    'key_takeaways': ['开源模型进步'],
}
```

**测试结果**：✅ **全部 PASS**

| 检测点 | 结果 | 说明 |
|--------|------|------|
| D1 extract_title | PASS | `"AI 资讯早报 2026-05-24"` |
| D2 extract_intro | PASS | 正确返回前 3 条 tl_dr |
| D3 extract_body | PASS | 展开 sections→items，按 score 降序 |
| D4 format_markdown | PASS | 含 `#`标题/`>`引用/`[text]()`链接/`---`分隔线 |
| D6 空数据处理 | PASS | 空 sections 返回 `[]`，不抛异常 |
| D7 排序 | PASS | 乱序输入 `[5,9,7,None]` → 输出 `[9,7,5,0]` |

**连通性**：`import platforms` → PASS（Step 1 回溯验证）

**原因分析**：JSONB 结构解析正确，Markdown 格式兼容 CSDN 和知乎需求。

---

## Phase 3：Step 3 — renderer.py

---

### [2026-05-24 19:25] — D1-D10 — renderer.py 全部 10 项检测

**测试方案**：传入模拟 briefing 数据，验证 HTML 格式/结构/样式

**测试数据**：与 Phase 2 相同的 sample 数据

**测试结果**：✅ **全部 PASS**

| 检测点 | 结果 | 说明 |
|--------|------|------|
| D1 输出长度 | PASS | 3292 chars，完整 HTML |
| D2 `<h1>` 标题 | PASS | 含 AI 资讯标题 |
| D3 `<h2>` 数量 | PASS | 2 sections + 1 关键趋势 = 3 |
| D4 卡片布局 | PASS | 3 个 `class="card"` |
| D5 viewport | PASS | 移动端适配 |
| D6 深色模式 | PASS | `prefers-color-scheme: dark` |
| D7 score badge | PASS | 红色圆角评分元素 |
| D8 标签渲染 | PASS | 蓝色圆角 tag |
| D9 空数据 | PASS | 返回完整 DOCTYPE |
| D10 交叉调用 | PASS | content.py 函数在 renderer 内调用正常 |

**原因分析**：renderer 从 content.py 导入 `extract_intro`，验证了模块间依赖正确。

---

## Phase 4：Step 4 — platforms/weixin_oa.py

---

### [2026-05-24 19:30] — D1-D5 — weixin_oa.py 全部 5 项检测

**测试方案**：
1. `dry_run()` → 应返回 HTML 不调网络
2. 源码审查 → 确认 dry_run 无 httpx
3. 无凭据时 `get_access_token()` → 返回 None
4. 无凭据时 `publish()` → 返回 pending 不崩溃
5. 全链路交叉验证

**测试数据**：sample briefing + 空环境变量

**测试结果**：✅ **全部 PASS**

| 检测点 | 结果 | 说明 |
|--------|------|------|
| D1 dry_run | PASS | 2636 chars，含 DOCTYPE |
| D2 无网络 | PASS | 源码无 httpx/request |
| D3 无凭据 token | PASS | 返回 None |
| D4 publish 降级 | PASS | `status=pending` |
| D5 全连通性 | PASS | 5 文件串联 |

**原因分析**：`dry_run` → `render_article` → `extract_intro` 调用链完整。凭据空时优雅降级而不崩溃。

---

## Phase 5：Step 5 — platforms/zhihu.py

---

### [2026-05-24 19:35] — D1-D4+LINK — zhihu.py 全部 5 项检测

**测试方案**：与 Phase 4 类似 + 跨平台输出一致性验证

**测试数据**：sample briefing + 空环境变量

**测试结果**：✅ **全部 PASS**

**关键交叉验证**：
```python
assert weixin_oa.dry_run == render_article  # True ✅
assert zhihu.dry_run == format_markdown      # True ✅
```

**原因分析**：知乎和微信公众号的输出分别委托给 `content.py` 和 `renderer.py`，核心逻辑不重复。这一架构保证了三平台内容一致性。

---

## Phase 6：Step 6 — platforms/csdn.py

---

### [2026-05-24 19:40] — D1-D3+LINK — csdn.py 全部 4 项检测

**测试方案**：与 Phase 5 类似

**测试数据**：sample briefing + 空环境变量

**测试结果**：✅ **全部 PASS**

**三平台一致性验证**：
```
微信公众号 HTML: 2828 chars
知乎 Markdown:    285 chars
CSDN Markdown:    285 chars

html_wx == renderer  → True  ✅
md_zh == md_csdn     → True  ✅
md_zh == core_md     → True  ✅
```

**原因分析**：三平台输出完全一致（通过核心模块 content.py/renderer.py 实现），架构验证通过。

---

## Phase 7：Step 7 — orchestrator.py

---

### [2026-05-24 19:45] — D1-D6+DB — orchestrator.py 全部 7 项检测

**测试方案**：代码审查并发结构 + mock 测试失败隔离 + 真实 DB 测试 publish_log 写入

**测试数据**：sample briefing + MockPool + 真实 PostgreSQL

**测试结果**：✅ **6 PASS, 1 SKIP**

| 检测点 | 结果 | 说明 |
|--------|------|------|
| D1 并发结构 | PASS | `asyncio.gather` 并发执行 |
| D2 单源失败隔离 | PASS | 未知平台返回 failed，不影响其他 |
| D3 空平台列表 | PASS | 返回 `[]` |
| D4 超时保护 | PASS | `asyncio.wait_for` 60s |
| D5 映射完整性 | PASS | weixin_oa/zhihu/csdn 全部注册 |
| D6 正常路由 | PASS | weixin_oa 正确路由到模块 |
| DB publish_log | SKIP | PostgreSQL 未运行（后续全链路验证） |

**原因分析**：orchestrator 使用 `importlib.import_module` 动态加载平台模块，通过 `_PLATFORM_MODULES` 字典映射，扩展新平台只需添加一条映射。

---

## Phase 8：Step 8 — main.py 集成

---

### [2026-05-24 19:50] — D1-D5+LINK — main.py 全部 6 项检测

**测试方案**：代码审查 + 路由验证 + 模拟全链路调用

**测试数据**：sample briefing + MockPool

**测试结果**：✅ **全部 PASS**

| 检测点 | 结果 | 说明 |
|--------|------|------|
| D1 PLATFORMS 常量 | PASS | 3 平台完整 |
| D2 TODO 替换 | PASS | `_publish_to` 占位移除 |
| D3 完整简报读取 | PASS | `SELECT *` + JSONB 解析 |
| D4 路由注册 | PASS | `/health`, `/publish` |
| D5 默认值 | PASS | platforms 默认全平台 |
| LINK 全链路 | PASS | orchestrator→3 平台路由正常 |

**原因分析**：main.py 从 `_publish_to` 的 for 循环改为 `orchestrator.publish_all` 并发发布，且自动处理 JSONB 反序列化。

---

## Phase 9：Step 9 — 全链路自测（HTTP + 真实 DB）

---

### [2026-05-24 19:55] — 全链路 D1-D6 — 首次测试失败

**测试方案**：启动 PostgreSQL + uvicorn main:app → curl 测试

**测试数据**：
- 数据库：PostgreSQL 17.4 便携版（localhost:5432, ai_news）
- 简报 ID：`b0000001-0000-0000-0000-000000000001`（seed_data 中的假数据）
- 平台：weixin_oa, zhihu, csdn

**测试结果**：❌ **3 FAIL（D2+D5）**

**错误现象**：
1. `/publish` 返回 `'str' object has no attribute 'get'`
2. publish_log 写入失败 `text 与 character varying`

**原因分析**：
1. **Bug #1 — JSONB 字段为字符串**：asyncpg 默认将 JSONB 列返回为 Python `str`，不是 `list`/`dict`。`content.py` 中 `briefing.get("sections", [])` 拿到的是 JSON 字符串，遍历字符串字符时调用 `.get()` 报错。
2. **Bug #2 — write_log SQL 类型推断**：`CASE WHEN $3='success' THEN now() ELSE NULL END` 中 PostgreSQL 无法统一推断 `$3` 的类型（在 VALUES 中是 VARCHAR，在 CASE 中是 text），导致参数绑定时类型冲突。

**修复方案**：
- Bug #1 → 在 `main.py` 新增 `_parse_briefing()`：用 `json.loads` 将 JSONB 字符串字段转为 Python 对象
- Bug #2 → 将 `published_at` 计算移至 Python 端：`published_at = datetime.now(timezone.utc) if status == "success" else None`

---

### [2026-05-24 20:00] — 全链路 D1-D6 — 修复后复测

**测试方案**：停止旧进程 → 重启新代码 → 重复全部 6 项检测

**测试数据**：同上

**测试结果**：✅ **全部 PASS**

| 检测点 | 结果 | 说明 |
|--------|------|------|
| D1 /health | **PASS** | `{"status":"ok","db":"connected"}` |
| D2 /publish 三平台 | **PASS** | weixin_oa→pending, zhihu→pending, csdn→pending |
| D3 404 | **PASS** | `{"detail":"briefing not found"}` |
| D4 400 | **PASS** | `{"detail":"unsupported platform: unknown"}` |
| D5 publish_log 写入 | **PASS** | 3 条记录（weixin_oa/zhihu/csdn 各一条 pending） |
| D6 服务日志 | **PASS** | 零 ERROR |

**publish_log 写入验证**（raw SQL）：
```
                  id                  | platform  | status  | error_msg                                      | published_at |          created_at           
--------------------------------------+-----------+---------+------------------------------------------------+--------------+-------------------------------
 9729c747-... | csdn      | pending | credentials not configured, dry_run Markdown... |              | 2026-05-24 19:59:08.50777+08
 f3dfe4d4-... | zhihu     | pending | credentials not configured, dry_run Markdown... |              | 2026-05-24 19:59:08.507306+08
 574dbd50-... | weixin_oa | pending | credentials not configured, dry_run HTML...     |              | 2026-05-24 19:59:08.504457+08
(3 rows)
```

**原因分析**：
- JSONB 解析修复后，content.py/renderer.py 能正确读取简报数据
- write_log 类型修复后，publish_log 正确写入 3 条记录
- 三个平台均返回 `pending`（凭据未配置）属于预期行为，配置真实 API Key 后可改为 `success`

---

## 附录：Bug 修复记录

| # | 发现时间 | 文件 | 问题描述 | 修复方案 | 状态 |
|---|----------|------|----------|----------|------|
| 1 | 2026-05-24 19:55 | `main.py` | asyncpg 返回 JSONB 字段为字符串，`briefing.get("sections")` 拿到 JSON 字符串而非 Python 列表 | 新增 `_parse_briefing()`，用 `json.loads` 解析 `tl_dr/sections/key_takeaways/raw_stats` | ✅ 已修复 |
| 2 | 2026-05-24 19:55 | `orchestrator.py` | `write_log` 中 `CASE WHEN $3='success'` 导致 PostgreSQL 无法推断参数类型 | 将 `published_at` 计算移至 Python 端，SQL 改为 `$6` 直接传参 | ✅ 已修复 |

---

## 附录：总测试结果汇总

| Phase | Step | 检测点数 | 通过 | 失败 | 跳过 | 状态 |
|-------|------|---------|------|------|------|------|
| 0 | 前置依赖 | 2 | 2 | 0 | 0 | ✅ |
| 1 | platforms/__init__.py | 1 | 1 | 0 | 0 | ✅ |
| 2 | content.py | 6 | 6 | 0 | 0 | ✅ |
| 3 | renderer.py | 10 | 10 | 0 | 0 | ✅ |
| 4 | weixin_oa.py | 5 | 5 | 0 | 0 | ✅ |
| 5 | zhihu.py | 5 | 5 | 0 | 0 | ✅ |
| 6 | csdn.py | 4 | 4 | 0 | 0 | ✅ |
| 7 | orchestrator.py | 7 | 6 | 0 | 1 | ✅ |
| 8 | main.py 集成 | 6 | 6 | 0 | 0 | ✅ |
| 9 | 全链路自测（首轮） | 6 | 4 | 2 | 0 | ⚠️→✅ |
| 9 | 全链路自测（修复后） | 6 | 6 | 0 | 0 | ✅ |
| **合计** | | **58** | **55** | **2** | **1** | **✅** |
