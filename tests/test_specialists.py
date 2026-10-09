import asyncio
import json

from langchain_core.messages import AIMessage, ToolMessage

from ai import specialists
from ai.prompts import QUALITY_USER_PROMPT, TRIAGE_SYSTEM_PROMPT
from ai.states import SpecialistAnswer


def _tool(name, data):
    return ToolMessage(content=json.dumps(data), name=name, tool_call_id="t")


class TestDescribe:
    def test_empty_history(self):
        assert specialists.describe_history({}) == "(início da conversa)"

    def test_history_transcript_with_skus(self):
        state = {
            "history": [
                {"role": "user", "content": "oi"},
                {"role": "assistant", "content": "olá", "skus": ["CAM-1", "CAL-2"]},
                {"role": "assistant", "content": "ok", "skus": []},
            ]
        }
        assert specialists.describe_history(state).splitlines() == [
            "Cliente: oi",
            "Atendente: olá [peças do acervo citadas, SKU: CAM-1, CAL-2]",
            "Atendente: ok",
        ]

    def test_long_history_message_is_truncated(self):
        content = "x" * (specialists._MAX_HISTORY_MESSAGE_CHARS + 50)
        line = specialists.describe_history({"history": [{"role": "user", "content": content}]})
        assert line == "Cliente: " + "x" * specialists._MAX_HISTORY_MESSAGE_CHARS + "…"

    def test_measurements(self):
        assert specialists.describe_measurements({}) == "não informadas"
        assert specialists.describe_measurements({"buyer_measurements": {"waist": 80}}) == '{"waist": 80}'

    def test_item(self):
        assert "CAL-1" in specialists.describe_item({"item_id": "CAL-1"})
        assert "pergunte" in specialists.describe_item({})


class TestBuildInput:
    def test_includes_feedback_and_other_answers_only(self):
        state = {
            "message": "combina?",
            "rejection_reason": "faltou citar a bota",
            "agent_outputs": {
                "size_fit": {"text": "Serve no 40"},
                "style_consulting": {"text": "MINHA RESPOSTA ANTERIOR"},
            },
        }
        text = specialists._build_input("style_consulting", state)
        assert "combina?" in text
        assert "faltou citar a bota" in text
        assert "Serve no 40" in text
        assert "MINHA RESPOSTA ANTERIOR" not in text

    def test_first_attempt_has_no_feedback(self):
        text = specialists._build_input("size_fit", {"message": "serve?"})
        assert "Motivo:" not in text


class TestCatalogSkus:
    def test_collects_from_catalog_tools_excluding_context_piece(self):
        messages = [
            _tool("get_item_spec", {"id": "id-ctx", "sku": "CTX-1"}),
            _tool("search_catalog", [{"id": "a", "sku": "CAM-1"}, {"id": "b"}, {"id": "c", "sku": "CAL-2"}]),
            _tool("compare_fit", {"sku": "IGNORED"}),
        ]
        assert specialists._catalog_skus(messages, "CTX-1") == ["CAM-1", "CAL-2"]
        assert specialists._catalog_skus(messages, "id-ctx") == ["CAM-1", "CAL-2"]

    def test_tolerates_errors_and_invalid_json(self):
        messages = [
            ToolMessage(content="not json", name="search_catalog", tool_call_id="t"),
            _tool("get_item_spec", {"error": "Peça não encontrada"}),
            _tool("search_catalog", ["str", 1]),
        ]
        assert specialists._catalog_skus(messages, None) == []


class FakeAgent:
    def __init__(self, result):
        self.result = result
        self.inputs = []

    async def ainvoke(self, payload):
        self.inputs.append(payload)
        return self.result


def _run(monkeypatch, result, state=None):
    monkeypatch.setattr(specialists, "_agent", lambda intent: FakeAgent(result))
    return asyncio.run(specialists.run_specialist("style_consulting", state or {"message": "oi"}))


class TestRunSpecialist:
    def test_structured_skus_are_filtered_to_tool_results(self, monkeypatch):
        result = {
            "messages": [
                _tool("search_catalog", [{"id": "a", "sku": "CAM-1"}, {"id": "b", "sku": "CAL-2"}]),
                AIMessage(content=""),
            ],
            "structured_response": SpecialistAnswer(message="Use a camisa", skus=["CAL-2", "INVENTADO", "CAL-2"]),
        }
        answer, evidence, skus = _run(monkeypatch, result)
        assert answer == "Use a camisa"
        assert skus == ["CAL-2"]
        assert evidence.startswith("[search_catalog] ")

    def test_fallback_to_skus_cited_in_text(self, monkeypatch):
        result = {
            "messages": [
                _tool("search_catalog", [{"sku": "CAM-1"}, {"sku": "CAL-2"}]),
                AIMessage(content="Gostei da CAL-2"),
            ]
        }
        answer, _, skus = _run(monkeypatch, result)
        assert answer == "Gostei da CAL-2"
        assert skus == ["CAL-2"]

    def test_no_tools_called(self, monkeypatch):
        result = {"messages": [AIMessage(content="oi")], "structured_response": SpecialistAnswer(message="oi")}
        _, evidence, skus = _run(monkeypatch, result)
        assert evidence == "(nenhuma ferramenta foi chamada)"
        assert skus == []

    def test_evidence_is_capped_and_excludes_structured_output_tool(self, monkeypatch):
        result = {
            "messages": [
                ToolMessage(content="x" * 10_000, name="search_catalog", tool_call_id="t"),
                ToolMessage(content="SECRET", name="SpecialistAnswer", tool_call_id="u"),
            ],
            "structured_response": SpecialistAnswer(message="oi"),
        }
        _, evidence, _ = _run(monkeypatch, result)
        assert len(evidence) == specialists._MAX_EVIDENCE_CHARS
        assert "SECRET" not in evidence


def test_prompt_templates_format_without_errors():
    QUALITY_USER_PROMPT.format(
        intent="i", history="h", message="m", item="it", measurements="me", evidence="e", work_result="w"
    )
    # system prompts are sent as-is; they must not carry unfilled placeholders
    assert "{message}" not in TRIAGE_SYSTEM_PROMPT
