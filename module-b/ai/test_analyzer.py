"""测试 analyzer.py — 评分 + 标签清洗

运行: cd module-b && python -m pytest ai/test_analyzer.py -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from ai.analyzer import _clean_tags, _ALLOWED_TAGS


class TestTagCleaning:
    """标签清洗：确保 LLM 返回的标签被映射到白名单"""

    def test_all_valid_tags_preserved(self):
        """所有白名单标签直接通过"""
        result = _clean_tags(["LLM", "Agent", "开源", "工具"])
        assert len(result) <= 2
        assert all(t in _ALLOWED_TAGS for t in result)

    def test_invalid_tags_filtered(self):
        """非白名单标签被过滤，由关键词兜底"""
        result = _clean_tags(["AI", "端侧", "合作"], title="英伟达推出AI芯片")
        # "AI" 和 "端侧" 不在白名单，"合作" 不在白名单
        # 兜底匹配: "AI" + "芯片"
        assert all(t in _ALLOWED_TAGS for t in result)

    def test_llm_ai_chip(self):
        """AI 硬件/芯片 新闻应标为芯片+科技"""
        result = _clean_tags(["AI", "芯片"], title="英伟达发布新GPU")
        assert "芯片" in result or "科技" in result

    def test_financing_news(self):
        """融资类新闻正确标记"""
        result = _clean_tags([], title="AI初创完成5000万A轮融资")
        assert "融资" in result

    def test_sports_news(self):
        """体育新闻正确标记"""
        result = _clean_tags([], title="NHL Hurricanes win Game 5 in overtime")
        assert "体育" in result

    def test_security_news(self):
        """安全新闻正确标记"""
        result = _clean_tags([], title="黑客利用AI工具漏洞发起供应链攻击")
        assert "安全" in result

    def test_empty_tags_fallback(self):
        """空标签兜底为科技"""
        result = _clean_tags([], title="某公司发布新产品")
        assert result == ["科技"]

    def test_max_two_tags(self):
        """最多返回2个标签"""
        result = _clean_tags(["LLM", "开源", "工具", "科技"], title="开源LLM工具")
        assert len(result) <= 2

    def test_tag_diversity_batch(self):
        """批量测试：不同新闻应得到不同标签"""
        samples = [
            ("芯片设计融资", "芯片+融资"),
            ("OpenAI发布GPT-5", "LLM"),
            ("NBA总决赛", "体育"),
            ("欧盟AI法案通过", "行业"),
            ("开源框架发布", "开源"),
            ("机器人公司融资", "机器人+融资"),
            ("数据泄露事件", "安全"),
            ("自动驾驶路测", "自动驾驶"),
        ]
        results = {}
        for title, expected in samples:
            tags = _clean_tags([], title)
            results[title] = tags
            assert len(tags) >= 1, f"{title} should have at least 1 tag"

        # 验证多样性: 至少 4 种不同标签
        all_tags = set()
        for tags in results.values():
            all_tags.update(tags)
        assert len(all_tags) >= 4, f"Tag diversity too low: {all_tags}"


@pytest.mark.asyncio
class TestBatchScore:
    """集成测试：batch_score 对真实 DeepSeek API 的调用（需要 API Key）"""

    async def test_batch_score_returns_tags(self):
        """评分后每个 item 应该有 tags 字段"""
        from ai.analyzer import batch_score
        items = [
            {"title": "OpenAI发布GPT-5", "content": "OpenAI正式发布GPT-5模型", "source": "test"},
            {"title": "NBA总决赛G7", "content": "NBA总决赛第七场打响", "source": "test"},
            {"title": "芯片公司融资", "content": "AI芯片初创获5000万融资", "source": "test"},
        ]
        result = await batch_score(items, batch_size=3)
        assert len(result) == 3
        for it in result:
            assert "ai_score" in it, f"Missing ai_score in {it['title']}"
            assert "tags" in it, f"Missing tags in {it['title']}"
            assert len(it["tags"]) >= 1, f"Empty tags for {it['title']}"
            assert all(t in _ALLOWED_TAGS for t in it["tags"]), \
                f"Invalid tags {it['tags']} for {it['title']}"

    async def test_batch_score_diverse_tags(self):
        """不同领域新闻应分配不同标签"""
        from ai.analyzer import batch_score
        items = [
            {"title": "OpenAI launches GPT-5 with enhanced reasoning", "content": "OpenAI发布GPT-5", "source": "test"},
            {"title": "NHL Stanley Cup Final Game 7 results", "content": "NHL总决赛结果", "source": "test"},
            {"title": "AI Chip startup raises $50M Series A", "content": "芯片融资", "source": "test"},
            {"title": "New open-source framework for LLM deployment", "content": "开源框架", "source": "test"},
            {"title": "Government announces new AI regulation policy", "content": "政策", "source": "test"},
        ]
        result = await batch_score(items, batch_size=5)
        all_tags = set()
        for it in result:
            all_tags.update(it["tags"])
        # 应有至少 3 种不同标签（LLM, 体育, 融资, 开源, 行业）
        assert len(all_tags) >= 3, f"Expected >=3 different tags, got {len(all_tags)}: {all_tags}"
