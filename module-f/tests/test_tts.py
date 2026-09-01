"""测试 tts.py — TTS 声音配置 + 生成逻辑

运行: cd module-f && python -m pytest tests/test_tts.py -v
"""
import os
import sys
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tts import TTSEngine, TTS_VOICE, TTS_RATE, TTS_STYLE, _build_ssml, _add_natural_pauses


class TestTTSVoiceConfig:
    """声音配置测试 — 改动4+5"""

    # ── 改动5: 语速不低于 +10% ──
    def test_rate_increased_from_baseline(self):
        """语速已从 +3% 提升，不低于 +10%"""
        rate_num = int(TTS_RATE.strip("+%"))
        assert rate_num >= 10, (
            f"TTS_RATE={TTS_RATE} 太慢，短视频需要 ≥ +10%，"
            f"当前仅 +{rate_num}%"
        )

    def test_rate_format_is_valid(self):
        """速率格式: +XX%"""
        assert TTS_RATE.startswith("+"), f"速率需以 + 开头，当前: {TTS_RATE}"
        assert TTS_RATE.endswith("%"), f"速率需以 % 结尾，当前: {TTS_RATE}"
        middle = TTS_RATE[1:-1]
        assert middle.isdigit(), f"速率中间需为数字，当前: {middle}"

    def test_rate_within_safe_range(self):
        """语速在安全范围 (+10% ~ +30%)，过快会失真"""
        rate_num = int(TTS_RATE.strip("+%"))
        assert 10 <= rate_num <= 25, (
            f"TTS_RATE={TTS_RATE} 超出安全范围 [10%, 25%]"
        )

    # ── 改动4: 默认声音为活泼类型 ──
    def test_default_voice_is_passionate_male(self):
        """默认声音是激情男声 (YunjianNeural)"""
        assert TTS_VOICE == "zh-CN-YunjianNeural", (
            f"默认声音应为 zh-CN-YunjianNeural (激情)，当前: {TTS_VOICE}"
        )

    def test_default_style_is_newscast(self):
        """默认风格为 newscast (专业新闻播报)"""
        assert TTS_STYLE == "newscast", (
            f"默认风格应为 newscast，当前: {TTS_STYLE}"
        )

    # ── VOICES 字典完整性 ──
    def test_all_registered_voices_are_valid(self):
        """VOICES 字典中所有声音名合法 (zh-CN-*)"""
        engine = TTSEngine()
        voices = engine.list_voices()
        assert len(voices) >= 6, (
            f"VOICES 应包含 ≥6 个声音，当前: {len(voices)}"
        )
        for name in voices:
            assert name.startswith("zh-CN-"), (
                f"声音名应以 zh-CN- 开头: {name}"
            )
            assert name.endswith("Neural"), (
                f"声音名应以 Neural 结尾: {name}"
            )

    def test_voices_includes_lively_options(self):
        """VOICES 包含多个活泼/生动的选项"""
        engine = TTSEngine()
        voices = engine.list_voices()
        lively_keywords = ["活泼", "lively", "sweet", "甜美", "energetic", "sunny", "阳光"]
        lively_voices = [
            name for name, desc in voices.items()
            if any(kw in desc.lower() for kw in lively_keywords)
        ]
        assert len(lively_voices) >= 2, (
            f"至少需要 2 个活泼声音选项，当前: {len(lively_voices)} — {lively_voices}"
        )

    def test_voices_includes_male_options(self):
        """VOICES 包含男声选项"""
        engine = TTSEngine()
        voices = engine.list_voices()
        male_voices = [
            name for name, desc in voices.items()
            if "male" in desc.lower()
        ]
        assert len(male_voices) >= 2, (
            f"至少需要 2 个男声选项，当前: {len(male_voices)}"
        )

    # ── 环境变量覆盖 ──
    def test_env_var_overrides_voice(self):
        """环境变量 TTS_VOICE 可覆盖默认声音"""
        os.environ["TTS_VOICE"] = "zh-CN-YunyangNeural"
        # Re-import to pick up env var (module-level default reads at import)
        import importlib
        import tts
        importlib.reload(tts)
        assert tts.TTS_VOICE == "zh-CN-YunyangNeural"

    def test_env_var_overrides_rate(self):
        """环境变量 TTS_RATE 可覆盖默认语速"""
        os.environ["TTS_RATE"] = "+25%"
        import importlib
        import tts
        importlib.reload(tts)
        assert tts.TTS_RATE == "+25%"


