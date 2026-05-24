"""TDD: scrapers/reddit.py — Reddit 抓取测试"""
import uuid
from datetime import datetime, timezone

from scrapers.reddit import to_raw_items, SUBREDDITS


def test_subreddits_not_empty():
    """子版块列表至少包含已知的 AI 版块"""
    assert len(SUBREDDITS) >= 3
    assert "MachineLearning" in SUBREDDITS


def test_to_raw_items_maps_fields():
    """to_raw_items 正确映射 Reddit post 到 raw_items"""
    batch_id = uuid.uuid4()
    posts = [
        {
            "data": {
                "title": "DeepSeek-V4 beats GPT-5 on coding benchmarks",
                "url": "https://v.redd.it/abc123",
                "selftext": "Detailed comparison of the latest models...",
                "author": "ml_researcher",
                "created_utc": 1717171200.0,
                "ups": 520,
                "num_comments": 85,
                "permalink": "/r/MachineLearning/comments/abc123/dsv4/",
            }
        }
    ]
    result = to_raw_items(posts, batch_id)
    assert len(result) == 1
    r = result[0]
    assert r["source"] == "reddit"
    assert "DeepSeek" in r["title"]
    assert r["author"] == "ml_researcher"
    assert r["published_at"].tzinfo == timezone.utc
    assert r["metadata"]["ups"] == 520
    assert r["metadata"]["comments"] == 85
    assert "reddit.com" in r["url"]
    # v.redd.it 链接保存在 metadata.external_url
    assert "v.redd.it" in r["metadata"].get("external_url", "")


def test_to_raw_items_handles_external_url():
    """Reddit post 带外部链接时：主 url 为 Reddit 帖子，外部链接存 metadata"""
    batch_id = uuid.uuid4()
    posts = [
        {
            "data": {
                "title": "Check out this paper",
                "url": "https://arxiv.org/abs/2605.00001",
                "selftext": "Great paper...",
                "author": "user1",
                "created_utc": 1717171200.0,
                "ups": 100,
                "num_comments": 20,
                "permalink": "/r/MachineLearning/comments/xyz/paper/",
            }
        }
    ]
    result = to_raw_items(posts, batch_id)
    assert "reddit.com" in result[0]["url"]  # 主链接是 Reddit 帖子
    assert result[0]["metadata"]["external_url"] == "https://arxiv.org/abs/2605.00001"


def test_to_raw_items_empty():
    """空列表返回空"""
    assert to_raw_items([], uuid.uuid4()) == []


if __name__ == "__main__":
    import sys
    passed = 0
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
                passed += 1
            except AssertionError as e:
                print(f"  FAIL {name}: {e}")
                failed += 1
            except Exception as e:
                print(f"  ERROR {name}: {e}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed, {passed+failed} total")
    sys.exit(1 if failed else 0)
