# Control Tower header image

`refinery-banner.jpg` is the panorama supplied for the Control Tower header.
`build.py` inlines it as a data URI, so the console stays a single file and
makes no network request at runtime.

It is used in exactly one place — the `.ct-hero-bg` layer behind the Control
Tower header — at 62% opacity under a flat off-white wash, with a white fade
across the left third so the headline never crosses plant detail. It is not
darkened, carries no colour gradient, and appears nowhere else in the console.

To replace it, drop a new `refinery-banner.jpg` (or `.webp` / `.png`) here and
rebuild. Around 1800px wide is plenty; the band renders about 178px tall.
