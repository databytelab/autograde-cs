"""
The one place AutoGrade's version is written down.

It was hard-coded as "1.0.0" in two places in `main.py` while the release
being shipped was v0.9.3-pilot, so the health endpoint - the thing support
asks for first - reported a version that did not exist. Keep this in step
with the git tag when cutting a release; `scripts/package_release.py`
checks that they match.
"""
from __future__ import annotations

APP_VERSION = "0.9.3-pilot"
