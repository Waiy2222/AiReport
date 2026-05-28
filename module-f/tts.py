"""Text-to-speech engine — Edge TTS (free, good Chinese quality).

Phase 2: added long-text chunking + concatenation + synthesize() alias.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./output")).resolve()
TTS_VOICE = os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoNeural")  # warm female
TTS_RATE = os.getenv("TTS_RATE", "+0%")  # speed adjustment
TTS_CHUNK_SIZE = int(os.getenv("TTS_CHUNK_SIZE", "3000"))  # max chars per chunk


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

        try:
            cmd = [
                "edge-tts",
                "--voice", voice,
                "--rate", TTS_RATE,
                "--text", text,
                "--write-media", output_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
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

    async def synthesize(
        self,
        text: str,
        output_path: str,
        voice: str | None = None,
    ) -> str | None:
        """Alias for generate() — returns path or None."""
        return await self.generate(text, output_path, voice)

    async def synthesize_long_text(
        self,
        text: str,
        output_path: str,
        voice: str | None = None,
    ) -> str | None:
        """Synthesize long text by splitting into chunks and concatenating.

        Edge TTS has a character limit (~3000 chars per call).
        For longer texts, this method splits, generates each chunk,
        and concatenates the audio files.
        """
        if len(text) <= TTS_CHUNK_SIZE:
            return await self.generate(text, output_path, voice)

        voice = voice or TTS_VOICE
        chunks = self._split_text(text, TTS_CHUNK_SIZE)
        chunk_files: list[str] = []

        logger.info(
            "Long text: %d chars, splitting into %d chunks",
            len(text), len(chunks),
        )

        for i, chunk in enumerate(chunks):
            chunk_path = str(
                Path(output_path).parent / f"chunk_{i:03d}.mp3"
            )
            result = await self.generate(chunk, chunk_path, voice)
            if result:
                chunk_files.append(result)
            else:
                logger.warning("Chunk %d/%d failed", i + 1, len(chunks))

        if not chunk_files:
            logger.warning("All TTS chunks failed")
            return None

        if len(chunk_files) == 1:
            # Single chunk — just rename
            Path(chunk_files[0]).rename(output_path)
            return output_path

        # Concatenate chunks using ffmpeg or pydub
        return await self._concat_audio(chunk_files, output_path)

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
        """Return available voices."""
        return dict(self.VOICES)

    # ---- internal -----------------------------------------------------

    @staticmethod
    def _split_text(text: str, max_chars: int) -> list[str]:
        """Split text into chunks at sentence boundaries."""
        import re
        sentences = re.split(r"(?<=[。！？.!?])", text)
        chunks: list[str] = []
        current = ""

        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(current) + len(s) <= max_chars:
                current += s
            else:
                if current:
                    chunks.append(current.strip())
                # If a single sentence is too long, split by punctuation
                if len(s) > max_chars:
                    sub_chunks = re.split(r"(?<=[，,；;])", s)
                    for sc in sub_chunks:
                        if not sc.strip():
                            continue
                        if len(sc) > max_chars:
                            # Force split at max_chars
                            for i in range(0, len(sc), max_chars):
                                chunks.append(sc[i:i+max_chars].strip())
                        else:
                            chunks.append(sc.strip())
                else:
                    current = s

        if current:
            chunks.append(current.strip())

        return [c for c in chunks if c]

    async def _concat_audio(
        self, audio_files: list[str], output_path: str
    ) -> str | None:
        """Concatenate multiple audio files using ffmpeg."""
        concat_file = str(output_path) + ".txt"
        try:
            with open(concat_file, "w", encoding="utf-8") as f:
                for af in audio_files:
                    resolved = Path(af).resolve().as_posix()
                    f.write(f"file '{resolved}'\n")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                output_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                logger.info(
                    "Concatenated %d audio chunks -> %s",
                    len(audio_files), output_path,
                )
                return output_path
            else:
                logger.warning(
                    "Audio concat failed: %s", result.stderr[:200]
                )
                # Fallback: return first chunk
                if audio_files:
                    Path(audio_files[0]).rename(output_path)
                    return output_path
                return None

        except Exception as e:
            logger.warning("Audio concatenation failed: %s", e)
            return audio_files[0] if audio_files else None
        finally:
            if Path(concat_file).exists():
                Path(concat_file).unlink()

    def _mock_audio(self, text: str, output_path: str) -> str:
        """Create a minimal valid MP3 file for testing (silence)."""
        # Minimal MP3 frame (silence) — won't crash FFmpeg
        with open(output_path, "wb") as f:
            f.write(b'\xff\xfb\x90\x00')
        logger.warning("Created mock silence audio: %s", output_path)
        return output_path
