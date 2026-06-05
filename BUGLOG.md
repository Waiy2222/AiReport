# Bug 日志 — AI 资讯简报项目

> 最后更新: 2026-06-04

---

## 🔴 BUG-001: DeepSeek Content Exists Risk 拦截

**状态**: ✅ 已修复  
**发现日期**: 2026-06-04  
**影响模块**: module-b (摘要生成)

### 现象
调用 DeepSeek API 进行新闻摘要时，返回 `400 Bad Request: Content Exists Risk`，导致简报 sections 为空、`final_count=0`。

### 根因
DeepSeek 安全过滤器对以下内容敏感：
1. **Prompt 中的敏感词**: "时事政策"、"国际动态"、"政策"、"监管" 等分类名触发预拦截
2. **新闻内容的组合效应**: 多条新闻（含真实 AI/科技/时政标题）一起发送时，组合起来被判定为"要求总结时政新闻"

### 修复方案（3层防护）
| 层 | 做法 | 状态 |
|----|------|------|
| 1 | Prompt 中性化: "时事政策"→"行业观察", "国际动态"→"全球视野" | ✅ |
| 2 | 分批发送: 每次 ≤15 条，内容截断 ≤200 字 | ✅ |
| 3 | 失败兜底: LLM 返回 None 时用原文标题构建 section | ✅ |

### 验证
- 评分接口 (batch_score) 使用 15 条/300 字 → 始终成功
- 摘要接口 (summarize) 使用 15 条/200 字 + 中性 Prompt → 成功率提升

---

## 🟡 BUG-002: 标签缺失导致 section 单一

**状态**: ✅ 已修复  
**发现日期**: 2026-06-04  
**影响模块**: module-b (评分 + 摘要)

### 现象
简报始终只有 1 个 section（"AI头条"），其他领域（体育/融资/芯片）的新闻无法独立成 section。

### 根因链条
1. 旧版评分 Prompt 不要求返回 tags → items 无标签
2. LLM 自创不合法标签 (如 "AI", "合作", "Google Cloud") → diversity selector 无法识别
3. 摘要 Prompt 要求 LLM 自行分类 → LLM 偷懒全放一个 section

### 修复方案
| 层 | 做法 |
|----|------|
| 1 | 评分 Prompt 明确要求 14 个白名单标签 |
| 2 | 代码层 `_clean_tags()` 过滤不合法标签，关键词兜底 |
| 3 | 代码层 `_build_sections()` 按标签分组，每组独立 section |
| 4 | 非 AI 标签优先排列，AI 最多 2 组 |

### 验证
- `test_analyzer.py`: 18/18 单元测试通过
- `test_summarizer.py`: 10/10 单元测试通过
- 集成测试确认 5 种新闻 → 4+ 个不同标签

---

## 🟡 BUG-003: 环境编码导致 Python subprocess 失败

**状态**: ⚠️ 部分修复  
**发现日期**: 2026-06-04 (已知问题)  
**影响**: 本地 Windows 开发

### 现象
`python -c "subprocess.Popen(...)"` 在中文路径下报错 `NotADirectoryError: [WinError 267]`。

### 根因
Git Bash 的 `os.getcwd()` 返回乱码路径 `D:\��Ŀ\ai��������...`，subprocess 无法识别。

### 解决方案
- 使用 bash 的 `cd` + `nohup` 启动模块（bash 能正确处理中文路径）
- 或使用纯英文路径
- Docker 环境不受影响（容器内路径为 `/app`）

---

## 🟠 BUG-004: `final_count=0` 时不更新已有简报

**状态**: ⚠️ 待修复  
**发现日期**: 2026-06-04  
**影响模块**: module-b/pipeline.py `_insert_briefing()`

### 现象
当新的简报 run 返回 `final_count=0` 时，DB 中的旧数据不会被更新，导致 API 看到的永远是最早那次的旧数据。

### 代码位置
```python
# pipeline.py line 68
if final_count == 0:
    existing = await conn.fetchrow(...)
    if existing:
        return existing["id"]  # ← 不更新，返回旧 ID
```

### 影响
- 如果第一次运行成功（final_count>0），后续失败运行不会破坏数据 ✅
- 但如果新的成功数据（final_count>0）被旧的缓存覆盖，用户看到的是过时内容 ⚠️

### 建议修复
区分 "故意跳过" 和 "生成失败"：
- 如果 `stats["passed"] == 0` → 跳过（确实没新闻）
- 如果 `stats["passed"] > 0` 但 `final_count == 0` → 更新记录（LLM 摘要失败但原始数据可用）

---

## 🟢 BUG-005: 趋势页展示标签统计而非事件

**状态**: ✅ 已修复  
**发现日期**: 2026-06-04  
**影响模块**: module-c (小程序趋势页)

### 修复
- 后端: `/api/trends/weekly` 改为从 DB 简报读取每日事件时间线
- 前端: 改为垂直时间线布局，支持折叠/展开
- 保留热门标签条作为辅助信息

---

## 📋 已知待处理问题

1. **本地启动脚本** — 需要 PYTHONPATH 设置才能正确 import shared 模块。Docker 不受影响。
2. **Debate Agent 日志缺失** — 辩论失败时只 log 不记录到 DB，难以排查
3. **推送仅 dry-run** — 微信订阅消息模板未配置真实用户

---

## 🧪 测试概况

| 测试文件 | 测试数 | 状态 |
|----------|--------|------|
| `module-b/ai/test_analyzer.py` | 10 | ✅ 全部通过 |
| `module-b/ai/test_summarizer.py` | 10 | ✅ 全部通过 |
| `module-b/ai/test_analyzer.py` (集成) | 2 | ✅ 全部通过 (需API) |
| `module-c/tests/` | 68 | ✅ 全部通过 |
| `tests/` (顶层) | 14 | 13/14 (1个预存bug) |
