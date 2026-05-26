"""Subtitle generation with Whisper (OpenAI / local).

Generates .srt or .ass subtitles from the final video audio track.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./output")).resolve()
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")  # tiny/base/small/medium/large
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "zh")


class SubtitleGenerator:
    """Whisper-based subtitle engine."""

    def __init__(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self._model = None  # lazy load

    async def generate(
        self,
        audio_path: str,
        output_path: str | None = None,
        format: str = "srt",
    ) -> str | None:
        """Generate subtitles from an audio file. Returns path to .srt file."""
        output_path = output_path or str(
            OUTPUT_DIR / f"{Path(audio_path).stem}.{format}"
        )

        try:
            import whisper

            model = self._load_model(whisper)
            result = model.transcribe(
                audio_path,
                language=WHISPER_LANGUAGE,
                verbose=False,
            )

            # Write SRT
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(self._to_srt(result["segments"]))

            logger.info("Subtitles generated: %s (%d segments)",
                        output_path, len(result["segments"]))
            return output_path

        except ImportError:
            logger.warning("openai-whisper not installed — using mock")
            return self._mock_srt(audio_path, output_path)
        except Exception:
            logger.exception("Subtitle generation failed")
            return None

    async def generate_from_video(
        self,
        video_path: str,
        output_path: str | None = None,
    ) -> str | None:
        """Extract audio from video and generate subtitles."""
        import subprocess

        audio_path = str(OUTPUT_DIR / f"{Path(video_path).stem}_audio.wav")

        # extract audio
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        except Exception:
            logger.warning("Audio extraction failed for %s", video_path)
            return None

        result = await self.generate(audio_path, output_path)

        # clean up temp audio
        if Path(audio_path).exists():
            Path(audio_path).unlink()

        return result

    # ---- internal -----------------------------------------------------

    def _load_model(self, whisper_module):
        if self._model is None:
            self._model = whisper_module.load_model(WHISPER_MODEL)
        return self._model

    @staticmethod
    def _to_srt(segments: list[dict]) -> str:
        """Convert Whisper segments to SRT format."""
        lines: list[str] = []
        for i, seg in enumerate(segments, 1):
            start = _format_srt_time(seg["start"])
            end = _format_srt_time(seg["end"])
            text = seg["text"].strip()
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        return "\n".join(lines)

    def _mock_srt(self, audio_path: str, output_path: str) -> str:
        """Create a minimal .srt for testing."""
        content = (
            "1\n"
            "00:00:00,000 --> 00:00:05,000\n"
            "[Mock] AI 资讯每周视频 — 字幕待生成\n\n"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        return output_path


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
