"""测试 editor.py — 字幕样式 + 转场动画 + 拼接回归

运行: cd module-f && python -m pytest tests/test_editor.py -v
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from editor import VideoEditor


class TestSubtitleStyle:
    """改动1: 字幕灰条背景样式测试"""

    def test_burn_subtitles_has_box_background(self):
        """验证 BorderStyle=3 参数存在"""
        editor = VideoEditor()
        with patch.object(editor, "_run", return_value=True), \
             patch("shutil.copy"), \
             patch("pathlib.Path.unlink"):
            vf = None

            def capture_cmd(cmd, label=""):
                nonlocal vf
                for i, arg in enumerate(cmd):
                    if arg == "-vf" and i + 1 < len(cmd):
                        vf = cmd[i + 1]
                return True

            editor._run = MagicMock(side_effect=capture_cmd)

            video_dir = str(Path(__file__).parent)
            editor.burn_subtitles(
                str(Path(video_dir) / "test.mp4"),
                str(Path(video_dir) / "test.srt"),
                str(Path(video_dir) / "out.mp4"),
            )

            assert vf is not None, "burn_subtitles 应生成 -vf 参数"
            assert "BorderStyle=3" in vf, (
                f"缺少 BorderStyle=3 (背景盒), 当前 vf: {vf}"
            )
            assert "BackColour" in vf, (
                f"缺少 BackColour (背景色), 当前 vf: {vf}"
            )

    def test_background_is_semi_transparent_gray(self):
        """背景色为半透明灰色 (&H80000000)"""
        editor = VideoEditor()
        with patch.object(editor, "_run", return_value=True), \
             patch("shutil.copy"), \
             patch("pathlib.Path.unlink"):
            vf = None

            def capture_cmd(cmd, label=""):
                nonlocal vf
                for i, arg in enumerate(cmd):
                    if arg == "-vf" and i + 1 < len(cmd):
                        vf = cmd[i + 1]
                return True

            editor._run = MagicMock(side_effect=capture_cmd)

            video_dir = str(Path(__file__).parent)
            editor.burn_subtitles(
                str(Path(video_dir) / "test.mp4"),
                str(Path(video_dir) / "test.srt"),
                str(Path(video_dir) / "out.mp4"),
            )

            assert vf is not None
            # BackColour=&H80000000 = semi-transparent gray (A=80, R=00, G=00, B=00)
            assert "BackColour=&H80000000" in vf, (
                f"BackColour 应为 &H80000000 (半透明灰), 当前 vf: {vf}"
            )

    def test_subtitle_has_outline(self):
        """字幕保留黑色描边 (Outline)"""
        editor = VideoEditor()
        with patch.object(editor, "_run", return_value=True), \
             patch("shutil.copy"), \
             patch("pathlib.Path.unlink"):
            vf = None

            def capture_cmd(cmd, label=""):
                nonlocal vf
                for i, arg in enumerate(cmd):
                    if arg == "-vf" and i + 1 < len(cmd):
                        vf = cmd[i + 1]
                return True

            editor._run = MagicMock(side_effect=capture_cmd)

            video_dir = str(Path(__file__).parent)
            editor.burn_subtitles(
                str(Path(video_dir) / "test.mp4"),
                str(Path(video_dir) / "test.srt"),
                str(Path(video_dir) / "out.mp4"),
            )

            assert vf is not None
            assert "OutlineColour" in vf, "应保留 OutlineColour (描边色)"
            assert "Outline=2" in vf, "应保留 Outline=2 (描边宽度)"

    def test_subtitle_uses_chinese_font(self):
        """字幕使用中文字体"""
        editor = VideoEditor()
        with patch.object(editor, "_run", return_value=True), \
             patch("shutil.copy"), \
             patch("pathlib.Path.unlink"):
            vf = None

            def capture_cmd(cmd, label=""):
                nonlocal vf
                for i, arg in enumerate(cmd):
                    if arg == "-vf" and i + 1 < len(cmd):
                        vf = cmd[i + 1]
                return True

            editor._run = MagicMock(side_effect=capture_cmd)

            video_dir = str(Path(__file__).parent)
            editor.burn_subtitles(
                str(Path(video_dir) / "test.mp4"),
                str(Path(video_dir) / "test.srt"),
                str(Path(video_dir) / "out.mp4"),
            )

            assert vf is not None
            assert "Microsoft YaHei" in vf, "应使用微软雅黑中文字体"

    def test_subtitle_alignment_bottom_center(self):
        """字幕对齐方式为底部居中 (Alignment=2)"""
        editor = VideoEditor()
        with patch.object(editor, "_run", return_value=True), \
             patch("shutil.copy"), \
             patch("pathlib.Path.unlink"):
            vf = None

            def capture_cmd(cmd, label=""):
                nonlocal vf
                for i, arg in enumerate(cmd):
                    if arg == "-vf" and i + 1 < len(cmd):
                        vf = cmd[i + 1]
                return True

            editor._run = MagicMock(side_effect=capture_cmd)

            video_dir = str(Path(__file__).parent)
            editor.burn_subtitles(
                str(Path(video_dir) / "test.mp4"),
                str(Path(video_dir) / "test.srt"),
                str(Path(video_dir) / "out.mp4"),
            )

            assert vf is not None
            assert "Alignment=2" in vf, "字幕应底部居中 (Alignment=2)"


class TestConcatWithTransitions:
    """改动3: 新闻段落平滑过渡测试"""

    def test_concat_with_transitions_uses_xfade(self):
        """验证 concat_with_transitions 使用 xfade 滤镜"""
        editor = VideoEditor()
        with patch.object(editor, "_run", return_value=True):
            filter_str = None

            def capture_cmd(cmd, label=""):
                nonlocal filter_str
                for i, arg in enumerate(cmd):
                    if arg == "-filter_complex" and i + 1 < len(cmd):
                        filter_str = cmd[i + 1]
                return True

            editor._run = MagicMock(side_effect=capture_cmd)

            clip_a = str(Path(__file__).parent / "a.mp4")
            clip_b = str(Path(__file__).parent / "b.mp4")
            out = str(Path(__file__).parent / "out.mp4")

            editor.concat_with_transitions([clip_a, clip_b], out, transition="fade", duration=0.5)

            assert filter_str is not None, "concat_with_transitions 应生成 filter_complex"
            assert "xfade" in filter_str, f"filter_complex 应包含 xfade, 当前: {filter_str}"
            assert "fade" in filter_str, f"transition 应为 fade, 当前: {filter_str}"

    def test_transition_duration_is_configurable(self):
        """过渡时长可配置"""
        editor = VideoEditor()
        with patch.object(editor, "_run", return_value=True):
            filter_str = None

            def capture_cmd(cmd, label=""):
                nonlocal filter_str
                for i, arg in enumerate(cmd):
                    if arg == "-filter_complex" and i + 1 < len(cmd):
                        filter_str = cmd[i + 1]
                return True

            editor._run = MagicMock(side_effect=capture_cmd)

            clip_a = str(Path(__file__).parent / "a.mp4")
            clip_b = str(Path(__file__).parent / "b.mp4")
            out = str(Path(__file__).parent / "out.mp4")

            editor.concat_with_transitions([clip_a, clip_b], out, transition="fade", duration=1.0)

            assert filter_str is not None
            assert "duration=1.0" in filter_str or "duration=1" in filter_str, (
                f"duration 应为 1.0, 当前: {filter_str}"
            )

    def test_single_clip_skips_transition(self):
        """单个片段时无过渡（直接复制）"""
        editor = VideoEditor()
        with patch("shutil.copy") as mock_copy, \
             patch.object(editor, "_run", return_value=True):
            clip_a = str(Path(__file__).parent / "a.mp4")
            out = str(Path(__file__).parent / "out.mp4")

            result = editor.concat_with_transitions([clip_a], out)
            assert result is True
            mock_copy.assert_called_once()

    def test_two_clips_has_one_transition(self):
        """N=2 个片段产生 1 个 xfade"""
        editor = VideoEditor()
        with patch.object(editor, "_run", return_value=True):
            filter_str = None

            def capture_cmd(cmd, label=""):
                nonlocal filter_str
                for i, arg in enumerate(cmd):
                    if arg == "-filter_complex" and i + 1 < len(cmd):
                        filter_str = cmd[i + 1]
                return True

            editor._run = MagicMock(side_effect=capture_cmd)

            clips = [
                str(Path(__file__).parent / "a.mp4"),
                str(Path(__file__).parent / "b.mp4"),
            ]
            out = str(Path(__file__).parent / "out.mp4")

            editor.concat_with_transitions(clips, out)

            assert filter_str is not None
            # Should have exactly 1 xfade for 2 clips
            xfade_count = filter_str.count("xfade")
            assert xfade_count == 1, (
                f"2个片段应有 1 个 xfade, 实际: {xfade_count}, filter: {filter_str}"
            )

    def test_three_clips_has_two_transitions(self):
        """N=3 个片段产生 2 个 xfade"""
        editor = VideoEditor()
        with patch.object(editor, "_run", return_value=True):
            filter_str = None

            def capture_cmd(cmd, label=""):
                nonlocal filter_str
                for i, arg in enumerate(cmd):
                    if arg == "-filter_complex" and i + 1 < len(cmd):
                        filter_str = cmd[i + 1]
                return True

            editor._run = MagicMock(side_effect=capture_cmd)

            clips = [
                str(Path(__file__).parent / "a.mp4"),
                str(Path(__file__).parent / "b.mp4"),
                str(Path(__file__).parent / "c.mp4"),
            ]
            out = str(Path(__file__).parent / "out.mp4")

            editor.concat_with_transitions(clips, out)

            assert filter_str is not None
            xfade_count = filter_str.count("xfade")
            assert xfade_count == 2, (
                f"3个片段应有 2 个 xfade, 实际: {xfade_count}, filter: {filter_str}"
            )

    def test_transition_type_default_is_fade(self):
        """默认过渡类型为 fade"""
        editor = VideoEditor()
        with patch.object(editor, "_run", return_value=True):
            filter_str = None

            def capture_cmd(cmd, label=""):
                nonlocal filter_str
                for i, arg in enumerate(cmd):
                    if arg == "-filter_complex" and i + 1 < len(cmd):
                        filter_str = cmd[i + 1]
                return True

            editor._run = MagicMock(side_effect=capture_cmd)

            clip_a = str(Path(__file__).parent / "a.mp4")
            clip_b = str(Path(__file__).parent / "b.mp4")
            out = str(Path(__file__).parent / "out.mp4")

            editor.concat_with_transitions([clip_a, clip_b], out)

            assert filter_str is not None
            assert "transition=fade" in filter_str, (
                f"默认 transition 应为 fade, 当前: {filter_str}"
            )


class TestConcat:
    """原有 concat 方法回归测试"""

    def test_concat_single_clip_copies(self):
        """单个片段应直接复制"""
        editor = VideoEditor()
        with patch("shutil.copy") as mock_copy:
            result = editor.concat(
                [str(Path(__file__).parent / "a.mp4")],
                str(Path(__file__).parent / "out.mp4"),
            )
            assert result is True
            mock_copy.assert_called_once()

    def test_concat_multiple_clips_builds_filter(self):
        """多个片段应构建 filter_complex"""
        editor = VideoEditor()
        with patch.object(editor, "_run", return_value=True):
            filter_str = None

            def capture_cmd(cmd, label=""):
                nonlocal filter_str
                for i, arg in enumerate(cmd):
                    if arg == "-filter_complex" and i + 1 < len(cmd):
                        filter_str = cmd[i + 1]
                return True

            editor._run = MagicMock(side_effect=capture_cmd)

            clips = [
                str(Path(__file__).parent / "a.mp4"),
                str(Path(__file__).parent / "b.mp4"),
            ]
            out = str(Path(__file__).parent / "out.mp4")

            editor.concat(clips, out)

            assert filter_str is not None
            assert "concat" in filter_str, f"应包含 concat, 当前: {filter_str}"
            assert "scale=1920:1080" in filter_str, f"应缩放到 1080p, 当前: {filter_str}"

    def test_concat_empty_list_returns_false(self):
        """空列表返回 False（不崩溃）"""
        editor = VideoEditor()
        result = editor.concat([], str(Path(__file__).parent / "out.mp4"))
        assert result is False
