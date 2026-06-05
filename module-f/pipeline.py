"""Video generation pipeline — full 10-step news briefing flow.

Previously two diverging implementations existed:
  • run_local.py  — full 10-step: intro card → RSS news → DeepSeek script
    → per-segment B-roll → TTS → script subtitles → closing segment
  • pipeline.py   — skeleton 6-step: generic B站 search → mock analysis
    → template script → Whisper subtitles (no intro/closing)

NOW UNIFIED: pipeline.py contains the complete logic.  run_local.py
delegates here.  The HTTP API (:8006 /generate) triggers the same flow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess as _sp
import ssl
import sys
import uuid as _uuid
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

# Ensure module-a scrapers are importable (for RSS news fetching)
_module_a_dir = str(Path(__file__).parent.parent / "module-a")
if _module_a_dir not in sys.path:
    sys.path.insert(0, _module_a_dir)

import asyncpg
import httpx

from gemini_client import GeminiClient
from video_search import VideoSearcher
from editor import VideoEditor
from tts import TTSEngine
from subtitle import SubtitleGenerator

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", str(Path(__file__).parent / "output"))).resolve()
DOWNLOAD_DIR = Path(os.getenv("VIDEO_DOWNLOAD_DIR", str(Path(__file__).parent / "downloads"))).resolve()
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ai_news")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# VideoPipeline — HTTP service wrapper
# ═══════════════════════════════════════════════════════════════════════════

class VideoPipeline:
    """Orchestrates the full 10-step news briefing video workflow."""

    def __init__(self):
        self.searcher = VideoSearcher()
        self.gemini = GeminiClient()
        self.tts = TTSEngine()
        self.subtitle = SubtitleGenerator()
        self.editor = VideoEditor()
        self._pool: asyncpg.Pool | None = None
        self._tasks: dict[str, asyncio.Task] = {}

    # ---- public API -------------------------------------------------------

    async def start(self, video_id: str, vtype: str, vdate: date) -> dict:
        pool = await self._get_pool()

        existing = await pool.fetchrow(
            "SELECT id, status FROM videos WHERE type = $1 AND date = $2",
            vtype, vdate,
        )
        if existing:
            vid = str(existing["id"])
            if existing["status"] in ("pending", "processing"):
                return {"id": vid, "status": existing["status"], "type": vtype, "date": vdate.isoformat()}
            await pool.execute("DELETE FROM videos WHERE id = $1", existing["id"])

        await pool.execute(
            "INSERT INTO videos (id, type, date, status) VALUES ($1, $2, $3, 'processing')",
            video_id, vtype, vdate,
        )

        task = asyncio.create_task(self._run_and_catch(video_id, vtype, vdate))
        self._tasks[video_id] = task

        return {"id": video_id, "status": "processing", "type": vtype, "date": vdate.isoformat()}

    async def status(self, video_id: str) -> dict:
        pool = await self._get_pool()
        row = await pool.fetchrow("SELECT * FROM videos WHERE id = $1::uuid", video_id)
        if row is None:
            raise ValueError(f"video not found: {video_id}")
        result = dict(row)
        for key in ("date", "created_at", "finished_at"):
            val = result.get(key)
            if isinstance(val, (date, datetime)):
                result[key] = val.isoformat()
        return result

    async def list_videos(self, limit: int = 10, offset: int = 0) -> list[dict]:
        pool = await self._get_pool()
        rows = await pool.fetch(
            "SELECT * FROM videos ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
        results = []
        for r in rows:
            d = dict(r)
            for key in ("date", "created_at", "finished_at"):
                val = d.get(key)
                if isinstance(val, (date, datetime)):
                    d[key] = val.isoformat()
            results.append(d)
        return results

    # ---- background task --------------------------------------------------

    async def _run_and_catch(self, video_id: str, vtype: str, vdate: date):
        try:
            output_path = await self.run_full_pipeline(video_id, vtype, vdate)
            pool = await self._get_pool()
            await pool.execute(
                "UPDATE videos SET status = 'done', output_path = $1, finished_at = now() WHERE id = $2",
                output_path, video_id,
            )
            logger.info("Video %s completed: %s", video_id, output_path)
        except Exception as e:
            logger.exception("Video %s failed", video_id)
            pool = await self._get_pool()
            await pool.execute(
                "UPDATE videos SET status = 'failed', error_msg = $1, finished_at = now() WHERE id = $2",
                str(e)[:500], video_id,
            )
        finally:
            self._tasks.pop(video_id, None)

    # ════════════════════════════════════════════════════════════════════
    # FULL 10-STEP PIPELINE (unified from run_local.py)
    # ════════════════════════════════════════════════════════════════════

    async def run_full_pipeline(self, video_id: str, vtype: str, vdate: date) -> str:
        pool = await self._get_pool()
        video_dir = OUTPUT_DIR / video_id
        video_dir.mkdir(parents=True, exist_ok=True)
        today = vdate.isoformat()

        # ---- Step -1: fetch intro background ----
        intro_bg = await _fetch_intro_background(video_dir)

        # ---- Step 0: fetch real AI news from RSS ----
        logger.info("[F:%s] Step 0: 抓取真实AI新闻 (RSS)...", video_id)
        real_news = await _fetch_real_news()
        if real_news:
            logger.info("[F:%s] 获取 %d 条真实AI新闻", video_id, len(real_news))

        # ---- Step 1: generate news briefing script (DeepSeek + real news) ----
        logger.info("[F:%s] Step 1: DeepSeek 基于真实新闻生成早报脚本...", video_id)
        script_text, segments = await _generate_news_script(today, real_news)
        if not script_text or not segments:
            raise RuntimeError("脚本生成失败！")

        script_path = video_dir / "script.txt"
        script_path.write_text(script_text, encoding="utf-8")
        logger.info("[F:%s] 脚本: %d 字, %d 段", video_id, len(script_text), len(segments))
        for i, seg in enumerate(segments):
            logger.info("[F:%s]   段%d: [%s] (%d字) B-roll: %s",
                        video_id, i, seg['topic'], len(seg['text']), seg.get('broll_keywords', ''))

        # ---- Step 2: search B站 B-roll per segment (quality-gate retry) ----
        MAX_RETRIES = 3
        segment_clips: list[list[dict]] = []

        for retry in range(MAX_RETRIES):
            logger.info("[F:%s] Step 2: 搜索B站素材 (attempt %d/%d)", video_id, retry + 1, MAX_RETRIES)
            segment_clips = []
            broll_failures = 0
            news_segment_count = 0

            for i, seg in enumerate(segments):
                topic = seg.get("topic", "")
                is_opening = "开场" in topic or "概述" in topic
                is_closing = "结尾" in topic or "总结" in topic

                if is_opening:
                    logger.info("[F:%s]   段%d [%s]: 跳过B-roll，使用标题卡", video_id, i, topic)
                    segment_clips.append([])
                    continue

                news_segment_count += 1
                keywords = seg.get("broll_keywords", "AI 科技")

                # Preprocess keywords for B站
                _EN_TO_CN = {
                    "github": "开源项目", "deepseek": "深度求索", "copilot": "编程助手",
                    "claude": "", "chatgpt": "", "openai": "OpenAI",
                    "gemini": "", "agent": "智能体", "openhuman": "桌面智能体",
                    "crewai": "多智能体框架", "autogpt": "自动智能体",
                    "devin": "AI编程", "cursor": "AI编程工具",
                    "openclaw": "桌面操控", "dumate": "办公智能体",
                    "manus": "AI智能体", "langgraph": "AI工作流",
                    "dify": "AI应用平台", "coze": "AI应用平台",
                    "mcp": "模型上下文协议", "a2a": "多智能体协作",
                    "comfyui": "AI工作流", "n8n": "自动化工作流",
                    "huggingface": "AI开源", "ollama": "本地大模型",
                }
                clean_kw: list[str] = []
                for w in keywords.split():
                    wl = w.lower().strip()
                    if wl in _EN_TO_CN:
                        cn = _EN_TO_CN[wl]
                        if cn:
                            clean_kw.append(cn)
                    elif wl.isascii() and len(wl) <= 2:
                        continue
                    else:
                        clean_kw.append(w)
                keywords = " ".join(clean_kw) if clean_kw else keywords
                keywords = re.sub(r'([^\w\s])\1+', r'\1', keywords)

                topic_clean = topic.split("：", 1)[-1].strip() if "：" in topic else topic
                results: list[dict] = []

                # Strategy 1: BROLL keywords
                results = await self.searcher.search(keywords, max_results=5)
                logger.info("[F:%s]   搜索段%d (BROLL): %s -> %d 结果", video_id, i, keywords[:40], len(results))

                # Strategy 2: topic entities supplement
                if len(results) < 3:
                    topic_terms = _extract_search_terms(topic_clean, keywords)
                    if topic_terms and topic_terms != keywords:
                        kw_results = await self.searcher.search(topic_terms, max_results=3)
                        seen_urls = {r.get("url") for r in results}
                        for r in kw_results:
                            if r.get("url") not in seen_urls:
                                results.append(r)
                        logger.info("[F:%s]   搜索段%d (主题词): %s -> +%d", video_id, i, topic_terms[:40], len(kw_results))

                # Strategy 3: broader AI search (Agent-specific terms, not generic)
                if not results:
                    results = await self.searcher.search("AI智能体 Agent 编程 开源", max_results=3)
                    logger.info("[F:%s]   搜索段%d (兜底): -> %d 结果", video_id, i, len(results))

                # Domain gate + relevance scoring
                scored = _score_clip_relevance(results, topic_clean + " " + keywords)
                results = [s[0] for s in scored if s[1] >= 3]
                if not results and scored:
                    results = [s[0] for s in scored[:2]]

                if not results:
                    broll_failures += 1
                    logger.warning("[F:%s]   段%d [%s]: 0个素材！", video_id, i, topic)

                segment_clips.append(results)
                await asyncio.sleep(3 if len(results) == 0 else 1.5)

            # Quality gate
            if news_segment_count > 0:
                failure_ratio = broll_failures / news_segment_count
                if failure_ratio >= 0.5 and retry < MAX_RETRIES - 1:
                    wait_sec = (retry + 1) * 10
                    logger.warning("[F:%s] B-roll quality FAILED: %d/%d (%.0f%%), waiting %ds...",
                                   video_id, broll_failures, news_segment_count, failure_ratio * 100, wait_sec)
                    await asyncio.sleep(wait_sec)
                    continue
                else:
                    logger.info("[F:%s] B-roll quality OK: %d/%d with clips (%d missing)",
                                video_id, news_segment_count - broll_failures, news_segment_count, broll_failures)
            break

        # ---- Step 3: download B-roll clips ----
        logger.info("[F:%s] Step 3: 下载B-roll素材...", video_id)
        downloaded: list[list[str]] = []

        for i, clips in enumerate(segment_clips):
            seg_downloads: list[str] = []
            seg = segments[i]
            topic = seg.get("topic", "")
            is_news = not ("开场" in topic or "概述" in topic or "结尾" in topic or "总结" in topic)

            for j, clip in enumerate(clips[:2]):
                # Pexels relevance gate: skip clip if title has zero overlap with topic
                if clip.get("platform") == "pexels" and is_news:
                    if not _pexels_clip_is_relevant(clip, topic):
                        logger.info("[F:%s]   跳过不相关Pexels: %s (topic: %s)",
                                    video_id, clip.get('title', '')[:40], topic[:30])
                        continue

                logger.info("[F:%s]   下载 段%d素材%d: %s", video_id, i, j, clip.get('title', '')[:50])
                try:
                    path = await self.searcher.download(clip["url"])
                    if path:
                        # Pre-transcode to 1080p to avoid UHD bottleneck during concat
                        transcoded = str(video_dir / f"pre_{i:02d}_{j:02d}.mp4")
                        if _pre_scale_clip(path, transcoded):
                            seg_downloads.append(transcoded)
                        else:
                            seg_downloads.append(path)  # fallback to original
                except Exception as e:
                    logger.warning("[F:%s]   下载失败: %s", video_id, e)
            downloaded.append(seg_downloads)

        total_clips = sum(len(d) for d in downloaded)
        if total_clips == 0:
            raise RuntimeError("所有素材下载失败！")
        logger.info("[F:%s] 成功下载 %d 个素材", video_id, total_clips)

        # ---- Step 3.5: emergency re-search for empty news segments ----
        for i, seg_downloads in enumerate(downloaded):
            seg = segments[i]
            topic = seg.get("topic", "")
            is_news = not ("开场" in topic or "概述" in topic or "结尾" in topic or "总结" in topic)
            if not is_news or seg_downloads:
                continue

            logger.warning("[F:%s]   段%d [%s]: 0素材！紧急补搜Pexels...", video_id, i, topic)
            # Extract pure Chinese keywords from topic for broader Pexels search
            rescue_kw = _extract_rescue_keywords(topic)
            for rescue_attempt, kw in enumerate(rescue_kw[:2]):
                logger.info("[F:%s]   补搜%d: '%s'", video_id, rescue_attempt + 1, kw)
                rescue_clips = await self.searcher.search(kw, max_results=3)
                # Filter relevant only
                rescue_clips = [c for c in rescue_clips if c.get("platform") != "pexels" or _pexels_clip_is_relevant(c, topic)]
                for j, clip in enumerate(rescue_clips[:2]):
                    logger.info("[F:%s]   紧急下载 段%d素材%d: %s", video_id, i, j, clip.get('title', '')[:40])
                    try:
                        path = await self.searcher.download(clip["url"])
                        if path:
                            transcoded = str(video_dir / f"rescue_{i:02d}_{j:02d}.mp4")
                            if _pre_scale_clip(path, transcoded):
                                seg_downloads.append(transcoded)
                            else:
                                seg_downloads.append(path)
                    except Exception as e:
                        logger.warning("[F:%s]   紧急下载失败: %s", video_id, e)
                if seg_downloads:
                    logger.info("[F:%s]   段%d 补搜成功: %d个素材", video_id, i, len(seg_downloads))
                    break
            if not seg_downloads:
                logger.warning("[F:%s]   段%d [%s]: 补搜也失败，将使用占位画面", video_id, i, topic)

        # ---- Step 4: TTS voiceover per segment ----
        logger.info("[F:%s] Step 4: Edge TTS 生成AI配音...", video_id)
        audio_segments: list[str] = []

        for i, seg in enumerate(segments):
            audio_path = str(video_dir / f"voice_seg_{i:02d}.mp3")
            clean_text = _clean_spoken_text(seg["text"])
            if i > 0:
                await asyncio.sleep(1.5)
            result = await self.tts.generate(clean_text, audio_path)
            if result:
                audio_segments.append(result)
            else:
                logger.warning("[F:%s]   TTS 段%d 失败", video_id, i)

        if not audio_segments:
            raise RuntimeError("TTS 全部失败！")
        logger.info("[F:%s] 配音完成: %d 段", video_id, len(audio_segments))

        # Get durations
        segment_durations: list[float] = []
        for ap in audio_segments:
            dur = self.editor.get_duration(ap)
            segment_durations.append(dur if dur else 10.0)

        total_duration = sum(segment_durations)
        logger.info("[F:%s] 总配音时长: %.0f秒", video_id, total_duration)

        # ---- Step 5: trim B-roll to match TTS ----
        logger.info("[F:%s] Step 5: 裁剪B-roll匹配配音...", video_id)
        trimmed_segments: list[list[str]] = []

        for i, (clip_paths, target_dur) in enumerate(zip(downloaded, segment_durations)):
            seg_trimmed: list[str] = []
            if not clip_paths:
                seg = segments[i]
                topic = seg.get("topic", "")
                is_opening = "开场" in topic or "概述" in topic
                is_closing = "结尾" in topic or "总结" in topic

                if is_opening:
                    title_path = str(video_dir / f"title_card_{i:02d}.mp4")
                    _generate_title_card(title_path, today, target_dur, background_video=intro_bg)
                    seg_trimmed.append(title_path)
                    logger.info("[F:%s]   段%d [%s]: 标题卡 (%.0fs)", video_id, i, topic, target_dur)
                elif is_closing and intro_bg and Path(intro_bg).exists():
                    close_path = str(video_dir / f"closing_{i:02d}.mp4")
                    _generate_title_card(close_path, today, target_dur,
                                         background_video=intro_bg,
                                         title_text="感谢收看",
                                         subtitle_text="AI早报 明日再见",
                                         font_size=64)
                    seg_trimmed.append(close_path)
                    logger.info("[F:%s]   段%d [%s]: 片尾卡 (%.0fs)", video_id, i, topic, target_dur)
                else:
                    placeholder = str(video_dir / f"placeholder_{i:02d}.mp4")
                    _generate_placeholder(placeholder, target_dur)
                    seg_trimmed.append(placeholder)
                    logger.warning("[F:%s]   段%d [%s]: 占位画面 (%.0fs)", video_id, i, topic, target_dur)
                trimmed_segments.append(seg_trimmed)
                continue

            per_clip_dur = target_dur / len(clip_paths)
            for j, cp in enumerate(clip_paths):
                clip_dur = self.editor.get_duration(cp)
                if clip_dur is None:
                    clip_dur = 30
                start = 0.0
                end = min(per_clip_dur, clip_dur)
                if end < 3:
                    end = min(per_clip_dur, clip_dur)
                trimmed_path = str(video_dir / f"broll_{i:02d}_{j:02d}.mp4")
                ok = self.editor.trim(cp, trimmed_path, start, end)
                if ok:
                    seg_trimmed.append(trimmed_path)
                else:
                    seg_trimmed.append(cp)
            trimmed_segments.append(seg_trimmed)

        # ---- Step 6: concat B-roll ----
        logger.info("[F:%s] Step 6: 拼接B-roll画面...", video_id)
        all_broll: list[str] = []
        for clips in trimmed_segments:
            all_broll.extend(clips)
        if not all_broll:
            raise RuntimeError("无可用B-roll素材！")

        raw_video = str(video_dir / "raw_broll.mp4")
        ok = self.editor.concat(all_broll, raw_video, audio=False)
        if not ok:
            raise RuntimeError("B-roll拼接失败")

        # ---- Step 7: concat TTS audio ----
        logger.info("[F:%s] Step 7: 合并配音音频...", video_id)
        full_audio = str(video_dir / "full_voiceover.mp3")

        if len(audio_segments) == 1:
            shutil.copy(audio_segments[0], full_audio)
        else:
            concat_list = str(video_dir / "audio_concat.txt")
            with open(concat_list, "w", encoding="utf-8") as f:
                for ap in audio_segments:
                    f.write(f"file '{ap.replace(chr(92), '/')}'\n")
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", full_audio]
            result = _sp.run(cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                logger.warning("[F:%s] 音频合并失败: %s", video_id, (result.stderr or '')[:300])
                shutil.copy(audio_segments[0], full_audio)

        # ---- Step 8: composite audio + video ----
        logger.info("[F:%s] Step 8: 合成配音+画面...", video_id)
        video_dur = self.editor.get_duration(raw_video) or 0
        audio_dur = self.editor.get_duration(full_audio) or 0
        logger.info("[F:%s]   视频:%.0fs, 音频:%.0fs", video_id, video_dur, audio_dur)

        current_video = raw_video
        if audio_dur > video_dur + 1.0:
            padded = str(video_dir / "padded_video.mp4")
            pad_cmd = [
                "ffmpeg", "-y", "-i", raw_video,
                "-vf", f"tpad=stop_mode=clone:stop_duration={audio_dur - video_dur:.1f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", padded,
            ]
            result = _sp.run(pad_cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
            if result.returncode == 0:
                current_video = padded
                logger.info("[F:%s]   视频已填充: +%.0fs", video_id, audio_dur - video_dur)

        with_audio = str(video_dir / "with_audio.mp4")
        ok = self.editor.add_audio(current_video, full_audio, with_audio)
        if not ok:
            logger.warning("[F:%s] 音频合成失败，使用原始画面", video_id)
            shutil.copy(current_video, with_audio)
        current_video = with_audio

        # ---- Step 9: script-based subtitles (zero typos) ----
        logger.info("[F:%s] Step 9: 脚本原文生成字幕...", video_id)
        final_path = str(video_dir / f"{vtype}_{vdate.isoformat()}.mp4")

        sub_path = _generate_script_subtitles(segments, segment_durations, video_dir)
        if sub_path and Path(sub_path).exists():
            ok = self.editor.burn_subtitles(current_video, sub_path, final_path)
            if ok:
                logger.info("[F:%s] 字幕嵌入完成: %s", video_id, final_path)
            else:
                shutil.copy(current_video, final_path)
                logger.warning("[F:%s] 字幕嵌入失败", video_id)
        else:
            shutil.copy(current_video, final_path)

        # ---- Save metadata (upsert: works for both HTTP and local runs) ----
        meta = json.dumps({
            "segments": len(segments),
            "clips_downloaded": total_clips,
            "duration_sec": round(total_duration),
            "model": "deepseek-chat",
            "tts": "edge-tts (zh-CN-XiaoyiNeural)",
            "subtitles": "script-based (zero-typo)",
            "intro_bg": "pexels" if intro_bg else "gradient",
        })
        await pool.execute(
            "INSERT INTO videos (id, type, date, status, script, title, metadata, duration_seconds, output_path) "
            "VALUES ($1, $2, $3, 'done', $4, $5, $6, $7, $8) "
            "ON CONFLICT (type, date) DO UPDATE SET "
            "id = $1, status = 'done', script = $4, title = $5, metadata = $6, "
            "duration_seconds = $7, output_path = $8, finished_at = now()",
            video_id, vtype, vdate,
            script_text,
            f"AI智能体早报 — {today}",
            meta,
            round(total_duration),
            final_path,
        )

        size_mb = Path(final_path).stat().st_size / (1024 * 1024) if Path(final_path).exists() else 0
        logger.info("[F:%s] === 完成 === 输出:%s 大小:%.1fMB 时长:%.0fs",
                    video_id, final_path, size_mb, total_duration)
        return final_path

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        return self._pool


# ═══════════════════════════════════════════════════════════════════════════
# Real news fetching (RSS from module-a scrapers)
# ═══════════════════════════════════════════════════════════════════════════

async def _fetch_real_news() -> list[dict]:
    """Fetch real AI/agent news from RSS sources (no DB required)."""
    try:
        from scrapers.rss import fetch_single_rss, RSS_SOURCES, to_raw_items
    except ImportError:
        logger.warning("无法导入 module-a RSS 模块")
        return []

    ai_sources = [s for s in RSS_SOURCES if s.get("category") == "科技"]
    batch_id = _uuid.uuid4()
    since = datetime.now(timezone.utc) - timedelta(hours=36)

    tasks = [fetch_single_rss(src) for src in ai_sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_entries = []
    for i, result in enumerate(results):
        source_name = ai_sources[i]["name"]
        if isinstance(result, Exception):
            logger.warning("RSS [%s] 失败: %s", source_name, result)
            continue
        for entry in result:
            entry["_source_name"] = source_name
            entry["_category"] = "科技"
        all_entries.extend(result)

    filtered = [e for e in all_entries if _rss_entry_time(e) >= since]
    raw_items = to_raw_items(filtered, "rss", batch_id)
    logger.info("RSS抓取: %d 条科技新闻", len(raw_items))

    arxiv_items = await _fetch_arxiv_news(batch_id)
    logger.info("arXiv抓取: %d 篇AI论文", len(arxiv_items))
    raw_items.extend(arxiv_items)

    ai_items = _filter_ai_news(raw_items)
    logger.info("AI筛选后: %d 条Agent相关新闻", len(ai_items))
    return ai_items[:15]


async def _fetch_arxiv_news(batch_id) -> list[dict]:
    """Fetch recent AI papers from arXiv API."""
    import xml.etree.ElementTree as ET

    url = (
        "https://export.arxiv.org/api/query"
        "?search_query=cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.LG"
        "&sortBy=submittedDate&sortOrder=descending&max_results=20"
    )

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("arXiv API returned %d", resp.status_code)
                return []
            xml_data = resp.text

        root = ET.fromstring(xml_data)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        since = datetime.now(timezone.utc) - timedelta(hours=72)
        items = []

        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            link_el = entry.find("atom:link", ns)
            published_el = entry.find("atom:published", ns)

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""
            link = link_el.get("href", "") if link_el is not None else ""
            published_str = published_el.text.strip() if published_el is not None and published_el.text else ""

            try:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                published = datetime.now(timezone.utc)

            if published < since:
                continue

            summary = re.sub(r"<[^>]+>", "", summary)
            summary = re.sub(r"\s+", " ", summary).strip()

            if not title:
                continue

            items.append({
                "source": "arxiv", "title": f"[论文] {title}",
                "url": link or f"https://arxiv.org/search/?query={title[:50]}",
                "content": summary[:300], "author": "",
                "published_at": published, "batch_id": batch_id,
                "metadata": {"category": "科技"},
            })

        return items
    except Exception:
        logger.warning("arXiv fetch failed", exc_info=True)
        return []


def _rss_entry_time(entry: dict) -> datetime:
    from calendar import timegm
    parsed = entry.get("published_parsed")
    if parsed and len(parsed) >= 6:
        try:
            ts = timegm(parsed[:6] + (0, 0, 0))
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass
    return datetime.now(timezone.utc)


def _filter_ai_news(items: list[dict]) -> list[dict]:
    """Filter news by the 14-tag system used by module-b scoring.

    Tags: LLM, Agent, 开源, 工具, 科技, 行业, 全球, 体育, 安全, 芯片, 机器人, 自动驾驶, 融资, 医疗

    Agent-related content gets priority scoring, but all 14 tag categories
    are eligible so that the video tags match the actual news tags.
    """
    # Core Agent keywords (highest priority — matches "Agent" tag)
    agent_core = [
        "agent", "智能体", "agentic", "自主", "multi-agent", "多智能体", "多agent",
        "桌面智能", "desktop agent", "电脑操控", "电脑操作", "computer use",
        "gui自动化", "gui automation", "浏览器智能体", "browser agent",
        "编程智能体", "coding agent", "代码agent", "办公智能体", "办公agent",
        "工具调用", "function call", "tool use", "任务规划", "task planning",
        "自主执行", "工作流自动化", "workflow automation", "mcp", "model context protocol",
        "a2a", "agent-to-agent",
    ]

    agent_products = [
        "openhuman", "openclaw", "dumate", "genflow", "crewai", "autogpt",
        "babyagi", "agentgpt", "copilot", "cursor", "windsurf", "devin",
        "manus", "aionui", "echobot", "superpowers", "claude code",
        "gemini agent", "copilot studio", "langgraph", "langflow", "dify",
        "coze", "扣子", "百炼", "元器",
    ]

    # 14-tag keyword mapping — aligns with module-b/ai/analyzer.py _KEYWORD_TAG_MAP
    tag_keywords = {
        "LLM":    ["llm", "大模型", "gpt", "claude", "gemini", "文心", "星火", "通义", "deepseek", "深度求索"],
        "Agent":  [],  # covered by agent_core + agent_products above
        "开源":    ["开源", "open source", "github", "gitlab", "apache", "mit license"],
        "工具":    ["工具", "tool", "插件", "plugin", "sdk", "api", "框架", "framework"],
        "科技":    ["科技", "tech", "发布", "推出", "新产品", "功能更新", "版本发布"],
        "行业":    ["行业", "企业", "合作", "市场", "产业", "政策", "监管", "法规"],
        "全球":    ["国际", "全球", "外交", "贸易", "制裁", "关税", "地缘"],
        "体育":    ["体育", "sport", "nba", "足球", "篮球", "比赛", "赛事", "冠军", "联赛"],
        "安全":    ["安全", "security", "漏洞", "攻击", "黑客", "隐私", "数据泄露", "后门"],
        "芯片":    ["芯片", "chip", "nvidia", "intel", "amd", "半导体", "gpu", "算力", "处理器"],
        "机器人":  ["机器人", "robot", "具身智能", "人形机器人", "机械臂", "自动化"],
        "自动驾驶": ["自动驾驶", "self driving", "autonomous vehicle", "fsd", "激光雷达", "毫米波"],
        "融资":    ["融资", "ipo", "上市", "投资", "估值", "a轮", "b轮", "天使轮", "收购", "并购"],
        "医疗":    ["医疗", "医学", "health", "药物", "临床", "诊断", "基因", "蛋白质", "疫苗"],
    }

    agent_context = [
        "编程助手", "代码助手", "ai编程",
        "自动化", "automation", "自主操作",
    ]

    # Hard exclude: content that should never appear in a tech news video
    hard_exclude = [
        "广告", "推广", "课程", "培训", "退费", "报名",
    ]

    scored = []
    for item in items:
        title = item.get("title", "")
        content = item.get("content", "")
        text = f"{title} {content}".lower()

        # Hard exclude ads
        if any(kw in text for kw in hard_exclude):
            continue

        product_score = sum(5 for kw in agent_products if kw in text)
        core_score = sum(3 for kw in agent_core if kw in text)
        ctx_score = sum(1 for kw in agent_context if kw in text)

        # Score by 14-tag keyword match (1pt per tag hit)
        tag_score = 0
        matched_tags = []
        for tag, keywords in tag_keywords.items():
            if any(kw in text for kw in keywords):
                tag_score += 2
                matched_tags.append(tag)

        # If no Agent signal AND no tag match at all, skip
        if product_score == 0 and core_score == 0 and tag_score == 0:
            continue

        total = product_score + core_score + ctx_score + tag_score

        # Lower threshold for tag-matched news (was >= 5, now >= 3 for tag-matched)
        if total >= 3:
            # Attach matched tags so the script prompt can use them
            item["_matched_tags"] = matched_tags
            scored.append((total, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ═══════════════════════════════════════════════════════════════════════════
# News script generation (DeepSeek + real RSS news)
# ═══════════════════════════════════════════════════════════════════════════

async def _generate_news_script(today: str, news_items: list[dict] | None = None) -> tuple[str, list[dict]]:
    """Generate structured AI agent morning briefing script."""
    import openai

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

    if not api_key:
        logger.error("DEEPSEEK_API_KEY 未配置")
        return _fallback_script(today)

    news_context = ""
    if news_items:
        lines = []
        for i, item in enumerate(news_items[:12]):
            title = item.get("title", "")
            content = item.get("content", "")[:200]
            source = item.get("source", "")
            lines.append(f"[{i+1}] {title}（来源：{source}）\n    {content}")
        news_context = "\n\n".join(lines)

    if news_context:
        prompt = f"""你是AI/科技领域的专业新闻主播。下方是最近24小时的科技新闻素材。

