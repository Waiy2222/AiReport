# 队员 A — Phase 2 测试日志

> 模块：Module A — 资讯抓取 + LLM 智能筛选
> 格式：时间流记录（每步：测试方案 → 测试数据 → 测试结果 → 原因分析）
> 状态标记：✅ PASS | ❌ FAIL | 🔄 待执行

---

## Phase 0：环境准备

### 0.1 验证 Phase 1 基线

| 项目 | 内容 |
|------|------|
| 测试方案 | 运行 Phase 1 的 34 个单元测试，确认基线无回归 |
| 测试命令 | `cd module-a && python -m pytest test_filters.py test_github.py test_hackernews.py test_rss.py test_reddit.py test_orchestrator.py -v` |
| 测试数据 | 使用现有测试用例（无外部依赖） |
| 预期结果 | 34 passed, 0 failed |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 0.2 验证集成测试基线

| 项目 | 内容 |
|------|------|
| 测试方案 | 运行 `tests/test_module_a.py`，确认集成测试基线 |
| 测试命令 | `python -m pytest tests/test_module_a.py -v` |
| 测试数据 | Mock 数据（无真实 DB） |
| 预期结果 | 全部 PASS（需确认当前状态，可能因 Phase 1 合并有变化） |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

---

## Phase 1：scrapers/__init__.py 恢复

### 1.1 RED — 写 _insert_items 测试

| 项目 | 内容 |
|------|------|
| 测试方案 | 写 `test_insert_items_*` 测试用例 |
| 测试数据 | Mock pool + Mock conn.fetchval |
| 预期结果 | 测试 FAIL（`_insert_items` 不存在） |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 1.2 GREEN — 实现 _insert_items + SCRAPERS

| 项目 | 内容 |
|------|------|
| 测试方案 | 实现 `_insert_items` + `SCRAPERS` 注册表，运行测试 |
| 测试命令 | `python -m pytest tests/test_module_a.py::test_insert_items_skips_duplicates tests/test_module_a.py::test_insert_items_counts_inserted -v` |
| 测试数据 | Mock pool（conn.fetchval 返回 None 或 UUID） |
| 预期结果 | 2 passed |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 1.3 验证 SCRAPERS 注册

| 项目 | 内容 |
|------|------|
| 测试方案 | 验证 SCRAPERS 包含 4 个源，每个值可调用 |
| 测试命令 | `python -c "from scrapers import SCRAPERS; print(len(SCRAPERS), all(callable(v) for v in SCRAPERS.values()))"` |
| 测试数据 | 无 |
| 预期结果 | `4 True` |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

---

## Phase 2：Scraper fetch 包装函数

### 2.1 github.py — 添加 fetch 包装

| 项目 | 内容 |
|------|------|
| 测试方案 | 验证 `fetch` 函数存在且行为与 `fetch_github` 一致 |
| 测试命令 | `python -c "from scrapers.github import fetch; print(callable(fetch))"` |
| 测试数据 | 无 |
| 预期结果 | `True` |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 2.2 hackernews.py — 检查量 100→300 + fetch 包装

| 项目 | 内容 |
|------|------|
| 测试方案 | 1) 验证 `get_top_stories` 默认 limit 2) 验证 `fetch` 存在 |
| 测试数据 | Mock httpx 响应 |
| 预期结果 | limit=300, fetch 可调用 |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 2.3 rss.py + reddit.py — fetch 包装

| 项目 | 内容 |
|------|------|
| 测试方案 | 验证两个模块的 `fetch` 函数存在 |
| 测试命令 | `python -c "from scrapers.rss import fetch; from scrapers.reddit import fetch"` |
| 测试数据 | 无 |
| 预期结果 | 无 ImportError |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 2.4 集成测试 — fetch 包装后

| 项目 | 内容 |
|------|------|
| 测试方案 | 运行集成测试中引用 SCRAPERS 的用例 |
| 测试命令 | `python -m pytest tests/test_module_a.py -v` |
| 测试数据 | Mock |
| 预期结果 | 全部 PASS |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

---

## Phase 3：llm_filter.py 核心实现（TDD）

### 3.1 RED — 写全部 llm_filter 测试

