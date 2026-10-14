"""HTTP layer with the actions stubbed out (no lifespan → no migrations, no DB)."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import api
from actions import chat as chat_actions
from actions.base import ChatRequest, ChatResponse
from actions.catalog import NotFoundError


@pytest.fixture
def client():
    return TestClient(api.app)  # not used as a context manager: lifespan doesn't run


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_item_not_found_is_404(client, monkeypatch):
    def missing(ref):
        raise NotFoundError(f"Item '{ref}' not found")

    monkeypatch.setattr(api.catalog_actions, "get_item", missing)
    response = client.get("/items/XYZ")
    assert response.status_code == 404
    assert "XYZ" in response.json()["detail"]


def test_chat_validates_body(client):
    assert client.post("/chat", json={"message": ""}).status_code == 422
    assert client.post("/chat", json={"message": "oi", "buyer_measurements": {"waist": -1}}).status_code == 422


def test_chat_success(client, monkeypatch):
    async def fake(request):
        return ChatResponse(intents=["size_fit"], response="Serve!", skus=["A"])

    monkeypatch.setattr(api, "process_chat", fake)
    body = client.post("/chat", json={"message": "serve?"}).json()
    assert body["response"] == "Serve!"
    assert body["skus"] == ["A"]


def test_chat_error_is_500(client, monkeypatch):
    async def boom(request):
        raise RuntimeError("llm offline")

    monkeypatch.setattr(api, "process_chat", boom)
    response = client.post("/chat", json={"message": "oi"})
    assert response.status_code == 500
    assert response.json()["detail"] == "llm offline"


# --------------------------------------------------------------------------- #
# actions.chat helpers
# --------------------------------------------------------------------------- #
def test_sse_format():
    assert chat_actions._sse("token", {"text": "ção"}) == 'event: token\ndata: {"text": "ção"}\n\n'


def test_graph_input_without_session_does_not_touch_db(monkeypatch):
    monkeypatch.setattr(chat_actions, "session_scope", None)  # would crash if used
    request = ChatRequest(message="oi", item_id="CAL-1", buyer_measurements={"waist": 80})
    assert chat_actions._graph_input(request) == {
        "message": "oi",
        "item_id": "CAL-1",
        "buyer_measurements": {"waist": 80.0},
        "history": [],
        "channel": "text",
    }


def test_save_turn_skipped_without_session_or_response(monkeypatch):
    monkeypatch.setattr(chat_actions, "session_scope", None)
    chat_actions._save_turn(ChatRequest(message="oi"), {}, {"response": "x"})
    chat_actions._save_turn(ChatRequest(message="oi", session_id="s"), {}, {"response": ""})


def test_save_turn_failure_is_swallowed(monkeypatch):
    def broken():
        raise RuntimeError("db down")

    monkeypatch.setattr(chat_actions, "session_scope", broken)
    chat_actions._save_turn(ChatRequest(message="oi", session_id="s"), {}, {"response": "x"})


def test_stream_emits_error_event(monkeypatch):
    def broken(request):
        raise RuntimeError("db down")

    monkeypatch.setattr(chat_actions, "_graph_input", broken)

    async def collect():
        return [e async for e in chat_actions.process_chat_stream(ChatRequest(message="oi"))]

    events = asyncio.run(collect())
    assert len(events) == 1
    assert events[0].startswith("event: error\n")
    assert json.loads(events[0].split("data: ", 1)[1]) == {"detail": "db down"}


class FakeGraph:
    """Emits the triage, then waits for `release` before finishing the turn."""

    def __init__(self):
        self.release = asyncio.Event()

    async def astream_events(self, graph_input, config, version):
        yield {
            "event": "on_chain_end",
            "name": "triage",
            "data": {"output": {"intents": ["size_fit"], "ack": "Já vejo."}},
        }
        await self.release.wait()
        yield {
            "event": "on_chain_end",
            "name": chat_actions.GRAPH_NAME,
            "data": {"output": {"intents": ["size_fit"], "response": "Serve!", "skus": []}},
        }


@pytest.fixture
def fake_turn(monkeypatch):
    """Fake graph + records the saved turns (no DB, no LLM)."""
    graph = FakeGraph()
    saved = []
    monkeypatch.setattr(chat_actions, "rethread_agent", graph)
    monkeypatch.setattr(chat_actions, "_graph_input", lambda request: {"message": request.message})
    monkeypatch.setattr(
        chat_actions, "_save_turn", lambda request, graph_input, state: saved.append(state["response"])
    )
    return graph, saved


def _event_names(events):
    return [e.split("\n", 1)[0].removeprefix("event: ") for e in events]


def test_stream_replays_the_answer_and_saves_the_turn(fake_turn):
    graph, saved = fake_turn

    async def collect():
        graph.release.set()
        return [e async for e in chat_actions.process_chat_stream(ChatRequest(message="serve?"))]

    events = asyncio.run(collect())
    names = _event_names(events)
    assert names[0] == "triage" and names[-1] == "done"
    assert "".join(json.loads(e.split("data: ", 1)[1])["text"] for e in events if e.startswith("event: token")) == "Serve!"
    assert saved == ["Serve!"]


def test_turn_is_saved_even_if_the_client_disconnects(fake_turn):
    graph, saved = fake_turn

    async def scenario():
        stream = chat_actions.process_chat_stream(ChatRequest(message="serve?", session_id="s"))
        first = await anext(stream)
        await stream.aclose()  # client gone (closed tab, voice interruption)
        assert saved == []
        graph.release.set()  # the graph finishes afterwards
        await asyncio.gather(*list(chat_actions._running_turns))
        return first

    first = asyncio.run(scenario())
    assert first.startswith("event: triage")
    assert saved == ["Serve!"]
    assert not chat_actions._running_turns
