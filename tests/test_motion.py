from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from raidio_scene.models import Layer
from raidio_scene.motion import (
    ambient_elements,
    light_opacity,
    object_transform,
    preview_signals,
    radial_alpha,
    reaction_signal,
)


def layer(preset: str, **values: object) -> Layer:
    return Layer.model_validate(
        {
            "id": "detail",
            "kind": "object",
            "resource": "sprite",
            "preset": preset,
            "x": 0.2,
            "y": 0.3,
            "width": 0.4,
            "height": 0.2,
            **values,
        }
    )


def test_continuous_rotation_preserves_perspective_ellipse() -> None:
    matrix = object_transform(layer("rotate"), 200, 100, math.pi / 2)
    assert matrix.point(0.5, 0.5) == pytest.approx((80, 40))
    assert matrix.point(1, 0.5) == pytest.approx((80, 50))
    assert matrix.point(0.5, 1) == pytest.approx((40, 40))
    second = object_transform(layer("rotate"), 200, 100, math.pi)
    assert second.point(1, 0.5) == pytest.approx((40, 40))


def test_cloth_is_anchored_and_phase_is_applied_to_rest() -> None:
    matrix = object_transform(layer("cloth", phase=math.pi / 2, anchorY=0.0), 200, 100, 0)
    assert matrix.point(0, 0) == pytest.approx((40, 30))
    assert matrix.point(1, 0) == pytest.approx((120, 30))
    assert matrix.point(1, 1) == pytest.approx((120.2, 50))


def test_flame_keeps_base_anchored() -> None:
    matrix = object_transform(layer("flame", phase=math.pi / 6, anchorY=1.0), 200, 100, 0)
    assert matrix.point(0.5, 1) == pytest.approx((80, 50))
    assert matrix.point(0.5, 0) == pytest.approx((80, 29.8))


def test_reference_light_and_radial_edges() -> None:
    assert light_opacity(0.1, 0.2, 0.5) == pytest.approx(0.19)
    assert light_opacity(0.1, 0.2, 0) == 0.1
    assert radial_alpha(0.5, 0.5) == 255
    assert radial_alpha(0.75, 0.5) == 128
    assert radial_alpha(0, 0.5) == 0
    assert radial_alpha(0, 0) == 0


def test_cross_language_conformance_fixture() -> None:
    fixture = Path(__file__).parent.parent / "examples" / "motion-conformance.json"
    for case in json.loads(fixture.read_text())["cases"]:
        matrix = object_transform(
            Layer.model_validate(case["layer"]), case["width"], case["height"], case["elapsed"]
        )
        assert [matrix.a, matrix.b, matrix.c, matrix.d, matrix.tx, matrix.ty] == pytest.approx(
            case["affine"],
            abs=1e-10,
        )


def test_ambient_recipe_matches_native_and_browser_fixture() -> None:
    fixture = Path(__file__).parent.parent / "examples" / "ambient-conformance.json"
    for case in json.loads(fixture.read_text())["cases"]:
        elements = ambient_elements(case["preset"], case["bounds"], case["time"])
        assert len(elements) == case["count"]
        for sample in case["samples"]:
            actual = elements[sample["index"]]
            assert actual["kind"] == sample["element"]["kind"]
            for key, value in actual.items():
                if key != "kind":
                    assert value == pytest.approx(sample["element"][key], abs=1e-10)


def test_reaction_mapping_and_preview_signals_match_conformance_fixture() -> None:
    fixture = Path(__file__).parent.parent / "examples" / "reaction-conformance.json"
    values = json.loads(fixture.read_text())
    for case in values["cases"]:
        assert reaction_signal(case["reaction"], case["signals"]) == pytest.approx(case["expected"])
    for case in values["previewCases"]:
        assert preview_signals(case["energy"], case["age"]) == pytest.approx(case["signals"])


def test_simulated_accent_exercises_all_channels_without_hiding_full_scale() -> None:
    steady = preview_signals(0.35, None)
    peak = preview_signals(0.35, 0.1)
    for reaction in ("energy", "attack", "sustained"):
        assert reaction_signal(reaction, peak) > reaction_signal(reaction, steady) + 0.2
    assert preview_signals(0.35, 6)["energy"] == pytest.approx(0.35, abs=0.00001)
    assert preview_signals(0.35, 6)["sustained"] == pytest.approx(0.35, abs=0.006)
    full_steady, full_accent = preview_signals(1, None), preview_signals(1, 0)
    assert full_accent["energy"] == full_accent["sustained"] == 1
    assert reaction_signal("attack", full_steady) == 0.25
    assert reaction_signal("attack", full_accent) == 1
    assert reaction_signal("none", full_accent) == 0


def test_meteors_have_sparse_smooth_flights_and_diagonal_tails() -> None:
    bounds = {"x": 20.0, "y": 10.0, "width": 500.0, "height": 300.0}
    start = ambient_elements("meteors", bounds, 0)
    peak = ambient_elements("meteors", bounds, 1.15 / 2)
    tail = peak[:6]
    assert len(peak) == 8
    assert all(element["opacity"] == 0 for element in start)
    assert all(float(element["width"]) < 0 and float(element["height"]) < 0 for element in tail)
    assert all(
        float(a["opacity"]) > float(b["opacity"]) for a, b in zip(tail, tail[1:], strict=False)
    )
    assert ambient_elements("meteors", bounds, 3.7) == []
    # At maximum speed, the two flight starts remain 1.5 seconds apart.
    assert len(ambient_elements("meteors", bounds, 4.5 + 1.15 / 2)) == 8
    assert ambient_elements("meteors", bounds, 9.0) == start


def test_reflection_is_elongated_water_ripples_with_slow_visible_motion() -> None:
    bounds = {"x": 20.0, "y": 10.0, "width": 500.0, "height": 300.0}
    initial = ambient_elements("reflection", bounds, 0)
    later = ambient_elements("reflection", bounds, 2)
    assert len(initial) == 18
    assert all(float(item["width"]) > 40 * float(item["height"]) for item in initial)
    assert max(float(item["opacity"]) for item in initial) > 0.5
    assert any(abs(float(a["x"]) - float(b["x"])) > 5 for a, b in zip(initial, later, strict=True))
    assert all(0 <= float(item["opacity"]) <= 1 for item in later)
