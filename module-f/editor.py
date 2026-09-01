"""Video editing with FFmpeg.

Clip trimming, concatenation, transitions, audio mixing, and final compositing.
All operations are subprocess calls to ffmpeg.
"""

from __future__ import annotations

import logging
import os
import random
import subprocess
from pathlib import Path
logger = logging.getLogger(__name__)

# Domain-aware defaults (read from env, fall back to AI domain)
# Built-in presets + dynamic support via env vars for unknown domains
_VIDEO_DOMAIN = os.getenv("VIDEO_DOMAIN", "AI")
_DOMAIN_DISPLAY_MAP = {"AI": "AI智能体", "体育": "体育", "芯片": "芯片", "机器人": "机器人", "医疗": "医疗", "自动驾驶": "自动驾驶", "融资": "科技创投"}
_DOMAIN_BADGE_MAP = {"AI": "AI 早报", "体育": "体育早报", "芯片": "芯片早报", "机器人": "机器人早报", "医疗": "医疗早报", "自动驾驶": "自动驾驶早报", "融资": "创投早报"}


def _resolve_domain_display() -> str:
    """Resolve domain display name dynamically."""
    domain = os.getenv("VIDEO_DOMAIN", "AI")
    return _DOMAIN_DISPLAY_MAP.get(domain) or os.getenv("VIDEO_DOMAIN_DISPLAY") or domain


def _resolve_domain_host() -> str:
    """Resolve virtual host name dynamically."""
    domain = os.getenv("VIDEO_DOMAIN", "AI")
    return os.getenv("VIDEO_DOMAIN_HOST") or ({"AI": "AI主播"}.get(domain, "AI主播"))


def _resolve_domain_badge() -> str:
    """Resolve domain badge text dynamically."""
    domain = os.getenv("VIDEO_DOMAIN", "AI")
    return _DOMAIN_BADGE_MAP.get(domain) or os.getenv("VIDEO_DOMAIN_BADGE") or f"{_resolve_domain_display()}早报"