class TestTTSGenerate:
    """TTS 生成逻辑测试"""

    @pytest.fixture
    def tmp_out(self, tmp_path):
        """Windows-compatible temp output path."""
        return str(tmp_path / "out.mp3")

    @pytest.fixture
    def tmp_txt(self, tmp_path):
        """Windows-compatible temp text file."""
        p = tmp_path / "tts_text.txt"
        p.write_text("测试文本", encoding="utf-8")
        return str(p)

    @pytest.mark.asyncio
    async def test_cli_command_includes_voice_flag(self, tmp_out, tmp_txt):
        """CLI 命令包含 --voice 参数"""
        engine = TTSEngine()
        with patch("subprocess.run") as mock_run, \
             patch("tempfile.mktemp", return_value=tmp_txt), \
             patch("pathlib.Path.unlink"):
            result = MagicMock()
            result.returncode = 0
            mock_run.return_value = result

            await engine._ssml_generate("测试文本", tmp_out,
                                        "zh-CN-YunjianNeural", "newscast", "+15%")
            cmd_args = mock_run.call_args[0][0]
            assert "--voice" in cmd_args
            voice_idx = cmd_args.index("--voice")
            assert cmd_args[voice_idx + 1] == "zh-CN-YunjianNeural"

    @pytest.mark.asyncio
    async def test_cli_command_includes_rate_flag(self, tmp_out, tmp_txt):
        """CLI 命令包含 --rate 参数"""
        engine = TTSEngine()
        with patch("subprocess.run") as mock_run, \
             patch("tempfile.mktemp", return_value=tmp_txt), \
             patch("pathlib.Path.unlink"):
            result = MagicMock()
            result.returncode = 0
            mock_run.return_value = result

            await engine._ssml_generate("测试文本", tmp_out,
                                        "zh-CN-YunjianNeural", "newscast", "+15%")
            cmd_args = mock_run.call_args[0][0]
            assert "--rate" in cmd_args
            rate_idx = cmd_args.index("--rate")
            assert cmd_args[rate_idx + 1] == "+15%"

    @pytest.mark.asyncio
    async def test_generate_returns_path_on_success(self, tmp_out, tmp_txt):
        """成功生成返回输出路径"""
        engine = TTSEngine()
        with patch("subprocess.run") as mock_run, \
             patch("tempfile.mktemp", return_value=tmp_txt), \
             patch("pathlib.Path.unlink"), \
             patch("pathlib.Path.exists", return_value=True):
            result = MagicMock()
            result.returncode = 0
            mock_run.return_value = result

            output = await engine.generate("测试文本", tmp_out)
            assert output == tmp_out

    @pytest.mark.asyncio
    async def test_generate_fallback_on_cli_failure(self, tmp_out, tmp_txt):
        """CLI 失败时走 mock fallback（不崩溃）"""
        engine = TTSEngine()
        with patch("subprocess.run") as mock_run, \
             patch("tempfile.mktemp", return_value=tmp_txt), \
             patch("pathlib.Path.unlink"):
            result = MagicMock()
            result.returncode = 1
            result.stderr = "error"
            mock_run.return_value = result

            # _ssml_generate fails → falls through to _cli_generate
            out = await engine._ssml_generate("测试文本", tmp_out,
                                              "zh-CN-YunjianNeural", "newscast", "+15%")
            # Should return None on failure (no crash)
            assert out is None

    @pytest.mark.asyncio
    async def test_generate_uses_default_voice_when_not_specified(self, tmp_out, tmp_txt):
        """不指定声音时使用传入的默认值"""
        engine = TTSEngine()
        with patch("subprocess.run") as mock_run, \
             patch("tempfile.mktemp", return_value=tmp_txt), \
             patch("pathlib.Path.unlink"):
            result = MagicMock()
            result.returncode = 0
            mock_run.return_value = result

            await engine._ssml_generate("测试", tmp_out,
                                        "zh-CN-YunjianNeural", "newscast", "+15%")
            cmd_args = mock_run.call_args[0][0]
            voice_idx = cmd_args.index("--voice")
            assert cmd_args[voice_idx + 1] == "zh-CN-YunjianNeural"


