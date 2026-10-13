"""Client of the rethread-agents chat pipeline (`POST /chat/stream`, SSE)."""

import json
from typing import Any, AsyncIterator

import httpx

# The pipeline runs several LLM calls (triage, specialist, quality, compose)
# before the first token: be generous with the read timeout.
_TIMEOUT = httpx.Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0)


class RethreadClient:
    def __init__(self, base_url: str):
        self._http = httpx.AsyncClient(base_url=base_url, timeout=_TIMEOUT)

    async def stream_chat(
        self,
        message: str,
        session_id: str | None,
        item_id: str | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Yields the pipeline's SSE events as (event, data)."""
        body: dict[str, Any] = {"message": message, "channel": "voice"}
        if session_id:
            body["session_id"] = session_id
        if item_id:
            body["item_id"] = item_id

        async with self._http.stream("POST", "/chat/stream", json=body) as response:
            response.raise_for_status()
            event = "message"
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    yield event, json.loads(line[len("data:"):].strip())
                    event = "message"

    async def aclose(self) -> None:
        await self._http.aclose()
