# Authoring with Scene Kit

Read `skills/create-raidio-scene/SKILL.md` when making a scene. `FORMAT.md` defines
the renderer contract; `schema/scene-v2.schema.json` is generated from the Python
models, not a separate source of truth.

The deliverable is a validated `.raidioscene` package the user imports through
the signed-in Raidio app. This toolkit neither handles account credentials nor
publishes art. Use an available image tool selected by the user for creative
generation. Do not require a particular agent, model, or vendor.

Keep each moving object out of the stationary base. Use separate transparent
cutouts, clean plates, and fixed alpha masks excluding frames and architecture.
An imperfect cutout is worse than omitting an optional moving object. Ordinary
still art can remain stationary with carefully placed atmospheric/light layers.

Use the public API for validation and packaging. Never extract untrusted ZIP
entries to disk. Tests belong in `tests/`; tiny original geometry fixtures are
acceptable. Do not add production app artwork or customer prompts to fixtures.
Keep source JSON and preview titles inert, never executable. Network access,
arbitrary shaders, provider keys and automatic uploads are outside this utility.
