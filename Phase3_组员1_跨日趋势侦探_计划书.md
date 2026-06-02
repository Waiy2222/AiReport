# Phase 3 组员1 — 跨日趋势侦探 · 详细计划书

> 日期：2026-06-02
> 基于：module-b AI 管道 + module-c 后端 API + module-c 小程序 + contracts/schema_v2.sql
> 功能：Agent 分析近 7 天简报数据，自动发现标签频率变化趋势，生成趋势报告并在小程序新 Tab 展示

---

## 总体目标

新增"趋势"功能模块：Agent 每日自动分析近 7 天简报，发现标签热度变化，生成趋势报告。在小程序底部新增"趋势"Tab 展示。

---

## 文件清单（共 9 个文件，含 1 个测试日志文件）

### 1. module-b/ai/trend_agent.py（新增）

- **功能**：跨日趋势分析 Agent 核心逻辑
- **核心函数**：
  - `analyze_trends(pool: asyncpg.Pool, days: int = 7) → dict` — **主入口函数**。查询近 N 天简报数据，计算各标签逐日频次，LLM 分析趋势变化，返回完整趋势报告
  - `_fetch_briefing_history(pool, days) → list[dict]` — 从 briefings 表查询近 N 天的 morning + evening 简报（每个 type/date 取最新一条），按日期升序排列。返回格式：`[{"date":"2026-05-27","type":"morning","sections":[...]}, ...]`
  - `_extract_all_tags(briefings) → dict[str, list[int]]` — 遍历所有简报 sections → items → tags 字段，统计每个 tag 在每个日期的出现次数。返回格式：`{"LLM":[3,5,5,8,9,11,11], "Agent":[1,2,3,5,5,7,8], ...}`（数组第 0 个=最早一天）
  - `_detect_anomalies(tag_freq: dict) → dict` — 对比最新一天和 7 天前的频次，计算变化百分比。分类为 rising（涨>30%）、falling（跌>30%）、stable（波动<30%）、new（新出现）
  - `_call_llm_trend_analysis(tag_freq, anomalies) → str` — **LLM 调用**。将统计数据发给 LLM，让 Agent 生成趋势解读文字（100-150 字中文）。prompt 包含频次数据和异常标签，要求 Agent 识别背后的行业趋势
  - `_mock_trends() → dict` — **无 API Key 回退**。返回预设的 mock 趋势数据，确保功能始终可用
- **LLM 调用模式**：复用 `module-b/ai/pipeline.py` 的 `_llm_chat()` 函数（直接 import），传入趋势分析专用 prompt
- **数据流转**：
  ```
  briefings 表（7天历史）
    → _fetch_briefing_history() 提取
      → _extract_all_tags() 统计频次
        → _detect_anomalies() 检测异常
          → _call_llm_trend_analysis() 生成解读
            → 返回 dict{period, rising[], falling[], new_tags[], agent_insight}
  ```
- **调试检测点**：
  - DB 连接正常且有 7 天数据时，`_fetch_briefing_history` 返回 14 条记录（7天×2简报）
  - `_extract_all_tags` 输出的每个 tag 数组长度 = days（7）
  - `_detect_anomalies` 的 rising/falling 数量合理（各不超过 5 个）
  - LLM 返回的 agent_insight 是中文且 100-150 字
  - 无 API Key 时 `_mock_trends` 返回完整的 mock 数据
  - 任意步骤异常不阻塞整体流程，返回部分数据 + 错误标记
- **测试方案**：
  1. 单元测试：mock 7 天 14 条简报数据，验证 tag 频次统计正确
  2. 单元测试：给固定频次数据，验证 rising/falling 分类正确（±30% 阈值）
  3. 集成测试：连真实 DB，调用 `analyze_trends(pool)`，验证返回结构完整
  4. Mock 回退测试：不传 API Key，验证返回 mock 数据
- **预期结果**：
  - 有 DB 数据时：返回 `{"period":"2026-05-27~2026-06-02","rising":[...],"falling":[...],"new_tags":[...],"agent_insight":"..."}`
  - 无 DB 数据时：返回 mock 趋势数据，period 为最近 7 天
  - 返回结构固定，字段不缺失

### 2. module-c/backend/trends.py（新增）

- **功能**：趋势数据 API 端点，供小程序和 Dashboard 调用
- **路由（在 main.py 中注册）**：
  - `GET /api/trends/weekly` — 返回近 7 天趋势报告
  - `GET /api/trends/tag/{tag}` — 返回单个标签的 7 天频次曲线（供详情展开）