⚠️ 分类标签体系（与新闻评分系统一致，BROLL必须使用这些标签）：
  LLM（大模型相关）、Agent（智能体）、开源、工具、科技、行业、
  全球、体育、安全、芯片、机器人、自动驾驶、融资、医疗

✅ 优先报道的领域（对应标签）：
  1. Agent / 智能体: 桌面智能体、编程智能体、办公智能体、多智能体协作、MCP协议等
  2. LLM / 大模型: 新模型发布、API更新、推理优化、开源模型
  3. 开源 / 工具: GitHub热门项目、开发框架、AI编程工具、新SDK
  4. 科技: 重大产品发布、技术突破、AI应用落地
  5. 芯片 / 机器人 / 自动驾驶 / 融资: 重要进展也可报道

❌ 绝对禁止：
  - 广告/营销/课程推广/培训
  - 游戏/娱乐/综艺/美食/旅游等非科技内容
  - 股票理财/荐股/资金盘等金融诈骗

⚠️ 选择标准：
  - 优先选择 Agent + LLM 相关的新闻（至少2条）
  - 其他标签的新闻选最有价值的1-2条
  - 如果新闻不够4条 → 有几条报几条，不编造

⚠️ 核心铁律：
1. 必须基于上方提供的真实新闻，绝对不要编造
2. 这是新闻播报，不是科普教程
3. 严禁任何Markdown格式，纯文本口播稿
4. 中文TTS无法朗读英文 → 所有英文必须用中文表达
5. 严禁出现任何URL网址

