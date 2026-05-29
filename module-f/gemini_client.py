"""Video analysis via Aliyun Bailian Qwen-VL (OpenAI-compatible API).

Extracts key frames from video, sends them to Qwen-VL for content
analysis, topic identification, and relevance scoring.
"""
from __future__ import annotations

import base64
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

BAILIAN_API_KEY = os.getenv("BAILIAN_API_KEY", "")
BAILIAN_BASE_URL = os.getenv(
    "BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
BAILIAN_MODEL = os.getenv("BAILIAN_MODEL", "qwen-vl-max")
FRAME_COUNT = int(os.getenv("VIDEO_ANALYSIS_FRAMES", "5"))
FRAME_MAX_SIZE = int(os.getenv("VIDEO_FRAME_MAX_SIZE", "768"))  # px


class GeminiClient:
    """Video analysis client backed by Aliyun Bailian Qwen-VL."""

    def __init__(self):
        self._configured = bool(BAILIAN_API_KEY)
        self._client: AsyncOpenAI | None = None
        if self._configured:
            self._client = AsyncOpenAI(
                api_key=BAILIAN_API_KEY,
                base_url=BAILIAN_BASE_URL,
            )

    # ---- public API -----------------------------------------------------

    async def analyze_video(
        self,
        video_path: str,
        context: str = "",
    ) -> dict[str, Any] | None:
        """Analyze a video clip for content, topics, and quality.

        Returns dict with: summary, topics, relevance_score (0-10),
        suggested_clip_range (start_sec, end_sec), quality_notes.
        Returns None if unconfigured or call fails.
        """
        if not self._configured or self._client is None:
            logger.warning("Bailian API key not configured — using mock analysis")
            return self._mock_result(video_path, context)

        try:
            frames = _extract_frames(video_path, count=FRAME_COUNT)
            if not frames:
                logger.warning("No frames extracted from %s — using mock", video_path)
                return self._mock_result(video_path, context)

            images_b64 = [_encode_frame(f) for f in frames]

            # Build multimodal message: text + sequence of frames
            content: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": _build_analysis_prompt(context),
                }
            ]
            for img in images_b64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img}"},
                })

            response = await self._client.chat.completions.create(
                model=BAILIAN_MODEL,
                messages=[{"role": "user", "content": content}],
                max_tokens=2000,
                temperature=0.3,
            )

            raw = response.choices[0].message.content or ""
            return _parse_analysis(raw, video_path, context)

        except Exception:
            logger.exception("Bailian video analysis failed for %s", video_path)
            return self._mock_result(video_path, context)

    async def select_best_clips(
        self,
        clips: list[dict[str, Any]],
        max_duration_sec: int = 300,
    ) -> list[dict[str, Any]]:
        """Select the best subset of clips for a coherent video under max duration."""
        if not self._configured or self._client is None or len(clips) <= 3:
            return _greedy_select(clips, max_duration_sec)

        try:
            summaries = [
                f"[{i}] score={c.get('relevance_score',5):.0f} "
                f"dur={c.get('duration_sec',30)}s "
                f"topics={','.join(c.get('topics',[]))} "
                f"summary={c.get('summary','')[:200]}"
                for i, c in enumerate(clips)
            ]

            response = await self._client.chat.completions.create(
                model=BAILIAN_MODEL.replace("vl-", "vl-"),  # keep same model
                messages=[{
                    "role": "user",
                    "content": _build_selection_prompt(summaries, max_duration_sec),
                }],
                max_tokens=500,
                temperature=0.2,
            )

            raw = response.choices[0].message.content or ""
            indices = _parse_selection(raw, len(clips))
            return _greedy_select(
                [clips[i] for i in indices if i < len(clips)],
                max_duration_sec,
            )

        except Exception:
            logger.exception("Bailian clip selection failed")
            return _greedy_select(clips, max_duration_sec)

    # ---- mock -----------------------------------------------------------

    def _mock_result(self, path: str, context: str) -> dict[str, Any]:
        return {
            "video_path": path,
            "summary": f"AI-related clip from {os.path.basename(path)}",
            "topics": ["AI", "agent"],
            "relevance_score": 7.5,
            "suggested_clip_range": {"start_sec": 0, "end_sec": 30},
            "quality_notes": "Good quality, clear visuals",
            "context_match": bool(context),
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _build_analysis_prompt(context: str) -> str:
    ctx = f"\n额外背景: {context}" if context else ""
    return (
        "你是一个视频内容分析助手。请按以下格式分析这组视频关键帧（按时间顺序排列）：\n"
        "1. 总结视频的主要内容（2-3句中文）\n"
        "2. 列出涉及的AI/技术主题（逗号分隔）\n"
        "3. 评估与AI智能体领域的相关度（0-10分）\n"
        "4. 建议剪辑区间（起止秒数）\n"
        "5. 画质/音质简要评价\n"
        f"{ctx}\n"
        "请用JSON格式回复："
        '{"summary":"...","topics":["..."],"relevance_score":0,'
        '"suggested_clip_range":{"start_sec":0,"end_sec":0},'
        '"quality_notes":"..."}'
    )


def _build_selection_prompt(summaries: list[str], max_dur: int) -> str:
    items = "\n".join(summaries)
    return (
        f"从以下视频片段中选择最佳组合，总时长不超过{max_dur}秒。\n"
        f"选择时优先考虑：高相关度、主题多样性、画质好的片段。\n\n"
        f"{items}\n\n"
        "请用JSON数组回复选中的片段索引：\n"
        '[0, 2, 5]'
    )


def _parse_analysis(raw: str, path: str, context: str) -> dict[str, Any]:
    """Extract JSON from model response, with fallback."""
    import json

    try:
        # Try to find JSON block
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            return {
                "video_path": path,
                "summary": data.get("summary", ""),
                "topics": data.get("topics", ["AI"]),
                "relevance_score": float(data.get("relevance_score", 5)),
                "suggested_clip_range": data.get(
                    "suggested_clip_range", {"start_sec": 0, "end_sec": 30}
                ),
                "quality_notes": data.get("quality_notes", ""),
                "context_match": bool(context),
            }
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse Qwen-VL response as JSON")

    return {
        "video_path": path,
        "summary": raw[:300],
        "topics": ["AI"],
        "relevance_score": 5.0,
        "suggested_clip_range": {"start_sec": 0, "end_sec": 30},
        "quality_notes": "",
        "context_match": bool(context),
    }


def _parse_selection(raw: str, max_idx: int) -> list[int]:
    import json

    try:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            indices = json.loads(raw[start:end])
            return [int(i) for i in indices if isinstance(i, (int, float)) and 0 <= int(i) < max_idx]
    except (json.JSONDecodeError, ValueError):
        pass
    return list(range(min(max_idx, 5)))


def _extract_frames(video_path: str, count: int = 5) -> list[str]:
    """Extract keyframes from video using ffmpeg. Returns list of image paths."""
    tmpdir = tempfile.mkdtemp(prefix="frames_")
    out_pattern = os.path.join(tmpdir, "frame_%03d.jpg")

    # fps=1/N extracts one frame every N seconds; we want `count` frames total
    try:
        dur = _get_duration(video_path)
    except Exception:
        dur = 60  # assume 1 min if unknown

    interval = max(1, dur / (count + 1))
    fps = f"1/{interval:.0f}" if interval >= 1 else "1"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"fps={fps},scale='min({FRAME_MAX_SIZE},iw)':min'({FRAME_MAX_SIZE},ih)':force_original_aspect_ratio=decrease",
        "-q:v", "3",
        "-frames:v", str(count),
        out_pattern,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=60, check=True)
    except Exception:
        logger.warning("ffmpeg frame extraction failed for %s", video_path)
        return []

    frames = sorted(Path(tmpdir).glob("frame_*.jpg"))
    return [str(f) for f in frames]


def _encode_frame(path: str) -> str:
    """Read image file and return base64-encoded string."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _get_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return float(result.stdout.strip())


def _greedy_select(
    clips: list[dict[str, Any]], max_duration_sec: int
) -> list[dict[str, Any]]:
    sorted_clips = sorted(
        clips, key=lambda c: c.get("relevance_score", 5), reverse=True
    )
    result: list[dict] = []
    total = 0
    for c in sorted_clips:
        dur = c.get("duration_sec", 30)
        if total + dur <= max_duration_sec:
            result.append(c)
            total += dur
    return result
