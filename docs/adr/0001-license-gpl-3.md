# 0001: License the project under GPL-3.0

- Status: accepted
- Date: 2026-10-06

## Context
ReelHaven is a public, self-hosted tool. The owner had no preference and asked
for the license that gives the project the widest choice of libraries.

## Decision
**GPL-3.0-or-later**, with the standard license text in `LICENSE`.

## Consequences
- We can use libraries under MIT, BSD, Apache-2.0, LGPL and GPL-3.0. An
  MIT-licensed project could not include GPL libraries.
- We cannot include code that is "GPL-2.0-only" (rare in the Python and
  JavaScript ecosystems). Check licenses when adding dependencies.
- Anyone may use and modify ReelHaven; anyone who distributes a modified
  version must publish their source.
- ffmpeg is run as a separate program, so its license does not constrain ours.
