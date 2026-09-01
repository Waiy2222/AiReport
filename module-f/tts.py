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

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./output")).resolve()
# Default: YunjianNeural — male, passionate (激情), most energetic zh-CN voice.
# +15% rate with +3Hz pitch for bright, lively short-video delivery.
TTS_VOICE = os.getenv("TTS_VOICE", "zh-CN-YunjianNeural")
TTS_RATE = os.getenv("TTS_RATE", "+8%")
TTS_STYLE = os.getenv("TTS_STYLE", "newscast")


class TTSEngine:
    """Edge TTS wrapper for Chinese voiceover generation with SSML emotion."""

    VOICES = {
        # === Female voices ===
        "zh-CN-XiaoxiaoNeural": "Female, warm, gentle (温柔)",
        "zh-CN-XiaoyiNeural": "Female, lively, young (活泼) ★ default",
        # === Male voices ===
        "zh-CN-YunxiNeural": "Male, lively, sunshine (清朗阳光)",
        "zh-CN-YunjianNeural": "Male, passionate, intense (激情) ★ default",
        "zh-CN-YunyangNeural": "Male, professional, reliable (专业可靠)",
        "zh-CN-YunxiaNeural": "Male, cute, cartoon-style (可爱)",
        # === Dialect ===
        "zh-CN-liaoning-XiaobeiNeural": "Female, Liaoning dialect (辽宁)",
        "zh-CN-shaanxi-XiaoniNeural": "Female, Shaanxi dialect (陕西)",
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
        self._chattts = None  # lazy load

    async def generate(
        self,
        text: str,
        output_path: str | None = None,
        voice: str | None = None,
        style: str | None = None,
        rate: str | None = None,
    ) -> str | None:
        """Generate audio from text (no subtitle timing data).

        Primary: ChatTTS (natural Chinese with emotion, no robotic sound).
        Fallback: edge-tts CLI (reliable, always works).
        """
        voice = voice or TTS_VOICE
        style = style or TTS_STYLE
        rate = rate or TTS_RATE

        if output_path is None:
            import uuid
            output_path = str(OUTPUT_DIR / f"voiceover_{uuid.uuid4().hex[:8]}.mp3")

        # Primary: ChatTTS for natural Chinese speech
        chattts_result = await self._chattts_generate(text, output_path, rate)
        if chattts_result:
            return chattts_result

        # Fallback: edge-tts CLI
        logger.info("ChatTTS 不可用 → 回退到 edge-tts")
        return await self._edge_generate(text, output_path, voice, rate)

    async def generate_with_subs(
        self,
        text: str,
        output_path: str | None = None,
        voice: str | None = None,
        style: str | None = None,
        rate: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Generate audio + word-level VTT subtitles from the TTS engine.

        Returns (audio_path, vtt_path) — VTT contains phrase-level timestamps
        directly from the TTS synthesis engine, giving PERFECT voice sync.
        Fallback (ChatTTS/mock): audio only, no subtitles → returns (path, None).
        """
        voice = voice or TTS_VOICE
        style = style or TTS_STYLE
        rate = rate or TTS_RATE

        if output_path is None:
            import uuid
            output_path = str(OUTPUT_DIR / f"voiceover_{uuid.uuid4().hex[:8]}.mp3")

        # ChatTTS doesn't support word timestamps — edge-tts needed for sync
        # So skip ChatTTS when we need subtitles
        return await self._edge_generate_with_subs(text, output_path, voice, rate)

    async def _edge_generate_with_subs(
        self, text: str, output_path: str, voice: str, rate: str,
    ) -> tuple[str | None, str | None]:
        """Generate audio + VTT subtitles via edge-tts CLI."""
        import subprocess
        import tempfile

        vtt_path = output_path.rsplit(".", 1)[0] + ".vtt"
        tmp_text = tempfile.mktemp(suffix=".txt")
        try:
            with open(tmp_text, "w", encoding="utf-8") as f:
                f.write(text)

            cmd = [
                "edge-tts",
                "--voice", voice,
                "--rate", rate,
                "--pitch=+3Hz",
                "-f", tmp_text,
                "--write-media", output_path,
                "--write-subtitles", vtt_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )

            if result.returncode != 0:
                logger.warning("Edge TTS CLI failed: %s",
                               (result.stderr or "")[:300])
                # Try without subtitles as fallback
                return await self._edge_generate(text, output_path, voice, rate), None

            logger.info("TTS + subs generated (%s, %s): %s", voice, rate, output_path)
            return output_path, vtt_path if Path(vtt_path).exists() else None
        except FileNotFoundError:
            logger.warning("edge-tts not installed")
            return None, None
        except Exception:
            logger.exception("TTS CLI failed")
            return None, None
        finally:
            try:
                Path(tmp_text).unlink()
            except Exception:
                pass

    async def generate(
        self,
        text: str,
        output_path: str | None = None,
        voice: str | None = None,
        style: str | None = None,
        rate: str | None = None,
    ) -> str | None:
        """Generate audio from text.

        Primary: ChatTTS (natural Chinese with emotion, no robotic sound).
        Fallback: edge-tts CLI (reliable, always works).
        """
        voice = voice or TTS_VOICE
        style = style or TTS_STYLE
        rate = rate or TTS_RATE

        if output_path is None:
            import uuid
            output_path = str(OUTPUT_DIR / f"voiceover_{uuid.uuid4().hex[:8]}.mp3")

        # Primary: ChatTTS for natural Chinese speech
        chattts_result = await self._chattts_generate(text, output_path, rate)
        if chattts_result:
            return chattts_result

        # Fallback: edge-tts CLI
        logger.info("ChatTTS 不可用 → 回退到 edge-tts")
        return await self._edge_generate(text, output_path, voice, rate)

    # ---- ChatTTS: natural Chinese speech with emotion --------------------

    async def _chattts_generate(
        self, text: str, output_path: str, rate: str,
    ) -> str | None:
        """Generate speech using ChatTTS — natural, emotional Chinese TTS."""
        try:
            import torch
            import chattts
        except ImportError:
            return None

        try:
            if self._chattts is None:
                logger.info("ChatTTS: 加载模型...")
                chat = chattts.Chat()
                chat.load(compile=False)
                self._chattts = chat
                logger.info("ChatTTS: 模型就绪")

            # Parse rate: +15% → speed factor 1.15
            rate_val = 1.0
            if rate:
                try:
                    rate_val = 1.0 + int(rate.strip("+%")) / 100.0
                except ValueError:
                    rate_val = 1.0

            # Generate wav
            wav_path = output_path.rsplit(".", 1)[0] + ".wav"
            params = {
                "text": [text],
                "skip_refine_text": True,
                "do_text_normalization": True,
            }
            import numpy as np
            import soundfile as sf

            wavs = self._chattts.infer(params, use_decoder=True)
            if wavs and len(wavs) > 0:
                audio = wavs[0]
                # Apply speed via resampling if needed
                sf.write(wav_path, audio, 24000)

                # Convert wav → mp3 with ffmpeg
                import subprocess
                cmd = [
                    "ffmpeg", "-y", "-i", wav_path,
                    "-codec:a", "libmp3lame", "-b:a", "192k",
                    output_path,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                        encoding="utf-8", errors="replace")
                try:
                    Path(wav_path).unlink()
                except Exception:
                    pass

                if result.returncode == 0 and Path(output_path).exists():
                    logger.info("ChatTTS 生成: %s", output_path)
                    return output_path

            logger.warning("ChatTTS: 生成失败，回退 edge-tts")
            return None
        except Exception:
            logger.exception("ChatTTS: 异常")
            return None

    # ---- Edge TTS: reliable fallback ------------------------------------

    async def _edge_generate(
        self, text: str, output_path: str, voice: str, rate: str,
    ) -> str | None:
        """Generate via edge-tts CLI (reliable, always works)."""
        return await self._ssml_generate(text, output_path, voice, "newscast", rate)

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
                "--pitch=+3Hz",  # slightly brighter for energy
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
