"""抖音视频发布 — Playwright 浏览器自动化模拟人工操作

通过控制 Chromium 浏览器操作 creator.douyin.com 创作者平台完成:
  1. Cookie 登录态检查/恢复
  2. 上传视频文件
  3. 填写标题 + 话题标签
  4. 上传封面图
  5. 发布

首次使用需手动扫码登录，后续会自动复用 Cookie。

环境变量:
  DOUYIN_COOKIE_PATH  — Cookie 持久化文件路径 (默认: module-d/douyin_cookies.json)
  DOUYIN_HEADLESS     — 是否无头模式 (默认: false，首次登录必须可见)
  DOUYIN_AUTO_PUBLISH — 是否启用自动发布 (默认: false)
  DOUYIN_TIMEOUT_SEC  — 单步操作超时秒数 (默认: 120)
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)

# ── 配置 ──
_MODULE_DIR = Path(__file__).parent.parent
COOKIE_PATH = Path(os.getenv("DOUYIN_COOKIE_PATH", str(_MODULE_DIR / "douyin_cookies.json")))
HEADLESS = os.getenv("DOUYIN_HEADLESS", "false").lower() == "true"
TIMEOUT_SEC = int(os.getenv("DOUYIN_TIMEOUT_SEC", "120"))
AUTO_PUBLISH = os.getenv("DOUYIN_AUTO_PUBLISH", "false").lower() == "true"

# ── 抖音创作者平台 URL ──
CREATOR_URL = "https://creator.douyin.com/creator-micro/content/upload"
LOGIN_URL = "https://creator.douyin.com/"
DASHBOARD_URL = "https://creator.douyin.com/creator-micro/content/manage"


def _random_delay(min_s: float = 0.5, max_s: float = 2.0, reason: str = "") -> None:
    """Random delay to mimic human behavior and avoid bot detection."""
    delay = random.uniform(min_s, max_s)
    if reason:
        logger.debug("⏳ %.1fs — %s", delay, reason)


async def _human_type(page, selector: str, text: str) -> None:
    """Type text character by character with random delays (human-like)."""
    await page.click(selector)
    await asyncio.sleep(random.uniform(0.2, 0.5))
    await page.fill(selector, "")  # clear first
    for char in text:
        await page.type(selector, char, delay=random.randint(30, 120))
    await asyncio.sleep(random.uniform(0.3, 0.8))


async def check_login(page) -> bool:
    """Check if user is logged into Douyin Creator platform.

    Navigates to the creator dashboard and verifies the page doesn't
    redirect to login.  Returns True if already logged in.
    """
    try:
        await page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # Check if redirected to login page
        current_url = page.url
        if "login" in current_url.lower() or "passport" in current_url.lower():
            logger.info("⚠️ 未登录，需要扫码")
            return False

        # Look for indicators of being logged in (content management page loaded)
        page_title = await page.title()
        logger.info("当前页面标题: %s", page_title)

        if "创作者" in page_title or "内容管理" in page_title or "douyin" in page_title.lower():
            logger.info("✅ 已登录抖音创作者平台")
            return True

        # Fallback: check for login button presence
        login_btn = await page.query_selector('text=登录')
        if login_btn:
            logger.info("⚠️ 页面显示登录按钮，未登录")
            return False

        logger.info("✅ 未检测到登录页面，可能已登录")
        return True

    except Exception as e:
        logger.warning("登录检查异常: %s", e)
        return False


async def do_login(page) -> bool:
    """Open login page and wait for user to scan QR code.

    The user must manually scan the QR code with their Douyin app.
    This function waits up to 120 seconds for login to complete.
    """
    logger.info("📱 打开登录页面，请用抖音APP扫码...")
    logger.info("   (等待最多 120 秒)")

    try:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # The creator platform typically shows a QR code on the login page
        # Wait for the URL to change away from login (indicates successful login)
        for i in range(120):
            current_url = page.url
            page_title = await page.title()

            if "login" not in current_url.lower() and "passport" not in current_url.lower():
                logger.info("✅ 登录成功！(URL: %s)", current_url[:80])
                await asyncio.sleep(2)
                return True

            if i % 15 == 0 and i > 0:
                logger.info("   等待扫码中... (%ds/120s)", i)

            await asyncio.sleep(1)

        logger.error("❌ 登录超时（120秒），请重试")
        return False

    except Exception as e:
        logger.error("登录流程异常: %s", e)
        return False


async def ensure_login(context, page) -> bool:
    """Ensure browser context is logged into Douyin Creator.

    Returns True if logged in (either already or after QR scan).
    """
    # First try: check if already logged in
    if await check_login(page):
        return True

    # Not logged in — need QR scan
    logger.info("🔐 首次使用需要登录抖音创作者平台")

    if HEADLESS:
        logger.error(
            "❌ 无头模式下无法扫码登录！请设置 DOUYIN_HEADLESS=false 后重试"
        )
        return False

    login_ok = await do_login(page)
    if login_ok:
        # Save cookies for future runs
        await context.storage_state(path=str(COOKIE_PATH))
        logger.info("💾 Cookie 已保存到: %s", COOKIE_PATH)
        return True

    return False


async def upload_video(page, video_path: str) -> bool:
    """Upload a video file to the Douyin creator upload page.

    The upload is done via a hidden <input type="file"> element.
    Waits for the platform to finish processing the video.
    """
    abs_path = str(Path(video_path).resolve())
    if not Path(abs_path).exists():
        logger.error("❌ 视频文件不存在: %s", abs_path)
        return False

    file_size_mb = Path(abs_path).stat().st_size / (1024 * 1024)
    logger.info("📤 上传视频: %s (%.1f MB)", Path(abs_path).name, file_size_mb)

    try:
        # Navigate to upload page
        await page.goto(CREATOR_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # Close any popup dialogs that might appear
        try:
            close_btns = await page.query_selector_all('[class*="close"], [class*="dialog"] [class*="close"], .byte-modal-close')
            for btn in close_btns[:3]:
                try:
                    await btn.click()
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
        except Exception:
            pass

        # Find the file input (usually hidden) and set the video file
        # Douyin creator uses a standard file input for uploads
        file_input = await page.query_selector('input[type="file"]')
        if not file_input:
            # Alternative: look for upload area and click it first
            upload_area_selectors = [
                '[class*="upload"]',
                '[class*="Upload"]',
                '.container-selector-upload',
                'div:has-text("上传视频")',
                'div:has-text("发布视频")',
            ]
            for sel in upload_area_selectors:
                try:
                    area = await page.query_selector(sel)
                    if area:
                        await area.click()
                        await asyncio.sleep(1)
                        break
                except Exception:
                    continue
            file_input = await page.query_selector('input[type="file"]')

        if not file_input:
            logger.error("❌ 找不到上传入口 (input[type=file])")
            return False

        # Upload the file
        await file_input.set_input_files(abs_path)
        logger.info("   视频文件已选择，等待平台处理...")

        # Wait for upload + processing (video transcoding takes time)
        # Look for indicators that processing is complete
        max_wait = TIMEOUT_SEC
        for i in range(max_wait):
            await asyncio.sleep(1)

            # Check for success indicators
            success_indicators = await page.query_selector_all(
                '[class*="success"], [class*="upload-success"], [class*="video-preview"], '
                'video, [class*="cover"], [class*="thumbnail"]'
            )
            if success_indicators:
                logger.info("   ✅ 视频处理完成 (%ds)", i + 1)
                await asyncio.sleep(2)  # extra wait for UI to stabilize
                return True

            # Check for error indicators
            error_indicators = await page.query_selector_all(
                '[class*="error"], [class*="upload-error"], [class*="upload-fail"]'
            )
            if error_indicators:
                for ei in error_indicators[:3]:
                    try:
                        text = await ei.inner_text()
                        logger.error("   上传错误: %s", text[:200])
                    except Exception:
                        pass
                return False

            if i % 10 == 0 and i > 0:
                logger.info("   等待中... (%ds/%ds)", i, max_wait)

        logger.warning("⚠️ 视频处理等待超时，继续尝试...")
        return True  # Try to continue anyway

    except Exception as e:
        logger.error("上传视频异常: %s", e)
        return False


async def fill_metadata(page, title: str, tags: list[str] | None = None,
                        cover_path: str | None = None) -> bool:
    """Fill in video title, tags, and upload cover image.

    Args:
        page: Playwright page on the upload/edit page.
        title: Video title (max ~55 chars for Douyin).
        tags: Optional list of hashtags (without # prefix).
        cover_path: Optional path to cover/thumbnail image.
    """
    try:
        await asyncio.sleep(2)

        # ── Title ──
        # Douyin title limit: ~55 characters
        douyin_title = title[:55] if len(title) > 55 else title
        logger.info("📝 填写标题: %s", douyin_title)

        # Try various selectors for the title input
        title_selectors = [
            '[placeholder*="标题"]',
            '[placeholder*="作品标题"]',
            '[class*="title"] input',
            '[class*="title"] textarea',
            'input[class*="title"]',
            '[class*="desc"] input',
            '[class*="desc"] textarea',
            'textarea[placeholder*="添加"]',
        ]
        title_input = None
        for sel in title_selectors:
            try:
                title_input = await page.query_selector(sel)
                if title_input:
                    break
            except Exception:
                continue

        if title_input:
            await _human_type(page, sel, douyin_title)
            logger.info("   标题已填写")
        else:
            logger.warning("⚠️ 找不到标题输入框，跳过标题填写")

        await asyncio.sleep(1)

        # ── Tags / Hashtags ──
        if tags:
            logger.info("🏷️ 添加话题: %s", " ".join(f"#{t}" for t in tags))
            for tag in tags:
                # Try to find tag input and add
                tag_done = False

                # Method 1: Look for dedicated tag input
                tag_selectors = [
                    '[placeholder*="话题"]',
                    '[placeholder*="标签"]',
                    '[class*="tag"] input',
                ]
                for tsel in tag_selectors:
                    try:
                        tag_input = await page.query_selector(tsel)
                        if tag_input:
                            await tag_input.click()
                            await asyncio.sleep(0.3)
                            await tag_input.fill(f"#{tag}")
                            await asyncio.sleep(0.5)
                            await page.keyboard.press("Enter")
                            await asyncio.sleep(0.5)
                            tag_done = True
                            break
                    except Exception:
                        continue

                # Method 2: Type in title area and hope it picks up
                if not tag_done and title_input:
                    try:
                        await title_input.click()
                        await asyncio.sleep(0.2)
                        await title_input.press("End")
                        await title_input.type(f" #{tag}", delay=50)
                        await asyncio.sleep(0.3)
                        tag_done = True
                    except Exception:
                        pass

                if not tag_done:
                    logger.debug("   标签 '%s' 添加失败，跳过", tag)
                await asyncio.sleep(random.uniform(0.3, 0.8))

        # ── Cover image ──
        if cover_path and Path(cover_path).exists():
            logger.info("🖼️ 上传封面: %s", Path(cover_path).name)
            try:
                # Look for cover upload input
                cover_input_selectors = [
                    '[class*="cover"] input[type="file"]',
                    'input[accept*="image"]',
                ]
                cover_input = None
                for csel in cover_input_selectors:
                    try:
                        cover_input = await page.query_selector(csel)
                        if cover_input:
                            break
                    except Exception:
                        continue

                if cover_input:
                    await cover_input.set_input_files(str(Path(cover_path).resolve()))
                    await asyncio.sleep(2)
                    logger.info("   封面上传完成")
                else:
                    logger.warning("⚠️ 找不到封面上传入口")
            except Exception as e:
                logger.warning("封面上传失败: %s", e)

        return True

    except Exception as e:
        logger.error("填写元数据异常: %s", e)
        return False


async def click_publish(page) -> bool:
    """Click the publish button and wait for confirmation.

    Returns True if publish succeeded.
    """
    logger.info("🚀 准备发布...")
    await asyncio.sleep(2)

    try:
        # Try various publish button selectors
        publish_selectors = [
            'button:has-text("发布")',
            'button:has-text("投稿")',
            '[class*="publish"] button',
            '[class*="submit"] button',
            '.publish-btn',
            '.submit-btn',
        ]

        clicked = False
        for sel in publish_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    is_disabled = await btn.get_attribute("disabled")
                    if is_disabled:
                        logger.debug("   发布按钮已禁用 (可能是视频还在处理)")
                        continue
                    await btn.click()
                    clicked = True
                    logger.info("   已点击发布按钮 (%s)", sel)
                    break
            except Exception:
                continue

        if not clicked:
            logger.error("❌ 找不到可用的发布按钮")
            # Take a screenshot for debugging
            try:
                debug_path = str(_MODULE_DIR / "douyin_debug_screenshot.png")
                await page.screenshot(path=debug_path)
                logger.info("📸 调试截图保存: %s", debug_path)
            except Exception:
                pass
            return False

        # Wait for publish result
        await asyncio.sleep(3)

        # Check for success indicators
        success_selectors = [
            'text=发布成功',
            'text=投稿成功',
            '[class*="success"]',
            'text=作品审核中',
            'text=审核中',
        ]
        for ssel in success_selectors:
            try:
                el = await page.query_selector(ssel)
                if el:
                    text = await el.inner_text()
                    logger.info("✅ %s", text[:100])
                    return True
            except Exception:
                continue

        # Check URL change (often redirects to manage page after publish)
        current_url = page.url
        if "manage" in current_url or "content" in current_url:
            logger.info("✅ 已跳转到内容管理页，发布成功")
            return True

        # No clear indicator, but if no error, assume success
        logger.info("✅ 未检测到错误，视作发布成功")
        return True

    except Exception as e:
        logger.error("发布操作异常: %s", e)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

async def publish_video(
    video_path: str,
    title: str = "",
    tags: list[str] | None = None,
    cover_path: str | None = None,
    *,
    headless: bool | None = None,
) -> dict:
    """Publish a video to Douyin via browser automation.

    This is the main entry point.  It launches a Chromium browser,
    ensures login, uploads the video, fills metadata, and publishes.

    Args:
        video_path: Path to the MP4 video file.
        title: Video title (max ~55 chars for Douyin).
        tags: Optional list of hashtags (without # prefix).
        cover_path: Optional cover/thumbnail image path.
        headless: Override headless mode (None = use env var).

    Returns:
        dict with keys: platform, status, url, error
    """
    if not Path(video_path).exists():
        return {
            "platform": "douyin",
            "status": "failed",
            "url": None,
            "error": f"video file not found: {video_path}",
        }

    if not title:
        title = f"AI早报 {Path(video_path).stem[:30]}"

    if tags is None:
        tags = ["AI", "人工智能", "科技", "AI早报"]

    use_headless = headless if headless is not None else HEADLESS

    logger.info("=" * 60)
    logger.info("🎬 抖音发布开始")
    logger.info("   视频: %s", video_path)
    logger.info("   标题: %s", title)
    logger.info("   标签: %s", tags)
    logger.info("   封面: %s", cover_path or "(无)")
    logger.info("   无头: %s", use_headless)
    logger.info("=" * 60)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "platform": "douyin",
            "status": "failed",
            "url": None,
            "error": "playwright not installed — run: pip install playwright && playwright install chromium",
        }

    try:
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(
                headless=use_headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            # Create context with persistent storage
            context_kwargs = {
                "viewport": {"width": 1280, "height": 900},
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "locale": "zh-CN",
            }

            # Load saved cookies if available
            if COOKIE_PATH.exists():
                try:
                    context_kwargs["storage_state"] = str(COOKIE_PATH)
                    logger.info("📂 加载已保存的 Cookie: %s", COOKIE_PATH)
                except Exception as e:
                    logger.warning("Cookie 加载失败: %s，将重新登录", e)

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            # Hide automation traces
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            """)

            try:
                # Step 1: Login
                if not await ensure_login(context, page):
                    return {
                        "platform": "douyin",
                        "status": "failed",
                        "url": None,
                        "error": "login failed — 请在非无头模式下重新运行并扫码",
                    }

                # Save cookies after login check
                await context.storage_state(path=str(COOKIE_PATH))

                # Step 2: Upload video
                if not await upload_video(page, video_path):
                    return {
                        "platform": "douyin",
                        "status": "failed",
                        "url": None,
                        "error": "video upload failed",
                    }

                # Step 3: Fill metadata
                if not await fill_metadata(page, title, tags, cover_path):
                    logger.warning("⚠️ 元数据填写部分失败，继续发布...")

                # Step 4: Publish
                if not await click_publish(page):
                    return {
                        "platform": "douyin",
                        "status": "failed",
                        "url": None,
                        "error": "publish button click failed — 请检查调试截图 douyin_debug_screenshot.png",
                    }

                # Save cookies again (refresh expiry)
                await context.storage_state(path=str(COOKIE_PATH))
                logger.info("💾 Cookie 已更新")

                return {
                    "platform": "douyin",
                    "status": "success",
                    "url": "https://creator.douyin.com/creator-micro/content/manage",
                    "error": None,
                }

            finally:
                await browser.close()

    except Exception as e:
        logger.exception("抖音发布异常")
        return {
            "platform": "douyin",
            "status": "failed",
            "url": None,
            "error": str(e),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Module-D compatible interface
# ═══════════════════════════════════════════════════════════════════════════════

async def publish(pool, briefing_id: UUID, briefing: dict) -> dict:
    """Module-D compatible publish interface.

    Expected keys in briefing dict:
      - video_path: str (required) — path to the MP4 video file
      - cover_path: str (optional) — path to cover image
      - title: str (optional) — video title, auto-generated if missing
      - tags: list[str] (optional) — hashtags list

    If video_path is not provided, returns 'skipped'.
    """
    if not AUTO_PUBLISH:
        logger.info("[douyin] DOUYIN_AUTO_PUBLISH=false, 跳过")
        return {
            "platform": "douyin",
            "status": "skipped",
            "url": None,
            "error": "DOUYIN_AUTO_PUBLISH not enabled",
        }

    video_path = briefing.get("video_path", "")
    if not video_path:
        logger.info("[douyin] 未提供 video_path，跳过")
        return {
            "platform": "douyin",
            "status": "skipped",
            "url": None,
            "error": "no video_path in briefing",
        }

    title = briefing.get("title", "")
    if not title:
        date_str = briefing.get("date", "")
        title = f"AI早报 {date_str}" if date_str else "AI早报"

    tags = briefing.get("tags", ["AI", "人工智能", "科技", "AI早报"])
    cover_path = briefing.get("cover_path", "")

    return await publish_video(
        video_path=video_path,
        title=title,
        tags=tags,
        cover_path=cover_path if cover_path else None,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [douyin] %(message)s",
    )

    parser = argparse.ArgumentParser(description="抖音视频自动发布")
    parser.add_argument("--video", required=True, help="视频文件路径 (MP4)")
    parser.add_argument("--title", default="", help="视频标题 (≤55字)")
    parser.add_argument("--tags", nargs="*", default=["AI", "人工智能", "科技"], help="话题标签")
    parser.add_argument("--cover", default="", help="封面图片路径")
    parser.add_argument("--headless", action="store_true", help="无头模式运行")
    args = parser.parse_args()

    result = asyncio.run(publish_video(
        video_path=args.video,
        title=args.title,
        tags=args.tags,
        cover_path=args.cover if args.cover else None,
        headless=args.headless if args.headless else None,
    ))

    print()
    print("=" * 50)
    print(f"平台: {result['platform']}")
    print(f"状态: {result['status']}")
    if result.get("url"):
        print(f"链接: {result['url']}")
    if result.get("error"):
        print(f"错误: {result['error']}")
    print("=" * 50)
    sys.exit(0 if result["status"] == "success" else 1)
