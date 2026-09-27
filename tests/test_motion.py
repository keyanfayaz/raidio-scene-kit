from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from raidio_scene.models import Layer
from raidio_scene.motion import ambient_elements, light_opacity, object_transform, radial_alpha


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
