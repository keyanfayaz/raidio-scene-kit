# Raidio Scene Kit

Make a place you want to spend time in. Scene Kit is an open, agent-first utility
for authoring illustrated music-player scenes: a stationary room, independent
objects, quiet atmosphere, and light that can respond to music.

The toolkit runs locally. It does not need a Raidio account, provider key, cloud
service, or subscription. Your agent can use the image tools you already choose.
The utility validates, previews and packages their output; it does not generate
images itself. Its original geometric starter is a small demonstration, not one
of Raidio's curated illustrations.

## Start

Requires Python 3.12 or later. Install the pinned public release with uv:

```sh
uv tool install git+https://github.com/keyanfayaz/raidio-scene-kit.git@v0.1.1
raidio-scene init dream-room
raidio-scene preview dream-room
raidio-scene pack dream-room --output dream-room.raidioscene
raidio-scene validate dream-room.raidioscene --json
```

For agents, the pinned [authoring guide v2](https://github.com/keyanfayaz/raidio-scene-kit/blob/v0.1.1/skills/create-raidio-scene/SKILL.md)
and [format v2](https://github.com/keyanfayaz/raidio-scene-kit/blob/v0.1.1/FORMAT.md)
are the instructions for this release. If you prefer a standalone checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/raidio-scene init dream-room
.venv/bin/raidio-scene preview dream-room
.venv/bin/raidio-scene pack dream-room --output dream-room.raidioscene
.venv/bin/raidio-scene validate dream-room.raidioscene --json
```

Or install with `uv tool install .` and use `raidio-scene` directly. The preview
binds only to `127.0.0.1`, reads no remote resources, captures no audio and stops
with Ctrl-C. Use `preview SCENE --no-open` to print its local URL without opening
a browser. A directory or `.raidioscene` archive is accepted by `preview` and
`validate`.

Use **Inspect transparency (hide base)** with an isolated layer to examine cutout
edges over a checkerboard. Pause and animation-off preserve the current pose;
Reduce Motion shows the flattened poster.

The preview's **Test attack across lights** button excites attack, energy and
sustained layers together. **Energy baseline** reaches full-scale at 1; the
artwork's own `strength` controls how much illumination is added. Use a lower
baseline when checking how an energy/sustained light brightens during an accent.
Scene Kit 0.1.1 adds sparse `meteors` and longer, clearer water `reflection` ripples.

`pack` refreshes image hashes, strips metadata, preserves PNG transparency,
regenerates resting posters, and writes a reproducible archive. It never changes
the authoring directory or overwrites an existing output. After replacing image
files, validate the newly packed archive: the original manifest's hashes may be
stale until updated by your authoring tool.

## Copy this to your agent

> Install `uv tool install git+https://github.com/keyanfayaz/raidio-scene-kit.git@v0.1.1`
> if needed. Read the versioned authoring guide at
> https://github.com/keyanfayaz/raidio-scene-kit/blob/v0.1.1/skills/create-raidio-scene/SKILL.md
> and its linked format v2 instructions. Help me create my dream listening scene:
> **[describe your place, mood, time of day, materials and favorite objects]**.
> Make coordinated landscape and portrait illustrations. Keep the camera,
> architecture and furniture still. Put moving objects on separate transparent
> layers over a clean base; include gentle atmosphere and localized reactive
> light where they belong. Ask about creative choices only when needed. Use the
> image tools available to you; do not ask for Raidio login credentials or API
> keys. Inspect both orientations, isolated masks, the clean base and maximum
> motion/light in the preview. Fix validation errors and return a valid
> `.raidioscene` file I can import in Raidio's Artwork section, plus a short
> explanation of its moving details. Do not upload or publish my scene for me.

The portable manifest supports optional `provenance` for intentional attribution:
author, tool, license and source description. Preserve this when adapting a
scene; it is retained while incidental image metadata is stripped. Do not put
tokens, keys, account identifiers, location metadata or private prompts there.

In a Raidio build supporting scene packages, choose **Import scene package** in
the station Artwork section, preview the result, then press Create or Save.
The signed-in app handles private upload. This first toolkit release deliberately
has no account login or direct publishing command. Ordinary still imports remain
static; animation is supplied by the scene manifest, not guessed from a JPEG.

## Files and contract

An authoring directory contains `scene.json` and its referenced `resources/`.
The `.raidioscene` file is a ZIP with **stored, unencrypted regular files only**;
no folders, executable code, scripts, external URLs, account identifiers or
provider credentials. A package is not a plugin.

The canonical Python models are in `src/raidio_scene/models.py` and the exported
JSON Schema is [schema/scene-v2.schema.json](schema/scene-v2.schema.json).
[FORMAT.md](FORMAT.md) describes motion, masking, orientation and limits.
Server delivery may add private signed resource URLs; these are never portable
package data. Existing application posters remain a separate v1 compatibility
envelope.

Programmatic APIs:

```python
from raidio_scene import (
    SceneManifest, SceneBundle, SceneError, validate_directory,
    read_package, normalize_bundle, render_posters, pack,
)

bundle = validate_directory("dream-room")
# bundle.manifest is SceneManifest; bundle.resources maps resource IDs to bytes.
data = pack("dream-room")
checked = read_package(data)  # validates hashes/pixels; never extracts ZIP paths
clean = normalize_bundle(checked.manifest, checked.resources)  # strips metadata
ready = render_posters(clean)
```

All imported bytes must pass `read_package` before use. Normalization regenerates
hashes because stripped metadata or JPEG encoding changes the bytes. Structure
and hash validation establish file safety and consistency, not artistic quality;
mask placement, clean-plate coverage, stationary architecture and native-device
performance still need visual review.

## Contributing and license

Install with `python -m pip install '.[dev]'` in an isolated environment and run
`python -m pytest tests`, `ruff check .`, and `mypy src`. With Node.js installed,
run `node --test tests/motion.test.cjs` to verify browser/native/Python motion parity.
Do not copy app credentials, private scenes, generated
customer artwork, or model weights into this repository. `raidio-scene init`
creates the original MIT-licensed example using Pillow geometry; you can inspect
and redistribute it. User-authored artwork retains its own licensing terms.

[MIT](LICENSE) applies to this toolkit, schema, documentation and original starter
only. It does not license the rest of the Raidio application or third-party art.
