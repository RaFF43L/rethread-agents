import pytest

from catalog.fit import compare_fit


def _verdict(result, dimension):
    return next(c for c in result["comparisons"] if c["dimension"] == dimension)


@pytest.mark.parametrize(
    ("garment_chest", "expected"),
    [
        (89, "apertado"),  # ease -1, no stretch
        (90, "justo"),  # ease 0
        (94, "justo"),  # ease 4 = snug_max (inclusive)
        (94.5, "confortável"),
        (102, "confortável"),  # ease 12 = comfy_max (inclusive)
        (102.5, "folgado"),
    ],
)
def test_chest_thresholds(garment_chest, expected):
    result = compare_fit({"chest": garment_chest}, {"chest": 90})
    assert _verdict(result, "busto/tórax")["verdict"] == expected


@pytest.mark.parametrize(
    ("stretch", "expected"),
    [(None, "apertado"), ("none", "apertado"), ("low", "apertado"), ("medium", "justo"), ("high", "justo")],
)
def test_stretch_widens_tight_tolerance(stretch, expected):
    # garment 2 cm smaller than the body
    result = compare_fit({"waist": 78}, {"waist": 80}, stretch=stretch)
    assert _verdict(result, "cintura")["verdict"] == expected


def test_unknown_stretch_behaves_as_none():
    result = compare_fit({"waist": 78}, {"waist": 80}, stretch="super")
    assert _verdict(result, "cintura")["verdict"] == "apertado"


def test_ease_is_rounded():
    result = compare_fit({"hip": 100.04}, {"hip": 96})
    assert _verdict(result, "quadril")["ease_cm"] == 4.0


@pytest.mark.parametrize(
    ("garment", "expected"),
    [(42, "alinhado"), (44, "alinhado"), (44.5, "ombro caído"), (39.5, "apertado nos ombros")],
)
def test_shoulder(garment, expected):
    result = compare_fit({"shoulder": garment}, {"shoulder": 42})
    assert _verdict(result, "ombro a ombro")["verdict"] == expected


def test_lengths_report_surplus_and_shortfall():
    result = compare_fit({"sleeve": 62, "inseam": 75}, {"sleeve": 60, "inseam": 78})
    assert _verdict(result, "manga")["verdict"] == "sobra 2 cm"
    assert _verdict(result, "entrepernas")["verdict"] == "falta 3 cm"


def test_missing_garment_measurement_is_listed_not_compared():
    result = compare_fit({"chest": 100}, {"chest": 90, "waist": 80, "shoulder": 40, "sleeve": 60})
    assert result["missing_on_garment"] == ["cintura", "ombro a ombro", "manga"]
    assert [c["dimension"] for c in result["comparisons"]] == ["busto/tórax"]


def test_body_dimension_absent_is_ignored():
    result = compare_fit({"chest": 100, "waist": 80}, {"chest": 95})
    assert len(result["comparisons"]) == 1
    assert result["missing_on_garment"] == []


@pytest.mark.parametrize(
    ("garment", "body", "overall"),
    [
        ({}, {}, "sem dados suficientes"),
        ({"chest": 80}, {"chest": 90}, "provavelmente não serve (apertado)"),
        ({"shoulder": 38}, {"shoulder": 42}, "provavelmente não serve (apertado)"),
        # tight wins over loose
        ({"chest": 120, "waist": 70}, {"chest": 90, "waist": 80}, "provavelmente não serve (apertado)"),
        ({"chest": 120}, {"chest": 90}, "serve, com folga"),
        ({"shoulder": 48}, {"shoulder": 42}, "serve, com folga"),
        ({"chest": 98}, {"chest": 90}, "serve"),
        # lengths never make it "not fit"
        ({"length": 50}, {"length": 70}, "serve"),
    ],
)
def test_overall(garment, body, overall):
    assert compare_fit(garment, body)["overall"] == overall


def test_stretch_label():
    assert compare_fit({}, {})["stretch"] == "não informado"
    assert compare_fit({}, {}, stretch="low")["stretch"] == "low"
