"""RNAscope CLI & FastAPI server — entry points for the agent system."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler

app = typer.Typer(name="rnascope", help="Autonomous RNA-seq analysis agent")
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger("rnascope")


# ---------------------------------------------------------------------------
# CLI: Run pipeline
# ---------------------------------------------------------------------------

@app.command()
def run(
    project: str = typer.Option(..., help="Project name"),
    s3_input: str = typer.Option(..., help="S3 path to FASTQ files"),
    metadata: str = typer.Option(..., help="S3 path to sample metadata CSV"),
    species: str = typer.Option("human", help="Species: human, mouse"),
    condition_a: str = typer.Option(..., help="Name of condition A"),
    condition_b: str = typer.Option(..., help="Name of condition B"),
    n_a: int = typer.Option(..., help="Number of samples in condition A"),
    n_b: int = typer.Option(..., help="Number of samples in condition B"),
    slack_channel: str = typer.Option("", help="Slack channel for notifications"),
    email: str = typer.Option("", help="Email for notifications"),
    tissue: str = typer.Option("", help="Tissue type"),
    disease: str = typer.Option("", help="Disease context"),
) -> None:
    """Launch a full autonomous RNA-seq analysis pipeline."""
    from rnascope.agents.orchestrator import run_pipeline
    from rnascope.infra.aws import s3_get_dataset_size_gb, s3_list_objects
    from rnascope.models.schemas import Job, JobMetadata, ReadLayout, Sample
    from rnascope.notifications import notify_job_completed, notify_job_error, notify_job_started

    console.print(f"[bold green]RNAscope[/] Starting pipeline for {project}")

    # Parse S3 bucket and prefix
    s3_parts = s3_input.replace("s3://", "").split("/", 1)
    bucket = s3_parts[0]
    prefix = s3_parts[1] if len(s3_parts) > 1 else ""

    # Discover samples
    objects = s3_list_objects(bucket, prefix)
    fastq_files = [o["key"] for o in objects if o["key"].endswith((".fastq.gz", ".fq.gz"))]
    dataset_size = s3_get_dataset_size_gb(bucket, prefix)

    # Build sample list from filenames
    sample_map: dict[str, dict] = {}
    for f in fastq_files:
        fname = f.split("/")[-1]
        if "_R1" in fname or "_1.fastq" in fname:
            sid = fname.replace("_R1", "").replace("_1.fastq.gz", "").replace(".fastq.gz", "")
            sample_map.setdefault(sid, {})["r1"] = f"s3://{bucket}/{f}"
        elif "_R2" in fname or "_2.fastq" in fname:
            sid = fname.replace("_R2", "").replace("_2.fastq.gz", "").replace(".fastq.gz", "")
            sample_map.setdefault(sid, {})["r2"] = f"s3://{bucket}/{f}"

    samples = []
    for sid, files in sample_map.items():
        samples.append(Sample(
            sample_id=sid,
            fastq_r1=files.get("r1", ""),
            fastq_r2=files.get("r2"),
            layout=ReadLayout.PAIRED if "r2" in files else ReadLayout.SINGLE,
        ))

    job = Job(
        project_name=project,
        species=species,
        samples=samples,
        condition_a=condition_a,
        condition_b=condition_b,
        n_a=n_a,
        n_b=n_b,
        dataset_size_gb=dataset_size,
        s3_input_path=s3_input,
        metadata_path=metadata,
        metadata=JobMetadata(
            researcher_email=email,
            slack_channel=slack_channel,
            tissue_type=tissue,
            disease_context=disease,
        ),
    )

    console.print(f"Job ID: [bold]{job.job_id}[/]")
    console.print(f"Samples: {len(samples)} | Size: {dataset_size:.1f} GB | Species: {species}")

    notify_job_started(
        job.job_id, project, len(samples),
        slack_channel, email,
    )

    try:
        results = run_pipeline(job)
        report_url = results.get("run_report_agent", {}).get("report_pdf_s3_path", "N/A")
        notify_job_completed(
            job.job_id, project,
            f"Pipeline completed. {len(samples)} samples analyzed.",
            report_url, slack_channel, email,
        )
        console.print(f"[bold green]Done![/] Report: {report_url}")
    except Exception as e:
        logger.exception("Pipeline failed")
        notify_job_error(job.job_id, project, str(e), slack_channel, email)
        console.print(f"[bold red]Pipeline failed:[/] {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI: Chat interface
# ---------------------------------------------------------------------------

@app.command()
def chat(
    job_id: str = typer.Argument(..., help="Job ID to query"),
) -> None:
    """Interactive chat with the RNAscope agent about a completed/running job."""
    from rnascope.agents.chat import ChatAgent

    agent = ChatAgent(job_id)
    console.print(f"[bold green]RNAscope Chat[/] — Job {job_id}")
    console.print("Type your question (or 'quit' to exit)\n")

    while True:
        question = console.input("[bold blue]You:[/] ")
        if question.strip().lower() in ("quit", "exit", "q"):
            break
        response = agent.ask(question)
        console.print(f"[bold green]RNAscope:[/] {response}\n")


# ---------------------------------------------------------------------------
# CLI: Job status
# ---------------------------------------------------------------------------

@app.command()
def status(
    job_id: str = typer.Argument(..., help="Job ID to check"),
) -> None:
    """Check the status of a running or completed pipeline job."""
    from rnascope.infra.checkpoint import get_job_state

    state = get_job_state(job_id)
    if not state:
        console.print(f"[red]Job {job_id} not found[/]")
        sys.exit(1)

    console.print(f"[bold]Job:[/] {job_id}")
    console.print(f"[bold]Status:[/] {state.get('status', 'unknown')}")
    console.print(f"[bold]Current step:[/] {state.get('current_step', 'none')}")
    console.print(f"[bold]Steps completed:[/] {', '.join(state.get('steps_completed', []))}")
    console.print(f"[bold]Cost so far:[/] ${state.get('cost_so_far_usd', 0):.2f}")


# ---------------------------------------------------------------------------
# FastAPI server for chat API + webhooks
# ---------------------------------------------------------------------------

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to bind"),
) -> None:
    """Start the FastAPI server for the chat API and job webhooks."""
    import uvicorn
    uvicorn.run("rnascope.api:api_app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
