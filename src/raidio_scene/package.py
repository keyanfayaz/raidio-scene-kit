"""Bounded package parsing and lossless-alpha normalization; never extracts archives."""

from __future__ import annotations

import hashlib
import io
import json
import stat
import struct
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageOps
from pydantic import ValidationError

from raidio_scene.models import (
    MAX_ARCHIVE_BYTES,
    MAX_EDGE,
    MAX_EXPANDED_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_RESOURCES,
    SceneManifest,
)
from raidio_scene.motion import object_transform, radial_alpha


class SceneError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_scene", path: str = "scene.json"):
        super().__init__(message)
        self.code = code
        self.path = path

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": str(self)}


@dataclass(frozen=True)
class SceneBundle:
    manifest: SceneManifest
    # Keys are resource IDs, not paths. Bytes are never executed or fetched as URLs.
    resources: dict[str, bytes]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SceneError(f"Duplicate JSON key: {key}", code="duplicate_key")
        result[key] = value
    return result


def _manifest(data: bytes) -> SceneManifest:
    if len(data) > MAX_MANIFEST_BYTES:
        raise SceneError("Manifest exceeds 256 KiB", code="manifest_size")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
        manifest = SceneManifest.model_validate(value)

        # Python callers may use field names; portable JSON uses canonical aliases only.
        def canonical_keys(original: Any, encoded: Any) -> None:
            if isinstance(original, dict) and isinstance(encoded, dict):
                if not original.keys() <= encoded.keys():
                    raise SceneError("Portable JSON must use canonical camelCase field names")
                for key, item in original.items():
                    canonical_keys(item, encoded[key])
            elif isinstance(original, list) and isinstance(encoded, list):
                for item, rendered in zip(original, encoded, strict=True):
                    canonical_keys(item, rendered)

        canonical_keys(value, manifest.model_dump(mode="json", by_alias=True))
        return manifest
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValidationError) as error:
        raise SceneError(str(error), code="manifest_invalid") from error


