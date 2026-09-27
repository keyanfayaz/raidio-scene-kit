from __future__ import annotations

import hashlib
import io
import json
import math
import stat
import struct
import zipfile
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin
from pydantic import ValidationError

from raidio_scene import (
    SceneBundle,
    SceneError,
    SceneManifest,
    normalize_bundle,
    pack,
    read_package,
    render_posters,
    validate_directory,
)
from raidio_scene.cli import initialize, main
from raidio_scene.preview import preview_html


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    path = tmp_path / "scene"
    initialize(path)
    return path


def archive_bytes(entries: list[tuple[str | zipfile.ZipInfo, bytes]], method: int = 0) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=method) as archive:
        for key, data in entries:
            archive.writestr(key, data)
    return output.getvalue()


def entries(data: bytes) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return [(key, archive.read(key)) for key in archive.namelist()]


def test_roundtrip_reproducible_stored_archive(directory: Path) -> None:
    first = pack(directory)
    assert first == pack(directory)
    loaded = read_package(first)
    assert loaded.manifest.version == 2
    assert loaded.manifest.landscape.layers[0].kind == "ambient"
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert all(entry.compress_type == 0 for entry in archive.infolist())


@pytest.mark.parametrize("name", ["../escape", "/tmp/escape", "resources/../escape", "program.js"])
def test_archive_cannot_include_extra_or_traversing_paths(directory: Path, name: str) -> None:
    bad = archive_bytes([*entries(pack(directory)), (name, b"arbitrary")])
    with pytest.raises(SceneError, match="exactly match"):
        read_package(bad)


def test_archive_rejects_duplicates_links_and_compression(directory: Path) -> None:
    content = entries(pack(directory))
    with pytest.warns(UserWarning), pytest.raises(SceneError, match="Duplicate"):
        read_package(archive_bytes([*content, content[0]]))
    link = zipfile.ZipInfo("scene.json")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(SceneError, match="regular"):
        read_package(archive_bytes([(link, b"other")]))
    with pytest.raises(SceneError, match="regular"):
        read_package(archive_bytes(content, zipfile.ZIP_DEFLATED))


def test_central_directory_is_bounded_before_zipfile_allocation(
    directory: Path, monkeypatch
) -> None:
    original = pack(directory)
    giant_count = bytearray(original)
    struct.pack_into("<HH", giant_count, len(giant_count) - 14, 65535, 65535)
    forged_small = bytearray(original)
    struct.pack_into("<HH", forged_small, len(forged_small) - 14, 1, 1)

    def never_construct(*args, **kwargs):
        raise AssertionError("Untrusted central directory reached ZipFile allocation")

    monkeypatch.setattr(zipfile, "ZipFile", never_construct)
    with pytest.raises(SceneError, match="directory"):
        read_package(bytes(giant_count))
    with pytest.raises(SceneError, match="entry count"):
        read_package(bytes(forged_small))


def test_data_descriptors_and_zip_comments_are_rejected(directory: Path) -> None:
    original = bytearray(pack(directory))
    central = original.index(b"PK\x01\x02")
    struct.pack_into("<H", original, central + 8, 8)
    with pytest.raises(SceneError, match="canonical"):
        read_package(bytes(original))
    original = bytearray(pack(directory))
    struct.pack_into("<H", original, len(original) - 2, 1)
    original.extend(b"x")
    with pytest.raises(SceneError, match="directory"):
        read_package(bytes(original))


def test_hash_and_decoded_format_are_authoritative(directory: Path) -> None:
    bundle = validate_directory(directory)
    value = bundle.manifest.model_dump(by_alias=True)
    key = bundle.manifest.landscape.base
    path = bundle.manifest.resources[key].path
    corrupted = [
        (name, data + b"changed" if name == path else data)
        for name, data in entries(pack(directory))
    ]
    with pytest.raises(SceneError, match="SHA-256"):
        read_package(archive_bytes(corrupted))
    value["resources"][key]["sha256"] = hashlib.sha256(b"not an image").hexdigest()
    data = [
        ("scene.json", json.dumps(value).encode()),
        *(
            (
                resource.path,
                b"not an image" if resource_key == key else bundle.resources[resource_key],
            )
            for resource_key, resource in bundle.manifest.resources.items()
        ),
    ]
    with pytest.raises(SceneError, match="still image"):
        read_package(archive_bytes(data))


