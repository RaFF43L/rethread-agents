"""Pydantic schemas for the thrift-store catalog.

Measurement convention (applies to garments AND buyers):
- Circumferences (chest, waist, hip, thigh) are the FULL round, in cm.
  If you measure the garment lying flat, double the value before saving.
- Lengths (shoulder, sleeve, length, rise, inseam, hem) are linear, in cm.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ItemStatus = Literal["draft", "active", "reserved", "sold"]
Department = Literal["feminino", "masculino", "unissex"]
# How much the fabric gives — widens the "tight" tolerance in compare_fit.
Stretch = Literal["none", "low", "medium", "high"]


class Measurements(BaseModel):
    """Measurements in cm. Every field is optional: fill them in as you measure."""

    chest: float | None = Field(default=None, gt=0, description="Busto/tórax — circunferência (cm)")
    waist: float | None = Field(default=None, gt=0, description="Cintura — circunferência (cm)")
    hip: float | None = Field(default=None, gt=0, description="Quadril — circunferência (cm)")
    thigh: float | None = Field(default=None, gt=0, description="Coxa — circunferência (cm)")
    shoulder: float | None = Field(default=None, gt=0, description="Ombro a ombro (cm)")
    sleeve: float | None = Field(default=None, gt=0, description="Comprimento da manga (cm)")
    length: float | None = Field(default=None, gt=0, description="Comprimento total (cm)")
    rise: float | None = Field(default=None, gt=0, description="Gancho (cm)")
    inseam: float | None = Field(default=None, gt=0, description="Entrepernas (cm)")
    hem: float | None = Field(default=None, gt=0, description="Boca/barra — largura (cm)")


MEASUREMENT_FIELDS = tuple(Measurements.model_fields)


class ItemBase(BaseModel):
    sku: str | None = Field(default=None, max_length=64, description="Código interno da peça")
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    category: str = Field(
        ..., max_length=50, description="Ex.: calça, camisa, vestido, saia, jaqueta, blusa, short"
    )
    department: Department | None = None
    brand: str | None = Field(default=None, max_length=100)
    era: str | None = Field(default=None, max_length=30, description="Ex.: anos 80, anos 90, Y2K")
    label_size: str | None = Field(default=None, max_length=20, description="Tamanho da etiqueta")
    size_region: str = Field(default="BR", max_length=5)
    color: str | None = Field(default=None, max_length=60)
    fabric: str | None = Field(default=None, max_length=100)
    stretch: Stretch | None = None
    style_tags: list[str] = Field(default_factory=list, description="Ex.: vintage, minimalista, boho")
    occasions: list[str] = Field(default_factory=list, description="Ex.: trabalho, festa, dia a dia")
    condition: str | None = Field(default=None, max_length=60)
    price: float | None = Field(default=None, ge=0)
    status: ItemStatus = "active"
    notes: str | None = Field(default=None, description="Observações de caimento/defeitos")
    measurements: Measurements = Field(default_factory=Measurements)


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    """Partial update. `measurements` is MERGED into what is already saved;
    send a measurement as null to remove it."""

    sku: str | None = None
    title: str | None = None
    description: str | None = None
    category: str | None = None
    department: Department | None = None
    brand: str | None = None
    era: str | None = None
    label_size: str | None = None
    size_region: str | None = None
    color: str | None = None
    fabric: str | None = None
    stretch: Stretch | None = None
    style_tags: list[str] | None = None
    occasions: list[str] | None = None
    condition: str | None = None
    price: float | None = None
    status: ItemStatus | None = None
    notes: str | None = None
    measurements: Measurements | None = None


class ItemOut(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    has_embedding: bool = False
    created_at: datetime
    updated_at: datetime


class ItemSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Descrição livre de estilo/cor/ocasião")
    k: int | None = Field(default=None, ge=1, le=50)
    category: str | None = None
    department: Department | None = None
    max_price: float | None = Field(default=None, ge=0)


class ItemSearchHit(BaseModel):
    item: ItemOut
    similarity: float


class SizeEquivalenceIn(BaseModel):
    category: str = Field(..., max_length=50)
    label_size: str = Field(..., max_length=20)
    region: str = Field(default="BR", max_length=5)
    department: Department | None = None
    brand: str | None = Field(default=None, max_length=100, description="Vazio = tabela genérica")
    era: str | None = Field(default=None, max_length=30, description="Vazio = qualquer época")
    measurements: dict[str, tuple[float, float]] = Field(
        ..., description='Faixas de medida do CORPO em cm. Ex.: {"waist": [74, 78]}'
    )
    notes: str | None = None

    @field_validator("measurements")
    @classmethod
    def _known_fields(cls, value: dict[str, tuple[float, float]]):
        unknown = set(value) - set(MEASUREMENT_FIELDS)
        if unknown:
            raise ValueError(f"Medidas desconhecidas: {sorted(unknown)}")
        return value


class SizeEquivalenceOut(SizeEquivalenceIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
