```python
# eck/telemetry.py
"""
Structured telemetry for the Epistemic Control Kernel (ECK).

Implements the ADR-045 telemetry foundation:

- canonical event envelope
- lightweight validation
- stdlib-only implementation
- backwards-compatible logging via extra={"telemetry_event": ...}
- optional redact_hook for payload scrubbing

Telemetry is observability-only and MUST NOT influence behavior.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

__all__ = [
    "SCHEMA_VERSION",
    "ALLOWED_EVENT_TYPES",
    "ALLOWED_SEVERITIES",
    "make_step_id",
    "validate_event",
    "build_event",
    "emit_event",
]

SCHEMA_VERSION = "1.0"

ALLOWED_EVENT_TYPES = frozenset(
    {
        "step.start",
        "step.end",
        "action.proposed",
        "policy.evaluate",
        "action.executed",
        "epistemic.signal",
    }
)

ALLOWED_SEVERITIES = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


def make_step_id(trace_id: str, deterministic_nonce: int) -> str:
    """
    Deterministically derive a step identifier from trace_id and nonce.

    This function is pure and introduces no randomness.
    """
    if not isinstance(trace_id, str) or not trace_id.strip():
        raise ValueError("trace_id must be a non-empty string")
    if isinstance(deterministic_nonce, bool) or not isinstance(
        deterministic_nonce, int
    ):
        raise ValueError("deterministic_nonce must be an int and not bool")
    if deterministic_nonce < 0:
        raise ValueError("deterministic_nonce must be >= 0")

    return f"{trace_id}:step:{deterministic_nonce}"


def validate_event(event: dict[str, Any]) -> None:
    """
    Validate a telemetry event envelope.

    Raises:
        ValueError: If the event does not conform to the ADR-045 envelope.
    """
    if not isinstance(event, dict):
        raise ValueError("event must be a dict")

    required_keys = {
        "event_type",
        "version",
        "timestamp",
        "trace_id",
        "step_id",
        "deterministic_nonce",
        "severity",
        "source",
        "payload",
    }
    missing = required_keys - set(event.keys())
    if missing:
        raise ValueError(
            "telemetry event missing required keys: " + ", ".join(sorted(missing))
        )

    event_type = event["event_type"]
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"invalid event_type: {event_type!r}")

    version = event["version"]
    if not isinstance(version, str) or not version.strip():
        raise ValueError("version must be a non-empty string")

    timestamp = event["timestamp"]
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        raise ValueError("timestamp must be int/float and not bool")

    trace_id = event["trace_id"]
    if not isinstance(trace_id, str) or not trace_id.strip():
        raise ValueError("trace_id must be a non-empty string")

    step_id = event["step_id"]
    if not isinstance(step_id, str) or not step_id.strip():
        raise ValueError("step_id must be a non-empty string")

    deterministic_nonce = event["deterministic_nonce"]
    if isinstance(deterministic_nonce, bool) or not isinstance(
        deterministic_nonce, int
    ):
        raise ValueError("deterministic_nonce must be an int and not bool")
    if deterministic_nonce < 0:
        raise ValueError("deterministic_nonce must be >= 0")

    severity = event["severity"]
    if severity not in ALLOWED_SEVERITIES:
        raise ValueError(f"invalid severity: {severity!r}")

    source = event["source"]
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be a non-empty string")

    payload = event["payload"]
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")


def build_event(
    event_type: str,
    *,
    trace_id: str,
    step_id: str,
    deterministic_nonce: int,
    severity: str,
    source: str,
    payload: dict[str, Any],
    version: str = SCHEMA_VERSION,
    timestamp: float | None = None,
    redact_hook: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build and validate a telemetry event envelope.

    Args:
        event_type: Canonical event name.
        trace_id: Identifier for the full agent run.
        step_id: Identifier for the current step() cycle.
        deterministic_nonce: Monotonic integer derived from kernel state.
        severity: Event severity string.
        source: Emitting component.
        payload: Event-specific payload.
        version: Telemetry schema version.
        timestamp: Optional explicit timestamp. If omitted, current time is used.
        redact_hook: Optional payload redaction callable.

    Returns:
        Validated telemetry event dict.
    """
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")

    effective_payload = dict(payload)
    if redact_hook is not None:
        redacted = redact_hook(effective_payload)
        if not isinstance(redacted, dict):
            raise ValueError("redact_hook must return a dict")
        effective_payload = redacted

    event = {
        "event_type": event_type,
        "version": version,
        "timestamp": time.time() if timestamp is None else timestamp,
        "trace_id": trace_id,
        "step_id": step_id,
        "deterministic_nonce": deterministic_nonce,
        "severity": severity,
        "source": source,
        "payload": effective_payload,
    }
    validate_event(event)
    return event


def emit_event(
    event_type: str,
    *,
    trace_id: str,
    step_id: str,
    deterministic_nonce: int,
    severity: str,
    source: str,
    payload: dict[str, Any],
    logger: logging.Logger | None = None,
    redact_hook: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> None:
    """
    Build, validate, and emit a telemetry event via Python logging.

    The event is attached under extra={"telemetry_event": ...} to preserve
    backwards compatibility with existing logging patterns.

    Args:
        event_type: Canonical event name.
        trace_id: Identifier for the full agent run.
        step_id: Identifier for the current step() cycle.
        deterministic_nonce: Monotonic integer derived from kernel state.
        severity: Event severity string.
        source: Emitting component.
        payload: Event-specific payload.
        logger: Optional logger. Defaults to the canonical ECK logger.
        redact_hook: Optional payload redaction callable.
    """
    event = build_event(
        event_type,
        trace_id=trace_id,
        step_id=step_id,
        deterministic_nonce=deterministic_nonce,
        severity=severity,
        source=source,
        payload=payload,
        redact_hook=redact_hook,
    )

    effective_logger = logger if logger is not None else logging.getLogger("eck-core")
    message = f"telemetry event emitted: {event_type}"

    if severity == "DEBUG":
        effective_logger.debug(message, extra={"telemetry_event": event})
    elif severity == "INFO":
        effective_logger.info(message, extra={"telemetry_event": event})
    elif severity == "WARNING":
        effective_logger.warning(message, extra={"telemetry_event": event})
    elif severity == "ERROR":
        effective_logger.error(message, extra={"telemetry_event": event})
```