⚠️ 结构铁律：
【开场概述】→ N条新闻 → 【结尾总结】，N=3~5

⚠️ BROLL铁律（搜索关键词，2-5个中文词）：
- BROLL必须是新闻核心实体 + 对应标签名
- 例如: Agent新闻 → "OpenHuman 智能体 Agent"
- 例如: LLM新闻 → "深度求索 大模型 LLM"
- 例如: 开源新闻 → "GitHub开源 编程工具"
- 严禁占位符如"搜索关键词"、"此处填写"

格式示例：
【开场概述】
各位观众早上好，欢迎收看今天的AI科技早报。今天我们将聚焦...
BROLL: AI科技 智能体 Agent

【新闻一：<具体标题，包含标签提示>】
...（新闻内容）...
BROLL: <核心实体> <对应标签>

今日科技新闻素材：
{news_context}

⚠️ 输出前请自检：
1. 每条新闻是否标注了正确的分类标签？
2. BROLL关键词是否包含标签名？总字数600-1000字。"""
    else:
        prompt = f"""你是AI/科技领域的专业新闻主播。今天（{today}）没有实时新闻素材，请基于你的知识撰写AI科技领域的早报解说词。

⚠️ 分类标签体系（BROLL必须使用这些标签）：
  LLM（大模型）、Agent（智能体）、开源、工具、科技

