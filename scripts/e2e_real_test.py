"""E2E real test: scrape live news → DeepSeek AI analysis → HTML briefing page.

No seed data. Every step driven by real scraping and AI.

Usage:
    python scripts/e2e_real_test.py          # morning briefing (default)
    python scripts/e2e_real_test.py evening  # evening briefing
    python scripts/e2e_real_test.py morning --skip-scrape  # reuse existing raw_items
"""
import asyncio
import json
import os
import sys
import uuid
import webbrowser
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

# ── Path setup ───────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "module-a"))
sys.path.insert(0, str(PROJECT_ROOT / "module-b"))
sys.path.insert(0, str(PROJECT_ROOT / "module-d"))

# ── Load .env manually ───────────────────────────────────────────────────────
_ENV_PATH = PROJECT_ROOT / ".env"
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

import asyncpg

# ── Constants ────────────────────────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT / "module-d" / "dry-run-output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PG_DSN = (
    f"postgresql://{os.getenv('POSTGRES_USER','postgres')}:"
    f"{os.getenv('POSTGRES_PASSWORD','postgres')}@"
    f"{os.getenv('POSTGRES_HOST','localhost')}:"
    f"{os.getenv('POSTGRES_PORT','5432')}/"
    f"{os.getenv('POSTGRES_DB','ai_news')}"
)

# Ensure clean UTF-8 output on Windows
os.environ.setdefault("PGCLIENTENCODING", "UTF8")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1: Scrape real news
# ═══════════════════════════════════════════════════════════════════════════════

async def phase_scrape(pool, batch_id: str, hours_back: int = 72) -> int:
    """Run all scrapers, return total count of new items."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    print(f"\n{'='*60}")
    print(f"  Phase 1: Scraping real news (since {since.strftime('%Y-%m-%d %H:%M')} UTC)")
    print(f"{'='*60}")

    from scrapers import github, hackernews, rss

    total = 0
    batch_uuid = uuid.UUID(batch_id)

    # GitHub
    print("\n[1/3] GitHub trending AI repos...")
    try:
        n = await github.fetch(pool, since, batch_uuid)
        print(f"      -> {n} new repos inserted")
        total += n
    except Exception as e:
        print(f"      -> FAILED: {e}")

    # HackerNews
    print("\n[2/3] HackerNews AI stories...")
    try:
        n = await hackernews.fetch(pool, since, batch_uuid)
        print(f"      -> {n} new stories inserted")
        total += n
    except Exception as e:
        print(f"      -> FAILED: {e}")

    # RSS
    print("\n[3/3] RSS feeds...")
    try:
        n = await rss.fetch(pool, since, batch_uuid)
        print(f"      -> {n} new items inserted")
        total += n
    except Exception as e:
        print(f"      -> FAILED: {e}")

    print(f"\n  Phase 1 done: {total} total new raw_items\n")
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2: AI processing (DeepSeek-powered 7-step pipeline)
# ═══════════════════════════════════════════════════════════════════════════════

async def phase_ai_process(pool, batch_id: str, briefing_type: str) -> dict:
    """Run Module B's 7-step pipeline with DeepSeek API."""
    from ai.pipeline import run_pipeline

    today = date.today()
    print(f"{'='*60}")
    print(f"  Phase 2: AI Processing ({briefing_type} briefing for {today})")
    print(f"  Model: {os.getenv('DEEPSEEK_BASE_URL','')} | deepseek-chat")
    print(f"{'='*60}")

    result = await run_pipeline(pool, batch_id, briefing_type, today)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3: Generate viewable HTML page
# ═══════════════════════════════════════════════════════════════════════════════

