from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Anthropic
    anthropic_api_key: str = ""
    orchestrator_model: str = "claude-sonnet-4-6-20250514"
    interpretation_model: str = "claude-sonnet-4-6-20250514"
    chat_model: str = "claude-sonnet-4-6-20250514"

    # AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-2"
    s3_bucket_raw: str = "rnascope-raw-data"
    s3_bucket_results: str = "rnascope-results"
    s3_bucket_reports: str = "rnascope-reports"
    batch_job_queue: str = "rnascope-queue"
    batch_job_definition: str = "rnascope-job-def"
    efs_mount_path: str = "/mnt/efs/rnascope"
    star_genome_index_s3: str = "s3://rnascope-references/star-index/hg38/"
    ensembl_gtf_s3: str = "s3://rnascope-references/gtf/Homo_sapiens.GRCh38.110.gtf.gz"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Database
    database_url: str = ""

    # Slack
    slack_bot_token: str = ""
    slack_default_channel: str = "#rnaseq-results"

    # NCBI
    ncbi_api_key: str = ""


settings = Settings()