✅ 报道领域（3-4条）：
  - Agent / 智能体: 桌面智能体、编程智能体、办公智能体、多智能体协作
  - LLM / 大模型: 新模型、推理优化、开源模型
  - 开源 / 工具: AI编程工具、开发框架、GitHub热门项目
  - 科技: 重大产品发布、技术突破

❌ 禁止报道：广告营销、游戏娱乐、理财股票、非科技内容

这是新闻播报，不是科普教程。语言专业简洁有新闻感，适合口播。
严禁Markdown格式，纯文本口播稿。所有英文必须用中文表达。

格式（【】括号标记，3-4条新闻）：
【开场概述】
...
BROLL: AI科技 智能体 Agent

【新闻一：<标题，含标签提示>】
...
BROLL: <核心实体> <对应标签>

【结尾总结】
...
BROLL: AI科技

BROLL铁律：2-5个中文词，必须包含对应标签名。总字数600-1000字。"""

    try:
        client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=2500,
        )
        raw = response.choices[0].message.content or ""
        logger.info("DeepSeek 生成脚本: %d 字", len(raw))
        return _parse_script(raw, today)
    except Exception as e:
        logger.warning("DeepSeek 失败: %s，使用模板", e)
        return _fallback_script(today)


def _parse_script(raw: str, today: str) -> tuple[str, list[dict]]:
    """Parse DeepSeek output into segments with B-roll keywords."""
    raw = re.sub(r'\*\*(.+?)\*\*', r'\1', raw)
    raw = raw.replace('**', '')
    raw = re.sub(r'^[-*_]{3,}\s*$', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'^#{1,6}\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'(第[一二三四五六七八九\d]+条新闻[：:].+?\n)\s*\1+', r'\1', raw)
    raw = re.sub(r'\n{3,}', '\n\n', raw)

    segments: list[dict] = []
    clean_lines: list[str] = []
    broll_new = re.compile(r'^BROLL[：:]\s*(.+?)(?:\n|$)', re.MULTILINE)
    broll_old = re.compile(r'<!--BROLL:\s*(.+?)-->')

    def _extract_broll(text: str) -> tuple[str | None, str]:
        m = broll_new.search(text)
        if m:
            kw = m.group(1).strip()
            if kw in ("搜索关键词", "此处填写", "替换为", "在此填写", "实际搜索词", "搜索词"):
                return "AI 科技新闻", broll_new.sub("", text)
            return kw, broll_new.sub("", text)
        m = broll_old.search(text)
        if m:
            kw = m.group(1).strip()
            if kw in ("搜索关键词", "此处填写", "替换为", "在此填写", "实际搜索词", "搜索词"):
                return "AI 科技新闻", broll_old.sub("", text)
            return kw, broll_old.sub("", text)
        return None, text

    # Try 【】 bracket format
    if '【' in raw and '】' in raw:
        section_pattern = re.compile(r'【(.+?)】\s*\n?')
        parts = section_pattern.split(raw)

        if len(parts) >= 2:
            for i in range(1, len(parts), 2):
                section_name = parts[i].strip()
                content = parts[i + 1] if i + 1 < len(parts) else ""
                broll_keywords, content = _extract_broll(content)
                if broll_keywords is None:
                    broll_keywords = "AI 科技新闻"
                content = content.strip()
                if not content:
                    continue

                header = f"【{section_name}】"
                clean_lines.append(header)
                clean_lines.append(content)
                clean_lines.append("")

                is_opening = "开场" in section_name or "概述" in section_name
                is_closing = "结尾" in section_name or "总结" in section_name
                topic = section_name
                if is_opening:
                    topic = "开场概述"
                elif is_closing:
                    topic = "结尾总结"

                segments.append({
                    "topic": topic, "text": content, "broll_keywords": broll_keywords,
                })

            if segments:
                return "\n".join(clean_lines), segments

    # Fallback: parse by 第N条新闻 markers
    news_pattern = re.compile(
        r'(第[一二三四五六七八九\d]+条新闻[：:].*?)(?=第[一二三四五六七八九\d]+条新闻[：:]|总结今天|$)',
        re.DOTALL,
    )
    news_matches = list(news_pattern.finditer(raw))

    if news_matches:
        first_pos = news_matches[0].start()
        opening_text = raw[:first_pos].strip()
        if opening_text and len(opening_text) > 20:
            opening_broll, opening_text = _extract_broll(opening_text)
            if opening_broll is None:
                opening_broll = "AI 科技新闻"
            clean_lines.append(opening_text)
            segments.append({"topic": "开场概述", "text": opening_text.strip(), "broll_keywords": opening_broll})

        for m in news_matches:
            block = m.group(1).strip()
            first_line_end = block.find('\n')
            first_line = block[:first_line_end].strip() if first_line_end > 0 else block[:80].strip()
            raw_title = re.sub(r'\*\*', '', first_line)
            raw_title = re.sub(r'^第[一二三四五六七八九\d]+条新闻[：:]\s*', '', raw_title)
            body = block[first_line_end:].strip() if first_line_end > 0 else ""
            broll_keywords, body = _extract_broll(body)
            if broll_keywords is None:
                broll_keywords = "AI 科技新闻"
            spoken = first_line + "\n" + body if body else first_line
            clean_lines.append(raw_title)
            clean_lines.append(spoken.strip())
            clean_lines.append("")
            segments.append({"topic": raw_title, "text": spoken.strip(), "broll_keywords": broll_keywords})

        last_pos = news_matches[-1].end()
        closing_text = raw[last_pos:].strip()
        if closing_text and len(closing_text) > 20:
            closing_broll, closing_text = _extract_broll(closing_text)
            if closing_broll is None:
                closing_broll = "AI 科技新闻"
            clean_lines.append("结尾总结")
            clean_lines.append(closing_text.strip())
            segments.append({"topic": "结尾总结", "text": closing_text.strip(), "broll_keywords": closing_broll})

        if segments:
            return "\n".join(clean_lines), segments

    # Ultimate fallback
    text = raw.strip()
    single_broll, text = _extract_broll(text)
    if single_broll is None:
        single_broll = "AI 人工智能 科技新闻"
    segments.append({"topic": "AI智能体早报", "text": text.strip(), "broll_keywords": single_broll})
    return "\n".join(clean_lines) if clean_lines else text, segments


def _fallback_script(today: str) -> tuple[str, list[dict]]:
    """Fallback Agent-only news script when DeepSeek is unavailable."""
    script = f"""【开场概述】
