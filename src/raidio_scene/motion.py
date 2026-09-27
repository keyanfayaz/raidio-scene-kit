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


def reaction_signal(reaction: str, signals: dict[str, float]) -> float:
    """Attack preserves room energy while adding the causal attack pulse."""
    if reaction == "attack":
        return .25 * signals["energy"] + .75 * signals["attack"]
    if reaction in {"energy", "sustained"}:
        return signals[reaction]
    return 0


def preview_signals(energy: float, accent_age: float | None) -> dict[str, float]:
    """An explicitly simulated musical accent for authoring, never beat detection.

    Energy rises quickly, sustained light blooms more slowly, and an attack pulse
    decays on the native detector's 130 ms timescale. A level of 1 is full-scale.
    """
    baseline = min(1, max(0, energy))
    if accent_age is None or accent_age < 0:
        return {"energy": baseline, "sustained": baseline, "attack": 0}

    def pulse(rise: float, decay: float) -> float:
        peak_time = rise * math.log(1 + decay / rise)
        peak = (1 - math.exp(-peak_time / rise)) * math.exp(-peak_time / decay)
        return min(1, (1 - math.exp(-accent_age / rise)) * math.exp(-accent_age / decay) / peak)

    return {
        "energy": baseline + (1 - baseline) * pulse(.04, .45),
        "sustained": baseline + (1 - baseline) * pulse(.25, 1.1),
        "attack": math.exp(-accent_age / .13),
    }


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
    if preset == "meteors":
        for lane in range(2):
            age = (time + lane * 4.5) % 9
            if age >= 1.15:
                continue
            progress = age / 1.15
            envelope = math.sin(math.pi * progress)
            head_x = left + width * (0.12 + 0.40 * lane + 0.42 * progress)
            head_y = top + height * (0.10 + 0.16 * lane + 0.48 * progress)
            for segment in range(6):
                near = segment / 6
                result.append(
                    {
                        "kind": "line",
                        "x": head_x - width * 0.12 * near,
                        "y": head_y - height * 0.18 * near,
                        "width": -width * 0.12 / 6,
                        "height": -height * 0.18 / 6,
                        "opacity": envelope * 0.75 * (1 - near) ** 1.8,
                        "lineWidth": 1 + 1.1 * (1 - near),
                    }
                )
            result.append(
                {
                    "kind": "ellipse",
                    "x": head_x - 2,
                    "y": head_y - 2,
                    "width": 4.0,
                    "height": 4.0,
                    "opacity": envelope * 0.8,
                }
            )
            result.append(
                {
                    "kind": "glow",
                    "x": head_x - 7,
                    "y": head_y - 7,
                    "width": 14.0,
                    "height": 14.0,
                    "opacity": envelope * 0.16,
                }
            )
        return result
    if preset == "reflection":
        for index in range(18):
            seed = ((index * 7919 + 13) % 997) / 997
            across = ((index * 139 + 71) % 997) / 997
            travel = (index / 18 + time * 0.012) % 1
            wave = math.sin(time * 0.6 + seed * 13)
            ripple_width = width * (0.17 + seed * 0.24) * (1 + 0.12 * math.sin(time * 0.45 + index))
            center_x = left + width * (0.15 + 0.7 * across + 0.08 * wave)
            result.append(
                {
                    "kind": "ellipse",
                    "x": center_x - ripple_width / 2,
                    "y": top + travel * height,
                    "width": ripple_width,
                    "height": 1.1 + seed * 0.9,
                    "opacity": math.sin(travel * math.pi)
                    * (0.25 + 0.35 * (0.5 + 0.5 * math.sin(time * 0.55 + index * 1.7))),
                }
            )
        return result
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