- **核心函数**：
  - `get_weekly_trends(request: Request) → dict` — 从 DB 获取 DB pool，调用 `trend_agent.analyze_trends()`，包装为 JSON 响应。DB 不可用时调用 mock 回退
  - `get_tag_trend(tag: str, request: Request) → dict` — 查询单个标签的逐日频次，返回 `{"tag":"LLM","label_zh":"大模型","chart":[3,5,5,8,9,11,11],"dates":["05-27","05-28",...]}`
- **数据格式（/api/trends/weekly）**：
  ```json
  {
    "period": "2026-05-27 ~ 2026-06-02",
    "rising": [
      {"tag": "Agent", "label_zh": "智能体", "change_pct": 267, "current": 11, "previous": 3}
    ],
    "falling": [
      {"tag": "RAG", "label_zh": "RAG", "change_pct": -60, "current": 2, "previous": 5}
    ],
    "new_tags": [
      {"tag": "机器人", "label_zh": "机器人", "first_seen": "2026-06-01"}
    ],
    "agent_insight": "本周 Agent 话题热度飙升 267%，ICRA 2026 和宇树科技 IPO 是主要驱动力...",
    "generated_at": "2026-06-02T20:00:00+00:00"
  }
  ```
- **调试检测点**：
  - 路由 `/api/trends/weekly` 返回 HTTP 200
  - 返回 JSON 中 period/rising/falling/agent_insight 字段完整
  - DB 不可用时 fallback 到 mock 数据（不返回 500）
  - `/api/trends/tag/{tag}` 返回的 chart 数组长度为 7
  - 不存在的 tag 返回 404
- **测试方案**：
  1. 启动 module-c 后端 → curl `/api/trends/weekly` → 验证返回结构
  2. curl `/api/trends/tag/LLM` → 验证返回 7 天数据
  3. curl `/api/trends/tag/NotExist` → 验证返回 404
  4. 停掉 DB → curl `/api/trends/weekly` → 验证返回 mock 数据
- **预期结果**：
  - 有 DB 数据：rising/falling 数据真实反映标签频率变化
  - 无 DB 数据：返回彩色 mock 数据，不影响小程序展示

### 3. module-c/backend/main.py（修改）

- **功能**：注册趋势路由
- **修改点**：
  - 文件顶部新增：`from trends import router as trends_router`
  - 在 `app.include_router(tags_router)` 之后新增：`app.include_router(trends_router)`
- **调试检测点**：
  - 服务启动后 `/api/trends/weekly` 返回 200
  - 原有路由不受影响（`/api/tags`、`/api/briefings/latest` 正常）
  - 启动日志无 import 错误
- **测试方案**：
  1. 启动服务 → 访问 `/health` 确认正常
  2. 访问 `/api/trends/weekly` 确认新路由可用
  3. 访问 `/api/tags` 确认旧路由不受影响
- **预期结果**：三个 api 前缀路由全部正常工作

### 4. module-c/miniprogram/pages/trends/trends.js（新增）

- **功能**：趋势页数据加载与状态管理
- **核心逻辑**：
  - `onLoad()` — 调用 `api.getWeeklyTrends()` 获取趋势数据
  - `data` 字段：`{period, rising:[], falling:[], new_tags:[], agent_insight, loading, error}`
  - `onPullDownRefresh()` — 下拉刷新重新加载
  - `onTagTap(e)` — 点击单个标签跳转查看历史简报中该标签的文章
- **API 调用**：使用 `../../utils/api.js` 中新增的 `getWeeklyTrends()` 方法
- **调试检测点**：
  - `onLoad` 后 data 中 period/rising/falling/agent_insight 都有值
  - loading 状态正确切换（加载中→完成）
  - 接口失败时 error 显示，不白屏
  - 下拉刷新能重新加载数据
- **测试方案**：
  1. 小程序打开趋势 Tab → 验证数据加载
  2. 断开后端 → 刷新 → 验证错误提示
  3. 下拉刷新 → 验证重新加载
- **预期结果**：数据加载后显示完整的趋势卡片列表

### 5. module-c/miniprogram/pages/trends/trends.wxml（新增）

