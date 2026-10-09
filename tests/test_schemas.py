import pytest
from pydantic import ValidationError

from actions.base import ChatRequest
from catalog.schemas import ItemCreate, ItemUpdate, Measurements, SizeEquivalenceIn


def test_measurements_must_be_positive():
    with pytest.raises(ValidationError):
        Measurements(chest=0)
    with pytest.raises(ValidationError):
        Measurements(waist=-1)


def test_item_create_defaults():
    item = ItemCreate(title="Calça", category="calça")
    assert item.status == "active"
    assert item.size_region == "BR"
    assert item.style_tags == []
    assert item.measurements.model_dump(exclude_none=True) == {}


def test_item_create_rejects_invalid_stretch_and_status():
    with pytest.raises(ValidationError):
        ItemCreate(title="x", category="calça", stretch="muito")
    with pytest.raises(ValidationError):
        ItemCreate(title="x", category="calça", status="vendido")


def test_item_update_keeps_explicit_null_measurements():
    # Explicit null must survive exclude_unset: it means "remove this measurement".
    update = ItemUpdate.model_validate({"measurements": {"waist": None, "hip": 100}})
    assert update.model_dump(exclude_unset=True) == {"measurements": {"waist": None, "hip": 100}}


def test_size_equivalence_rejects_unknown_measurements():
    with pytest.raises(ValidationError, match="Medidas desconhecidas"):
        SizeEquivalenceIn(category="calça", label_size="40", measurements={"cintura": (70, 74)})


def test_size_equivalence_accepts_known_measurements():
    row = SizeEquivalenceIn(category="calça", label_size="40", measurements={"waist": [74, 78]})
    assert row.measurements == {"waist": (74, 78)}


def test_chat_request_requires_message():
    with pytest.raises(ValidationError):
        ChatRequest(message="")
    with pytest.raises(ValidationError):
        ChatRequest(message="oi", session_id="")
