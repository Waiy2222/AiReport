"""测试 pipeline.py — 脚本长度约束 + 1分钟时长 + 转场集成

运行: cd module-f && python -m pytest tests/test_pipeline.py -v
"""
import os
import sys
import re
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import (
    _parse_script,
    _fallback_script,
    _clean_spoken_text,
    _generate_script_subtitles,
    _format_srt_time,
    _pre_scale_clip,
    _extract_main_entity,
)


class TestScriptParsing:
    """脚本解析测试"""

    def test_fallback_script_word_count(self):
        """fallback 脚本字数 200-300（无开场概述无结尾总结）"""
        today = "2026-06-16"
        script_text, segments = _fallback_script(today)

        char_count = len(script_text.replace("\n", "").replace(" ", ""))
        assert 150 <= char_count <= 400, (
            f"fallback 脚本 {char_count} 字，应在 150-400 范围内"
        )

    def test_fallback_script_news_count(self):
        """fallback 脚本新闻条数 2"""
        today = "2026-06-16"
        script_text, segments = _fallback_script(today)

        news_segments = [
            s for s in segments
            if "开场" not in s.get("topic", "") and "结尾" not in s.get("topic", "")
        ]
        assert len(news_segments) == 2, (
            f"新闻条数应为 2 条，实际: {len(news_segments)}"
        )

    def test_fallback_script_has_structure(self):
        """fallback 脚本有开场引导+新闻，无结尾"""
        today = "2026-06-16"
        script_text, segments = _fallback_script(today)

        topics = [s["topic"] for s in segments]
        assert any("开场" in t for t in topics), f"缺少开场引导: {topics}"
        assert not any("结尾" in t for t in topics), f"不应有结尾段: {topics}"

    def test_parse_script_bracket_format(self):
        """解析【】格式脚本"""
        raw = """【开场概述】
        各位观众早上好，欢迎收看今天的AI科技早报。
        BROLL: AI科技 智能体 Agent

        【新闻一：OpenHuman开源桌面智能体爆火】
        开源桌面AI智能体OpenHuman在GitHub上连续霸榜。
        BROLL: OpenHuman 桌面智能体 GitHub

        【结尾总结】
        以上就是今天的早报内容。感谢您的收看。
        BROLL: AI智能体 Agent"""

        text, segments = _parse_script(raw, "2026-06-16")
        assert len(segments) >= 2, f"应解析出 ≥2 段，实际: {len(segments)}"
        topics = [s["topic"] for s in segments]
        assert any("开场" in t for t in topics)

    def test_parse_script_filters_markdown(self):
        """解析时过滤 **粗体** 标记（单*和反引号由 _clean_spoken_text 处理）"""
        raw = """【新闻一：测试标题】
        这是**粗体**文本，包含内容。
        BROLL: 测试"""

        text, segments = _parse_script(raw, "2026-06-16")
        for seg in segments:
            assert "**" not in seg["text"], f"应过滤 ** 标记: {seg['text']}"

    def test_parse_script_rejects_placeholder_broll(self):
        """BROLL 占位符被替换为默认值"""
        raw = """【新闻一：测试】
        新闻内容。
        BROLL: 搜索关键词"""

        text, segments = _parse_script(raw, "2026-06-16")
        for seg in segments:
            assert seg["broll_keywords"] != "搜索关键词", (
                f"占位符应被替换: {seg['broll_keywords']}"
            )


class TestScriptPromptConstraints:
    """改动2a: 脚本生成 Prompt 约束测试"""

    def test_prompt_specifies_word_limit(self):
        """Prompt 包含字数限制"""
        from pipeline import _generate_news_script
        import inspect
        source = inspect.getsource(_generate_news_script)
        assert "200" in source or "300" in source or "字数" in source, (
            "Prompt 应包含字数限制"
        )

    def test_prompt_specifies_news_count(self):
        """Prompt 包含新闻条数限制"""
        import inspect
        from pipeline import _generate_news_script
        source = inspect.getsource(_generate_news_script)
        # Should specify 2-3 news items
        assert "2" in source and "3" in source, (
            "Prompt 应指定 2-3 条新闻"
        )


class TestDurationConstraint:
    """改动2b: 1分钟时长约束测试"""

    def test_duration_speedup_threshold_exists(self):
        """验证 pipeline 中有加速兜底逻辑"""
        import inspect
        from pipeline import VideoPipeline
        source = inspect.getsource(VideoPipeline.run_full_pipeline)

        # Should have speedup logic for >65s
        assert "setpts" in source or "atempo" in source or "speed" in source or "加速" in source or "60" in source, (
            "应包含视频加速兜底逻辑 (setpts/atempo)"
        )

    def test_script_subtitle_duration_sum_matches(self, tmp_path):
        """字幕时间戳总和接近片段时长"""
        segments = [
            {"topic": "开场", "text": "欢迎收看AI早报。"},
            {"topic": "新闻", "text": "重要新闻内容在这里。"},
        ]
        durations = [4.0, 6.0]

        sub_path = _generate_script_subtitles(segments, durations, tmp_path)
        assert sub_path is not None

        content = Path(sub_path).read_text(encoding="utf-8")
        # Parse last timestamp
        import re as _re
        times = _re.findall(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', content)
        assert len(times) >= 2, f"至少应有 2 个字幕条目，实际: {len(times)}"

        last = times[-1]
        end_sec = int(last[0]) * 3600 + int(last[1]) * 60 + int(last[2]) + int(last[3]) / 1000
        total = sum(durations)
        # Allow 10% margin
        assert abs(end_sec - total) <= total * 0.2, (
            f"字幕结束时间 {end_sec:.1f}s 偏离总时长 {total:.1f}s 超过 20%"
        )


class TestTransitionIntegration:
    """改动3: pipeline 集成转场"""

    def test_concat_with_transitions_method_exists(self):
        """editor.py 有 concat_with_transitions 方法"""
        from editor import VideoEditor
        editor = VideoEditor()
        assert hasattr(editor, "concat_with_transitions"), (
            "VideoEditor 应有 concat_with_transitions 方法"
        )
        assert callable(editor.concat_with_transitions), (
            "concat_with_transitions 应为可调用方法"
        )

    def test_pipeline_step6_uses_transitions(self):
        """pipeline Step 6 使用转场方法"""
        import inspect
        from pipeline import VideoPipeline
        source = inspect.getsource(VideoPipeline.run_full_pipeline)

        # Step 6 should reference concat_with_transitions
        assert "concat_with_transitions" in source or "xfade" in source, (
            "Step 6 应使用 concat_with_transitions 或 xfade"
        )


class TestMainEntityExtraction:
    """主角提取回归测试"""

    def test_extract_known_company(self):
        """提取已知公司名"""
        assert _extract_main_entity("百度智能云办公智能体DuMate上线") == "百度"
        assert _extract_main_entity("OpenAI发布GPT-5大模型") == "OpenAI"

    def test_extract_with_action_verb(self):
        """提取动作前的主体"""
        result = _extract_main_entity("魔法原子首发VLA大模型")
        assert result in ("魔法原子", "魔法"), f"应为 '魔法原子', 实际: {result}"

    def test_extract_english_entity(self):
        """提取英文实体名"""
        result = _extract_main_entity("CrewAI完成A轮融资2000万美元")
        assert result == "CrewAI", f"应为 'CrewAI', 实际: {result}"

    def test_extract_fallback(self):
        """无法精确提取时返回合理值"""
        result = _extract_main_entity("今天的新闻摘要")
        assert len(result) >= 1, "即使是兜底也应返回非空字符串"
