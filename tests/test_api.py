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
        return ChatResponse(intents=["size_fit"], reasoning="r", response="Serve!", skus=["A"])

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
