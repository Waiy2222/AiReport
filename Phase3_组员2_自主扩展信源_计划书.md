# Phase 3 组员2 — Agent 自主扩展信源 · 详细计划书

> 日期：2026-06-02
> 基于：module-a RSS 抓取管道 + module-c 后端 API + module-c 小程序 + module-e Dashboard + contracts/schema_v2.sql
> 功能：Agent 监测各标签新闻覆盖率，覆盖不足时自主搜索评估新 RSS 信源，推荐给管理员审批

---

## 总体目标

Agent 不再被动使用固定 RSS 列表，而是主动监测 19 个标签的新闻覆盖情况。当某标签连续 3 天覆盖不足（<2 条/天），Agent 自主搜索新的 RSS 源、评估质量、生成推荐列表。管理员在 Dashboard 一键审批即可加入抓取队列。小程序"我的"页展示各标签信源健康度。

---

## 文件清单（共 8 个文件，含 1 个测试日志文件）

### 1. contracts/schema_v3.sql（新增）

- **功能**：新增推荐信源表，持久化 Agent 发现的候选源
- **新增表**：
  ```sql
  CREATE TABLE IF NOT EXISTS recommended_sources (
      id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      tag             VARCHAR(32) NOT NULL,
      name            TEXT NOT NULL,           -- 信源名称（如 "机器学习周刊"）
      url             TEXT NOT NULL,           -- 网站主页
      rss_url         TEXT,                    -- RSS/Atom feed URL
      quality_score   DECIMAL(3,1),            -- 综合评分 1.0-5.0
      relevance_score DECIMAL(3,1),            -- 内容相关性 1.0-5.0
      freshness_score DECIMAL(3,1),            -- 更新频率 1.0-5.0
      authority_score DECIMAL(3,1),            -- 权威性 1.0-5.0
      status          VARCHAR(16) DEFAULT 'pending',  -- pending/approved/rejected
      discovered_at   TIMESTAMPTZ DEFAULT now(),
      approved_at     TIMESTAMPTZ,
      sample_titles   TEXT[],                  -- Agent 抓取的样本标题（3条）
      agent_comment   TEXT,                    -- Agent 推荐理由
      FOREIGN KEY (tag) REFERENCES tag_catalog(tag)
  );
  CREATE INDEX IF NOT EXISTS idx_rs_tag ON recommended_sources(tag);
  CREATE INDEX IF NOT EXISTS idx_rs_status ON recommended_sources(status);
  ```
- **调试检测点**：
  - 建表成功，`\d recommended_sources` 显示所有列
  - 外键约束生效（插入不存在的 tag 报错）
  - status 默认值为 'pending'
  - sample_titles 数组类型正确
- **测试方案**：
  1. `psql -d ai_news -f schema_v3.sql` → 验证无报错
  2. `INSERT INTO recommended_sources (tag,name,url) VALUES ('Sports','test','http://x.com')` → 外键报错
  3. `INSERT INTO recommended_sources (tag,name,url) VALUES ('体育','test','http://x.com')` → 成功
- **预期结果**：表创建成功，字段约束生效，索引可用

### 2. module-a/source_agent.py（新增）