- **功能**：趋势页 UI 布局
- **UI 结构**：
  - **顶部 Agent 解读卡片**：🤖 图标 + `agent_insight` 文字 + 渐变背景（紫蓝）
  - **🔥 热度飙升榜**：`wx:for="{{rising}}"` 渲染，每个 tag 显示：中文标签名 + 红色箭头 `↑` + 百分比变化 + 迷你趋势线（用 view 模拟 7 个小柱状条）
  - **❄️ 热度降温榜**：`wx:for="{{falling}}"` 渲染，绿色箭头 `↓` + 百分比 + 迷你趋势线
  - **🆕 新兴标签**：`wx:for="{{new_tags}}"` 渲染，标签名 + "首次出现" 标记
  - **空状态**：`wx:if="{{!loading && !rising.length}}"` 显示"暂无趋势数据"
- **数据绑定**：
  - `{{agent_insight}}` — Agent 解读文字
  - `{{period}}` — 统计周期
  - `wx:for="{{rising}}"` — 飙升榜
  - `wx:for="{{falling}}"` — 降温榜
  - `mini-bar` 高度绑定：`style="height:{{item.current * 4}}px"`（最高 40px）
- **调试检测点**：
  - Agent 解读卡片正确渲染
  - 飙升榜每个条目显示 tag / 涨幅 / 趋势条
  - 降温榜每个条目显示 tag / 跌幅 / 趋势条
  - 红色箭头（↑）和绿色箭头（↓）正确
  - 空数据时显示空状态
  - 加载中显示 loading
- **测试方案**：
  1. 有数据时查看完整布局（Agent卡片 + 飙升榜 + 降温榜）
  2. 模拟空数据查看空状态
  3. 不同屏幕宽度查看响应式布局
- **预期结果**：4 个区域清晰分隔，颜色区分涨跌

### 6. module-c/miniprogram/pages/trends/trends.wxss（新增）

- **功能**：趋势页样式
- **样式清单**：
  - `.agent-insight-card` — 紫蓝渐变背景，圆角 12px，白色文字
  - `.trend-section` — 分区容器，白色背景卡片
  - `.section-label` — 分区标题（🔥 热度飙升榜）
  - `.trend-item` — 单个趋势条目，flex 横向布局
  - `.trend-tag` — 标签名称，加粗
  - `.trend-change` — 百分比变化，`.up` 红色 `.down` 绿色
  - `.mini-chart` — 7 个小柱状条容器
  - `.mini-bar` — 单个柱状条，`.bar-rising` 红 `.bar-falling` 绿 `.bar-new` 蓝
  - `.empty-state` / `.loading` — 空状态和加载态
- **调试检测点**：
  - 涨跌颜色区分度足够（红=#e74c3c, 绿=#07c160）
  - Agent 卡片渐变正常（`linear-gradient(135deg, #667eea, #764ba2)`）
  - 迷你柱状条对齐底部
  - 移动端适配（所有元素不超出屏幕）
- **测试方案**：
  1. 肉眼检查颜色区分度
  2. 手机/模拟器不同尺寸查看
  3. 涨跌条目混合时颜色不混淆
- **预期结果**：视觉清晰，红涨绿跌一目了然

### 7. module-c/miniprogram/pages/trends/trends.json（新增）

- **功能**：页面配置
- **内容**：
  ```json
  {
    "navigationBarTitleText": "趋势洞察",
    "enablePullDownRefresh": true,
    "backgroundColor": "#f5f5f5"
  }
  ```
- **调试检测点**：页面标题显示为"趋势洞察"，支持下拉刷新
- **测试方案**：打开趋势页查看标题栏文字
- **预期结果**：导航栏标题"趋势洞察"

### 8. module-c/miniprogram/app.json（修改）

- **功能**：注册趋势 Tab 到小程序底部导航
- **修改点**：
  - `pages` 数组新增：`"pages/trends/trends"`
  - `tabBar.list` 新增（在"历史"和"我的"之间）：
    ```json
    {
      "pagePath": "pages/trends/trends",
      "text": "趋势",
      "iconPath": "images/trend.png",
      "selectedIconPath": "images/trend-active.png"
    }
    ```
- **⚠️ 注意**：需要准备两个 40×40 的 PNG 图标 `trend.png` 和 `trend-active.png`，放在 `miniprogram/images/` 目录。可先用 emoji 🔥 替代或纯文字
- **调试检测点**：底部导航栏出现 4 个 Tab（今日简报、历史、趋势、我的），新增"趋势"Tab
- **测试方案**：编译小程序，点击底部"趋势"Tab，验证能跳转到趋势页
- **预期结果**：底部 4 Tab，切换正常

