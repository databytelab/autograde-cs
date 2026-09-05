"""
Build the ZIP you hand to a customer.

    python scripts/package_release.py

Produces ``dist/autograde-<version>.zip`` containing exactly the files that
are committed to git — which is the point: your ``.env``, your database,
your virtualenv and any student work you have lying around are untracked
or ignored, so they cannot travel with the bundle by accident.

The archive is then re-opened and checked for anything that looks like a
live secret. If that check fails, nothing ships.
"""
from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

# Files that must be in the bundle for it to be installable at all. If a
# rename ever drops one of these, the customer finds out, not us.
REQUIRED = [
    # What a professor double-clicks. Without any one of these the package
    # is not installable by the person it is for.
    "Start AutoGrade.bat",
    "Stop AutoGrade.bat",
    "Restart AutoGrade.bat",
    "Update AutoGrade.bat",
    "Backup AutoGrade.bat",
    "Restore AutoGrade.bat",
    "Show AutoGrade Logs.bat",
    "scripts/autograde.ps1",
    "autograde.sh",
    "docker-compose.local.yml",
    # The guides they follow.
    "README.md",
    "INSTALL.md",
    "AI_PROVIDERS.md",
    "USER_GUIDE.md",
    "CANVAS.md",
    "RUN_AND_SHARE.md",
    "BACKUP_AND_RESTORE.md",
    "TROUBLESHOOTING.md",
    # The application itself.
    "docker/Dockerfile.backend",
    "docker/Dockerfile.frontend",
    "docker/entrypoint.sh",
    "docker/backup.sh",
    "requirements.txt",
    "alembic.ini",
    # The department-server path, which ships too but is not advertised.
    "docker-compose.prod.yml",
    "docker/Caddyfile",
    "setup.sh",
    "setup.ps1",
    ".env.example",
]

# Shapes of real credentials. Deliberately narrow: these match live keys,
# not the words "api key" in prose or a placeholder in .env.example.
SECRET_PATTERNS = [
    ("OpenAI key", re.compile(rb"sk-[A-Za-z0-9_\-]{32,}")),
    ("Anthropic key", re.compile(rb"sk-ant-[A-Za-z0-9_\-]{32,}")),
    ("Canvas token", re.compile(rb"\b\d{4,6}~[A-Za-z0-9]{40,}")),
    ("private key", re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

# Obvious stand-ins. Test fixtures and .env.example deliberately carry
# credential-shaped strings; a real key does not announce itself as fake.
PLACEHOLDER_MARKERS = (
    b"test", b"fake", b"dummy", b"example", b"sample", b"placeholder",
    b"replacement", b"your-", b"xxxx", b"...", b"redacted", b"changeme",
)


def is_placeholder(matched: bytes) -> bool:
    lowered = matched.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


# Text files are worth scanning; a .png that happens to contain those bytes
# is not a leak.
SCANNED_SUFFIXES = {
    "", ".py", ".md", ".txt", ".yml", ".yaml", ".json", ".sh", ".ps1",
    ".ini", ".cfg", ".toml", ".env", ".example", ".html", ".css", ".js",
    ".Caddyfile", ".backend", ".frontend",
}


def run(*args: str) -> str:
    return subprocess.run(
        args, cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def version() -> str:
    """The current tag if we are on one, otherwise a short commit id."""
    try:
        return run("git", "describe", "--tags", "--exact-match")
    except subprocess.CalledProcessError:
        pass
    try:
        return run("git", "rev-parse", "--short", "HEAD")
    except subprocess.CalledProcessError:
        return "snapshot"


def main() -> int:
    try:
        run("git", "rev-parse", "--git-dir")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("This has to run inside the git checkout — that is what keeps "
              "your .env out of the bundle.", file=sys.stderr)
        return 1

    dirty = run("git", "status", "--porcelain", "--untracked-files=no")
    if dirty:
        print("! Uncommitted changes will NOT be in the bundle:\n")
        print(dirty + "\n")
        if input("  Package anyway? [y/N] ").strip().lower() not in ("y", "yes"):
            return 1

    tag = version()
    DIST.mkdir(exist_ok=True)
    target = DIST / f"autograde-{tag}.zip"

    # git archive writes only tracked files, with the tree prefix a customer
    # gets when they unzip it.
    subprocess.run(
        ["git", "archive", "--format=zip",
         f"--prefix=autograde-{tag}/", "-o", str(target), "HEAD"],
        cwd=ROOT, check=True,
    )

    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
        prefix = f"autograde-{tag}/"

        missing = [f for f in REQUIRED if prefix + f not in names]
        if missing:
            target.unlink()
            print("Bundle is missing files a customer needs:", file=sys.stderr)
            for f in missing:
                print("  " + f, file=sys.stderr)
            return 1

        leaks: list[str] = []
        for name in names:
            if name.endswith("/"):
                continue
            if Path(name).suffix not in SCANNED_SUFFIXES:
                continue
            blob = zf.read(name)
            for label, pattern in SECRET_PATTERNS:
                for found in pattern.findall(blob):
                    if is_placeholder(found):
                        continue
                    leaks.append(f"{name}: looks like a {label}")
                    break

    if leaks:
        target.unlink()
        print("Refusing to ship. Something secret-shaped is committed:",
              file=sys.stderr)
        for leak in leaks:
            print("  " + leak, file=sys.stderr)
        return 1

    size_mb = target.stat().st_size / 1_000_000
    print(f"\n  {target.relative_to(ROOT)}  ({size_mb:.1f} MB, {len(names)} files)")
    print("\n  Send this with one sentence:")
    print("  unzip it, open the folder, and double-click Start AutoGrade.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
