"""Local video news briefing — thin wrapper around pipeline.py.

Previously had a full copy of the pipeline logic (~1900 lines).  Now
delegates to the unified pipeline in pipeline.py so both the HTTP API
and local runs share the same code path.

Usage: python run_local.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "module-a"))

# Load .env from project root AND .env.local from module-f
for _env_path in [
    Path(__file__).parent.parent / ".env",
    Path(__file__).parent / ".env.local",
]:
    if _env_path.exists():
        with open(_env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip()
                if not os.getenv(key):
                    os.environ[key] = val

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("run_local")

os.environ.setdefault("VIDEO_OUTPUT_DIR", str(Path(__file__).parent / "output"))
os.environ.setdefault("VIDEO_DOWNLOAD_DIR", str(Path(__file__).parent / "downloads"))
os.environ.setdefault("VIDEO_SEARCH_SOURCES", "youtube,bilibili,pexels,archive")

from pipeline import VideoPipeline


async def main():
    domain = os.getenv("VIDEO_DOMAIN", "AI")
    # Support keyword via CLI arg or VIDEO_KEYWORD env var
    keyword = sys.argv[1].strip() if len(sys.argv) > 1 else os.getenv("VIDEO_KEYWORD")
    _MAP = {"AI": "AI智能体", "体育": "体育", "芯片": "芯片", "机器人": "机器人", "医疗": "医疗", "自动驾驶": "自动驾驶", "融资": "科技创投"}
    domain_display = keyword or _MAP.get(domain) or os.getenv("VIDEO_DOMAIN_DISPLAY") or domain
    logger.info("=== %s新闻早报生成 (统一流水线) ===", domain_display)

    pipeline = VideoPipeline()
    today = date.today()
    vtype = "ai_agent_weekly"
    video_id = str(uuid.uuid4())

    try:
        output_path = await pipeline.run_full_pipeline(video_id, vtype, today, keyword=keyword)
        size_mb = Path(output_path).stat().st_size / (1024 * 1024) if Path(output_path).exists() else 0
        logger.info("=== 完成 ===")
        logger.info(f"输出: {output_path}")
        logger.info(f"大小: {size_mb:.1f} MB")
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        raise


if __name__ == "__main__":
    asyncio.run(main())