各位观众早上好，欢迎收看{today}AI智能体领域早报。今天我们将聚焦桌面智能体、编程智能体和办公智能体的最新进展。
BROLL: AI智能体 Agent

【新闻一：开源桌面智能体OpenHuman引爆GitHub】
开源桌面AI智能体OpenHuman在GitHub上连续霸榜，6天内从三千余星飙升至近两万星。这款运行在用户桌面上的智能体能直接辅助完成日常电脑操作，其爆发式增长反映了开发者对本地化、可操控AI助手的强烈需求。
BROLL: OpenHuman 桌面智能体 GitHub

【新闻二：百度智能云办公智能体DuMate实测表现亮眼】
百度针对企业场景设计的桌面级AI智能体DuMate全量上线后，科技媒体对其实际办公能力进行了深度测评。结果显示DuMate在真实办公场景中表现出色，能有效完成多形态输出任务，被评价为真正能"抗活儿"的AI办公搭档。
BROLL: 百度 DuMate 办公智能体

【新闻三：本地AI智能体框架OpenClaw补齐操控能力】
本地AI智能体框架OpenClaw正式上线桌面操控工具Peekaboo，提供像素级截图、界面元素识别和完整GUI自动化能力。这标志着本地智能体在自主操控电脑方面迈出了关键一步。
BROLL: OpenClaw 桌面操控 GUI自动化

【新闻四：开源多智能体框架CrewAI获千万美元融资】
开源多智能体协作框架CrewAI完成A轮融资，估值突破两亿美元。该框架支持多个AI智能体角色扮演和任务分工，已被上千家企业用于自动化工作流搭建。
BROLL: CrewAI 多智能体 开源框架

