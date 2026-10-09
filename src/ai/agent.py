"""Orchestrator graph: router -> specialists (in sequence) -> compose.

START → triage → dispatch ─┬─ size_fit ──────────┐
                ▲          ├─ style_consulting ──┤
                │          └─ (queue empty) ─→ compose → END
                │                                ▼
                └──── approved / max attempts ── quality ── rejected → same specialist

A message with several intents ("veste 40 e combina com bota preta?") puts
both in the `pending` queue; `dispatch` runs them one at a time (fit first) and
the stylist receives the fit answer as context.
"""

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from ai.llm import llm_factory
from ai.prompts import (
    COMPOSE_PROMPT,
    NOT_APPROVED_NOTE,
    QUALITY_SYSTEM_PROMPT,
    QUALITY_USER_PROMPT,
    TRIAGE_SYSTEM_PROMPT,
)
from ai.specialists import (
    describe_history,
    describe_item,
    describe_measurements,
    run_specialist,
)
from ai.states import INTENT_ORDER, Intent, QualityResult, RethreadState, TriageResult
from ai.utils import chunk_to_text, sanitize_customer_message
from config import envs
from config.logging import get_logger

logger = get_logger(__name__)

GRAPH_NAME = "rethread"


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def triage_node(state: RethreadState) -> dict:
    """Detects every intent in the message (structured output, fast model)."""
    logger.info("Executing message triage...")

    model = llm_factory.model_fast(temperature=0).with_structured_output(TriageResult)
    context = f"\n\n(Cliente está vendo a peça {state['item_id']})" if state.get("item_id") else ""
    history = (
        f"Conversa anterior:\n{describe_history(state)}\n\nMensagem atual: "
        if state.get("history")
        else ""
    )
    result: TriageResult = model.invoke(
        [
            SystemMessage(content=TRIAGE_SYSTEM_PROMPT),
            HumanMessage(content=history + state["message"] + context),
        ]
    )

    # Dedupe + fixed order (fit before style); never leave the queue empty.
    intents = [i for i in INTENT_ORDER if i in set(result.intents)] or ["style_consulting"]

    logger.info(f"Triage: intents={intents}")
    return {
        "intents": intents,
        "pending": intents,
        "current": None,
        "reasoning": result.reasoning,
        "metadata": {"triage_intents": intents},
    }


def dispatch_node(state: RethreadState) -> dict:
    """Stores the finished specialist's answer and pops the next one."""
    update: dict = {}

    current = state.get("current")
    if current:
        update["agent_outputs"] = {
            current: {
                "text": sanitize_customer_message(state.get("work_result", "")),
                "approved": state.get("quality_approved", False),
                "attempts": state.get("attempts", 0),
                "skus": state.get("work_skus", []),
            }
        }

    pending = list(state.get("pending") or [])
    next_intent = pending.pop(0) if pending else None
    logger.info(f"Dispatch: next={next_intent} remaining={pending}")

    update.update(
        {
            "pending": pending,
            "current": next_intent,
            "attempts": 0,
            "rejection_reason": "",
            "work_result": "",
            "evidence": "",
            "work_skus": [],
            "quality_approved": False,
        }
    )
    return update


def _make_specialist_node(intent: Intent):
    async def specialist_node(state: RethreadState) -> dict:
        attempts = state.get("attempts", 0) + 1
        work_result, evidence, skus = await run_specialist(intent, state)
        return {
            "work_result": work_result,
            "evidence": evidence,
            "work_skus": skus,
            "attempts": attempts,
            "metadata": {f"{intent}_attempts": attempts},
        }

    specialist_node.__name__ = f"{intent}_node"
    return specialist_node


def quality_node(state: RethreadState) -> dict:
    """LLM-as-judge: checks the answer is on-topic and grounded on the tools' evidence."""
    logger.info(f"Validating quality of {state.get('current')} (attempt {state.get('attempts', 0)})...")

    model = llm_factory.model_judge(temperature=0).with_structured_output(QualityResult)
    result: QualityResult = model.invoke(
        [
            SystemMessage(content=QUALITY_SYSTEM_PROMPT),
            HumanMessage(
                content=QUALITY_USER_PROMPT.format(
                    intent=state.get("current"),
                    history=describe_history(state),
                    message=state["message"],
                    item=describe_item(state),
                    measurements=describe_measurements(state),
                    evidence=state.get("evidence", ""),
                    work_result=state.get("work_result", ""),
                )
            ),
        ]
    )

    logger.info(f"Quality: approved={result.approved}")
    return {
        "quality_approved": result.approved,
        "rejection_reason": "" if result.approved else result.rejection_reason,
        "metadata": {f"{state.get('current')}_approved": result.approved},
    }


def compose_node(state: RethreadState) -> dict:
    """Merges the specialists' answers into a single customer message."""
    outputs = state.get("agent_outputs") or {}
    ordered = [outputs[i] for i in INTENT_ORDER if i in outputs]

    if len(ordered) == 1:
        response = ordered[0]["text"]
    else:
        sections = "\n\n".join(
            f"## Resposta de {intent}\n{outputs[intent]['text']}"
            for intent in INTENT_ORDER
            if intent in outputs
        )
        model = llm_factory.model_fast(temperature=0.2)
        result = model.invoke(
            [HumanMessage(content=COMPOSE_PROMPT.format(message=state["message"], sections=sections))]
        )
        response = sanitize_customer_message(chunk_to_text(result.content))

    skus = list(dict.fromkeys(sku for o in ordered for sku in o.get("skus", [])))

    not_approved = [o for o in ordered if not o["approved"]]
    if not_approved:
        response += NOT_APPROVED_NOTE.format(
            attempts=max(o["attempts"] for o in not_approved)
        )

    return {"response": response, "skus": skus}


# --------------------------------------------------------------------------- #
# Routers (conditional edges)
# --------------------------------------------------------------------------- #
def route_dispatch(
    state: RethreadState,
) -> Literal["size_fit", "style_consulting", "compose"]:
    """Next specialist in the queue, or compose when it's empty."""
    return state.get("current") or "compose"


def route_after_quality(
    state: RethreadState,
) -> Literal["dispatch", "size_fit", "style_consulting"]:
    """Approved or attempts exhausted -> dispatch; otherwise retry the same specialist."""
    if state.get("quality_approved"):
        return "dispatch"
    if state.get("attempts", 0) >= envs.max_attempts:
        logger.info("Attempt limit reached. Moving on without approval.")
        return "dispatch"
    logger.info("Rejected. Resending to specialist with rejection_reason.")
    return state["current"]


# --------------------------------------------------------------------------- #
# Graph construction
# --------------------------------------------------------------------------- #
def build_graph():
    graph = StateGraph(RethreadState)

    graph.add_node("triage", triage_node)
    graph.add_node("dispatch", dispatch_node)
    for intent in INTENT_ORDER:
        graph.add_node(intent, _make_specialist_node(intent))
    graph.add_node("quality", quality_node)
    graph.add_node("compose", compose_node)

    graph.add_edge(START, "triage")
    graph.add_edge("triage", "dispatch")

    graph.add_conditional_edges(
        "dispatch",
        route_dispatch,
        {**{i: i for i in INTENT_ORDER}, "compose": "compose"},
    )

    for intent in INTENT_ORDER:
        graph.add_edge(intent, "quality")

    graph.add_conditional_edges(
        "quality",
        route_after_quality,
        {**{i: i for i in INTENT_ORDER}, "dispatch": "dispatch"},
    )

    graph.add_edge("compose", END)

    return graph.compile(name=GRAPH_NAME)


# Compiled graph, ready for use.
rethread_agent = build_graph()
