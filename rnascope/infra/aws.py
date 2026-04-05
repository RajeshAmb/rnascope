"""AWS infrastructure: S3 operations, Batch job management, compute selection."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

from rnascope.config import settings
from rnascope.models.schemas import ComputeEstimate, ComputeTier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

_s3 = None


def _get_s3():
    global _s3
    if _s3 is None:
        from botocore.config import Config
        _s3 = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual"},
                tcp_keepalive=True,
                retries={"max_attempts": 10, "mode": "adaptive"},
                connect_timeout=30,
                read_timeout=300,
            ),
        )
    return _s3


def s3_list_objects(bucket: str, prefix: str) -> list[dict]:
    s3 = _get_s3()
    objects: list[dict] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            objects.append({"key": obj["Key"], "size": obj["Size"], "etag": obj["ETag"]})
    return objects


def s3_head(bucket: str, key: str) -> dict:
    return _get_s3().head_object(Bucket=bucket, Key=key)


def s3_upload_json(bucket: str, key: str, data: Any) -> str:
    body = json.dumps(data, default=str, indent=2)
    _get_s3().put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    return f"s3://{bucket}/{key}"


def s3_download_json(bucket: str, key: str) -> Any:
    resp = _get_s3().get_object(Bucket=bucket, Key=key)
    return json.loads(resp["Body"].read())


def s3_delete_prefix(bucket: str, prefix: str) -> int:
    """Delete all objects under a prefix. Returns number of objects deleted."""
    s3 = _get_s3()
    objects = s3_list_objects(bucket, prefix)
    if not objects:
        return 0
    # S3 delete_objects accepts max 1000 keys per call
    deleted = 0
    for i in range(0, len(objects), 1000):
        batch = objects[i : i + 1000]
        s3.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": o["key"]} for o in batch], "Quiet": True},
        )
        deleted += len(batch)
    logger.info("Deleted %d objects from s3://%s/%s", deleted, bucket, prefix)
    return deleted


def s3_get_dataset_size_gb(bucket: str, prefix: str) -> float:
    objects = s3_list_objects(bucket, prefix)
    total_bytes = sum(o["size"] for o in objects)
    return round(total_bytes / (1024**3), 2)


def s3_multipart_upload(bucket: str, key: str, file_path: str, chunk_mb: int = 100):
    """Upload a large file using S3 multipart upload with MD5 verification."""
    s3 = _get_s3()
    chunk_size = chunk_mb * 1024 * 1024
    mpu = s3.create_multipart_upload(Bucket=bucket, Key=key)
    upload_id = mpu["UploadId"]
    parts: list[dict] = []

    try:
        with open(file_path, "rb") as f:
            part_number = 1
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                md5 = hashlib.md5(chunk).hexdigest()
                resp = s3.upload_part(
                    Bucket=bucket,
                    Key=key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk,
                    ContentMD5=_b64_md5(chunk),
                )
                parts.append({"PartNumber": part_number, "ETag": resp["ETag"]})
                logger.info("Uploaded part %d (md5=%s)", part_number, md5)
                part_number += 1

        s3.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
    except Exception:
        s3.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
        raise

    return f"s3://{bucket}/{key}"


def _b64_md5(data: bytes) -> str:
    import base64
    return base64.b64encode(hashlib.md5(data).digest()).decode()


# ---------------------------------------------------------------------------
# Compute selection
# ---------------------------------------------------------------------------

TIER_SPECS = {
    ComputeTier.SMALL: {"vcpu": 4, "ram_gb": 32, "cost_per_hour": 0.252},
    ComputeTier.MEDIUM: {"vcpu": 32, "ram_gb": 256, "cost_per_hour": 2.016},
    ComputeTier.LARGE: {"vcpu": 0, "ram_gb": 0, "cost_per_hour": 0.0},  # Batch: per-job pricing
}


def select_compute_tier(dataset_size_gb: float, n_samples: int) -> ComputeEstimate:
    if dataset_size_gb < 10:
        tier = ComputeTier.SMALL
        spec = TIER_SPECS[tier]
        hours = max(1.0, dataset_size_gb * 0.5)
        return ComputeEstimate(
            instance_type=tier.value,
            n_instances=1,
            vcpu_total=spec["vcpu"],
            ram_gb_total=spec["ram_gb"],
            estimated_runtime_hours=hours,
            estimated_cost_usd=round(hours * spec["cost_per_hour"], 2),
            use_spot=True,
            use_batch_array=False,
        )
    elif dataset_size_gb <= 100:
        tier = ComputeTier.MEDIUM
        spec = TIER_SPECS[tier]
        hours = max(2.0, dataset_size_gb * 0.1)
        return ComputeEstimate(
            instance_type=tier.value,
            n_instances=1,
            vcpu_total=spec["vcpu"],
            ram_gb_total=spec["ram_gb"],
            estimated_runtime_hours=hours,
            estimated_cost_usd=round(hours * spec["cost_per_hour"], 2),
            use_spot=True,
            use_batch_array=False,
        )
    else:
        # Batch array: one job per sample, Spot pricing ~$0.05/vCPU-hour
        vcpu_per_job = 8
        hours_per_sample = max(1.0, (dataset_size_gb / n_samples) * 0.15)
        total_cost = n_samples * vcpu_per_job * hours_per_sample * 0.05 * 0.3  # Spot discount
        return ComputeEstimate(
            instance_type="batch_array",
            n_instances=n_samples,
            vcpu_total=n_samples * vcpu_per_job,
            ram_gb_total=n_samples * 64,
            estimated_runtime_hours=hours_per_sample,
            estimated_cost_usd=round(total_cost, 2),
            use_spot=True,
            use_batch_array=True,
        )


# ---------------------------------------------------------------------------
# AWS Batch
# ---------------------------------------------------------------------------

_batch = None


def _get_batch():
    global _batch
    if _batch is None:
        _batch = boto3.client("batch", region_name=settings.aws_region)
    return _batch


def submit_batch_job(
    job_name: str,
    command: list[str],
    vcpus: int = 4,
    memory_mb: int = 30000,
    environment: dict[str, str] | None = None,
    array_size: int | None = None,
) -> str:
    """Submit a job to AWS Batch. Returns the job ID."""
    batch = _get_batch()
    params: dict[str, Any] = {
        "jobName": job_name,
        "jobQueue": settings.batch_job_queue,
        "jobDefinition": settings.batch_job_definition,
        "containerOverrides": {
            "command": command,
            "vcpus": vcpus,
            "memory": memory_mb,
            "environment": [
                {"name": k, "value": v}
                for k, v in (environment or {}).items()
            ],
        },
    }
    if array_size and array_size > 1:
        params["arrayProperties"] = {"size": array_size}

    resp = batch.submit_job(**params)
    job_id = resp["jobId"]
    logger.info("Submitted Batch job %s (%s)", job_name, job_id)
    return job_id


def wait_for_batch_job(job_id: str, poll_interval: int = 30) -> dict:
    """Poll until a Batch job completes. Returns final job detail."""
    import time
    batch = _get_batch()
    while True:
        resp = batch.describe_jobs(jobs=[job_id])
        job = resp["jobs"][0]
        status = job["status"]
        if status in ("SUCCEEDED", "FAILED"):
            return job
        logger.info("Batch job %s status: %s", job_id, status)
        time.sleep(poll_interval)


def submit_batch_array(
    job_name_prefix: str,
    sample_ids: list[str],
    command_template: list[str],
    vcpus: int = 8,
    memory_mb: int = 60000,
    environment: dict[str, str] | None = None,
) -> list[str]:
    """Submit one Batch job per sample. Returns list of job IDs."""
    job_ids = []
    for sample_id in sample_ids:
        cmd = [c.replace("{sample_id}", sample_id) for c in command_template]
        env = {**(environment or {}), "SAMPLE_ID": sample_id}
        jid = submit_batch_job(
            job_name=f"{job_name_prefix}_{sample_id}",
            command=cmd,
            vcpus=vcpus,
            memory_mb=memory_mb,
            environment=env,
        )
        job_ids.append(jid)
    return job_ids


# ---------------------------------------------------------------------------
# SES email
# ---------------------------------------------------------------------------

def send_email(recipient: str, subject: str, body: str) -> dict:
    ses = boto3.client("ses", region_name=settings.aws_region)
    return ses.send_email(
        Source="rnascope@noreply.aws",
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body}},
        },
    )
