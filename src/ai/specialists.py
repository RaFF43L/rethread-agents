"""Specialist agents (tool-calling ReAct loops built with `create_agent`).

Each specialist is its own small agent: system prompt + tools + the large model.
The orchestrator graph (`ai/agent.py`) calls `run_specialist` and only sees the
final answer plus the tool outputs (evidence) used by the quality node.

Adding a specialist = new prompt + tools here, a new `Intent` in `states.py`
and a line in the router prompt.
"""

import json
from functools import lru_cache

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage

from ai.llm import llm_factory
from ai.prompts import (
    FIT_AGENT_PROMPT,
    PREVIOUS_ANSWERS_TEMPLATE,
    RETRY_FEEDBACK_TEMPLATE,
    SPECIALIST_INPUT_TEMPLATE,
    STYLIST_AGENT_PROMPT,
)
from ai.states import Intent, RethreadState, SpecialistAnswer
from ai.tools import FIT_TOOLS, STYLIST_TOOLS
from ai.utils import chunk_to_text, cited_skus
from config.envs import envs
from config.logging import get_logger

logger = get_logger(__name__)

SPECIALISTS: dict[Intent, tuple[str, list]] = {
    "size_fit": (FIT_AGENT_PROMPT, FIT_TOOLS),
    "style_consulting": (STYLIST_AGENT_PROMPT, STYLIST_TOOLS),
}

# Limits the evidence handed to the judge (tool outputs can be long).
_MAX_EVIDENCE_CHARS = 6000

# Limits each previous message fed back to the models.
_MAX_HISTORY_MESSAGE_CHARS = 800

# Tools whose output is catalog pieces (source of the SKUs returned to the backend).
_CATALOG_TOOLS = {"search_catalog", "get_item_spec"}


@lru_cache(maxsize=None)
def _agent(intent: Intent):
    """Builds (once) the agent for an intent. Lazy: no model is created on import."""
    system_prompt, tools = SPECIALISTS[intent]
    return create_agent(
        llm_factory.model_large(max_tokens=envs.agent_max_tokens),
        tools=tools,
        system_prompt=system_prompt,
        response_format=SpecialistAnswer,
        name=f"{intent}_agent",
    )


def describe_item(state: RethreadState) -> str:
    item_id = state.get("item_id")
    if item_id:
        return f"{item_id} (use get_item_spec)"
    return "nenhuma informada — se precisar, pergunte ao cliente qual peça"


def describe_history(state: RethreadState) -> str:
    """Previous turns as a transcript (the agent's turns list the SKUs it recommended)."""
    lines = []
    for turn in state.get("history") or []:
        content = turn["content"]
        if len(content) > _MAX_HISTORY_MESSAGE_CHARS:
            content = content[:_MAX_HISTORY_MESSAGE_CHARS] + "…"
        if turn["role"] == "user":
            lines.append(f"Cliente: {content}")
        else:
            skus = turn.get("skus") or []
            cited = f" [peças do acervo citadas, SKU: {', '.join(skus)}]" if skus else ""
            lines.append(f"Atendente: {content}{cited}")
    return "\n".join(lines) or "(início da conversa)"


def describe_measurements(state: RethreadState) -> str:
    measurements = state.get("buyer_measurements") or {}
    return json.dumps(measurements, ensure_ascii=False) if measurements else "não informadas"


def _build_input(intent: Intent, state: RethreadState) -> str:
    previous = ""
    answers = {
        k: v["text"] for k, v in (state.get("agent_outputs") or {}).items() if k != intent
    }
    if answers:
        previous = PREVIOUS_ANSWERS_TEMPLATE.format(
            answers="\n\n".join(f"[{k}]\n{v}" for k, v in answers.items())
        )

    feedback = ""
    if state.get("rejection_reason"):
        feedback = RETRY_FEEDBACK_TEMPLATE.format(
            rejection_reason=state["rejection_reason"]
        )

    return SPECIALIST_INPUT_TEMPLATE.format(
        history=describe_history(state),
        message=state["message"],
        item=describe_item(state),
        measurements=describe_measurements(state),
        previous=previous,
        feedback=feedback,
    )


def _catalog_skus(tool_messages: list[ToolMessage], context_ref: str | None) -> list[str]:
    """SKUs of the catalog pieces returned by the tools, minus the piece in context."""
    skus: list[str] = []
    for message in tool_messages:
        if message.name not in _CATALOG_TOOLS:
            continue
        try:
            data = json.loads(chunk_to_text(message.content))
        except json.JSONDecodeError:
            continue
        for piece in data if isinstance(data, list) else [data]:
            if not isinstance(piece, dict) or not piece.get("sku"):
                continue
            if context_ref and context_ref in (piece.get("id"), piece.get("sku")):
                continue
            skus.append(piece["sku"])
    return skus


async def run_specialist(intent: Intent, state: RethreadState) -> tuple[str, str, list[str]]:
    """Runs the specialist agent.

    Returns (final answer, tool evidence, SKUs of the catalog pieces it recommends).
    The SKUs are kept only if a catalog tool actually returned them.
    """
    logger.info(f"Running specialist: {intent} (attempt {state.get('attempts', 0) + 1})")

    result = await _agent(intent).ainvoke(
        {"messages": [HumanMessage(content=_build_input(intent, state))]}
    )
    messages = result["messages"]
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    known_skus = _catalog_skus(tool_messages, state.get("item_id"))

    structured: SpecialistAnswer | None = result.get("structured_response")
    if structured is not None:
        answer = structured.message
        skus = [s for s in dict.fromkeys(structured.skus) if s in known_skus]
    else:
        # Model skipped the structured output: fall back to SKUs written in the text.
        answer = chunk_to_text(messages[-1].content)
        skus = cited_skus(answer, known_skus)

    evidence = "\n\n".join(
        f"[{m.name}] {chunk_to_text(m.content)}"
        for m in tool_messages
        if m.name != SpecialistAnswer.__name__
    )
    return answer, evidence[:_MAX_EVIDENCE_CHARS] or "(nenhuma ferramenta foi chamada)", skus