### 9. module-c/miniprogram/utils/api.js（修改）

- **功能**：新增趋势相关 API 调用方法
- **新增方法**：
  - `getWeeklyTrends()` — 调用 `GET /api/trends/weekly`
  - `getTagTrend(tag)` — 调用 `GET /api/trends/tag/{tag}`
- **代码**：
  ```javascript
  getWeeklyTrends() {
    return request("/api/trends/weekly");
  },
  getTagTrend(tag) {
    return request(`/api/trends/tag/${encodeURIComponent(tag)}`);
  },
  ```
- **调试检测点**：
  - `getWeeklyTrends()` 返回包含 period/rising/falling 的 JSON
  - `getTagTrend("LLM")` 返回包含 chart 数组的 JSON
  - 与现有 `request()` 函数兼容
- **测试方案**：
  1. 小程序调用 `api.getWeeklyTrends()` → 控制台查看返回值
  2. 调用 `api.getTagTrend("Agent")` → 验证 chart 数组
- **预期结果**：两种调用均返回结构化 JSON 数据

---

## 测试日志文件

### 10. Phase3_组员1_测试日志.md（新建，持续追加）

- **格式**：时间流日志，记录每步测试的：时间、测试项、测试数据、结果、原因分析
- **模板结构**：
  ```
  # Phase3 组员1 — 跨日趋势侦探 · 测试日志
  
  ## [2026-06-02 20:00] 测试1: trend_agent.py 单元测试
  - 测试方案：mock 7天数据，调用 analyze_trends()
  - 测试数据：[具体 mock 数据]
  - 测试结果：✅/❌
  - 原因分析：[成功/失败的根因]
  ```
- **调试检测点**：每次测试后有明确的结果标记（✅/❌）+ 原因分析
- **测试方案**：每完成一个文件立即测试，记录结果后再进行下一步
- **预期结果**：最终所有测试项 ✅

---

## 执行顺序

1. `trend_agent.py`（新增）→ 单元测试 → 记录日志
2. `trends.py`（新增）→ API 测试 → 记录日志
3. `main.py`（修改 — 1行 import + 1行注册）→ 路由测试 → 记录日志
4. `api.js`（修改 — 2个新函数）→ 调用测试 → 记录日志
5. `trends.js` + `trends.wxml` + `trends.wxss` + `trends.json`（新增 4 文件）→ 页面渲染测试 → 记录日志
6. `app.json`（修改）→ Tab 注册测试 → 记录日志
7. 联调：全链路测试（DB → trend_agent → API → 小程序 → UI）→ 记录日志

每步完成后运行测试验证，通过后再进行下一步。测试日志实时填充。

---

## 总文件目录

```
ai-news-briefing-agent/
├── module-b/ai/
│   └── trend_agent.py           (新增 — 趋势分析 Agent)
├── module-c/backend/
│   ├── trends.py                (新增 — 趋势 API 端点)
│   └── main.py                  (修改 — 注册趋势路由，+2行)
├── module-c/miniprogram/
│   ├── app.json                 (修改 — 注册趋势 Tab)
│   ├── utils/
│   │   └── api.js               (修改 — 新增 2个趋势 API 方法)
│   ├── images/                  (新增目录 — tabBar 图标)
│   │   ├── trend.png
│   │   └── trend-active.png
│   └── pages/
│       └── trends/              (新增目录 — 趋势页)
│           ├── trends.js
│           ├── trends.wxml
│           ├── trends.wxss
│           └── trends.json
└── Phase3_组员1_测试日志.md      (新增 — 测试日志)
```

**文件统计**：新增 7 个文件 + 修改 2 个文件 = 9 个交付物（含 1 个测试日志）

---

## 与其他任务的解耦说明

| | 本任务（组员1） | 队长任务 | 组员2任务 |
|---|---|---|---|
| 改动的模块 | module-b/ai + module-c | module-b/ai + module-c/detail | module-a + module-c/mine |
| 冲突风险 | 无 | 无（详情页 vs 趋势页，不同 Tab） | 无（mine页 vs 趋势页，不同 Tab） |
| 共用文件 | app.json（trends tab 在"历史"和"我的"之间） | 不碰 app.json | 不碰 app.json |
| 依赖 | 需要 briefings 表有 7 天数据 | 无依赖 | 无依赖 |

app.json 的修改点（在 tabBar.list 中"历史"和"我的"之间插入趋势页）是唯一的交叉点，但不影响其他两人的工作，只需注意合并时顺序正确。