def _image(data: bytes, path: str) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG"} or getattr(source, "n_frames", 1) != 1:
                    raise SceneError("Only JPEG and PNG stills are allowed", path=path)
                if max(source.size) > MAX_EDGE:
                    raise SceneError("Resource longest edge exceeds 2048 pixels", path=path)
                source.load()
                clean = ImageOps.exif_transpose(source).convert("RGBA")
                # Reconstruct pixels so text chunks, EXIF, profiles and location do not survive.
                return Image.frombytes("RGBA", clean.size, clean.tobytes())
    except (
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        if isinstance(error, SceneError):
            raise
        raise SceneError("Resource is not a supported still image", path=path) from error


def _validate(bundle: SceneBundle) -> SceneBundle:
    if bundle.resources.keys() != bundle.manifest.resources.keys():
        raise SceneError("Resource data must exactly match the manifest")
    total = 0
    for key, resource in bundle.manifest.resources.items():
        data = bundle.resources[key]
        total += len(data)
        if total > MAX_EXPANDED_BYTES:
            raise SceneError("Resources exceed 80 MiB", code="expanded_size")
        if hashlib.sha256(data).hexdigest() != resource.sha256:
            raise SceneError(
                "Resource SHA-256 does not match; repack after editing", path=resource.path
            )
        image = _image(data, resource.path)
        if image.size != (resource.width, resource.height):
            raise SceneError("Resource dimensions do not match manifest", path=resource.path)
        with Image.open(io.BytesIO(data)) as source:
            expected = "PNG" if resource.media_type == "image/png" else "JPEG"
            if source.format != expected:
                raise SceneError("Decoded format does not match mediaType", path=resource.path)
            has_alpha = "A" in source.getbands() or "transparency" in source.info
            if source.getexif().get(274, 1) != 1:
                raise SceneError(
                    "Package images must have normalized orientation; repack first",
                    path=resource.path,
                )
        for orientation in (bundle.manifest.landscape, bundle.manifest.portrait):
            if key in {orientation.base, orientation.poster}:
                if image.getchannel("A").getextrema() != (255, 255):
                    raise SceneError("Base and poster images must be opaque", path=resource.path)
            for layer in orientation.layers:
                if key == layer.mask:
                    low, high = image.getchannel("A").getextrema()
                    if not has_alpha or low == 255 or high == 0:
                        raise SceneError(
                            "Mask PNG needs visible and transparent alpha coverage",
                            path=resource.path,
                        )
                if key == layer.resource and layer.kind == "object":
                    low, high = image.getchannel("A").getextrema()
                    if not has_alpha or low == 255 or high == 0:
                        raise SceneError(
                            "Object PNG must contain transparent pixels", path=resource.path
                        )
    return bundle


def _directory(path: Path) -> SceneBundle:
    if not path.is_dir():
        raise SceneError("Choose a scene directory", path=str(path))
    manifest_path = path / "scene.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise SceneError("Missing regular scene.json file")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise SceneError("Manifest exceeds 256 KiB")
    manifest = _manifest(manifest_path.read_bytes())
    resources: dict[str, bytes] = {}
    total = 0
    for key, resource in manifest.resources.items():
        source = path / resource.path
        if source.parent.is_symlink() or source.is_symlink() or not source.is_file():
            raise SceneError("Resource must be a regular file, never a symlink", path=resource.path)
        total += source.stat().st_size
        if total > MAX_EXPANDED_BYTES:
            raise SceneError("Resources exceed 80 MiB", code="expanded_size")
        resources[key] = source.read_bytes()
    return SceneBundle(manifest, resources)


def validate_directory(path: str | Path) -> SceneBundle:
    """Validate hashes, format, geometry and budget without changing source files."""
    return _validate(_directory(Path(path)))


def _check_zip_index(data: bytes) -> None:
    """Bound central-directory parsing before ZipFile allocates a ZipInfo per entry.

    The format intentionally uses the small canonical subset emitted by pack():
    no ZIP64, data descriptors, comments, extra fields, preamble or trailing data.
    Local and central records must agree and cover the archive without gaps.
    """
    if len(data) < 22:
        raise SceneError("Truncated ZIP archive", code="invalid_archive")
    end = len(data) - 22
    signature, disk, central_disk, disk_count, count, size, start, comment = struct.unpack_from(
        "<4s4H2IH", data, end
    )
    if (
        signature != b"PK\x05\x06"
        or disk
        or central_disk
        or comment
        or count != disk_count
        or not 1 <= count <= MAX_RESOURCES + 1
        or size > (46 + 160) * (MAX_RESOURCES + 1)
        or start + size != end
    ):
        raise SceneError("Invalid or oversized ZIP directory", code="invalid_archive")
    cursor = start
    intervals = []
    for _ in range(count):
        if cursor + 46 > end:
            raise SceneError("Truncated ZIP directory", code="invalid_archive")
        header = struct.unpack_from("<4s6H3I5H2I", data, cursor)
        (
            _,
            _made,
            needed,
            flags,
            method,
            _time,
            _date,
            crc,
            compressed,
            expanded,
            name_length,
            extra_length,
            comment_length,
            record_disk,
            _attrs,
            _external,
            local,
        ) = header
        if (
            header[0] != b"PK\x01\x02"
            or needed > 20
            or flags & ~0x800
            or method != 0
            or not 1 <= name_length <= 160
            or extra_length
            or comment_length
            or record_disk
            or compressed != expanded
            or cursor + 46 + name_length > end
        ):
            raise SceneError(
                "Only canonical stored regular ZIP entries are allowed", code="unsafe_entry"
            )
        name = data[cursor + 46 : cursor + 46 + name_length]
        if local + 30 > start:
            raise SceneError("Invalid local ZIP entry", code="invalid_archive")
        local_header = struct.unpack_from("<4s5H3I2H", data, local)
        if (
            local_header[0] != b"PK\x03\x04"
            or local_header[1] != needed
            or local_header[2] != flags
            or local_header[3] != method
            or local_header[6:9] != (crc, compressed, expanded)
            or local_header[9] != name_length
            or local_header[10] != 0
            or data[local + 30 : local + 30 + name_length] != name
        ):
            raise SceneError("Local and central ZIP entries disagree", code="invalid_archive")
        stop = local + 30 + name_length + compressed
        if stop > start:
            raise SceneError("ZIP entries overlap the directory", code="invalid_archive")
        intervals.append((local, stop))
        cursor += 46 + name_length
    if cursor != end:
        raise SceneError("ZIP entry count does not match its directory", code="invalid_archive")
    previous = 0
    for begin, stop in sorted(intervals):
        if begin != previous:
            raise SceneError(
                "ZIP entries overlap or contain undeclared bytes", code="invalid_archive"
            )
        previous = stop
    if previous != start:
        raise SceneError("ZIP contains undeclared bytes", code="invalid_archive")


def read_package(data: bytes) -> SceneBundle:
    """Read a stored ZIP into memory under bounded limits. Never writes archive paths."""
    if not data or len(data) > MAX_ARCHIVE_BYTES:
        raise SceneError("Package must be nonempty and at most 40 MiB", code="archive_size")
    _check_zip_index(data)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_RESOURCES + 1:
                raise SceneError("Package contains too many entries", code="entry_count")
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)):
                raise SceneError("Duplicate archive paths", code="duplicate_entry")
            expanded = 0
            for entry in entries:
                mode = entry.external_attr >> 16
                if (
                    entry.is_dir()
                    or entry.flag_bits & 1
                    or stat.S_ISLNK(mode)
                    or (stat.S_IFMT(mode) not in {0, stat.S_IFREG})
                    or entry.compress_type != zipfile.ZIP_STORED
                    or entry.file_size != entry.compress_size
                ):
                    raise SceneError(
                        "Only unencrypted, stored regular ZIP entries are allowed",
                        path=entry.filename,
                        code="unsafe_entry",
                    )
                expanded += entry.file_size
                if expanded > MAX_EXPANDED_BYTES:
                    raise SceneError("Package exceeds 80 MiB expanded", code="expanded_size")
            if "scene.json" not in names:
                raise SceneError("Package is missing scene.json")
            if archive.getinfo("scene.json").file_size > MAX_MANIFEST_BYTES:
                raise SceneError("Manifest exceeds 256 KiB", code="manifest_size")
            manifest = _manifest(archive.read("scene.json"))
            expected = {"scene.json", *(resource.path for resource in manifest.resources.values())}
            if set(names) != expected:
                raise SceneError(
                    "Archive paths must exactly match referenced resources", code="unexpected_entry"
                )
            resources = {}
            actual = 0
            for key, resource in manifest.resources.items():
                with archive.open(resource.path) as stream:
                    raw = stream.read(MAX_EXPANDED_BYTES - actual + 1)
                    actual += len(raw)
                    if actual > MAX_EXPANDED_BYTES:
                        raise SceneError("Package exceeds 80 MiB expanded", code="expanded_size")
                    resources[key] = raw
            return _validate(SceneBundle(manifest, resources))
    except (zipfile.BadZipFile, EOFError, OSError, NotImplementedError, RuntimeError) as error:
        raise SceneError("Invalid or unsupported ZIP archive", code="invalid_archive") from error