| 项目 | 内容 |
|------|------|
| 测试方案 | 写 `test_llm_filter.py` 的 14 个测试用例 |
| 测试数据 | 见下方测试数据表 |
| 预期结果 | 全部 FAIL（模块不存在） |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

**测试数据表：**

| 测试用例 | 输入数据 |
|----------|----------|
| `test_has_api_key_false` | `os.environ.pop("DEEPSEEK_API_KEY")` |
| `test_has_api_key_true` | `os.environ["DEEPSEEK_API_KEY"] = "sk-test123"` |
| `test_extract_json_fenced` | `"```json\n[{\"index\":0}]\n```"` |
| `test_extract_json_plain` | `"[{\"index\":0}]"` |
| `test_extract_json_nested` | `"some text [{\"index\":0,\"data\":{\"score\":8}}] end"` |
| `test_mock_score_high` | `{"title":"DeepSeek-V4开源发布","content":"重大突破","source":"github"}` |
| `test_mock_score_low` | `{"title":"Best hiking trails","content":"California","source":"rss"}` |
| `test_mock_score_medium` | `{"title":"Python web framework released","content":"new version","source":"hackernews"}` |
| `test_build_prompt` | 2 items + rag_context string |
| `test_filter_enrich_fallback` | pool mock, 3 items, no API key |
| `test_filter_enrich_threshold` | pool mock, items with mixed mock scores, threshold=8.0 |
| `test_filter_enrich_embedding` | pool mock, Mock generate_embeddings_batch |
| `test_get_rag_context` | Mock pool + Mock search_similar_items |
| `test_extract_json_empty` | `""` → 返回空字符串 |

### 3.2 GREEN — 实现 _has_api_key + _extract_json

| 项目 | 内容 |
|------|------|
| 测试方案 | 实现 `_has_api_key` 和 `_extract_json`，运行对应测试 |
| 测试命令 | `python -m pytest test_llm_filter.py -k "has_api_key or extract_json" -v` |
| 测试数据 | 同 3.1 |
| 预期结果 | 4 passed（false, true, fenced, plain, nested, empty） |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 3.3 GREEN — 实现 _mock_score_one

| 项目 | 内容 |
|------|------|
| 测试方案 | 实现启发式评分，运行 mock_score 测试 |
| 测试命令 | `python -m pytest test_llm_filter.py -k "mock_score" -v` |
| 测试数据 | 高信号/低信号/中等信号条目 |
| 预期结果 | 3 passed |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 3.4 GREEN — 实现 _build_filter_prompt

| 项目 | 内容 |
|------|------|
| 测试方案 | 实现 prompt 构建，验证包含条目 + RAG + 标准 |
| 测试命令 | `python -m pytest test_llm_filter.py -k "build_prompt" -v` |
| 测试数据 | 2 items + rag_context |
| 预期结果 | 1 passed |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 3.5 GREEN — 实现 _get_rag_context

| 项目 | 内容 |
|------|------|
| 测试方案 | Mock `search_similar_items`，验证上下文组装 |
| 测试命令 | `python -m pytest test_llm_filter.py -k "rag_context" -v` |
| 测试数据 | Mock 返回 3 条相似条目 |
| 预期结果 | 1 passed |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 3.6 GREEN — 实现 filter_and_enrich 主函数

| 项目 | 内容 |
|------|------|
| 测试方案 | 实现主函数，运行剩余测试 |
| 测试命令 | `python -m pytest test_llm_filter.py -k "filter_enrich" -v` |
| 测试数据 | Mock pool + Mock embedding |
| 预期结果 | 4 passed |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 3.7 REFACTOR — 清理 llm_filter.py

| 项目 | 内容 |
|------|------|
| 测试方案 | 重构后运行全部 llm_filter 测试，确认无回归 |
| 测试命令 | `python -m pytest test_llm_filter.py -v` |
| 测试数据 | 同上 |
| 预期结果 | 14 passed |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

---

## Phase 4：orchestrator.py 更新（TDD）

### 4.1 RED — 写 run_pipeline 测试

| 项目 | 内容 |
|------|------|
| 测试方案 | 写 `test_run_pipeline_*` 测试用例 |
| 测试数据 | Mock scrapers + Mock llm_filter |
| 预期结果 | FAIL（`run_pipeline` 不存在） |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 4.2 GREEN — 实现 run_pipeline

| 项目 | 内容 |
|------|------|
| 测试方案 | 实现 `run_pipeline`，运行测试 |
| 测试命令 | `python -m pytest test_orchestrator.py -k "pipeline" -v` |
| 测试数据 | Mock 全链路 |
| 预期结果 | 全部 PASS |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 4.3 更新 bulk_insert 支持 embedding

| 项目 | 内容 |
|------|------|
| 测试方案 | 写 `test_bulk_insert_with_embedding`，验证 SQL 参数 |
| 测试数据 | items 含 embedding=[0.1, 0.2, ...] |
| 预期结果 | executemany 被调用，参数含 embedding |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 4.4 验证现有 dedup 测试无回归

| 项目 | 内容 |
|------|------|
| 测试方案 | 运行全部 orchestrator 测试 |
| 测试命令 | `python -m pytest test_orchestrator.py -v` |
| 测试数据 | 同 Phase 1 |
| 预期结果 | 原有 6 个 + 新增 2-3 个 = 全部 PASS |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

---

## Phase 5：main.py 更新

### 5.1 恢复 _get_pool_or_503 + _fetch_source

| 项目 | 内容 |
|------|------|
| 测试方案 | 运行集成测试中引用这些函数的用例 |
| 测试命令 | `python -m pytest tests/test_module_a.py::test_get_pool_or_503_raises_when_no_db tests/test_module_a.py::test_run_returns_503_without_db tests/test_module_a.py::test_fetch_source_unknown_source -v` |
| 测试数据 | Mock |
| 预期结果 | 3 passed |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 5.2 更新 /run 返回 llm_filtered

| 项目 | 内容 |
|------|------|
| 测试方案 | Mock `run_pipeline`，验证响应含 `llm_filtered` 字段 |
| 测试数据 | Mock 返回 `{"fetched": 10, "llm_filtered": True, "per_source": {...}}` |
| 预期结果 | 响应 JSON 含 `llm_filtered: true` |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 5.3 全量集成测试

| 项目 | 内容 |
|------|------|
| 测试方案 | 运行 `tests/test_module_a.py` 全部用例 |
| 测试命令 | `python -m pytest tests/test_module_a.py -v` |
| 测试数据 | Mock |
| 预期结果 | 全部 PASS |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

---

## Phase 6：requirements.txt 更新

### 6.1 安装 openai 依赖

| 项目 | 内容 |
|------|------|
| 测试方案 | 安装 openai 并验证导入 |
| 测试命令 | `pip install openai>=1.12.0 && python -c "from openai import AsyncOpenAI; print('OK')"` |
| 测试数据 | 无 |
| 预期结果 | `OK` |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

---

## Phase 7：全量回归测试

### 7.1 单元测试全量

| 项目 | 内容 |
|------|------|
| 测试方案 | 运行 module-a 下全部测试文件 |
| 测试命令 | `cd module-a && python -m pytest test_filters.py test_github.py test_hackernews.py test_rss.py test_reddit.py test_orchestrator.py test_llm_filter.py -v` |
| 测试数据 | 全部 Mock |
| 预期结果 | ~48 passed（原 34 + 新 ~14），0 failed |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 7.2 集成测试全量

| 项目 | 内容 |
|------|------|
| 测试方案 | 运行 `tests/test_module_a.py` |
| 测试命令 | `python -m pytest tests/test_module_a.py -v` |
| 测试数据 | Mock |
| 预期结果 | 全部 PASS |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

---

## Phase 8：集成验证（需 PostgreSQL + pgvector）

### 8.1 启动数据库

| 项目 | 内容 |
|------|------|
| 测试方案 | 启动 pgvector 容器 + 导入 schema |
| 测试命令 | `docker run -d --name pg-vector -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ai_news pgvector/pgvector:pg16` 然后 `psql -f contracts/schema.sql && psql -f contracts/schema_v2.sql && psql -f contracts/seed_data_v2.sql` |
| 测试数据 | seed_data_v2.sql 假数据 |
| 预期结果 | 容器 healthy，表创建成功 |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 8.2 启动 Module A 服务

| 项目 | 内容 |
|------|------|
| 测试方案 | 启动 FastAPI 服务 |
| 测试命令 | `cd module-a && uvicorn main:app --port 8001` |
| 测试数据 | 无 |
| 预期 | 服务启动无报错 |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 8.3 /health 端点

| 项目 | 内容 |
|------|------|
| 测试方案 | GET /health |
| 测试命令 | `curl http://localhost:8001/health` |
| 测试数据 | 无 |
| 预期结果 | `{"status":"ok","db":"connected"}` |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 8.4 /run 端点（无 API Key 回退模式）

| 项目 | 内容 |
|------|------|
| 测试方案 | POST /run（不设 DEEPSEEK_API_KEY，走启发式评分） |
| 测试命令 | `curl -X POST http://localhost:8001/run -H "Content-Type: application/json" -d '{"batch_id":"550e8400-e29b-41d4-a716-446655440000","hours_back":24}'` |
| 测试数据 | batch_id = 550e8400-e29b-41d4-a716-446655440000 |
| 预期结果 | `{"status":"ok","fetched":N,"llm_filtered":false,...}` (N >= 0) |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 8.5 /run 端点（有 API Key LLM 模式）

| 项目 | 内容 |
|------|------|
| 测试方案 | POST /run（设 DEEPSEEK_API_KEY，走 LLM 评分） |
| 测试命令 | `DEEPSEEK_API_KEY=sk-xxx curl -X POST http://localhost:8001/run -H "Content-Type: application/json" -d '{"batch_id":"660e8400-e29b-41d4-a716-446655440001","hours_back":24}'` |
| 测试数据 | 真实 API Key |
| 预期结果 | `{"status":"ok","fetched":N,"llm_filtered":true,...}` |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 8.6 数据库验证 — ai_score 写入

| 项目 | 内容 |
|------|------|
| 测试方案 | 查 raw_items 的 metadata 中 ai_score 字段 |
| 测试命令 | `psql -d ai_news -c "SELECT source, title, metadata->>'ai_score' as score FROM raw_items ORDER BY fetched_at DESC LIMIT 10;"` |
| 测试数据 | /run 写入的数据 |
| 预期结果 | 每条有 ai_score 值（1-10） |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 8.7 数据库验证 — embedding 写入

| 项目 | 内容 |
|------|------|
| 测试方案 | 查 raw_items 的 embedding 列 |
| 测试命令 | `psql -d ai_news -c "SELECT count(*) FROM raw_items WHERE embedding IS NOT NULL;"` |
| 测试数据 | /run 写入的数据 |
| 预期结果 | count > 0 |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 8.8 数据库验证 — tags 写入

| 项目 | 内容 |
|------|------|
| 测试方案 | 查 raw_items 的 metadata 中 tags 字段 |
| 测试命令 | `psql -d ai_news -c "SELECT title, metadata->>'tags' FROM raw_items WHERE metadata->>'tags' IS NOT NULL LIMIT 5;"` |
| 测试数据 | /run 写入的数据 |
| 预期结果 | 每条有 tags 数组 |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

---

## 测试结果汇总

| Phase | 测试项 | 预期 | 实际 | 状态 |
|-------|--------|------|------|------|
| 0.1 | Phase 1 基线 | 34 passed | — | 🔄 |
| 0.2 | 集成测试基线 | 全部 PASS | — | 🔄 |
| 1.1 | _insert_items RED | FAIL | — | 🔄 |
| 1.2 | _insert_items GREEN | 2 passed | — | 🔄 |
| 1.3 | SCRAPERS 注册 | 4 True | — | 🔄 |
| 2.1 | github fetch 包装 | True | — | 🔄 |
| 2.2 | HN 300 + fetch | limit=300 | — | 🔄 |
| 2.3 | rss+reddit fetch | 无 ImportError | — | 🔄 |
| 2.4 | 集成测试 fetch | 全部 PASS | — | 🔄 |
| 3.1 | llm_filter RED | 全部 FAIL | — | 🔄 |
| 3.2 | api_key + extract_json | 4 passed | — | 🔄 |
| 3.3 | mock_score | 3 passed | — | 🔄 |
| 3.4 | build_prompt | 1 passed | — | 🔄 |
| 3.5 | rag_context | 1 passed | — | 🔄 |
| 3.6 | filter_and_enrich | 4 passed | — | 🔄 |
| 3.7 | REFACTOR | 14 passed | — | 🔄 |
| 4.1 | run_pipeline RED | FAIL | — | 🔄 |
| 4.2 | run_pipeline GREEN | 全部 PASS | — | 🔄 |
| 4.3 | bulk_insert embedding | PASS | — | 🔄 |
| 4.4 | dedup 无回归 | 全部 PASS | — | 🔄 |
| 5.1 | 恢复函数 | 3 passed | — | 🔄 |
| 5.2 | llm_filtered 字段 | 含 true | — | 🔄 |
| 5.3 | 集成测试全量 | 全部 PASS | — | 🔄 |
| 6.1 | openai 安装 | OK | — | 🔄 |
| 7.1 | 单元测试全量 | ~48 passed | — | 🔄 |
| 7.2 | 集成测试全量 | 全部 PASS | — | 🔄 |
| 8.1 | DB 启动 | healthy | — | 🔄 |
| 8.2 | 服务启动 | 无报错 | — | 🔄 |
| 8.3 | /health | ok+connected | — | 🔄 |
| 8.4 | /run 回退模式 | status ok | — | 🔄 |
| 8.5 | /run LLM 模式 | llm_filtered true | — | 🔄 |
| 8.6 | ai_score 写入 | 非空 | — | 🔄 |
| 8.7 | embedding 写入 | count > 0 | — | 🔄 |
| 8.8 | tags 写入 | 非空 | — | 🔄 |

---

## Phase 9：设计优化验证（可选）

### 9.1 embedding 缓存复用

| 项目 | 内容 |
|------|------|
| 测试方案 | Mock `generate_embeddings_batch`，验证 `_get_rag_context` 返回的 `cached_embs` 被 `filter_and_enrich` 复用 |
| 测试数据 | 3 个 items，其中 2 个在 RAG 阶段已生成 embedding |
| 预期结果 | `generate_embeddings_batch` 第二次调用时，已缓存的条目不重复请求 |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 9.2 关键词粗筛效果

| 项目 | 内容 |
|------|------|
| 测试方案 | 统计 scraper 输出的条目数 vs LLM 筛选后的条目数 |
| 测试命令 | `/run` 端点返回的 `per_source` 与 `fetched` 对比 |
| 测试数据 | 真实 API 抓取 |
| 预期结果 | 粗筛后条目数 < 原始抓取数的 40%（削减 60%+） |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

### 9.3 bulk_insert ON CONFLICT

| 项目 | 内容 |
|------|------|
| 测试方案 | 重复插入同 URL 的条目，验证 ON CONFLICT 生效 |
| 测试数据 | 同 URL 不同 batch_id 的 2 条 item |
| 预期结果 | 第 2 条被静默跳过，不报错 |
| 实际结果 | 🔄 待执行 |
| 原因分析 | — |

---

## Bug 记录

| # | 发现阶段 | 现象 | 原因 | 修复 | 状态 |
|---|----------|------|------|------|------|
| — | — | — | — | — | — |

---

## 总结

| 指标 | 数值 |
|------|------|
| 新增文件 | 2 (llm_filter.py, test_llm_filter.py) |
| 修改文件 | 8 (main.py, orchestrator.py, __init__.py, github.py, hackernews.py, rss.py, reddit.py, requirements.txt) |
| 新增测试 | ~15 (llm_filter) + 4 (orchestrator 新增) = ~19 |
| 原有测试 | 34 (单元) + 8 (集成) |
| 总测试 | ~61 |
| 调试检测点 | 10 (llm_filter) + 7 (main) + 6 (orchestrator) + 5 (__init__) + 3 (github) + 3 (hackernews) + 3 (rss) + 2 (reddit) = 39 |
| 设计优化 | 5 项（embedding 缓存、关键词粗筛、shared 提取、_insert_items 移出、ON CONFLICT） |
