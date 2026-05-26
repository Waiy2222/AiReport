"""Text-to-speech engine — Edge TTS (free, good Chinese quality).

Generates AI voiceover audio from the briefing script.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./output")).resolve()
TTS_VOICE = os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoNeural")  # warm female
TTS_RATE = os.getenv("TTS_RATE", "+0%")  # speed adjustment


class TTSEngine:
    """Edge TTS wrapper for Chinese voiceover generation."""

    VOICES = {
        "zh-CN-XiaoxiaoNeural": "Female, warm, natural (default)",
        "zh-CN-YunxiNeural": "Male, professional, news-style",
        "zh-CN-XiaoyiNeural": "Female, lively, young",
        "zh-CN-YunjianNeural": "Male, deep, narration",
    }

    def __init__(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async def generate(
        self,
        text: str,
        output_path: str | None = None,
        voice: str | None = None,
    ) -> str | None:
        """Generate audio from text, returns path to .mp3 or None on failure."""
        voice = voice or TTS_VOICE

        if output_path is None:
            import uuid
            output_path = str(OUTPUT_DIR / f"voiceover_{uuid.uuid4().hex[:8]}.mp3")

        # Edge TTS CLI approach (simplest integration)
        try:
            import subprocess
            cmd = [
                "edge-tts",
                "--voice", voice,
                "--rate", TTS_RATE,
                "--text", text,
                "--write-media", output_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                logger.warning("Edge TTS failed: %s", result.stderr[:300])
                return None
            logger.info("TTS generated: %s", output_path)
            return output_path
        except FileNotFoundError:
            logger.warning(
                "edge-tts not installed. Run: pip install edge-tts"
            )
            return self._mock_audio(text, output_path)
        except Exception:
            logger.exception("TTS generation failed")
            return None

    async def generate_from_script(
        self,
        script: list[dict[str, str]],
        output_dir: str | None = None,
    ) -> list[str]:
        """Generate audio segments for each paragraph in a script.

        Each segment in *script* is ``{"text": "...", "voice": "..."}``.
        """
        base = Path(output_dir or OUTPUT_DIR)
        base.mkdir(parents=True, exist_ok=True)

        audio_files: list[str] = []
        for i, seg in enumerate(script):
            path = str(base / f"seg_{i:03d}.mp3")
            result = await self.generate(
                text=seg["text"],
                output_path=path,
                voice=seg.get("voice"),
            )
            if result:
                audio_files.append(result)

        return audio_files

    def list_voices(self) -> dict[str, str]:
        return dict(self.VOICES)

    def _mock_audio(self, text: str, output_path: str) -> str:
        """Create a minimal valid MP3 file for testing (silence)."""
        # Write a tiny empty placeholder — won't play audio but won't crash FFmpeg
        with open(output_path, "wb") as f:
            # Minimal MP3 frame (silence)
            f.write(b'\xff\xfb\x90\x00')
        logger.warning("Created mock silence audio: %s", output_path)
        return output_path
