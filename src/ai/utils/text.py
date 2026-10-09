"""Text helpers for model output.

Chat models can return `content` as a string or as a list of blocks
(e.g. Claude: [{"type": "text", "text": "..."}, {"type": "tool_use", ...}]).
`chunk_to_text` normalizes both to a plain string.
"""

import re
from typing import Any


# Marker that some models insert before the final answer ("Mensagem ao cliente:").
_CUSTOMER_MARKER = re.compile(
    r".*?(?:mensagem\s+(?:final\s+)?(?:ao|para\s+o)\s+cliente|"
    r"resposta\s+(?:ao|para\s+o)\s+cliente)\s*:?\s*",
    re.IGNORECASE | re.DOTALL,
)

# "Leaked" internal reasoning lines that should be removed from the beginning.
_INTERNAL_LINE = re.compile(
    r"^\s*(?:\**\s*)?(?:\[|\()?\s*"
    r"(?:análise\s+interna|analise\s+interna|raciocínio|raciocinio|"
    r"diagnóstico|diagnostico|evidências|evidencias|ferramentas?|"
    r"rascunho|nota\s+interna)\b.*$",
    re.IGNORECASE,
)


def sanitize_customer_message(text: str) -> str:
    """Removes any 'internal reasoning' preamble leaked by the LLM.

    Safety net (prompts already ask for only the final message). Strategy:
    1. If there's an explicit marker like "Mensagem ao cliente:", keep only
       what comes after it.
    2. Otherwise, discard initial lines that are clearly internal notes and
       separators '---'.
    """
    if not text:
        return text

    cleaned = text.strip()

    match = _CUSTOMER_MARKER.match(cleaned)
    if match:
        cleaned = cleaned[match.end():]
        cleaned = re.sub(r"^[\s*_:#>\-]+", "", cleaned).strip()

    lines = cleaned.split("\n")
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped in {"---", "***", "___"} or _INTERNAL_LINE.match(
            stripped
        ):
            start = i + 1
            continue
        break

    if start < len(lines):
        cleaned = "\n".join(lines[start:]).strip()

    return cleaned or text.strip()


def cited_skus(text: str, skus: list[str]) -> list[str]:
    """SKUs from `skus` that appear in `text`, in order of first appearance.

    Matches the whole code only ("CAM-1" does not match inside "CAM-12").
    """
    positions: dict[str, int] = {}
    for sku in dict.fromkeys(skus):
        match = re.search(rf"(?<![\w-]){re.escape(sku)}(?![\w-])", text, re.IGNORECASE)
        if match:
            positions[sku] = match.start()
    return sorted(positions, key=positions.__getitem__)


def chunk_to_text(content: Any) -> str:
    """Extracts text from a `content` that can be str, list of blocks, or None."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type", "text") == "text":
                parts.append(item.get("text") or "")
        return "".join(parts)
    return str(content)