【结尾总结】
以上就是今天的AI智能体领域早报。从桌面智能体的爆发到办公智能体的落地验证，AI智能体正在从概念走向真正的日常工具。感谢您的收看。
BROLL: AI智能体 Agent"""
    text, segments = _parse_script(script, today)
    logger.info("使用Agent模板脚本: %d 字, %d 段", len(script), len(segments))
    return text, segments


# ═══════════════════════════════════════════════════════════════════════════
# B-roll relevance scoring (domain gate + keyword overlap)
# ═══════════════════════════════════════════════════════════════════════════

# Irrelevant domains — these clips should NEVER be used as AI news B-roll
DOMAIN_IRRELEVANT = {
    "音乐", "歌曲", "MV", "翻唱", "演唱会", "歌手", "乐队", "专辑",
    "QQ音乐", "酷狗", "网易云", "唱吧", "全民K歌", "抖音神曲",
    "游戏", "电竞", "王者荣耀", "英雄联盟", "原神", "崩坏", "星穹铁道",
    "吃鸡", "绝地求生", "赛博朋克", "我的世界", "LOL", "PUBG", "DNF",
    "蛋仔派对", "第五人格", "阴阳师", "永劫无间", "光遇",
    "Steam", "switch", "PS5", "Xbox",
    "综艺", "搞笑", "鬼畜", "恶搞", "整蛊", "脱口秀", "相声", "小品",
    "真人秀", "选秀", "练习生", "女团", "男团", "偶像",
    "美食", "探店", "旅游", "美妆", "穿搭", "减肥", "健身", "瑜伽",
    "星座", "塔罗", "占卜", "宠物", "萌宠", "钓鱼", "手工", "绘画",
    "书法", "舞蹈", "翻跳", "广场舞",
    "相亲", "恋爱", "婚姻", "育儿", "母婴",
    "中小学", "高考", "考研", "考公", "英语学习", "日语学习",
    "股票", "基金", "期货", "彩票", "荐股", "涨停", "跌停",
    "直播带货", "秒杀", "优惠券", "拼多多", "抽奖", "开箱",
    "电影", "电视剧", "网剧", "动漫", "番剧", "追番", "剧情",
    # === 广告/营销/商业推广（新增）===
    "课程", "培训", "退费", "退款", "报名", "网课", "培训班", "训练营",
    "赚钱", "副业", "月入", "暴富", "躺赚", "薅羊毛", "返利",
    "理财", "炒股", "私募", "炒币", "资金盘", "传销", "加盟", "代理",
    "广告", "推广", "营销", "引流", "涨粉", "带货",
    "限时优惠", "最后一天", "名额有限", "早鸟价", "扫码入群",
    "加微信", "私信", "试听课", "体验课",
    "算命", "风水", "星座运势", "塔罗牌",
}

DOMAIN_TECH = {
    "编程", "代码", "开发", "开源", "AI", "人工智能", "机器学习",
    "深度学习", "大模型", "LLM", "Agent", "智能体", "模型训练",
    "推理", "部署", "API", "SDK", "框架", "工具链", "算力",
    "芯片", "GPU", "服务器", "数据中心", "云计算", "云原生",
    "Python", "JavaScript", "Rust", "Go", "Java", "C++",
    "GitHub", "GitLab", "Docker", "Kubernetes", "Linux",
    "机器人", "自动驾驶", "具身智能", "计算机视觉", "NLP",
    "科技", "技术", "软件", "硬件", "系统", "架构", "平台",
    "数据", "算法", "模型", "神经网络", "transformer",
    "HuggingFace", "OpenAI", "DeepSeek", "Anthropic", "Claude",
    "Copilot", "Cursor", "终端", "命令行", "vim", "neovim",
}

_AMBIGUOUS_TOKENS = {
    "桌面", "布局", "系统", "设置", "界面", "窗口", "菜单",
    "文件", "文件夹", "图标", "主题", "壁纸", "背景", "屏幕",
    "鼠标", "键盘", "显示", "播放", "下载", "安装", "启动",
    "运行", "配置", "管理", "控制", "操作", "功能", "模式",
    "版本", "更新", "升级", "优化", "修复", "支持", "兼容",
    "设计", "风格", "方案", "解决", "实现", "处理", "分析",
    "搜索", "浏览", "查看", "编辑", "创建", "删除", "选择",
    "打开", "关闭", "保存", "导入", "导出", "分享", "同步",
    "助手", "工具", "应用", "程序", "服务", "平台", "项目",
}

_STOPWORDS = {
    "人工智能", "科技", "技术", "公司", "发布", "最新", "一个", "这种",
    "可以", "使用", "进行", "这个", "我们", "他们", "什么", "已经",
    "今天", "现在", "目前", "主要", "包括", "以及", "其中", "通过",
    "相关", "方面", "领域", "正在", "同时", "但是", "因此", "所以",
    "如果", "虽然", "不过", "而且", "并且",
}


def _score_clip_relevance(clips: list[dict], topic_text: str) -> list[tuple[dict, int]]:
    """Score B站 clips by domain relevance + keyword overlap with news topic."""
    mid = min(40, len(topic_text) // 2)
    head_text = topic_text[:mid]
    tail_text = topic_text[mid:]

    def _tokens(text: str, min_len: int = 2) -> set[str]:
        return {
            m.group() for m in re.finditer(r'[一-鿿]{' + str(min_len) + r',}', text)
            if m.group() not in _STOPWORDS
        }

    head_tokens = _tokens(head_text, min_len=2)
    tail_tokens = _tokens(tail_text, min_len=2)

    eng_entities = {
        m.group().lower()
        for m in re.finditer(r'[A-Za-z][A-Za-z0-9.+]{2,}', head_text)
    }

    def _classify_domain(title: str, desc: str) -> tuple[str, int, list]:
        content = title + " " + desc
        content_lower = content.lower()
        irr_hits = [kw for kw in DOMAIN_IRRELEVANT if kw.lower() in content_lower]
        tech_hits = [kw for kw in DOMAIN_TECH if kw.lower() in content_lower]

        if irr_hits and not tech_hits:
            return ("irrelevant", -100, irr_hits)
        if irr_hits and tech_hits:
            title_lower = title.lower()
            title_irr = [kw for kw in irr_hits if kw.lower() in title_lower]
            if title_irr:
                return ("irrelevant", -100, title_irr)
            return ("neutral", 0, [])
        if tech_hits:
            return ("tech", 0, [])
        return ("neutral", 0, [])

    def _score_overlap(clip_title: str, clip_desc: str) -> int:
        content = clip_title + " " + clip_desc
        score = 0

        for ent in eng_entities:
            if ent in content.lower():
                score += 20

        specific_head = head_tokens - _AMBIGUOUS_TOKENS
        ambiguous_head = head_tokens & _AMBIGUOUS_TOKENS
        specific_tail = tail_tokens - _AMBIGUOUS_TOKENS

        for t in specific_head:
            if t in content:
                score += 15
        for t in specific_tail:
            if t in content:
                score += 8
        if score > 0:
            for t in ambiguous_head:
                if t in content:
                    score += 3

        _AI_CONTEXT = {
            "AI", "人工智能", "大模型", "智能体", "深度学习", "机器学习",
            "神经网络", "自然语言", "计算机视觉", "机器人", "自动驾驶",
            "编程", "代码", "开源", "Agent", "Copilot", "LLM",
            "推理", "训练", "模型", "算法",
        }
        ai_hits = sum(1 for t in _AI_CONTEXT if t in content)
        if ai_hits > 0:
            score += ai_hits * 5

        return score

    scored: list[tuple[dict, int]] = []
    for clip in clips:
        title = clip.get("title", "") or ""
        desc = clip.get("description", "") or ""
        content = title + " " + desc
        view_count = clip.get("view_count", 0) or 0

        domain, penalty, irr_hits = _classify_domain(title, desc)
        if domain == "irrelevant":
            scored.append((clip, -100))
            continue

        score = _score_overlap(title, desc)

        if re.search(r'教程|从零开始|全套|合集|入门到精通|零基础|速成', content):
            score -= 5
        hashtag_count = content.count('#')
        if hashtag_count > 10:
            score -= 5

        # === Ad / commercial penalty (新增) ===
        _AD_PATTERNS = [
            r'课程|培训|退费|退款|报名|试听|网课|培训班|训练营',
            r'赚钱|副业|月入\d|暴富|躺赚|薅羊毛|返利|优惠券',
            r'理财|炒股|荐股|私募|炒币|资金盘|加盟|代理',
            r'限时|最后.*天|名额有限|早鸟价|扫码|加微信|私信',
            r'广告|推广|营销|引流|涨粉|带货',
            r'算命|风水|星座运势|塔罗',
        ]
        for pat in _AD_PATTERNS:
            if re.search(pat, content):
                score -= 30  # Heavy penalty for ad-like content

        if view_count > 100000:
            score += 5
        elif view_count > 10000:
            score += 3
        elif view_count > 1000:
            score += 1

        scored.append((clip, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _extract_search_terms(topic: str, fallback: str) -> str:
    """Extract short, searchable Chinese keywords from a news topic."""
    priority_terms = [
        "特斯拉", "小米", "微软", "谷歌", "OpenAI", "Anthropic", "Claude",
        "GitHub", "Copilot", "FSD", "全自动驾驶", "自动驾驶", "大模型",
        "AI助手", "AI编程", "DeepSeek", "软银", "三星", "英伟达",
    ]
    found = []
    remaining = topic
    for term in priority_terms:
        if term in remaining:
            found.append(term)
            remaining = remaining.replace(term, " ", 1)
    if found:
        return " ".join(found[:3])

    short = topic[:20]
    for sep in ["，", "、", "：", "。", "；", " ", "的", "在"]:
        idx = short.rfind(sep)
        if idx >= 4:
            short = short[:idx]
            break
    return short.strip() or fallback


# ═══════════════════════════════════════════════════════════════════════════
# Pexels relevance check — filter out unrelated stock footage
# ═══════════════════════════════════════════════════════════════════════════

# Words in Pexels titles that indicate generic/irrelevant stock footage
_PEXELS_NOISE = {
    "call center", "smartphone", "chocolates", "marshmallow", "cityscape",
    "twilight", "sunset", "sunrise", "travel", "vacation", "food", "cooking",
    "fashion", "makeup", "shopping", "sport", "fitness", "yoga", "party",
    "wedding", "concert", "festival", "nature", "landscape", "beach",
    "mountain", "forest", "ocean", "flower", "animal", "wildlife",
    "people walking", "crowd", "traffic",
    # === 扩展: 更多不相关的素材 ===
    "kids", "children", "baby", "family", "elderly", "senior",
    "car", "vehicle", "driving", "highway", "parking",
    "house", "real estate", "interior design", "furniture",
    "medical", "hospital", "doctor", "patient", "pharmacy",
    "school", "classroom", "university", "graduation",
    "factory", "warehouse", "construction", "industrial",
    "agriculture", "farm", "harvest", "crop",
    "religion", "church", "temple", "prayer", "worship",
    "gambling", "casino", "lottery", "poker", "betting",
}


def _pexels_clip_is_relevant(clip: dict, topic: str) -> bool:
    """Check if a Pexels clip is relevant to the news topic.

    Returns False for clearly irrelevant stock footage (cityscapes, food, etc.)
    and clips whose title has zero overlap with the topic's core terms.
    """
    title = (clip.get("title", "") or "").lower()
    desc = (clip.get("description", "") or "").lower()
    combined = title + " " + desc

    # Hard exclude: generic stock footage noise words
    for noise in _PEXELS_NOISE:
        if noise in combined:
            return False

    # Soft check: at least one meaningful Chinese keyword from topic in clip text
    # Extract 2+ char Chinese words from topic
    topic_cn = set(re.findall(r'[一-鿿]{2,}', topic))
    # Remove stopwords for relevance check
    topic_terms = topic_cn - _STOPWORDS
    if not topic_terms:
        return True  # can't judge, let it through

    # Also check English entities from topic
    topic_en = set(re.findall(r'[A-Za-z]{2,}', topic))

    # Check if any topic term appears in clip title/description
    for term in topic_terms:
        if term in combined:
            return True
    for term in topic_en:
        if term.lower() in combined:
            return True

    # No overlap at all → irrelevant
    return False


def _extract_rescue_keywords(topic: str) -> list[str]:
    """Extract progressively broader keywords for emergency search.

    Returns up to 3 keyword strings, from specific to broad.
    Strips the '新闻N：' prefix first.
    """
    # Strip section prefix like "新闻一：", "新闻二："
    clean_topic = re.sub(r'^新闻[一二三四五六七八九\d]+[：:]\s*', '', topic)

    # Strategy 1: Core Chinese entities (2+ chars), sorted by length (longer = more specific)
    cn_words = re.findall(r'[一-鿿]{2,}', clean_topic)
    cn_words = [w for w in cn_words if w not in _STOPWORDS and len(w) >= 2]
    # Also extract English entities
    en_words = re.findall(r'[A-Za-z]{2,}', clean_topic)
    # Longer words first (more specific)
    cn_words.sort(key=len, reverse=True)
    kw_specific = cn_words[:3] if cn_words else ["AI智能体"]

    # Strategy 2: Add Agent context prefix with extracted keywords
    if en_words:
        kw_agent = f"AI智能体 {' '.join(kw_specific[:2])} {' '.join(en_words[:2])}"
    else:
        kw_agent = f"AI智能体 {' '.join(kw_specific[:2])}"

    # Strategy 3: Broad Agent-focused fallback (more specific than generic AI)
    kw_broad = "AI Agent 智能体 编程开发 开源软件"

    return [kw_agent, kw_broad, "AI technology agent"]


# ═══════════════════════════════════════════════════════════════════════════
# Pre-scale clips to 1080p (avoids UHD bottleneck in concat)
# ═══════════════════════════════════════════════════════════════════════════

def _pre_scale_clip(input_path: str, output_path: str) -> bool:
    """Transcode a clip to 1080p H.264 with ultrafast preset.

    Returns True if the transcoded file was created successfully.
    This dramatically speeds up the later concat step which would
    otherwise need to decode + scale UHD sources.
    """
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                   "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-an",  # strip audio (B-roll)
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        result = _sp.run(cmd, capture_output=True, text=True, timeout=120,
                         encoding="utf-8", errors="replace")
        if result.returncode == 0 and Path(output_path).exists():
            return True
        logger.warning("Pre-scale failed for %s: %s", input_path, (result.stderr or "")[:200])
        return False
    except Exception:
        logger.warning("Pre-scale exception for %s", input_path, exc_info=True)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Intro background + title card + helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _fetch_intro_background(video_dir: Path) -> str | None:
    """Fetch a free tech/AI stock video from Pexels for the intro title card."""
    api_key = os.getenv("PEXELS_API_KEY", "")
    if not api_key:
        logger.info("Intro bg: no PEXELS_API_KEY — will use gradient fallback")
        return None

    try:
        search_url = "https://api.pexels.com/videos/search"
        params = {
            "query": "artificial intelligence technology digital data",
            "per_page": 5,
            "orientation": "landscape",
            "size": "medium",
        }
        headers = {"Authorization": api_key}

        async with httpx.AsyncClient(timeout=30, proxy=None) as client:
            resp = await client.get(search_url, params=params, headers=headers)
            if resp.status_code != 200:
                logger.info("Intro bg: Pexels API returned %d", resp.status_code)
                return None

            data = resp.json()
            videos = data.get("videos", [])
            if not videos:
                return None

            best = videos[0]
            files = sorted(best.get("video_files", []), key=lambda f: f.get("width", 0), reverse=True)
            best_file = None
            for f in files:
                if f.get("width", 0) <= 1920:
                    best_file = f
                    break
            if not best_file and files:
                best_file = files[0]
            if not best_file:
                return None

            download_url = best_file.get("link", "")
            if not download_url:
                return None

            resp2 = await client.get(download_url)
            if resp2.status_code != 200:
                return None

            ext = Path(download_url).suffix or ".mp4"
            bg_path = video_dir / f"intro_bg_{_uuid.uuid4().hex[:8]}{ext}"
            bg_path.write_bytes(resp2.content)

            logger.info("Intro bg: downloaded Pexels → %s (%.1f MB)", bg_path.name, len(resp2.content) / 1e6)
            return str(bg_path)

    except Exception as exc:
        logger.info("Intro bg: Pexels failed (%s) — using gradient", exc)
        return None


def _generate_title_card(output_path: str, today: str, duration_sec: float,
                         background_video: str | None = None, title_text: str = "AI 智能体领域早报",
                         subtitle_text: str | None = None, font_size: int = 72) -> None:
    """Title/closing card: Pillow text overlay on Pexels/gradient background."""
    dur = max(duration_sec, 3.0)

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning("Pillow not available — falling back to solid card")
        _generate_solid_card(output_path, dur)
        return

    font_paths = [
        "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
    ]
    font_title = None
    font_date = None
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font_title = ImageFont.truetype(fp, font_size)
                font_date = ImageFont.truetype(fp, 28)
                break
            except Exception:
                continue
    if font_title is None:
        font_title = ImageFont.load_default()
        font_date = ImageFont.load_default()

    overlay = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    accent_color = (58, 123, 213, 150)
    draw.rectangle([0, 0, 1920, 5], fill=accent_color)
    draw.rectangle([0, 1075, 1920, 1080], fill=accent_color)

    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (1920 - tw) // 2
    ty = (1080 - th) // 2 - 60
    draw.text((tx + 3, ty + 3), title_text, font=font_title, fill=(0, 0, 0, 80))
    draw.text((tx, ty), title_text, font=font_title, fill=(255, 255, 255, 255))

    line_y = ty + th + 20
    draw.rectangle([(1920 - 140) // 2, line_y, (1920 + 140) // 2, line_y + 3], fill=(58, 123, 213, 200))

    date_text = today if subtitle_text is None else subtitle_text
    bbox2 = draw.textbbox((0, 0), date_text, font=font_date)
    dw = bbox2[2] - bbox2[0]
    dx = (1920 - dw) // 2
    dy = line_y + 30
    draw.text((dx + 2, dy + 2), date_text, font=font_date, fill=(0, 0, 0, 60))
    draw.text((dx, dy), date_text, font=font_date, fill=(180, 190, 210, 255))

    overlay_path = str(Path(output_path).parent / "_title_overlay.png")
    overlay.save(overlay_path, "PNG")

    if background_video and Path(background_video).exists():
        vf = (
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            "eq=brightness=-0.15:saturation=0.7,"
            "fade=in:0:25"
        )
        cmd = [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", background_video,
            "-i", overlay_path,
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-filter_complex", f"[0:v]{vf}[bg];[bg][1:v]overlay=0:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "1k", "-pix_fmt", "yuv420p",
            "-t", f"{dur:.1f}", "-shortest", output_path,
        ]
    else:
        gradient_expr = (
            "r(X,Y)=15+10*sin(0.3*T)+(X/W-0.5)^2*30+(Y/H-0.5)^2*25:"
            "g(X,Y)=12+5*cos(0.25*T)+(X/W-0.5)^2*18+(Y/H-0.5)^2*15:"
            "b(X,Y)=30+8*sin(0.2*T)+(Y/H)*25+(X/W)*15"
        )
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=0x0A0A1A:s=1920x1080:r=30:d={dur:.1f}",
            "-i", overlay_path,
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-filter_complex",
            f"[0:v]geq='{gradient_expr}',format=yuv420p,fade=in:0:25[bg];[bg][1:v]overlay=0:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "1k", "-pix_fmt", "yuv420p",
            "-t", f"{dur:.1f}", output_path,
        ]

    result = _sp.run(cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
    try:
        Path(overlay_path).unlink()
    except Exception:
        pass

    if result.returncode != 0:
        logger.warning("Title card compositing failed: %s", (result.stderr or "")[:300])
        _generate_solid_card(output_path, dur)
    else:
        logger.info("Title card generated: %s", output_path)


def _generate_solid_card(output_path: str, dur: float) -> None:
    """Last-resort solid-colour card."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x0f0f23:s=1920x1080:d={dur:.1f}",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-c:a", "aac", "-b:a", "1k", "-pix_fmt", "yuv420p",
        "-t", f"{dur:.1f}", output_path,
    ]
    _sp.run(cmd, capture_output=True, timeout=30, encoding="utf-8", errors="replace")