async def phase_render_html(pool, briefing_id: str) -> Path:
    """Fetch briefing from DB and render as HTML."""
    from platforms.weixin import render_briefing_html

    print(f"{'='*60}")
    print(f"  Phase 3: Rendering HTML page")
    print(f"{'='*60}")

    row = await pool.fetchrow(
        """SELECT id, type, date, tl_dr, sections, key_takeaways, raw_stats
           FROM briefings WHERE id = $1::uuid""",
        briefing_id,
    )
    if not row:
        raise RuntimeError(f"Briefing {briefing_id} not found in DB")

    # Convert to dict for the render function
    briefing = {
        "type": row["type"],
        "date": str(row["date"]),
        "tl_dr": row["tl_dr"] if isinstance(row["tl_dr"], list) else json.loads(row["tl_dr"]) if isinstance(row["tl_dr"], str) else [],
        "sections": row["sections"] if isinstance(row["sections"], list) else json.loads(row["sections"]) if isinstance(row["sections"], str) else [],
        "key_takeaways": row["key_takeaways"] if isinstance(row["key_takeaways"], list) else json.loads(row["key_takeaways"]) if isinstance(row["key_takeaways"], str) else [],
    }
    raw_stats = row["raw_stats"]
    if isinstance(raw_stats, str):
        raw_stats = json.loads(raw_stats)

    print(f"  Type: {briefing['type']}")
    print(f"  Date: {briefing['date']}")
    print(f"  TL;DR: {len(briefing['tl_dr'])} items")
    print(f"  Sections: {len(briefing['sections'])} categories")
    print(f"  Key Takeaways: {len(briefing['key_takeaways'])} points")
    print(f"  Stats: {raw_stats}")

    # ── Build a standalone HTML page ────────────────────────────────────
    body_html = render_briefing_html(briefing)

    safe_date = briefing["date"].replace(":", "-")
    type_label = "早报" if briefing["type"] == "morning" else "晚报"

    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI资讯{type_label} | {briefing['date']}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #f0f2f5;
    display: flex;
    justify-content: center;
    padding: 20px;
  }}
  .page {{
    max-width: 680px;
    width: 100%;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 2px 20px rgba(0,0,0,0.08);
    overflow: hidden;
  }}
  .badge {{
    text-align: center;
    padding: 12px;
    background: linear-gradient(135deg, #07c160, #06ad56);
    color: #fff;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.1em;
  }}
</style>
</head>
<body>
<div class="page">
  <div class="badge">🤖 由 DeepSeek AI 自动生成 · 数据来自真实新闻源</div>
  {body_html}
  <div class="badge" style="margin-top:0;background:#f4fbf7;color:#8a9a91;font-weight:400;">
    Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')} · AI News Briefing Agent
  </div>
</div>
</body>
</html>"""

    filename = f"briefing_{briefing['type']}_{safe_date}.html"
    filepath = OUTPUT_DIR / filename
    filepath.write_text(full_html, encoding="utf-8")
    print(f"\n  HTML saved: {filepath}")

    return filepath


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    briefing_type = "morning"
    skip_scrape = False

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if args:
        if args[0] in ("morning", "evening"):
            briefing_type = args[0]
        else:
            print(f"Usage: python {__file__} [morning|evening] [--skip-scrape]")
            sys.exit(1)
    if "--skip-scrape" in flags:
        skip_scrape = True

    print(f"\n{'#'*60}")
    print(f"  AI News Briefing — E2E Real Test")
    print(f"  Type: {briefing_type} | DeepSeek API | Real scraping")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")

    # ── Check API key ───────────────────────────────────────────────────
    if not os.getenv("DEEPSEEK_API_KEY", "").startswith("sk-"):
        print("\n  ERROR: DEEPSEEK_API_KEY not set. Check your .env file.")
        sys.exit(1)
    print(f"  API Key: {os.getenv('DEEPSEEK_API_KEY')[:12]}...")

    # ── Connect to DB ───────────────────────────────────────────────────
    print(f"\n  Connecting to PostgreSQL: {PG_DSN}")
    pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=4)

    try:
        # Register JSON codec
        await pool.execute("SELECT 1")

        batch_id = str(uuid.uuid4())
        print(f"  Batch ID: {batch_id}")

        # ── Phase 1: Scrape ──────────────────────────────────────────
        if not skip_scrape:
            # Clear old seed data first
            print("\n  Clearing old seed data...")
            await pool.execute("DELETE FROM publish_log")
            await pool.execute("DELETE FROM raw_items")
            await pool.execute("DELETE FROM briefings")
            print("  Old data cleared.")

            total = await phase_scrape(pool, batch_id)
            if total == 0:
                print("  WARNING: No items scraped. Check network / API rate limits.")
                print("  The pipeline will still run but may produce empty results.")
        else:
            # Use most recent batch
            row = await pool.fetchrow("SELECT batch_id FROM raw_items ORDER BY fetched_at DESC LIMIT 1")
            if row:
                batch_id = str(row["batch_id"])
                print(f"  Reusing existing batch: {batch_id}")
                total = await pool.fetchval("SELECT count(*) FROM raw_items WHERE batch_id = $1", batch_id)
                print(f"  {total} raw_items in batch")
            else:
                print("  ERROR: No existing raw_items and --skip-scrape was set.")
                return

        # ── Phase 2: AI Process ───────────────────────────────────────
        result = await phase_ai_process(pool, batch_id, briefing_type)
        print(f"\n  Phase 2 result:")
        print(f"    Status: {result.get('status')}")
        print(f"    Briefing ID: {result.get('briefing_id')}")
        print(f"    Stats: {result.get('stats')}")

        stats = result.get("stats", {})
        if stats.get("fetched", 0) == 0:
            print("\n  Cannot generate briefing: 0 items scraped.")
            print("  This may be due to:")
            print("    - GitHub API rate limit (unauthenticated: 10 req/min)")
            print("    - No AI-related stories on HackerNews in the time window")
            print("    - RSS feeds temporarily unavailable (hnrss.org returned 502)")
            print("\n  Try running again with a wider time window or later.")
            return

        briefing_id = result.get("briefing_id")
        if not briefing_id or result.get("status") != "ok":
            print("\n  ERROR: AI processing failed. See stats above.")
            return

        # ── Phase 3: Render HTML ──────────────────────────────────────
        filepath = await phase_render_html(pool, briefing_id)

        # ── Open in browser ───────────────────────────────────────────
        print(f"\n{'='*60}")
        print(f"  Opening in browser...")
        print(f"{'='*60}")
        webbrowser.open(f"file:///{filepath.as_posix()}")

        print(f"\n{'='*60}")
        print(f"  DONE! Briefing page opened.")
        print(f"  File: {filepath}")
        print(f"{'='*60}\n")

    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