_DOMAIN_DISPLAY = _resolve_domain_display()
_DOMAIN_HOST = _resolve_domain_host()
_DOMAIN_BADGE = _resolve_domain_badge()

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
        if len(clip_paths) == 0:
            logger.warning("concat: empty clip list")
            return False

        if len(clip_paths) == 1:
            import shutil
            shutil.copy(clip_paths[0], output_path)
            return True

        # Build filter_complex: scale all to 1920x1080 fullscreen (crop, no black bars)
        filter_parts: list[str] = []
        for i, p in enumerate(clip_paths):
            # increase + crop: zoom to fill 1920x1080, crop excess
            filter_parts.append(
                f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                f"crop=1920:1080,setsar=1,fps=30[v{i}]"
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

    def concat_with_transitions(
        self,
        clip_paths: list[str],
        output_path: str,
        transition: str = "fadeblack",
        duration: float = 0.6,
    ) -> bool:
        """Concatenate clips with smooth xfade transitions between them.

        Uses FFmpeg's xfade filter for professional dip-to-black/fade effects
        between adjacent segments.  Single-clip lists are copied directly.

        Supported transitions: fade, fadeblack, fadewhite, dissolve, slideright,
        wipeleft, pixelize, zoomin, etc. (full xfade palette).

        Args:
            clip_paths: Ordered list of video files to join.
            output_path: Destination path for the concatenated video.
            transition: xfade transition type (default: 'fadeblack').
            duration: Transition duration in seconds (default: 0.6).
        """
        if len(clip_paths) == 0:
            logger.warning("concat_with_transitions: empty clip list")
            return False

        if len(clip_paths) == 1:
            import shutil
            shutil.copy(clip_paths[0], output_path)
            return True

        # ── Probe durations for offset calculation ──────────────────────
        clip_durations: list[float] = []
        for p in clip_paths:
            d = self.get_duration(p)
            clip_durations.append(d if d and d > 0 else 3.0)

        # ── Build xfade filter chain ────────────────────────────────────
        filter_parts: list[str] = []
        prev_label = f"v0"

        # First clip: scale to standard format (fullscreen crop)
        filter_parts.append(
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,setsar=1,fps=30,"
            f"setpts=PTS-STARTPTS[{prev_label}]"
        )

        cumulative_time = clip_durations[0]

        for i in range(1, len(clip_paths)):
            curr_label = f"v{i}"
            out_label = f"f{i - 1}"

            # Scale current clip (fullscreen crop)
            filter_parts.append(
                f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                f"crop=1920:1080,setsar=1,fps=30,"
                f"setpts=PTS-STARTPTS[{curr_label}]"
            )

            # xfade: transition starts at (cumulative_time - duration)
            offset = cumulative_time - duration
            if offset < 0:
                offset = 0.0

            filter_parts.append(
                f"[{prev_label}][{curr_label}]"
                f"xfade=transition={transition}:duration={duration}:offset={offset:.2f}"
                f"[{out_label}]"
            )

            cumulative_time += clip_durations[i] - duration
            prev_label = out_label

        filter_str = ";".join(filter_parts)

        cmd = [
            FFMPEG_BIN, "-y",
        ]
        for p in clip_paths:
            cmd.extend(["-i", p])
        cmd.extend([
            "-filter_complex", filter_str,
            "-map", f"[{prev_label}]",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-an",
            "-pix_fmt", "yuv420p",
            output_path,
        ])
        return self._run(cmd, f"concat_with_transitions {len(clip_paths)} clips")

    def reencode_final(self, input_path: str, output_path: str) -> bool:
        """Re-encode video with proper keyframes + faststart for smooth seeking.

        Takes the already-assembled video and re-encodes it with:
        - Keyframe every 30 frames (1s at 30fps) for seeking
        - movflags +faststart for streaming/progressive download
        - veryfast preset for reasonable quality/speed balance
        """
        cmd = [
            FFMPEG_BIN, "-y",
            "-i", input_path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-g", "30", "-movflags", "+faststart",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        return self._run(cmd, "reencode_final")

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

    def add_text_overlay(
        self,
        input_path: str,
        output_path: str,
        text: str,
        fontsize: int = 36,
        x: int = 28,
        y: int = 24,
    ) -> bool:
        """Overlay persistent top-left corner text — news ticker / chyron style.

        Draws white text with a semi-transparent dark background box that
        stays visible for the entire duration of the video.

        Uses textfile to avoid ffmpeg escaping issues with Chinese characters,
        and proper encoding params (keyframes + faststart) for smooth seeking.
        """
        # Write text to a temp file next to the output (same dir, short path)
        text_file = Path(output_path).with_suffix(".txt")
        text_file.write_text(text, encoding="utf-8")

        font_paths = [
            "C\\:/Windows/Fonts/msyh.ttc",
            "C\\:/Windows/Fonts/simhei.ttf",
            "C\\:/Windows/Fonts/simsun.ttc",
        ]
        fontfile = ""
        for fp in font_paths:
            if Path(fp.replace("\\:/", ":/")).exists():
                fontfile = fp
                break

        font_part = f":fontfile='{fontfile}'" if fontfile else ""
        # Use textfile with forward slashes + colon escaping for ffmpeg
        text_safe = str(text_file.resolve()).replace("\\", "/").replace(":", "\\:")
        vf = (
            f"drawtext=textfile='{text_safe}'"
            f":fontsize={fontsize}:fontcolor=white@0.95"
            f":x={x}:y={y}"
            f":box=1:boxcolor=black@0.5:boxborderw=10"
            f"{font_part}"
        )
        cmd = [
            FFMPEG_BIN, "-y",
            "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-g", "30", "-movflags", "+faststart",
            "-c:a", "copy",
            output_path,
        ]
        ok = self._run(cmd, f"add_text_overlay: {text[:30]}")
        # Clean up temp text file
        try:
            text_file.unlink(missing_ok=True)
        except Exception:
            pass
        return ok

    def burn_subtitles(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
    ) -> bool:
        """Burn subtitles — news ticker style with stable opaque background bar.

        Uses BorderStyle=4 (opaque box + outline) to eliminate subtitle jitter:
        each subtitle gets a solid dark background, anchoring it visually
        regardless of text length changes.
        """
        import shutil

        video_dir = str(Path(video_path).parent)
        local_sub = str(Path(video_dir) / "sub_burn.srt")
        shutil.copy(subtitle_path, local_sub)
        escaped_sub = local_sub.replace("\\", "\\\\").replace(":", "\\:")

        # BorderStyle=4: opaque background box (news ticker style)
        # Bold=0: regular weight for clean reading on busy backgrounds
        vf = (
            f"subtitles='{escaped_sub}'"
            f":force_style='FontName=Microsoft YaHei,FontSize=20,"
            f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            f"BorderStyle=4,Outline=1,Shadow=1,Bold=0,"
            f"Alignment=2,MarginV=40,MarginL=40,MarginR=40'"
        )

        cmd = [
            FFMPEG_BIN, "-y",
            "-i", video_path,
            "-vf", vf,
            "-c:a", "copy",
            output_path,
        ]
        success = self._run(cmd, f"burn_subtitles {video_path}")

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

    def image_to_video(
        self,
        image_path: str,
        output_path: str,
        duration_sec: float = 5.0,
    ) -> bool:
        """Convert a static image to video — stable, no animation glitches.

        Uses simple scale+crop+loop. No zoompan (causes visual twitching).
        """
        dur = max(duration_sec, 2.0)

        # Stable: scale to fill 1920x1080, crop excess, loop
        vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"

        cmd = [
            FFMPEG_BIN, "-y",
            "-loop", "1", "-i", image_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-t", f"{dur:.2f}",
            "-an",
            output_path,
        ]

        success = self._run(cmd, f"Image->video: {Path(image_path).name}")
        if success:
            logger.info("Image->video: %s -> %.1fs", Path(image_path).name, dur)
        return success


    def _generate_anime_avatar_frames(
        self, size: int = 100, temp_dir: str = ""
    ) -> list[str]:
        """Generate vivid anime avatar frames with smooth talking animation.

        Produces 8 frames with:
        - Smooth sine-wave mouth cycle (closed→open→closed)
        - Eye blinking (every 4th frame)
        - Subtle head bob (1-2px vertical shift)
        - All the anime details: big eyes, colored hair, blush, ahoge

        At 8fps playback, the cycle repeats naturally simulating speech.
        Returns list of 8 PNG paths.
        """
        from PIL import Image, ImageDraw

        frames = []
        half = size // 2
        face_r = half - 6
        face_center_base = (half, half + 2)

        # ── 8-frame cycle ──
        for fi in range(8):
            # Sine-wave mouth openness: 0=closed, 1=full open
            phase = fi / 8.0  # 0.0 → 1.0
            openness = abs(2.0 * (phase - 0.25))  # peaks at 0.25, 0 at 0.0/0.5
            openness = min(openness, 1.0) * 1.2  # clamp + boost

            # Subtle head bob (1-2px vertical)
            bob_y = -1 if fi < 4 else 1

            # Eye blink: every 4th frame (fi=3,7) → half-closed
            is_blinking = (fi == 3 or fi == 7)

            face_center = (face_center_base[0], face_center_base[1] + bob_y)
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # ---- Face ----
            draw.ellipse(
                [face_center[0] - face_r, face_center[1] - face_r,
                 face_center[0] + face_r, face_center[1] + face_r],
                fill=(255, 220, 188, 255),
            )

            # ---- Hair ----
            hair_color = (45, 85, 155, 255)
            hair_hi = (70, 120, 200, 255)
            draw.ellipse(
                [face_center[0] - face_r - 4, face_center[1] - face_r - 10,
                 face_center[0] + face_r + 4, face_center[1] + face_r - 20],
                fill=hair_color,
            )
            for side_x in [-face_r + 6, face_r - 6]:
                draw.ellipse(
                    [face_center[0] + side_x - 14, face_center[1] - 25,
                     face_center[0] + side_x + 14, face_center[1] + face_r - 15],
                    fill=hair_color,
                )
            # Bangs
            bangs_y = face_center[1] - face_r + 8
            for bx in range(face_center[0] - face_r + 4, face_center[0] + face_r - 3, 18):
                bh = 16 + (bx % 7) * 3
                draw.ellipse([bx - 11, bangs_y - 8, bx + 11, bangs_y + bh], fill=hair_color)
            for bx in range(face_center[0] - face_r + 12, face_center[0] + face_r - 12, 30):
                draw.ellipse([bx - 6, bangs_y - 2, bx + 6, bangs_y + 10], fill=hair_hi)
            # Ahoge
            ahoge_cx = face_center[0] + 8
            ahoge_cy = face_center[1] - face_r - 2
            draw.arc([ahoge_cx - 8, ahoge_cy - 15, ahoge_cx + 12, ahoge_cy + 5],
                     start=140, end=300, fill=hair_color, width=4)

            # ---- Eyes ----
            eye_y = face_center[1] - 12
            for eye_cx in [face_center[0] - 20, face_center[0] + 20]:
                if is_blinking:
                    # Blink: horizontal line
                    draw.line(
                        [eye_cx - 14, eye_y, eye_cx + 14, eye_y],
                        fill=(25, 30, 40, 255), width=3,
                    )
                else:
                    draw.ellipse(
                        [eye_cx - 14, eye_y - 15, eye_cx + 14, eye_y + 10],
                        fill=(25, 30, 40, 255),
                    )
                    draw.ellipse(
                        [eye_cx - 9, eye_y - 9, eye_cx + 9, eye_y + 7],
                        fill=(60, 140, 230, 255),
                    )
                    draw.ellipse(
                        [eye_cx - 4, eye_y - 5, eye_cx + 4, eye_y + 5],
                        fill=(10, 12, 18, 255),
                    )
                    draw.ellipse(
                        [eye_cx - 7, eye_y - 10, eye_cx - 1, eye_y - 4],
                        fill=(255, 255, 255, 240),
                    )
                    draw.ellipse(
                        [eye_cx + 2, eye_y - 7, eye_cx + 6, eye_y - 3],
                        fill=(240, 248, 255, 200),
                    )
                # Eyelid
                draw.arc(
                    [eye_cx - 14, eye_y - 15, eye_cx + 14, eye_y + 10],
                    start=180, end=360,
                    fill=(20, 22, 30, 200), width=2,
                )

            # ---- Eyebrows ----
            for eb_cx, eb_angle in [(face_center[0] - 20, 10), (face_center[0] + 20, -10)]:
                draw.arc(
                    [eb_cx - 10, eye_y - 28, eb_cx + 10, eye_y - 14],
                    start=180 + eb_angle, end=360 + eb_angle,
                    fill=(45, 60, 100, 200), width=3,
                )

            # ---- Nose ----
            nose_y = face_center[1] + 8
            draw.ellipse(
                [face_center[0] - 2, nose_y - 2, face_center[0] + 2, nose_y + 1],
                fill=(220, 180, 150, 180),
            )

            # ---- Blush ----
            for blush_cx in [face_center[0] - 28, face_center[0] + 28]:
                draw.ellipse(
                    [blush_cx - 10, nose_y - 2, blush_cx + 10, nose_y + 12],
                    fill=(255, 150, 160, 100),
                )

            # ---- Mouth (smoooth sine-wave openness) ----
            mouth_y = nose_y + 14
            mouth_w = 7
            mouth_h = max(3, int(openness * 16))
            if mouth_h <= 4:
                # Nearly closed: draw smile arc
                draw.arc(
                    [face_center[0] - mouth_w, mouth_y - 2,
                     face_center[0] + mouth_w, mouth_y + 4],
                    start=0, end=180,
                    fill=(200, 120, 110, 220), width=2,
                )
            else:
                # Open mouth: dark oval with tongue
                draw.ellipse(
                    [face_center[0] - mouth_w, mouth_y - 2,
                     face_center[0] + mouth_w, mouth_y + mouth_h],
                    fill=(70, 30, 25, 230),
                )
                if mouth_h > 8:
                    draw.ellipse(
                        [face_center[0] - 5, mouth_y + 3,
                         face_center[0] + 5, mouth_y + mouth_h - 2],
                        fill=(220, 110, 110, 210),
                    )

            # ---- Glow ring ----
            glow_r = face_r + 4
            for ring_i in range(3):
                alpha = 30 - ring_i * 8
                draw.ellipse(
                    [face_center[0] - glow_r - ring_i * 2,
                     face_center[1] - glow_r - ring_i * 2,
                     face_center[0] + glow_r + ring_i * 2,
                     face_center[1] + glow_r + ring_i * 2],
                    outline=(70, 140, 240, alpha), width=1,
                )

            out_path = str(Path(temp_dir) / f"_anime_{fi:02d}.png")
            img.save(out_path, "PNG")
            frames.append(out_path)

        logger.info("Anime avatar: 8 vivid frames (blink+bob+mouth) %dx%d → %s",
                     size, size, Path(temp_dir).name)
        return frames

    def add_virtual_anchor(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        host_name: str | None = None,
        domain_display: str | None = None,
    ) -> bool:
        """Add anime virtual anchor bar with talking animation (no waveform).

        Clean compact layout:
        - Left: Small anime avatar (80px) with vivid 8-frame talking animation
          (sine-wave mouth, blinking, head bob) at 8fps
        - Next to avatar: host name + subtitle text, compact
        - Slim 80px semi-transparent bar at bottom — minimal footprint
        """
        host_name = host_name or _resolve_domain_host()
        domain_display = domain_display or _resolve_domain_display()
        dur = self.get_duration(video_path) or 30
        temp_dir = Path(output_path).parent

        # ---- Step 0: Generate anime avatar frames (8 vivid frames) ----
        try:
            anime_frames = self._generate_anime_avatar_frames(size=100, temp_dir=str(temp_dir))
        except Exception as e:
            logger.warning("Anime avatar generation failed: %s, falling back to simple bar", e)
            anime_frames = []

        # ---- Step 1: Animated anime avatar video (8 vivid frames @ 8fps) ----
        anime_video_path = ""
        if anime_frames and len(anime_frames) >= 8:
            anime_video_path = str(temp_dir / "_anime_avatar.mp4")
            try:
                # Play all 8 frames in order at 8fps (~125ms per frame)
                # Full cycle = 1.0s of smooth talking + blinking + head bob
                frame_cycle = anime_frames  # all 8 frames: 0→1→2→3→4→5→6→7
                per_frame_dur = 0.125  # 8fps

                # Use concat with individual frame durations
                frame_inputs: list[str] = []
                for fi, fpath in enumerate(frame_cycle):
                    # Create a short clip for each frame
                    frame_clip = str(temp_dir / f"_anime_f{fi}.mp4")
                    cmd_frame = [
                        FFMPEG_BIN, "-y",
                        "-loop", "1", "-i", fpath,
                        "-c:v", "libx264", "-preset", "ultrafast",
                        "-crf", "18", "-pix_fmt", "yuva420p",
                        "-t", f"{per_frame_dur:.2f}", "-an",
                        frame_clip,
                    ]
                    if self._run(cmd_frame, f"anime frame {fi}"):
                        frame_inputs.append(frame_clip)

                if len(frame_inputs) >= 4:
                    # Concat frames into a single cycle, then loop for full duration
                    cycle_path = str(temp_dir / "_anime_cycle.mp4")
                    concat_list = str(temp_dir / "_anime_concat.txt")
                    with open(concat_list, "w", encoding="utf-8") as f:
                        for fp in frame_inputs:
                            f.write(f"file '{fp.replace(chr(92), '/')}'\n")

                    cmd_concat = [
                        FFMPEG_BIN, "-y",
                        "-f", "concat", "-safe", "0", "-i", concat_list,
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                        "-pix_fmt", "yuva420p", "-an",
                        cycle_path,
                    ]
                    if self._run(cmd_concat, "anime cycle concat"):
                        # Loop the cycle for full video duration
                        cycle_dur = self.get_duration(cycle_path) or 1.0
                        loop_count = max(1, int(dur / cycle_dur) + 1)
                        loop_list = str(temp_dir / "_anime_loop.txt")
                        with open(loop_list, "w", encoding="utf-8") as f:
                            for _ in range(loop_count):
                                f.write(f"file '{cycle_path.replace(chr(92), '/')}'\n")

                        cmd_loop = [
                            FFMPEG_BIN, "-y",
                            "-f", "concat", "-safe", "0", "-i", loop_list,
                            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                            "-pix_fmt", "yuva420p",
                            "-t", f"{dur:.1f}", "-an",
                            anime_video_path,
                        ]
                        self._run(cmd_loop, "anime loop")
            except Exception as e:
                logger.warning("Anime avatar video failed: %s", e)
                anime_video_path = ""

        # ---- Step 2: Generate slim anchor text bar PNG (80px) ----
        anchor_bar_path = str(temp_dir / "_anchor_bar.png")
        try:
            from PIL import Image, ImageDraw, ImageFont
            bar_h = 80
            bar = Image.new("RGBA", (1080, bar_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(bar)

            # Dark gradient bar
            for x in range(1080):
                if x < 300:
                    alpha = 170
                elif x < 500:
                    alpha = 150
                else:
                    alpha = 120
                draw.rectangle([x, 0, x + 1, bar_h], fill=(8, 10, 22, alpha))

            # Top accent line
            draw.rectangle([0, 0, 1080, 2], fill=(60, 150, 240, 200))

            # ---- Font setup (smaller) ----
            font_paths = [
                "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf",
            ]
            font_name = None
            font_sub = None
            for fp in font_paths:
                if Path(fp).exists():
                    try:
                        font_name = ImageFont.truetype(fp, 18)
                        font_sub = ImageFont.truetype(fp, 13)
                        break
                    except Exception:
                        continue
            if font_name is None:
                font_name = ImageFont.load_default()
                font_sub = ImageFont.load_default()

            # ---- Text: host name (right of avatar) ----
            # Avatar center at x=55, radius=45 → right edge at x=100
            text_x = 110
            name_text = host_name
            sub_text = f"{domain_display}早报"

            bbox_name = draw.textbbox((0, 0), name_text, font=font_name)
            name_w, name_h = bbox_name[2] - bbox_name[0], bbox_name[3] - bbox_name[1]

            # Vertical center of slim bar
            name_y = (bar_h - name_h - 4 - 16) // 2  # centered vertically
            draw.text((text_x + 1, name_y + 1), name_text, font=font_name, fill=(0, 0, 0, 100))
            draw.text((text_x, name_y), name_text, font=font_name, fill=(255, 255, 255, 250))

            # Subtitle below name
            sub_y = name_y + name_h + 2
            draw.text((text_x + 1, sub_y + 1), sub_text, font=font_sub, fill=(0, 0, 0, 80))
            draw.text((text_x, sub_y), sub_text, font=font_sub, fill=(140, 190, 240, 230))

            bar.save(anchor_bar_path, "PNG")
        except Exception as e:
            logger.warning("Anchor bar PNG failed: %s", e)
            import shutil
            shutil.copy(video_path, output_path)
            return True

        # ---- Step 3: Composite everything (no waveform — clean layout) ----
        # Layer order (bottom to top):
        #   1. Main video (full screen)
        #   2. Avatar animation video (left side, positioned above bar)
        #   3. Anchor bar PNG (bottom strip, full width)
        #   4. Text overlay (on bar, positioned next to avatar)

        has_anime = anime_video_path and Path(anime_video_path).exists()

        if has_anime:
            # 3-input composite: video + anime avatar + bar
            cmd = [
                FFMPEG_BIN, "-y",
                "-i", video_path,
                "-i", anime_video_path,
                "-i", anchor_bar_path,
                "-filter_complex",
                # Scale anime avatar to 80x80 and place at left-bottom
                f"[1:v]scale=80:80:force_original_aspect_ratio=decrease,"
                f"pad=80:80:(ow-iw)/2:(oh-ih)/2[avatar];"
                # Place avatar at position (15, H-72) — above the slim bar
                f"[0:v][avatar]overlay=15:H-72[with_avatar];"
                # Anchor bar at bottom
                f"[with_avatar][2:v]overlay=0:H-h",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "copy",
                "-pix_fmt", "yuv420p",
                "-t", f"{dur:.1f}", output_path,
            ]
        else:
            # 2-input fallback: video + bar only (no anime avatar)
            cmd = [
                FFMPEG_BIN, "-y",
                "-i", video_path,
                "-i", anchor_bar_path,
                "-filter_complex",
                "[0:v][1:v]overlay=0:H-h",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "copy",
                "-pix_fmt", "yuv420p",
                "-t", f"{dur:.1f}", output_path,
            ]

        if self._run(cmd, "virtual anchor composite"):
            # Clean up temp files
            for p in [anchor_bar_path, anime_video_path]:
                if p:
                    try:
                        Path(p).unlink()
                    except Exception:
                        pass
            # Clean up anime frame files
            for fn in Path(temp_dir).glob("_anime_*.png"):
                try:
                    fn.unlink()
                except Exception:
                    pass
            for fn in Path(temp_dir).glob("_anime_*.mp4"):
                try:
                    fn.unlink()
                except Exception:
                    pass
            logger.info("Virtual anchor bar added: anime avatar + text (slim 80px)")
            return True
        else:
            logger.warning("Anchor composite failed, using original video")
            import shutil
            shutil.copy(video_path, output_path)
            return True  # non-fatal

    def extract_frame(self, video_path: str, output_path: str, time_sec: float = 3) -> bool:
        """Extract a single frame from the video as a JPG thumbnail.

        Args:
            video_path: Source video file.
            output_path: Destination path for the JPG image.
            time_sec: Timestamp in seconds to extract the frame from.

        Returns:
            True if extraction succeeded.
        """
        cmd = [
            FFMPEG_BIN, "-y",
            "-ss", str(time_sec),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            output_path,
        ]
        return self._run(cmd, f"extract_frame @{time_sec}s")

    def generate_cover(
        self,
        video_path: str,
        output_path: str,
        title: str | None = None,
        subtitle: str = "",
        frame_pct: float = 0.15,
        bg_image: str = "",
        headlines: list[str] | None = None,
        badge_text: str | None = None,
        domain_tags: list[str] | None = None,
    ) -> bool:
        """Generate a cover/thumbnail image with text overlay.

        Uses a clean background image if provided (bg_image), otherwise extracts
        a frame from the video.  Pillow renders the title/subtitle/branding overlay.

        Args:
            video_path: Source video file (fallback if bg_image is empty).
            output_path: Destination path for the cover JPG (1920x1080).
            title: Main title text (defaults to domain display name + 早报).
            subtitle: Secondary text (e.g. date).
            frame_pct: Position in video to capture (0.0-1.0).
            bg_image: Optional clean background image path (bypasses video extraction).
            headlines: Optional list of news headlines to display on the cover.
            badge_text: Top-left badge text (defaults to domain badge).
            domain_tags: Bottom card tags (defaults to generic tags).

        Returns:
            True if the cover was generated successfully.
        """
        if title is None:
            title = f"{_resolve_domain_display()}早报"
        if badge_text is None:
            badge_text = _resolve_domain_badge()
        if domain_tags is None:
            domain_tags = ["每日速览", "新闻资讯"]
        # Step 1: Generate a clean light-minimal background (36Kr/Huxiu style)
        try:
            from PIL import Image, ImageDraw, ImageFont

            img = Image.new("RGB", (1080, 1080), (248, 250, 252))
            draw = ImageDraw.Draw(img)

            # ---- Subtle warm gradient from top ----
            for y in range(400):
                ratio = y / 400
                r = int(248 - ratio * 8)
                g = int(250 - ratio * 10)
                b = int(252 - ratio * 15)
                draw.rectangle([0, y, 1080, y + 1], fill=(r, g, b))

            # ---- Left accent bar (thin vertical) ----
            draw.rectangle([0, 0, 6, 1080], fill=(59, 130, 246, 255))

            # ---- Large light geometric circle (top-right decoration) ----
            draw.ellipse([1300, -300, 2200, 600], fill=(235, 240, 248, 200))
            draw.ellipse([1400, -200, 2100, 500], fill=(225, 232, 245, 150))

            # ---- Bottom section: white card area ----
            draw.rectangle([0, 680, 1080, 1080], fill=(255, 255, 255, 255))
            # Subtle top border of card
            draw.rectangle([0, 680, 1080, 682], fill=(230, 234, 240, 255))

            # ---- Font setup ----
            font_paths = [
                "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
            ]
            font_title = None
            font_sub = None
            font_badge = None
            font_tag = None
            for fp in font_paths:
                if Path(fp).exists():
                    try:
                        font_title = ImageFont.truetype(fp, 56)
                        font_sub = ImageFont.truetype(fp, 30)
                        font_badge = ImageFont.truetype(fp, 24)
                        font_tag = ImageFont.truetype(fp, 22)
                        break
                    except Exception:
                        continue
            if font_title is None:
                font_title = ImageFont.load_default()
                font_sub = font_title
                font_badge = font_title
                font_tag = font_title

            # ---- Top-left: domain badge ----
            # badge_text is set from parameter/default above
            badge_pad_x, badge_pad_y = 22, 10
            bbox_badge = draw.textbbox((0, 0), badge_text, font=font_badge)
            badge_w = bbox_badge[2] - bbox_badge[0] + badge_pad_x * 2
            badge_h = bbox_badge[3] - bbox_badge[1] + badge_pad_y * 2
            badge_x, badge_y = 80, 100
            draw.rounded_rectangle(
                [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
                radius=8, fill=(59, 130, 246, 255),
            )
            draw.text(
                (badge_x + badge_pad_x, badge_y + badge_pad_y),
                badge_text, font=font_badge, fill=(255, 255, 255, 255),
            )

            # ---- Centered large title ----
            title_lines = title.split("\n") if "\n" in title else [title]
            title_y_start = 280

            for li, line in enumerate(title_lines):
                bbox_t = draw.textbbox((0, 0), line, font=font_title)
                tw = bbox_t[2] - bbox_t[0]
                tx = (1080 - tw) // 2
                ty = title_y_start + li * 70
                draw.text((tx + 1, ty + 1), line, font=font_title, fill=(200, 200, 210, 60))
                draw.text((tx, ty), line, font=font_title, fill=(30, 35, 50, 255))

            # ---- Subtitle below title (or dynamic headlines) ----
            if headlines:
                # Display real news headlines on the cover
                hl_y = title_y_start + len(title_lines) * 70 + 30
                for hi, hl in enumerate(headlines[:4]):
                    # Truncate long headlines
                    display = hl[:28] + "…" if len(hl) > 28 else hl
                    bbox_hl = draw.textbbox((0, 0), display, font=font_tag)
                    hl_w = bbox_hl[2] - bbox_hl[0]
                    hl_x = (1080 - hl_w) // 2
                    hl_yy = hl_y + hi * 48

                    # Number badge
                    num_text = f"{hi + 1}"
                    num_size = 22
                    draw.ellipse([hl_x - 36, hl_yy + 2, hl_x - 8, hl_yy + 30],
                                 fill=(59, 130, 246, 255))
                    draw.text((hl_x - 30, hl_yy + 4), num_text, font=font_tag,
                             fill=(255, 255, 255, 255))

                    draw.text((hl_x + 8, hl_yy + 4), display, font=font_tag,
                             fill=(80, 90, 120, 255))

                # Subtitle: date below headlines
                if subtitle:
                    bbox_s = draw.textbbox((0, 0), subtitle, font=font_sub)
                    sw = bbox_s[2] - bbox_s[0]
                    sx = (1080 - sw) // 2
                    sy = hl_y + len(headlines[:4]) * 48 + 30
                    draw.text((sx, sy), subtitle, font=font_sub, fill=(150, 155, 175, 255))
            elif subtitle:
                bbox_s = draw.textbbox((0, 0), subtitle, font=font_sub)
                sw = bbox_s[2] - bbox_s[0]
                sx = (1080 - sw) // 2
                sy = title_y_start + len(title_lines) * 70 + 24
                draw.text((sx, sy), subtitle, font=font_sub, fill=(130, 140, 160, 255))

            # ---- Bottom card: tags row ----
            tags = domain_tags
            tag_y = 760
            total_tags_w = 0
            tag_info = []
            for tag_text in tags:
                bbox_tag = draw.textbbox((0, 0), tag_text, font=font_tag)
                tw_tag = bbox_tag[2] - bbox_tag[0]
                tag_info.append((tag_text, tw_tag))
                total_tags_w += tw_tag
            total_gap = (len(tags) - 1) * 24
            total_tags_w += total_gap
            tag_start_x = (1080 - total_tags_w) // 2

            cx = tag_start_x
            for tag_text, tw_tag in tag_info:
                draw.rounded_rectangle(
                    [cx, tag_y, cx + tw_tag + 28, tag_y + 40],
                    radius=20,
                    fill=(243, 245, 250, 255),
                    outline=(225, 230, 240, 255),
                    width=1,
                )
                draw.text((cx + 14, tag_y + 8), tag_text, font=font_tag, fill=(100, 110, 140, 255))
                cx += tw_tag + 28 + 24

            # ---- Bottom text ----
            bottom_text = f"每日{_resolve_domain_display()}领域重要资讯速览"
            bbox_bt = draw.textbbox((0, 0), bottom_text, font=font_tag)
            bw = bbox_bt[2] - bbox_bt[0]
            bx = (1080 - bw) // 2
            by = 860
            draw.text((bx, by), bottom_text, font=font_tag, fill=(170, 175, 190, 255))

            # ---- Bottom-right branding ----
            brand_text = "VCAST.AI"
            bbox_brand = draw.textbbox((0, 0), brand_text, font=font_sub)
            brand_w = bbox_brand[2] - bbox_brand[0]
            draw.text(
                (1080 - brand_w - 80, 1040),
                brand_text, font=font_sub, fill=(180, 185, 200, 255),
            )

            # ---- Save ----
            img.save(output_path, "JPEG", quality=92, optimize=True)
            logger.info("Cover generated: %s (%.0fKB)", output_path,
                        Path(output_path).stat().st_size / 1024)

        except Exception as e:
            logger.warning("Cover text overlay failed: %s", e)
            return False

        return Path(output_path).exists()

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

    def to_vertical(
        self,
        video_path: str,
        output_path: str,
        blur_strength: int = 20,
    ) -> bool:
        """Convert landscape (16:9) video to vertical (9:16) for Douyin.

        Places the original video centered horizontally with blurred background
        filling the top and bottom areas.  Audio is preserved as-is.

        Args:
            video_path: Source landscape video (e.g. 1920x1080).
            output_path: Destination vertical video (1920x1080).
            blur_strength: Boxblur strength for background (default 20).

        Returns:
            True if the vertical video was generated successfully.
        """
        # Layout math:
        #   Target canvas: 1080×1080
        #   Foreground: original scaled to fit width=1080 → 1080×608
        #   Position: centered vertically at y=(1080-608)/2 = 656
        #   Background: original scaled to fill 1080×1080 + boxblur

        filter_complex = (
            f"[0:v]split[orig][blur];"
            f"[blur]scale=1080:1080:force_original_aspect_ratio=increase,"
            f"crop=1080:1080,boxblur={blur_strength}:10[bg];"
            f"[orig]scale=1080:608:force_original_aspect_ratio=decrease,"
            f"pad=1080:608:(ow-iw)/2:(oh-ih)/2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )

        cmd = [
            FFMPEG_BIN, "-y",
            "-i", video_path,
            "-filter_complex", filter_complex,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        success = self._run(cmd, f"to_vertical {Path(video_path).name}")
        if success:
            size_mb = Path(output_path).stat().st_size / (1024 * 1024)
            logger.info("Vertical video: %s (%.1f MB)", Path(output_path).name, size_mb)
        return success

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