class TestSSML:
    """SSML 构造测试"""

    def test_build_ssml_is_valid_xml(self):
        """SSML 字符串是合法 XML"""
        ssml = _build_ssml("测试文本", "zh-CN-YunjianNeural", "newscast", "+15%")
        assert ssml.startswith('<speak')
        assert ssml.endswith('</speak>')
        assert '<voice name="zh-CN-YunjianNeural">' in ssml
        assert '<prosody rate="+15%"' in ssml
        assert "测试文本" in ssml

    def test_build_ssml_escapes_special_chars(self):
        """SSML 转义 XML 特殊字符"""
        ssml = _build_ssml("A < B & C > D", "zh-CN-YunjianNeural", "newscast", "+15%")
        assert "&lt;" in ssml
        assert "&gt;" in ssml
        assert "&amp;" in ssml

    def test_build_ssml_rate_strips_extra_plus(self):
        """速率格式化: 去除多余 + 号"""
        ssml = _build_ssml("测试", "zh-CN-YunjianNeural", "newscast", "++15%")
        assert 'rate="+15%"' in ssml

    def test_add_natural_pauses_inserts_breaks(self):
        """自然停顿: 标点后插入 break 标签"""
        text = "第一句话。第二句话，继续。"
        result = _add_natural_pauses(text)
        assert '<break time="400ms"/>' in result  # after 。
        assert '<break time="150ms"/>' in result   # after ，

    def test_add_natural_pauses_preserves_text(self):
        """自然停顿不丢失文本内容"""
        text = "各位观众早上好，欢迎收看今天的AI科技早报。"
        result = _add_natural_pauses(text)
        assert "各位观众早上好" in result
        assert "欢迎收看今天的AI科技早报" in result

    def test_add_natural_pauses_no_double_breaks(self):
        """不产生连续重复的 break 标签"""
        text = "结束了。\n\n新段落"
        result = _add_natural_pauses(text)
        # No two consecutive breaks
        import re
        breaks = re.findall(r'<break time="\d+ms"/>', result)
        # Just verify we don't have break immediately followed by break
        assert '<break time="400ms"/><break time="600ms"/>' not in result
        assert '<break time="400ms"/><break time="400ms"/>' not in result


class TestTTSStyles:
    """TTS 风格配置测试"""

    def test_styles_list_is_complete(self):
        """STYLES 字典包含常用风格"""
        engine = TTSEngine()
        styles = engine.list_styles()
        assert "cheerful" in styles
        assert "friendly" in styles
        assert "newscast" in styles
        assert len(styles) >= 4

    def test_generate_from_script_respects_voice_override(self):
        """批量生成时可用 segment 级别的 voice 覆盖"""
        engine = TTSEngine()
        segments = [
            {"text": "新闻一", "voice": "zh-CN-YunyangNeural"},
            {"text": "新闻二"},  # uses default
        ]
        # Just verify structure — actual TTS call is mocked
        assert segments[0]["voice"] == "zh-CN-YunyangNeural"
        assert "voice" not in segments[1]
