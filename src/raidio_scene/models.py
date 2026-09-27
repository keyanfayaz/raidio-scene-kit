"""Canonical portable scene contract. No URLs, executable behavior, or account identity."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_RESOURCES = 32
MAX_LAYERS = 12
MAX_EDGE = 2048
MAX_RGBA_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 40 * 1024 * 1024
MAX_EXPANDED_BYTES = 80 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)


class Resource(StrictModel):
    path: str = Field(pattern=r"^resources/[a-z][a-z0-9_-]{0,63}\.(png|jpg)$")
    media_type: Literal["image/jpeg", "image/png"] = Field(alias="mediaType")
    width: int = Field(gt=0, le=MAX_EDGE)
    height: int = Field(gt=0, le=MAX_EDGE)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def extension(self) -> Resource:
        expected = ".png" if self.media_type == "image/png" else ".jpg"
        if not self.path.endswith(expected):
            raise ValueError("Resource path extension must match mediaType")
        return self


class Layer(StrictModel):
    id: Identifier
    kind: Literal["foreground", "object", "ambient", "light"]
    resource: Identifier | None = None
    mask: Identifier | None = None
    x: Unit = 0
    y: Unit = 0
    width: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 1
    height: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 1
    anchor_x: Unit = Field(default=0.5, alias="anchorX")
    anchor_y: Unit = Field(default=0.5, alias="anchorY")
    opacity: Unit = 1
    blend: Literal["normal", "screen"] = "normal"
    preset: Literal[
        "still",
        "sway",
        "cloth",
        "rotate",
        "drift",
        "flame",
        "rain",
        "mist",
        "dust",
        "stars",
        "steam",
        "reflection",
    ]
    amplitude: float = Field(default=0.01, ge=0, le=0.05, allow_inf_nan=False)
    speed: float = Field(default=1, ge=0.05, le=3, allow_inf_nan=False)
    phase: float = Field(default=0, ge=0, le=math.tau, allow_inf_nan=False)
    reaction: Literal["none", "energy", "attack", "sustained"] = "none"
    strength: Unit = 0.3
    color: str = Field(default="#FFD6A0", pattern=r"^#[0-9A-Fa-f]{6}$")

    @model_validator(mode="after")
    def behavior(self) -> Layer:
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("Layer bounds extend outside orientation")
        if self.kind in {"object", "foreground"} and self.resource is None:
            raise ValueError("Object and foreground layers require a resource")
        if self.kind == "foreground" and self.preset != "still":
            raise ValueError("Foreground layers must remain stationary")
        if self.kind == "object" and self.preset not in {
            "still",
            "sway",
            "cloth",
            "rotate",
            "drift",
            "flame",
        }:
            raise ValueError("Unsupported object motion")
        if self.kind == "ambient":
            if self.resource is not None or self.preset not in {
                "rain",
                "mist",
                "dust",
                "stars",
                "steam",
                "reflection",
            }:
                raise ValueError("Ambient layers use a procedural preset and no image resource")
        if self.kind == "light" and self.preset != "still":
            raise ValueError("Light layers remain stationary")
        if self.kind != "light" and self.reaction != "none":
            raise ValueError("Only light layers respond to music")
        return self


class Orientation(StrictModel):
    width: int = Field(gt=0, le=MAX_EDGE)
    height: int = Field(gt=0, le=MAX_EDGE)
    base: Identifier
    poster: Identifier
    layers: list[Layer] = Field(default_factory=list, max_length=MAX_LAYERS)

    @model_validator(mode="after")
    def unique_layers(self) -> Orientation:
        if len({layer.id for layer in self.layers}) != len(self.layers):
            raise ValueError("Layer IDs must be unique within an orientation")
        return self


class Provenance(StrictModel):
    author: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
        | None
    ) = None
    tool: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
        | None
    ) = None
    license: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
        | None
    ) = None
    source_description: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
        | None
    ) = Field(default=None, alias="sourceDescription")


class SceneManifest(StrictModel):
    version: Literal[2]
    title: str = Field(min_length=1, max_length=100)
    provenance: Provenance | None = None
    resources: dict[Identifier, Resource] = Field(min_length=2, max_length=MAX_RESOURCES)
    landscape: Orientation
    portrait: Orientation

    @model_validator(mode="after")
    def references(self) -> SceneManifest:
        if not self.title.strip():
            raise ValueError("Scene title must not be blank")
        paths = [resource.path for resource in self.resources.values()]
        if len(paths) != len(set(paths)):
            raise ValueError("Each resource must have a distinct path")
        memory = sum(r.width * r.height * 4 for r in self.resources.values())
        if memory > MAX_RGBA_BYTES:
            raise ValueError("Scene exceeds the 64 MiB decoded RGBA budget")
        used: set[str] = set()
        for orientation in (self.landscape, self.portrait):
            refs = {orientation.base, orientation.poster}
            for layer in orientation.layers:
                refs.update(ref for ref in (layer.resource, layer.mask) if ref is not None)
            missing = refs - self.resources.keys()
            if missing:
                raise ValueError(f"Missing referenced resources: {sorted(missing)}")
            used.update(refs)
            for ref in (orientation.base, orientation.poster):
                resource = self.resources[ref]
                if resource.media_type != "image/jpeg":
                    raise ValueError("Base and poster resources must be JPEG")
                if (resource.width, resource.height) != (orientation.width, orientation.height):
                    raise ValueError(f"Resource {ref} dimensions must match its orientation")
            for layer in orientation.layers:
                if layer.kind == "object" and layer.resource:
                    if self.resources[layer.resource].media_type != "image/png":
                        raise ValueError("Independent objects require transparent PNG resources")
                if layer.mask:
                    resource = self.resources[layer.mask]
                    if resource.media_type != "image/png" or (resource.width, resource.height) != (
                        orientation.width,
                        orientation.height,
                    ):
                        raise ValueError("Masks must be full-orientation PNG alpha coverage")
        if unused := self.resources.keys() - used:
            raise ValueError(f"Unreferenced resources: {sorted(unused)}")
        return self
