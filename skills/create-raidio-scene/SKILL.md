---
name: create-raidio-scene
description: Author coordinated, layered Raidio listening scenes with available image tools, inspect them locally, and deliver a validated .raidioscene package for app import.
---

Authoring guide **v2**, for scene manifest v2 and Scene Kit v0.1.0. The pinned
format reference is https://github.com/keyanfayaz/raidio-scene-kit/blob/v0.1.0/FORMAT.md.

Use the user's imagined place, mood, palette and focal objects as the creative
brief. Read [FORMAT.md](../../FORMAT.md) before authoring layers. Install Scene
Kit from its checkout if needed; the README contains commands. No Raidio account
or provider key is needed by this utility.

Start a new project with `raidio-scene init NAME`. Replace the demonstration
artwork with original images using the user's chosen/available image tools.
Author separately composed portrait and landscape versions. Keep the lower
quarter visually quiet for player controls; preserve the scene's focal object
and materials across both orientations.

Use stationary architecture as the base. An independently moving object requires
a transparent cutout **and a clean base with that object removed**. Fill the
space behind it before animation, otherwise its original will show underneath.
Include static occluding foreground layers when motion passes behind furniture
or window frames. Alpha masks belong to the orientation, not a screen crop.
Inspect mask coverage at full size; no atmosphere should leak onto walls.

Favor a few convincing details: rain beyond a window, quiet drifting dust, a
slow curtain, warm light spill. Ambient motion has its own time; music controls
only localized light. Keep uncertain objects still instead of claiming automatic
segmentation succeeded. Never warp the whole image. No people or text are needed
unless the user explicitly wants them.

After modifying images, `raidio-scene pack NAME --output NAME.raidioscene`
normalizes metadata, refreshes hashes and regenerates posters without changing
the source. Run `raidio-scene validate NAME.raidioscene --json`; fix reported
errors and repack to a new file. Inspect with `raidio-scene preview NAME.raidioscene`:

- Both orientations, player guides and flattened poster.
- Clean base alone: no duplicated movable objects or unfilled holes.
- Isolated layers and mask coverage; minimum and maximum light signal.
- Motion enabled/disabled, pause, Reduce Motion, and stronger test attacks.

Record intentional author/tool/license attribution in optional `provenance`,
preserving attribution from reused source material. Keep its source description
short; never store credentials, location data, account identifiers or private
prompts in the package. Stripped image metadata is not a provenance record.

Return the package and a concise description of what moves and reacts. State any
remaining visual limitations. The user imports it in Raidio's Artwork section
and chooses Create or Save. Do not request session tokens, sign in for the user,
publish assets, or silently use cloud image services for uploaded private images.