def normalize_bundle(manifest: SceneManifest, resources: dict[str, bytes]) -> SceneBundle:
    """Strip metadata and refresh hashes; retain PNG alpha and authored coordinates."""
    if resources.keys() != manifest.resources.keys():
        raise SceneError("Resource data must exactly match the manifest")
    if sum(map(len, resources.values())) > MAX_EXPANDED_BYTES:
        raise SceneError("Resources exceed 80 MiB", code="expanded_size")
    value = manifest.model_dump(mode="json", by_alias=True)
    normalized: dict[str, bytes] = {}
    for key, resource in manifest.resources.items():
        image = _image(resources[key], resource.path)
        with Image.open(io.BytesIO(resources[key])) as source:
            has_alpha = "A" in source.getbands() or "transparency" in source.info
        for orientation in (manifest.landscape, manifest.portrait):
            for layer in orientation.layers:
                if layer.mask == key:
                    low, high = image.getchannel("A").getextrema()
                    if not has_alpha or low == 255 or high == 0:
                        raise SceneError(
                            "Mask PNG needs visible and transparent alpha coverage",
                            path=resource.path,
                        )
                if layer.resource == key and layer.kind == "object":
                    low, high = image.getchannel("A").getextrema()
                    if not has_alpha or low == 255 or high == 0:
                        raise SceneError(
                            "Object PNG must contain transparent pixels", path=resource.path
                        )
        output = io.BytesIO()
        if resource.media_type == "image/jpeg":
            image.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
        else:
            image.save(output, format="PNG", optimize=True)
        normalized[key] = output.getvalue()
        value["resources"][key].update(
            width=image.width,
            height=image.height,
            sha256=hashlib.sha256(normalized[key]).hexdigest(),
        )
    return _validate(SceneBundle(SceneManifest.model_validate(value), normalized))