def _generate_simple_bg(output_path: str, duration_sec: float,
                        background_video: str | None = None) -> None:
    """Loop a background video with darkening + silence, no text overlay."""
    dur = max(duration_sec, 2.0)

    if background_video and Path(background_video).exists():
        vf = (
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            "eq=brightness=-0.2:saturation=0.5,"
            "fade=out:st={:.0f}:d=1".format(max(dur - 1, 0))
        )
        cmd = [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", background_video,
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", vf,
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "1k", "-pix_fmt", "yuv420p",
            "-t", f"{dur:.1f}", "-shortest", output_path,
        ]
    else:
        gradient_expr = (
            "r(X,Y)=8+5*sin(0.2*T)+(X/W-0.5)^2*15+(Y/H-0.5)^2*20:"
            "g(X,Y)=6+3*cos(0.15*T)+(X/W-0.5)^2*10+(Y/H-0.5)^2*12:"
            "b(X,Y)=20+5*sin(0.1*T)+(Y/H)*20+(X/W)*10"
        )
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=0x0A0A1A:s=1920x1080:r=30:d={dur:.1f}",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", f"geq='{gradient_expr}',format=yuv420p,fade=out:st={max(dur - 1, 0):.0f}:d=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-c:a", "aac", "-b:a", "1k", "-pix_fmt", "yuv420p",
            "-t", f"{dur:.1f}", output_path,
        ]

    _sp.run(cmd, capture_output=True, timeout=120, encoding="utf-8", errors="replace")


