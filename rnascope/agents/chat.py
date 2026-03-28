"""Chat agent — researcher-facing conversational interface."""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from rnascope.config import settings
from rnascope.infra.checkpoint import get_job_state
from rnascope.prompts.chat import CHAT_SYSTEM_PROMPT, build_chat_context

logger = logging.getLogger(__name__)


class ChatAgent:
    """Stateful chat agent that maintains conversation history per job."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.messages: list[dict] = []

    def _get_system_prompt(self) -> str:
        job_state = get_job_state(self.job_id) or {}
        context = build_chat_context(job_state)
        return CHAT_SYSTEM_PROMPT + "\n\n" + context

    def ask(self, question: str) -> str:
        """Send a researcher question and get a response."""
        self.messages.append({"role": "user", "content": question})

        response = self.client.messages.create(
            model=settings.chat_model,
            max_tokens=1024,
            temperature=0.2,
            system=self._get_system_prompt(),
            messages=self.messages,
        )

        reply = ""
        for block in response.content:
            if block.type == "text":
                reply += block.text

        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def reset(self) -> None:
        self.messages.clear()