- **功能**：信源自扩展 Agent 核心逻辑
- **核心函数**：
  - `check_coverage(pool: asyncpg.Pool, tag: str = None, days: int = 3) → list[dict]` — 检查近 N 天各标签在 briefings 中的出现次数。只返回覆盖不足的标签（日均 < 2 条）。如果传了 tag 参数则只查单个标签。返回格式：`[{"tag":"RAG","label_zh":"RAG","avg_daily":0.3,"days_covered":1}]`
  - `search_sources(tag: str, label_zh: str) → list[dict]` — **LLM 调用**。让 Agent 搜索该领域的高质量中文 RSS 源。Prompt 要求返回 JSON 格式：`[{"name":"...","url":"...","rss_url":"...","reason":"..."}]`。Agent 基于训练数据中的知识推荐（不需要实时爬取）
  - `evaluate_source(source: dict, tag: str) → dict` — 评估单个候选信源。尝试 HTTP GET 访问 RSS URL（10s 超时），检查返回内容。再用 LLM 评估内容与标签的相关性。返回 `{"quality":4.5,"relevance":5.0,"freshness":3.0,"authority":4.0,"comment":"该源更新频繁，内容与RAG高度相关"}`
  - `discover_sources(pool: asyncpg.Pool) → dict` — **主入口函数**。串联 check_coverage → search_sources → evaluate_source → 写入 recommended_sources 表。返回 `{"checked_tags":19,"low_coverage":3,"found_sources":8,"recommended":3}`
  - `_fetch_rss_samples(rss_url: str) → list[str]` — 尝试抓取 RSS 源的前 3 个标题作为样本，用于 LLM 评估相关性
- **LLM 调用模式**：复用 `module-b/ai/pipeline.py` 的 `_llm_chat()` 函数（直接 import）
- **关键决策链路**：
  ```
  check_coverage → 发现体育标签 3 天平均 0.7 条/天（<2）
    → search_sources("体育","体育") → Agent 推荐 5 个体育 RSS 源
      → evaluate_source 逐源评估（HTTP GET → LLM 判断）
        → 筛选 quality>=3.0 的源 → INSERT INTO recommended_sources
          → 返回推荐结果
  ```
- **调试检测点**：
  - `check_coverage()` 对 19 个标签逐个统计，日均计算准确
  - `search_sources()` 返回的候选源 URL 格式正确（http/https 开头）
  - `evaluate_source()` 对不可达 URL 返回 quality=0 而非崩溃
  - `discover_sources()` 去重（同一个 URL 不会重复推荐）
  - 无 API Key 时退化为规则模式（只检查覆盖，不搜索新源）
  - 所有 HTTP 调用有超时保护（10s）
- **测试方案**：
  1. 单元测试：mock coverage 数据 → 验证覆盖判断逻辑（日均<2 → 告警）
  2. 单元测试：给定 mock RSS URL → 验证 evaluation 评分在 1-5 范围
  3. 集成测试：连真实 DB → 调用 `discover_sources(pool)` → 验证写入 recommended_sources 表
  4. 错误测试：给定不可达 URL → 验证 evaluate_source 返回 quality=0 + 错误注释
- **预期结果**：
  - 覆盖正常的标签（日均>=2）不出现在 low_coverage 列表中
  - 覆盖不足的标签收到推荐（至少 1 条候选源）
  - 推荐结果写入数据库，status='pending'
  - 异常情况不崩溃，返回部分结果 + 错误标记

### 3. module-c/backend/sources_api.py（新增）

- **功能**：信源健康度 + 推荐管理 API 端点
- **路由（在 main.py 中注册）**：
  - `GET /api/sources/health` — 返回各标签覆盖率概览（红黄绿三档）
  - `GET /api/sources/recommendations` — 返回待审核推荐信源列表
  - `POST /api/sources/{source_id}/approve` — 管理员审核通过
  - `POST /api/sources/{source_id}/reject` — 管理员驳回
- **核心函数**：
  - `get_source_health(request: Request) → dict` — 调用 `source_agent.check_coverage()`，对每个标签计算健康等级（绿=日均>=5、黄=日均 2-4、红=日均<2）。返回 `{"tags":[{tag,label_zh,health,avg_daily,days_covered}]}`
  - `get_recommendations(request: Request, status: str = "pending") → dict` — 从 recommended_sources 表查询待审/已审信源
  - `approve_source(source_id: str, request: Request) → dict` — 更新 status='approved' + approved_at=now()。额外逻辑：将 approved 的 rss_url 写入 module-a 的 RSS_SOURCES 配置（通过环境变量或 JSON 配置文件）
  - `reject_source(source_id: str, request: Request) → dict` — 更新 status='rejected'
