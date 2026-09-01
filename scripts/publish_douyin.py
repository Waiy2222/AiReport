#!/usr/bin/env python
"""一键发布视频到抖音（命令行工具）

用法:
  # 基本发布
  python scripts/publish_douyin.py --video output/my_video_vertical.mp4

  # 带标题和标签
  python scripts/publish_douyin.py --video output/my_video_vertical.mp4 \
      --title "AI早报 2026-07-20" \
      --tags AI 人工智能 科技 AI早报 \
      --cover output/cover.jpg

  # 无头模式（后台运行，需确保已登录过）
  python scripts/publish_douyin.py --video output/my_video_vertical.mp4 --headless

首次使用:
  1. 确保已安装 Playwright: pip install playwright && playwright install chromium
  2. 运行脚本（不加 --headless），浏览器会打开抖音创作者登录页
  3. 用抖音APP扫描页面上的二维码
  4. 登录成功后 Cookie 会自动保存，下次无需重新扫码
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure module-d is on path
_MODULE_D = Path(__file__).parent.parent / "module-d"
if str(_MODULE_D) not in sys.path:
    sys.path.insert(0, str(_MODULE_D))

from platforms.douyin import publish_video

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="抖音视频自动发布",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/publish_douyin.py --video my_video_vertical.mp4
  python scripts/publish_douyin.py --video v.mp4 --title "AI早报" --tags AI 科技
  python scripts/publish_douyin.py --video v.mp4 --headless
        """,
    )
    parser.add_argument("--video", required=True, help="视频文件路径 (MP4, 建议竖屏 1080x1920)")
    parser.add_argument("--title", default="", help="视频标题 (≤55字)")
    parser.add_argument("--tags", nargs="*", default=["AI", "人工智能", "科技", "AI早报"],
                        help="话题标签 (不含#号)")
    parser.add_argument("--cover", default="", help="封面图片路径 (JPG/PNG)")
    parser.add_argument("--headless", action="store_true",
                        help="无头模式 (需已登录过，Cookie 有效)")
    args = parser.parse_args()

    result = asyncio.run(publish_video(
        video_path=args.video,
        title=args.title,
        tags=args.tags,
        cover_path=args.cover if args.cover else None,
        headless=args.headless,
    ))

    print()
    print("=" * 50)
    print(f"平台:  {result['platform']}")
    print(f"状态:  {result['status']}")
    if result.get("url"):
        print(f"链接:  {result['url']}")
    if result.get("error"):
        print(f"说明:  {result['error']}")
    print("=" * 50)

    sys.exit(0 if result["status"] == "success" else 1)
