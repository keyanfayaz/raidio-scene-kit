from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from PIL import Image, ImageDraw

from raidio_scene.models import SceneManifest
from raidio_scene.package import (
    SceneBundle,
    SceneError,
    normalize_bundle,
    pack,
    read_package,
    render_posters,
    validate_directory,
)
from raidio_scene.preview import preview_html


def initialize(path: Path) -> None:
    """Small original geometry fixture, redistributable with the MIT toolkit."""
    if path.exists():
        raise SceneError(
            "Choose a new directory; existing work is never overwritten", path=str(path)
        )
    resources = {}
    pixels = {}
    orientations = {}
    for name, width, height in (("landscape", 576, 384), ("portrait", 384, 576)):
        image = Image.new("RGB", (width, height), "#101a30")
        draw = ImageDraw.Draw(image)
        for y in range(height):
            t = y / height
            draw.line((0, y, width, y), fill=(int(18 - 7 * t), int(30 - 14 * t), int(55 - 28 * t)))
        draw.rectangle((0, height * 0.65, width, height), fill="#0c1723")
        draw.ellipse(
            (width * 0.65, height * 0.12, width * 0.78, height * 0.12 + width * 0.13),
            fill="#c1c8c0",
        )
        draw.polygon(
            [(0, height * 0.66), (width * 0.23, height * 0.4), (width * 0.52, height * 0.66)],
            fill="#192e38",
        )
        draw.polygon(
            [(width * 0.25, height * 0.66), (width * 0.65, height * 0.44), (width, height * 0.66)],
            fill="#142732",
        )
        draw.rectangle((width * 0.16, height * 0.7, width * 0.84, height * 0.73), fill="#534833")
        draw.rectangle((width * 0.2, height * 0.73, width * 0.22, height), fill="#302a24")
        draw.rectangle((width * 0.78, height * 0.73, width * 0.80, height), fill="#302a24")
        for suffix in ("base", "poster"):
            key = f"{name}-{suffix}"
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=92)
            data = buffer.getvalue()
            pixels[key] = data
            resources[key] = {
                "path": f"resources/{key}.jpg",
                "mediaType": "image/jpeg",
                "width": width,
                "height": height,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        orientations[name] = {
            "width": width,
            "height": height,
            "base": f"{name}-base",
            "poster": f"{name}-poster",
            "layers": [
                {
                    "id": "night-sky",
                    "kind": "ambient",
                    "preset": "stars",
                    "x": 0.0,
                    "y": 0.0,
                    "width": 1.0,
                    "height": 0.4,
                    "opacity": 0.24,
                    "speed": 0.2,
                    "color": "#CEE1F0",
                },
                {
                    "id": "moonlight",
                    "kind": "light",
                    "preset": "still",
                    "x": 0.6,
                    "y": 0.08,
                    "width": 0.25,
                    "height": 0.22,
                    "opacity": 0.03,
                    "blend": "screen",
                    "reaction": "sustained",
                    "strength": 0.15,
                    "color": "#C7DBE4",
                },
            ],
        }
    manifest = SceneManifest.model_validate(
        {
            "version": 2,
            "title": "Quiet Observatory · starter study",
            "provenance": {
                "author": "Raidio Scene Kit contributors",
                "tool": "Scene Kit 0.1.0 · Pillow geometry",
                "license": "MIT",
                "sourceDescription": "Original geometric starter; no external images.",
            },
            "resources": resources,
            **orientations,
        }
    )
    bundle = render_posters(normalize_bundle(manifest, pixels))
    (path / "resources").mkdir(parents=True)
    (path / "scene.json").write_text(
        bundle.manifest.model_dump_json(by_alias=True, indent=2) + "\n"
    )
    for key, data in bundle.resources.items():
        (path / bundle.manifest.resources[key].path).write_bytes(data)


def _load(path: Path) -> SceneBundle:
    if path.is_dir():
        return validate_directory(path)
    if path.stat().st_size > 40 * 1024 * 1024:
        raise SceneError("Package exceeds 40 MiB")
    return read_package(path.read_bytes())


def serve(bundle: SceneBundle, port: int, open_browser: bool) -> None:
    document = preview_html(bundle).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.headers.get("Host") not in {
                f"127.0.0.1:{server.server_port}",
                f"localhost:{server.server_port}",
            }:
                self.send_error(403)
                return
            if self.path not in {"/", "/index.html"}:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(document)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; img-src data:; "
                "script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; "
                "frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(document)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Preview: {url}\nLocal files only. Press Ctrl-C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Author portable, layered Raidio scenes offline.")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a small, redistributable starter scene")
    init.add_argument("directory", type=Path)
    validate = commands.add_parser("validate", help="Validate a directory or .raidioscene package")
    validate.add_argument("scene", type=Path)
    validate.add_argument(
        "--json", action="store_true", help="Print stable machine-readable results"
    )
    build = commands.add_parser("pack", help="Normalize images and generate a reproducible package")
    build.add_argument("directory", type=Path)
    build.add_argument("--output", required=True, type=Path)
    preview = commands.add_parser(
        "preview", help="Inspect scenes in a loopback-only browser preview"
    )
    preview.add_argument("scene", type=Path)
    preview.add_argument("--port", default=0, type=int)
    preview.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize(args.directory)
            print(
                f"Created {args.directory}. Edit scene.json and resources, then validate and pack."
            )
        elif args.command == "validate":
            bundle = _load(args.scene)
            result = {
                "valid": True,
                "version": 2,
                "title": bundle.manifest.title,
                "resources": len(bundle.resources),
                "errors": [],
            }
            print(json.dumps(result) if args.json else f"Valid scene: {bundle.manifest.title}")
        elif args.command == "pack":
            data = pack(args.directory, args.output)
            print(f"Created {args.output} ({len(data):,} bytes). Import it in Raidio → Artwork.")
        elif args.command == "preview":
            serve(_load(args.scene), args.port, not args.no_open)
        return 0
    except (SceneError, OSError, ValueError) as error:
        item = (
            error.as_dict()
            if isinstance(error, SceneError)
            else {
                "code": "operation_failed",
                "path": "",
                "message": str(error),
            }
        )
        if args.command == "validate" and args.json:
            print(json.dumps({"valid": False, "errors": [item]}))
        else:
            print(f"{item['path']}: {item['message']}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
