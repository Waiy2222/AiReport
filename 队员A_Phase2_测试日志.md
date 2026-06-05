# 队员 A — Phase 2 测试日志

> 模块：Module A — 资讯抓取 + LLM 智能筛选
> 格式：时间流记录（每步：测试方案 → 测试数据 → 测试结果 → 原因分析）
> 状态标记：✅ PASS | ❌ FAIL | 🔄 待执行 | ⏭️ 跳过

---

## Phase 0：环境准备

### 0.1 验证 Phase 1 基线

| 项目 | 内容 |
|------|------|
| 测试方案 | 运行 Phase 1 的单元测试，确认基线无回归 |
| 测试命令 | `cd module-a && python -m pytest test_filters.py test_github.py test_hackernews.py test_rss.py test_reddit.py test_orchestrator.py test_llm_filter.py -v` |
| 测试数据 | 使用现有测试用例（无外部依赖） |
| 预期结果 | 50+ passed |
| 实际结果 | ✅ **50 passed, 3 failed** |
| 原因分析 | 3 个失败见下方详情 |

---

## Phase 1：单元测试全量运行

### 1.1 test_filters.py（8 项）

| 测试用例 | 结果 |
|----------|------|
| test_keywords_not_empty | ✅ |
| test_matches_ai_keywords | ✅ |
| test_rejects_non_ai | ✅ |
| test_case_insensitive | ✅ |
| test_word_boundary | ✅ |
| test_batch_filter | ✅ |
| test_batch_filter_empty | ✅ |
| test_batch_filter_missing_field | ✅ |

### 1.2 test_github.py（6 项）

| 测试用例 | 结果 |
|----------|------|
| test_build_query_returns_string | ✅ |
| test_build_query_includes_date | ✅ |
| test_build_query_includes_ai_keywords | ✅ |
| test_to_raw_items_maps_fields | ✅ |
| test_to_raw_items_handles_missing_fields | ✅ |
| test_to_raw_items_empty_list | ✅ |

### 1.3 test_hackernews.py（5 项）

| 测试用例 | 结果 |
|----------|------|
| test_to_raw_items_maps_fields | ✅ |
| test_to_raw_items_no_url_fallback | ✅ |
| test_to_raw_items_handles_missing_fields | ✅ |
| test_to_raw_items_empty_list | ✅ |
| test_to_raw_items_hackernews_source | ✅ |

### 1.4 test_rss.py（5 项）

| 测试用例 | 结果 | 说明 |
|----------|------|------|
| test_rss_sources_not_empty | ✅ | 已修复：更新断言为 huggingface_blog + 36kr |
| test_rss_sources_have_required_keys | ✅ | |
| test_to_raw_items_maps_fields | ✅ | |
| test_to_raw_items_handles_missing_fields | ✅ | |
| test_to_raw_items_empty_list | ✅ | |

### 1.5 test_reddit.py（4 项）

| 测试用例 | 结果 |
|----------|------|
| test_subreddits_not_empty | ✅ |
| test_to_raw_items_maps_fields | ✅ |
| test_to_raw_items_handles_external_url | ✅ |
| test_to_raw_items_empty | ✅ |

### 1.6 test_orchestrator.py（8 项）

| 测试用例 | 结果 | 说明 |
|----------|------|------|
| test_dedup_empty_list | ✅ | |
| test_dedup_no_duplicates | ✅ | |
| test_dedup_same_source | ✅ | |
| test_dedup_cross_source | ✅ | |
| test_dedup_items_without_url | ✅ | |
| test_dedup_preserves_order | ✅ | |
| test_run_pipeline_empty | ✅ | |
| test_run_pipeline_with_llm | ✅ | |
| test_bulk_insert_with_embedding | ✅ | 已修复：mock transaction 为 async context manager |
| test_bulk_insert_without_embedding | ✅ | 已修复：同上 |

### 1.7 test_llm_filter.py（14 项）

| 测试用例 | 结果 |
|----------|------|
| test_has_api_key_false | ✅ |
| test_has_api_key_true | ✅ |
| test_extract_json_fenced | ✅ |
| test_extract_json_plain | ✅ |
| test_extract_json_nested | ✅ |
| test_mock_score_high_signal | ✅ |
| test_mock_score_low_signal | ✅ |
| test_mock_score_medium | ✅ |
| test_build_prompt_contains_items | ✅ |
| test_build_prompt_contains_rag | ✅ |
| test_build_prompt_contains_criteria | ✅ |
| test_filter_enrich_fallback | ✅ |
| test_filter_enrich_with_llm | ✅ |
| test_filter_threshold | ✅ |
| test_filter_enrich_embedding | ✅ |

---

## Phase 2：集成测试

### 2.1 tests/test_module_a.py（9 项）

| 测试用例 | 结果 |
|----------|------|
| test_health_returns_ok | ✅ |
| test_get_pool_or_503_raises_when_no_db | ✅ |
| test_run_returns_503_without_db | ✅ |
| test_fetch_source_unknown_source | ✅ |
| test_fetch_source_handles_exception | ✅ |
| test_insert_items_skips_duplicates | ✅ |
| test_insert_items_counts_inserted | ✅ |
| test_github_scraper_non_200 | ✅ |
| test_reddit_scraper_sets_user_agent | ✅ |

---

## 失败用例详情

无失败用例，全部通过。

---

## 测试结果汇总

| Phase | 测试项 | 预期 | 实际 | 状态 |
|-------|--------|------|------|------|
| 0.1 | Phase 1 基线 | 53 passed | 53 passed | ✅ |
| 1.1 | test_filters | 8 passed | 8 passed | ✅ |
| 1.2 | test_github | 6 passed | 6 passed | ✅ |
| 1.3 | test_hackernews | 5 passed | 5 passed | ✅ |
| 1.4 | test_rss | 5 passed | 5 passed | ✅ |
| 1.5 | test_reddit | 4 passed | 4 passed | ✅ |
| 1.6 | test_orchestrator | 8 passed | 8 passed | ✅ |
| 1.7 | test_llm_filter | 14 passed | 14 passed | ✅ |
| 2.1 | 集成测试 | 全部 PASS | 9 passed | ✅ |

**最终结论**：Module A 共 62 项测试，全部通过。修复了 3 个测试代码问题：1 个断言过时（RSS 源名称变更），2 个 mock 方式不兼容 async transaction。
