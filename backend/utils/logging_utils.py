"""
Structured operational logging.

Logs here are for operating the service - who failed to log in, which job
ran, which provider call failed, what was exported. They are deliberately
machine-readable (one JSON object per line) so they can be grepped, shipped
or queried without a parser written for prose.

What must never reach a log, and why:

* **Passwords and API keys.** Obvious, and enforced rather than trusted:
  `_REDACT` drops any field whose name looks like a credential, so a future
  caller cannot leak one by passing it in.
* **Student submission content.** It is coursework, and it is large. Log the
  submission id; the file is on disk and in the database if anyone needs it.
* **Unnecessary personal data.** An email address identifies a person, so
  authentication events log a one-way hash of it - enough to correlate
  repeated failures against the same account without writing that account's
  address into a log aggregator. Ids are used everywhere else.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from backend.config import settings

logger = logging.getLogger("autograde.events")

# Field names that must never be written out, whatever a caller passes.
_REDACT = (
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "credential", "cookie", "session",
)

# Fields that carry submission or student text rather than identifiers.
_TOO_BIG = ("content", "source", "submission_text", "prompt", "feedback")


def hash_identifier(value: str) -> str:
    """
    A stable, non-reversible tag for an email address.

    Correlating "this account failed to log in five times" does not require
    storing the address in the log; a truncated digest is enough, and it is
    salted with the app secret so the same address is not recognisable
    across deployments.
    """
    if not value:
        return ""
    digest = hashlib.sha256(
        f"{settings.secret_key}:{value.strip().lower()}".encode()
    ).hexdigest()
    return digest[:16]


def _clean(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(marker in lowered for marker in _REDACT):
        return "[redacted]"
    if any(marker in lowered for marker in _TOO_BIG):
        return f"[{len(str(value))} chars omitted]"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:500]


def log_event(event: str, *, level: str = "info", **fields: Any) -> None:
    """
    Emit one structured event.

        log_event("auth.login_failed", email_hash=..., ip=...)

    `event` is a dotted name so related events group by prefix
    (`auth.*`, `grading_job.*`, `export.*`, `provider.*`).
    """
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": event,
        "env": settings.environment,
    }
    payload.update({k: _clean(k, v) for k, v in fields.items()})
    getattr(logger, level, logger.info)(json.dumps(payload, default=str))


class JsonFormatter(logging.Formatter):
    """
    Renders ordinary log records as JSON.

    Records from `log_event` are already a JSON object and are passed
    through untouched, so the output is one object per line either way.
    """

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.name == "autograde.events" and message.startswith("{"):
            return message
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": message,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """
    Install the formatter on the root handler.

    JSON in production and staging, where something is collecting logs;
    plain text in development, where a person is reading them.
    """
    root = logging.getLogger()
    level = logging.INFO if settings.environment != "production" else logging.WARNING
    root.setLevel(level)

    handler = logging.StreamHandler()
    if settings.is_production():
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))

    root.handlers = [handler]
    # Events are always worth keeping, even when the root level is raised.
    logging.getLogger("autograde.events").setLevel(logging.INFO)
