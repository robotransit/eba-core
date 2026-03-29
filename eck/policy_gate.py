# eck/policy_gate.py
"""
Policy gate contract and default implementation for the Epistemic Control
Kernel (ECK).

The policy gate is the exclusive consumer of epistemic signals for execution
control. It is the only component permitted to translate confidence and
structured policy context into a control decision.

Contract surface:
- input: (proposed_action, confidence, context)
- output: PolicyDecision
- invariants:
  - deterministic
  - side-effect free
  - no hidden inputs
  - no internal mutable state
  - no randomness
  - no external calls

PolicyGate is expressed as a structural Protocol rather than a nominal base
class. Any class implementing the required evaluate(...) signature satisfies
the contract.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, NamedTuple, Protocol, runtime_checkable


class ExecutionMode(Enum):
    """Execution mode returned by any ECK-compliant policy gate."""

    EXECUTE = "EXECUTE"
    RETRY = "RETRY"
    HALT = "HALT"
    DEGRADE = "DEGRADE"


class PolicyCause(Enum):
    """Coarse-grained cause category for a policy decision."""

    FAILURE_WINDOW = "FAILURE_WINDOW"
    CONFIDENCE = "CONFIDENCE"
    SAFETY = "SAFETY"
    DEFAULT = "DEFAULT"


class PolicyContext(NamedTuple):
    """
    Minimal typed context passed to every policy gate evaluation.

    This is the only structured context the gate may depend on.
    """

    user_id: str | None = None
    safety_level: str | None = None  # e.g. "high", "medium", "low"
    environment: str | None = None  # e.g. "childcare", "banking"
    failure_window_active: bool = False  # from confidence kernel


class PolicyDecision(NamedTuple):
    """Deterministic output of any ECK-compliant policy gate."""

    mode: ExecutionMode
    cause: PolicyCause
    reason: str
    rule_id: str  # MUST be non-empty, machine-stable identifier


@runtime_checkable
class PolicyGate(Protocol):
    """
    Structural contract for ECK-compliant policy gates.

    The policy gate is the exclusive consumer of the confidence signal.
    It is the only component allowed to map confidence -> control decision.

    All implementations MUST behave as a pure, referentially transparent
    function of:
        (proposed_action, confidence, context)

    This implies:
    - no internal mutable state
    - no randomness
    - no dependence on time or external environment
    - no hidden inputs or implicit context
    - no side effects (no I/O, no external calls)

    For identical inputs, the gate MUST return identical PolicyDecision
    outputs.

    This guarantees:
    - determinism
    - testability
    - auditability
    - strict preservation of epistemic isolation
    """

    def evaluate(
        self,
        proposed_action: Any,
        confidence: float,
        context: PolicyContext,
    ) -> PolicyDecision:
        """
        Evaluate the proposed action based on confidence and context.

        Must return a PolicyDecision with mode, cause, reason, and rule_id.
        """
        ...


class DefaultPolicyGate:
    """
    Minimal default policy gate for bootstrapping or fallback.

    Conservative baseline:
    - HALT on very low confidence or active failure window
    - RETRY on moderate uncertainty
    - DEGRADE on borderline confidence
    - EXECUTE only on high confidence

    proposed_action is accepted for contract compatibility but is not
    interpreted.

    Pure logic, deterministic, side-effect free.

    Domain scope:
    This gate is intentionally domain-agnostic. It does not inspect
    context.environment, context.safety_level, or any domain-specific
    fields. ADR-044 out-of-domain semantics do not apply here because
    this gate has no intended domain — it is a confidence-only baseline
    valid in any deployment context.
    """

    HALT_THRESHOLD = 0.40
    RETRY_THRESHOLD = 0.70

    # Execution threshold only — governs when the gate authorises execution.
    # Conceptually distinct from ECKConfig.goal_completion_threshold (ADR-041)
    # even though both default to 0.90. Do not implicitly couple these values.
    DEGRADE_THRESHOLD = 0.90

    def evaluate(
        self,
        proposed_action: Any,
        confidence: float,
        context: PolicyContext,
    ) -> PolicyDecision:
        """Default conservative evaluation logic."""
        # Strict validation (bool explicitly excluded)
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not (0.0 <= confidence <= 1.0)
        ):
            raise ValueError(
                f"Invalid confidence value: {confidence}. "
                "Must be int/float in [0.0, 1.0] and not bool."
            )

        # Rule 001: Failure window active -> immediate HALT
        if context.failure_window_active:
            return PolicyDecision(
                mode=ExecutionMode.HALT,
                cause=PolicyCause.FAILURE_WINDOW,
                reason="Failure window active — immediate halt required",
                rule_id="RULE_001",
            )

        # Rule 002: Very low confidence -> HALT
        if confidence < self.HALT_THRESHOLD:
            return PolicyDecision(
                mode=ExecutionMode.HALT,
                cause=PolicyCause.CONFIDENCE,
                reason=(
                    f"Confidence {confidence:.2f} below halt threshold "
                    f"{self.HALT_THRESHOLD}"
                ),
                rule_id="RULE_002",
            )

        # Rule 003: Moderate uncertainty -> RETRY
        if confidence < self.RETRY_THRESHOLD:
            return PolicyDecision(
                mode=ExecutionMode.RETRY,
                cause=PolicyCause.CONFIDENCE,
                reason=(
                    f"Confidence {confidence:.2f} below retry threshold "
                    f"{self.RETRY_THRESHOLD} — awaiting stability"
                ),
                rule_id="RULE_003",
            )

        # Rule 004: Borderline confidence -> DEGRADE
        if confidence < self.DEGRADE_THRESHOLD:
            return PolicyDecision(
                mode=ExecutionMode.DEGRADE,
                cause=PolicyCause.CONFIDENCE,
                reason=(
                    f"Confidence {confidence:.2f} below degrade threshold "
                    f"{self.DEGRADE_THRESHOLD} — using safer fallback"
                ),
                rule_id="RULE_004",
            )

        # Rule 005: High confidence -> EXECUTE
        return PolicyDecision(
            mode=ExecutionMode.EXECUTE,
            cause=PolicyCause.CONFIDENCE,
            reason=f"Confidence {confidence:.2f} sufficient for execution",
            rule_id="RULE_005",
        )
