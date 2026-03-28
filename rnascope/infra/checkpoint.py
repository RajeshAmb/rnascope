"""Checkpoint and recovery system using Redis + S3."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis

from rnascope.config import settings
from rnascope.infra.aws import s3_download_json, s3_upload_json
from rnascope.models.schemas import Checkpoint

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _checkpoint_key(job_id: str, step: str, sample_id: str | None = None) -> str:
    parts = ["rnascope", "checkpoint", job_id, step]
    if sample_id:
        parts.append(sample_id)
    return ":".join(parts)


def _s3_checkpoint_key(job_id: str, step: str, sample_id: str | None = None) -> str:
    parts = [job_id, "checkpoints", step]
    if sample_id:
        parts.append(sample_id)
    return "/".join(parts) + ".json"


def save_checkpoint(
    job_id: str,
    step: str,
    state: dict[str, Any],
    sample_id: str | None = None,
    metrics: dict[str, Any] | None = None,
    output_s3_path: str = "",
) -> str:
    """Save checkpoint to both Redis (fast lookup) and S3 (durability)."""
    cp = Checkpoint(
        job_id=job_id,
        step=step,
        sample_id=sample_id,
        output_s3_path=output_s3_path,
        metrics=metrics or {},
        state=state,
    )
    cp_dict = cp.model_dump()

    # Redis (TTL: 7 days)
    r = _get_redis()
    key = _checkpoint_key(job_id, step, sample_id)
    r.setex(key, 7 * 86400, json.dumps(cp_dict, default=str))

    # S3 (permanent)
    s3_key = _s3_checkpoint_key(job_id, step, sample_id)
    s3_path = s3_upload_json(settings.s3_bucket_results, s3_key, cp_dict)

    logger.info("Checkpoint saved: %s (Redis + S3)", key)
    return s3_path


def restore_checkpoint(
    job_id: str, step: str, sample_id: str | None = None
) -> dict[str, Any] | None:
    """Restore checkpoint from Redis first, fallback to S3."""
    r = _get_redis()
    key = _checkpoint_key(job_id, step, sample_id)
    data = r.get(key)
    if data:
        logger.info("Checkpoint restored from Redis: %s", key)
        return json.loads(data)

    # Fallback to S3
    try:
        s3_key = _s3_checkpoint_key(job_id, step, sample_id)
        data = s3_download_json(settings.s3_bucket_results, s3_key)
        logger.info("Checkpoint restored from S3: %s", s3_key)
        return data
    except Exception:
        logger.info("No checkpoint found for %s", key)
        return None


def has_checkpoint(job_id: str, step: str, sample_id: str | None = None) -> bool:
    return restore_checkpoint(job_id, step, sample_id) is not None


def clear_checkpoints(job_id: str) -> int:
    """Delete all Redis checkpoints for a job."""
    r = _get_redis()
    pattern = f"rnascope:checkpoint:{job_id}:*"
    keys = list(r.scan_iter(match=pattern))
    if keys:
        r.delete(*keys)
    logger.info("Cleared %d checkpoints for job %s", len(keys), job_id)
    return len(keys)


# ---------------------------------------------------------------------------
# Job state (lightweight job status in Redis)
# ---------------------------------------------------------------------------

def save_job_state(job_id: str, state: dict[str, Any]) -> None:
    r = _get_redis()
    r.setex(f"rnascope:job:{job_id}", 30 * 86400, json.dumps(state, default=str))


def get_job_state(job_id: str) -> dict[str, Any] | None:
    r = _get_redis()
    data = r.get(f"rnascope:job:{job_id}")
    return json.loads(data) if data else None


def update_job_step(job_id: str, step: str, status: str = "running") -> None:
    state = get_job_state(job_id) or {}
    state["current_step"] = step
    state["step_status"] = status
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    if status == "completed":
        completed = state.get("steps_completed", [])
        if step not in completed:
            completed.append(step)
        state["steps_completed"] = completed
    save_job_state(job_id, state)
