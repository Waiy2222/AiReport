"""Video editing with FFmpeg.

Clip trimming, concatenation, transitions, audio mixing, and final compositing.
All operations are subprocess calls to ffmpeg.
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
        self._check_ffmpeg()

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
        audio: bool = True,
    ) -> bool:
        """Concatenate multiple clips into one video using filter_complex.

        Re-encodes to H.264/AAC for compatibility across different source formats.
        Set audio=False for B-roll only (strips original audio).
        """
        if len(clip_paths) == 1:
            import shutil
            shutil.copy(clip_paths[0], output_path)
            return True

        # Build filter_complex: scale all to 1920x1080, then concat
        filter_parts: list[str] = []
        for i, p in enumerate(clip_paths):
            # Scale and set SAR, fps standardization
            filter_parts.append(
                f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]"
            )

        # Concat all video streams
        vin = "".join(f"[v{i}]" for i in range(len(clip_paths)))
        filter_parts.append(f"{vin}concat=n={len(clip_paths)}:v=1:a=0[outv]")

        if audio:
            filter_parts.append(
                f"{''.join(f'[{i}:a]' for i in range(len(clip_paths)))}"
                f"concat=n={len(clip_paths)}:v=0:a=1[outa]"
            )

        filter_str = ";".join(filter_parts)

        cmd = [
            FFMPEG_BIN, "-y",
        ]
        for p in clip_paths:
            cmd.extend(["-i", p])
        cmd.extend([
            "-filter_complex", filter_str,
            "-map", "[outv]",
        ])
        if audio:
            cmd.extend(["-map", "[outa]", "-c:a", "aac", "-b:a", "128k"])
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            output_path,
        ])
        return self._run(cmd, f"concat {len(clip_paths)} clips")

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
        """Burn subtitles into the video with Chinese font support.

        Copies the subtitle file to the video directory to avoid path
        escaping issues with FFmpeg's subtitles filter on Windows.
        """
        import shutil

        # Copy subtitle to video dir, escape path for FFmpeg filter
        video_dir = str(Path(video_path).parent)
        local_sub = str(Path(video_dir) / "sub_burn.srt")
        shutil.copy(subtitle_path, local_sub)

        # Escape backslashes for FFmpeg filter string
        escaped_sub = local_sub.replace("\\", "\\\\").replace(":", "\\:")

        vf = (
            f"subtitles='{escaped_sub}'"
            f":force_style='FontName=Microsoft YaHei,FontSize=22,"
            f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,"
            f"Alignment=2,MarginV=30'"
        )

        cmd = [
            FFMPEG_BIN, "-y",
            "-i", video_path,
            "-vf", vf,
            "-c:a", "copy",
            output_path,
        ]
        success = self._run(cmd, f"burn_subtitles {video_path}")

        # Clean up temp subtitle
        try:
            Path(local_sub).unlink()
        except Exception:
            pass

        return success

    def get_duration(self, video_path: str) -> float | None:
        """Get video duration in seconds."""
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
                encoding="utf-8", errors="replace",
            )
            return float(result.stdout.strip())
        except Exception:
            logger.warning("Failed to get duration for %s", video_path)
            return None

    # ---- internal -----------------------------------------------------

    def _check_ffmpeg(self):
        try:
            subprocess.run(
                [FFMPEG_BIN, "-version"],
                capture_output=True, timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning(
                "ffmpeg not found at %s — video editing will fail", FFMPEG_BIN
            )

    def _run(self, cmd: list[str], label: str = "") -> bool:
        logger.debug("FFmpeg [%s]: %s", label, " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=1800,
                encoding="utf-8", errors="replace",
            )
            if result.returncode != 0:
                stderr_tail = (result.stderr or "")[:500]
                logger.warning(
                    "FFmpeg [%s] failed (rc=%d): %s",
                    label, result.returncode, stderr_tail,
                )
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg [%s] timed out", label)
            return False
        except Exception:
            logger.exception("FFmpeg [%s] unexpected error", label)
            return False
