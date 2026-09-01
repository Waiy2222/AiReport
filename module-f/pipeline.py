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
from video_search import VideoSearcher, set_active_domain as _vs_set_active_domain
from editor import VideoEditor
from tts import TTSEngine
from subtitle import SubtitleGenerator

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", str(Path(__file__).parent / "output"))).resolve()
DOWNLOAD_DIR = Path(os.getenv("VIDEO_DOWNLOAD_DIR", str(Path(__file__).parent / "downloads"))).resolve()
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ai_news")
_VIDEO_DOMAIN = os.getenv("VIDEO_DOMAIN", "AI")
_ACTIVE_DOMAIN: str | None = None  # set by run_full_pipeline when keyword is provided


def _get_domain_config(domain: str | None = None) -> dict:
    """Return domain configuration dict.

    1. If domain is a known preset in _DOMAIN_CONFIG → use it directly.
    2. Otherwise → dynamically build config from env vars / domain name itself,
       so ANY domain value works without editing Python code.

    Env vars for custom domains (all optional, sensible defaults from domain name):
      VIDEO_DOMAIN_DISPLAY       - display name (default: domain name)
      VIDEO_DOMAIN_CATEGORY      - RSS category (default: domain name)
      VIDEO_DOMAIN_BADGE         - cover badge text (default: {display}早报)
      VIDEO_DOMAIN_HOST          - virtual host name (default: AI主播)
      VIDEO_DOMAIN_BROLL_FALLBACK- B-roll fallback search keywords
      VIDEO_DOMAIN_PEXELS_QUERY  - Pexels search query
      VIDEO_DOMAIN_PROMPT_CONTEXT- LLM prompt: topic areas to cover
      VIDEO_DOMAIN_PROMPT_FOCUS  - LLM prompt: focus areas
    """
    key = (domain or _ACTIVE_DOMAIN or _VIDEO_DOMAIN).strip()
    if key in _DOMAIN_CONFIG:
        return _DOMAIN_CONFIG[key]

    # ── Dynamic domain: build config from env vars ──
    display = os.getenv("VIDEO_DOMAIN_DISPLAY", key).strip() or key
    category = os.getenv("VIDEO_DOMAIN_CATEGORY", key).strip() or key
    badge = os.getenv("VIDEO_DOMAIN_BADGE", f"{display}早报").strip()
    host = os.getenv("VIDEO_DOMAIN_HOST", "AI主播").strip()
    broll_fallback = os.getenv("VIDEO_DOMAIN_BROLL_FALLBACK", display).strip()
    pexels_query = os.getenv("VIDEO_DOMAIN_PEXELS_QUERY", key).strip()
    prompt_context = os.getenv("VIDEO_DOMAIN_PROMPT_CONTEXT", display).strip()
    prompt_focus = os.getenv("VIDEO_DOMAIN_PROMPT_FOCUS", "").strip()

    # Optional JSON-configured fields
    en_to_cn: dict[str, str] = {}
    agent_core: list[str] = []
    agent_products: list[str] = []
    try:
        raw = os.getenv("VIDEO_DOMAIN_EN_TO_CN", "")
        if raw:
            en_to_cn = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("VIDEO_DOMAIN_EN_TO_CN is not valid JSON, ignoring")
    try:
        raw = os.getenv("VIDEO_DOMAIN_AGENT_CORE", "")
        if raw:
            agent_core = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("VIDEO_DOMAIN_AGENT_CORE is not valid JSON, ignoring")
    try:
        raw = os.getenv("VIDEO_DOMAIN_AGENT_PRODUCTS", "")
        if raw:
            agent_products = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("VIDEO_DOMAIN_AGENT_PRODUCTS is not valid JSON, ignoring")

    logger.info("Dynamic domain %r: display=%r category=%r", key, display, category)
    return {
        "label": key,
        "display": display,
        "category": category,
        "badge": badge,
        "host": host,
        "broll_fallback": broll_fallback,
        "pexels_query": pexels_query,
        "prompt_context": prompt_context,
        "prompt_focus": prompt_focus,
        "en_to_cn": en_to_cn,
        "agent_core": agent_core,
        "agent_products": agent_products,
    }


