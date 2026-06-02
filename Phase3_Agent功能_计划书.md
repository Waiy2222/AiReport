# Phase 3 Agent 功能 — 队长 + 组员1 + 组员2 · 计划书

> 日期：2026-06-02
> 基于：module-b AI 管道 + module-c 小程序 + module-e 调度系统
> 原则：三个任务完全解耦，各改各的模块，互不阻塞

---

## 总体目标

在现有"手动操作 + 规则驱动"的基础上，引入真正的 Agent 自主能力：

1. **多智能体新闻辩论**（队长）—— 3 个 Agent 以不同视角同时评分，生成多维度简报
2. **跨日趋势侦探**（组员1）—— Agent 分析 7 天数据，自动发现趋势变化
3. **Agent 自主扩展信源**（组员2）—— Agent 监测标签覆盖，自主搜索推荐新信源

三个任务**只在小程序展示**，推送仅做引导入口。

---

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│  module-a (抓取)           module-b (AI 加工)            │
│  ┌──────────────┐         ┌──────────────────────┐      │
│  │ 组员2:        │         │ 队长: 多 Agent 辩论   │      │
│  │ 信源自扩展     │ ────→  │ 组员1: 跨日趋势       │      │
│  │ source_agent  │         │                      │      │
│  └──────────────┘         └──────────┬───────────┘      │
│                                      ↓                   │
│  module-c (小程序 + 后端)             module-e (调度)     │
│  ┌──────────────────────┐         ┌──────────────┐      │
│  │ 详情页: 三方观点卡片   │         │ 统一触发入口   │      │
│  │ 趋势页: 趋势图表       │         │ 不新增任务     │      │
│  │ 我的页: 信源健康度     │         │              │      │
│  └──────────────────────┘         └──────────────┘      │
└─────────────────────────────────────────────────────────┘
```

---

## 任务一：多智能体新闻辩论（👤 队长）

### 目标
评分阶段不再单一 LLM 打分，改为 3 个 Agent 并行辩论，生成含多方观点的简报。

### 涉及文件（共 5 个）

#### 1. module-b/ai/debate_agent.py（新增）
- **功能**：多 Agent 辩论核心逻辑
- **核心函数**：
  - `run_debate(items: list[dict]) → list[dict]` — 主入口，对每条高优先级新闻跑 3 个 Agent
  - `_build_persona_prompt(persona: str, item: dict) → str` — 构建角色化 prompt
  - `_synthesize_perspectives(tech, biz, social) → dict` — 综合三方观点
- **三个 Agent 角色**：
  - Tech-Agent（技术派）：评估技术创新度、开源影响、开发者生态
  - Biz-Agent（商业派）：评估商业价值、市场影响、融资信号
  - Social-Agent（社会派）：评估社会影响、监管风险、伦理考量
- **并行策略**：3 个 Agent 对同一批 items 并行调用（`asyncio.gather`）
- **调试检测点**：并行调用耗时 < 串行 1/3，三方观点不雷同
- **测试方案**：给 10 条新闻，验证每条有 3 个不重复的观点
- **预期结果**：tech/biz/social 三个维度观点差异化明显

#### 2. module-b/ai/prompts.py（修改）
- **功能**：新增 3 个角色化 system prompt
- **新增内容**：
  - `DEBATE_TECH_PROMPT` — "你是技术分析师，关注技术创新、开源生态、架构突破"
  - `DEBATE_BIZ_PROMPT` — "你是商业分析师，关注市场格局、投融资、商业化策略"
  - `DEBATE_SOCIAL_PROMPT` — "你是社会观察家，关注监管政策、社会影响、伦理风险"
- **调试检测点**：每个 prompt 不超过 500 字，角色定位明确不重叠
- **测试方案**：用同一新闻发给 3 个 prompt，验证输出角度不同
- **预期结果**：三个 Agent 回复关注点不同（技术/商业/社会）

#### 3. module-b/pipeline.py（修改）
- **功能**：在评分阶段后插入辩论步骤
- **修改点**：
  - `run_pipeline()` 第 ② 步（AI 评分）之后 → 新增 `⑧.⑤ AI 辩论`
  - 只对 `ai_score >= 8` 的 Top 新闻跑辩论（控制成本）
  - 辩论结果写入 `item["metadata"]["debate"]`
- **辩论结果结构**：
  ```json
  {
    "tech_view": "技术角度分析...",
    "biz_view": "商业角度分析...",
    "social_view": "社会角度分析...",
    "consensus": "三方共识点",
    "controversy": "争议度(0-10)"
  }
  ```
- **调试检测点**：辩论不影响原有评分流程，辩论失败回退到无辩论模式
- **测试方案**：触发管道，验证简报 items 中有 debate 字段
- **预期结果**：8 分以上新闻有 debate，8 分以下无（节省 Token）

#### 4. module-c/miniprogram/pages/detail/detail.wxml（修改）
- **功能**：文章卡片下方展示三方观点
- **新增 UI**：
  - 辩论标签 `🎭 AI三方观点`
  - 3 个彩色横条卡片（蓝=技术 / 橙=商业 / 绿=社会）
  - 争议度进度条
- **调试检测点**：有 debate 数据的文章显示卡片，无数据的不显示
- **测试方案**：打开一篇高分文章详情，查看三方观点展示
- **预期结果**：三方观点卡片颜色区分清晰，争议度可视化

#### 5. module-c/miniprogram/pages/detail/detail.wxss（修改）
- **功能**：三方观点卡片样式
- **新增样式**：`.debate-card`、`.debate-tech`、`.debate-biz`、`.debate-social`、`.controversy-bar`
- **调试检测点**：三色区分度足够，移动端适配
- **测试方案**：不同屏幕尺寸查看卡片布局
- **预期结果**：蓝橙绿三色卡片并排或纵向排列，不重叠

### 执行顺序
1. prompts.py（加 3 个角色 prompt）
2. debate_agent.py（写辩论核心逻辑）
3. pipeline.py（集成到管道）
4. detail.wxml + detail.wxss（小程序前端展示）
5. 联调测试：触发早报 → 查看详情页三方观点

---

## 任务二：跨日趋势侦探（👤 组员1）

### 目标
Agent 分析近 7 天简报数据，自动发现标签频率变化趋势，生成趋势报告。

### 涉及文件（共 5 个）

#### 1. module-b/ai/trend_agent.py（新增）
- **功能**：跨日趋势分析 Agent
- **核心函数**：
  - `analyze_trends(days: int = 7) → dict` — 主入口，查询 7 天数据，LLM 分析趋势
  - `_fetch_history(pool, days) → list[dict]` — 查询近 N 天简报数据
  - `_calc_tag_frequency(briefings) → dict` — 计算各标签逐日出现频次
  - `_detect_anomalies(tag_data) → list[dict]` — 检测异常波动（±50%变化）
  - `_generate_trend_report(tag_data, anomalies) → str` — LLM 生成趋势文字报告
- **趋势指标**：
  - 热度飙升榜：本周增长最快的 5 个标签（涨幅 %）
  - 热度降温榜：本周下降最快的 5 个标签（跌幅 %）
  - 新兴标签：本周首次出现的标签
  - Agent 洞察：LLM 生成的一段趋势解读（100 字）
- **调试检测点**：频次计算准确，异常检测阈值合理
- **测试方案**：用 7 天 mock 数据验证趋势计算和 LLM 报告
- **预期结果**：返回 5 个飙升标签 + 5 个降温标签 + Agent 解读

#### 2. module-c/backend/trends.py（新增）
- **功能**：趋势数据 API 端点
- **路由**：
  - `GET /api/trends/weekly` — 返回近 7 天趋势数据（标签频次变化 + Agent 解读）
  - `GET /api/trends/tag/{tag}` — 返回单个标签的趋势曲线
- **数据格式**：
  ```json
  {
    "period": "2026-05-27 ~ 2026-06-02",
    "rising": [{"tag": "Agent", "label_zh": "智能体", "change": "+267%", "chart": [3,5,5,8,9,11,11]}],
    "falling": [{"tag": "RAG", "label_zh": "RAG", "change": "-60%", "chart": [5,4,3,2,2,2,2]}],
    "new_tags": ["机器人", "VLA"],
    "agent_insight": "本周Agent话题热度飙升267%..."
  }
  ```
- **调试检测点**：DB 查询正确，fallback 到 mock 数据
- **测试方案**：httpx 测试端点返回正确 JSON 结构
- **预期结果**：无 DB 时返回 mock 趋势数据，有 DB 时返回真实数据

#### 3. module-c/backend/main.py（修改）
- **功能**：注册趋势路由
- **修改点**：`from trends import router as trends_router` + `app.include_router(trends_router)`
- **调试检测点**：`/api/trends/weekly` 可访问
- **测试方案**：服务启动后 curl 新端点
- **预期结果**：返回 200 + 趋势 JSON 数据

#### 4. module-c/miniprogram/pages/trends/（新增页面）
- **功能**：小程序趋势 Tab 页
- **新增文件**：
  - `trends.js` — 调用 `/api/trends/weekly`，绑定数据
  - `trends.wxml` — 趋势卡片布局（飙升榜 + 降温榜 + Agent 解读）
  - `trends.wxss` — 趋势页样式（涨红跌绿、新旧标签色）
  - `trends.json` — 页面配置
- **UI 结构**：
  - 顶部：Agent 趋势洞察卡片（带 🤖 图标）
  - 中部：🔥 热度飙升榜（红色箭头 + 涨幅百分比）
  - 下部：❄️ 热度降温榜（绿色箭头 + 跌幅百分比）
  - 底部：🆕 新兴标签
- **调试检测点**：涨跌颜色正确、数据绑定正确
- **测试方案**：小程序导航到趋势页，查看数据展示
- **预期结果**：飙升标签红色向上箭头，降温标签绿色向下箭头

#### 5. module-c/miniprogram/app.json（修改）
- **功能**：在 tabBar 中新增"趋势"Tab
- **修改点**：`pages/trends/trends` 加入 pages 和 tabBar.list
- **调试检测点**：底部导航栏出现"趋势"图标
- **测试方案**：编译小程序，点击趋势 Tab
- **预期结果**：底部 4 个 Tab（今日简报、历史、趋势、我的）

### 执行顺序
1. trend_agent.py（趋势分析 Agent 逻辑）
2. trends.py（API 端点）
3. main.py（注册路由）
4. trends 页面 4 个文件（小程序前端）
5. app.json（注册 Tab）
6. 联调测试：启动后端 → 打开小程序趋势页

---

## 任务三：Agent 自主扩展信源（👤 组员2）

### 目标
Agent 监测各标签的新闻覆盖率，当某标签连续 3 天覆盖不足时，自动搜索推荐新 RSS 信源。

### 涉及文件（共 5 个）

#### 1. module-a/source_agent.py（新增）
- **功能**：信源自扩展 Agent
- **核心函数**：
  - `check_coverage(pool) → list[dict]` — 检查各标签近 3 天覆盖率，返回不足标签
  - `search_sources(tag: str) → list[dict]` — LLM 自主搜索该领域的 RSS 源
  - `evaluate_source(url: str, tag: str) → dict` — 评估信源质量（可靠性 + 更新频率 + 内容匹配度）
  - `recommend_sources() → list[dict]` — 主入口：检测 → 搜索 → 评估 → 推荐
- **自主决策链路**：
  ```
  检查覆盖率 → 发现"RAG"标签连续3天 < 2条
    → Agent 搜索 "RAG retrieval augmented generation RSS feed"
      → 找到 5 个候选源
        → Agent 逐个评估（爬取首页 → LLM 判断质量）
          → 推荐 Top 2 → 写入 recommended_sources 表
  ```
- **评估维度**（每个 1-5 分）：
  - 内容相关性：文章是否真的和标签相关
  - 更新频率：最近 3 天是否有新内容
  - 权威性：是否知名网站/博客
  - 可用性：RSS/API 是否可正常访问
- **调试检测点**：覆盖率阈值（<2 条触发）、搜索关键词准确性、评估合理性
- **测试方案**：mock 标签覆盖数据，验证搜索和推荐流程
- **预期结果**：覆盖不足的标签收到新信源推荐

#### 2. contracts/schema_v3.sql（新增）
- **功能**：新增推荐信源表
- **新增表**：
  ```sql
  CREATE TABLE IF NOT EXISTS recommended_sources (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      tag VARCHAR(32) NOT NULL,
      name TEXT NOT NULL,
      url TEXT NOT NULL,
      rss_url TEXT,
      quality_score DECIMAL(2,1),     -- 综合评分 1-5
      relevance_score DECIMAL(2,1),   -- 相关性
      freshness_score DECIMAL(2,1),   -- 更新频率
      authority_score DECIMAL(2,1),   -- 权威性
      status VARCHAR(16) DEFAULT 'pending',  -- pending/approved/rejected
      discovered_at TIMESTAMPTZ DEFAULT now(),
      approved_at TIMESTAMPTZ,
      FOREIGN KEY (tag) REFERENCES tag_catalog(tag)
  );
  ```
- **调试检测点**：表结构正确，外键约束生效
- **测试方案**：psql 执行 schema，验证建表成功
- **预期结果**：表创建成功，约束生效

#### 3. module-c/backend/main.py（修改）
- **功能**：新增信源健康度 API
- **新增路由**：
  - `GET /api/sources/health` — 返回各标签覆盖率（绿/黄/红三档）
  - `GET /api/sources/recommendations` — 返回待审推荐信源列表
  - `POST /api/sources/approve` — 管理员通过推荐信源
- **调试检测点**：覆盖率计算正确，颜色分档合理（>=5 绿、2-4 黄、<2 红）
- **测试方案**：curl 端点验证返回结构
- **预期结果**：每个标签返回 cover_rate + health 颜色

#### 4. module-c/miniprogram/pages/mine/mine.wxml + mine.js + mine.wxss（修改）
- **功能**：在"我的"页展示信源健康度
- **新增 UI**：
  - 信源健康度卡片（在标签偏好下方）
  - 每个标签显示绿/黄/红圆点 + 覆盖条数
  - 有推荐时显示 "🔔 N个新信源待审核" 红点提示
- **调试检测点**：颜色指示正确，推荐提示显示
- **测试方案**：查看我的页，验证信源健康度展示
- **预期结果**：标签旁显示健康灯，不足标签红色警示

#### 5. module-e/dashboard/frontend/src/pages/index.html + app.js（修改）
- **功能**：Dashboard 展示推荐信源 + 审核按钮
- **新增 UI**：
  - "信源健康"面板区
  - 覆盖率低的标签高亮显示
  - 推荐信源列表（名称/URL/评分/通过按钮）
- **调试检测点**：点击"通过"按钮后信源加入抓取列表
- **测试方案**：Dashboard 刷新查看信源面板
- **预期结果**：管理面板显示信源健康度 + 可操作审核

### 执行顺序
1. schema_v3.sql（建表）
2. source_agent.py（信源 Agent 逻辑）
3. main.py（API 端点）
4. mine 页面（小程序前端展示）
5. Dashboard（管理面板展示）
6. 联调测试：触发覆盖率检查 → 查看推荐 → 通过信源

---

## 总文件清单

```
模块间完全解耦，改自己的文件，互不影响：

