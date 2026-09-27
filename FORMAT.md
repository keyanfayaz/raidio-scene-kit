# Scene format v2

The root object has `version: 2`, a nonblank `title`, `resources`, `landscape` and
`portrait`, plus optional `provenance`. Unknown fields are rejected. Provenance
accepts optional `author`, `tool`, `license` (each 1–120 nonblank characters),
and `sourceDescription` (1–500). These are intentional attribution, retained
through packing; no secrets, account identifiers or private prompts belong here.
Missing provenance remains valid. Resource IDs are lowercase letters,
digits, `_` or `-`, start with a letter, and contain at most 64 characters.
Resources use `resources/ID.png` or `.jpg`, declared `mediaType`, pixel `width`
and `height`, and a lowercase SHA-256 of their complete file bytes. Paths must be
distinct and every resource must be referenced.

Each orientation contains `width`, `height`, `base`, `poster` and ordered
`layers`. Base and poster are opaque JPEGs and match orientation dimensions. Portrait
and landscape are separately composed: no stretched or copied coordinates.
The base includes the architecture and the filled area behind movable objects.
The poster is a flattened resting composition for cards, reduced motion and old
clients. For layered scenes its resource must be distinct from the base/layers.

## Layer behavior

Every layer has `id`, `kind`, and `preset`. Order is back to front, above the
stationary base. Coordinates `x`, `y`, `width`, `height` are normalized against
the orientation; their rectangle stays within `[0,1]`. Optional `resource` is
drawn in this rectangle. `anchorX`/`anchorY` are local normalized pivot coordinates.
Optional `mask` is a **full-orientation PNG, with alpha expressing coverage**:
zero excludes pixels, 255 includes them, intermediate alpha feathers edges.
The mask stays fixed in scene coordinates even when an object moves. Masks
require an actual PNG alpha channel; masks and independent objects must have
both visible and transparent pixels. RGB mask
color is irrelevant. Use alpha, not an opaque black-and-white image.

| Kind | Presets | Resource | Behavior |
| --- | --- | --- | --- |
| `foreground` | `still` | Required | Stationary frame, furniture or occluder |
| `object` | `still`, `sway`, `rotate`, `cloth`, `drift`, `flame` | Required | Independent cutout; only these pixels move |
| `ambient` | `rain`, `mist`, `dust`, `stars`, `steam`, `reflection` | None | Procedural, clipped atmosphere |
| `light` | `still` | Optional | Static texture or radial color glow, optionally music-reactive |

No layer executes code. `blend` is `normal` (default) or `screen`; `color` is
`#RRGGBB`, default `#FFD6A0`. Opacity defaults to 1 and remains in `[0,1]`.
Ambient presets remain independent of music. Stars/dust drift gently; rain falls;
steam rises; mist drifts; reflection adds restrained horizontal shimmer.

For object motion, let `t = elapsedSeconds * speed + phase`:

- `sway`: `amplitude * sin(t)` radians around the anchor.
- `rotate`: continuous `t` radians, applied to normalized texture coordinates
  **before** scaling to the layer rectangle. A circular record therefore spins
  inside its stationary perspective ellipse. Amplitude is unused for this preset.
- `cloth`: horizontal shear `amplitude * sin(t)`, pinned at the anchor's Y.
- `drift`: translation `(canvasWidth * amplitude * sin(t),
  canvasHeight * amplitude * 0.35 * sin(t * 0.73))`.
- `flame`: Y scale `1 + amplitude * sin(t * 3)` around the anchor.

Defaults/bounds: amplitude `0.01`, `[0,0.05]`; speed `1`, `[0.05,3]`; phase `0`,
`[0,2π]`; anchor `(0.5,0.5)`. These are preset motion controls, not animation
keyframes. Resting posters evaluate every transform at elapsed time zero,
including the authored phase. Cloth transforms a cutout, never the flattened scene. A well-prepared
base is essential because motion exposes the pixels underneath.

Only light layers accept `reaction`: `none` (default), `energy`, `attack` or
`sustained`. These denote smoothed amplitude, a causal musical attack, and a slow
energy envelope, not verified beat tracking. `strength` defaults to 0.3 in
`[0,1]`; effective opacity is
`clamp(opacity + strength * signal * (1 - opacity), 0, 1)`.
With reactions disabled the signal is zero and baseline opacity remains.
The preview energy slider drives energy/sustained manually; **Test attack** is
a synthetic exponentially decaying accent, clearly labeled as a test.

Pause, buffering, hidden/background state and animation-off freeze the existing
object and atmosphere pose; they do not reset its phase or remove its particles.
Reactive light settles toward baseline over 300 ms when disabled. Reduce Motion
uses the flattened poster. A full-player renderer may use the poster while loading; cards always
use posters. Native and browser effects may differ slightly in rasterization;
source placement, masks, transforms, bounds and lifecycle must agree.

`motion.py` and `motion.js` implement the same reference equations. Object and
ambient conformance fixtures in `examples/` are checked by the browser and Python
tests and shared with the native renderer. Atmosphere uses 88 rain streaks, 40
stars/dust/reflection elements, or 8 elliptical mist/steam glows per region.
These counts and seeds are deterministic; crop/mask coverage controls placement.
Light and mist glows have radial alpha stops `(0,1)`, `(0.5,0.5)`, `(1,0)`.

## Limits and archive validation

- At most 12 layers per orientation and 32 resources for the entire scene.
- Longest raster edge 2048 pixels. JPEG/PNG stills only; no animation or HEIC
  inside packages. Convert HEIC before authoring; ordinary app still imports
  retain their existing HEIC support.
- At most 64 MiB from `sum(width * height * 4)` across unique resources,
  including both posters and masks. This is a deterministic authoring budget,
  not a promise of native GPU memory use.
- Archive at most 40 MiB; total expanded resources at most 80 MiB; JSON manifest
  at most 256 KiB. ZIP_STORED only, no encryption, links, directories, duplicate
  entries, unexpected resources or path traversal. Extra fields, comments, ZIP64,
  data descriptors, hidden gaps and preambles are rejected. The central directory
  is bounded before constructing an archive parser. Actual reads remain bounded.

`validate --json` exits 0 with `valid: true`, or 1 with `valid: false` and
`errors: [{code,path,message}]`. Error messages are actionable but not a stable
API; `code` and `path` are the machine-facing fields. Pixels, alpha and hashes are
verified independently of declarations. The server must still validate a package
even when a client or toolkit already accepted it.
