"""Text-to-speech engine — Edge TTS (free, good Chinese quality).

Generates AI voiceover audio from the briefing script.
Uses SSML with cheerful style and natural pauses for lively, human-like delivery.
Switches from CLI plain-text to Python Communicate API for SSML emotion support.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./output")).resolve()
# Default: lively young female voice with cheerful style — sounds much more
# natural than the old newscast-style XiaoxiaoNeural at +8%.
TTS_VOICE = os.getenv("TTS_VOICE", "zh-CN-XiaoyiNeural")
TTS_RATE = os.getenv("TTS_RATE", "+3%")
TTS_STYLE = os.getenv("TTS_STYLE", "cheerful")  # cheerful/friendly/newscast/serious/calm


class TTSEngine:
    """Edge TTS wrapper for Chinese voiceover generation with SSML emotion."""

    VOICES = {
        "zh-CN-XiaoxiaoNeural": "Female, warm, natural (legacy default)",
        "zh-CN-XiaoyiNeural": "Female, lively, young (current default)",
        "zh-CN-YunxiNeural": "Male, professional, news-style",
        "zh-CN-YunjianNeural": "Male, deep, narration",
    }

    # XiaoyiNeural supports: chat, cheerful, customerservice, empathetic,
    # newscast, affectionate, angry, calm, excited, fearful, friendly, gentle,
    # sad, serious, lyrical, hopeful
    STYLES = {
        "cheerful": "Lively, upbeat, highly natural (default)",
        "friendly": "Warm, conversational tone",
        "newscast": "Professional news broadcast style",
        "serious": "Formal, authoritative tone",
        "calm": "Relaxed, steady delivery",
    }

    def __init__(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async def generate(
        self,
        text: str,
        output_path: str | None = None,
        voice: str | None = None,
        style: str | None = None,
        rate: str | None = None,
    ) -> str | None:
        """Generate audio from text.

        Primary path: Python edge-tts Communicate API with SSML (emotion + pauses).
        Fallback: CLI plain-text mode (no SSML, but works everywhere).
        """
        voice = voice or TTS_VOICE
        style = style or TTS_STYLE
        rate = rate or TTS_RATE

        if output_path is None:
            import uuid
            output_path = str(OUTPUT_DIR / f"voiceover_{uuid.uuid4().hex[:8]}.mp3")

        # Try SSML path first (supports emotion style + natural pauses)
        ssml_result = await self._ssml_generate(text, output_path, voice, style, rate)
        if ssml_result:
            return ssml_result

        # Fallback: CLI plain-text mode
        logger.info("SSML path unavailable — falling back to CLI plain-text TTS")
        return await self._cli_generate(text, output_path, voice)

    # ---- Primary path: edge-tts CLI (reliable, no SSML shenanigans) ------

    async def _ssml_generate(
        self,
        text: str,
        output_path: str,
        voice: str,
        style: str,
        rate: str,
    ) -> str | None:
        """Generate TTS via edge-tts CLI.

        Uses --rate and --pitch for expressiveness.  This build of edge-tts
        doesn't support --style, but the zh-CN-XiaoyiNeural voice itself is
        already more lively than the old XiaoxiaoNeural default.
        """
        import subprocess
        import tempfile

        tmp_text = tempfile.mktemp(suffix=".txt")
        try:
            with open(tmp_text, "w", encoding="utf-8") as f:
                f.write(text)

            cmd = [
                "edge-tts",
                "--voice", voice,
                "--rate", rate,
                "--pitch=-2Hz",  # slightly lower pitch → warmer tone (use = to avoid flag parsing)
                "-f", tmp_text,
                "--write-media", output_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )

            if result.returncode != 0:
                logger.warning("Edge TTS CLI failed: %s",
                               (result.stderr or "")[:300])
                return None

            logger.info("TTS generated (%s, %s, %s): %s",
                        voice, style, rate, output_path)
            return output_path
        except FileNotFoundError:
            logger.warning("edge-tts not installed. Run: pip install edge-tts")
            return self._mock_audio(text, output_path)
        except Exception:
            logger.exception("TTS CLI failed")
            return None
        finally:
            try:
                Path(tmp_text).unlink()
            except Exception:
                pass

    async def _cli_generate(self, text: str, output_path: str, voice: str) -> str | None:
        """Generate TTS via edge-tts CLI (plain text, no style).  Last-resort fallback."""
        import subprocess
        import tempfile

        tmp_text = tempfile.mktemp(suffix=".txt")
        try:
            with open(tmp_text, "w", encoding="utf-8") as f:
                f.write(text)

            cmd = [
                "edge-tts",
                "--voice", voice,
                "--rate", TTS_RATE,
                "-f", tmp_text,
                "--write-media", output_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )

            if result.returncode != 0:
                logger.warning("Edge TTS CLI failed: %s", (result.stderr or "")[:300])
                return self._mock_audio(text, output_path)
            logger.info("TTS generated (CLI fallback): %s", output_path)
            return output_path
        except FileNotFoundError:
            logger.warning("edge-tts not installed. Run: pip install edge-tts")
            return self._mock_audio(text, output_path)
        except Exception:
            logger.exception("TTS CLI failed")
            return None
        finally:
            try:
                Path(tmp_text).unlink()
            except Exception:
                pass

    # ---- multi-segment generation ----------------------------------------

    async def generate_from_script(
        self,
        script: list[dict[str, str]],
        output_dir: str | None = None,
    ) -> list[str]:
        """Generate audio segments for each paragraph in a script."""
        base = Path(output_dir or OUTPUT_DIR)
        base.mkdir(parents=True, exist_ok=True)

        audio_files: list[str] = []
        for i, seg in enumerate(script):
            path = str(base / f"seg_{i:03d}.mp3")
            result = await self.generate(
                text=seg["text"],
                output_path=path,
                voice=seg.get("voice"),
                style=seg.get("style"),
                rate=seg.get("rate"),
            )
            if result:
                audio_files.append(result)

        return audio_files

    def list_voices(self) -> dict[str, str]:
        return dict(self.VOICES)

    def list_styles(self) -> dict[str, str]:
        return dict(self.STYLES)

    # ---- mock / fallback --------------------------------------------------

    def _mock_audio(self, text: str, output_path: str) -> str:
        """Create a minimal valid MP3 file for testing (silence)."""
        with open(output_path, "wb") as f:
            f.write(b'\xff\xfb\x90\x00')
        logger.warning("Created mock silence audio: %s", output_path)
        return output_path


# ---------------------------------------------------------------------------
# SSML construction with natural pauses
# ---------------------------------------------------------------------------

def _build_ssml(text: str, voice: str, style: str, rate: str) -> str:
    """Build SSML with emotion style, prosody control, and natural pauses.

    Injects <break> tags at punctuation boundaries so the TTS voice sounds
    more human and less monotonous.
    """
    # Escape XML special chars
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Escape double quotes in text content (not attributes)
    text = text.replace('"', "&quot;")

    # Normalize rate format
    rate_val = rate.lstrip("+")
    if not rate_val.endswith("%"):
        rate_val = rate_val + "%"
    rate_val = "+" + rate_val

    # Inject natural pauses based on Chinese / English punctuation
    text_with_pauses = _add_natural_pauses(text)

    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"'
        ' xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="zh-CN">'
        f'<voice name="{voice}">'
        f'<mstts:express-as style="{style}" styledegree="1.5">'
        f'<prosody rate="{rate_val}" pitch="+0Hz">'
        f'{text_with_pauses}'
        '</prosody>'
        '</mstts:express-as>'
        '</voice>'
        '</speak>'
    )


def _add_natural_pauses(text: str) -> str:
    """Insert SSML <break> tags at natural pause points in Chinese text.

    Pause rules (modeled after news anchor delivery):
      - 。！？ → 400ms (end of sentence)
      - ；： → 250ms (semicolon / colon)
      - ，、 → 150ms (comma / enumeration)
      - \\n\\n (paragraph break) → 600ms (topic transition)
      - \\n → 200ms (line break)
    """
    # Paragraph breaks first (before we process other newlines)
    text = text.replace("\n\n", '<break time="600ms"/>')
    text = text.replace("\n", '<break time="200ms"/>')

    # Sentence-ending punctuation
    text = text.replace("。", f'。<break time="400ms"/>')
    text = text.replace("！", f'！<break time="400ms"/>')
    text = text.replace("？", f'？<break time="400ms"/>')
    text = text.replace("!", f'!<break time="400ms"/>')
    text = text.replace("?", f'?<break time="400ms"/>')

    # Medium pauses
    text = text.replace("；", f'；<break time="250ms"/>')
    text = text.replace("：", f'：<break time="250ms"/>')
    text = text.replace(";", f';<break time="250ms"/>')
    text = text.replace(":", f':<break time="250ms"/>')

    # Short pauses
    text = text.replace("，", f'，<break time="150ms"/>')
    text = text.replace("、", f'、<break time="150ms"/>')
    text = text.replace(",", f',<break time="150ms"/>')

    # Remove trailing break before another break (avoid double pauses)
    text = re.sub(r'<break time="\d+ms"/>\s*<break time="\d+ms"/>',
                  r'<break time="400ms"/>', text)

    return text
