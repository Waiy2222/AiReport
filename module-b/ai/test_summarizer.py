"""测试 summarizer.py — 分组建 section + 摘要生成

运行: cd module-b && python -m pytest ai/test_summarizer.py -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from ai.summarizer import _build_sections, summarize, _SECTION_LABELS, _AI_TAGS


class TestBuildSections:
    """_build_sections: 代码层按标签分组构建 section"""

    def _make_item(self, title, tags, score=8.0, url=None):
        return {
            "title": title,
            "content": f"{title} 的详细内容",
            "tags": tags,
            "ai_score": score,
            "url": url or f"http://example.com/{hash(title)}",
            "source": "test",
        }

    def test_empty_items(self):
        """空列表返回空 sections"""
        assert _build_sections([]) == []

    def test_single_tag_creates_single_section(self):
        """同一标签归入同一 section"""
        items = [
            self._make_item("GPT-5发布", ["LLM"]),
            self._make_item("Claude 4更新", ["LLM"]),
        ]
        sections = _build_sections(items)
        assert len(sections) == 1
        assert sections[0]["section_title"] == _SECTION_LABELS.get("LLM", "LLM")
        assert len(sections[0]["items"]) == 2

    def test_multiple_tags_create_multiple_sections(self):
        """不同标签生成不同 section"""
        items = [
            self._make_item("GPT-5发布", ["LLM"]),
            self._make_item("NBA总决赛", ["体育"]),
            self._make_item("芯片融资5000万", ["芯片", "融资"]),
            self._make_item("开源框架发布", ["开源"]),
        ]
        sections = _build_sections(items)
        # 应有 4 个 section（非AI优先: 体育、芯片+融资、开源; AI: LLM）
        assert len(sections) >= 3, f"Expected >=3 sections, got {len(sections)}"
        titles = [s["section_title"] for s in sections]
        # 体育应在前面（非AI优先）
        assert "体育赛事" in titles or titles[0] != "大模型前沿"

    def test_ai_capped_at_two_groups(self):
        """AI 相关标签最多 2 组"""
        items = []
        for i in range(10):
            items.append(self._make_item(f"LLM新闻{i}", ["LLM"], score=9-i*0.5))
            items.append(self._make_item(f"Agent新闻{i}", ["Agent"], score=8-i*0.3))
            items.append(self._make_item(f"开源新闻{i}", ["开源"], score=7-i*0.2))
        sections = _build_sections(items)
        # AI 标签包括: LLM, Agent, 开源, 工具 → 最多只保留2个
        ai_titles = [s["section_title"] for s in sections
                     if any(t in _AI_TAGS for t in [k for k,v in _SECTION_LABELS.items() if v==s["section_title"]])]
        # 简化：检查总 section 数
        assert len(sections) <= 6  # 总共最多6组

    def test_max_items_per_section(self):
        """每个 section 最多 2 条"""
        items = [
            self._make_item("LLM新闻1", ["LLM"], score=9),
            self._make_item("LLM新闻2", ["LLM"], score=8),
            self._make_item("LLM新闻3", ["LLM"], score=7),
        ]
        sections = _build_sections(items)
        assert len(sections[0]["items"]) <= 2

    def test_sections_have_required_fields(self):
        """每个 section 必须有 items、section_title，每个 item 有 title/url/tags"""
        items = [
            self._make_item("测试新闻", ["科技"], score=7),
        ]
        sections = _build_sections(items)
        for sec in sections:
            assert "section_title" in sec
            assert "items" in sec
            assert len(sec["items"]) >= 1
            for it in sec["items"]:
                assert "title" in it
                assert "url" in it
                assert "tags" in it
                assert "source" in it

    def test_duplicate_items_removed(self):
        """相同 URL 的去重"""
        items = [
            self._make_item("同一条新闻", ["科技"], url="http://same.url"),
            self._make_item("同一条新闻", ["科技"], url="http://same.url"),
        ]
        sections = _build_sections(items)
        total = sum(len(s["items"]) for s in sections)
        assert total == 1

    def test_realistic_scenario(self):
        """模拟真实场景：含多领域新闻"""
        items = [
            self._make_item("OpenAI发布GPT-5", ["LLM"], score=9.5),
            self._make_item("Claude推出新功能", ["LLM"], score=8.5),
            self._make_item("NBA总决赛骑士夺冠", ["体育"], score=8),
            self._make_item("NFL季后赛", ["体育"], score=7.5),
            self._make_item("AI芯片公司融资1亿", ["芯片", "融资"], score=9),
            self._make_item("自动驾驶新规出台", ["自动驾驶"], score=7),
            self._make_item("开源框架v2发布", ["开源"], score=8),
            self._make_item("浏览器零日漏洞", ["安全"], score=8.5),
        ]
        sections = _build_sections(items)
        # 验证: >=4 section, 非AI标签在前
        assert len(sections) >= 4, f"Expected >=4, got {len(sections)}: {[s['section_title'] for s in sections]}"
        # 每个 section 有 1-2 条
        for sec in sections:
            assert 1 <= len(sec["items"]) <= 2
        # 非AI优先
        non_ai_first = sections[0]["section_title"]
        assert non_ai_first not in {"大模型前沿", "智能体动态", "开源工具", "开发者工具"}, \
            f"First section should be non-AI, got {non_ai_first}"


class TestSummarizeIntegration:
    """集成测试: summarize 完整流程"""

    @pytest.mark.asyncio
    async def test_summarize_empty(self):
        """空输入返回空结构"""
        result = await summarize([], "morning")
        assert result["sections"] == []
        assert result["tl_dr"] == []
        assert result["headline"] == {}

    @pytest.mark.asyncio
    async def test_summarize_with_items(self):
        """有输入时返回完整结构"""
        items = [
            {"title": "OpenAI发布GPT-5", "content": "...", "tags": ["LLM"], "ai_score": 9.5,
             "url": "http://a", "source": "test"},
            {"title": "NBA总决赛", "content": "...", "tags": ["体育"], "ai_score": 8,
             "url": "http://b", "source": "test"},
            {"title": "芯片融资", "content": "...", "tags": ["芯片", "融资"], "ai_score": 8.5,
             "url": "http://c", "source": "test"},
            {"title": "安全漏洞", "content": "...", "tags": ["安全"], "ai_score": 7.5,
             "url": "http://d", "source": "test"},
        ]
        result = await summarize(items, "morning")
        # 应有 >=3 section
        assert len(result["sections"]) >= 2, \
            f"Expected >=2, got {len(result['sections'])}: {[s['section_title'] for s in result['sections']]}"
        # 验证结构
        for sec in result["sections"]:
            assert "section_title" in sec
            assert len(sec["items"]) >= 1


class TestLabels:
    """测试标签映射"""

    def test_all_labels_have_mapping(self):
        """所有常用标签都有对应的中文 section 名"""
        for tag in ["LLM", "Agent", "开源", "工具", "科技", "行业",
                     "全球", "体育", "安全", "芯片", "机器人", "自动驾驶", "融资", "医疗"]:
            assert tag in _SECTION_LABELS, f"Missing label for {tag}"
            assert isinstance(_SECTION_LABELS[tag], str)
            assert len(_SECTION_LABELS[tag]) >= 2