def _generate_placeholder(output_path: str, duration_sec: float) -> None:
    """Dark placeholder video for segments without B-roll."""
    dur = max(duration_sec, 2.0)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x1a1a2e:s=1920x1080:d={dur:.1f}",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-c:a", "aac", "-b:a", "1k", "-pix_fmt", "yuv420p",
        "-t", f"{dur:.1f}", output_path,
    ]
    _sp.run(cmd, capture_output=True, timeout=30, encoding="utf-8", errors="replace")


# ═══════════════════════════════════════════════════════════════════════════
# Script subtitles + text cleaning
# ═══════════════════════════════════════════════════════════════════════════

def _clean_spoken_text(text: str) -> str:
    """Strip markdown formatting so Edge TTS doesn't read it aloud."""
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = text.replace('**', '').replace('__', '').replace('*', '').replace('_', '')
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', text)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = text.replace('`', '')
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.replace('<!--BROLL:', '').replace('-->', '')
    text = re.sub(r'^BROLL[：:].*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'我们明天同一时间再见[。.]?', '感谢您的收看。', text)
    text = re.sub(r'明天同一时间[，,]?\s*.*?[。.]', '。', text)
    text = re.sub(r'敬请期待[。.]?', '', text)
    text = re.sub(r'我们下期再见[。.]?', '感谢您的收看。', text)
    return text.strip()


def _generate_script_subtitles(segments: list[dict], durations: list[float],
                               video_dir: Path) -> str | None:
    """Generate SRT subtitles from script text (zero Whisper typos)."""

    def _split_phrases(text: str, max_chars: int = 20) -> list[str]:
        text = _clean_spoken_text(text)
        parts = re.split(r'([。，、；：？！\n,.!?;:])', text)
        phrases: list[str] = []
        buf = ""
        for p in parts:
            if not p:
                continue
            if re.match(r'^[。，、；：？！\n,.!?;:]$', p):
                buf += p
                if len(buf) > 2:
                    phrases.append(buf)
                    buf = ""
            else:
                if buf and len(buf) + len(p) > max_chars:
                    phrases.append(buf)
                    buf = p
                else:
                    buf += p
        if buf:
            phrases.append(buf)
        merged: list[str] = []
        for ph in phrases:
            if merged and len(merged[-1]) + len(ph) <= max_chars:
                merged[-1] += ph
            else:
                merged.append(ph)
        return [m.strip() for m in merged if m.strip()]

    entries: list[tuple[float, float, str]] = []
    time_offset = 0.0

    for seg, total_dur in zip(segments, durations):
        text = seg.get("text", "")
        phrases = _split_phrases(text)
        if not phrases or total_dur <= 0:
            time_offset += total_dur
            continue
        total_chars = sum(len(p) for p in phrases)
        for phrase in phrases:
            phrase_dur = (len(phrase) / total_chars) * total_dur
            phrase_dur = max(phrase_dur, 1.0)
            start = time_offset
            end = time_offset + phrase_dur
            entries.append((start, end, phrase))
            time_offset += phrase_dur

    if not entries:
        return None

    sub_path = str(video_dir / "script_subtitles.srt")
    with open(sub_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(entries, 1):
            start_s = _format_srt_time(start)
            end_s = _format_srt_time(end)
            try:
                from subtitle import _to_simplified
                text = _to_simplified(text)
            except ImportError:
                pass
            f.write(f"{i}\n{start_s} --> {end_s}\n{text}\n\n")

    logger.info("Script subtitles: %d entries → %s", len(entries), sub_path)
    return sub_path


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
