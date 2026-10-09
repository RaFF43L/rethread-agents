from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


def merge_dict(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> dict[str, Any]:
    """Reducer: merges keys that each node adds to the global state."""
    return {**(left or {}), **(right or {})}


# Specialists the router can pick.
Intent = Literal["size_fit", "style_consulting"]

# Execution order when a message has several intents: fit first, so the
# stylist can build on the size answer instead of repeating it.
INTENT_ORDER: tuple[Intent, ...] = ("size_fit", "style_consulting")


class TriageResult(BaseModel):
    """Structured output of the router."""

    intents: list[Intent] = Field(
        description="Todas as intenções presentes na mensagem (uma ou mais)"
    )
    reasoning: str = Field(description="Justificativa curta da classificação")


class QualityResult(BaseModel):
    """Structured output of the quality node."""

    approved: bool = Field(
        description="True se a resposta do especialista pode ir ao cliente"
    )
    rejection_reason: str = Field(
        default="",
        description="Se reprovada, explica objetivamente o que corrigir",
    )


class SpecialistAnswer(BaseModel):
    """Structured final answer of a specialist agent."""

    message: str = Field(
        description="Mensagem final ao cliente, sem códigos SKU/id e sem rótulos internos"
    )
    skus: list[str] = Field(
        default_factory=list,
        description=(
            "SKUs (exatamente como vieram das ferramentas) das peças do acervo que a "
            "mensagem recomenda ou cita, na ordem em que aparecem. Não inclua a peça em "
            "contexto. Lista vazia se nenhuma."
        ),
    )


class AgentOutput(TypedDict):
    text: str
    approved: bool
    attempts: int
    skus: list[str]  # catalog pieces recommended in the text


class RethreadState(TypedDict, total=False):
    """State that travels through the graph nodes."""

    # Input
    message: str
    item_id: str | None  # piece the customer is looking at (id or SKU)
    buyer_measurements: dict[str, float]  # body measurements in cm
    # Previous turns of the session, oldest first: {role, content, skus}
    history: list[dict[str, Any]]

    # Produced by triage
    intents: list[Intent]
    reasoning: str

    # Dispatcher: queue of specialists still to run + the one running now
    pending: list[Intent]
    current: Intent | None

    # Produced by the current specialist / controlled by the quality loop
    work_result: str
    evidence: str  # tool outputs the answer must be grounded on
    work_skus: list[str]  # catalog pieces recommended in work_result
    quality_approved: bool
    rejection_reason: str
    attempts: int

    # Final answer of each specialist (intent -> AgentOutput)
    agent_outputs: Annotated[dict[str, AgentOutput], merge_dict]

    # Global metadata: each node adds/updates keys here
    metadata: Annotated[dict[str, Any], merge_dict]

    # Final response + SKUs of the catalog pieces recommended in it (for the backend)
    response: str
    skus: list[str]
