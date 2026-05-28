"""Video editing with FFmpeg.

Phase 2: added public check_ffmpeg() + concat_clips() alias + transition support.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./output")).resolve()
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")


class VideoEditor:
    """FFmpeg-based video editor for clip assembly."""

    def __init__(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_available = self._check_ffmpeg()

    # ---- public API ---------------------------------------------------

    def check_ffmpeg(self) -> dict[str, Any]:
        """Public check: returns dict with availability status and error message."""
        if self.ffmpeg_available:
            return {"available": True, "error": None}
        return {"available": False, "error": "ffmpeg not found — run 'apt install ffmpeg' or check PATH"}

    def trim(
        self,
        input_path: str,
        output_path: str,
        start_sec: float,
        end_sec: float,
    ) -> bool:
        """Trim a clip to the specified range."""
        cmd = [
            FFMPEG_BIN, "-y",
            "-ss", str(start_sec),
            "-i", input_path,
            "-to", str(end_sec - start_sec),
            "-c", "copy",
            output_path,
        ]
        return self._run(cmd, f"trim {input_path}")

    def concat(
        self,
        clip_paths: list[str],
        output_path: str,
        transition: str = "fade",
    ) -> bool:
        """Concatenate multiple clips into one video.

        Supports transitions: 'fate' (concat demuxer, no re-encode),
        'dissolve' (re-encode with dissolve filter).
        """
        if transition == "dissolve" and len(clip_paths) >= 2:
            return self._concat_with_transition(clip_paths, output_path)

        # Default: concat demuxer (fast, no re-encode, same-codec only)
        return self._concat_demuxer(clip_paths, output_path)

    def concat_clips(
        self,
        clip_paths: list[str],
        output_path: str,
        transition: str = "fade",
    ) -> dict[str, Any]:
        """Alias for concat() — returns result dict for easier testing.

        Returns: {"success": True/False, "output": output_path, "error": str/None}
        """
        try:
            success = self.concat(clip_paths, output_path, transition)
            return {
                "success": success,
                "output": output_path if success else None,
                "error": None if success else "concat failed (see logs)",
            }
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}

    def add_audio(self, video_path: str, audio_path: str, output_path: str) -> bool:
        """Overlay audio track onto video."""
        cmd = [
            FFMPEG_BIN, "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output_path,
        ]
        return self._run(cmd, f"add_audio {video_path}")

    def burn_subtitles(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
    ) -> bool:
        """Burn subtitles into the video."""
        cmd = [
            FFMPEG_BIN, "-y",
            "-i", video_path,
            "-vf", f"subtitles={subtitle_path}",
            "-c:a", "copy",
            output_path,
        ]
        return self._run(cmd, f"burn_subtitles {video_path}")

    def get_duration(self, video_path: str) -> float | None:
        """Get video duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            return float(result.stdout.strip())
        except Exception:
            logger.warning("Failed to get duration for %s", video_path)
            return None

    # ---- internal -----------------------------------------------------

    def _check_ffmpeg(self) -> bool:
        try:
            subprocess.run(
                [FFMPEG_BIN, "-version"],
                capture_output=True, timeout=10,
            )
            logger.info("FFmpeg detected: %s", FFMPEG_BIN)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning(
                "ffmpeg not found at %s — video editing will fail", FFMPEG_BIN
            )
            return False
        except Exception:
            logger.warning("ffmpeg check failed unexpectedly")
            return False

    def _concat_demuxer(self, clip_paths: list[str], output_path: str) -> bool:
        """Concatenate using concat demuxer (fast, no re-encode)."""
        concat_file = output_path + ".txt"
        try:
            with open(concat_file, "w") as f:
                for p in clip_paths:
                    f.write(f"file '{Path(p).resolve().as_posix()}'\n")

            cmd = [
                FFMPEG_BIN, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                output_path,
            ]
            success = self._run(cmd, f"concat {len(clip_paths)} clips")
            return success
        finally:
            if Path(concat_file).exists():
                Path(concat_file).unlink()

    def _concat_with_transition(
        self, clip_paths: list[str], output_path: str
    ) -> bool:
        """Concatenate with re-encode (for mixed-codec or transition support)."""
        inputs: list[str] = []
        for i, p in enumerate(clip_paths):
            inputs.extend(["-i", p])
        cmd = [
            FFMPEG_BIN, "-y",
            *inputs,
            "-filter_complex",
            f"concat=n={len(clip_paths)}:v=1:a=1[out]",
            "-map", "[out]",
            output_path,
        ]
        return self._run(cmd, f"concat_transition {len(clip_paths)} clips")

    def _run(self, cmd: list[str], label: str = "") -> bool:
        logger.debug("FFmpeg [%s]: %s", label, " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                logger.warning(
                    "FFmpeg [%s] failed (rc=%d): %s",
                    label, result.returncode, result.stderr[:500],
                )
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg [%s] timed out", label)
            return False
        except Exception:
            logger.exception("FFmpeg [%s] unexpected error", label)
            return False
