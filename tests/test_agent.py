from types import SimpleNamespace

import pytest
from conftest import FakeModel

from ai import agent
from ai.prompts import COMPOSE_PROMPT, NOT_APPROVED_NOTE
from ai.states import QualityResult, TriageResult


def _output(text, approved=True, attempts=1, skus=()):
    return {"text": text, "approved": approved, "attempts": attempts, "skus": list(skus)}


def test_graph_compiles_with_expected_nodes():
    nodes = set(agent.build_graph().get_graph().nodes)
    assert {"triage", "dispatch", "size_fit", "style_consulting", "quality", "compose"} <= nodes


class TestTriage:
    @pytest.mark.parametrize(
        ("intents", "expected"),
        [
            (["style_consulting", "size_fit", "size_fit"], ["size_fit", "style_consulting"]),
            (["style_consulting"], ["style_consulting"]),
            ([], ["style_consulting"]),
        ],
    )
    def test_intents_are_deduped_and_ordered(self, fake_llm, intents, expected):
        fake_llm(fast=FakeModel(TriageResult(intents=intents, reasoning="r")))
        out = agent.triage_node({"message": "oi"})
        assert out["intents"] == expected
        assert out["pending"] == expected
        assert out["current"] is None

    def test_item_and_history_reach_the_model(self, fake_llm):
        model = FakeModel(TriageResult(intents=["size_fit"], reasoning="r"))
        fake_llm(fast=model)
        agent.triage_node(
            {"message": "serve?", "item_id": "CAL-1", "history": [{"role": "user", "content": "oi"}]}
        )
        human = model.calls[0][1].content
        assert "CAL-1" in human
        assert "Cliente: oi" in human
        assert human.index("Cliente: oi") < human.index("serve?")


class TestDispatch:
    def test_first_call_pops_first_intent(self):
        out = agent.dispatch_node({"pending": ["size_fit", "style_consulting"], "current": None})
        assert out["current"] == "size_fit"
        assert out["pending"] == ["style_consulting"]
        assert "agent_outputs" not in out

    def test_stores_finished_specialist_and_resets_work(self):
        state = {
            "pending": [],
            "current": "size_fit",
            "work_result": "Mensagem ao cliente: Serve!",
            "quality_approved": True,
            "attempts": 2,
            "work_skus": ["CAM-1"],
            "rejection_reason": "x",
        }
        out = agent.dispatch_node(state)
        assert out["agent_outputs"] == {"size_fit": _output("Serve!", attempts=2, skus=["CAM-1"])}
        assert out["current"] is None
        assert out["attempts"] == 0
        assert out["rejection_reason"] == ""
        assert out["work_skus"] == []

    def test_does_not_mutate_state_queue(self):
        pending = ["size_fit", "style_consulting"]
        agent.dispatch_node({"pending": pending})
        assert pending == ["size_fit", "style_consulting"]


class TestRouters:
    def test_route_dispatch(self):
        assert agent.route_dispatch({"current": "size_fit"}) == "size_fit"
        assert agent.route_dispatch({"current": None}) == "compose"

    @pytest.mark.parametrize(
        ("approved", "attempts", "expected"),
        [(True, 1, "dispatch"), (False, 1, "style_consulting"), (False, 2, "style_consulting"), (False, 3, "dispatch")],
    )
    def test_route_after_quality(self, monkeypatch, approved, attempts, expected):
        monkeypatch.setattr(agent.envs, "max_attempts", 3)
        state = {"quality_approved": approved, "attempts": attempts, "current": "style_consulting"}
        assert agent.route_after_quality(state) == expected


class TestQuality:
    def test_rejection_reason_cleared_when_approved(self, fake_llm):
        fake_llm(judge=FakeModel(QualityResult(approved=True, rejection_reason="ignored")))
        out = agent.quality_node({"message": "oi", "current": "size_fit"})
        assert out == {
            "quality_approved": True,
            "rejection_reason": "",
            "metadata": {"size_fit_approved": True},
        }

    def test_rejected(self, fake_llm):
        fake_llm(judge=FakeModel(QualityResult(approved=False, rejection_reason="sem evidência")))
        out = agent.quality_node({"message": "oi", "current": "size_fit"})
        assert out["quality_approved"] is False
        assert out["rejection_reason"] == "sem evidência"


class TestCompose:
    def test_single_output_skips_the_model(self, fake_llm):
        fake_llm(fast=None)  # would crash if called
        out = agent.compose_node({"message": "oi", "agent_outputs": {"size_fit": _output("Serve!", skus=["A"])}})
        assert out == {"response": "Serve!", "skus": ["A"]}

    def test_multiple_outputs_are_merged_by_the_model(self, fake_llm):
        model = FakeModel(SimpleNamespace(content=[{"type": "text", "text": "Resposta unida"}]))
        fake_llm(fast=model)
        out = agent.compose_node(
            {
                "message": "serve e combina?",
                "agent_outputs": {
                    "style_consulting": _output("Combina", skus=["B", "A"]),
                    "size_fit": _output("Serve", skus=["A"]),
                },
            }
        )
        assert out["response"] == "Resposta unida"
        # fit first, deduped
        assert out["skus"] == ["A", "B"]
        prompt = model.calls[0][0].content
        assert prompt.index("size_fit") < prompt.index("style_consulting")

    def test_not_approved_note_uses_max_attempts(self, fake_llm):
        fake_llm(fast=FakeModel(SimpleNamespace(content="Unida")))
        out = agent.compose_node(
            {
                "message": "x",
                "agent_outputs": {
                    "size_fit": _output("a", approved=False, attempts=2),
                    "style_consulting": _output("b", approved=False, attempts=3),
                },
            }
        )
        assert out["response"] == "Unida" + NOT_APPROVED_NOTE.format(attempts=3)


def test_prompt_templates_format_without_errors():
    # A literal "{" in a prompt would only blow up at runtime
    COMPOSE_PROMPT.format(message="m", sections="s")
    NOT_APPROVED_NOTE.format(attempts=1)
