# Original starter

Run `raidio-scene init /path/to/new-example` to materialize the small original
geometric night scene with landscape and portrait resources, star atmosphere,
and soft moonlight. It is generated deterministically by `cli.initialize`, uses
no external assets, and is covered by this toolkit's MIT license.

This keeps a runnable redistributable example without copying Raidio's bundled
production illustrations into the open-source utility.

The conformance fixtures cover object transforms, all ambient recipes, and light
signal mapping. Their numeric samples are shared by the Python, browser and
native renderers. `reaction-conformance.json` also contains preview-only test
accent envelopes; these do not replace the app's real audio measurements.