👤 队长:
  module-b/ai/debate_agent.py  (新增)
  module-b/ai/prompts.py       (修改)
  module-b/pipeline.py         (修改)
  module-c/miniprogram/pages/detail/detail.wxml  (修改)
  module-c/miniprogram/pages/detail/detail.wxss  (修改)

👤 组员1:
  module-b/ai/trend_agent.py   (新增)
  module-c/backend/trends.py   (新增)
  module-c/backend/main.py     (修改 — 注册趋势路由)
  module-c/miniprogram/pages/trends/trends.js    (新增)
  module-c/miniprogram/pages/trends/trends.wxml   (新增)
  module-c/miniprogram/pages/trends/trends.wxss   (新增)
  module-c/miniprogram/pages/trends/trends.json   (新增)
  module-c/miniprogram/app.json (修改 — 注册趋势Tab)

👤 组员2:
  module-a/source_agent.py     (新增)
  contracts/schema_v3.sql      (新增)
  module-c/backend/main.py     (修改 — 注册信源路由)
  module-c/miniprogram/pages/mine/mine.wxml  (修改)
  module-c/miniprogram/pages/mine/mine.js    (修改)
  module-c/miniprogram/pages/mine/mine.wxss  (修改)
  module-e/dashboard/frontend/src/pages/index.html  (修改)
  module-e/dashboard/frontend/src/pages/app.js       (修改)
```

---

## 解耦说明

| | 队长 | 组员1 | 组员2 |
|---|---|---|---|
| **负责模块** | module-b（AI管道）| module-b + module-c | module-a + module-c + module-e |
| **是否依赖其他人** | 否（独立改评分链路）| 否（独立加趋势模块）| 否（独立加信源模块）|
| **小程序冲突点** | detail 页面 | trends 页面（新增）| mine 页面 |
| **共用文件** | 无冲突（detail.wxml/wxss 二人不碰）| 无冲突（新页面）| 无冲突（mine 页面二人不碰）|
| **测试方式** | 触发早报 → 看详情页观点卡片 | 访问 /api/trends/weekly → 看趋势页 | 访问 /api/sources/health → 看信源面板 |

---

## 统一验收

三人完成后，队长负责集成验证：

1. 触发早报管道 → 详情页出现三方观点卡片 ✅
2. 打开趋势 Tab → 看到飙升/降温榜 + Agent 解读 ✅
3. 打开我的页 → 信源健康灯 + 推荐提示 ✅
4. Dashboard → 审核推荐信源 → 通过 ✅
5. 三个功能同时工作，互不影响 ✅