- **数据格式（/api/sources/health）**：
  ```json
  {
    "tags": [
      {"tag":"LLM","label_zh":"大模型","health":"green","avg_daily":8.3,"days_covered":3},
      {"tag":"RAG","label_zh":"RAG","health":"red","avg_daily":0.3,"days_covered":1},
      {"tag":"体育","label_zh":"体育","health":"yellow","avg_daily":2.3,"days_covered":3}
    ],
    "low_coverage_count": 2,
    "total_tags": 19
  }
  ```
- **调试检测点**：
  - `/api/sources/health` 返回 19 个标签的完整数据
  - 健康等级颜色正确：avg>=5=绿，avg 2-4=黄，avg<2=红
  - `/api/sources/recommendations?status=pending` 只返回待审信源
  - `/api/sources/{id}/approve` 成功后该记录 status='approved'
  - DB 不可用时返回 503（此 API 必须依赖 DB）
- **测试方案**：
  1. curl `/api/sources/health` → 验证 19 个标签 + 健康等级
  2. curl `/api/sources/recommendations` → 验证返回待审列表
  3. curl -X POST `/api/sources/{id}/approve` → 验证状态变更
  4. curl -X POST `/api/sources/{id}/reject` → 验证状态变更
- **预期结果**：4 个端点全部正常工作，数据与数据库一致

### 4. module-c/backend/main.py（修改）

- **功能**：注册信源 API 路由
- **修改点**：
  - 新增 `from sources_api import router as sources_router`
  - 新增 `app.include_router(sources_router)`
- **调试检测点**：原有路由 + 趋势路由 + 信源路由全部正常
- **测试方案**：curl `/health` + `/api/sources/health` + `/api/trends/weekly` 全部 200
- **预期结果**：三个模块路由不冲突

### 5. module-c/miniprogram/pages/mine/mine.wxml（修改）

- **功能**：在"推送订阅"下方新增"信源健康度"卡片
- **新增 UI**：
  ```html
  <view class="settings-block">
    <view class="settings-title">📡 信源健康度</view>
    <view class="source-health-grid">
      <view class="health-row" wx:for="{{healthTags}}" wx:key="tag">
        <view class="health-dot {{item.health}}"></view>
        <view class="health-tag-name">{{item.label_zh}}</view>
        <view class="health-stat">{{item.avg_daily}}条/天</view>
      </view>
    </view>
    <view wx:if="{{lowCoverageCount > 0}}" class="health-warning">
      ⚠️ {{lowCoverageCount}}个标签覆盖不足，Agent正在搜索新信源...
    </view>
  </view>
  ```
- **调试检测点**：绿/黄/红圆点正确、覆盖不足警告可见
- **测试方案**：打开"我的"页查看信源健康度卡片
- **预期结果**：标签旁显示健康灯，不足标签红点+警告文字

### 6. module-c/miniprogram/pages/mine/mine.js（修改）

- **功能**：加载信源健康度数据
- **新增逻辑**：
  - `onLoad()` → 新增调用 `api.getSourceHealth()` → 存入 `data.healthTags` 和 `data.lowCoverageCount`
  - 每 30s 自动刷新（可选，避免频繁请求）
- **调试检测点**：healthTags 加载后有 19 条数据
- **测试方案**：小程序打开"我的"页 → 检查 healthTags 数据
- **预期结果**：信源健康数据正确加载

### 7. module-c/miniprogram/pages/mine/mine.wxss（修改）

- **功能**：信源健康度卡片样式
- **新增样式**：
  - `.source-health-grid` — 2 列网格布局
  - `.health-row` — 单行 flex
  - `.health-dot` — 10px 圆点，`.green`=#07c160, `.yellow`=#f0ad4e, `.red`=#e74c3c
  - `.health-warning` — 橙黄色警告条
- **调试检测点**：三色区分度足够
- **测试方案**：肉眼检查颜色
- **预期结果**：绿黄红三色清晰

