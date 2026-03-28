"""Interpretation sub-agent — generates biological narrative from DE + pathway results."""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from rnascope.config import settings
from rnascope.prompts.interpretation import INTERPRETATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def run_interpretation(
    client: anthropic.Anthropic,
    deg_results: dict[str, Any],
    pathway_results: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    """Call the interpretation model to generate biological narrative.

    Returns the full interpretation text (all 6 sections).
    """
    user_content = f"""Interpret these RNA-seq results:

TOP DEGs:
{json.dumps(deg_results, indent=2, default=str)}

PATHWAY RESULTS:
{json.dumps(pathway_results, indent=2, default=str)}

METADATA:
{json.dumps(metadata, indent=2, default=str)}

TISSUE: {metadata.get("tissue_type", "unknown")}
DISEASE CONTEXT: {metadata.get("disease_context", "unknown")}

Generate full biological interpretation with all 6 sections."""

    logger.info("Calling interpretation model...")

    response = client.messages.create(
        model=settings.interpretation_model,
        max_tokens=2048,
        temperature=0.3,
        system=INTERPRETATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    interpretation = ""
    for block in response.content:
        if block.type == "text":
            interpretation += block.text

    logger.info("Interpretation generated (%d chars)", len(interpretation))
    return interpretation