def test_reject_duplicate_json_and_external_url(directory: Path) -> None:
    data = entries(pack(directory))
    original = dict(data)["scene.json"]
    duplicate = b'{"version":2,' + original[1:]
    with pytest.raises(SceneError, match="Duplicate JSON"):
        read_package(
            archive_bytes(
                [(key, duplicate if key == "scene.json" else value) for key, value in data]
            )
        )
    value = json.loads(original)
    value["resources"]["landscape-base"]["url"] = "https://example.invalid/art.jpg"
    with pytest.raises(ValidationError):
        SceneManifest.model_validate(value)


def test_portable_manifest_requires_version_and_wire_field_names(directory: Path) -> None:
    data = entries(pack(directory))
    value = json.loads(dict(data)["scene.json"])
    del value["version"]
    with pytest.raises(ValidationError):
        SceneManifest.model_validate(value)
    value["version"] = 2
    resource = value["resources"]["landscape-base"]
    resource["media_type"] = resource.pop("mediaType")
    with pytest.raises(SceneError, match="camelCase"):
        read_package(
            archive_bytes(
                [
                    (key, json.dumps(value).encode() if key == "scene.json" else raw)
                    for key, raw in data
                ]
            )
        )


def test_scene_layer_geometry_and_budget(directory: Path) -> None:
    source = validate_directory(directory).manifest.model_dump(by_alias=True)
    source["landscape"]["layers"][0]["x"] = 0.9
    with pytest.raises(ValidationError, match="outside"):
        SceneManifest.model_validate(source)
    source["landscape"]["layers"][0]["x"] = 0
    source["landscape"]["layers"][0]["speed"] = float("nan")
    with pytest.raises(ValidationError):
        SceneManifest.model_validate(source)
    source["landscape"]["layers"][0]["speed"] = 1
    source["landscape"]["layers"][0]["reaction"] = "energy"
    with pytest.raises(ValidationError, match="Only light"):
        SceneManifest.model_validate(source)


