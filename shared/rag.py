"""RAG (Retrieval-Augmented Generation) shared utilities.

Provides embedding generation and pgvector-based similarity search for
all modules that need to store or retrieve semantically similar content.

Usage::

    from shared.rag import generate_embedding, search_similar_items

    emb = await generate_embedding("GPT-5 released")
    similar = await search_similar_items(pool, emb, top_k=5)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# embedding provider configuration
# ---------------------------------------------------------------------------
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "deepseek")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMS", "1536"))

# DeepSeek-compatible embedding endpoint (OpenAI-compatible /v1/embeddings)
EMBEDDING_BASE_URL = os.getenv(
    "EMBEDDING_BASE_URL",
    os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
)
EMBEDDING_API_KEY = os.getenv(
    "EMBEDDING_API_KEY",
    os.getenv("DEEPSEEK_API_KEY", ""),
)


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


async def generate_embedding(text: str) -> list[float] | None:
    """Generate embedding vector for a single text.

    Returns a list of floats (length = EMBEDDING_DIMS), or None on failure.
    """
    embeddings = await generate_embeddings_batch([text])
    if embeddings is None:
        return None
    return embeddings[0] if embeddings else None


async def generate_embeddings_batch(
    texts: list[str],
    batch_size: int = 20,
) -> list[list[float]] | None:
    """Generate embeddings for multiple texts in batches.

    Returns a list of float-lists, parallel to *texts*, or None on failure.
    """
    if not texts:
        return []

    if not _has_api_key():
        logger.warning("No embedding API key configured — using mock zeros")
        return [[0.0] * EMBEDDING_DIMS for _ in texts]

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai package not installed — using mock zeros")
        return [[0.0] * EMBEDDING_DIMS for _ in texts]

    client = AsyncOpenAI(
        api_key=EMBEDDING_API_KEY,
        base_url=EMBEDDING_BASE_URL,
    )

    model = EMBEDDING_MODEL or _default_model()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            resp = await client.embeddings.create(
                model=model,
                input=batch,
            )
            for item in resp.data:
                all_embeddings.append(item.embedding)
        except Exception:
            logger.warning(
                "Embedding batch %d-%d failed, using zeros", i, i + len(batch)
            )
            for _ in batch:
                all_embeddings.append([0.0] * EMBEDDING_DIMS)

    return all_embeddings if all_embeddings else None


async def search_similar_items(
    pool: asyncpg.Pool,
    embedding: list[float],
    top_k: int = 5,
    *,
    exclude_id: str | None = None,
    source_filter: str | None = None,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    """Search raw_items by embedding cosine similarity.

    Returns up to *top_k* items ordered by similarity (descending).
    Each result is a dict with keys: id, title, url, source, similarity,
    ai_score, tags.

    Parameters
    ----------
    pool:
        asyncpg connection pool.
    embedding:
        Query embedding vector.
    top_k:
        Max results to return.
    exclude_id:
        Optional item UUID to exclude (e.g. the query item itself).
    source_filter:
        Optional source name to restrict search scope.
    min_score:
        Optional minimum ai_score filter.
    """
    embedding_str = f"[{','.join(str(x) for x in embedding)}]"

    query = """
        SELECT id, title, url, source, metadata,
               1 - (embedding <=> $1::vector) AS similarity
        FROM raw_items
        WHERE embedding IS NOT NULL
    """
    params: list[Any] = [embedding_str]
    idx = 2

    if exclude_id is not None:
        query += f" AND id != ${idx}::uuid"
        params.append(exclude_id)
        idx += 1

    if source_filter is not None:
        query += f" AND source = ${idx}"
        params.append(source_filter)
        idx += 1

    if min_score is not None:
        query += f" AND (metadata->>'ai_score')::numeric >= ${idx}"
        params.append(min_score)
        idx += 1

    query += f"""
        ORDER BY embedding <=> ${idx}::vector
        LIMIT ${idx + 1}
    """
    params.append(embedding_str)
    params.append(top_k)

    try:
        rows = await pool.fetch(query, *params)
    except Exception:
        logger.warning("pgvector similarity search failed", exc_info=True)
        return []

    results: list[dict[str, Any]] = []
    for r in rows:
        meta = r["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        results.append({
            "id": str(r["id"]),
            "title": r["title"],
            "url": r["url"],
            "source": r["source"],
            "similarity": round(float(r.get("similarity", 0)), 4),
            "ai_score": meta.get("ai_score") if isinstance(meta, dict) else None,
            "tags": meta.get("tags", []) if isinstance(meta, dict) else [],
        })

    return results


async def search_similar_with_behavior(
    pool: asyncpg.Pool,
    embedding: list[float],
    user_openid: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Search similar items, boosting those matching user's click history.

    Combines embedding similarity with user behavior signals for better
    relevance ranking.
    """
    # 1. get vector similarity results
    similar = await search_similar_items(pool, embedding, top_k=top_k * 2)

    if not similar:
        return []

    # 2. get user's frequently-clicked tags (last 14 days)
    user_tags = await _get_user_top_tags(pool, user_openid)

    # 3. boost items matching user's preferred tags
    for item in similar:
        item_tags = item.get("tags", [])
        boost = 0.0
        for t in set(item_tags):
            boost += user_tags.get(t, 0.0)
        item["behavior_boost"] = round(boost, 4)
        item["combined_score"] = round(item["similarity"] * (1.0 + boost * 0.3), 4)

    # 4. re-sort by combined score
    similar.sort(key=lambda x: x.get("combined_score", 0), reverse=True)
    return similar[:top_k]


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _has_api_key() -> bool:
    return bool(EMBEDDING_API_KEY)


def _default_model() -> str:
    """Select a sensible default embedding model based on provider."""
    provider = EMBEDDING_PROVIDER.lower()
    if provider == "openai":
        return "text-embedding-3-small"
    # DeepSeek / OpenAI-compatible
    return "text-embedding-3-small"


async def _get_user_top_tags(
    pool: asyncpg.Pool, openid: str, days: int = 14
) -> dict[str, float]:
    """Aggregate user's top-clicked tags into a weight map."""
    try:
        rows = await pool.fetch(
            """SELECT item_tags
               FROM user_behavior
               WHERE user_openid = $1
                 AND action IN ('click', 'share')
                 AND created_at > NOW() - make_interval(days => $2)""",
            openid,
            days,
        )
    except Exception:
        return {}

    tag_counts: dict[str, int] = {}
    total = 0
    for r in rows:
        tags = r.get("item_tags")
        if isinstance(tags, str):
            tags = json.loads(tags)
        if not isinstance(tags, list):
            continue
        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
            total += 1

    if total == 0:
        return {}

    return {t: c / total for t, c in tag_counts.items()}