def render_posters(bundle: SceneBundle) -> SceneBundle:
    """Flatten resting image layers and baseline light; atmosphere stays time-independent."""
    manifest = bundle.manifest.model_dump(mode="json", by_alias=True)
    resources = dict(bundle.resources)
    for name in ("landscape", "portrait"):
        orientation = getattr(bundle.manifest, name)
        base = _image(resources[orientation.base], "base")
        for layer in orientation.layers:
            if layer.kind == "ambient":
                continue
            width = max(1, round(layer.width * base.width))
            height = max(1, round(layer.height * base.height))
            if layer.resource:
                overlay = _image(resources[layer.resource], layer.resource)
                transform = object_transform(layer, base.width, base.height, 0)
                canvas = overlay.transform(
                    base.size,
                    Image.Transform.AFFINE,
                    transform.inverse_pixels(overlay.width, overlay.height),
                    resample=Image.Resampling.BICUBIC,
                )
            else:
                # A radial light texture in its own bounds, matching the native/Canvas default.
                overlay = Image.new("RGBA", (width, height))
                color = tuple(int(layer.color[index : index + 2], 16) for index in (1, 3, 5))
                overlay.paste((*color, 255), (0, 0, width, height))
                gradient = Image.frombytes(
                    "L",
                    (width, height),
                    bytes(
                        radial_alpha((x + 0.5) / width, (y + 0.5) / height)
                        for y in range(height)
                        for x in range(width)
                    ),
                )
                overlay.putalpha(gradient)
                canvas = Image.new("RGBA", base.size)
                canvas.paste(overlay, (round(layer.x * base.width), round(layer.y * base.height)))
            alpha = canvas.getchannel("A").point(
                [round(channel * layer.opacity) for channel in range(256)]
            )
            canvas.putalpha(alpha)
            if layer.mask:
                mask = _image(resources[layer.mask], layer.mask).getchannel("A")
                canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), mask))
            if layer.blend == "screen":
                screened = ImageChops.screen(base.convert("RGB"), canvas.convert("RGB"))
                base = Image.composite(screened, base.convert("RGB"), canvas.getchannel("A"))
                base = base.convert("RGBA")
            else:
                base = Image.alpha_composite(base, canvas)
        poster_key = orientation.poster
        poster = bundle.manifest.resources[poster_key]
        # Poster may not alias base or a layer: overwriting it would mutate the scene geometry.
        other_refs = {orientation.base}
        other_refs.update(layer.resource for layer in orientation.layers if layer.resource)
        other_refs.update(layer.mask for layer in orientation.layers if layer.mask)
        if poster_key in other_refs:
            if orientation.layers:
                raise SceneError("A layered scene needs a separate poster resource")
            continue
        output = io.BytesIO()
        if poster.media_type == "image/jpeg":
            base.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
        else:
            base.save(output, format="PNG", optimize=True)
        resources[poster_key] = output.getvalue()
        manifest["resources"][poster_key]["sha256"] = hashlib.sha256(output.getvalue()).hexdigest()
    return _validate(SceneBundle(SceneManifest.model_validate(manifest), resources))


def pack(directory: str | Path, output: str | Path | None = None) -> bytes:
    """Normalize, regenerate posters and produce a reproducible stored .raidioscene ZIP."""
    source = _directory(Path(directory))
    bundle = render_posters(normalize_bundle(source.manifest, source.resources))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        files = {"scene.json": bundle.manifest.model_dump_json(by_alias=True, indent=2).encode()}
        files.update(
            {bundle.manifest.resources[key].path: value for key, value in bundle.resources.items()}
        )
        for path, value in sorted(files.items()):
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, value)
    data = stream.getvalue()
    if len(data) > MAX_ARCHIVE_BYTES:
        raise SceneError("Normalized package exceeds 40 MiB", code="archive_size")
    read_package(data)
    if output is not None:
        target = Path(output)
        with target.open("xb") as destination:
            destination.write(data)
    return data
