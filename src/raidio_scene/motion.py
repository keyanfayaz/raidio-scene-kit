"""Reference transforms shared by authoring/posters; clients mirror these equations."""

from __future__ import annotations

import math
from dataclasses import dataclass

from raidio_scene.models import Layer


@dataclass(frozen=True)
class Affine:
    a: float
    b: float
    c: float
    d: float
    tx: float
    ty: float

    def point(self, x: float, y: float) -> tuple[float, float]:
        return self.a * x + self.c * y + self.tx, self.b * x + self.d * y + self.ty

    def inverse_pixels(self, width: int, height: int) -> tuple[float, ...]:
        determinant = self.a * self.d - self.b * self.c
        return (
            self.d * width / determinant,
            -self.c * width / determinant,
            (self.c * self.ty - self.d * self.tx) * width / determinant,
            -self.b * height / determinant,
            self.a * height / determinant,
            (self.b * self.tx - self.a * self.ty) * height / determinant,
        )


def object_transform(layer: Layer, width: int, height: int, elapsed: float) -> Affine:
    """Map normalized texture coordinates into source-image coordinates.

    Continuous rotate occurs before anisotropic rectangle scaling, preserving a
    perspective ellipse for records. Other motions transform the placed object.
    Static/poster composition evaluates elapsed=0, preserving authored phase.
    """
    sx, sy = width * layer.width, height * layer.height
    x = width * layer.x + sx * layer.anchor_x
    y = height * layer.y + sy * layer.anchor_y
    a, b, c, d = sx, 0.0, 0.0, sy
    t = elapsed * layer.speed + layer.phase
    if layer.kind == "object":
        if layer.preset == "rotate":
            a, b, c, d = sx * math.cos(t), sy * math.sin(t), -sx * math.sin(t), sy * math.cos(t)
        elif layer.preset == "sway":
            angle = layer.amplitude * math.sin(t)
            a, b, c, d = (
                sx * math.cos(angle),
                sx * math.sin(angle),
                -sy * math.sin(angle),
                sy * math.cos(angle),
            )
        elif layer.preset == "cloth":
            c = sy * layer.amplitude * math.sin(t)
        elif layer.preset == "drift":
            x += width * layer.amplitude * math.sin(t)
            y += height * layer.amplitude * 0.35 * math.sin(t * 0.73)
        elif layer.preset == "flame":
            d *= 1 + layer.amplitude * math.sin(t * 3)
    return Affine(
        a,
        b,
        c,
        d,
        x - a * layer.anchor_x - c * layer.anchor_y,
        y - b * layer.anchor_x - d * layer.anchor_y,
    )


def light_opacity(opacity: float, strength: float, signal: float) -> float:
    return min(1, max(0, opacity + strength * signal * (1 - opacity)))


def radial_alpha(x: float, y: float) -> int:
    """Coverage at a normalized texture position; linear Canvas radial stops."""
    return round(255 * max(0, 1 - math.hypot(2 * x - 1, 2 * y - 1)))


def ambient_elements(
    preset: str, bounds: dict[str, float], time: float
) -> list[dict[str, str | float]]:
    """Native/Canvas atmosphere in source-image coordinates, before layer opacity/mask.

    `time` already includes speed and phase. Line width/height are endpoint deltas;
    ellipse/glow width/height are bounding-box dimensions. No audio input is used.
    """
    left, top, width, height = (bounds[key] for key in ("x", "y", "width", "height"))
    result: list[dict[str, str | float]] = []
    if preset in {"mist", "steam"}:
        for index in range(8):
            seed = index * 2.399
            x = left + width * 0.5 + math.sin(time * 0.08 + seed) * width * 0.35
            y = top + height * 0.5 + math.cos(time * 0.05 + seed) * height * 0.22
            result.append(
                {
                    "kind": "glow",
                    "x": x - width * 0.38,
                    "y": y - height * 0.32,
                    "width": width * 0.76,
                    "height": height * 0.64,
                    "opacity": 0.14,
                }
            )
        return result
    for index in range(88 if preset == "rain" else 40):
        seed = ((index * 7919 + 13) % 997) / 997
        travel = (seed + time * (0.23 if preset == "rain" else 0.014)) % 1
        x = left + ((index * 139 + 71) % 997) / 997 * width + math.sin(time * 0.2 + seed * 13) * 3
        y = top + travel * height
        alpha = math.sin(travel * math.pi)
        if preset == "rain":
            result.append(
                {
                    "kind": "line",
                    "x": x,
                    "y": y,
                    "width": -1.5,
                    "height": 10 + seed * 18,
                    "opacity": alpha * 0.24,
                    "lineWidth": 0.8,
                }
            )
        elif preset == "reflection":
            wave = math.sin(time * 1.5 + index * 1.8)
            result.append(
                {
                    "kind": "ellipse",
                    "x": x + wave * 2,
                    "y": y,
                    "width": 3 + (wave + 1) * 4,
                    "height": 1.5,
                    "opacity": alpha * (0.25 + (wave + 1) * 0.15),
                }
            )
        else:
            radius = 1.3 if preset == "stars" else 1.8
            particle_y = (
                top + seed * height if preset == "stars" else top + height - travel * height
            )
            opacity = (
                0.35 + 0.15 * math.sin(time * 0.4 + seed * 12) if preset == "stars" else alpha * 0.4
            )
            result.append(
                {
                    "kind": "ellipse",
                    "x": x,
                    "y": particle_y,
                    "width": radius * 2,
                    "height": radius * 2,
                    "opacity": opacity,
                }
            )
    return result
