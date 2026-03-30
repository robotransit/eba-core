# tests/test_telemetry.py
"""Tests for the ADR-045 telemetry foundation module."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from eck.telemetry import (
    ALLOWED_EVENT_TYPES,
    ALLOWED_SEVERITIES,
    SCHEMA_VERSION,
    build_event,
    emit_event,
    make_step_id,
    validate_event,
)


def _valid_event() -> dict:
    """Return a minimal valid telemetry event envelope."""
    return {
        "event_type": "step.start",
        "version": SCHEMA_VERSION,
        "timestamp": 1234.5,
        "trace_id": "trace-001",
        "step_id": "trace-001:step:1",
        "deterministic_nonce": 1,
        "severity": "INFO",
        "source": "agent",
        "payload": {"objective": "test"},
    }


class TestMakeStepId(unittest.TestCase):
    """Pure deterministic step-id derivation."""

    def test_valid_inputs_produce_expected_step_id(self) -> None:
        """Valid inputs return the canonical trace_id:step:nonce form."""
        self.assertEqual(
            make_step_id("trace-abc", 12),
            "trace-abc:step:12",
        )

    def test_empty_trace_id_raises(self) -> None:
        """Empty trace_id raises ValueError."""
        with self.assertRaises(ValueError):
            make_step_id("", 1)

    def test_whitespace_trace_id_raises(self) -> None:
        """Whitespace-only trace_id raises ValueError."""
        with self.assertRaises(ValueError):
            make_step_id("   ", 1)

    def test_non_integer_nonce_raises(self) -> None:
        """Non-int deterministic_nonce raises ValueError."""
        with self.assertRaises(ValueError):
            make_step_id("trace-abc", 1.5)

    def test_bool_nonce_raises(self) -> None:
        """Bool deterministic_nonce raises ValueError."""
        with self.assertRaises(ValueError):
            make_step_id("trace-abc", True)

    def test_negative_nonce_raises(self) -> None:
        """Negative deterministic_nonce raises ValueError."""
        with self.assertRaises(ValueError):
            make_step_id("trace-abc", -1)


class TestValidateEvent(unittest.TestCase):
    """Envelope validation for ADR-045."""

    def test_valid_event_passes(self) -> None:
        """A conformant event envelope validates without error."""
        validate_event(_valid_event())

    def test_non_dict_event_raises(self) -> None:
        """Non-dict event raises ValueError."""
        with self.assertRaises(ValueError):
            validate_event("not_a_dict")  # type: ignore[arg-type]

    def test_missing_required_keys_raise(self) -> None:
        """Missing required envelope keys raise ValueError."""
        event = _valid_event()
        del event["payload"]
        with self.assertRaises(ValueError):
            validate_event(event)

    def test_invalid_event_type_raises(self) -> None:
        """Unknown event_type raises ValueError."""
        event = _valid_event()
        event["event_type"] = "not.real"
        with self.assertRaises(ValueError):
            validate_event(event)

    def test_invalid_severity_raises(self) -> None:
        """Unknown severity raises ValueError."""
        event = _valid_event()
        event["severity"] = "TRACE"
        with self.assertRaises(ValueError):
            validate_event(event)

    def test_non_string_version_raises(self) -> None:
        """Non-string version raises ValueError."""
        event = _valid_event()
        event["version"] = 1  # type: ignore[assignment]
        with self.assertRaises(ValueError):
            validate_event(event)

    def test_bool_timestamp_raises(self) -> None:
        """Bool timestamp raises ValueError."""
        event = _valid_event()
        event["timestamp"] = True
        with self.assertRaises(ValueError):
            validate_event(event)

    def test_string_timestamp_raises(self) -> None:
        """Non-numeric timestamp raises ValueError."""
        event = _valid_event()
        event["timestamp"] = "1234.5"  # type: ignore[assignment]
        with self.assertRaises(ValueError):
            validate_event(event)

    def test_empty_trace_id_raises(self) -> None:
        """Empty trace_id raises ValueError."""
        event = _valid_event()
        event["trace_id"] = ""
        with self.assertRaises(ValueError):
            validate_event(event)

    def test_empty_step_id_raises(self) -> None:
        """Empty step_id raises ValueError."""
        event = _valid_event()
        event["step_id"] = ""
        with self.assertRaises(ValueError):
            validate_event(event)

    def test_empty_source_raises(self) -> None:
        """Empty source raises ValueError."""
        event = _valid_event()
        event["source"] = ""
        with self.assertRaises(ValueError):
            validate_event(event)

    def test_negative_deterministic_nonce_raises(self) -> None:
        """Negative deterministic_nonce raises ValueError."""
        event = _valid_event()
        event["deterministic_nonce"] = -1
        with self.assertRaises(ValueError):
            validate_event(event)

    def test_bool_deterministic_nonce_raises(self) -> None:
        """Bool deterministic_nonce raises ValueError."""
        event = _valid_event()
        event["deterministic_nonce"] = False
        with self.assertRaises(ValueError):
            validate_event(event)

    def test_non_dict_payload_raises(self) -> None:
        """Non-dict payload raises ValueError."""
        event = _valid_event()
        event["payload"] = ["not", "a", "dict"]  # type: ignore[assignment]
        with self.assertRaises(ValueError):
            validate_event(event)


class TestBuildEvent(unittest.TestCase):
    """Envelope construction with validation and optional redaction."""

    def test_valid_inputs_produce_valid_event(self) -> None:
        """build_event returns a validated envelope with expected fields."""
        event = build_event(
            "step.start",
            trace_id="trace-abc",
            step_id="trace-abc:step:3",
            deterministic_nonce=3,
            severity="INFO",
            source="agent",
            payload={"objective": "test"},
            timestamp=1234.5,
        )

        self.assertEqual(event["event_type"], "step.start")
        self.assertEqual(event["version"], SCHEMA_VERSION)
        self.assertEqual(event["timestamp"], 1234.5)
        self.assertEqual(event["trace_id"], "trace-abc")
        self.assertEqual(event["step_id"], "trace-abc:step:3")
        self.assertEqual(event["deterministic_nonce"], 3)
        self.assertEqual(event["severity"], "INFO")
        self.assertEqual(event["source"], "agent")
        self.assertEqual(event["payload"], {"objective": "test"})

    def test_timestamp_defaults_to_time_time_when_not_supplied(self) -> None:
        """timestamp defaults to time.time() when omitted."""
        with patch("eck.telemetry.time.time", return_value=9876.5):
            event = build_event(
                "step.start",
                trace_id="trace-abc",
                step_id="trace-abc:step:1",
                deterministic_nonce=1,
                severity="INFO",
                source="agent",
                payload={"objective": "test"},
            )

        self.assertEqual(event["timestamp"], 9876.5)

    def test_explicit_timestamp_is_preserved_exactly(self) -> None:
        """Explicit timestamp bypasses time.time() and is preserved exactly."""
        with patch("eck.telemetry.time.time", return_value=9999.9):
            event = build_event(
                "step.start",
                trace_id="trace-abc",
                step_id="trace-abc:step:1",
                deterministic_nonce=1,
                severity="INFO",
                source="agent",
                payload={"objective": "test"},
                timestamp=1111.25,
            )

        self.assertEqual(event["timestamp"], 1111.25)

    def test_payload_is_copied_not_reused_by_reference(self) -> None:
        """Mutating the original payload after build_event does not affect the event."""
        payload = {"objective": "before"}
        event = build_event(
            "step.start",
            trace_id="trace-abc",
            step_id="trace-abc:step:1",
            deterministic_nonce=1,
            severity="INFO",
            source="agent",
            payload=payload,
            timestamp=1234.5,
        )

        payload["objective"] = "after"
        self.assertEqual(event["payload"]["objective"], "before")

    def test_version_override_works(self) -> None:
        """Explicit version override is preserved."""
        event = build_event(
            "step.start",
            trace_id="trace-abc",
            step_id="trace-abc:step:1",
            deterministic_nonce=1,
            severity="INFO",
            source="agent",
            payload={"objective": "test"},
            version="2.0",
            timestamp=1234.5,
        )
        self.assertEqual(event["version"], "2.0")

    def test_redact_hook_is_applied(self) -> None:
        """redact_hook transforms the payload before validation/emission."""
        def hook(payload: dict) -> dict:
            redacted = dict(payload)
            redacted["secret"] = "[REDACTED]"
            return redacted

        event = build_event(
            "step.start",
            trace_id="trace-abc",
            step_id="trace-abc:step:1",
            deterministic_nonce=1,
            severity="INFO",
            source="agent",
            payload={"secret": "raw"},
            timestamp=1234.5,
            redact_hook=hook,
        )
        self.assertEqual(event["payload"]["secret"], "[REDACTED]")

    def test_redact_hook_returning_non_dict_raises(self) -> None:
        """redact_hook must return a dict."""
        def bad_hook(payload: dict) -> list:
            return ["not", "a", "dict"]

        with self.assertRaises(ValueError):
            build_event(
                "step.start",
                trace_id="trace-abc",
                step_id="trace-abc:step:1",
                deterministic_nonce=1,
                severity="INFO",
                source="agent",
                payload={"objective": "test"},
                timestamp=1234.5,
                redact_hook=bad_hook,  # type: ignore[arg-type]
            )

    def test_invalid_inputs_propagate_through_validation(self) -> None:
        """build_event surfaces validation errors from invalid envelope content."""
        with self.assertRaises(ValueError):
            build_event(
                "not.real",
                trace_id="trace-abc",
                step_id="trace-abc:step:1",
                deterministic_nonce=1,
                severity="INFO",
                source="agent",
                payload={"objective": "test"},
                timestamp=1234.5,
            )

    def test_non_dict_payload_raises_before_validation(self) -> None:
        """payload must be a dict before any envelope is built."""
        with self.assertRaises(ValueError):
            build_event(
                "step.start",
                trace_id="trace-abc",
                step_id="trace-abc:step:1",
                deterministic_nonce=1,
                severity="INFO",
                source="agent",
                payload=["not", "a", "dict"],  # type: ignore[arg-type]
                timestamp=1234.5,
            )


class TestEmitEvent(unittest.TestCase):
    """Logging emission wrapper for telemetry events."""

    def test_valid_inputs_emit_without_error(self) -> None:
        """emit_event emits a valid event without raising."""
        logger = MagicMock()
        emit_event(
            "step.start",
            trace_id="trace-abc",
            step_id="trace-abc:step:1",
            deterministic_nonce=1,
            severity="INFO",
            source="agent",
            payload={"objective": "test"},
            logger=logger,
        )
        logger.info.assert_called_once()

    def test_debug_severity_dispatches_to_debug_only(self) -> None:
        """DEBUG severity dispatches to logger.debug only."""
        logger = MagicMock()
        emit_event(
            "step.start",
            trace_id="trace-abc",
            step_id="trace-abc:step:1",
            deterministic_nonce=1,
            severity="DEBUG",
            source="agent",
            payload={"objective": "test"},
            logger=logger,
        )
        logger.debug.assert_called_once()
        logger.info.assert_not_called()
        logger.warning.assert_not_called()
        logger.error.assert_not_called()

    def test_info_severity_dispatches_to_info_only(self) -> None:
        """INFO severity dispatches to logger.info only."""
        logger = MagicMock()
        emit_event(
            "step.start",
            trace_id="trace-abc",
            step_id="trace-abc:step:1",
            deterministic_nonce=1,
            severity="INFO",
            source="agent",
            payload={"objective": "test"},
            logger=logger,
        )
        logger.debug.assert_not_called()
        logger.info.assert_called_once()
        logger.warning.assert_not_called()
        logger.error.assert_not_called()

    def test_warning_severity_dispatches_to_warning_only(self) -> None:
        """WARNING severity dispatches to logger.warning only."""
        logger = MagicMock()
        emit_event(
            "step.start",
            trace_id="trace-abc",
            step_id="trace-abc:step:1",
            deterministic_nonce=1,
            severity="WARNING",
            source="agent",
            payload={"objective": "test"},
            logger=logger,
        )
        logger.debug.assert_not_called()
        logger.info.assert_not_called()
        logger.warning.assert_called_once()
        logger.error.assert_not_called()

    def test_error_severity_dispatches_to_error_only(self) -> None:
        """ERROR severity dispatches to logger.error only."""
        logger = MagicMock()
        emit_event(
            "step.start",
            trace_id="trace-abc",
            step_id="trace-abc:step:1",
            deterministic_nonce=1,
            severity="ERROR",
            source="agent",
            payload={"objective": "test"},
            logger=logger,
        )
        logger.debug.assert_not_called()
        logger.info.assert_not_called()
        logger.warning.assert_not_called()
        logger.error.assert_called_once()

    def test_emitted_message_string_is_correct(self) -> None:
        """The emitted log message matches the canonical telemetry format."""
        logger = MagicMock()
        emit_event(
            "policy.evaluate",
            trace_id="trace-abc",
            step_id="trace-abc:step:2",
            deterministic_nonce=2,
            severity="INFO",
            source="policy_gate",
            payload={"mode": "EXECUTE"},
            logger=logger,
        )

        args, kwargs = logger.info.call_args
        self.assertEqual(args[0], "telemetry event emitted: policy.evaluate")

    def test_telemetry_event_key_present_in_extra(self) -> None:
        """Telemetry envelope is attached under extra['telemetry_event']."""
        logger = MagicMock()
        emit_event(
            "step.start",
            trace_id="trace-abc",
            step_id="trace-abc:step:1",
            deterministic_nonce=1,
            severity="INFO",
            source="agent",
            payload={"objective": "test"},
            logger=logger,
        )

        _, kwargs = logger.info.call_args
        self.assertIn("extra", kwargs)
        self.assertIn("telemetry_event", kwargs["extra"])

    def test_custom_logger_is_used_when_provided(self) -> None:
        """Explicit logger is used instead of the default eck-core logger."""
        logger = MagicMock()
        with patch("eck.telemetry.logging.getLogger") as mock_get_logger:
            emit_event(
                "step.start",
                trace_id="trace-abc",
                step_id="trace-abc:step:1",
                deterministic_nonce=1,
                severity="INFO",
                source="agent",
                payload={"objective": "test"},
                logger=logger,
            )

        logger.info.assert_called_once()
        mock_get_logger.assert_not_called()

    def test_default_eck_core_logger_used_when_none_provided(self) -> None:
        """emit_event defaults to logging.getLogger('eck-core')."""
        default_logger = MagicMock()
        with patch("eck.telemetry.logging.getLogger", return_value=default_logger) as mock_get_logger:
            emit_event(
                "step.start",
                trace_id="trace-abc",
                step_id="trace-abc:step:1",
                deterministic_nonce=1,
                severity="INFO",
                source="agent",
                payload={"objective": "test"},
            )

        mock_get_logger.assert_called_once_with("eck-core")
        default_logger.info.assert_called_once()

    def test_redact_hook_is_passed_through_to_build_event(self) -> None:
        """emit_event forwards redact_hook to build_event."""
        logger = MagicMock()

        def hook(payload: dict) -> dict:
            redacted = dict(payload)
            redacted["secret"] = "[REDACTED]"
            return redacted

        emit_event(
            "step.start",
            trace_id="trace-abc",
            step_id="trace-abc:step:1",
            deterministic_nonce=1,
            severity="INFO",
            source="agent",
            payload={"secret": "raw"},
            logger=logger,
            redact_hook=hook,
        )

        _, kwargs = logger.info.call_args
        event = kwargs["extra"]["telemetry_event"]
        self.assertEqual(event["payload"]["secret"], "[REDACTED]")

    def test_build_event_validation_failures_propagate(self) -> None:
        """emit_event does not swallow build_event/validation failures."""
        logger = MagicMock()
        with self.assertRaises(ValueError):
            emit_event(
                "not.real",
                trace_id="trace-abc",
                step_id="trace-abc:step:1",
                deterministic_nonce=1,
                severity="INFO",
                source="agent",
                payload={"objective": "test"},
                logger=logger,
            )


class TestTelemetryModuleConstants(unittest.TestCase):
    """Sanity checks for exported telemetry constants."""

    def test_allowed_event_types_contains_all_v1_events(self) -> None:
        """ALLOWED_EVENT_TYPES contains exactly the ADR-045 v1 event names."""
        self.assertEqual(
            ALLOWED_EVENT_TYPES,
            frozenset(
                {
                    "step.start",
                    "step.end",
                    "action.proposed",
                    "policy.evaluate",
                    "action.executed",
                    "epistemic.signal",
                }
            ),
        )

    def test_allowed_severities_contains_all_v1_levels(self) -> None:
        """ALLOWED_SEVERITIES contains exactly the supported log levels."""
        self.assertEqual(
            ALLOWED_SEVERITIES,
            frozenset({"DEBUG", "INFO", "WARNING", "ERROR"}),
        )


if __name__ == "__main__":
    unittest.main()
