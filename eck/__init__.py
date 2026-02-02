"""
Epistemic Control Kernel (ECK).

Minimal reliability-first control kernel for autonomous agents.
Provides explicit phase separation, epistemic signal recording,
multi-level drift detection, and policy-gated control.

v0.1.x line is behaviorally stable, test-complete, and invariant-locked.
"""

from .agent import ECKAgent
from .config import ECKConfig

__version__ = "0.1.1"

__all__ = [
    "ECKAgent",
    "ECKConfig",
]
