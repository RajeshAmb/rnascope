"""RNAscope Orchestrator — the main agentic loop that drives the pipeline.

This module implements the core Claude API agentic loop:
1. Send the job description to the orchestrator agent
2. The agent responds with tool calls
3. We execute the tools and feed results back
4. Repeat until the agent signals completion (end_turn / no more tool calls)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import anthropic

from rnascope.agents.interpretation import run_interpretation
from rnascope.config import settings
from rnascope.infra.checkpoint import save_job_state, update_job_step
from rnascope.models.schemas import Job, JobStatus
from rnascope.prompts.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT
from rnascope.tools.definitions import TOOL_DEFINITIONS
from rnascope.tools.handlers import handle_tool_call

logger = logging.getLogger(__name__)

MAX_TURNS = 50  # Safety limit on agentic loop iterations
MAX_RETRIES = 3


def run_pipeline(job: Job) -> dict[str, Any]:
    """Execute the full RNA-seq pipeline autonomously.

    This is the main entry point. It:
    1. Initializes the Claude orchestrator agent
    2. Sends the job description
    3. Runs the agentic tool-calling loop
    4. Returns final results
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    job.status = JobStatus.RUNNING
    save_job_state(job.job_id, job.model_dump())

    # Build the initial user message with job details
    user_message = _build_job_message(job)

    messages: list[dict] = [{"role": "user", "content": user_message}]
    all_results: dict[str, Any] = {"job_id": job.job_id}

    logger.info("Starting pipeline for job %s (%d samples, %.1f GB)",
                job.job_id, len(job.samples), job.dataset_size_gb)

    for turn in range(MAX_TURNS):
        logger.info("--- Orchestrator turn %d ---", turn + 1)

        response = _call_orchestrator(client, messages)

        # Extract text blocks and tool_use blocks
        text_blocks = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_blocks.append(block.text)
                logger.info("Agent: %s", block.text[:200])
            elif block.type == "tool_use":
                tool_calls.append(block)

        # If no tool calls, the agent is done
        if not tool_calls:
            logger.info("Pipeline complete — no more tool calls")
            break

        # Add assistant message to conversation
        messages.append({"role": "assistant", "content": response.content})

        # Execute all tool calls and collect results
        tool_results = []
        for tc in tool_calls:
            logger.info("Tool call: %s(%s)", tc.name, json.dumps(tc.input)[:100])

            # Special handling: interpretation agent needs a separate Claude call
            if tc.name == "run_interpretation_agent":
                result = _handle_interpretation(client, tc.input, all_results)
            else:
                result = handle_tool_call(tc.name, tc.input)

            # Track results
            parsed = json.loads(result) if isinstance(result, str) else result
            all_results[tc.name] = parsed

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result if isinstance(result, str) else json.dumps(result, default=str),
            })

        # Feed tool results back to the agent
        messages.append({"role": "user", "content": tool_results})

        # Check stop reason
        if response.stop_reason == "end_turn":
            logger.info("Agent signaled end_turn")
            break

    # Finalize
    job.status = JobStatus.COMPLETED
    save_job_state(job.job_id, job.model_dump())
    all_results["status"] = "completed"
    logger.info("Pipeline finished for job %s", job.job_id)

    return all_results


def _call_orchestrator(
    client: anthropic.Anthropic,
    messages: list[dict],
    retry: int = 0,
) -> anthropic.types.Message:
    """Call the orchestrator model with retry logic."""
    try:
        return client.messages.create(
            model=settings.orchestrator_model,
            max_tokens=4096,
            system=ORCHESTRATOR_SYSTEM_PROMPT,
            messages=messages,
            tools=TOOL_DEFINITIONS,
        )
    except anthropic.APIError as e:
        if retry < MAX_RETRIES:
            wait = 2 ** retry
            logger.warning("API error (retry %d/%d in %ds): %s", retry + 1, MAX_RETRIES, wait, e)
            time.sleep(wait)
            return _call_orchestrator(client, messages, retry + 1)
        raise


def _handle_interpretation(
    client: anthropic.Anthropic,
    tool_input: dict,
    all_results: dict,
) -> str:
    """Run the interpretation sub-agent as a separate Claude call."""
    deg_data = all_results.get("run_deg_agent", {})
    pathway_data = all_results.get("run_pathway_agent", {})
    metadata = tool_input.get("metadata", {})

    interpretation = run_interpretation(
        client=client,
        deg_results=deg_data,
        pathway_results=pathway_data,
        metadata=metadata,
    )

    return json.dumps({
        "job_id": tool_input["job_id"],
        "interpretation": interpretation,
        "status": "completed",
    })


def _build_job_message(job: Job) -> str:
    sample_ids = [s.sample_id for s in job.samples]
    return f"""New RNA-seq job received.

Job ID: {job.job_id}
Project: {job.project_name}
Samples: {len(job.samples)} FASTQ files
Sample IDs: {', '.join(sample_ids)}
Total size: {job.dataset_size_gb} GB
Species: {job.species}
Genome: {job.genome}
GTF: {job.gtf}
Condition A: {job.condition_a} (n={job.n_a})
Condition B: {job.condition_b} (n={job.n_b})
S3 input path: {job.s3_input_path}
Metadata file: {job.metadata_path}
Tissue type: {job.metadata.tissue_type}
Disease context: {job.metadata.disease_context}
Covariates: {', '.join(job.metadata.covariates) if job.metadata.covariates else 'none'}
Requested outputs: QC report, DEG table, pathway enrichment, AI interpretation, PDF report
Slack channel: {job.metadata.slack_channel}
Notify email: {job.metadata.researcher_email}

Begin autonomous pipeline execution."""
