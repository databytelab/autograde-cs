"""
The one place AutoGrade's version is written down.

The health endpoint - the first thing support asks for - reports this, so it
has to be the version that actually shipped. Keep it in step with the git tag
when cutting a release; `scripts/package_release.py` refuses to build a bundle
whose tag and this string disagree.
"""
from __future__ import annotations

APP_VERSION = "1.0.0"