def test_alpha_survives_normalization_metadata_does_not(directory: Path) -> None:
    bundle = validate_directory(directory)
    value = bundle.manifest.model_dump(by_alias=True)
    image = Image.new("RGBA", (16, 16), (90, 150, 190, 0))
    image.putpixel((5, 5), (10, 20, 30, 123))
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private_location", "must disappear")
    image.save(output, format="PNG", pnginfo=metadata)
    raw = output.getvalue()
    value["resources"]["cutout"] = {
        "path": "resources/cutout.png",
        "mediaType": "image/png",
        "width": 16,
        "height": 16,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    value["landscape"]["layers"].append(
        {
            "id": "cutout",
            "kind": "object",
            "preset": "sway",
            "resource": "cutout",
        }
    )
    clean = normalize_bundle(
        SceneManifest.model_validate(value), {**bundle.resources, "cutout": raw}
    )
    with Image.open(io.BytesIO(clean.resources["cutout"])) as decoded:
        assert decoded.getpixel((5, 5)) == (10, 20, 30, 123)
        assert decoded.getpixel((0, 0))[3] == 0
        assert "private_location" not in decoded.info


def test_masks_are_orientation_sized_and_png(directory: Path) -> None:
    source = validate_directory(directory).manifest.model_dump(by_alias=True)
    source["landscape"]["layers"][0]["mask"] = "landscape-base"
    with pytest.raises(ValidationError, match="PNG alpha"):
        SceneManifest.model_validate(source)


def test_rgb_masks_and_opaque_objects_do_not_gain_false_alpha(directory: Path) -> None:
    bundle = validate_directory(directory)
    value = bundle.manifest.model_dump(by_alias=True)
    image = Image.new("RGB", (576, 384), "white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    data = output.getvalue()
    value["resources"]["coverage"] = {
        "path": "resources/coverage.png",
        "mediaType": "image/png",
        "width": 576,
        "height": 384,
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    value["landscape"]["layers"][0]["mask"] = "coverage"
    with pytest.raises(SceneError, match="alpha coverage"):
        normalize_bundle(
            SceneManifest.model_validate(value), {**bundle.resources, "coverage": data}
        )
    del value["landscape"]["layers"][0]["mask"]
    value["landscape"]["layers"].append(
        {
            "id": "object",
            "kind": "object",
            "resource": "coverage",
            "preset": "sway",
        }
    )
    with pytest.raises(SceneError, match="transparent pixels"):
        normalize_bundle(
            SceneManifest.model_validate(value), {**bundle.resources, "coverage": data}
        )


def test_base_and_poster_cannot_be_png(directory: Path) -> None:
    value = validate_directory(directory).manifest.model_dump(by_alias=True)
    value["resources"]["landscape-base"].update(
        path="resources/landscape-base.png",
        mediaType="image/png",
    )
    with pytest.raises(ValidationError, match="must be JPEG"):
        SceneManifest.model_validate(value)


def test_resting_poster_applies_phase_before_nonuniform_rotate_scaling(directory: Path) -> None:
    bundle = validate_directory(directory)
    value = bundle.manifest.model_dump(by_alias=True)
    image = Image.new("RGBA", (32, 32))
    for y in range(6, 14):
        for x in range(12, 20):
            image.putpixel((x, y), (255, 0, 0, 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    data = output.getvalue()
    value["resources"]["detail"] = {
        "path": "resources/detail.png",
        "mediaType": "image/png",
        "width": 32,
        "height": 32,
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    value["landscape"]["layers"] = [
        {
            "id": "record",
            "kind": "object",
            "resource": "detail",
            "preset": "rotate",
            "x": 0.2,
            "y": 0.2,
            "width": 0.6,
            "height": 0.2,
            "phase": math.pi / 2,
        }
    ]
    scene = normalize_bundle(
        SceneManifest.model_validate(value), {**bundle.resources, "detail": data}
    )
    rendered = render_posters(scene)
    with Image.open(io.BytesIO(rendered.resources["landscape-poster"])) as poster:
        # A spot above the source center rotates right, remaining inside the shallow ellipse.
        x, y = round((0.2 + 0.6 * (1 - 10 / 32)) * 576), round((0.2 + 0.2 * 0.5) * 384)
        red, green, blue = poster.getpixel((x, y))
        assert red > 220 and green < 30 and blue < 30


def test_decoded_budget_cannot_hide_in_small_compressed_files(directory: Path) -> None:
    value = validate_directory(directory).manifest.model_dump(by_alias=True)
    for resource in value["resources"].values():
        resource.update(width=2048, height=2048)
    for name in ("landscape", "portrait"):
        value[name].update(width=2048, height=2048)
    value["resources"]["extra"] = {
        "path": "resources/extra.png",
        "mediaType": "image/png",
        "width": 1,
        "height": 1,
        "sha256": "0" * 64,
    }
    value["landscape"]["layers"].append(
        {
            "id": "extra",
            "kind": "foreground",
            "preset": "still",
            "resource": "extra",
        }
    )
    with pytest.raises(ValidationError, match="64 MiB"):
        SceneManifest.model_validate(value)


def test_directory_symlink_not_followed(directory: Path) -> None:
    source = directory / "resources" / "landscape-base.jpg"
    data = source.read_bytes()
    source.unlink()
    target = directory.parent / "private.jpg"
    target.write_bytes(data)
    source.symlink_to(target)
    with pytest.raises(SceneError, match="symlink"):
        validate_directory(directory)


def test_cli_returns_json_error_and_does_not_overwrite(
    directory: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("sys.argv", ["raidio-scene", "validate", str(directory), "--json"])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
    (directory / "scene.json").write_text("{invalid}")
    assert main() == 1
    error = json.loads(capsys.readouterr().out)
    assert error["errors"][0]["code"] == "manifest_invalid"
    with pytest.raises(SceneError, match="never overwritten"):
        initialize(directory)


def test_title_is_inert_in_preview(directory: Path) -> None:
    bundle = validate_directory(directory)
    title = '</script><script>alert("injection")</script>'
    manifest = bundle.manifest.model_copy(update={"title": title})
    html = preview_html(SceneBundle(manifest, bundle.resources))
    assert title not in html
    assert "\\u003c/script>" in html
    assert "textContent=scene.title" in html


def test_exported_schema_matches_canonical_models() -> None:
    path = Path(__file__).parent.parent / "schema" / "scene-v2.schema.json"
    assert json.loads(path.read_text()) == SceneManifest.model_json_schema(by_alias=True)


def test_intentional_provenance_roundtrips_and_remains_optional(directory: Path) -> None:
    bundle = read_package(pack(directory))
    assert bundle.manifest.provenance is not None
    assert bundle.manifest.provenance.license == "MIT"
    cleaned = normalize_bundle(bundle.manifest, bundle.resources)
    assert cleaned.manifest.provenance == bundle.manifest.provenance
    value = bundle.manifest.model_dump(by_alias=True)
    del value["provenance"]
    assert SceneManifest.model_validate(value).provenance is None
    value["provenance"] = {"author": "a" * 121}
    with pytest.raises(ValidationError):
        SceneManifest.model_validate(value)
    value["provenance"] = {"sourceDescription": " ", "apiKey": "not-allowed"}
    with pytest.raises(ValidationError):
        SceneManifest.model_validate(value)