### 8. module-c/miniprogram/utils/api.js（修改）

- **功能**：新增信源 API 调用方法
- **新增方法**：
  ```javascript
  getSourceHealth() {
    return request("/api/sources/health");
  },
  getSourceRecommendations(status) {
    return request(`/api/sources/recommendations?status=${status || 'pending'}`);
  },
  approveSource(id) {
    return request(`/api/sources/${encodeURIComponent(id)}/approve`, "POST");
  },
  rejectSource(id) {
    return request(`/api/sources/${encodeURIComponent(id)}/reject`, "POST");
  },
  ```
- **调试检测点**：`getSourceHealth()` 返回 19 条标签数据
- **测试方案**：控制台调用 `api.getSourceHealth()` → 查看返回值
- **预期结果**：返回结构与后端一致

---

## 测试日志文件

### 9. Phase3_组员2_测试日志.md（新建）

- **格式**：时间流日志，每步测试后记录方案/数据/结果/原因分析
- **测试流程**（9 步）：
  1. 环境检查
  2. schema_v3.sql 建表测试
  3. source_agent.py check_coverage 单元测试
  4. source_agent.py 集成测试
  5. sources_api.py API 测试
  6. main.py 路由注册测试
  7. api.js 方法测试
  8. mine 页面信源健康度渲染测试
  9. 全链路联调 + 异常场景测试
- **调试检测点**：每步有明确 ✅/❌ 标记 + 原因分析
- **测试方案**：一个文件完成 → 立即测试 → 记录结果 → 下一步
- **预期结果**：最终所有测试项 ✅

---

## 执行顺序

1. `schema_v3.sql`（建表）→ DB 测试 → 记录日志
2. `source_agent.py`（Agent 核心）→ 单元测试 → 记录日志
3. `sources_api.py`（API 端点）→ curl 测试 → 记录日志
4. `main.py`（注册路由，+2行）→ 路由测试 → 记录日志
5. `api.js`（新增 4 个方法）→ 控制台测试 → 记录日志
6. `mine.wxml + mine.js + mine.wxss`（3文件修改）→ 页面渲染测试 → 记录日志
7. 全链路联调 → 记录日志

---

## 总文件目录

```
ai-news-briefing-agent/
├── contracts/
│   └── schema_v3.sql                     (新增 — 推荐信源表)
├── module-a/
│   └── source_agent.py                   (新增 — 信源自主扩展 Agent)
├── module-c/backend/
│   ├── sources_api.py                    (新增 — 信源 API 端点)
│   └── main.py                           (修改 — 注册信源路由，+2行)
├── module-c/miniprogram/
│   ├── utils/
│   │   └── api.js                        (修改 — 新增 4个信源 API 方法)
│   └── pages/
│       └── mine/
│           ├── mine.js                   (修改 — 加载信源健康数据)
│           ├── mine.wxml                 (修改 — 新增信源健康卡片)
│           └── mine.wxss                 (修改 — 新增健康卡片样式)
└── Phase3_组员2_测试日志.md               (新增 — 测试日志)
```

**文件统计**：新增 4 个文件 + 修改 4 个文件 = 8 个交付物（含 1 个测试日志）

---

## 与其他任务的解耦说明

| | 本任务（组员2） | 队长任务 | 组员1任务 |
|---|---|---|---|
| 改动的模块 | module-a + module-c/mine + contracts | module-b/ai + module-c/detail | module-b/ai + module-c |
| 冲突风险 | 无 | 无 | 无 |
| 共用文件 | main.py（仅+1行import+1行include） | 不碰 main.py | main.py（组员1也+2行） |
| 同一文件冲突 | main.py: 组员1加trends路由，组员2加sources路由 | 不碰 | main.py: 顺序不同但互不影响 |

main.py 是唯一的交叉点：组员1 加 `from trends import router`，组员2 加 `from sources_api import router`。两行 import 和两行 include_router 互不冲突，合并时按字母顺序排列即可。
