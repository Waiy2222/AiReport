# Phase3 组员2 — Agent 自主扩展信源 · 测试日志

> 测试人：组员2
> 开始时间：2026-06-02
> 原则：每完成一个文件立即测试，记录结果；失败需写原因分析

---

## [2026-06-02 20:00] 环境检查

- **测试方案**：确认 PostgreSQL 运行 + module-a 依赖 + module-c 运行 + tag_catalog 表有 19 个标签
- **测试数据**：`SELECT count(*) FROM tag_catalog; SELECT count(*) FROM briefings;`
- **测试结果**：待填写
- **原因分析**：待填写

---

## [2026-06-02 20:30] 测试1: schema_v3.sql 建表

- **测试方案**：psql 执行 schema_v3.sql → 验证表创建 + 约束 + 索引
- **测试数据**：
  ```sql
  \d recommended_sources
  INSERT INTO recommended_sources (tag,name,url) VALUES ('NotExist','test','http://x.com'); -- 应失败
  INSERT INTO recommended_sources (tag,name,url) VALUES ('体育','ESPN China','http://espn.com/rss'); -- 应成功
  ```
- **测试结果**：待填写
- **原因分析**：待填写
- **预期**：表有 14 个字段，外键约束阻止非法 tag，合法插入成功

---

## [2026-06-02 21:00] 测试2: source_agent.py — check_coverage 单元测试

- **测试方案**：构造 3 天 mock 简报数据，调用 `check_coverage(pool=None)` 的 mock 路径
- **测试数据**：
  ```python
  # Mock 3 天数据：
  # Day1: LLM=5, Agent=3, RAG=0, 体育=2, Python=0
  # Day2: LLM=6, Agent=4, RAG=1, 体育=1, Python=0
  # Day3: LLM=7, Agent=5, RAG=0, 体育=1, Python=0
  # 期望：RAG(avg=0.3, red), Python(avg=0, red) 被标记为低覆盖
  #       体育(avg=1.3, red) 也被标记
  #       LLM/Agent 正常
  ```
- **测试结果**：待填写
- **原因分析**：待填写
- **预期**：low_coverage 列表含 RAG/Python/体育，不含 LLM/Agent

---

## [2026-06-02 21:30] 测试3: source_agent.py — search_sources 测试

- **测试方案**：调用 `search_sources("体育", "体育")` → 验证 LLM 返回 RSS 源列表
- **测试数据**：输入 tag=体育, label_zh=体育
- **测试结果**：待填写
- **原因分析**：待填写
- **预期**：返回 3-5 个候选 RSS 源，每个含 name/url/rss_url/reason

---

## [2026-06-02 22:00] 测试4: source_agent.py — evaluate_source 测试

- **测试方案**：
  1. 给一个真实可访问的 RSS URL → 验证评分 > 0
  2. 给一个不可达的 URL → 验证返回 quality=0
- **测试数据**：
  - 有效 URL: `https://www.espn.com/espn/rss/news`
  - 无效 URL: `http://notexist.example.com/rss`
- **测试结果**：待填写
- **原因分析**：待填写
- **预期**：有效 URL 4 项评分在 1-5 范围；无效 URL 返回 quality=0 + 错误信息

---

## [2026-06-02 22:30] 测试5: source_agent.py — discover_sources 集成测试

- **测试方案**：连真实 DB → 调用 `discover_sources(pool)` → 验证全流程
- **测试数据**：使用数据库中真实简报数据
- **测试结果**：待填写
- **原因分析**：待填写
- **预期**：
  - checked_tags=19
  - low_coverage≥0（取决于实际数据）
  - 低覆盖标签有对应推荐写入 DB
  - 返回 found_sources/recommended 计数

---

## [2026-06-02 23:00] 测试6: sources_api.py — API 端点测试

- **测试方案**：启动 module-c → curl 4 个端点
- **测试数据**：
  ```bash
  curl http://localhost:8003/api/sources/health
  curl http://localhost:8003/api/sources/recommendations?status=pending
  curl -X POST http://localhost:8003/api/sources/{id}/approve
  curl -X POST http://localhost:8003/api/sources/{id}/reject
  ```
- **测试结果**：待填写
- **原因分析**：待填写
- **预期**：
  - health → 200 + 19 标签 + health 颜色字段
  - recommendations → 200 + 待审列表
  - approve → 200 + status 变为 approved
  - reject → 200 + status 变为 rejected

---

## [2026-06-02 23:30] 测试7: main.py 路由注册

- **测试方案**：重启 module-c → `/health` + `/api/sources/health` 全部访问
- **测试数据**：curl 多个端点
- **测试结果**：待填写
- **原因分析**：待填写
- **预期**：所有路由 200，import 无报错

---

## [2026-06-03 00:00] 测试8: api.js 信源方法

- **测试方案**：小程序控制台调用 `api.getSourceHealth()` 等方法
- **测试数据**：实际调用返回值
- **测试结果**：待填写
- **原因分析**：待填写
- **预期**：返回数据结构与后端 API 一致

---

## [2026-06-03 00:30] 测试9: mine 页面信源健康度渲染

- **测试方案**：编译小程序 → 打开"我的"页 → 查看信源健康度卡片
- **测试数据**：19 个标签的健康数据
- **测试结果**：待填写
- **原因分析**：待填写
- **预期**：
  - 信源健康度卡片在推送订阅下方
  - 每个标签显示绿/黄/红圆点 + 日均条数
  - 覆盖不足标签显示警告文字

---

## [2026-06-03 01:00] 测试10: 全链路联调

- **测试方案**：
  1. 启动所有服务
  2. 手动调用 `discover_sources(pool)` 触发现有覆盖检查
  3. 验证 low_coverage 标签有推荐
  4. Dashboard/API approve 一个推荐源
  5. 确认 RSS_SOURCES 配置文件更新（或手动更新）
- **测试数据**：真实数据全链路
- **测试结果**：待填写
- **原因分析**：待填写
- **预期**：Agent 发现 → 推荐 → 审批 → 可用的完整闭环

---

## [2026-06-03 01:30] 测试11: 异常场景

- **测试方案**：
  1. 停 DB → 验证 API 返回 503 + 错误信息
  2. 断网 → 验证 evaluate_source 不崩溃
  3. LLM API 不可用 → 验证 check_coverage 仍可工作（纯 SQL）
  4. recommended_sources 表为空 → 验证返回空数组不报错
- **测试数据**：各种故障注入
- **测试结果**：待填写
- **原因分析**：待填写
- **预期**：所有场景有降级处理，不崩溃

---

## 测试总结

| 测试项 | 状态 | 关键发现 |
|---|---|---|
| 环境检查 | 待填写 | 待填写 |
| 测试1: 建表 | 待填写 | 待填写 |
| 测试2: coverage | 待填写 | 待填写 |
| 测试3: search | 待填写 | 待填写 |
| 测试4: evaluate | 待填写 | 待填写 |
| 测试5: discover | 待填写 | 待填写 |
| 测试6: API | 待填写 | 待填写 |
| 测试7: 路由 | 待填写 | 待填写 |
| 测试8: api.js | 待填写 | 待填写 |
| 测试9: mine页 |待填写 | 待填写 |
| 测试10: 全链路 | 待填写 | 待填写 |
| 测试11: 异常 | 待填写 | 待填写 |

**最终结论**：待测试完成后填写
