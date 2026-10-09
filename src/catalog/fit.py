"""Deterministic fit comparison (garment vs body measurements).

The numbers are computed here, not by the LLM: the Fit agent receives this
verdict and only explains it. Thresholds are heuristics in cm — tune them to
the way you measure your pieces.
"""

from __future__ import annotations

from typing import Any

# Circumference ease (garment - body), in cm: (snug_max, comfortable_max).
#   ease < -tolerance       -> apertado
#   -tolerance..snug_max    -> justo
#   snug_max..comfy_max     -> confortável
#   > comfy_max             -> folgado
CIRCUMFERENCE_EASE: dict[str, tuple[float, float]] = {
    "chest": (4, 12),
    "waist": (3, 8),
    "hip": (3, 10),
    "thigh": (3, 8),
}

# How many cm the garment can be SMALLER than the body and still close, by stretch.
STRETCH_TOLERANCE: dict[str, float] = {
    "none": 0,
    "low": 1,
    "medium": 3,
    "high": 6,
}

SHOULDER_TOLERANCE = 2.0

# Lengths are only reported (garment - body): positive = sobra, negative = falta.
LENGTH_FIELDS = ("sleeve", "length", "rise", "inseam")

LABELS = {
    "chest": "busto/tórax",
    "waist": "cintura",
    "hip": "quadril",
    "thigh": "coxa",
    "shoulder": "ombro a ombro",
    "sleeve": "manga",
    "length": "comprimento",
    "rise": "gancho",
    "inseam": "entrepernas",
}


def _circumference_verdict(ease: float, snug: float, comfy: float, tolerance: float) -> str:
    if ease < -tolerance:
        return "apertado"
    if ease <= snug:
        return "justo"
    if ease <= comfy:
        return "confortável"
    return "folgado"


def compare_fit(
    garment: dict[str, float],
    body: dict[str, float],
    stretch: str | None = None,
) -> dict[str, Any]:
    """Compares garment vs body measurements dimension by dimension."""
    tolerance = STRETCH_TOLERANCE.get(stretch or "none", 0)
    comparisons: list[dict[str, Any]] = []
    missing_on_garment: list[str] = []

    for dim, (snug, comfy) in CIRCUMFERENCE_EASE.items():
        b = body.get(dim)
        if b is None:
            continue
        g = garment.get(dim)
        if g is None:
            missing_on_garment.append(LABELS[dim])
            continue
        ease = round(g - b, 1)
        comparisons.append(
            {
                "dimension": LABELS[dim],
                "garment_cm": g,
                "body_cm": b,
                "ease_cm": ease,
                "verdict": _circumference_verdict(ease, snug, comfy, tolerance),
            }
        )

    if body.get("shoulder") is not None:
        g = garment.get("shoulder")
        if g is None:
            missing_on_garment.append(LABELS["shoulder"])
        else:
            diff = round(g - body["shoulder"], 1)
            if diff > SHOULDER_TOLERANCE:
                verdict = "ombro caído"
            elif diff < -SHOULDER_TOLERANCE:
                verdict = "apertado nos ombros"
            else:
                verdict = "alinhado"
            comparisons.append(
                {
                    "dimension": LABELS["shoulder"],
                    "garment_cm": g,
                    "body_cm": body["shoulder"],
                    "diff_cm": diff,
                    "verdict": verdict,
                }
            )

    for dim in LENGTH_FIELDS:
        b = body.get(dim)
        if b is None:
            continue
        g = garment.get(dim)
        if g is None:
            missing_on_garment.append(LABELS[dim])
            continue
        diff = round(g - b, 1)
        comparisons.append(
            {
                "dimension": LABELS[dim],
                "garment_cm": g,
                "body_cm": b,
                "diff_cm": diff,
                "verdict": f"sobra {diff} cm" if diff >= 0 else f"falta {-diff} cm",
            }
        )

    verdicts = {c["verdict"] for c in comparisons}
    if not comparisons:
        overall = "sem dados suficientes"
    elif "apertado" in verdicts or "apertado nos ombros" in verdicts:
        overall = "provavelmente não serve (apertado)"
    elif verdicts & {"folgado", "ombro caído"}:
        overall = "serve, com folga"
    else:
        overall = "serve"

    return {
        "overall": overall,
        "stretch": stretch or "não informado",
        "comparisons": comparisons,
        "missing_on_garment": missing_on_garment,
    }