_DOMAIN_CONFIG: dict[str, dict] = {
    # ── AI / 智能体（默认） ──
    "AI": {
        "label": "AI",
        "display": "AI智能体",
        "category": "科技",
        "badge": "AI 早报",
        "host": "AI主播",
        "broll_fallback": "AI科技 智能体 Agent",
        "pexels_query": "artificial intelligence technology digital data",
        "prompt_context": "LLM（大模型）、Agent（智能体）、开源、工具、科技、行业、全球、芯片、机器人、自动驾驶、融资、医疗",
        "prompt_focus": "Agent / 智能体: 桌面智能体、编程智能体、办公智能体、多智能体协作、MCP协议等",
        # English→Chinese keyword map for B站 search (AI domain)
        "en_to_cn": {
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
        },
        # Agent-specific keywords for news filtering (Agent tag priority)
        "agent_core": [
            "agent", "智能体", "agentic", "自主", "multi-agent", "多智能体", "多agent",
            "桌面智能", "desktop agent", "电脑操控", "电脑操作", "computer use",
            "gui自动化", "gui automation", "浏览器智能体", "browser agent",
            "编程智能体", "coding agent", "代码agent", "办公智能体", "办公agent",
            "工具调用", "function call", "tool use", "任务规划", "task planning",
            "自主执行", "工作流自动化", "workflow automation", "mcp", "model context protocol",
            "a2a", "agent-to-agent",
        ],
        "agent_products": [
            "openhuman", "openclaw", "dumate", "genflow", "crewai", "autogpt",
            "babyagi", "agentgpt", "copilot", "cursor", "windsurf", "devin",
            "manus", "aionui", "echobot", "superpowers", "claude code",
            "gemini agent", "copilot studio", "langgraph", "langflow", "dify",
            "coze", "扣子", "百炼", "元器",
        ],
    },
    # ── 体育 ──
    "体育": {
        "label": "体育",
        "display": "体育",
        "category": "体育",
        "badge": "体育早报",
        "host": "AI主播",
        "broll_fallback": "体育赛事 竞技",
        "pexels_query": "sports competition athletics stadium",
        "prompt_context": "足球、篮球、网球、F1、综合格斗、奥运会等主流体育赛事",
        "prompt_focus": "赛事结果、转会动态、运动员动态、联赛排名",
        "en_to_cn": {
            "nba": "NBA篮球", "nfl": "橄榄球", "mlb": "棒球", "ufc": "综合格斗",
            "fifa": "国际足联", "uefa": "欧冠", "premier": "英超",
            "laliga": "西甲", "seriea": "意甲", "bundesliga": "德甲",
        },
        "agent_core": [],
        "agent_products": [],
    },
    # ── 芯片 ──
    "芯片": {
        "label": "芯片",
        "display": "芯片",
        "category": "芯片",
        "badge": "芯片早报",
        "host": "AI主播",
        "broll_fallback": "芯片 半导体 处理器",
        "pexels_query": "computer chip semiconductor processor technology",
        "prompt_context": "芯片设计、半导体制造、处理器架构、GPU/CPU/NPU、EDA工具、晶圆代工",
        "prompt_focus": "芯片发布、制程工艺、架构迭代、半导体产业链动态",
        "en_to_cn": {
            "nvidia": "英伟达", "amd": "AMD", "intel": "英特尔",
            "tsmc": "台积电", "samsung": "三星", "qualcomm": "高通",
            "arm": "ARM架构", "riscv": "RISC-V", "gpu": "GPU显卡",
            "cpu": "CPU处理器", "npu": "AI芯片", "hbm": "高带宽内存",
        },
        "agent_core": [],
        "agent_products": [],
    },
    # ── 机器人 ──
    "机器人": {
        "label": "机器人",
        "display": "机器人",
        "category": "机器人",
        "badge": "机器人早报",
        "host": "AI主播",
        "broll_fallback": "机器人 自动化 AI",
        "pexels_query": "robot automation technology factory",
        "prompt_context": "人形机器人、工业机器人、具身智能、机械臂、自动化、ROS、传感器",
        "prompt_focus": "机器人新品发布、人形机器人进展、自动化落地案例、融资动态",
        "en_to_cn": {
            "robot": "机器人", "robotics": "机器人技术",
            "boston": "波士顿动力", "tesla": "特斯拉",
            "humanoid": "人形机器人", "ros": "机器人系统",
            "embodied": "具身智能", "actuator": "执行器",
        },
        "agent_core": [],
        "agent_products": [],
    },
    # ── 医疗 ──
    "医疗": {
        "label": "医疗",
        "display": "医疗",
        "category": "医疗",
        "badge": "医疗早报",
        "host": "AI主播",
        "broll_fallback": "医疗 AI 医学",
        "pexels_query": "medical healthcare technology research",
        "prompt_context": "AI医疗、药物研发、基因编辑、医疗器械、临床试验、数字健康",
        "prompt_focus": "新药获批、临床试验进展、医疗AI应用、医疗器械创新",
        "en_to_cn": {
            "fda": "FDA审批", "crispr": "基因编辑", "mrna": "mRNA疫苗",
            "alphafold": "蛋白质预测", "clinical": "临床试验",
            "diagnosis": "诊断", "therapy": "治疗",
        },
        "agent_core": [],
        "agent_products": [],
    },
    # ── 自动驾驶 ──
    "自动驾驶": {
        "label": "自动驾驶",
        "display": "自动驾驶",
        "category": "自动驾驶",
        "badge": "自动驾驶早报",
        "host": "AI主播",
        "broll_fallback": "自动驾驶 智能汽车",
        "pexels_query": "autonomous driving car technology road",
        "prompt_context": "自动驾驶、智能汽车、激光雷达、FSD、Robotaxi、车路协同、ADAS",
        "prompt_focus": "自动驾驶政策、FSD更新、Robotaxi运营、车企智驾方案",
        "en_to_cn": {
            "tesla": "特斯拉", "waymo": "Waymo", "fsd": "全自动驾驶",
            "lidar": "激光雷达", "robotaxi": "无人出租车",
            "adas": "辅助驾驶", "cruise": "Cruise",
        },
        "agent_core": [],
        "agent_products": [],
    },
    # ── 融资（科技创投） ──
    "融资": {
        "label": "融资",
        "display": "科技创投",
        "category": "科技",
        "badge": "创投早报",
        "host": "AI主播",
        "broll_fallback": "科技 融资 创投",
        "pexels_query": "startup business technology investment",
        "prompt_context": "科技融资、IPO上市、创投动态、收购并购、估值变化",
        "prompt_focus": "大额融资、独角兽动态、IPO消息、并购整合",
        "en_to_cn": {},
        "agent_core": [],
        "agent_products": [],
    },
}


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

    async def start(self, video_id: str, vtype: str, vdate: date, keyword: str | None = None) -> dict:
        pool = await self._get_pool()

        # Check for duplicate processing task (same video_id)
        existing = await pool.fetchrow(
            "SELECT id, status FROM videos WHERE id = $1::uuid", video_id,
        )
        if existing:
            if existing["status"] in ("pending", "processing"):
                return {"id": video_id, "status": existing["status"], "type": vtype, "date": vdate.isoformat()}

        await pool.execute(
            "INSERT INTO videos (id, type, date, status, keyword) VALUES ($1, $2, $3, 'processing', $4)"
            " ON CONFLICT (id) DO UPDATE SET status = 'processing', keyword = $4",
            video_id, vtype, vdate, keyword or vtype,
        )

        task = asyncio.create_task(self._run_and_catch(video_id, vtype, vdate, keyword=keyword))
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
            # Flatten cover_path from metadata JSON to top level
            meta_raw = d.get("metadata")
            if isinstance(meta_raw, str):
                try:
                    meta = json.loads(meta_raw)
                    d["cover_path"] = meta.get("cover_path", "")
                except (json.JSONDecodeError, TypeError):
                    d["cover_path"] = ""
            elif isinstance(meta_raw, dict):
                d["cover_path"] = meta_raw.get("cover_path", "")
            else:
                d["cover_path"] = ""
            results.append(d)
        return results

    # ---- background task --------------------------------------------------

    async def _run_and_catch(self, video_id: str, vtype: str, vdate: date, keyword: str | None = None):
        try:
            output_path = await self.run_full_pipeline(video_id, vtype, vdate, keyword=keyword)
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

    async def run_full_pipeline(self, video_id: str, vtype: str, vdate: date, keyword: str | None = None) -> str:
        global _ACTIVE_DOMAIN
        pool = await self._get_pool()
        video_dir = OUTPUT_DIR / video_id
        video_dir.mkdir(parents=True, exist_ok=True)
        today = vdate.isoformat()

        # Resolve domain: keyword takes priority, then env var, then default "AI"
        _domain_key = keyword or _VIDEO_DOMAIN
        _ACTIVE_DOMAIN = _domain_key
        dc = _get_domain_config()

        # Inject into video_search so all filters become domain-aware
        _vs_set_active_domain(_domain_key, dc)

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
                keywords = seg.get("broll_keywords", _get_domain_config()["broll_fallback"])

                # Preprocess keywords for B站 (domain-aware EN→CN mapping)
                _EN_TO_CN = _get_domain_config().get("en_to_cn", {})
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

                # Enrich sparse keywords with domain context
                if len(keywords.split()) <= 2:
                    dc_broll = _get_domain_config()["broll_fallback"]
                    dc_kws = set(keywords.split()) | set(dc_broll.split())
                    keywords = " ".join(dc_kws)

                topic_clean = topic.split("：", 1)[-1].strip() if "：" in topic else topic
                results: list[dict] = []

                # Strategy 1: BROLL keywords (enriched)
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

                # Strategy 3: domain fallback search
                if not results:
                    results = await self.searcher.search(_get_domain_config()["broll_fallback"], max_results=3)
                    logger.info("[F:%s]   搜索段%d (兜底): -> %d 结果", video_id, i, len(results))

                # Domain gate + relevance scoring
                # Build richer scoring context: topic + keywords + domain display
                score_context = topic_clean + " " + keywords + " " + _get_domain_config()["display"]
                scored = _score_clip_relevance(results, score_context)
                # Adaptive threshold: higher when we have strong domain context
                threshold = 5 if len(_build_domain_context()) > 5 else 3
                results = [s[0] for s in scored if s[1] >= threshold]
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

        
        # ---- Step 2.6: search online photos (B站 covers = most relevant visual) ----
        logger.info("[F:%s] Step 2.6: 搜索在线图片...", video_id)
        segment_images: list[list[dict]] = []
        for i, seg in enumerate(segments):
            topic = seg.get("topic", "")
            if "开场" in topic or "结尾" in topic:
                segment_images.append([])
                continue
            broll_kw = seg.get("broll_keywords", "")
            # Use broll_keywords directly as B站 query (DeepSeek generates sports-specific terms)
            # Fall back to entity + domain if empty
            bili_q = broll_kw.strip() if broll_kw.strip() else _get_domain_config()["broll_fallback"]
            imgs = []
            try:
                bili_covers = await asyncio.wait_for(
                    self.searcher._search_bilibili_covers(bili_q, max_results=6), timeout=15)
                if bili_covers:
                    imgs.extend(bili_covers)
            except Exception:
                pass
            # Also try with entity name
            entity = _extract_main_entity(topic.split("：", 1)[-1].strip() if "：" in topic else topic)
            if entity and entity not in bili_q:
                try:
                    more = await asyncio.wait_for(
                        self.searcher._search_bilibili_covers(entity, max_results=3), timeout=12)
                    seen = {img.get("url", "") for img in imgs}
                    for m in more:
                        if m.get("url", "") not in seen:
                            imgs.append(m)
                except Exception:
                    pass
            # Pexels fallback: if B站 returns nothing, try general image search
            if not imgs:
                try:
                    fallback_q = bili_q if any(ord(c) < 128 for c in bili_q) else _get_domain_config()["broll_fallback"]
                    general = await asyncio.wait_for(
                        self.searcher.search_images(fallback_q, max_results=5), timeout=20)
                    imgs.extend(general)
                except Exception:
                    pass
            segment_images.append(imgs)
            logger.info("[F:%s]   段%d: %d张图片 for '%s'", video_id, i, len(imgs), bili_q[:30])

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

        # ---- Image fallback: use B站 cover images when no video clips ----
        for i, seg_downloads in enumerate(downloaded):
            if seg_downloads:
                continue  # Already have video clips
            images = segment_images[i] if i < len(segment_images) else []
            if not images:
                continue
            seg_text = segments[i].get("text", "")
            est_dur = max(5.0, len(seg_text) / 3.5)
            for j, img in enumerate(images[:3]):
                try:
                    local = await self.searcher.download_image(img.get("url", ""))
                    if local:
                        kb_path = str(video_dir / f"kenburns_{i:02d}_{j:02d}.mp4")
                        kb_dur = max(4.0, est_dur / max(len(images[:3]), 1))
                        if self.editor.image_to_video(local, kb_path, kb_dur):
                            seg_downloads.append(kb_path)
                except Exception:
                    pass
            if seg_downloads:
                logger.info("[F:%s]   段%d: 0视频 -> %d图片 (图像模式)", video_id, i, len(seg_downloads))

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
            seg = segments[i]
            topic = seg.get("topic", "")
            is_opening = "开场" in topic or "概述" in topic
            is_closing = "结尾" in topic or "总结" in topic

            if not clip_paths:
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
                                         subtitle_text=f"{_get_domain_config()['display']}早报 明日再见",
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

            per_clip_dur = target_dur / len(clip_paths) if len(clip_paths) > 0 else target_dur
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

        # ---- Step 5.5: assemble per-segment videos + floating corner titles ----
        logger.info("[F:%s] Step 5.5: 逐段拼合 + 浮动标题...", video_id)
        segment_videos: list[str] = []
        for i, (clips, _target_dur) in enumerate(zip(trimmed_segments, segment_durations)):
            seg = segments[i]
            topic = seg.get("topic", "")
            is_opening = "开场" in topic or "概述" in topic
            is_closing = "结尾" in topic or "总结" in topic

            if len(clips) == 0:
                continue  # opening / closing / placeholder handled in step 5

            # Combine segment clips with short intra-segment transitions
            seg_raw = str(video_dir / f"seg_raw_{i:02d}.mp4")
            if len(clips) == 1:
                import shutil as _sh
                _sh.copy(clips[0], seg_raw)
            else:
                self.editor.concat_with_transitions(clips, seg_raw, transition="fadeblack", duration=0.3)

            # Add floating news headline for real news segments
            if not is_opening and not is_closing:
                topic_clean = re.sub(r'^消息[一二三四五六七八九十\d]+[：:\s]*', '', topic).strip()
                if not topic_clean:
                    topic_clean = topic
                seg_titled = str(video_dir / f"seg_titled_{i:02d}.mp4")
                ok = self.editor.add_text_overlay(seg_raw, seg_titled, topic_clean)
                if ok:
                    segment_videos.append(seg_titled)
                    logger.info("[F:%s]   段%d [%s]: 浮动标题已叠加", video_id, i, topic_clean)
                else:
                    segment_videos.append(seg_raw)
                    logger.warning("[F:%s]   段%d [%s]: 标题叠加失败，使用原画面", video_id, i, topic_clean)
            # Non-news segments (opening/closing) are handled directly in all_broll;
            # do NOT add them to segment_videos, which would offset news indexing.

        # Build final clip list: cards (opening/closing/placeholder) + segment videos
        all_broll: list[str] = []
        seg_vid_idx = 0
        for i, clips in enumerate(trimmed_segments):
            if len(clips) == 0:
                continue  # these don't contribute clips (unexpected)
            seg = segments[i]
            topic = seg.get("topic", "")
            is_non_news = "开场" in topic or "概述" in topic or "结尾" in topic or "总结" in topic
            if is_non_news:
                all_broll.extend(clips)  # title card / closing card / placeholder → 1 clip
            else:
                if seg_vid_idx < len(segment_videos):
                    all_broll.append(segment_videos[seg_vid_idx])
                    seg_vid_idx += 1
                else:
                    all_broll.extend(clips)  # fallback: raw clips

        # ---- Step 6: concat segment videos ----
        logger.info("[F:%s] Step 6: 拼接各段视频...", video_id)
        if not all_broll:
            raise RuntimeError("无可用B-roll素材！")

        raw_video = str(video_dir / "raw_broll.mp4")
        ok = self.editor.concat_with_transitions(
            all_broll, raw_video, transition="fadeblack", duration=0.6)
        if not ok:
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

        # ---- Final re-encode: keyframes + faststart for smooth seeking ----
        final_seekable = str(video_dir / f"{vtype}_{vdate.isoformat()}_final.mp4")
        if self.editor.reencode_final(final_path, final_seekable):
            final_path = final_seekable
            logger.info("[F:%s] 最终编码优化完成 (keyframe+faststart)", video_id)

        # ---- Generate cover: take a frame from the video ----
        cover_path = str(video_dir / "cover.jpg")
        try:
            self.editor.extract_frame(final_path, cover_path, time_sec=3)
            logger.info("[F:%s] 封面抽帧: %s", video_id, cover_path)
        except Exception:
            logger.exception("[F:%s] 封面抽帧失败，跳过", video_id)
            cover_path = ""

        # ---- Save metadata (upsert: works for both HTTP and local runs) ----
        meta = json.dumps({
            "segments": len(segments),
            "clips_downloaded": total_clips,
            "duration_sec": round(total_duration),
            "model": "deepseek-chat",
            "tts": "edge-tts (zh-CN-XiaoyiNeural)",
            "subtitles": "script-based (zero-typo)",
            "intro_bg": "pexels" if intro_bg else "gradient",
            "cover_path": cover_path,
        })
        await pool.execute(
            "INSERT INTO videos (id, type, date, status, script, title, metadata, duration_seconds, output_path) "
            "VALUES ($1, $2, $3, 'done', $4, $5, $6, $7, $8) "
            "ON CONFLICT (id) DO UPDATE SET "
            "status = 'done', script = $4, title = $5, metadata = $6, "
            "duration_seconds = $7, output_path = $8, finished_at = now()",
            video_id, vtype, vdate,
            script_text,
            f"{_get_domain_config()['display']}早报 — {today}",
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
    """Fetch real news from RSS sources based on _VIDEO_DOMAIN."""
    try:
        from scrapers.rss import fetch_single_rss, RSS_SOURCES, to_raw_items
    except ImportError:
        logger.warning("无法导入 module-a RSS 模块")
        return []

    # Map domain to RSS category via domain config
    dc = _get_domain_config()
    category = dc.get("category", "科技")
    sources = [s for s in RSS_SOURCES if s.get("category") == category]
    is_fallback_sources = False
    if not sources:
        sources = [s for s in RSS_SOURCES if s.get("category") == "科技"]  # fallback
        is_fallback_sources = True

    batch_id = _uuid.uuid4()
    since = datetime.now(timezone.utc) - timedelta(hours=36)

    tasks = [fetch_single_rss(src) for src in sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_entries = []
    for i, result in enumerate(results):
        source_name = sources[i]["name"]
        if isinstance(result, Exception):
            logger.warning("RSS [%s] 失败: %s", source_name, result)
            continue
        for entry in result:
            entry["_source_name"] = source_name
            entry["_category"] = dc.get("category", "科技")
        all_entries.extend(result)

    filtered = [e for e in all_entries if _rss_entry_time(e) >= since]
    raw_items = to_raw_items(filtered, "rss", batch_id)
    logger.info("RSS抓取: %d 条%s新闻 (来源类别=%s)", len(raw_items), dc["display"], category)

    # Always apply domain filter when using fallback sources or for 科技 category.
    # For custom domains (e.g. 量子计算), this filters out irrelevant tech news.
    if category == "科技" or is_fallback_sources:
        arxiv_items = await _fetch_arxiv_news(batch_id)
        logger.info("arXiv抓取: %d 篇论文", len(arxiv_items))
        raw_items.extend(arxiv_items)
        raw_items = _filter_domain_news(raw_items)
        logger.info("领域过滤后: %d 条%s相关新闻", len(raw_items), dc["display"])

    # If after filtering we have too few or zero items, let DeepSeek use its own knowledge
    if len(raw_items) == 0:
        logger.info("无%s相关新闻，将使用DeepSeek知识生成脚本", dc["display"])
        return []

    return raw_items[:15]


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


def _filter_domain_news(items: list[dict]) -> list[dict]:
    """Filter news by domain relevance using config-driven keyword scoring.

    Uses the active domain's prompt_context to build dynamic keyword matchers.
    Falls back to the 14-tag system for preset domains. For custom keywords,
    builds matching keywords from the domain name and prompt_context.
    """
    dc = _get_domain_config()
    domain_label = dc["label"]

    # Domain-specific keywords from config
    agent_core = dc.get("agent_core", [])
    agent_products = dc.get("agent_products", [])

    # Build domain-specific context keywords from prompt_context
    prompt_ctx = dc.get("prompt_context", domain_label)
    # Split by Chinese/English punctuation to get individual topic words
    domain_topics = set()
    for part in re.split(r'[、，,；;。.\s]+', prompt_ctx):
        part = part.strip()
        if part and len(part) >= 2:
            domain_topics.add(part.lower())
    # Also add the domain label itself
    domain_topics.add(domain_label.lower())

    # 14-tag keyword mapping — aligns with module-b/ai/analyzer.py _KEYWORD_TAG_MAP
    tag_keywords = {
        "LLM":    ["llm", "大模型", "gpt", "claude", "gemini", "文心", "星火", "通义", "deepseek", "深度求索"],
        "Agent":  [],
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

    # Hard exclude: content that should never appear in a news video
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

        # Product/core keyword scoring (from domain config, if configured)
        product_score = sum(5 for kw in agent_products if kw in text)
        core_score = sum(3 for kw in agent_core if kw in text)

        # Domain topic scoring: match against domain_topics from prompt_context
        domain_topic_score = sum(2 for dt in domain_topics if dt in text)

        # Score by 14-tag keyword match (1pt per tag hit)
        tag_score = 0
        matched_tags = []
        for tag, keywords in tag_keywords.items():
            if any(kw in text for kw in keywords):
                tag_score += 2
                matched_tags.append(tag)

        # For custom domains (no agent_core/products), rely on domain_topic_score + tag_score
        total = product_score + core_score + domain_topic_score + tag_score

        # Threshold: lower for custom domains, standard for preset domains
        has_preset_config = bool(agent_core or agent_products)
        threshold = 5 if has_preset_config else 2

        if total >= threshold:
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
        dc = _get_domain_config()
        display = dc["display"]
        prompt = f"""你是{display}领域的专业新闻主播。下方是最近24小时的新闻素材。

⚠️ 核心铁律：
1. 必须基于上方提供的真实新闻，绝对不要编造
2. 标题≤15字，简洁有力
3. 每条新闻=事件句+意义句，各一句
4. 不同公司/实体，禁止同一公司出现两次
5. 中文TTS无法朗读英文 → 所有英文用中文表达
6. 严禁Markdown、URL、过渡词

⚠️ 结构铁律：【开场引导】→ 4-5条新闻 → 无结尾

格式（必须严格复制！【新闻N：】前缀不可省略！）：
【开场引导】
欢迎收看{today} {display}早报。
BROLL: {dc["broll_fallback"]}

【新闻一：≤15字标题】
事件句.简要背景或影响.
BROLL: <公司/实体名> <关键词>

【新闻二：≤15字标题】
事件句.简要背景或影响.
BROLL: <公司/实体名> <关键词>

【新闻三：≤15字标题】
事件句.简要背景或影响.
BROLL: <公司/实体名> <关键词>

【新闻四：≤15字标题】
事件句.简要背景或影响.
BROLL: <公司/实体名> <关键词>

【新闻五：≤15字标题】
事件句.简要背景或影响.
BROLL: <公司/实体名> <关键词>

总字数250-350字。

今日新闻素材：
{news_context}"""
    else:
        dc = _get_domain_config()
        display = dc["display"]
        prompt_ctx = dc.get("prompt_context", display)
        prompt_focus = dc.get("prompt_focus", "")
        focus_block = f"\n重点关注领域：{prompt_focus}" if prompt_focus else ""
        prompt = f"""你是{display}领域的专业新闻主播。今天（{today}）没有实时新闻素材，请基于你的知识撰写{display}早报解说词。

可覆盖的主题领域：{prompt_ctx}{focus_block}

格式（必须严格复制！【新闻N：】前缀不可省略！）：
【开场引导】
欢迎收看{today}{display}早报。
BROLL: {dc["broll_fallback"]}

【新闻一：具体标题示例】
一句话事件。一句话意义。
BROLL: 公司名 关键词

【新闻二：具体标题示例】
一句话事件。一句话意义。
BROLL: 公司名 关键词

4-5条新闻，无结尾。总字数250-350字。"""

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
        broll_fb = _get_domain_config()["broll_fallback"]
        m = broll_new.search(text)
        if m:
            kw = m.group(1).strip()
            if kw in ("搜索关键词", "此处填写", "替换为", "在此填写", "实际搜索词", "搜索词"):
                return broll_fb, broll_new.sub("", text)
            return kw, broll_new.sub("", text)
        m = broll_old.search(text)
        if m:
            kw = m.group(1).strip()
            if kw in ("搜索关键词", "此处填写", "替换为", "在此填写", "实际搜索词", "搜索词"):
                return broll_fb, broll_old.sub("", text)
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
                    broll_keywords = _get_domain_config()["broll_fallback"]
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
                opening_broll = _get_domain_config()["broll_fallback"]
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
                broll_keywords = _get_domain_config()["broll_fallback"]
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
                closing_broll = _get_domain_config()["broll_fallback"]
            clean_lines.append("结尾总结")
            clean_lines.append(closing_text.strip())
            segments.append({"topic": "结尾总结", "text": closing_text.strip(), "broll_keywords": closing_broll})

        if segments:
            return "\n".join(clean_lines), segments

    # Ultimate fallback
    text = raw.strip()
    single_broll, text = _extract_broll(text)
    if single_broll is None:
        single_broll = _get_domain_config()["broll_fallback"]
    segments.append({"topic": f"{_get_domain_config()['display']}早报", "text": text.strip(), "broll_keywords": single_broll})
    return "\n".join(clean_lines) if clean_lines else text, segments


def _fallback_script(today: str) -> tuple[str, list[dict]]:
    """Fallback domain news script when DeepSeek is unavailable."""
    dc = _get_domain_config()
    display = dc["display"]
    broll_fb = dc.get("broll_fallback", display)
    script = f"""【开场引导】
欢迎收看{today}{display}早报。今天我们将关注{display}领域的最新进展和重要动态。
BROLL: {broll_fb}

【新闻一：今日{display}领域快讯】
今日{display}领域有多项值得关注的动态，产业各方积极布局推动技术落地应用.
BROLL: {broll_fb}

【新闻二：行业趋势观察】
{display}技术持续发展，产业生态不断演进，多家企业推出创新方案加速行业变革.
BROLL: {broll_fb}"""
    text, segments = _parse_script(script, today)
    logger.info("使用%s模板脚本: %d 字, %d 段", display, len(script), len(segments))
    return text, segments


# ═══════════════════════════════════════════════════════════════════════════
# B-roll relevance scoring (domain gate + keyword overlap)
# ═══════════════════════════════════════════════════════════════════════════

# Always-irrelevant domains — these clips should NEVER be used as B-roll
# regardless of the active domain.  Entertainment, ads, scams, etc.
DOMAIN_ALWAYS_IRRELEVANT = {
    "音乐", "歌曲", "MV", "翻唱", "演唱会", "歌手", "乐队", "专辑",
    "QQ音乐", "酷狗", "网易云", "唱吧", "全民K歌", "抖音神曲",
    "游戏", "电竞", "王者荣耀", "英雄联盟", "原神", "崩坏", "星穹铁道",
    "吃鸡", "绝地求生", "赛博朋克", "我的世界", "LOL", "PUBG", "DNF",
    "蛋仔派对", "第五人格", "阴阳师", "永劫无间", "光遇",
    "Steam", "switch", "PS5", "Xbox",
    "综艺", "搞笑", "鬼畜", "恶搞", "整蛊", "脱口秀", "相声", "小品",
    "真人秀", "选秀", "练习生", "女团", "男团", "偶像",
    "美食", "探店", "美妆", "穿搭", "减肥", "瑜伽",
    "星座", "塔罗", "占卜", "宠物", "萌宠", "钓鱼", "手工", "绘画",
    "书法", "舞蹈", "翻跳", "广场舞",
    "相亲", "恋爱", "婚姻", "育儿", "母婴",
    "中小学", "高考", "考研", "考公", "英语学习", "日语学习",
    "股票", "基金", "期货", "彩票", "荐股", "涨停", "跌停",
    "直播带货", "秒杀", "优惠券", "拼多多", "抽奖", "开箱",
    "电影", "电视剧", "网剧", "动漫", "番剧", "追番", "剧情",
    # Ads / scams / commercial
    "课程", "培训", "退费", "退款", "报名", "网课", "培训班", "训练营",
    "赚钱", "副业", "月入", "暴富", "躺赚", "薅羊毛", "返利",
    "理财", "炒股", "私募", "炒币", "资金盘", "传销", "加盟", "代理",
    "广告", "推广", "营销", "引流", "涨粉", "带货",
    "限时优惠", "最后一天", "名额有限", "早鸟价", "扫码入群",
    "加微信", "私信", "试听课", "体验课",
    "算命", "风水", "星座运势", "塔罗牌",
}

# Domain-specific irrelevant keywords: per-domain overrides.
# Each domain can have its own "irrelevant" list that supplements
# DOMAIN_ALWAYS_IRRELEVANT.  Keys match domain labels.
DOMAIN_IRRELEVANT_OVERRIDES: dict[str, set[str]] = {
    # For sports domain, "健身" and "旅游" are actually relevant
    "体育": {"健身", "旅游"},
    # For medical domain, "健身" could be relevant (health/fitness)
    "医疗": {"健身"},
}

# Previously DOMAIN_TECH — now built dynamically from domain config.
# Keep as fallback for when no domain config is available.
_DOMAIN_TECH_FALLBACK = {
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


def _build_domain_context() -> set[str]:
    """Build a set of domain-relevant keywords from the active domain config.

    Used by _score_clip_relevance to identify relevant clips for the
    current domain (replaces the old hardcoded DOMAIN_TECH).
    """
    dc = _get_domain_config()
    keywords: set[str] = set()

    # 1. Domain label + display name
    keywords.add(dc["label"].lower())
    keywords.add(dc["display"].lower())

    # 2. From prompt_context: split by punctuation to get topic words
    prompt_ctx = dc.get("prompt_context", "")
    for part in re.split(r'[、，,；;。.\s]+', prompt_ctx):
        part = part.strip().lower()
        if part and len(part) >= 2:
            keywords.add(part)

    # 3. From broll_fallback: split by spaces
    broll_fb = dc.get("broll_fallback", "")
    for part in broll_fb.split():
        part = part.strip().lower()
        if part and len(part) >= 2:
            keywords.add(part)

    # 4. From agent_core / agent_products if configured
    for kw in dc.get("agent_core", []):
        if kw and len(kw) >= 2:
            keywords.add(kw.lower())
    for kw in dc.get("agent_products", []):
        if kw and len(kw) >= 2:
            keywords.add(kw.lower())

    # 5. Fallback: if no keywords were built, use the tech fallback + domain label
    if len(keywords) <= 2:
        keywords.update(_DOMAIN_TECH_FALLBACK)

    return keywords


def _build_domain_irrelevant() -> set[str]:
    """Build the irrelevant keyword set for the active domain.

    Starts from DOMAIN_ALWAYS_IRRELEVANT, then removes any keywords
    that the current domain considers relevant (from DOMAIN_IRRELEVANT_OVERRIDES).
    """
    dc = _get_domain_config()
    domain_label = dc["label"]

    irr = set(DOMAIN_ALWAYS_IRRELEVANT)

    # Remove domain-specific overrides (keywords that ARE relevant for this domain)
    overrides = DOMAIN_IRRELEVANT_OVERRIDES.get(domain_label, set())
    irr -= overrides

    return irr

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
    """Score B站/Pexels clips by domain relevance + keyword overlap with news topic.

    Domain-aware: builds domain context keywords from the active domain config
    and uses them for both clip classification (relevant vs irrelevant) and
    content scoring.  Pre-computes keyword sets once for efficiency.
    """
    # ── Pre-compute domain context once ──
    _DOMAIN_CONTEXT = _build_domain_context()
    _DOMAIN_IRRELEVANT = _build_domain_irrelevant()

    # ── Tokenize topic text ──
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

    # ── Clip classification: domain-relevant vs irrelevant ──
    def _classify_domain(title: str, desc: str) -> tuple[str, int, list]:
        """Classify clip as 'relevant', 'neutral', or 'irrelevant'.

        Uses the dynamic _DOMAIN_CONTEXT instead of hardcoded DOMAIN_TECH.
        A clip is 'relevant' if it matches domain context keywords.
        It's 'irrelevant' only if it matches always-irrelevant keywords
        AND has NO domain context match.
        """
        content = title + " " + desc
        content_lower = content.lower()

        irr_hits = [kw for kw in _DOMAIN_IRRELEVANT if kw.lower() in content_lower]
        domain_hits = [kw for kw in _DOMAIN_CONTEXT if kw.lower() in content_lower]

        if irr_hits and not domain_hits:
            return ("irrelevant", -100, irr_hits)
        if irr_hits and domain_hits:
            # Has both: check if the primary signal (title) is irrelevant
            title_lower = title.lower()
            title_irr = [kw for kw in irr_hits if kw.lower() in title_lower]
            if title_irr:
                return ("irrelevant", -100, title_irr)
            return ("neutral", 0, [])
        if domain_hits:
            return ("relevant", 0, [])
        return ("neutral", 0, [])

    # ── Keyword overlap scoring ──
    def _score_overlap(clip_title: str, clip_desc: str) -> int:
        content = clip_title + " " + clip_desc
        score = 0

        # English entities: strong signal (20 pts each)
        for ent in eng_entities:
            if ent in content.lower():
                score += 20

        # Head tokens (most specific, highest weight)
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

        # Domain context hits: boost for clips matching the active domain
        domain_hits = sum(1 for t in _DOMAIN_CONTEXT if t.lower() in content.lower())
        if domain_hits > 0:
            score += domain_hits * 8  # was 5, increased for better relevance

        # Entity alias hits: check if known entities from topic appear in clip
        topic_entities = set()
        for entity in _ENTITY_ALIASES:
            if entity.lower() in head_text.lower():
                topic_entities.add(entity.lower())
        for ent in topic_entities:
            aliases = _get_entity_aliases(ent)
            for alias in aliases:
                if alias.lower() in content.lower():
                    score += 10  # strong signal: entity match

        return score

    # ── Score each clip ──
    scored: list[tuple[dict, int]] = []
    for clip in clips:
        title = clip.get("title", "") or ""
        desc = clip.get("description", "") or ""
        content = title + " " + desc
        view_count = clip.get("view_count", 0) or 0

        domain_label, penalty, irr_hits = _classify_domain(title, desc)
        if domain_label == "irrelevant":
            scored.append((clip, -100))
            continue

        score = _score_overlap(title, desc)

        # Domain-relevant clips get a baseline boost
        if domain_label == "relevant":
            score += 5

        # Tutorial / course penalty
        if re.search(r'教程|从零开始|全套|合集|入门到精通|零基础|速成', content):
            score -= 5
        # Hashtag spam penalty
        hashtag_count = content.count('#')
        if hashtag_count > 10:
            score -= 5

        # Ad / commercial penalty
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
                score -= 30

        # Popularity boost
        if view_count > 100000:
            score += 5
        elif view_count > 10000:
            score += 3
        elif view_count > 1000:
            score += 1

        scored.append((clip, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored



_ENTITY_ALIASES: dict[str, list[str]] = {
    "月之暗面": ["Kimi", "K3", "Moonshot"],
    "DeepSeek": ["deepseek", "深度求索"],
    "OpenAI": ["openai", "GPT"],
    "Anthropic": ["anthropic", "Claude"],
    "百度": ["Baidu"],
    "腾讯": ["Tencent"],
    "阿里": ["Alibaba", "Qwen"],
    "华为": ["Huawei"],
    "小米": ["Xiaomi"],
    "微软": ["Microsoft", "Copilot"],
    "谷歌": ["Google", "Gemini"],
    "Meta": ["LLaMA"],
    "英伟达": ["NVIDIA"],
    "字节跳动": ["ByteDance"],
    "特斯拉": ["Tesla"],
    "魔法原子": ["MagicAtom"],
    "CrewAI": ["crewai"],
    "OpenHuman": ["openhuman"],
    "DuMate": ["dumate"],
    "OpenClaw": ["openclaw"],
    "AutoGPT": ["autogpt"],
    "Cursor": ["cursor"],
    "Devin": ["devin"],
    "Dify": ["dify"],
    "Coze": ["coze", "扣子"],
    "ComfyUI": ["comfyui"],
    "Ollama": ["ollama"],
    "HuggingFace": ["huggingface"],
    "GitHub": ["github"],
    "Gemini": ["gemini"],
    "Claude": ["claude"],
    "GPT": ["gpt", "chatgpt"],
    "LLaMA": ["llama"],
    "波士顿动力": ["Boston Dynamics", "Atlas", "Spot"],
}
_ENTITY_ALIASES_LOWER = {k.lower(): [a.lower() for a in v] for k, v in _ENTITY_ALIASES.items()}


def _get_entity_aliases(entity: str) -> list[str]:
    """Return all known aliases for an entity (company name + product names)."""
    aliases = [entity]
    for k, vals in _ENTITY_ALIASES_LOWER.items():
        if entity.lower() == k or entity.lower() in vals:
            aliases.extend(vals)
            if k not in aliases:
                aliases.append(k)
            break
    return list(set(aliases))


def _extract_main_entity(topic: str) -> str:
    """Extract the primary subject (company/product) from a news topic.

    First checks known entities (Chinese entities preferred, then English),
    then falls back to extracting the first Chinese or English proper noun.
    """
    clean = re.sub(r"^新闻[一二三四五六七八九\d]+[：:]\s*", "", topic)
    # Split known entities into Chinese and English
    cn_entities = sorted(
        [e for e in _ENTITY_ALIASES if re.search(r'[一-鿿]', e)],
        key=len, reverse=True
    )
    en_entities = sorted(
        [e for e in _ENTITY_ALIASES if not re.search(r'[一-鿿]', e)],
        key=len, reverse=True
    )
    # Check Chinese entities first (they're usually the main subject)
    for ent in cn_entities:
        if ent in clean:
            return ent
    # Then check English entities
    for ent in en_entities:
        if ent in clean:
            return ent
    # Fallback: extract first Chinese word (2+ chars)
    cn_match = re.search(r'[一-鿿]{2,}', clean)
    if cn_match:
        return cn_match.group()
    # Try English word (2+ chars)
    en_match = re.search(r'[A-Za-z]{2,}', clean)
    if en_match:
        return en_match.group()
    return clean[:4] if len(clean) >= 2 else clean
def _extract_search_terms(topic: str, fallback: str) -> str:
    """Extract high-quality search keywords from a news topic (domain-agnostic).

    Strategy (in order):
    1. Known entities from _ENTITY_ALIASES (company/product names)
    2. Domain context keywords that appear in the topic
    3. Chinese noun phrases (2+ chars, non-stopword)
    4. Fallback to domain broll_fallback
    """
    # Strip news prefix
    clean_topic = re.sub(r'^新闻[一二三四五六七八九\d]+[：:]\s*', '', topic)

    found = []
    remaining = clean_topic

    # Strategy 1: Known entities (longest match first)
    for entity in sorted(_ENTITY_ALIASES.keys(), key=len, reverse=True):
        if entity in remaining:
            found.append(entity)
            remaining = remaining.replace(entity, " ", 1)

    # Strategy 2: Domain context keywords that appear in topic
    dc = _get_domain_config()
    prompt_ctx = dc.get("prompt_context", "")
    domain_topics = set()
    for part in re.split(r'[、，,；;。.\s]+', prompt_ctx):
        part = part.strip()
        if part and len(part) >= 2:
            domain_topics.add(part)
    domain_topics.add(dc["label"])
    domain_topics.add(dc["display"])

    for dt in sorted(domain_topics, key=len, reverse=True):
        if dt in remaining and dt not in found:
            found.append(dt)
            remaining = remaining.replace(dt, " ", 1)

    if found:
        return " ".join(found[:4])

    # Strategy 3: Chinese noun phrases from topic
    cn_words = re.findall(r'[一-鿿]{2,}', clean_topic)
    cn_words = [w for w in cn_words if w not in _STOPWORDS and len(w) >= 2]
    if cn_words:
        return " ".join(cn_words[:3])

    # Strategy 4: First meaningful phrase
    short = clean_topic[:20]
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
    """Check if a Pexels clip is relevant to the news topic (domain-aware).

    Returns False for clearly irrelevant stock footage and clips whose
    title/description has zero overlap with the topic's core terms
    AND domain context keywords.
    """
    title = (clip.get("title", "") or "").lower()
    desc = (clip.get("description", "") or "").lower()
    combined = title + " " + desc

    # Build domain-aware noise set: always-irrelevant minus domain overrides
    dc = _get_domain_config()
    domain_noise = set(_PEXELS_NOISE)
    domain_overrides = DOMAIN_IRRELEVANT_OVERRIDES.get(dc["label"], set())
    domain_noise -= {o.lower() for o in domain_overrides}

    # Hard exclude: generic stock footage noise words
    for noise in domain_noise:
        if noise in combined:
            return False

    # Build search terms: topic words + domain context keywords
    # Extract 2+ char Chinese words from topic
    topic_cn = set(re.findall(r'[一-鿿]{2,}', topic))
    topic_terms = topic_cn - _STOPWORDS

    # Add domain context keywords for broader matching
    domain_ctx = _build_domain_context()
    all_terms = topic_terms | {t.lower() for t in domain_ctx if len(t) >= 2}

    if not all_terms:
        return True  # can't judge, let it through

    # Also check English entities from topic
    topic_en = set(re.findall(r'[A-Za-z]{2,}', topic))

    # Check if any term appears in clip title/description
    for term in all_terms:
        if term.lower() in combined:
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
    dc = _get_domain_config()
    broll_fb = dc["broll_fallback"]

    # Strip section prefix like "新闻一：", "新闻二："
    clean_topic = re.sub(r'^新闻[一二三四五六七八九\d]+[：:]\s*', '', topic)

    # Strategy 1: Core Chinese entities (2+ chars), sorted by length (longer = more specific)
    cn_words = re.findall(r'[一-鿿]{2,}', clean_topic)
    cn_words = [w for w in cn_words if w not in _STOPWORDS and len(w) >= 2]
    # Also extract English entities
    en_words = re.findall(r'[A-Za-z]{2,}', clean_topic)
    # Longer words first (more specific)
    cn_words.sort(key=len, reverse=True)
    kw_specific = cn_words[:3] if cn_words else [broll_fb]

    # Strategy 2: Add domain context prefix with extracted keywords
    display = dc["display"]
    if en_words:
        kw_agent = f"{display} {' '.join(kw_specific[:2])} {' '.join(en_words[:2])}"
    else:
        kw_agent = f"{display} {' '.join(kw_specific[:2])}"

    # Strategy 3: Broad domain fallback
    kw_broad = broll_fb

    return [kw_agent, kw_broad, broll_fb]


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
            "query": _get_domain_config()["pexels_query"],
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
                         background_video: str | None = None, title_text: str | None = None,
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

    if title_text is None:
        title_text = f"{_get_domain_config()['display']}早报"
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


def _generate_news_section_card(output_path: str, title_text: str,
                                 duration_sec: float = 1.5) -> None:
    """Short solid-colour card with centred headline — for per-news titles."""
    dur = max(duration_sec, 0.8)

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        _generate_solid_card(output_path, dur)
        return

    font_paths = [
        "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
    ]
    font = None
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, 48)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    overlay = Image.new("RGBA", (1920, 1080), (10, 10, 30, 0))
    draw = ImageDraw.Draw(overlay)

    # Top accent line
    draw.rectangle([0, 0, 1920, 4], fill=(58, 123, 213, 200))

    # Centred title
    bbox = draw.textbbox((0, 0), title_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (1920 - tw) // 2
    ty = (1080 - th) // 2
    draw.text((tx + 2, ty + 2), title_text, font=font, fill=(0, 0, 0, 80))
    draw.text((tx, ty), title_text, font=font, fill=(255, 255, 255, 240))

    # Decorative line below title
    line_y = ty + th + 16
    draw.rectangle([(1920 - 100) // 2, line_y, (1920 + 100) // 2, line_y + 2],
                   fill=(58, 123, 213, 180))

    overlay_path = str(Path(output_path).parent / f"_sec_{Path(output_path).stem}.png")
    overlay.save(overlay_path, "PNG")

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x0f0f23:s=1920x1080:r=30:d={dur:.2f}",
        "-i", overlay_path,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-filter_complex", "[0:v][1:v]overlay=0:0",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-c:a", "aac", "-b:a", "1k", "-pix_fmt", "yuv420p",
        "-t", f"{dur:.2f}", output_path,
    ]

    result = _sp.run(cmd, capture_output=True, text=True, timeout=30,
                     encoding="utf-8", errors="replace")
    try:
        Path(overlay_path).unlink()
    except Exception:
        pass

    if result.returncode != 0:
        logger.warning("News section card failed: %s", (result.stderr or "")[:300])
        _generate_solid_card(output_path, dur)


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
